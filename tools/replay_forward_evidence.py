"""Read-only independent replay of recorded SHADOW outcomes from broker_ticks.

This audit deliberately does not trust forward_spots_json or stored outcome labels.
It never contacts Deriv, never issues proposals, and never buys a contract.
"""
import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

FAMILIES = {
    ("RISE_FALL", "CALL"), ("RISE_FALL", "PUT"),
    ("ONLY_UPS_ONLY_DOWNS", "RUNHIGH"), ("ONLY_UPS_ONLY_DOWNS", "RUNLOW"),
}

def _outcome(entry, forward, family, direction):
    if family == "RISE_FALL":
        end = forward[-1]
        return int(end > entry) if direction == "CALL" else int(end < entry)
    series = [entry] + forward
    if direction == "RUNHIGH":
        return int(all(b > a for a, b in zip(series, series[1:])))
    return int(all(b < a for a, b in zip(series, series[1:])))

def replay_database(db_path):
    path = Path(db_path)
    result = {
        "database": str(path), "available": path.is_file(),
        "status": "MISSING_SOURCE_DB", "checked": 0, "matches": 0,
        "mismatches": 0, "unverifiable": 0, "pending": 0,
        "reasons": {}, "examples": [],
        "authority_note": "Local SQLite broker_ticks replay; not independent broker-source authentication",
    }
    if not path.is_file():
        return result
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"broker_ticks", "forward_observations"}.issubset(tables):
            result["status"] = "MISSING_SOURCE_TABLE"
            return result
        observations = [dict(x) for x in cur.execute("SELECT * FROM forward_observations ORDER BY session_id, decision_timestamp, observation_id")]
        ticks_by_symbol = {}
        ticks = cur.execute(
            "SELECT id, symbol, epoch, quote, received_timestamp FROM broker_ticks ORDER BY received_timestamp, id"
        ).fetchall()
        for tick in ticks:
            ticks_by_symbol.setdefault(tick["symbol"], []).append(dict(tick))
        reasons = Counter()
        for obs in observations:
            if obs["outcome_status"] != "OUTCOME_RESOLVED":
                result["pending"] += 1
                continue
            result["checked"] += 1
            cause = None
            predicted = None
            family, direction = obs["contract_family"], obs["contract_type"]
            duration = obs["duration_ticks"]
            if (family, direction) not in FAMILIES or not isinstance(duration, int) or duration < 1:
                cause = "UNKNOWN_CONTRACT"
            else:
                stream = ticks_by_symbol.get(obs["symbol"], [])
                # Match the signal tick by both broker epoch and captured price;
                # ambiguous matches must not be silently resolved.
                signal_candidates = [
                    (idx, tick) for idx, tick in enumerate(stream)
                    if tick["epoch"] == obs["signal_epoch"]
                    and abs(tick["quote"] - obs["signal_price"]) < 1e-8
                    and tick["received_timestamp"] <= obs["decision_timestamp"] + 0.001
                ]
                if len(signal_candidates) != 1:
                    cause = "MISSING_OR_AMBIGUOUS_SIGNAL_TICK"
                else:
                    signal_idx, signal_tick = signal_candidates[0]
                    future = [
                        t for t in stream[signal_idx + 1:]
                        if t["epoch"] > obs["signal_epoch"]
                        and t["received_timestamp"] > signal_tick["received_timestamp"]
                    ]
                    # Entry = first subsequent broker tick; expiration is D ticks after entry.
                    if len(future) < duration + 1:
                        cause = "INCOMPLETE_REPLAY_TICKS"
                    else:
                        entry = future[0]
                        sequence = future[1:duration + 1]
                        predicted = _outcome(entry["quote"], [t["quote"] for t in sequence], family, direction)
                        if (obs["entry_epoch"] != entry["epoch"]
                            or obs["expiry_epoch"] != sequence[-1]["epoch"]
                            or abs(obs["entry_spot"] - entry["quote"]) > 1e-8
                            or abs(obs["expiry_spot"] - sequence[-1]["quote"]) > 1e-8
                            or predicted != obs["observed_outcome"]):
                            cause = "INDEPENDENT_TICK_REPLAY_DISAGREES"
            if cause:
                result["unverifiable" if cause != "INDEPENDENT_TICK_REPLAY_DISAGREES" else "mismatches"] += 1
                reasons[cause] += 1
                if len(result["examples"]) < 15:
                    result["examples"].append({
                        "observation_id": obs["observation_id"],
                        "reason": cause, "stored_outcome": obs["observed_outcome"],
                        "replayed_outcome": predicted,
                    })
            else:
                result["matches"] += 1
        result["reasons"] = dict(reasons)
        result["status"] = (
            "FULL_REPLAY_VERIFIED" if result["checked"] > 0
            and result["mismatches"] == result["unverifiable"] == 0
            else "REPLAY_INTEGRITY_INCOMPLETE"
        )
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", required=True, help="Read-only SQLite evidence database")
    parser.add_argument("--output", default="forward-tick-replay-audit.json")
    args = parser.parse_args()
    reports = [replay_database(p) for p in args.db]
    Path(args.output).write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    for report in reports:
        print("REPLAY_AUDIT", json.dumps({
            k: report[k] for k in ("database", "status", "checked", "matches", "mismatches", "unverifiable", "pending", "reasons")
        }, sort_keys=True), flush=True)
    # Keep the audit visible even for legacy evidence; require separate review
    # rather than modifying stored results or pretending replay passed.
    if any(r["status"] != "FULL_REPLAY_VERIFIED" for r in reports):
        raise SystemExit(2)

if __name__ == "__main__":
    main()
