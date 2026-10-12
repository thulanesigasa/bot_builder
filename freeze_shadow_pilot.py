"""Deterministic, SHADOW-only preregistration integrity gate.

The pilot is for feasibility/quote coverage, NOT positive-EV confirmation.
A final powered protocol requires independent preregistration before collection.
"""
import argparse
import hashlib
import json
from pathlib import Path

from forward_shadow_engine import LIVE_EXECUTION_DISABLED, DECISION
from model_registry import AuthoritativeModelRegistry, MODEL_ID_CAUSAL_MOMENTUM_V1

PILOT = {
    "protocol_version": "1.9.1-exploratory-feasibility",
    "study_type": "EXPLORATORY_FEASIBILITY_PILOT_NOT_CONFIRMATION",
    "mode": "SHADOW_RESEARCH_ONLY",
    "decision": "NO_TRADE",
    "markets": ["R_75"],
    "contracts": ["CALL", "PUT", "RUNHIGH", "RUNLOW"],
    "durations_ticks": [2, 5],
    "primary_metric": "strict_cohort_c_quote_coverage",
    "secondary_metrics": [
        "model_predicted_ev_per_individual_matched_quote",
        "outcome_replay_integrity",
        "model_provenance_integrity",
        "hypothetical_return_exploratory_only",
    ],
    "primary_hypothesis": None,
    "confirmation_activated": False,
    "pilot_fixed_sessions": 4,
    "pilot_session_seconds": 75,
    "pilot_early_stop_conditions": [
        "live_safety_invariant_violation",
        "broker_request_correlation_failure",
        "missing_commit_timestamps",
        "contract_outcome_replay_failure",
        "quote_authenticity_failure",
    ],
    "profitability_promotion_prohibited": True,
    "predeclared_verdict": "INSUFFICIENT_PROSPECTIVE_EVIDENCE",
}

def freeze_manifest():
    if LIVE_EXECUTION_DISABLED is not True or DECISION != "NO_TRADE":
        raise RuntimeError("Purchase execution invariant violated")
    registry = AuthoritativeModelRegistry()
    rec = registry.get_model_record(MODEL_ID_CAUSAL_MOMENTUM_V1)
    if rec is None or not rec.artifact_checksum:
        raise RuntimeError("Missing baseline model identity")
    payload = {**PILOT, "model_id": MODEL_ID_CAUSAL_MOMENTUM_V1,
               "model_checksum": rec.artifact_checksum}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "protocol_sha256": hashlib.sha256(canonical).hexdigest()}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="pilot-protocol.json")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    protocol = freeze_manifest()
    target = Path(a.output)
    if a.verify:
        if not target.is_file() or json.loads(target.read_text(encoding="utf-8")) != protocol:
            raise SystemExit("PREREGISTRATION_MANIFEST_CHANGED_OR_MISSING")
        print("PILOT_PROTOCOL_FROZEN", protocol["protocol_sha256"])
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
        print("PILOT_PROTOCOL_DRAFT_FROZEN", protocol["protocol_sha256"])

if __name__ == "__main__":
    main()
