"""Regression tests for prospective broker quote attribution.

No network calls and no purchasing.
"""
import time

from forward_shadow_engine import DerivLiveShadowCollector


def _collector(tmp_path):
    return DerivLiveShadowCollector(
        target_markets=["R_75", "R_100"],
        db_path=str(tmp_path / "quotes.db"),
    )


def _response():
    return {
        "id": "proposal-1", "ask_price": 2.0, "payout": 3.91,
        "spot": 100.0, "spot_time": 1791000000,
        "longcode": "Unhelpful or misleading longcode: Volatility 75",
    }


def test_unmatched_proposal_rejected(tmp_path):
    c = _collector(tmp_path)
    c._handle_incoming_proposal(_response(), time.time(), req_id=123)
    assert c.proposals_captured_count == 0
    c.db.close()


def test_correlated_proposal_uses_request_terms_not_longcode(tmp_path):
    c = _collector(tmp_path)
    now = time.time()
    c._pending_quote_requests[7] = {
        "symbol": "R_100", "family": "RISE_FALL", "direction": "PUT",
        "duration": 2, "request_timestamp": now - 0.1,
    }
    c._handle_incoming_proposal(_response(), now, req_id=7)
    with c.db._get_connection() as conn:
        q = conn.execute("SELECT * FROM broker_proposals WHERE proposal_id='proposal-1'").fetchone()
        assert q["underlying_symbol"] == "R_100"
        assert q["contract_type"] == "PUT"
        assert q["duration"] == 2
        assert q["request_timestamp"] == now - 0.1
    assert c.proposals_captured_count == 1
    c.db.close()


def test_mismatched_echo_request_is_rejected(tmp_path):
    c = _collector(tmp_path)
    c._pending_quote_requests[8] = {
        "symbol": "R_100", "family": "RISE_FALL", "direction": "PUT",
        "duration": 2, "request_timestamp": 100.0,
    }
    c._handle_incoming_proposal(
        _response(), 101.0, req_id=8,
        echo_req={"contract_type": "CALL", "underlying_symbol": "R_75",
                  "duration": 5, "duration_unit": "t"},
    )
    assert c.proposals_captured_count == 0
    c.db.close()


def test_bad_quote_prices_are_not_persisted(tmp_path):
    c = _collector(tmp_path)
    c._pending_quote_requests[9] = {
        "symbol": "R_75", "family": "RISE_FALL", "direction": "CALL",
        "duration": 2, "request_timestamp": 100.0,
    }
    bad = _response()
    bad["payout"] = 0
    c._handle_incoming_proposal(bad, 101, req_id=9)
    assert c.proposals_captured_count == 0
    c.db.close()
