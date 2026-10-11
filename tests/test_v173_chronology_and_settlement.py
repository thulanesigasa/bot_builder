"""V1.7.3 Regression & Unit Tests: Strict Quote Chronology, Contract Settlement Verification,
Distinct Quote Coverage, and NO_TRADE Safety Invariants.

Verifies:
  1. Adversarial Quote Chronology (quote response received after prediction decision -> rejected).
  2. Request-Time Fallback Prohibition (missing response_timestamp cannot use request_timestamp).
  3. Taxonomic Quote Rejection Reasons (QUOTE_UNAVAILABLE, QUOTE_RESPONSE_TIME_MISSING, etc.).
  4. Quote Reuse Within Freshness Window vs Stale Quotes (> 10s).
  5. 4 Distinct Quote Coverage Categories (Raw, Valid Chronological, Economic Evaluation, Execution Quality).
  6. Canonical 5-Movement Outcome Sequences (Monotonic RUNHIGH/RUNLOW, Equality Loss, Reversal Loss, All-Above-Entry Trap).
  7. 6 Separated Verification Dimensions in SessionReconciler.
  8. NO_TRADE Centralized Enforcement and LIVE_EXECUTION_DISABLED = True Safety Invariant.
"""
import os
import tempfile
import time
import uuid
import pytest

from contract_specification import (
    evaluate_canonical_outcome,
    ContractOutcomeResult,
    CONTRACT_TYPE_RUNHIGH,
    CONTRACT_TYPE_RUNLOW,
    STATUS_OUTCOME_WON,
    STATUS_OUTCOME_LOST,
    STATUS_OUTCOME_INCOMPLETE,
    STATUS_OUTCOME_DATA_GAP,
    REASON_MONOTONIC_RUNHIGH_SATISFIED,
    REASON_MONOTONIC_RUNLOW_SATISFIED,
    REASON_EQUALITY_VIOLATION,
    REASON_REVERSAL_VIOLATION,
    REASON_ALL_ABOVE_ENTRY_BUT_NOT_MONOTONIC,
    REASON_ALL_BELOW_ENTRY_BUT_NOT_MONOTONIC,
)
from decision_gate import (
    evaluate_paper_trade_eligibility,
    DecisionReason,
    DecisionResult,
    LIVE_EXECUTION_DISABLED,
)
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
)
from forward_session import (
    ForwardSessionRegistry,
    STATUS_COMPLETED,
    RECON_STATUS_RECONCILED,
    RECON_STATUS_TIMESTAMP_INCONSISTENCY,
)
from quote_database import (
    QuoteDatabase,
    QuoteRecord,
)
from session_reconciler import (
    SessionReconciler,
)


def _tmp_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    if os.path.exists(path):
        os.unlink(path)
    return path


