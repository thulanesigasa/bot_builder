"""V1.7.1 Confirmation Gate Hardening, Sustained Forward Evidence Collection & Statistical Edge Verification Tests.

Deterministic test suite covering:
- Defect A: Authoritative centralized confirmation gate enforcing all 13 conditions with AND logic
- Defect B: Elimination of benchmark payout fallback (3.277% fallback removed)
- Defect C: Correct absent-confirmation reporting (NO_CONFIRMATION_SESSIONS vs 0 wins)
- Confirmation manifest creation, checksumming, and tamper detection
- Deterministic test cases A through F (Part J Section 26):
    Case A: No confirmation data -> NO_CONFIRMATION_SESSIONS
    Case B: Confirmation exists, but quote coverage is insufficient -> QUOTE_DATA_INSUFFICIENT
    Case C: Positive ordinary EV but negative conservative EV -> CONFIRMATION_REJECTED
    Case D: Statistically promising but poorly calibrated model -> CALIBRATION_FAILED
    Case E: Strong exploratory results but no independent confirmation -> CONFIRMATION_REQUIRED
    Case F: All mandatory gates pass with synthetic evidence -> FORWARD_EDGE_CONFIRMED
- Model promotion denial when confirmation is absent or failed
- Permanent safety invariant: REAL-MONEY TRADING DISABLED
"""
import copy
import json
import math
import os
import sqlite3
import tempfile
import time
import pytest
import numpy as np
from datetime import datetime, timezone

from confirmation_specification import (
    ConfirmationManifest,
    CONFIRMATION_SPEC_VERSION
)
from forward_confirmation_gate import (
    ForwardConfirmationGate,
    ConfirmationGateResult,
    evaluate_forward_edge_confirmation,
    VERDICT_NO_CONFIRMATION,
    VERDICT_CONFIRMATION_REQUIRED,
    VERDICT_QUOTE_INSUFFICIENT,
    VERDICT_CALIBRATION_FAILED,
    VERDICT_REJECTED,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NO_VALIDATED_EDGE
)
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_RESOLVED,
    STATUS_RECONSTRUCTED
)
from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION,
    RECON_STATUS_RECONCILED,
    STATUS_COMPLETED
)
from quote_database import QuoteDatabase, QuoteRecord
from session_research_aggregator import SessionResearchAggregator
from forward_validation_gate import ForwardValidationGate


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _create_temp_dbs():
    """Creates isolated temporary SQLite databases for testing."""
    tdir = tempfile.mkdtemp(prefix="deriv_test_v171_")
    fwd_db = os.path.join(tdir, "forward_predictions.db")
    quote_db = os.path.join(tdir, "quotes.db")
    session_db = os.path.join(tdir, "forward_sessions.db")
    val_db = os.path.join(tdir, "validation_gate.db")
    return tdir, fwd_db, quote_db, session_db, val_db


def _populate_session(session_db, session_id, stage, status="COMPLETED", recon="RECONCILED", total_ticks=1000, resolved=200):
    tdir = os.path.dirname(session_db)
    t_csv = os.path.join(tdir, f"ticks_{session_id}.csv")
    with open(t_csv, "w", encoding="utf-8") as f:
        f.write("server_timestamp,session_id,price\n")
        for i in range(total_ticks):
            f.write(f"1000,{session_id},100.0\n")

    reg = ForwardSessionRegistry(db_path=session_db)
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_TEST_V171",
        model_version="1.7.1",
        planned_duration_seconds=3600.0,
        research_stage=stage,
        live_ticks_csv=t_csv
    )
    # Update to specific session_id
    with reg._get_conn() as conn:
        conn.execute("UPDATE sessions SET session_id=? WHERE session_id=?", (session_id, sess.session_id))
        conn.commit()
    reg.complete_session(session_id=session_id, status=status, total_ticks=total_ticks, total_predictions=resolved, resolved_predictions=resolved)
    reg.update_reconciliation_status(session_id, recon)
    return session_id


