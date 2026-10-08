"""Download historical ticks from Deriv WebSocket API into data/<symbol>_ticks.csv
with checkpoint recovery, automatic reconnection, duplicate detection, gap reporting,
automatic data quarantine, comprehensive provenance metadata, and coverage reporting.

Usage:  python collector.py [symbol] [total_ticks] [app_id]
        python collector.py --coverage
        Example: python collector.py R_75 500000
"""
import argparse
import asyncio
import csv
import glob
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Optional
import websockets
import pandas as pd

from config import DEFAULT_CONFIG, query_proposal_payout_async
from features import validate_data

DEFAULT_APP_ID = "1089"
PRIMARY_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
FALLBACK_URL = "wss://ws.derivws.com/websockets/v3"
BATCH = 5000  # ticks requested per batch


def analyze_gaps(ticks: List[Tuple[int, float]], threshold_seconds: float = 3.0) -> Dict[str, Any]:
    """Analyzes timestamp gaps in chronologically sorted tick series."""
    if len(ticks) < 2:
        return {"gap_count": 0, "max_gap_seconds": 0.0, "total_gap_seconds": 0.0, "gaps": []}

    gaps = []
    max_gap = 0.0
    total_gap_sec = 0.0

    for i in range(1, len(ticks)):
        delta = ticks[i][0] - ticks[i - 1][0]
        if delta > threshold_seconds:
            gaps.append((ticks[i - 1][0], ticks[i][0], delta))
            total_gap_sec += delta
            if delta > max_gap:
                max_gap = delta

    return {
        "gap_count": len(gaps),
        "max_gap_seconds": round(max_gap, 2),
        "total_gap_seconds": round(total_gap_sec, 2),
        "gaps_detected": len(gaps) > 0
    }


def quarantine_dataset(symbol: str, ticks: List[Tuple[int, float]], issues: List[str], data_dir: str) -> str:
    """Quarantines corrupt or non-compliant datasets to data/quarantine/."""
    quarantine_dir = os.path.join(data_dir, "quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)
    ts = int(time.time())
    q_file = os.path.join(quarantine_dir, f"{symbol}_quarantined_{ts}.csv")

    with open(q_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "price"])
        w.writerows(ticks)

    log_file = os.path.join(quarantine_dir, "quarantine_log.json")
    log_data = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                log_data = json.load(f)
        except Exception:
            log_data = []

    log_data.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "file": q_file,
        "tick_count": len(ticks),
        "issues": issues
    })

    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)

    print(f"\nWARNING: Dataset failed integrity check. Quarantined to: {q_file}")
    return q_file


