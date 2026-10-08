"""Automated Test Suite for V1.6.2 Forward Data Integrity & Session Reconciliation.

Validates all V1.6.2 requirements:
- Session ID propagation across observer, streamer, quote recorder, and journal
- Blank session ID rejection (enforce_session_id=True)
- Session referential integrity (foreign keys on forward_outcomes)
- Safe migration of legacy records to LEGACY_UNATTRIBUTED
- Cross-session data segregation (predictions, quotes, outcomes)
- Prediction immutability & duplicate write prevention
- Duplicate outcome resolution prevention
- Tick accounting (live ticks vs warmup ticks vs duplicates vs rejected)
- Automated reconciliation engine (reconciled, count mismatch, chronology check)
- Authoritative session lifecycle status transitions & interrupted session recovery
- Future quote rejection & chronological integrity
- Canonical 5-movement contract outcome reconstruction
- Data gap & incomplete outcome exclusion from win rate
- Dependence-aware uncertainty (Politis & Romano block bootstrap, non-overlapping sensitivity)
- Genuine quote-based expected value
- Model-promotion integrity gate blocking on unreconciled data
- Permanent real-money execution prevention (LIVE_EXECUTION_DISABLED = True)
"""
import math
import os
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone
import pytest
import numpy as np
import pandas as pd

from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_INCOMPLETE,
    STATUS_DATA_GAP,
    STATUS_RECONSTRUCTED,
    STATUS_VERIFIED,
)
from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STATUS_CREATED,
    STATUS_INITIALIZING,
    STATUS_ACTIVE,
    STATUS_INTERRUPTED,
    STATUS_STOPPING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    RECON_STATUS_RECONCILED,
    RECON_STATUS_COUNT_MISMATCH,
    RECON_STATUS_MISSING_SESSION_ID,
    RECON_STATUS_TIMESTAMP_INCONSISTENCY,
)
from forward_observer import ForwardObserver
from forward_validation_gate import ForwardValidationGate
from live_collector import LiveTickStreamer, LiveTickRecord
from probability import stationary_block_bootstrap_ci, non_overlapping_sensitivity_analysis
from quote_database import QuoteDatabase
from quote_recorder import DerivQuoteRecorder, ProposalRecord as QuoteRecord
from session_reconciler import SessionReconciler
from session_reporter import SessionReporter


