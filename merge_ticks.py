"""Tick merging and continuity engine for Deriv historical time series.
Merges newly collected ticks into data/<symbol>_master.csv, enforces duplicate removal,
audits for conflicting price mutations on identical epochs, and analyzes time gaps (>10s).

Usage:
    python merge_ticks.py [symbol]
    Example: python merge_ticks.py R_75
"""
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Tuple, List, Dict
import pandas as pd


def compute_file_hash(path: str) -> str:
    """Calculates SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def merge_symbol_ticks(symbol: str = "R_75", data_dir: str = "data") -> Dict:
    incoming_path = os.path.join(data_dir, f"{symbol}_ticks.csv")
    master_path = os.path.join(data_dir, f"{symbol}_master.csv")
    master_prov_path = os.path.join(data_dir, f"{symbol}_master_provenance.json")

    if not os.path.exists(incoming_path):
        raise FileNotFoundError(f"Incoming ticks file not found: {incoming_path}. Run collector.py first.")

    print(f"Reading incoming ticks from: {incoming_path}")
    incoming_df = pd.read_csv(incoming_path)
    incoming_df["epoch"] = incoming_df["epoch"].astype(int)
    incoming_df["price"] = incoming_df["price"].astype(float)
    incoming_count = len(incoming_df)

    if os.path.exists(master_path):
        print(f"Loading existing master archive: {master_path}")
        master_df = pd.read_csv(master_path)
        master_df["epoch"] = master_df["epoch"].astype(int)
        master_df["price"] = master_df["price"].astype(float)
        prev_master_count = len(master_df)
        combined_df = pd.concat([master_df, incoming_df], ignore_index=True)
    else:
        print(f"No existing master archive found. Initializing new master from incoming ticks.")
        prev_master_count = 0
        combined_df = incoming_df.copy()

    # 1. Integrity check: Stop if any epoch appears with two different prices
    price_by_epoch = {}
    conflicts = []
    for row in combined_df.itertuples(index=False):
        ep, pr = row.epoch, row.price
        if ep in price_by_epoch and price_by_epoch[ep] != pr:
            conflicts.append((ep, price_by_epoch[ep], pr))
            if len(conflicts) >= 5:
                break
        price_by_epoch[ep] = pr

    if conflicts:
        err_msg = "\n".join([f"  Epoch {ep}: recorded price {p1} != new price {p2}" for ep, p1, p2 in conflicts])
        raise ValueError(
            f"CRITICAL INTEGRITY ERROR: Detected price contradiction on identical epoch timestamps!\n{err_msg}\n"
            f"Halting merge to protect historical data integrity."
        )

    # 2. Deduplicate exact duplicate rows and sort chronologically
    dedup_df = combined_df.drop_duplicates(subset=["epoch"]).sort_values("epoch").reset_index(drop=True)
    total_master_count = len(dedup_df)
    new_ticks_added = total_master_count - prev_master_count

    # 3. Analyze time continuity and gaps over 10 seconds
    epochs = dedup_df["epoch"]
    gaps = epochs.diff()
    large_gaps = gaps[gaps > 10.0]
    large_gap_count = len(large_gaps)
    max_gap_sec = float(large_gaps.max()) if large_gap_count > 0 else 0.0

    # Save clean master CSV
    dedup_df.to_csv(master_path, index=False)
    file_hash = compute_file_hash(master_path)

    start_ep = int(dedup_df["epoch"].iloc[0])
    end_ep = int(dedup_df["epoch"].iloc[-1])
    start_dt = datetime.fromtimestamp(start_ep, tz=timezone.utc).isoformat()
    end_dt = datetime.fromtimestamp(end_ep, tz=timezone.utc).isoformat()

    stats = {
        "symbol": symbol,
        "incoming_ticks": incoming_count,
        "previous_master_ticks": prev_master_count,
        "new_ticks_added": new_ticks_added,
        "total_master_ticks": total_master_count,
        "start_epoch": start_ep,
        "end_epoch": end_ep,
        "start_time_utc": start_dt,
        "end_time_utc": end_dt,
        "gaps_over_10s_count": large_gap_count,
        "max_gap_seconds": max_gap_sec,
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "sha256_checksum": file_hash
    }

    # Write master provenance
    with open(master_prov_path, "w") as f:
        json.dump(stats, f, indent=2)

    # Print summary report
    print("\n" + "=" * 60)
    print("           TICK MERGE & CONTINUITY REPORT")
    print("=" * 60)
    print(f"Symbol:                 {symbol}")
    print(f"Incoming Ticks:         {incoming_count:,}")
    print(f"Previous Master Ticks:  {prev_master_count:,}")
    print(f"New Unique Ticks Added: {new_ticks_added:,}")
    print(f"Total Master Ticks:     {total_master_count:,}")
    print(f"Time Range (UTC):       {start_dt[:19]}  -->  {end_dt[:19]}")
    print("-" * 60)
    print(f"Gaps > 10 seconds:      {large_gap_count} gap(s)")
    if large_gap_count > 0:
        print(f"Largest Gap Duration:   {max_gap_sec:.1f}s ({max_gap_sec / 3600:.2f} hours)")
        # Show top 3 largest gap locations
        top_gaps = dedup_df.loc[large_gaps.index[:3]]
        for idx, row in top_gaps.iterrows():
            gap_sz = gaps.loc[idx]
            gap_time = datetime.fromtimestamp(row.epoch, tz=timezone.utc).isoformat()[:19]
            print(f"  - At {gap_time} UTC: {gap_sz:.1f}s pause")
    else:
        print("Continuity:             PERFECT (zero gaps > 10s)")
    print(f"Master Archive Path:    {master_path}")
    print(f"SHA-256 Checksum:       {file_hash[:16]}...")
    print("=" * 60 + "\n")

    return stats


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "R_75"
    try:
        merge_symbol_ticks(symbol)
    except Exception as e:
        print(f"\nError during tick merge: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
