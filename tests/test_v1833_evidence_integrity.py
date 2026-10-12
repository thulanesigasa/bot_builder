"""Focused V1.8.3.3 regression tests; no trading or external connections."""
import sqlite3
import time

from forward_shadow_engine import (
    ForwardResearchDatabase, ForwardObservationRecord, DerivLiveShadowCollector,
    FAMILY_RISE_FALL, DIRECTION_CALL, DIRECTION_RUNLOW,
    FAMILY_ONLY_UPS_DOWNS, LIVE_EXECUTION_DISABLED, DECISION,
)
from strict_cohort_validator import StrictCohortAuthorityValidator


def test_missing_proposal_row_fails_closed(tmp_path):
    db = ForwardResearchDatabase(str(tmp_path / "missing_proposal.db"))
    with sqlite3.connect(db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        validator = StrictCohortAuthorityValidator(db_conn=conn)
        decision = validator.validate_observation({
            "observation_id": "missing-proposal",
            "session_id": "test",
            "symbol": "R_75",
            "source_classification": "BROKER_API_LIVE_CAPTURE",
            "signal_epoch": 1700000000,
            "proposal_id": "DOES_NOT_EXIST",
            "ask_price": 2.0,
            "total_payout": 3.91,
            "decision_timestamp": 1700000000.0,
            "contract_type": "CALL",
            "contract_family": "RISE_FALL",
            "duration_ticks": 2,
        })
        assert not decision.quote_verification_verdict
        assert not decision.is_cohort_c_eligible
        assert any("not found" in reason for reason in decision.rejection_reasons)
    db.close()


def test_missing_source_connection_cannot_certify():
    decision = StrictCohortAuthorityValidator(db_conn=None).validate_observation({
        "observation_id": "no-db",
        "symbol": "R_75",
        "signal_epoch": 1700000000,
        "source_classification": "BROKER_API_LIVE_CAPTURE",
    })
    assert not decision.source_authenticity_verdict
    assert not decision.is_cohort_c_eligible


def test_commit_marker_recorded_only_after_insert(tmp_path):
    db = ForwardResearchDatabase(str(tmp_path / "commit.db"))
    observation = ForwardObservationRecord(
        observation_id="obs1", session_id="s1", symbol="R_75",
        contract_family=FAMILY_RISE_FALL, contract_type=DIRECTION_CALL,
        duration_ticks=2, decision_timestamp=time.time(),
        signal_epoch=1700000000, signal_price=100.0,
        predicted_prob=0.5, model_version="test",
    )
    db.insert_observation(observation)
    upper_bound = time.time()
    db.record_verified_commit_timestamp("obs1", upper_bound)
    with sqlite3.connect(db.db_path) as conn:
        recorded = conn.execute(
            "SELECT journal_commit_timestamp FROM forward_observations WHERE observation_id = ?",
            ("obs1",),
        ).fetchone()[0]
    assert recorded == upper_bound
    db.close()


def test_runlow_in_shadow_prediction_matrix(tmp_path):
    collector = DerivLiveShadowCollector(target_markets=["R_75"], db_path=str(tmp_path / "runlow.db"))
    assert LIVE_EXECUTION_DISABLED is True and DECISION == "NO_TRADE"
    assert any(
        fam == FAMILY_ONLY_UPS_DOWNS and direction == DIRECTION_RUNLOW
        for _, fam, direction, _ in collector.proposal_schedule
    )
    collector.db.close()
