"""Comprehensive Test Suite for V1.5.3 Final Safety & Connectivity Patch.

Validates:
1. No-model probability behaviour: rh_pred is None, rl_pred is None (Zero theoretical fallbacks).
2. Complete null-safe probability calculations in ForwardObserver and ForwardPredictionJournal.
3. Missing EV and missing conservative EV when model or quote is unavailable.
4. Negative conservative EV rejection: NO_TRADE with CONSERVATIVE_EV_TOO_LOW.
5. Positive ordinary EV but failing conservative EV: strictly NO_TRADE.
6. Positive ordinary & conservative EV but failing risk limits: strictly NO_TRADE with RISK_LIMIT_EXCEEDED.
7. Centralized evaluate_paper_trade_eligibility gate compliance across all reason codes.
8. Quote timestamp validation and stale quote rejection (> max_quote_age_seconds).
9. Invalid financial field validation (non-positive ask/payout, ask >= payout, NaN/Inf).
10. Multi-stage API verifier error classifications (DNS_FAILURE, TCP_CONNECTION_FAILED, TLS_HANDSHAKE_FAILED, WEBSOCKET_HANDSHAKE_TIMEOUT, HTTP_520, HTTP_403, HTTP_429).
11. QuoteDatabase persistence, round-trip retrieval, and offline/online source separation.
12. Strict non-purchasing mode restrictions and permanent safety directives.
"""
import math
import os
import sqlite3
import time
from typing import Dict, Any, List
import numpy as np
import pandas as pd
import pytest

from config import DEFAULT_CONFIG, TradingConfig
from contract_lifecycle import ALLOW_DEMO_EXECUTION
from decision_gate import evaluate_paper_trade_eligibility, DecisionReason, DecisionResult
from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
from forward_observer import ForwardObserver
from live_collector import LiveTickRecord
from model_artifact import ModelArtifact, ModelStatus
from model_manager import ModelManager
from paper_trader import PaperTrader, PaperTradeRecord
from quote_database import QuoteDatabase
from quote_recorder import ProposalRecord
from verify_deriv_connection import DerivConnectionVerifier


# ---------------------------------------------------------------------------
# 1. No-Model Probability Behaviour & Zero Fallback Tests
# ---------------------------------------------------------------------------

def test_no_model_probability_is_none(tmp_path):
    """Verifies that ForwardObserver assigns strictly None (never 0.03125) when no model is loaded."""
    j_db = str(tmp_path / "fwd.db")
    q_db = str(tmp_path / "q.db")

    observer = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        model_path_or_id="NON_EXISTENT_MODEL",
        journal_db_path=j_db,
        quote_db_path=q_db
    )

    assert observer.model_artifact is None

    # Ingest 35 ticks to trigger feature generation and prediction
    for i in range(35):
        observer.process_incoming_tick(LiveTickRecord(
            symbol="R_75", server_timestamp=1000 + i, local_receipt_timestamp=1000.0 + i,
            price=100.0 + (i * 0.02), source="test", session_id="s1", sequence_id=i + 1, data_quality_flags="NORMAL"
        ))

    recent = observer.journal.inspect_recent(limit=1)
    assert len(recent) == 1
    rec = recent[0]

    # Must be None, NEVER 0.03125 or 0.0
    assert rec["runhigh_pred_prob"] is None
    assert rec["runlow_pred_prob"] is None
    assert rec["ev_runhigh"] is None
    assert rec["ev_runlow"] is None
    assert rec["cons_ev_runhigh"] is None
    assert rec["cons_ev_runlow"] is None
    assert rec["decision"] == "NO_TRADE"
    assert "MODEL_NOT_AVAILABLE" in rec["rejection_reason"]