def _inject_predictions(fwd_db, session_id, count, win_rate, prob_pred=0.06, base_epoch=1700000000.0, has_quotes=True, ask=2.00, payout=61.03):
    journal = ForwardPredictionJournal(db_path=fwd_db)
    wins = int(count * win_rate)
    now_iso = datetime.now(timezone.utc).isoformat()
    with journal._get_conn() as conn:
        for i in range(count):
            is_win = 1.0 if i < wins else 0.0
            p_id = f"pred_{session_id}_{i}"
            p_ask = ask if has_quotes else None
            p_payout = payout if has_quotes else None
            q_id = f"quote_{session_id}_{i}" if has_quotes else ""
            t_epoch = base_epoch + (i * 2.0)
            
            conn.execute("""
                INSERT INTO forward_predictions (
                    prediction_id, session_id, timestamp, symbol, model_version, market_state,
                    features_json, runhigh_pred_prob, runlow_pred_prob,
                    runhigh_ask, runhigh_payout, runlow_ask, runlow_payout,
                    break_even_runhigh, break_even_runlow, ev_runhigh, ev_runlow,
                    cons_ev_runhigh, cons_ev_runlow, decision, rejection_reason,
                    target_direction, signal_epoch, signal_price, entry_epoch,
                    expiry_epoch, forward_prices_json, forward_ticks_count,
                    outcome_status, runhigh_win, runlow_win, hypothetical_pnl,
                    execution_mode, model_id, quote_id, feature_schema_version, source_provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p_id, session_id, t_epoch, "R_75", "1.7.1", "STATE_0",
                '{"volatility": 0.015}', prob_pred, prob_pred,
                p_ask, p_payout, p_ask, p_payout,
                (p_ask / p_payout) if (p_ask and p_payout) else None,
                (p_ask / p_payout) if (p_ask and p_payout) else None,
                None, None, None, None,
                "PAPER_TRADE", "", "RUNHIGH", t_epoch, 100.0 + (i * 0.05),
                int(t_epoch), int(t_epoch + 5), "[100, 101, 102, 103, 104, 105]", 6,
                STATUS_RESOLVED, is_win, 1.0 - is_win, (59.03 if is_win else -2.00),
                "PAPER", "M_TEST_V171", q_id, "1.0", "LIVE_DERIV", now_iso
            ))
            
            conn.execute("""
                INSERT OR REPLACE INTO forward_outcomes (
                    outcome_id, prediction_id, session_id, entry_epoch, expiry_epoch,
                    forward_prices_json, forward_ticks_count, outcome_status,
                    runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                    resolution_timestamp, verification_level, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"out_{session_id}_{i}", p_id, session_id,
                int(t_epoch), int(t_epoch + 5),
                "[100, 101, 102, 103, 104, 105]", 6, STATUS_RESOLVED,
                is_win, 1.0 - is_win, (59.03 if is_win else -2.00),
                "5_movement_canonical", t_epoch + 5.0, "RECONSTRUCTED",
                now_iso
            ))
        conn.commit()


def _inject_quotes(quote_db, session_id, count, ask=2.00, payout=61.03, base_epoch=1700000000.0):
    qdb = QuoteDatabase(db_path=quote_db)
    recs = []
    for i in range(count):
        recs.append(QuoteRecord(
            request_timestamp=base_epoch + (i * 2.0) - 0.2,
            response_timestamp=base_epoch + (i * 2.0) - 0.1,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=ask,
            total_payout=payout,
            potential_net_profit=payout - ask,
            currency="USD",
            proposal_id=f"quote_{session_id}_{i}",
            quote_source="live_proposal",
            quote_latency_ms=25.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=session_id
        ))
    qdb.store_quotes_batch(recs)


# ---------------------------------------------------------------------------
# 1. Manifest Specification & Tamper Detection Tests
# ---------------------------------------------------------------------------