def save_checkpoint(symbol: str, end_epoch: Any, collected_count: int, data_dir: str):
    """Saves collection progress checkpoint to resume gracefully on interruption."""
    cp_file = os.path.join(data_dir, f"{symbol}_checkpoint.json")
    cp_data = {
        "symbol": symbol,
        "end_epoch": end_epoch,
        "collected_count": collected_count,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with open(cp_file, "w") as f:
        json.dump(cp_data, f, indent=2)


def load_checkpoint(symbol: str, data_dir: str) -> Optional[Dict[str, Any]]:
    """Loads checkpoint if available."""
    cp_file = os.path.join(data_dir, f"{symbol}_checkpoint.json")
    if os.path.exists(cp_file):
        try:
            with open(cp_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


async def fetch_with_retry(symbol: str, total: int, endpoints: list, data_dir: str):
    """Fetches ticks with automatic reconnection, rate-limit backoff, and checkpointing."""
    end = "latest"
    connected_ws = None
    active_url = None
    chunks = []
    collected_count = 0

    # Check for existing checkpoint
    cp = load_checkpoint(symbol, data_dir)
    if cp and cp.get("end_epoch") != "latest":
        print(f"Resuming collection from checkpoint: {cp.get('collected_count', 0):,} ticks already tracked.")
        end = cp.get("end_epoch")

    max_retries = 5
    retry_count = 0

    while collected_count < total:
        if not connected_ws:
            for url in endpoints:
                print(f"Connecting to Deriv WebSocket endpoint: {url}")
                try:
                    ws = await websockets.connect(url, open_timeout=10, close_timeout=3)
                    await ws.send(json.dumps({"ticks_history": symbol, "style": "ticks", "count": 1, "end": "latest"}))
                    test_res = json.loads(await ws.recv())
                    if "error" not in test_res:
                        connected_ws = ws
                        active_url = url
                        print(f"Successfully connected to active gateway: {url}")
                        retry_count = 0
                        break
                    else:
                        await ws.close()
                except Exception as e:
                    print(f"Connection to {url} failed ({e}). Trying next gateway...")
                    continue

        if not connected_ws:
            retry_count += 1
            if retry_count > max_retries:
                raise ConnectionError(f"Unable to establish WebSocket connection after {max_retries} attempts.")
            backoff = min(30.0, 2.0 ** retry_count)
            print(f"Retrying connection in {backoff:.1f}s (Attempt {retry_count}/{max_retries})...")
            await asyncio.sleep(backoff)
            continue

        try:
            req_count = min(BATCH, total - collected_count + 50)
            await connected_ws.send(json.dumps({
                "ticks_history": symbol,
                "style": "ticks",
                "count": req_count,
                "end": end,
            }))
            raw = await asyncio.wait_for(connected_ws.recv(), timeout=12.0)
            msg = json.loads(raw)
            if "error" in msg:
                err_code = msg["error"].get("code", "")
                if "RateLimit" in err_code:
                    print("\nRate limit encountered. Backing off 5 seconds...")
                    await asyncio.sleep(5.0)
                    continue
                raise RuntimeError(msg["error"]["message"])

            h = msg.get("history")
            if not h or "times" not in h or "prices" not in h:
                break
            batch = list(zip(h["times"], h["prices"]))
            if not batch:
                break
            chunks.append(batch)
            collected_count += len(batch)
            end = batch[0][0] - 1  # step further back in time

            save_checkpoint(symbol, end, collected_count, data_dir)
            print(f"{collected_count:,} / {total:,} ticks collected", end="\r", flush=True)
            await asyncio.sleep(0.10)
        except Exception as e:
            print(f"\nConnection disrupted ({e}). Reconnecting...")
            try:
                await connected_ws.close()
            except Exception:
                pass
            connected_ws = None
            await asyncio.sleep(1.0)

    if connected_ws:
        await connected_ws.close()

    # Flatten chronologically and deduplicate (chunks were prepended backward in time)
    rows = []
    for c in reversed(chunks):
        rows.extend(c)

    # de-duplicate on epoch, keep strictly monotonic order
    seen = set()
    out = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)

    # Sort strictly by epoch ascending
    out.sort(key=lambda x: x[0])
    return out[-total:], active_url


def compute_file_hash(path: str) -> str:
    """Calculates SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def write_provenance(
    symbol: str,
    path: str,
    requested_total: int,
    actual_count: int,
    endpoint: str,
    app_id: str,
    start_epoch: int,
    end_epoch: int,
    live_payout: float,
    gap_info: Dict[str, Any],
    payout_source: str = "live_proposal"
):
    """Writes comprehensive provenance JSON metadata file verifying origin, gaps, and integrity."""
    prov_path = path.replace(".csv", "_provenance.json")
    file_hash = compute_file_hash(path)

    provenance = {
        "symbol": symbol,
        "requested_ticks": requested_total,
        "collected_ticks": actual_count,
        "request_time_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "app_id": app_id,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "start_time_utc": datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat(),
        "end_time_utc": datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat(),
        "duration_days": round((end_epoch - start_epoch) / 86400.0, 3),
        "live_proposal_payout": live_payout,
        "payout_source": payout_source,
        "sha256_checksum": file_hash,
        "gap_analysis": gap_info,
        "verified_source": "developers.deriv.com active WebSocket API",
        "integrity_status": "VERIFIED"
    }

    with open(prov_path, "w") as f:
        json.dump(provenance, f, indent=2)
    print(f"\nProvenance saved to: {prov_path}")


def report_all_historical_coverage(data_dir: str) -> List[Dict[str, Any]]:
    """Scans and reports coverage, timestamps, and integrity across all tick datasets in data/."""
    csv_files = glob.glob(os.path.join(data_dir, "*_ticks.csv")) + glob.glob(os.path.join(data_dir, "*_master.csv"))
    reports = []
    print("=== HISTORICAL TICK DATASET COVERAGE AUDIT ===")
    for path in sorted(csv_files):
        fname = os.path.basename(path)
        try:
            df = pd.read_csv(path)
            if "epoch" not in df.columns or "price" not in df.columns:
                continue
            count = len(df)
            if count == 0:
                continue
            min_epoch = int(df["epoch"].iloc[0])
            max_epoch = int(df["epoch"].iloc[-1])
            duration_days = round((max_epoch - min_epoch) / 86400.0, 2)
            min_iso = datetime.fromtimestamp(min_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            max_iso = datetime.fromtimestamp(max_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            is_valid, issues = validate_data(df)

            rep = {
                "file": fname,
                "ticks": count,
                "start": min_iso,
                "end": max_iso,
                "days": duration_days,
                "valid": is_valid,
                "issues_count": len(issues)
            }
            reports.append(rep)
            valid_tag = "VALID" if is_valid else "ISSUES"
            print(f"[{fname}] Ticks: {count:,} | Timespan: {duration_days} days ({min_iso} to {max_iso}) | Status: {valid_tag}")
        except Exception as e:
            print(f"[{fname}] Error reading dataset: {e}")
    return reports


def main():
    if "--coverage" in sys.argv:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "data")
        report_all_historical_coverage(data_dir)
        return

    symbol = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "R_75"
    total = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 50_000
    app_id = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else os.environ.get("DERIV_APP_ID", DEFAULT_APP_ID)
    custom_url = os.environ.get("DERIV_WS_URL")

    endpoints = []
    if custom_url:
        endpoints.append(custom_url)
    endpoints.extend([
        PRIMARY_URL,
        f"{FALLBACK_URL}?app_id={app_id}",
        f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
    ])

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, f"{symbol}_ticks.csv")

    print(f"Fetching {total:,} ticks for symbol: {symbol}...")
    try:
        ticks, active_url = asyncio.run(fetch_with_retry(symbol, total, endpoints, data_dir))
        if not ticks:
            print("No ticks received.")
            return

        # Data integrity audit before persistence
        test_df = pd.DataFrame(ticks, columns=["epoch", "price"])
        is_valid, issues = validate_data(test_df)
        if not is_valid:
            quarantine_dataset(symbol, ticks, issues, data_dir)
            return

        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["epoch", "price"])
            w.writerows(ticks)
        print(f"\nSaved {len(ticks):,} ticks to {csv_path}")

        # Gap analysis
        gap_info = analyze_gaps(ticks)

        # Query proposal quote for real payout
        live_quote = asyncio.run(query_proposal_payout_async(symbol=symbol, app_id=app_id))
        if live_quote is not None:
            live_payout = live_quote
            payout_source = "live_proposal"
        else:
            live_payout = DEFAULT_CONFIG.payout_ratio
            payout_source = "fallback_configured"

        # Write provenance file
        write_provenance(
            symbol=symbol,
            path=csv_path,
            requested_total=total,
            actual_count=len(ticks),
            endpoint=active_url,
            app_id=app_id,
            start_epoch=ticks[0][0],
            end_epoch=ticks[-1][0],
            live_payout=live_payout,
            gap_info=gap_info,
            payout_source=payout_source
        )

        # Remove checkpoint after successful write
        cp_file = os.path.join(data_dir, f"{symbol}_checkpoint.json")
        if os.path.exists(cp_file):
            try:
                os.remove(cp_file)
            except Exception:
                pass

    except Exception as err:
        print(f"\nError fetching ticks: {err}")
        print("Note: Check developers.deriv.com for WebSocket endpoint status.")


if __name__ == "__main__":
    main()
