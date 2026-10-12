"""Time-locked, non-purchasing calibration windows.

All eight scheduled windows were chosen prospectively. This module never
contacts a broker and cannot authorize a confirmation experiment.
"""
from datetime import datetime, timedelta, timezone
from calibration_protocol import check_session_schedule, frozen_protocol

SLOTS_UTC = [
    datetime(2026, 10, day, hour, 15, tzinfo=timezone.utc)
    for day in (13, 14) for hour in (0, 4, 8, 12)
]
MAX_START_DELAY = timedelta(minutes=55)

def resolve_window(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("SCHEDULE_REQUIRES_UTC")
    protocol = frozen_protocol()
    assert protocol["session_count"] == 8
    valid, reason = check_session_schedule([t.isoformat() for t in SLOTS_UTC])
    if not valid:
        raise RuntimeError("INVALID_PREREGISTERED_SLOTS: " + reason)
    selected = [(i, s) for i, s in enumerate(SLOTS_UTC, 1)
                if s <= now < s + MAX_START_DELAY]
    if len(selected) != 1:
        raise ValueError("OUTSIDE_PREREGISTERED_SESSION_WINDOW")
    idx, slot = selected[0]
    return {
        "calibration_id": "CAL_R75_20261013_20261014",
        "index": idx,
        "slot_utc": slot.isoformat(),
        "protocol_sha256": protocol["protocol_sha256"],
        "status": "EXPLORATORY_ONLY_NO_CONFIRMATION",
        "no_purchases": True,
    }
