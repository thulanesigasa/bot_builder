"""Fail-closed exploratory calibration protocol for separated SHADOW sessions.

This module freezes acquisition parameters only, not statistical confirmation.
No sessions are launched from here.
"""
import hashlib
import json
from datetime import datetime, timezone

from forward_shadow_engine import LIVE_EXECUTION_DISABLED, DECISION
from model_registry import AuthoritativeModelRegistry, MODEL_ID_CAUSAL_MOMENTUM_V1

SPEC = {
    "version": "1.9.2-exploratory-calibration",
    "status": "EXPLORATORY_ONLY_NO_CONFIRMATION",
    "market": "R_75",
    "contracts": ["CALL", "PUT", "RUNHIGH", "RUNLOW"],
    "durations_ticks": [2, 5],
    "session_count": 8,
    "session_duration_seconds": 75,
    "minimum_session_start_spacing_minutes": 60,
    "require_distinct_calendar_days": True,
    "minimum_distinct_utc_days": 2,
    "primary_metrics": ["strict_quoted_resolved_fraction", "resolved_fraction"],
    "secondary_metrics": ["per_session_return_sd", "inter_session_variability", "quote_latency_distribution"],
    "no_positive_ev_promotion": True,
    "no_purchases": True,
}

def frozen_protocol():
    if LIVE_EXECUTION_DISABLED is not True or DECISION != "NO_TRADE":
        raise RuntimeError("EXECUTION_NOT_DISABLED")
    record = AuthoritativeModelRegistry().get_model_record(MODEL_ID_CAUSAL_MOMENTUM_V1)
    if record is None or not record.artifact_checksum:
        raise RuntimeError("MODEL_NOT_VERIFIED")
    data = {**SPEC, "model_id": record.model_id, "model_sha256": record.artifact_checksum}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**data, "protocol_sha256": digest}

def check_session_schedule(utc_iso_starts):
    if len(utc_iso_starts) != SPEC["session_count"]:
        return False, "WRONG_SESSION_COUNT"
    try:
        times = [datetime.fromisoformat(x.replace("Z", "+00:00")) for x in utc_iso_starts]
    except (ValueError, AttributeError, TypeError):
        return False, "INVALID_START_TIME"
    if any(t.tzinfo is None or t.utcoffset().total_seconds() != 0 for t in times):
        return False, "NON_UTC_START"
    if any((b-a).total_seconds() < 60*SPEC["minimum_session_start_spacing_minutes"] for a,b in zip(times,times[1:])):
        return False, "SESSIONS_NOT_SEPARATED"
    if len({t.date() for t in times}) < SPEC["minimum_distinct_utc_days"]:
        return False, "INSUFFICIENT_DISTINCT_DAYS"
    return True, "EXPLORATORY_SCHEDULE_ACCEPTED"