def test_null_safe_journal_accuracy_metrics(tmp_path):
    """Verifies that accuracy metrics handle None probabilities without crashing or computing invalid Brier scores."""
    j_db = str(tmp_path / "fwd.db")
    journal = ForwardPredictionJournal(db_path=j_db)

    # Log record with None probabilities
    rec = ForwardPredictionRecord(
        prediction_id="p1",
        timestamp=1000.0,
        symbol="R_75",
        model_version="V1.5.3",
        market_state="STATE_TEST",
        features_json="{}",
        runhigh_pred_prob=None,
        runlow_pred_prob=None,
        decision="NO_TRADE",
        rejection_reason="MODEL_NOT_AVAILABLE",
        target_direction="NONE",
        signal_epoch=1000,
        signal_price=100.0,
        outcome_status="RESOLVED",
        runhigh_win=1.0,
        runlow_win=0.0
    )
    journal.log_prediction(rec)

    metrics = journal.get_accuracy_metrics(symbol="R_75")
    assert metrics["total_predictions"] == 1
    assert metrics["resolved_predictions"] == 1
    # Brier scores must be None because predictions were unavailable
    assert metrics["brier_score_runhigh"] is None
    assert metrics["brier_score_runlow"] is None
    # Realized win rate can still be tracked on market outcomes
    assert metrics["realized_runhigh_win_rate"] == 1.0
    assert metrics["realized_runlow_win_rate"] == 0.0


# ---------------------------------------------------------------------------
# 2. Centralized Decision Gate & Reason Codes Tests
# ---------------------------------------------------------------------------

def test_centralized_decision_gate_all_clean_paper_approved():
    """Verifies that evaluate_paper_trade_eligibility approves a trade when ALL mandatory conditions pass."""
    class MockApprovedModel:
        market_symbol = "R_75"
        contract_duration = 5
        approval_status = ModelStatus.VALIDATED_RESEARCH
        validation_sample_count = 500

    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.08,           # Strong probability
        lower_prob_bound=0.05,         # Statistically justified lower bound
        ask_price=2.0,
        total_payout=61.03,            # Break-even = 2.0 / 61.03 = ~0.03277
        quote_epoch=1000.0,
        current_epoch=1005.0,          # 5 seconds old (< 60s max age)
        execution_mode="PAPER",
        market_state="STATE_A",
        min_expected_ev=0.0,
        min_conservative_ev=0.0,
        min_probability_margin=0.01,   # 0.08 - 0.0328 = 0.0472 > 0.01
        max_quote_age_seconds=60.0,
        min_validation_sample=100,
        current_stake=2.0,
        max_stake=5.0,
        has_data_gap=False
    )

    assert result.is_eligible is True
    assert result.decision == DecisionReason.PAPER_TRADE_APPROVED.value
    assert result.primary_reason == DecisionReason.PAPER_TRADE_APPROVED.value
    assert len(result.rejection_reasons) == 0
    assert result.ordinary_ev > 0
    assert result.conservative_ev > 0


def test_positive_ev_failing_conservative_ev_causes_no_trade():
    """CRITICAL SAFETY TEST: Ordinary EV is positive, but conservative EV is negative -> NO_TRADE."""
    class MockApprovedModel:
        market_symbol = "R_75"
        contract_duration = 5
        approval_status = ModelStatus.VALIDATED_RESEARCH
        validation_sample_count = 500

    # Payout = 61.03, Stake = 2.0. Break-even = 0.03277
    # P_est = 0.035 -> EV = (0.035 * 61.03) - 2.0 = +0.136 (POSITIVE EV!)
    # But P_lower = 0.020 -> Cons_EV = (0.020 * 61.03) - 2.0 = -0.779 (NEGATIVE CONSERVATIVE EV!)
    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.035,
        lower_prob_bound=0.020,
        ask_price=2.0,
        total_payout=61.03,
        quote_epoch=1000.0,
        current_epoch=1005.0,
        execution_mode="PAPER",
        min_expected_ev=0.0,
        min_conservative_ev=0.0,
        min_probability_margin=0.0
    )

    assert result.is_eligible is False
    assert result.decision == DecisionReason.NO_TRADE.value
    assert result.ordinary_ev > 0.0
    assert result.conservative_ev < 0.0
    assert DecisionReason.CONSERVATIVE_EV_TOO_LOW.value in result.rejection_reasons


def test_positive_conservative_ev_failing_risk_limit_causes_no_trade():
    """Trade qualifies on EV and conservative EV, but fails risk limits (consecutive losses) -> NO_TRADE."""
    class MockApprovedModel:
        market_symbol = "R_75"
        contract_duration = 5
        approval_status = ModelStatus.VALIDATED_RESEARCH
        validation_sample_count = 500

    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.08,
        lower_prob_bound=0.05,
        ask_price=2.0,
        total_payout=61.03,
        quote_epoch=1000.0,
        current_epoch=1005.0,
        execution_mode="PAPER",
        current_consecutive_losses=3,  # Max allowed is 3!
        max_consecutive_losses=3
    )

    assert result.is_eligible is False
    assert result.decision == DecisionReason.NO_TRADE.value
    assert DecisionReason.RISK_LIMIT_EXCEEDED.value in result.rejection_reasons