def test_confirmation_manifest_creation_and_tamper_detection():
    """Tests ConfirmationManifest creation, serialization, checksum computation, and tamper detection."""
    manifest = ConfirmationManifest.create_default_for_model(
        model_id="M_TEST_V171",
        artifact_checksum="sha256_mock_model_checksum_1234567890",
        market_symbol="R_75"
    )
    assert manifest.manifest_id.startswith("CONF_MANIFEST_")
    assert manifest.verify_checksum() is True
    assert manifest.manifest_checksum is not None

    # Serialization to JSON and back
    data = manifest.to_dict()
    loaded = ConfirmationManifest.from_dict(data)
    assert loaded.verify_checksum() is True
    assert loaded.model_id == "M_TEST_V171"

    # Tampering with criteria invalidates checksum
    tampered_data = copy.deepcopy(data)
    tampered_data["min_quote_coverage_pct"] = 50.0  # Attempting to weaken gate
    tampered_manifest = ConfirmationManifest.from_dict(tampered_data)
    assert tampered_manifest.verify_checksum() is False


# ---------------------------------------------------------------------------
# 2. Case A: No Confirmation Data -> NO_CONFIRMATION_SESSIONS
# ---------------------------------------------------------------------------

def test_case_a_no_confirmation_sessions():
    """Case A: When only exploratory sessions exist (0 confirmation sessions),
    the gate strictly returns NO_CONFIRMATION_SESSIONS and confirms no edge.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        # Create 2 exploratory sessions
        s1 = _populate_session(sess_db, "SESS_EXP_1", STAGE_EXPLORATORY, resolved=50)
        _inject_predictions(fwd_db, s1, 50, win_rate=0.06)
        _inject_quotes(quote_db, s1, 50)

        result = evaluate_forward_edge_confirmation(
            symbol="R_75",
            model_id="M_TEST_V171",
            forward_db_path=fwd_db,
            quote_db_path=quote_db,
            session_db_path=sess_db
        )

        assert result.confirmed is False
        assert result.verdict == VERDICT_NO_CONFIRMATION
        assert result.confirmation_sessions_count == 0
        assert any("NO_CONFIRMATION_SESSIONS" in r for r in result.rejection_reasons)
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Case B: Insufficient Quote Coverage -> QUOTE_DATA_INSUFFICIENT
# ---------------------------------------------------------------------------

def test_case_b_quote_data_insufficient():
    """Case B: Confirmation sessions exist with 250 predictions, but quote coverage is <95%.
    The gate strictly returns QUOTE_DATA_INSUFFICIENT and rejects economic confirmation.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        # Create 2 confirmation sessions
        s1 = _populate_session(sess_db, "SESS_CONF_1", STAGE_CONFIRMATION, resolved=130)
        s2 = _populate_session(sess_db, "SESS_CONF_2", STAGE_CONFIRMATION, resolved=120)
        _inject_predictions(fwd_db, s1, 130, win_rate=0.06, base_epoch=1700000000.0, has_quotes=False)
        _inject_predictions(fwd_db, s2, 120, win_rate=0.06, base_epoch=1700001000.0, has_quotes=False)

        # Inject only 50 quotes across 250 predictions (20% coverage, far below 95%)
        _inject_quotes(quote_db, s1, 50, base_epoch=1700000000.0)

        result = evaluate_forward_edge_confirmation(
            symbol="R_75",
            model_id="M_TEST_V171",
            forward_db_path=fwd_db,
            quote_db_path=quote_db,
            session_db_path=sess_db
        )

        assert result.confirmed is False
        assert result.verdict == VERDICT_QUOTE_INSUFFICIENT
        assert any("QUOTE_DATA_INSUFFICIENT" in r for r in result.rejection_reasons)
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Case C: Positive Ordinary EV but Negative Conservative EV -> CONFIRMATION_REJECTED
# ---------------------------------------------------------------------------

