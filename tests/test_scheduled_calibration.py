"""No unscheduled, repeated, or confirmation-equivalent calibration runs."""
from datetime import datetime, timedelta, timezone
import pytest
from scheduled_calibration import SLOTS_UTC, MAX_START_DELAY, resolve_window
from calibration_protocol import check_session_schedule

def test_slots_are_preregistered_and_separated():
    assert len(SLOTS_UTC) == 8
    assert check_session_schedule([x.isoformat() for x in SLOTS_UTC])[0]
    assert len({x.date() for x in SLOTS_UTC}) == 2
    assert all(y-x >= timedelta(hours=4) for x,y in zip(SLOTS_UTC, SLOTS_UTC[1:]))

def test_resolve_exact_first_and_last_window():
    for i in (1,8):
        w=resolve_window(SLOTS_UTC[i-1]+timedelta(minutes=12))
        assert w["index"] == i
        assert w["status"] == "EXPLORATORY_ONLY_NO_CONFIRMATION"
        assert w["no_purchases"] is True
        assert len(w["protocol_sha256"]) == 64

def test_reject_before_after_or_between_windows():
    for now in (SLOTS_UTC[0]-timedelta(seconds=1),
                SLOTS_UTC[0]+MAX_START_DELAY,
                SLOTS_UTC[0]+timedelta(hours=2),
                SLOTS_UTC[-1]+timedelta(days=1)):
        with pytest.raises(ValueError, match="OUTSIDE_PREREGISTERED"):
            resolve_window(now)

def test_reject_non_utc_and_naive_timestamps():
    for now in (datetime(2026,10,13,0,15),
                datetime(2026,10,13,2,15,tzinfo=timezone(timedelta(hours=2)))):
        with pytest.raises(ValueError, match="SCHEDULE_REQUIRES_UTC"):
            resolve_window(now)
