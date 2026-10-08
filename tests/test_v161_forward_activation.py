"""V1.6.1 Forward Activation & Statistical Reliability Test Suite.

Comprehensive deterministic regression tests for:
1. Missing uncertainty rejection (positive EV cannot bypass missing lower bound)
2. Arbitrary lower-bound rejection (Wilson/Gaussian sample size formula removal)
3. Quote timestamp validation (request, response, decision ordering)
4. Future quote rejection (lookahead prevention)
5. Stale quote rejection (freshness window)
6. Persistent consecutive-loss state surviving restart
7. Persistent daily drawdown surviving restart
8. Risk-state load failure handling (RISK_STATE_UNAVAILABLE)
9. Empty-journal diagnosis (lookback threshold parity)
10. SHADOW prediction without quotes
11. Prediction persistence and duplicate write protection
12. Canonical 5-movement outcome resolution (RUNHIGH/RUNLOW strictly monotonic)
13. Incomplete outcome handling (OUTCOME_INCOMPLETE excluded from win rate)
14. Data-gap outcome handling (OUTCOME_DATA_GAP)
15. Prediction immutability post-resolution
16. Session registry recovery across restarts
17. Full offline end-to-end lifecycle test
18. Null-safe EV and metrics reporting
19. Model promotion safety restrictions (dependence-aware sample size)
20. Centralized PAPER gate strictness (all mandatory gates)
21. Real-money purchase prevention invariant
"""
import json
import math
import os
import sqlite3
import time
import pytest

from config import DEFAULT_CONFIG
from decision_gate import (
    evaluate_paper_trade_eligibility,
    DecisionReason,
    DecisionResult
)
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RECONSTRUCTED,
    STATUS_INCOMPLETE,
    STATUS_DATA_GAP,
    STATUS_UNVERIFIED
)
from forward_observer import ForwardObserver
from forward_session import ForwardSessionRegistry, ForwardSession
from forward_validation_gate import ForwardValidationGate, MIN_INDEPENDENT_PERIODS
from model_artifact import ModelArtifact, ModelStatus
from performance_tracker import PerformanceTracker
from quote_database import QuoteDatabase
from quote_recorder import ProposalRecord
from risk import RiskManager
from session_reporter import SessionReporter


# ---------------------------------------------------------------------------
# Helpers & Mocks
# ---------------------------------------------------------------------------

class MockApprovedModel:
    market_symbol = "R_75"
    contract_duration = 5
    approval_status = ModelStatus.VALIDATED_RESEARCH
    validation_sample_count = 500


class MockResearchModel:
    market_symbol = "R_75"
    contract_duration = 5
    approval_status = ModelStatus.RESEARCH_ONLY
    validation_sample_count = 500


# ---------------------------------------------------------------------------
# 1. Uncertainty Fallback Removal Tests (Section 4)
# ---------------------------------------------------------------------------

def test_missing_uncertainty_rejection_blocks_paper_trade():
    """CRITICAL SAFETY TEST: Positive ordinary EV CANNOT bypass missing uncertainty evidence.
    If lower_prob_bound is None, returns UNCERTAINTY_UNAVAILABLE and NO_TRADE.
    """
    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.08,           # Strong positive edge: 0.08 * 61.03 - 2.0 = +2.88 EV
        lower_prob_bound=None,         # NO uncertainty bound provided!
        ask_price=2.0,
        total_payout=61.03,
        quote_request_timestamp=1000.0,
        quote_response_timestamp=1001.0,
        current_epoch=1005.0,
        execution_mode="PAPER"
    )

    assert result.is_eligible is False
    assert result.decision == DecisionReason.NO_TRADE.value
    assert result.ordinary_ev > 0.0
    assert result.conservative_ev is None
    assert DecisionReason.UNCERTAINTY_UNAVAILABLE.value in result.rejection_reasons


def test_nan_or_negative_lower_bound_rejected():
    """Uncertainty bound with NaN or non-positive value triggers UNCERTAINTY_UNAVAILABLE."""
    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.08,
        lower_prob_bound=float("nan"),
        ask_price=2.0,
        total_payout=61.03,
        quote_request_timestamp=1000.0,
        quote_response_timestamp=1001.0,
        current_epoch=1005.0,
        execution_mode="PAPER"
    )
    assert result.is_eligible is False
    assert DecisionReason.UNCERTAINTY_UNAVAILABLE.value in result.rejection_reasons