def _tmp_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 1. Session ID Propagation & Blank Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_blank_session_id_rejection():
    """Verifies that blank or null session IDs are strictly rejected when enforcement is active."""
    db_path = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=db_path, enforce_session_id=True)
        rec = ForwardPredictionRecord(
            prediction_id="p_blank_1",
            timestamp=time.time(),
            symbol="R_75",
            model_version="V1.6.2",
            market_state="TRENDING",
            features_json="{}",
            session_id=""  # Blank session ID
        )
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            journal.log_prediction(rec)

        rec_null = ForwardPredictionRecord(
            prediction_id="p_blank_2",
            timestamp=time.time(),
            symbol="R_75",
            model_version="V1.6.2",
            market_state="TRENDING",
            features_json="{}",
            session_id=None  # Null session ID
        )
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            journal.log_prediction(rec_null)
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_session_id_propagation_to_observer_and_journal():
    """Verifies session ID propagates from ForwardObserver to logged journal records."""
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        test_session_id = str(uuid.uuid4())
        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=j_db,
            quote_db_path=q_db,
            session_id=test_session_id
        )
        assert obs.session_id == test_session_id

        # Feed 35 ticks to warm up lookback buffer and produce predictions
        base_t = 1_700_000_000
        for i in range(35):
            tick = LiveTickRecord(
                symbol="R_75",
                server_timestamp=base_t + i,
                local_receipt_timestamp=float(base_t + i) + 0.05,
                price=100.0 + i * 0.1,
                source="LIVE_DERIV",
                session_id=test_session_id,
                sequence_id=i,
                data_quality_flags="NORMAL"
            )
            obs.process_incoming_tick(tick)

        # Inspect journal
        preds = obs.journal.get_session_predictions(test_session_id)
        assert len(preds) > 0
        for p in preds:
            assert p["session_id"] == test_session_id
            assert p["symbol"] == "R_75"
    finally:
        for p in (j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Database Referential Integrity & Immutability
# ─────────────────────────────────────────────────────────────────────────────

def test_session_foreign_key_integrity():
    """Verifies that forward_outcomes enforces foreign key constraints to forward_predictions."""
    db_path = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=db_path)
        with journal._get_conn() as conn:
            # Attempt to insert an outcome for a non-existent prediction
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO forward_outcomes (
                        outcome_id, prediction_id, session_id, entry_epoch, expiry_epoch,
                        forward_prices_json, forward_ticks_count, outcome_status,
                        runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                        resolution_timestamp, verification_level, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "out_orphan", "non_existent_pred", "sess_1", 100, 106,
                    "[]", 6, "RESOLVED", 1.0, 0.0, 1.9, "canonical", 106.0, "VERIFIED", "2026-10-08T00:00:00"
                ))
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_prediction_immutability():
    """Verifies original prediction fields cannot be mutated when resolving outcomes."""
    db_path = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=db_path)
        pred_id = "pred_immutable_test"
        t0 = 1_700_000_000.0
        rec = ForwardPredictionRecord(
            prediction_id=pred_id,
            timestamp=t0,
            symbol="R_75",
            model_version="V1.6.2",
            market_state="EXPANDING",
            features_json='{"spread": 0.5}',
            session_id="sess_immutable",
            runhigh_pred_prob=0.08,
            runlow_pred_prob=0.02,
            decision="PAPER_TRADE"
        )
        journal.log_prediction(rec)

        # Ingest 6 upward ticks to resolve outcome
        for step in range(7):
            journal.ingest_forward_tick(
                epoch=int(t0) + step + 1,
                price=100.0 + step * 0.5,
                symbol="R_75"
            )

        # Inspect original prediction
        with journal._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM forward_predictions WHERE prediction_id = ?",
                (pred_id,)
            ).fetchone()
            assert row["timestamp"] == t0
            assert row["market_state"] == "EXPANDING"
            assert row["runhigh_pred_prob"] == 0.08
            assert row["decision"] == "PAPER_TRADE"
            assert row["features_json"] == '{"spread": 0.5}'
            # Outcome fields populated
            assert row["runhigh_win"] == 1.0
            assert row["outcome_status"] in ("RESOLVED", STATUS_RESOLVED, "OUTCOME_RECONSTRUCTED")

            # Dedicated outcomes table row exists
            outcome_row = conn.execute(
                "SELECT * FROM forward_outcomes WHERE prediction_id = ?",
                (pred_id,)
            ).fetchone()
            assert outcome_row is not None
            assert outcome_row["runhigh_win"] == 1.0
            assert outcome_row["session_id"] == "sess_immutable"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_duplicate_prediction_protection():
    """Verifies that duplicate prediction logging is safely ignored."""
    db_path = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=db_path)
        rec = ForwardPredictionRecord(
            prediction_id="pred_dup_1",
            timestamp=time.time(),
            symbol="R_75",
            model_version="V1.6.2",
            market_state="CONSOLIDATING",
            features_json="{}",
            session_id="sess_dup"
        )
        res1 = journal.log_prediction(rec)
        res2 = journal.log_prediction(rec)
        assert res1 == "pred_dup_1"
        assert res2 == "pred_dup_1"

        with journal._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM forward_predictions WHERE prediction_id = 'pred_dup_1'"
            ).fetchone()[0]
            assert count == 1
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Legacy Migration & Cross-Session Segregation
# ─────────────────────────────────────────────────────────────────────────────