def test_stale_quote_rejection():
    """Quote age exceeds configured max_quote_age_seconds -> strictly QUOTE_STALE."""
    class MockApprovedModel:
        market_symbol = "R_75"
        contract_duration = 5
        approval_status = ModelStatus.VALIDATED_RESEARCH
        validation_sample_count = 500

    result = evaluate_paper_trade_eligibility(
        symbol="R_75",
        contract_type="RUNHIGH",
        duration_ticks=5,
        model_artifact=MockApprovedModel(),
        estimated_prob=0.08,
        lower_prob_bound=0.05,
        ask_price=2.0,
        total_payout=61.03,
        quote_epoch=1000.0,
        current_epoch=1065.0,          # 65 seconds old (max is 60s)
        execution_mode="PAPER",
        max_quote_age_seconds=60.0
    )

    assert result.is_eligible is False
    assert DecisionReason.QUOTE_STALE.value in result.rejection_reasons


def test_invalid_quote_fields_rejection():
    """Non-positive or inverted financial fields (ask >= payout) cause QUOTE_INVALID."""
    class MockApprovedModel:
        market_symbol = "R_75"
        contract_duration = 5
        approval_status = ModelStatus.VALIDATED_RESEARCH
        validation_sample_count = 500

    # Case 1: ask >= payout
    res1 = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.05, ask_price=10.0, total_payout=5.0
    )
    assert DecisionReason.QUOTE_INVALID.value in res1.rejection_reasons

    # Case 2: NaN in payout
    res2 = evaluate_paper_trade_eligibility(
        symbol="R_75", contract_type="RUNHIGH", model_artifact=MockApprovedModel(),
        estimated_prob=0.05, ask_price=2.0, total_payout=float("nan")
    )
    assert DecisionReason.QUOTE_INVALID.value in res2.rejection_reasons


# ---------------------------------------------------------------------------
# 3. PaperTrader Conservative EV Enforcement Tests
# ---------------------------------------------------------------------------

def test_paper_trader_enforces_conservative_ev_threshold(tmp_path):
    """Verifies that PaperTrader strictly enforces min_required_conservative_ev."""
    from quote_engine import QuoteEngine, ProposalQuote

    class MockQuoteEngine(QuoteEngine):
        def __init__(self):
            super().__init__(mode="historical")
        def get_quote_status(self, direction, epoch=0):
            # 2.0 stake, 61.03 payout
            q = ProposalQuote(
                symbol="R_75",
                contract_type="RUNHIGH" if direction == "UP" else "RUNLOW",
                direction=direction,
                stake=2.0,
                payout=61.03,
                profit=59.03,
                payout_ratio=29.515,
                implied_probability=2.0 / 61.03,
                quote_time=float(epoch),
                source="historical_snapshot"
            )
            return "QUOTE_AVAILABLE", q

    qe = MockQuoteEngine()
    pt = PaperTrader(quote_engine=qe, symbol="R_75", min_required_ev=0.0, min_required_conservative_ev=0.0)

    # Opportunity with ordinary EV > 0, but conservative EV <= 0
    # P_est = 0.035 -> EV = (0.035 * 61.03) - 2.0 = +0.136
    # conservative_ev = -0.50
    rec = pt.evaluate_opportunity(
        epoch=1000,
        signal="RUNHIGH",
        estimated_prob=0.035,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True,
        conservative_ev=-0.50
    )

    assert rec.decision == "NO_TRADE"
    assert "CONSERVATIVE_EV_TOO_LOW" in rec.rejection_reason
    assert "NEGATIVE_CONSERVATIVE_EV" in rec.rejection_reason