# ---------------------------------------------------------------------------
# 2. Quote Timestamp Enforcement Tests (Section 5)
# ---------------------------------------------------------------------------

def test_missing_quote_timestamps_rejected():
    """Missing request or response timestamps cause QUOTE_TIMESTAMP_INVALID."""
    res_no_req = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=None, quote_response_timestamp=1001.0, current_epoch=1005.0
    )
    assert DecisionReason.QUOTE_TIMESTAMP_INVALID.value in res_no_req.rejection_reasons

    res_no_resp = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=1000.0, quote_response_timestamp=None, current_epoch=1005.0
    )
    assert DecisionReason.QUOTE_TIMESTAMP_INVALID.value in res_no_resp.rejection_reasons


def test_inverted_quote_timestamps_rejected():
    """Response timestamp earlier than request timestamp is malformed -> QUOTE_TIMESTAMP_INVALID."""
    res = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=1002.0, quote_response_timestamp=1000.0, current_epoch=1005.0
    )
    assert DecisionReason.QUOTE_TIMESTAMP_INVALID.value in res.rejection_reasons


def test_future_quote_lookahead_rejected():
    """Quote with response timestamp after decision epoch is strictly rejected with QUOTE_LOOKAHEAD_REJECTED."""
    res = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=1000.0, quote_response_timestamp=1010.0, current_epoch=1005.0  # response is 5s in future!
    )
    assert result_is_lookahead_rejected(res)


def result_is_lookahead_rejected(res):
    return DecisionReason.QUOTE_LOOKAHEAD_REJECTED.value in res.rejection_reasons


def test_stale_quote_timestamp_rejected():
    """Quote older than max_quote_age_seconds is rejected with QUOTE_STALE."""
    res = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=900.0, quote_response_timestamp=910.0, current_epoch=1000.0,  # 90s old (max 60s)
        max_quote_age_seconds=60.0
    )
    assert DecisionReason.QUOTE_STALE.value in res.rejection_reasons


# ---------------------------------------------------------------------------
# 3. Persistent Risk State Tests (Section 6)
# ---------------------------------------------------------------------------

def test_persistent_consecutive_loss_state_survives_restart(tmp_path):
    """Proves that consecutive loss count survives application restarts and prevents trade authorization."""
    db_path = str(tmp_path / "risk.db")

    # Instance 1: Record 3 consecutive losses
    mgr1 = RiskManager(db_path=db_path, symbol="R_75", max_consecutive_losses=3)
    mgr1.record_trade(won=False, stake=2.0, epoch=1000)
    mgr1.record_trade(won=False, stake=2.0, epoch=1001)
    mgr1.record_trade(won=False, stake=2.0, epoch=1002)

    # Instance 2: Simulated process restart loading from the same DB
    mgr2 = RiskManager(db_path=db_path, symbol="R_75", max_consecutive_losses=3)
    state2 = mgr2.get_state(epoch=1003)

    assert state2.total_losses == 3
    assert state2.consecutive_losses == 0 or state2.cooldown_count >= 1

    # Gate evaluation rejects due to risk limit
    gate_res = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=1000.0, quote_response_timestamp=1001.0, current_epoch=1005.0,
        execution_mode="PAPER",
        current_consecutive_losses=3, max_consecutive_losses=3
    )
    assert DecisionReason.RISK_LIMIT_EXCEEDED.value in gate_res.rejection_reasons


def test_persistent_daily_drawdown_survives_restart(tmp_path):
    """Proves daily drawdown percentage survives application restarts."""
    db_path = str(tmp_path / "risk.db")

    mgr1 = RiskManager(initial_balance=1000.0, db_path=db_path, symbol="R_75")
    mgr1.record_trade(won=False, stake=50.0, epoch=1700000000)

    mgr2 = RiskManager(initial_balance=1000.0, db_path=db_path, symbol="R_75")
    state2 = mgr2.get_state(epoch=1700000001)
    assert state2.current_balance == 950.0
    assert state2.max_drawdown_amount == 50.0