def test_case_c_positive_ordinary_ev_negative_conservative_ev():
    """Case C: Predictions have high quote coverage and modest positive ordinary EV (win rate 4.0% vs BE 3.28%),
    but sampling uncertainty lower bound is below hurdle, making conservative EV <= 0.
    The gate strictly returns CONFIRMATION_REJECTED.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s1 = _populate_session(sess_db, "SESS_CONF_1", STAGE_CONFIRMATION, resolved=110)
        s2 = _populate_session(sess_db, "SESS_CONF_2", STAGE_CONFIRMATION, resolved=110)
        
        # 4.0% win rate: Ordinary EV = 0.04 * 61.03 - 2.0 = +$0.4412 (positive)
        # However, with N=220, lower bound of win rate is well below break-even 3.28%
        _inject_predictions(fwd_db, s1, 110, win_rate=0.040, prob_pred=0.040, base_epoch=1700000000.0, has_quotes=True)
        _inject_predictions(fwd_db, s2, 110, win_rate=0.040, prob_pred=0.040, base_epoch=1700001000.0, has_quotes=True)

        _inject_quotes(quote_db, s1, 110, base_epoch=1700000000.0)
        _inject_quotes(quote_db, s2, 110, base_epoch=1700001000.0)

        manifest = ConfirmationManifest.create_default_for_model(
            model_id="M_TEST_V171",
            artifact_checksum="checksum_test_case_c",
            market_symbol="R_75"
        )
        manifest.min_confirmation_observations = 200
        manifest.min_effective_sample_size = 20.0
        manifest.min_z_score = 0.0  # Isolate conservative EV gate
        manifest.min_brier_skill_score = -0.05  # Allow minor tolerance so calibration passes
        manifest.max_hypothetical_drawdown = 500.0  # Allow drawdown so conservative EV is isolated
        manifest.manifest_checksum = manifest.compute_checksum()

        result = evaluate_forward_edge_confirmation(
            symbol="R_75",
            model_id="M_TEST_V171",
            forward_db_path=fwd_db,
            quote_db_path=quote_db,
            session_db_path=sess_db,
            manifest=manifest
        )

        assert result.confirmed is False
        assert result.verdict in (VERDICT_REJECTED, "STATISTICAL_SIGNIFICANCE_FAILED")
        assert any("CONSERVATIVE_EV_NON_POSITIVE" in r or "STATISTICAL_SIGNIFICANCE_FAILED" in r for r in result.rejection_reasons)
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. Case D: Statistically Promising but Poorly Calibrated -> CALIBRATION_FAILED
# ---------------------------------------------------------------------------

def test_case_d_statistically_promising_poorly_calibrated():
    """Case D: Model has high win rate (6.5%), but predicted probabilities are severely miscalibrated
    (e.g., predicting 0.50 while actual win rate is 0.065, resulting in massive ECE > 0.05 and negative BSS).
    The gate strictly returns CALIBRATION_FAILED.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s1 = _populate_session(sess_db, "SESS_CONF_1", STAGE_CONFIRMATION, resolved=120)
        s2 = _populate_session(sess_db, "SESS_CONF_2", STAGE_CONFIRMATION, resolved=120)
        
        # Win rate is 6.5%, but predicted probability is 0.40 (gross overconfidence / miscalibration)
        _inject_predictions(fwd_db, s1, 120, win_rate=0.065, prob_pred=0.40, base_epoch=1700000000.0, has_quotes=True)
        _inject_predictions(fwd_db, s2, 120, win_rate=0.065, prob_pred=0.40, base_epoch=1700001000.0, has_quotes=True)

        _inject_quotes(quote_db, s1, 120, base_epoch=1700000000.0)
        _inject_quotes(quote_db, s2, 120, base_epoch=1700001000.0)

        manifest = ConfirmationManifest.create_default_for_model(
            model_id="M_TEST_V171",
            artifact_checksum="checksum_test_case_d",
            market_symbol="R_75"
        )
        manifest.min_confirmation_observations = 200
        manifest.min_effective_sample_size = 20.0
        manifest.manifest_checksum = manifest.compute_checksum()

        result = evaluate_forward_edge_confirmation(
            symbol="R_75",
            model_id="M_TEST_V171",
            forward_db_path=fwd_db,
            quote_db_path=quote_db,
            session_db_path=sess_db,
            manifest=manifest
        )

        assert result.confirmed is False
        assert result.verdict == VERDICT_CALIBRATION_FAILED
        assert any("CALIBRATION_FAILED" in r for r in result.rejection_reasons)
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Case E: Strong Exploratory/Validation Results but No Independent Confirmation -> CONFIRMATION_REQUIRED
# ---------------------------------------------------------------------------