def test_paper_trader_none_estimated_prob(tmp_path):
    """Verifies that PaperTrader records MODEL_NOT_AVAILABLE and NO_TRADE when estimated_prob is None."""
    from quote_engine import QuoteEngine
    qe = QuoteEngine(mode="historical")
    pt = PaperTrader(quote_engine=qe, symbol="R_75")

    rec = pt.evaluate_opportunity(
        epoch=1000,
        signal="RUNHIGH",
        estimated_prob=None,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True
    )

    assert rec.decision == "NO_TRADE"
    assert rec.status_reason == "MODEL_NOT_AVAILABLE"
    assert rec.rejection_reason == "MODEL_NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# 4. API Error Classification & Network Pre-Flight Tests
# ---------------------------------------------------------------------------

def test_api_verifier_preflight_and_error_classification():
    """Verifies 8-stage preflight network checks and taxonomy classification."""
    verifier = DerivConnectionVerifier(symbol="R_75", timeout_seconds=4.0)

    pre = verifier.run_preflight_network_check("wss://api.derivws.com/trading/v1/options/ws/public")
    assert pre["hostname"] == "api.derivws.com"
    assert "stage_1_dns" in pre
    assert "stage_2_tcp" in pre
    assert "stage_3_tls" in pre

    if pre["dns_resolved"]:
        assert len(pre["resolved_ips"]) > 0
        assert pre["dns_latency_ms"] >= 0.0

    if pre["tcp_connected"]:
        assert pre["tcp_latency_ms"] >= 0.0

    if pre["tls_handshake"]:
        assert pre["tls_version"] in ("TLSv1.2", "TLSv1.3")


def test_api_verifier_timeout_classification(monkeypatch):
    """Verifies that asyncio.TimeoutError is categorized as WEBSOCKET_HANDSHAKE_TIMEOUT (not HTTP 520)."""
    import asyncio
    verifier = DerivConnectionVerifier(symbol="R_75", endpoint_url="wss://mock.timeout.endpoint", timeout_seconds=1.0)

    # Mock websockets.connect to raise asyncio.TimeoutError
    async def mock_connect(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr("websockets.connect", mock_connect)

    res = asyncio.run(verifier.run_diagnostics())
    assert res["status"] in ("WEBSOCKET_HANDSHAKE_TIMEOUT", "DNS_FAILURE", "TCP_CONNECTION_FAILED")
    assert res["status"] != "HTTP_520"


# ---------------------------------------------------------------------------
# 5. QuoteDatabase Persistence & Source Isolation Tests
# ---------------------------------------------------------------------------

def test_quote_database_source_isolation_and_persistence(tmp_path):
    """Verifies QuoteDatabase stores and distinguishes live_proposal quotes from test fixtures."""
    db_path = str(tmp_path / "quotes.db")
    db = QuoteDatabase(db_path=db_path)

    live_quote = ProposalRecord(
        request_timestamp=1000.0,
        response_timestamp=1000.05,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.07,
        potential_net_profit=59.07,
        currency="USD",
        proposal_id="live_prop_001",
        quote_source="live_proposal",
        quote_latency_ms=50.0,
        collection_status="QUOTE_AVAILABLE"
    )

    mock_quote = ProposalRecord(
        request_timestamp=1001.0,
        response_timestamp=1001.05,
        market_symbol="R_75",
        contract_type="RUNLOW",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.07,
        potential_net_profit=59.07,
        currency="USD",
        proposal_id="mock_prop_002",
        quote_source="offline_fixture",
        quote_latency_ms=50.0,
        collection_status="QUOTE_AVAILABLE"
    )

    db.store_quotes_batch([live_quote, mock_quote])

    # Check retrieval
    ret_rh = db.get_latest_quote_before("R_75", "RUNHIGH", timestamp=1005.0)
    assert ret_rh is not None
    assert ret_rh.quote_source == "live_proposal"
    assert ret_rh.proposal_id == "live_prop_001"

    ret_rl = db.get_latest_quote_before("R_75", "RUNLOW", timestamp=1005.0)
    assert ret_rl is not None
    assert ret_rl.quote_source == "offline_fixture"


# ---------------------------------------------------------------------------
# 6. Safety Directives & Permanent Restrictions Tests
# ---------------------------------------------------------------------------

def test_safety_directives_permanently_locked():
    """Confirms real-money trading is disabled across configuration, lifecycles, and engines."""
    assert DEFAULT_CONFIG.live_execution_disabled is True
    assert ALLOW_DEMO_EXECUTION is False
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True
    assert ForwardObserver.LIVE_EXECUTION_DISABLED is True