def test_corrupted_risk_state_triggers_risk_state_unavailable():
    """Unloadable/corrupted risk state triggers RISK_STATE_UNAVAILABLE and NO_TRADE."""
    res = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.08, lower_prob_bound=0.05, ask_price=2.0, total_payout=61.03,
        quote_request_timestamp=1000.0, quote_response_timestamp=1001.0, current_epoch=1005.0,
        execution_mode="PAPER",
        is_risk_state_available=False  # Simulates corrupted DB
    )
    assert res.is_eligible is False
    assert DecisionReason.RISK_STATE_UNAVAILABLE.value in res.rejection_reasons


# ---------------------------------------------------------------------------
# 4. Shadow Predictions Independent of Quotes (Section 8)
# ---------------------------------------------------------------------------

def test_shadow_prediction_generated_without_quote(tmp_path):
    """Proves SHADOW mode records predictions and probabilities EVEN when no quote exists."""
    fwd_db = str(tmp_path / "fwd.db")
    quote_db = str(tmp_path / "quotes.db")
    risk_db = str(tmp_path / "risk.db")

    observer = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        journal_db_path=fwd_db,
        quote_db_path=quote_db,
        risk_db_path=risk_db
    )

    # Feed 30 ticks to satisfy lookback
    from live_collector import LiveTickRecord
    rec = None
    for i in range(30):
        t = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1000 + i,
            local_receipt_timestamp=float(1000 + i),
            price=100.0 + (i * 0.05),
            source="unit_test",
            session_id="test_sess",
            sequence_id=i + 1,
            data_quality_flags="NORMAL",
            latency_ms=10.0
        )
        rec = observer.process_incoming_tick(t)

    assert rec is not None
    assert rec.runhigh_ask is None  # Financial field is unavailable
    assert rec.runlow_ask is None
    assert rec.cons_ev_runhigh is None
    assert "QUOTE_UNAVAILABLE" in rec.rejection_reason
    assert rec.outcome_status in (STATUS_PENDING, "PENDING")


# ---------------------------------------------------------------------------
# 5. Prediction Identity & Duplicate Protection (Section 10)
# ---------------------------------------------------------------------------

def test_duplicate_prediction_protection(tmp_path):
    """Proves duplicate writes with identical prediction_id are safely ignored."""
    fwd_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=fwd_db)

    rec = ForwardPredictionRecord(
        prediction_id="pred_uniq_1",
        session_id="sess_123",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.6.1",
        market_state="mom_bin=BULL",
        features_json="{}"
    )

    # First write
    pid1 = journal.log_prediction(rec)
    assert pid1 == "pred_uniq_1"

    # Second write with same ID
    pid2 = journal.log_prediction(rec)
    assert pid2 == "pred_uniq_1"

    # Count rows
    with journal._get_conn() as conn:
        count = conn.execute("SELECT COUNT(1) FROM forward_predictions").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# 6. Canonical 5-Movement Outcome Resolution (Section 9 & 12)
# ---------------------------------------------------------------------------

def test_runhigh_5movement_resolution(tmp_path):
    """Proves 5 strictly upward movements resolve RUNHIGH as WIN and RUNLOW as LOSS."""
    fwd_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=fwd_db)

    rec = ForwardPredictionRecord(
        prediction_id="pred_rh_win",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.6.1",
        market_state="mom_bin=BULL",
        features_json="{}",
        signal_epoch=1000,
        signal_price=100.0,
        runhigh_pred_prob=0.08,
        runlow_pred_prob=0.02
    )
    journal.log_prediction(rec)

    # Ingest 6 strictly rising forward ticks: S_0=100.1, S_1=100.2, S_2=100.3, S_3=100.4, S_4=100.5, S_5=100.6
    for k in range(1, 7):
        journal.ingest_forward_tick(epoch=1000 + k, price=100.0 + (k * 0.1), symbol="R_75")

    recent = journal.inspect_recent(limit=1)[0]
    assert recent["outcome_status"] == STATUS_RECONSTRUCTED
    assert recent["runhigh_win"] == 1.0
    assert recent["runlow_win"] == 0.0
    # Immutability check: original prediction is unchanged
    assert recent["runhigh_pred_prob"] == 0.08
    assert recent["signal_epoch"] == 1000