def _evaluate_gate(
    quote: dict,
    symbol: str = "R_75",
    contract_type: str = "RUNHIGH",
    decision_timestamp: float = 1700000100.0,
    max_quote_age_seconds: float = 60.0,
    execution_mode: str = "PAPER"
) -> DecisionResult:
    return evaluate_paper_trade_eligibility(
        symbol=symbol,
        contract_type=contract_type,
        duration_ticks=5,
        estimated_prob=0.15,
        lower_prob_bound=0.10,
        ask_price=quote.get("stake", 2.0),
        total_payout=quote.get("total_payout", 60.0),
        current_epoch=decision_timestamp,
        quote_request_timestamp=quote.get("request_timestamp"),
        quote_response_timestamp=quote.get("response_timestamp"),
        quote_currency=quote.get("currency"),
        quote_symbol=quote.get("market_symbol"),
        quote_duration=quote.get("contract_duration"),
        quote_contract_type=quote.get("contract_type"),
        max_quote_age_seconds=max_quote_age_seconds,
        execution_mode=execution_mode,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Canonical Contract Outcome Verification (V1.7.3 Part D & Part H)
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_runhigh_win():
    """Strict monotonic sequence 100 < 101 < 102 < 103 < 104 < 105 is a RUNHIGH win."""
    ticks = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    res = evaluate_canonical_outcome(CONTRACT_TYPE_RUNHIGH, ticks)
    assert res.outcome_status == STATUS_OUTCOME_WON
    assert res.rejection_reason == REASON_MONOTONIC_RUNHIGH_SATISFIED
    assert res.intermediate_evaluations == [True, True, True, True, True]


def test_canonical_runlow_win():
    """Strict monotonic sequence 105 > 104 > 103 > 102 > 101 > 100 is a RUNLOW win."""
    ticks = [105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
    res = evaluate_canonical_outcome(CONTRACT_TYPE_RUNLOW, ticks)
    assert res.outcome_status == STATUS_OUTCOME_WON
    assert res.rejection_reason == REASON_MONOTONIC_RUNLOW_SATISFIED
    assert res.intermediate_evaluations == [True, True, True, True, True]


def test_canonical_runhigh_all_above_entry_trap():
    """Sequence 100, 103, 102, 104, 105, 106 has all future prices > entry (100),
    but intermediate step (103 -> 102) reverses, so it must LOSE under strict monotonicity."""
    ticks = [100.0, 103.0, 102.0, 104.0, 105.0, 106.0]
    res = evaluate_canonical_outcome(CONTRACT_TYPE_RUNHIGH, ticks)
    assert res.outcome_status == STATUS_OUTCOME_LOST
    assert res.rejection_reason == REASON_ALL_ABOVE_ENTRY_BUT_NOT_MONOTONIC


def test_canonical_runlow_all_below_entry_trap():
    """Sequence 106, 103, 104, 102, 103, 101 has all future prices < entry (106),
    but intermediate step (103 -> 104) reverses, so it must LOSE under strict monotonicity."""
    ticks = [106.0, 103.0, 104.0, 102.0, 103.0, 101.0]
    res = evaluate_canonical_outcome(CONTRACT_TYPE_RUNLOW, ticks)
    assert res.outcome_status == STATUS_OUTCOME_LOST
    assert res.rejection_reason == REASON_ALL_BELOW_ENTRY_BUT_NOT_MONOTONIC


def test_canonical_equality_loss():
    """Sequence 100, 101, 102, 102, 104, 105 has an equal tick (102 == 102),
    which violates strict inequality (<) and must immediately LOSE."""
    ticks = [100.0, 101.0, 102.0, 102.0, 104.0, 105.0]
    res = evaluate_canonical_outcome(CONTRACT_TYPE_RUNHIGH, ticks)
    assert res.outcome_status == STATUS_OUTCOME_LOST
    assert res.rejection_reason == REASON_EQUALITY_VIOLATION


def test_canonical_incomplete_and_data_gap():
    """Fewer than 6 ticks must classify as INCOMPLETE or DATA_GAP, not loss."""
    res_short = evaluate_canonical_outcome(CONTRACT_TYPE_RUNHIGH, [100.0, 101.0])
    assert res_short.outcome_status == STATUS_OUTCOME_INCOMPLETE

    res_gap = evaluate_canonical_outcome(CONTRACT_TYPE_RUNHIGH, [100.0, 101.0, 102.0], data_gap=True)
    assert res_gap.outcome_status == STATUS_OUTCOME_DATA_GAP


# ─────────────────────────────────────────────────────────────────────────────
# 2. Strict Quote Chronology & Gate 6 Verification (V1.7.3 Part B)
# ─────────────────────────────────────────────────────────────────────────────

def test_decision_gate_rejects_quote_received_after_decision():
    """A quote whose response_timestamp > decision timestamp must be REJECTED (quote_received_at <= decision_at)."""
    t_decision = 1700000100.0
    quote = {
        "market_symbol": "R_75",
        "contract_type": "RUNHIGH",
        "contract_duration": 5,
        "duration_unit": "t",
        "currency": "USD",
        "stake": 2.0,
        "total_payout": 60.0,
        "request_timestamp": 1700000099.0,
        "response_timestamp": 1700000100.5,  # Arrived 0.5s AFTER decision
        "collection_status": "QUOTE_AVAILABLE",
    }
    result = _evaluate_gate(quote, decision_timestamp=t_decision)
    assert not result.is_eligible
    assert DecisionReason.QUOTE_RECEIVED_AFTER_DECISION.value in result.rejection_reasons


def test_decision_gate_rejects_missing_response_timestamp():
    """A quote with missing response_timestamp cannot fall back to request_timestamp."""
    t_decision = 1700000100.0
    quote = {
        "market_symbol": "R_75",
        "contract_type": "RUNHIGH",
        "contract_duration": 5,
        "duration_unit": "t",
        "currency": "USD",
        "stake": 2.0,
        "total_payout": 60.0,
        "request_timestamp": 1700000095.0,
        "response_timestamp": None,  # Missing response timestamp
        "collection_status": "QUOTE_AVAILABLE",
    }
    result = _evaluate_gate(quote, decision_timestamp=t_decision)
    assert not result.is_eligible
    assert DecisionReason.QUOTE_RESPONSE_TIME_MISSING.value in result.rejection_reasons


def test_decision_gate_rejects_stale_quote():
    """A quote older than max_quote_age_seconds must be rejected as QUOTE_STALE."""
    t_decision = 1700000120.0
    quote = {
        "market_symbol": "R_75",
        "contract_type": "RUNHIGH",
        "contract_duration": 5,
        "duration_unit": "t",
        "currency": "USD",
        "stake": 2.0,
        "total_payout": 60.0,
        "request_timestamp": 1700000099.0,
        "response_timestamp": 1700000100.0,  # 20s old relative to decision
        "collection_status": "QUOTE_AVAILABLE",
    }
    result = _evaluate_gate(quote, decision_timestamp=t_decision, max_quote_age_seconds=10.0)
    assert not result.is_eligible
    assert DecisionReason.QUOTE_STALE.value in result.rejection_reasons


def test_decision_gate_rejects_wrong_contract_or_symbol():
    """Quotes for wrong symbol, duration, or contract type must be explicitly rejected."""
    t_decision = 1700000100.0
    base_quote = {
        "market_symbol": "R_75",
        "contract_type": "RUNHIGH",
        "contract_duration": 5,
        "duration_unit": "t",
        "currency": "USD",
        "stake": 2.0,
        "total_payout": 60.0,
        "request_timestamp": 1700000098.0,
        "response_timestamp": 1700000099.0,
        "collection_status": "QUOTE_AVAILABLE",
    }

    # Wrong symbol
    q_wrong_sym = dict(base_quote, market_symbol="1HZ100V")
    r1 = _evaluate_gate(q_wrong_sym, decision_timestamp=t_decision)
    assert DecisionReason.QUOTE_WRONG_SYMBOL.value in r1.rejection_reasons

    # Wrong duration
    q_wrong_dur = dict(base_quote, contract_duration=10)
    r2 = _evaluate_gate(q_wrong_dur, decision_timestamp=t_decision)
    assert DecisionReason.QUOTE_WRONG_DURATION.value in r2.rejection_reasons

    # Wrong currency
    q_wrong_cur = dict(base_quote, currency="EUR")
    r3 = _evaluate_gate(q_wrong_cur, decision_timestamp=t_decision)
    assert DecisionReason.QUOTE_CURRENCY_MISMATCH.value in r3.rejection_reasons


# ─────────────────────────────────────────────────────────────────────────────
# 3. Session Reconciler Separated Dimensions & Quote Coverage Categories (V1.7.3 Part C & E)
# ─────────────────────────────────────────────────────────────────────────────

def test_session_reconciler_separated_dimensions_and_quote_coverage():
    """Verifies that SessionReconciler produces the 6 separated dimensions and 4 distinct quote coverages."""
    s_db = _tmp_db_path()
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="M1",
            model_version="1.0",
            planned_duration_seconds=3600.0,
            live_ticks_csv=os.path.join(tempfile.gettempdir(), f"test_ticks_{uuid.uuid4().hex}.csv")
        )
        journal = ForwardPredictionJournal(db_path=j_db)
        quotes = QuoteDatabase(db_path=q_db)

        # Store 2 quotes:
        # Quote 1 at t=1000.0 (fresh for pred 1 at t=1002.0)
        quotes.store_quote(QuoteRecord(
            request_timestamp=999.0,
            response_timestamp=1000.0,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=60.0,
            potential_net_profit=58.0,
            currency="USD",
            proposal_id="q_fresh",
            quote_source="live_proposal",
            quote_latency_ms=45.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess.session_id,
        ))

        # Quote 2 at t=1010.0 (reused for pred 2 at t=1018.0, age=8s: passes valid chrono & econ, but exceeds 5s execution quality)
        quotes.store_quote(QuoteRecord(
            request_timestamp=1009.0,
            response_timestamp=1010.0,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=60.0,
            potential_net_profit=58.0,
            currency="USD",
            proposal_id="q_reused",
            quote_source="live_proposal",
            quote_latency_ms=45.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess.session_id,
        ))

        # Prediction 1 (at t=1002.0, quote age = 2.0s <= 5.0s -> execution quality eligible)
        journal.log_prediction(ForwardPredictionRecord(
            prediction_id="p1",
            timestamp=1002.0,
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id=sess.session_id,
            outcome_status="RESOLVED",
            runhigh_win=1.0,
            source_provenance="LIVE_DERIV",
            runhigh_ask=2.0,
            runhigh_payout=60.0,
        ))

        # Prediction 2 (at t=1018.0, quote age = 8.0s > 5.0s -> valid chrono & econ, not execution quality)
        journal.log_prediction(ForwardPredictionRecord(
            prediction_id="p2",
            timestamp=1018.0,
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id=sess.session_id,
            outcome_status="RESOLVED",
            runhigh_win=0.0,
            source_provenance="LIVE_DERIV",
            runhigh_ask=2.0,
            runhigh_payout=60.0,
        ))

        with journal._get_conn() as conn:
            conn.execute("UPDATE forward_predictions SET quote_id='q_fresh' WHERE prediction_id='p1'")
            conn.execute("UPDATE forward_predictions SET quote_id='q_reused' WHERE prediction_id='p2'")
            conn.execute("""
                INSERT INTO forward_outcomes (outcome_id, prediction_id, session_id, symbol, outcome_status, resolution_timestamp, forward_prices_json, created_at)
                VALUES ('out_1', 'p1', ?, 'R_75', 'RESOLVED', 1010.0, '[]', '2026-10-11T00:00:00')
            """, (sess.session_id,))
            conn.execute("""
                INSERT INTO forward_outcomes (outcome_id, prediction_id, session_id, symbol, outcome_status, resolution_timestamp, forward_prices_json, created_at)
                VALUES ('out_2', 'p2', ?, 'R_75', 'RESOLVED', 1025.0, '[]', '2026-10-11T00:00:00')
            """, (sess.session_id,))
            conn.commit()

        reg.complete_session(
            session_id=sess.session_id,
            status=STATUS_COMPLETED,
            total_ticks=30,
            total_predictions=2,
            resolved_predictions=2,
            live_ticks=10,
            warmup_ticks=20
        )

        reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
        report = reconciler.reconcile_session(sess.session_id)

        assert report.status == RECON_STATUS_RECONCILED
        assert report.is_verified is True

        # Check 6 separated dimensions
        assert report.data_counts_reconciled is True
        assert report.prediction_chronology_verified is True
        assert report.outcome_reconstruction_verified is True
        assert report.quote_chronology_verified is True
        assert report.contract_mapping_verified is True
        assert report.economic_evidence_eligible is True

        # Check 4 distinct quote coverage categories
        assert report.raw_quote_coverage_pct == 100.0  # 2 / 2
        assert report.valid_chronological_quotes_count == 2
        assert report.valid_chronological_quote_coverage_pct == 100.0  # 2 / 2
        assert report.economic_eligible_predictions_count == 2
        assert report.economic_eligible_coverage_pct == 100.0  # 2 / 2
        assert report.execution_quality_quotes_count == 1  # only p1 (age 2s <= 5s)
        assert report.execution_quality_coverage_pct == 50.0  # 1 / 2

    finally:
        for p in (s_db, j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


def test_session_reconciler_detects_missing_response_timestamp():
    """Verifies that missing response timestamp on a quote triggers TIMESTAMP_INCONSISTENCY."""
    s_db = _tmp_db_path()
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(symbol="R_75", mode="SHADOW", model_id="M1", model_version="1.0", planned_duration_seconds=3600.0)
        journal = ForwardPredictionJournal(db_path=j_db)
        quotes = QuoteDatabase(db_path=q_db)

        # Store quote with NULL response_timestamp
        quotes.store_quote(QuoteRecord(
            request_timestamp=1000.0,
            response_timestamp=None,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=60.0,
            potential_net_profit=58.0,
            currency="USD",
            proposal_id="q_no_resp",
            quote_source="live_proposal",
            quote_latency_ms=0.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess.session_id,
        ))

        journal.log_prediction(ForwardPredictionRecord(
            prediction_id="p_no_resp",
            timestamp=1005.0,
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id=sess.session_id,
            outcome_status="RESOLVED",
            runhigh_win=1.0,
            source_provenance="LIVE_DERIV",
        ))

        with journal._get_conn() as conn:
            conn.execute("UPDATE forward_predictions SET quote_id='q_no_resp' WHERE prediction_id='p_no_resp'")
            conn.execute("""
                INSERT INTO forward_outcomes (outcome_id, prediction_id, session_id, symbol, outcome_status, resolution_timestamp, forward_prices_json, created_at)
                VALUES ('out_no_resp', 'p_no_resp', ?, 'R_75', 'RESOLVED', 1015.0, '[]', '2026-10-11T00:00:00')
            """, (sess.session_id,))
            conn.commit()

        reg.complete_session(session_id=sess.session_id, status=STATUS_COMPLETED, total_ticks=30, total_predictions=1, resolved_predictions=1)

        reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
        report = reconciler.reconcile_session(sess.session_id)

        assert report.status == RECON_STATUS_TIMESTAMP_INCONSISTENCY
        assert report.is_verified is False
        assert report.missing_response_time_errors == 1
        assert report.quote_chronology_verified is False
        assert report.economic_evidence_eligible is False
    finally:
        for p in (s_db, j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Centralized NO_TRADE and Live-Money Execution Invariant (Part G)
# ─────────────────────────────────────────────────────────────────────────────

def test_centralized_no_trade_permanent_invariant():
    """Verifies that LIVE_EXECUTION_DISABLED is permanently True and cannot be bypassed."""
    assert LIVE_EXECUTION_DISABLED is True

    quote = {
        "market_symbol": "R_75",
        "contract_type": "RUNHIGH",
        "contract_duration": 5,
        "duration_unit": "t",
        "currency": "USD",
        "stake": 2.0,
        "total_payout": 60.0,
        "request_timestamp": 1000.0,
        "response_timestamp": 1001.0,
        "collection_status": "QUOTE_AVAILABLE",
    }
    # In SHADOW mode, live trade execution must be False and NO_TRADE enforced
    res = _evaluate_gate(quote, execution_mode="SHADOW")
    assert not res.is_eligible
    assert res.decision == "NO_TRADE"
    assert DecisionReason.SHADOW_MODE_NON_TRADING.value in res.rejection_reasons