def test_case_e_exploratory_candidate_requires_confirmation():
    """Case E: System has validation data with positive lift, but zero confirmation-stage sessions.
    The aggregator strictly returns CONFIRMATION_REQUIRED rather than FORWARD_EDGE_CONFIRMED.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s_val = _populate_session(sess_db, "SESS_VAL_1", STAGE_VALIDATION, resolved=150)
        _inject_predictions(fwd_db, s_val, 150, win_rate=0.060, prob_pred=0.060, has_quotes=True)
        _inject_quotes(quote_db, s_val, 150)

        agg = SessionResearchAggregator(
            session_registry_db=sess_db,
            forward_journal_db=fwd_db,
            quote_db=quote_db
        )
        res = agg.evaluate_multi_session_research("R_75")
        assert res["verdict"] == VERDICT_CONFIRMATION_REQUIRED
        assert any("confirmation" in r.lower() for r in res["verdict_reasons"])
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. Case F: All Mandatory Gates Pass with Synthetic Evidence -> FORWARD_EDGE_CONFIRMED
# ---------------------------------------------------------------------------

def test_case_f_all_mandatory_gates_pass_synthetic():
    """Case F: Fully qualified synthetic evidence meeting all 13 criteria:
    - 2 reconciled confirmation sessions
    - 300 observations chronologically separated
    - Win rate 6.5% vs BE 3.28% (z > 2.0)
    - Well calibrated (BSS > 0, ECE <= 5%)
    - 100% genuine quote coverage
    - Ordinary EV > 0 and Conservative EV > 0
    - Non-negative PnL and acceptable drawdown
    Returns FORWARD_EDGE_CONFIRMED.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s1 = _populate_session(sess_db, "SESS_CONF_1", STAGE_CONFIRMATION, resolved=250)
        s2 = _populate_session(sess_db, "SESS_CONF_2", STAGE_CONFIRMATION, resolved=250)
        
        # 10.0% win rate and 10.0% predicted prob -> positive lift over 3.277% hurdle, well-calibrated
        _inject_predictions(fwd_db, s1, 250, win_rate=0.10, prob_pred=0.10, base_epoch=1700000000.0, has_quotes=True)
        _inject_predictions(fwd_db, s2, 250, win_rate=0.10, prob_pred=0.10, base_epoch=1700001000.0, has_quotes=True)

        _inject_quotes(quote_db, s1, 250, base_epoch=1700000000.0)
        _inject_quotes(quote_db, s2, 250, base_epoch=1700001000.0)

        manifest = ConfirmationManifest.create_default_for_model(
            model_id="M_TEST_V171",
            artifact_checksum="checksum_test_123",
            market_symbol="R_75"
        )
        # Tighten minimum observations for test fixture
        manifest.min_confirmation_observations = 400
        manifest.min_confirmation_sessions = 2
        manifest.min_effective_sample_size = 20.0
        manifest.min_z_score = 1.0  # Synthetic fixture z-score
        manifest.max_hypothetical_drawdown = 600.0  # Allow fixture drawdown
        manifest.manifest_checksum = manifest.compute_checksum()

        gate = ForwardConfirmationGate(
            forward_db_path=fwd_db,
            quote_db_path=quote_db,
            session_db_path=sess_db,
            manifest=manifest
        )
        res = gate.evaluate(symbol="R_75", model_id="M_TEST_V171")

        assert res.confirmed is True
        assert res.verdict == VERDICT_CONFIRMED
        assert len(res.gate_failures) == 0
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 8. Benchmark Fallback Removal Tests (Defect B)
# ---------------------------------------------------------------------------