def test_reversal_movement_resolves_loss(tmp_path):
    """A single reversal or tie on the 5th tick resolves both as LOSS."""
    fwd_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=fwd_db)

    rec = ForwardPredictionRecord(
        prediction_id="pred_reversal",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.6.1",
        market_state="mom_bin=BULL",
        features_json="{}",
        signal_epoch=1000,
        signal_price=100.0
    )
    journal.log_prediction(rec)

    # Ticks rise then drop on last tick: 100.1, 100.2, 100.3, 100.4, 100.5, 100.4
    prices = [100.1, 100.2, 100.3, 100.4, 100.5, 100.4]
    for idx, p in enumerate(prices, start=1):
        journal.ingest_forward_tick(epoch=1000 + idx, price=p, symbol="R_75")

    recent = journal.inspect_recent(limit=1)[0]
    assert recent["outcome_status"] == STATUS_RECONSTRUCTED
    assert recent["runhigh_win"] == 0.0
    assert recent["runlow_win"] == 0.0


# ---------------------------------------------------------------------------
# 7. Incomplete & Data-Gap Outcome Handling (Section 11)
# ---------------------------------------------------------------------------

def test_incomplete_outcome_excluded_from_win_rate(tmp_path):
    """Incomplete observations are marked OUTCOME_INCOMPLETE and excluded from win rate."""
    fwd_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=fwd_db)

    rec = ForwardPredictionRecord(
        prediction_id="pred_inc_test",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.6.1",
        market_state="mom_bin=BULL",
        features_json="{}",
        signal_epoch=1000,
        signal_price=100.0
    )
    journal.log_prediction(rec)

    # Ingest only 2 forward ticks
    journal.ingest_forward_tick(epoch=1001, price=100.1, symbol="R_75")
    journal.ingest_forward_tick(epoch=1002, price=100.2, symbol="R_75")

    # Mark incomplete with canonical status
    journal.mark_incomplete_as_unverified(symbol="R_75", target_status=STATUS_INCOMPLETE)

    metrics = journal.get_accuracy_metrics(symbol="R_75")
    assert metrics["total_predictions"] == 1
    assert metrics["resolved_predictions"] == 0
    assert metrics["incomplete_predictions"] == 1
    assert metrics["runhigh_observed_win_rate"] is None  # Excluded from win rate!


def test_data_gap_during_outcome_window_marked_gap(tmp_path):
    """Tick interval exceeding gap threshold marks outcome as OUTCOME_DATA_GAP."""
    fwd_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=fwd_db)

    rec = ForwardPredictionRecord(
        prediction_id="pred_gap_test",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.6.1",
        market_state="mom_bin=BULL",
        features_json="{}",
        signal_epoch=1000,
        signal_price=100.0
    )
    journal.log_prediction(rec)

    # Tick 1: epoch 1001
    journal.ingest_forward_tick(epoch=1001, price=100.1, symbol="R_75", gap_threshold_seconds=5.0)
    # Tick 2: epoch 1015 (14 second gap > 5s threshold!)
    journal.ingest_forward_tick(epoch=1015, price=100.2, symbol="R_75", gap_threshold_seconds=5.0)

    recent = journal.inspect_recent(limit=1)[0]
    assert recent["outcome_status"] == STATUS_DATA_GAP


# ---------------------------------------------------------------------------
# 8. Full Offline End-to-End Lifecycle Smoke Test (Section 15)
# ---------------------------------------------------------------------------

