"""Strict per-observation quoted SHADOW economics.

Read-only report built from the authoritative cohort validator. No Deriv
connection, orders, model fitting, or promotion of historic records.
"""
import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strict_cohort_validator import StrictCohortAuthorityValidator
from forward_shadow_engine import COHORT_C, LIVE_EXECUTION_DISABLED, DECISION

assert LIVE_EXECUTION_DISABLED and DECISION == "NO_TRADE"


def assess_database(path):
    report = {"database": str(path), "exists": Path(path).is_file(),
              "sessions": [], "status": "MISSING_DATABASE"}
    if not report["exists"]:
        return report
    with sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        validator = StrictCohortAuthorityValidator(db_conn=conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM forward_observations ORDER BY session_id, decision_timestamp, observation_id"
        )]
        sessions = defaultdict(list)
        for row in rows:
            sessions[row["session_id"]].append(row)
        for sid, observations in sorted(sessions.items()):
            hypotheses = defaultdict(list)
            failures = defaultdict(int)
            accepted_ids = []
            resolved = sum(o["outcome_status"] == "OUTCOME_RESOLVED" for o in observations)
            pending_quoted = sum(o["outcome_status"] != "OUTCOME_RESOLVED" and bool(o["proposal_id"]) for o in observations)
            for o in observations:
                verdict = validator.validate_observation(o, conn)
                if verdict.final_evidence_cohort != COHORT_C:
                    for reason in verdict.rejection_reasons:
                        failures[reason] += 1
                    continue
                # Recompute from the source proposal; do not trust copied
                # observation ask/payout or a precomputed hypothetical return.
                proposal = conn.execute(
                    "SELECT * FROM broker_proposals WHERE proposal_id = ?",
                    (o["proposal_id"],),
                ).fetchone()
                if proposal is None:
                    raise AssertionError("Authority validator accepted a missing proposal")
                ask, payout = float(proposal["ask_price"]), float(proposal["total_payout"])
                p, win = float(o["predicted_prob"]), int(o["observed_outcome"])
                if not all(map(math.isfinite, (ask, payout, p))) or not (ask > 0 and payout > 0 and 0 <= p <= 1):
                    raise AssertionError("Authority validator accepted non-finite economics")
                key = (o["symbol"], o["contract_family"], o["contract_type"], o["duration_ticks"])
                hypotheses[key].append({
                    "observation_id": o["observation_id"], "decision_timestamp": o["decision_timestamp"],
                    "win": win, "ask": ask, "payout": payout,
                    "break_even": ask / payout, "predicted_ev": p * payout - ask,
                    "hypothetical_return": win * payout - ask,
                })
                accepted_ids.append(o["observation_id"])
            results = []
            for (symbol, family, direction, duration), records in sorted(hypotheses.items()):
                n = len(records)
                wins = sum(r["win"] for r in records)
                returns = [r["hypothetical_return"] for r in records]
                mean_return = sum(returns) / n
                results.append({
                    "symbol": symbol, "family": family, "contract": direction,
                    "duration_ticks": duration, "eligible_n": n, "wins": wins,
                    "losses": n-wins, "win_rate": wins/n,
                    "mean_ask": sum(r["ask"] for r in records)/n,
                    "mean_break_even": sum(r["break_even"] for r in records)/n,
                    "mean_predicted_ev": sum(r["predicted_ev"] for r in records)/n,
                    "total_hypothetical_return": sum(returns),
                    "mean_hypothetical_return": mean_return,
                    "sample_warning": "UNDERPOWERED_EXPLORATORY_SAMPLE",
                    "observation_ids": [r["observation_id"] for r in records],
                })
            report["sessions"].append({
                "session_id": sid, "committed": len(observations),
                "resolved": resolved, "unresolved": len(observations)-resolved,
                "unresolved_with_quotes": pending_quoted,
                "strict_eligible": len(accepted_ids),
                "strict_eligible_observation_ids": accepted_ids,
                "hypotheses": results, "rejection_reasons": dict(failures),
                "research_verdict": "NO_VALIDATED_POSITIVE_EV_EDGE",
            })
    report["status"] = "AUDITED"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", required=True)
    parser.add_argument("--output", default="strict-quote-economics.json")
    args = parser.parse_args()
    reports = [assess_database(p) for p in args.db]
    Path(args.output).write_text(json.dumps(reports, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    for r in reports:
        for s in r["sessions"]:
            print("STRICT_QUOTE_ECONOMICS", json.dumps({
                "session_id": s["session_id"], "strict_eligible": s["strict_eligible"],
                "unresolved_with_quotes": s["unresolved_with_quotes"],
                "hypotheses": [{k: h[k] for k in ("symbol","family","contract","duration_ticks","eligible_n","wins","mean_predicted_ev","mean_hypothetical_return")} for h in s["hypotheses"]],
            }, sort_keys=True), flush=True)
    if any(r["status"] != "AUDITED" for r in reports):
        raise SystemExit("SOURCE_DATABASE_MISSING")


if __name__ == "__main__":
    main()
