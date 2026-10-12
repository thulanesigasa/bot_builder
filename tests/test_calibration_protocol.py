"""Separated calibration sessions must be temporally distinct and safe."""
from datetime import datetime, timedelta, timezone
from calibration_protocol import SPEC, frozen_protocol, check_session_schedule
from forward_shadow_engine import LIVE_EXECUTION_DISABLED, DECISION

def test_protocol_never_authorizes_confirmation_or_purchases():
    p=frozen_protocol()
    assert LIVE_EXECUTION_DISABLED is True and DECISION=="NO_TRADE"
    assert p["no_positive_ev_promotion"] and p["no_purchases"]
    assert len(p["protocol_sha256"])==64
    assert frozen_protocol()==p

def test_consecutive_sessions_rejected():
    start=datetime(2026,10,13,tzinfo=timezone.utc)
    times=[(start+timedelta(seconds=76*i)).isoformat() for i in range(8)]
    assert check_session_schedule(times)[0] is False

def test_distributed_calibration_schedule_accepted():
    start=datetime(2026,10,13,tzinfo=timezone.utc)
    times=[(start+timedelta(hours=4*i)).isoformat() for i in range(8)]
    assert check_session_schedule(times)==(True,"EXPLORATORY_SCHEDULE_ACCEPTED")

def test_missing_sessions_rejected():
    assert check_session_schedule([])==(False,"WRONG_SESSION_COUNT")