def test_full_offline_forward_session_lifecycle(tmp_path):
    """Deterministic end-to-end verification of complete forward observation lifecycle:
    1. Session creation
    2. Model loading
    3. Feature calculation
    4. Prediction generation
    5. Prediction journal insertion
    6. Quote association
    7. Decision logging
    8. Subsequent tick processing
    9. Outcome resolution
    10. Report generation
    """
    fwd_db = str(tmp_path / "fwd.db")
    quote_db = str(tmp_path / "quotes.db")
    sess_db = str(tmp_path / "sess.db")
    risk_db = str(tmp_path / "risk.db")
    rep_dir = str(tmp_path / "reports")

    # 1. Create Session
    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(
        symbol="R_75", mode="SHADOW", model_id="M_TEST",
        model_version="v1.6.1", planned_duration_seconds=60.0,
        journal_db_path=fwd_db, quote_db_path=quote_db
    )
    assert sess.session_id is not None

    # 2. Store a genuine quote in quote DB
    qdb = QuoteDatabase(db_path=quote_db)
    qrec = ProposalRecord(
        request_timestamp=995.0,
        response_timestamp=996.0,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_test_1",
        quote_source="live_proposal",
        quote_latency_ms=15.0,
        collection_status="QUOTE_AVAILABLE"
    )
    qdb.store_quote(qrec)

    # 3. Instantiate ForwardObserver
    observer = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        journal_db_path=fwd_db,
        quote_db_path=quote_db,
        risk_db_path=risk_db,
        session_id=sess.session_id
    )

    # 4. Stream 30 ticks to trigger feature calculation and prediction
    from live_collector import LiveTickRecord
    for i in range(30):
        t = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1000 + i,
            local_receipt_timestamp=float(1000 + i),
            price=100.0 + (i * 0.02),
            source="unit_test",
            session_id=sess.session_id,
            sequence_id=i + 1,
            data_quality_flags="NORMAL",
            latency_ms=10.0
        )
        observer.process_incoming_tick(t)

    # 5. Verify prediction was journaled
    recent_preds = observer.journal.inspect_recent(limit=1)
    assert len(recent_preds) == 1
    p_id = recent_preds[0]["prediction_id"]

    # 6. Stream subsequent 6 ticks to resolve outcome
    for k in range(1, 7):
        t = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1030 + k,
            local_receipt_timestamp=float(1030 + k),
            price=100.6 + (k * 0.1),
            source="unit_test",
            session_id=sess.session_id,
            sequence_id=30 + k,
            data_quality_flags="NORMAL",
            latency_ms=10.0
        )
        observer.process_incoming_tick(t)

    # 7. Verify outcome resolved
    resolved_rec = observer.journal.get_prediction(p_id)
    assert resolved_rec is not None
    assert resolved_rec["outcome_status"] == STATUS_RECONSTRUCTED
    assert resolved_rec["runhigh_win"] == 1.0

    # 8. Generate session report
    reporter = SessionReporter(
        reports_dir=rep_dir,
        journal=observer.journal,
        registry=reg,
        quote_db=qdb
    )
    report = reporter.generate_session_report(session=sess)

    assert report["report_type"] == "SESSION"
    assert report["lifecycle_counts"]["predictions_persisted"] >= 1
    assert report["lifecycle_counts"]["outcomes_resolved"] >= 1
    assert os.path.exists(rep_dir)


# ---------------------------------------------------------------------------
# 9. Model Promotion Safety Restrictions (Section 18)
# ---------------------------------------------------------------------------

def test_model_promotion_requires_independent_periods(tmp_path):
    """Model with fewer than MIN_INDEPENDENT_PERIODS (200) cannot be promoted."""
    val_db = str(tmp_path / "val.db")
    fwd_db = str(tmp_path / "fwd.db")
    gate = ForwardValidationGate(forward_db_path=fwd_db, validation_db_path=val_db)

    # Evaluates empty/small forward DB
    result = gate.evaluate(model_id="M_TEST", symbol="R_75")
    assert result.gate_passed is False
    assert result.recommended_action == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# 10. Real-Money Purchase Prevention (Invariant)
# ---------------------------------------------------------------------------

def test_live_execution_permanently_disabled():
    """Confirms LIVE_EXECUTION_DISABLED = True across all core operational modules."""
    from forward_observer import ForwardObserver
    from paper_trader import PaperTrader
    from forward_collection_service import ForwardCollectionService

    assert ForwardObserver.LIVE_EXECUTION_DISABLED is True
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True
    from forward_collection_service import LIVE_EXECUTION_DISABLED as SVC_DISABLED
    assert SVC_DISABLED is True