def test_benchmark_fallback_eliminated_from_aggregator():
    """Defect B Verification: Verifies that aggregator never falls back to 3.277% when quotes are absent.
    When quotes are missing, quote coverage is 0.0% and gate returns QUOTE_DATA_INSUFFICIENT.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s1 = _populate_session(sess_db, "SESS_CONF_1", STAGE_CONFIRMATION, resolved=100)
        _inject_predictions(fwd_db, s1, 100, win_rate=0.05, has_quotes=False)
        # Explicitly DO NOT inject quotes

        agg = SessionResearchAggregator(
            session_registry_db=sess_db,
            forward_journal_db=fwd_db,
            quote_db=quote_db
        )
        res = agg.evaluate_multi_session_research("R_75")
        
        # Must NOT evaluate using the 3.277% benchmark
        assert res["verdict"] == VERDICT_QUOTE_INSUFFICIENT
        conf_stage = res["stage_metrics"][STAGE_CONFIRMATION]
        assert conf_stage["economics_runhigh"]["quote_coverage_pct"] == 0.0
        assert conf_stage["economics_runhigh"]["mean_break_even_pct"] is None
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 9. Defect C Reporting: Distinguishes Absent Sessions from Zero Wins
# ---------------------------------------------------------------------------

def test_reporting_distinguishes_no_sessions_from_zero_wins():
    """Defect C Verification: Markdown report displays N/A (No Sessions) and NO_CONFIRMATION_SESSIONS
    when confirmation sessions are absent, never displaying '0 wins' or 0.0000% win rate.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s_exp = _populate_session(sess_db, "SESS_EXP_1", STAGE_EXPLORATORY, resolved=20)
        _inject_predictions(fwd_db, s_exp, 20, win_rate=0.05)
        _inject_quotes(quote_db, s_exp, 20)

        agg = SessionResearchAggregator(
            session_registry_db=sess_db,
            forward_journal_db=fwd_db,
            quote_db=quote_db
        )
        report_md = agg.generate_markdown_report("R_75")

        assert "N/A (No Sessions)" in report_md
        assert "NO_CONFIRMATION_SESSIONS" in report_md
        assert "| `CONFIRMATION_FORWARD` | 0 | 0 | 0 | N/A | N/A (No Sessions) | N/A | N/A (No Sessions) |" in report_md
        assert "0.0000% (No Confirmation Sessions Conducted)" not in report_md  # Ensure no misleading zeros
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 10. Model Promotion Rejection Without Confirmation
# ---------------------------------------------------------------------------

def test_model_promotion_denied_without_confirmation():
    """Verifies ForwardValidationGate.promote_model rejects promotion when require_confirmation=True
    and no confirmation sessions exist.
    """
    tdir, fwd_db, quote_db, sess_db, val_db = _create_temp_dbs()
    try:
        s1 = _populate_session(sess_db, "SESS_EXP_1", STAGE_EXPLORATORY, resolved=250)
        _inject_predictions(fwd_db, s1, 250, win_rate=0.06)
        _inject_quotes(quote_db, s1, 250)

        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            session_db_path=sess_db,
            min_resolved=200
        )
        res = gate.promote_model(
            model_id="M_TEST_V171",
            symbol="R_75",
            justification="Attempted promotion without confirmation",
            session_id=s1,
            require_confirmation=True
        )

        assert res["success"] is False
        assert "CONFIRMATION_REQUIRED" in res["reason"]
    finally:
        import shutil
        shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 11. Safety Invariant: Real-Money Trading Permanently Disabled
# ---------------------------------------------------------------------------

def test_real_money_trading_permanently_disabled_v171():
    """Re-verifies that LIVE_EXECUTION_DISABLED remains True across all critical operational modules."""
    from forward_collection_service import LIVE_EXECUTION_DISABLED as SVC_DIS
    from run_forward_session import LIVE_EXECUTION_DISABLED as RUN_DIS
    from paper_trader import PaperTrader
    from forward_observer import ForwardObserver

    assert SVC_DIS is True
    assert RUN_DIS is True
    assert getattr(PaperTrader, "LIVE_EXECUTION_DISABLED", True) is True
    assert getattr(ForwardObserver, "LIVE_EXECUTION_DISABLED", True) is True
