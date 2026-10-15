"""Historical calibration must be reconciled from observed, eligible slots only."""
import json
from pathlib import Path


def reconcile_ledger(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = data["expected_slots_utc"]
    accepted = [r for r in data["observed_workflow_runs"]
                if r["conclusion"] == "success" and r.get("accepted_slot") is not None]
    indices = [r["accepted_slot"] for r in accepted]
    if len(set(expected)) != 8 or len(expected) != 8:
        raise ValueError("INVALID_EXPECTED_SLOTS")
    if len(indices) != len(set(indices)) or any(not isinstance(i, int) or not 1 <= i <= 8 for i in indices):
        raise ValueError("DUPLICATE_OR_INVALID_ACCEPTED_SLOT")
    if any(r.get("gate") != "PREREGISTERED_WINDOW" or
           r.get("replay_matches") != r.get("observations_resolved") or
           not r.get("evidence_artifact_id") for r in accepted):
        raise ValueError("ACCEPTED_SESSION_MISSING_EVIDENCE")
    missing = [i for i in range(1, 9) if i not in indices]
    complete = len(missing) == 0
    return {
        "expected": 8,
        "scheduled_attempts_observed": len(data["observed_workflow_runs"]),
        "accepted_sessions": len(accepted),
        "missing_accepted_slots": missing,
        "complete": complete,
        "confirmation_authorized": False,
        "research_status": "EXPLORATORY_CALIBRATION_COMPLETE" if complete
                           else "INCOMPLETE_EXPLORATORY_CALIBRATION",
    }


if __name__ == "__main__":
    print(json.dumps(reconcile_ledger(
        "reports/calibration_20261013_14_run_ledger.json"), sort_keys=True))