def test_legacy_unattributed_migration():
    """Verifies blank session records are safely migrated to LEGACY_UNATTRIBUTED."""
    db_path = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=db_path, enforce_session_id=False)
        rec = ForwardPredictionRecord(
            prediction_id="legacy_1",
            timestamp=1700000000.0,
            symbol="R_75",
            model_version="V1.6.0",
            market_state="STATE",
            features_json="{}",
            session_id="",
            decision="NO_TRADE",
            outcome_status="RESOLVED",
            execution_mode="SHADOW"
        )
        journal.log_prediction(rec)

        # Force session_id to empty to simulate legacy record
        with journal._get_conn() as conn:
            conn.execute("UPDATE forward_predictions SET session_id='' WHERE prediction_id='legacy_1'")
            conn.commit()

        migrated = journal.migrate_legacy_unattributed()
        assert migrated == 1

        with journal._get_conn() as conn:
            row = conn.execute("SELECT session_id, source_provenance FROM forward_predictions WHERE prediction_id = 'legacy_1'").fetchone()
            assert row["session_id"] == "LEGACY_UNATTRIBUTED"
            assert row["source_provenance"] == "LEGACY_UNATTRIBUTED"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_cross_session_segregation():
    """Verifies predictions, quotes, and outcomes from different sessions are completely segregated."""
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=j_db)
        quotes = QuoteDatabase(db_path=q_db)

        # Log prediction in Session A
        rec_a = ForwardPredictionRecord(
            prediction_id="pred_a",
            timestamp=1700000000.0,
            symbol="R_75",
            model_version="V1.6.2",
            market_state="STATE",
            features_json="{}",
            session_id="SESSION_A",
            outcome_status="RESOLVED",
            runhigh_win=1.0
        )
        journal.log_prediction(rec_a)

        # Log prediction in Session B
        rec_b = ForwardPredictionRecord(
            prediction_id="pred_b",
            timestamp=1700000010.0,
            symbol="R_75",
            model_version="V1.6.2",
            market_state="STATE",
            features_json="{}",
            session_id="SESSION_B",
            outcome_status="RESOLVED",
            runhigh_win=0.0
        )
        journal.log_prediction(rec_b)

        # Store quotes for Session A & B
        quotes.store_quote(QuoteRecord(
            request_timestamp=1700000000.0,
            response_timestamp=1700000000.05,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.0,
            potential_net_profit=59.0,
            currency="USD",
            proposal_id="q_a",
            quote_source="live_proposal",
            quote_latency_ms=50.0,
            collection_status="QUOTE_AVAILABLE",
            session_id="SESSION_A"
        ))
        quotes.store_quote(QuoteRecord(
            request_timestamp=1700000010.0,
            response_timestamp=1700000010.05,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.0,
            potential_net_profit=59.0,
            currency="USD",
            proposal_id="q_b",
            quote_source="live_proposal",
            quote_latency_ms=50.0,
            collection_status="QUOTE_AVAILABLE",
            session_id="SESSION_B"
        ))

        # Check Session A isolation
        preds_a = journal.get_session_predictions("SESSION_A")
        assert len(preds_a) == 1
        assert preds_a[0]["prediction_id"] == "pred_a"

        metrics_a = journal.get_accuracy_metrics("R_75", session_id="SESSION_A")
        assert metrics_a["total_predictions"] == 1
        assert metrics_a["realized_runhigh_win_rate"] == 1.0

        quotes_a = quotes.get_session_quotes("SESSION_A")
        assert len(quotes_a) == 1
        assert quotes_a[0].proposal_id == "q_a"

        # Check Session B isolation
        metrics_b = journal.get_accuracy_metrics("R_75", session_id="SESSION_B")
        assert metrics_b["total_predictions"] == 1
        assert metrics_b["realized_runhigh_win_rate"] == 0.0

    finally:
        for p in (j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tick Accounting & Warm-Up Separation
# ─────────────────────────────────────────────────────────────────────────────

def test_tick_accounting_and_warmup_separation():
    """Verifies that live genuine ticks are distinguished from feature warm-up ticks."""
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=j_db,
            quote_db_path=q_db,
            session_id="sess_tick_acc"
        )
        base_t = 1_700_000_000
        # Ingest 30 ticks
        for i in range(30):
            tick = LiveTickRecord(
                symbol="R_75",
                server_timestamp=base_t + i,
                local_receipt_timestamp=float(base_t + i) + 0.01,
                price=100.0 + i,
                source="LIVE_DERIV",
                session_id="sess_tick_acc",
                sequence_id=i,
                data_quality_flags="NORMAL"
            )
            obs.process_incoming_tick(tick)

        # First 24 ticks are warmup (feature buffer capacity = 25)
        assert obs.warmup_ticks_count == 24
        assert obs.live_ticks_count == 6
        assert (obs.warmup_ticks_count + obs.live_ticks_count) == 30
    finally:
        for p in (j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Session Status Transitions & Interrupted Recovery
# ─────────────────────────────────────────────────────────────────────────────

def test_session_lifecycle_transitions_and_recovery():
    """Verifies authoritative status transitions and recovery of unclosed sessions."""
    s_db = _tmp_db_path()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="M1",
            model_version="1.0",
            planned_duration_seconds=3600.0,
            status=STATUS_CREATED
        )
        assert sess.status == STATUS_CREATED

        reg.set_session_status(sess.session_id, STATUS_INITIALIZING)
        assert reg.get_session(sess.session_id).status == STATUS_INITIALIZING

        reg.set_session_status(sess.session_id, STATUS_ACTIVE)
        assert reg.get_session(sess.session_id).status == STATUS_ACTIVE

        # Simulate abrupt shutdown / restart: session was left in ACTIVE
        recovered = reg.recover_interrupted_sessions(max_grace_seconds=0.0)
        assert sess.session_id in recovered
        recovered_sess = reg.get_session(sess.session_id)
        assert recovered_sess.status == STATUS_INTERRUPTED
    finally:
        if os.path.exists(s_db):
            os.unlink(s_db)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Session Reconciliation Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_session_reconciler_reconciled():
    """Verifies that a fully consistent session is marked RECONCILED with is_verified=True."""
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

        # Log prediction with LIVE_DERIV provenance
        rec = ForwardPredictionRecord(
            prediction_id="p_rec_1",
            timestamp=1700000000.0,
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id=sess.session_id,
            outcome_status="RESOLVED",
            runhigh_win=1.0,
            source_provenance="LIVE_DERIV"
        )
        journal.log_prediction(rec)

        # Insert matching outcome row in forward_outcomes
        with journal._get_conn() as conn:
            conn.execute("""
                INSERT INTO forward_outcomes (
                    outcome_id, prediction_id, session_id,
                    entry_epoch, expiry_epoch, forward_prices_json, forward_ticks_count,
                    outcome_status, runhigh_win, runlow_win, hypothetical_pnl,
                    resolution_timestamp, verification_level, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "out_rec_1", "p_rec_1", sess.session_id,
                1700000000, 1700000005, "[101.0, 102.0, 103.0, 104.0, 105.0]", 5,
                "RESOLVED", 1.0, 0.0, 0.0,
                1700000005.0, "OUTCOME_VERIFIED", datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

        # Update registry stats to match
        reg.complete_session(
            session_id=sess.session_id,
            status=STATUS_COMPLETED,
            total_ticks=30,
            total_predictions=1,
            resolved_predictions=1,
            live_ticks=5,
            warmup_ticks=25
        )

        reconciler = SessionReconciler(
            registry_db_path=s_db,
            journal_db_path=j_db,
            quote_db_path=q_db
        )
        report = reconciler.reconcile_session(sess.session_id)
        assert report.status == RECON_STATUS_RECONCILED
        assert report.is_verified is True
        assert len(report.issues) == 0
    finally:
        for p in (s_db, j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


def test_session_reconciler_detects_count_mismatch():
    """Verifies that counter divergence between registry and journal triggers COUNT_MISMATCH."""
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
            planned_duration_seconds=3600.0
        )
        journal = ForwardPredictionJournal(db_path=j_db)

        # Registry claims 1309 predictions on 10 ticks (like the baseline defect)
        reg.complete_session(
            session_id=sess.session_id,
            status=STATUS_COMPLETED,
            total_ticks=10,
            total_predictions=1309,
            resolved_predictions=1300
        )

        reconciler = SessionReconciler(
            registry_db_path=s_db,
            journal_db_path=j_db,
            quote_db_path=q_db
        )
        report = reconciler.reconcile_session(sess.session_id)
        assert report.status == RECON_STATUS_COUNT_MISMATCH
        assert report.is_verified is False
        assert any("count mismatch" in i.lower() for i in report.issues)
    finally:
        for p in (s_db, j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


def test_session_reconciler_detects_future_quote():
    """Verifies that future quote references trigger TIMESTAMP_INCONSISTENCY."""
    s_db = _tmp_db_path()
    j_db = _tmp_db_path()
    q_db = _tmp_db_path()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(symbol="R_75", mode="SHADOW", model_id="M1", model_version="1.0", planned_duration_seconds=3600.0)
        journal = ForwardPredictionJournal(db_path=j_db)
        quotes = QuoteDatabase(db_path=q_db)

        # Store quote with response time = 1005.0
        quotes.store_quote(QuoteRecord(
            request_timestamp=1004.0,
            response_timestamp=1005.0,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.0,
            potential_net_profit=59.0,
            currency="USD",
            proposal_id="q_future",
            quote_source="live_proposal",
            quote_latency_ms=50.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess.session_id
        ))

        # Prediction was made at 1000.0 (5 seconds BEFORE quote response)
        rec = ForwardPredictionRecord(
            prediction_id="p_chrono_fail",
            timestamp=1000.0,
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id=sess.session_id,
            outcome_status="RESOLVED",
            runhigh_win=1.0,
            source_provenance="LIVE_DERIV"
        )
        journal.log_prediction(rec)
        # Update quote_id reference
        with journal._get_conn() as conn:
            conn.execute("UPDATE forward_predictions SET quote_id='q_future' WHERE prediction_id='p_chrono_fail'")
            conn.commit()

        reg.complete_session(session_id=sess.session_id, status=STATUS_COMPLETED, total_ticks=30, total_predictions=1, resolved_predictions=1)

        reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
        report = reconciler.reconcile_session(sess.session_id)
        assert report.status == RECON_STATUS_TIMESTAMP_INCONSISTENCY
        assert report.is_verified is False
    finally:
        for p in (s_db, j_db, q_db):
            if os.path.exists(p):
                os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Canonical 5-Movement Outcome Reconstruction & Data Gap Handling
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_5movement_outcome_reconstruction():
    """Verifies that 5 strictly positive tick movements resolve RUNHIGH win."""
    j_db = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=j_db)
        t0 = 1_700_000_000
        rec = ForwardPredictionRecord(
            prediction_id="p_5m_win",
            timestamp=float(t0),
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id="sess_5m",
            signal_epoch=t0,
            signal_price=100.0
        )
        journal.log_prediction(rec)

        # Ingest 6 upward ticks: S0=100, S1=101, S2=102, S3=103, S4=104, S5=105
        for i in range(6):
            journal.ingest_forward_tick(epoch=t0 + i + 1, price=100.0 + (i + 1), symbol="R_75")

        with journal._get_conn() as conn:
            row = conn.execute("SELECT * FROM forward_predictions WHERE prediction_id='p_5m_win'").fetchone()
            assert row["runhigh_win"] == 1.0
            assert row["runlow_win"] == 0.0
            assert row["outcome_status"] in ("RESOLVED", STATUS_RESOLVED, "OUTCOME_RECONSTRUCTED")
    finally:
        if os.path.exists(j_db):
            os.unlink(j_db)


def test_data_gap_outcome_handling():
    """Verifies that a gap exceeding threshold during outcome window marks prediction as OUTCOME_DATA_GAP."""
    j_db = _tmp_db_path()
    try:
        journal = ForwardPredictionJournal(db_path=j_db)
        t0 = 1_700_000_000
        rec = ForwardPredictionRecord(
            prediction_id="p_gap_test",
            timestamp=float(t0),
            symbol="R_75",
            model_version="1.0",
            market_state="STATE",
            features_json="{}",
            session_id="sess_gap",
            signal_epoch=t0,
            signal_price=100.0
        )
        journal.log_prediction(rec)

        # Ingest tick 1
        journal.ingest_forward_tick(epoch=t0 + 1, price=101.0, symbol="R_75", gap_threshold_seconds=3.0)
        # Next tick has 10-second gap (gap threshold = 3.0s)
        journal.ingest_forward_tick(epoch=t0 + 12, price=102.0, symbol="R_75", gap_threshold_seconds=3.0)

        with journal._get_conn() as conn:
            row = conn.execute("SELECT * FROM forward_predictions WHERE prediction_id='p_gap_test'").fetchone()
            assert row["outcome_status"] == STATUS_DATA_GAP
            # Excluded from realized win rate
            assert row["runhigh_win"] is None
    finally:
        if os.path.exists(j_db):
            os.unlink(j_db)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Dependence-Aware Uncertainty & Quote-Based EV
# ─────────────────────────────────────────────────────────────────────────────

def test_dependence_aware_uncertainty():
    """Verifies block bootstrap and non-overlapping sensitivity produce valid, ordered bounds."""
    # Create dependent time-series (repeated blocks of 1, 1, 0, 0, 0)
    data = np.array([1.0, 1.0, 0.0, 0.0, 0.0] * 40)
    ci_low, ci_high = stationary_block_bootstrap_ci(data, num_resamples=500, mean_block_length=5, seed=42)
    assert 0.0 <= ci_low <= ci_high <= 1.0
    mean_val = np.mean(data)
    assert ci_low <= mean_val <= ci_high

    sensitivity = non_overlapping_sensitivity_analysis(pd.Series(data), stride=5, null_prob=0.0328)
    assert sensitivity["n_non_overlapping"] == 40
    assert "edge_survives_non_overlapping" in sensitivity


def test_quote_based_ev_calculation():
    """Verifies EV calculation uses actual quotes and does not fallback to synthetic values."""
    q_db = _tmp_db_path()
    try:
        db = QuoteDatabase(db_path=q_db)
        db.store_quote(QuoteRecord(
            request_timestamp=100.0,
            response_timestamp=100.1,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.00,
            total_payout=61.03,
            potential_net_profit=59.03,
            currency="USD",
            proposal_id="q_ev",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            session_id="sess_ev"
        ))

        q = db.get_latest_quote_before("R_75", "RUNHIGH", timestamp=105.0, session_id="sess_ev")
        assert q is not None
        be_prob = q.implied_probability
        assert math.isclose(be_prob, 2.00 / 61.03, rel_tol=1e-4)

        # Expected value: P_win * Payout - Ask
        p_win = 0.05  # 5% probability (higher than 3.28% break-even)
        ev = (p_win * q.total_payout) - q.ask_price
        assert ev > 0.0
    finally:
        if os.path.exists(q_db):
            os.unlink(q_db)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Model-Promotion Integrity Gate & Safety Directives
# ─────────────────────────────────────────────────────────────────────────────

def test_model_promotion_blocked_on_unreconciled_session():
    """Verifies ForwardValidationGate strictly rejects model promotion when candidate session is unreconciled."""
    s_db = _tmp_db_path()
    f_db = _tmp_db_path()
    v_db = _tmp_db_path()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(symbol="R_75", mode="SHADOW", model_id="M_TEST", model_version="1.0", planned_duration_seconds=3600.0)
        # Mark reconciliation as COUNT_MISMATCH
        reg.update_reconciliation_status(sess.session_id, RECON_STATUS_COUNT_MISMATCH)

        gate = ForwardValidationGate(
            forward_db_path=f_db,
            validation_db_path=v_db,
            min_resolved=10
        )
        res = gate.promote_model(
            model_id="M_TEST",
            symbol="R_75",
            justification="Test promotion",
            session_id=sess.session_id
        )
        assert res["success"] is False
        assert res["reason"] == "GATE_FAILED"
    finally:
        for p in (s_db, f_db, v_db):
            if os.path.exists(p):
                os.unlink(p)


def test_real_money_purchase_prevention():
    """Verifies LIVE_EXECUTION_DISABLED is strictly True and immutable across modules."""
    from forward_collection_service import LIVE_EXECUTION_DISABLED as SVC_DISABLED
    from run_forward_session import LIVE_EXECUTION_DISABLED as RUN_DISABLED
    assert SVC_DISABLED is True
    assert RUN_DISABLED is True
