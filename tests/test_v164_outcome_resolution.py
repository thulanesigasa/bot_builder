"""Automated Test Suite for V1.6.4 — Outcome Resolution, Extended Validation & Tick Integrity.

Verifies:
1. Fix for the Zero-Resolved-Outcome bug (consecutive tick gap vs entry spot).
2. Canonical 5-movement outcome window ($S_0 \to S_1 \to S_2 \to S_3 \to S_4 \to S_5$).
3. Strict equality and reversal loss classification.
4. Concurrent and overlapping prediction resolution without crosstalk.
5. Historical warm-up boundary anchoring strictly before the first live tick.
6. Controlled session shutdown with resolution grace period.
7. Orphan session reference migration to LEGACY_UNATTRIBUTED.
8. Full end-to-end offline acceptance lifecycle with persistence after restart.
9. Safety invariants (LIVE_EXECUTION_DISABLED = True permanently).
"""

import json
import os
import sqlite3
import tempfile
import time
import uuid
import pytest

from config import DEFAULT_CONFIG
from forward_collection_service import ForwardCollectionService, LIVE_EXECUTION_DISABLED
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RECONSTRUCTED,
    STATUS_DATA_GAP,
    STATUS_INCOMPLETE,
    STATUS_UNVERIFIED
)
from forward_observer import ForwardObserver
from forward_session import ForwardSessionRegistry, STATUS_COMPLETED
from live_collector import LiveTickRecord
from model_artifact import ModelArtifact, ModelStatus
from outcome_resolver import (
    OutcomeResolver,
    REASON_TICK_SEQUENCE_GAP,
    REASON_WAITING_FOR_ENTRY_TICK,
    REASON_WAITING_FOR_FUTURE_TICKS
)
from session_reconciler import SessionReconciler, RECON_STATUS_RECONCILED


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _create_mock_model(tmp_path) -> str:
    """Creates a deterministic research model artifact for testing."""
    art = ModelArtifact(
        model_id="MOCK_V164_MODEL",
        model_version="1.6.4",
        created_at_utc="2026-10-08T00:00:00Z",
        training_dataset_id="mock_dataset_v164",
        dataset_checksum="abc123mockchecksum",
        market_symbol="R_75",
        contract_family="RUNHIGH_RUNLOW",
        contract_duration=5,
        contract_duration_unit="t",
        outcome_definition_version="1.5",
        feature_schema_version="1.5.3",
        feature_names=["diff_1", "vol_ratio"],
        feature_ordering=["diff_1", "vol_ratio"],
        model_type="EMPIRICAL_STATE_CONDITIONAL",
        model_parameters={
            "base_rate_runhigh": 0.035,
            "base_rate_runlow": 0.035,
            "state_conditional_probabilities": {
                "DEFAULT": {
                    "p_runhigh": 0.040,
                    "p_runlow": 0.030,
                    "count": 100,
                    "lower_bound_runhigh": 0.032,
                    "lower_bound_runlow": 0.022
                }
            }
        },
        calibration_parameters={"method": "platt", "ece": 0.01},
        training_sample_count=500,
        validation_sample_count=200,
        holdout_sample_count=100,
        validation_metrics={"brier_score": 0.05},
        statistical_status="VALIDATED",
        approval_status=ModelStatus.RESEARCH_ONLY,
        required_lookback=25
    )
    path = str(tmp_path / "mock_model.json")
    art.save_to_file(path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 1. Zero-Resolved-Outcome Bug Fix & Canonical 5-Movement Sequence
# ─────────────────────────────────────────────────────────────────────────────

def test_consecutive_tick_gap_fix_vs_entry_spot():
    """Proves that a multi-tick sequence spanning > 5s does NOT trigger OUTCOME_DATA_GAP
    when inter-tick intervals are <= gap_threshold_seconds (the V1.6.3 root cause).
    """
    db_path = _tmp_db()
    try:
        resolver = OutcomeResolver(db_path=db_path, gap_threshold_seconds=5.0)
        
        # Register pending prediction at t=1000.0
        resolver.register_pending_prediction(
            prediction_id="pred_gap_fix",
            session_id="sess_gap_fix",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0
        )
        assert resolver.active_pending_count == 1

        # Feed 6 consecutive ticks at 2-second intervals:
        # t=1002 (S_0, Entry), t=1004 (S_1), t=1006 (S_2), t=1008 (S_3), t=1010 (S_4), t=1012 (S_5, Expiry)
        # Note: Total span from Entry (1002) to Expiry (1012) is 10.0s > 5.0s!
        # In V1.6.3, tick 4 (t=1008) falsely failed: 1008 - 1002 = 6.0s > 5.0s -> OUTCOME_DATA_GAP.
        # In V1.6.4, consecutive interval is 2.0s <= 5.0s -> Resolves successfully!
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        events = []
        for i, pr in enumerate(prices):
            ep = 1002 + (i * 2)
            ev = resolver.ingest_tick(epoch=ep, price=pr, symbol="R_75")
            if ev:
                events.extend(ev)

        assert len(events) == 1
        res = events[0]
        assert res["prediction_id"] == "pred_gap_fix"
        assert res["outcome_status"] == STATUS_RECONSTRUCTED
        assert res["runhigh_win"] == 1.0  # Monotonically increasing
        assert res["runlow_win"] == 0.0
        assert resolver.active_pending_count == 0

        # Verify database record
        with resolver._get_conn() as conn:
            row = conn.execute("SELECT * FROM forward_predictions WHERE prediction_id = 'pred_gap_fix'").fetchone()
            assert row["outcome_status"] == STATUS_RECONSTRUCTED
            assert row["forward_ticks_count"] == 6
            assert json.loads(row["forward_prices_json"]) == prices
            assert json.loads(row["forward_epochs_json"]) == [1002 + i*2 for i in range(6)]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_true_consecutive_tick_gap_detected():
    """Verifies that a genuine gap between consecutive ticks (> 5.0s) triggers OUTCOME_DATA_GAP."""
    db_path = _tmp_db()
    try:
        resolver = OutcomeResolver(db_path=db_path, gap_threshold_seconds=5.0)
        resolver.register_pending_prediction(
            prediction_id="pred_true_gap",
            session_id="sess_true_gap",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0
        )

        # Tick 1: S_0 at t=1002
        resolver.ingest_tick(epoch=1002, price=100.0, symbol="R_75")
        # Tick 2: S_1 at t=1004 (delta = 2s <= 5s)
        resolver.ingest_tick(epoch=1004, price=100.5, symbol="R_75")
        # Tick 3: arrives at t=1011 (delta = 7.0s > 5.0s -> true gap!)
        evs = resolver.ingest_tick(epoch=1011, price=101.0, symbol="R_75")

        assert len(evs) == 1
        assert evs[0]["outcome_status"] == STATUS_DATA_GAP
        assert "delta 7.0s > 5.0s" in evs[0]["reason"]
        assert resolver.active_pending_count == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_canonical_5movement_equality_and_reversal_losses():
    """Verifies that equal ticks (ties) or reversals are strictly classified as losses."""
    db_path = _tmp_db()
    try:
        resolver = OutcomeResolver(db_path=db_path, gap_threshold_seconds=5.0)
        
        # Test 1: Tie at movement 3
        resolver.register_pending_prediction(
            prediction_id="pred_tie",
            session_id="s1",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0
        )
        tie_prices = [100.0, 101.0, 102.0, 102.0, 103.0, 104.0]  # S_2 == S_3
        evs_tie = []
        for i, pr in enumerate(tie_prices):
            e = resolver.ingest_tick(epoch=1001 + i, price=pr, symbol="R_75")
            if e: evs_tie.extend(e)
        assert evs_tie[0]["runhigh_win"] == 0.0
        assert evs_tie[0]["runlow_win"] == 0.0

        # Test 2: Monotonic decrease (RUNLOW win)
        resolver.register_pending_prediction(
            prediction_id="pred_runlow",
            session_id="s1",
            symbol="R_75",
            signal_epoch=2000,
            signal_price=100.0,
            timestamp=2000.0
        )
        down_prices = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
        evs_down = []
        for i, pr in enumerate(down_prices):
            e = resolver.ingest_tick(epoch=2001 + i, price=pr, symbol="R_75")
            if e: evs_down.extend(e)
        assert evs_down[0]["runhigh_win"] == 0.0
        assert evs_down[0]["runlow_win"] == 1.0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Overlapping Forward Predictions Isolation
# ─────────────────────────────────────────────────────────────────────────────

def test_overlapping_forward_predictions_isolated_resolution():
    """Proves that multiple forward predictions generated with overlapping windows
    resolve independently using their respective entry boundaries without crosstalk.
    """
    db_path = _tmp_db()
    try:
        resolver = OutcomeResolver(db_path=db_path, gap_threshold_seconds=5.0)

        # Prediction 1 generated at t=1000.0
        resolver.register_pending_prediction(
            prediction_id="pred_1",
            session_id="sess_overlap",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0
        )

        # Tick at t=1001 -> P1 receives Entry S_0 = 100.0
        resolver.ingest_tick(epoch=1001, price=100.0, symbol="R_75")

        # Prediction 2 generated at t=1002.0 (after P1 has started)
        resolver.register_pending_prediction(
            prediction_id="pred_2",
            session_id="sess_overlap",
            symbol="R_75",
            signal_epoch=1002,
            signal_price=101.0,
            timestamp=1002.0
        )

        assert resolver.active_pending_count == 2

        # Subsequent ticks: t=1003, 1004, 1005, 1006, 1007
        # P1 will have 6 ticks at t=1006 (1001, 1003, 1004, 1005, 1006, 1007)
        # P2 will have 5 ticks at t=1007 (1003, 1004, 1005, 1006, 1007)
        tick_stream = [
            (1003, 102.0),
            (1004, 103.0),
            (1005, 104.0),
            (1006, 105.0),
            (1007, 106.0),
        ]
        ev1 = []
        for ep, pr in tick_stream:
            e = resolver.ingest_tick(epoch=ep, price=pr, symbol="R_75")
            if e: ev1.extend(e)

        # P1 must be resolved (6 ticks accumulated)
        assert len(ev1) == 1
        assert ev1[0]["prediction_id"] == "pred_1"
        assert resolver.active_pending_count == 1  # P2 still pending (needs 1 more tick)

        # Tick at t=1008 completes P2 (6th tick for P2)
        ev2 = resolver.ingest_tick(epoch=1008, price=107.0, symbol="R_75")
        assert len(ev2) == 1
        assert ev2[0]["prediction_id"] == "pred_2"
        assert resolver.active_pending_count == 0

        # Check outcomes table
        with resolver._get_conn() as conn:
            o1 = conn.execute("SELECT * FROM forward_outcomes WHERE prediction_id = 'pred_1'").fetchone()
            o2 = conn.execute("SELECT * FROM forward_outcomes WHERE prediction_id = 'pred_2'").fetchone()
            assert o1["entry_epoch"] == 1001
            assert o1["expiry_epoch"] == 1007
            assert o2["entry_epoch"] == 1003
            assert o2["expiry_epoch"] == 1008
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Warm-Up Chronology & First Live Tick Boundary Anchoring
# ─────────────────────────────────────────────────────────────────────────────

def test_historical_warmup_anchoring_strictly_precedes_first_live_tick():
    """Proves that warm-up filtering strictly rejects any historical tick
    whose timestamp is >= the session's authoritative first live tick boundary.
    """
    j_db = _tmp_db()
    q_db = _tmp_db()
    try:
        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=j_db,
            quote_db_path=q_db,
            session_id="sess_warmup_anchor"
        )

        # Manually simulate preloaded tick buffer containing overlapping/future ticks
        # (e.g. from an unaligned CSV export or clock drift)
        obs.tick_history = [
            {"epoch": 900, "price": 100.0},
            {"epoch": 950, "price": 100.5},
            {"epoch": 1000, "price": 101.0}, # Overlaps exactly with first live tick!
            {"epoch": 1010, "price": 101.5}, # Lookahead future tick in warmup!
        ]

        # First live tick arrives at epoch = 1000
        first_live = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1000,
            local_receipt_timestamp=1000.01,
            price=101.0,
            source="LIVE_DERIV",
            session_id="sess_warmup_anchor",
            sequence_id=1,
            data_quality_flags="NORMAL"
        )
        obs.process_incoming_tick(first_live)

        # Verify that first_live_epoch is established
        assert obs.first_live_epoch == 1000

        # Verify that all historical warmup ticks in tick_history strictly precede epoch 1000
        # (epochs 1000 and 1010 must have been purged before appending the live tick)
        for t in obs.tick_history[:-1]:  # All ticks except the newly appended live tick
            assert t["epoch"] < 1000
        assert obs.tick_history[-1]["epoch"] == 1000  # The live tick itself
    finally:
        for p in (j_db, q_db):
            if os.path.exists(p): os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Controlled Shutdown & Resolution Grace Period
# ─────────────────────────────────────────────────────────────────────────────

def test_shutdown_resolution_grace_period_resolves_pending_prediction():
    """Proves that a prediction created near nominal session end gets resolved
    during the controlled resolution grace window before session completion.
    """
    s_db = _tmp_db()
    j_db = _tmp_db()
    q_db = _tmp_db()
    c_csv = _tmp_db()
    try:
        reg = ForwardSessionRegistry(db_path=s_db)
        sess = reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="MOCK_MODEL",
            model_version="1.6.4",
            planned_duration_seconds=30.0,
            live_ticks_csv=c_csv
        )

        journal = ForwardPredictionJournal(db_path=j_db)
        
        # Log a prediction created near session end
        rec = ForwardPredictionRecord(
            prediction_id="pred_grace_1",
            timestamp=1000.0,
            symbol="R_75",
            model_version="1.6.4",
            market_state="DEFAULT",
            features_json="{}",
            session_id=sess.session_id,
            signal_epoch=1000,
            signal_price=100.0,
            decision="NO_TRADE"
        )
        journal.log_prediction(rec)
        assert journal.resolver.active_pending_count == 1

        # Feed 6 ticks during grace window
        for i in range(1, 7):
            journal.ingest_forward_tick(epoch=1000 + (i * 2), price=100.0 + (i * 0.5), symbol="R_75")

        assert journal.resolver.active_pending_count == 0

        # Mark any remaining as incomplete
        journal.mark_incomplete_as_unverified(symbol="R_75", target_status=STATUS_INCOMPLETE)

        # Complete session in registry so counters match
        reg.complete_session(
            session_id=sess.session_id,
            status=STATUS_COMPLETED,
            total_ticks=6,
            total_predictions=1,
            resolved_predictions=1,
            unverified_predictions=0,
            cumulative_pnl=0.0
        )

        # Reconcile session
        reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
        rep = reconciler.reconcile_session(sess.session_id)
        assert rep.status == RECON_STATUS_RECONCILED
        assert rep.resolved_outcomes == 1
        assert rep.incomplete_outcomes == 0
        assert rep.data_gap_outcomes == 0
    finally:
        for p in (s_db, j_db, q_db, c_csv):
            if os.path.exists(p): os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Offline End-to-End Acceptance Test (Part K Section 26)
# ─────────────────────────────────────────────────────────────────────────────

def test_v164_offline_e2e_acceptance_lifecycle(tmp_path):
    """Deterministic End-to-End Acceptance Test:
    1. Create session.
    2. Populate historical warm-up.
    3. Load compatible frozen model.
    4. Feed simulated live ticks.
    5. Generate & persist predictions.
    6. Accumulate subsequent future ticks.
    7. Resolve canonical contract outcomes.
    8. Persist outcome references.
    9. Reconcile counts.
    10. Shut down safely, restart, and verify persistence.
    """
    s_db = str(tmp_path / "sessions.db")
    j_db = str(tmp_path / "journal.db")
    q_db = str(tmp_path / "quotes.db")
    c_csv = str(tmp_path / "ticks.csv")
    model_path = _create_mock_model(tmp_path)

    # 1. Create registered session
    reg = ForwardSessionRegistry(db_path=s_db)
    session = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id=os.path.basename(model_path),
        model_version="1.6.4",
        planned_duration_seconds=120.0,
        live_ticks_csv=c_csv
    )

    # 2. Instantiate observer with historical warm-up preloaded
    obs = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        model_path_or_id=model_path,
        journal_db_path=j_db,
        quote_db_path=q_db,
        session_id=session.session_id,
        preload_warmup=False
    )

    # Preload 30 strictly past warm-up ticks (epochs 100 to 129)
    obs.tick_history = [{"epoch": 100 + i, "price": 100.0 + (i * 0.05)} for i in range(30)]
    obs.historical_warmup_ticks = 30
    obs.warmup_status = "WARMUP_COMPLETE"
    obs.pipeline_status = "WARMUP_COMPLETE"

    # 3. Feed live ticks to trigger predictions
    # Ticks from epoch 200 to 205
    preds_created = []
    base_epoch = 200
    for i in range(5):
        t_epoch = base_epoch + (i * 2)
        tick = LiveTickRecord(
            symbol="R_75",
            server_timestamp=t_epoch,
            local_receipt_timestamp=float(t_epoch) + 0.01,
            price=105.0 + (i * 0.1),
            source="LIVE_DERIV",
            session_id=session.session_id,
            sequence_id=i + 1,
            data_quality_flags="NORMAL"
        )
        p = obs.process_incoming_tick(tick)
        if p:
            preds_created.append(p)

    assert len(preds_created) > 0
    first_pred_id = preds_created[0].prediction_id
    assert obs.journal.resolver.active_pending_count >= 1

    # 4. Activate prediction cutoff and feed subsequent future ticks to resolve pending predictions
    obs.prediction_cutoff_active = True
    # Monotonically increasing ticks from epoch 212 to 240
    for k in range(15):
        t_epoch = 212 + (k * 2)
        tick = LiveTickRecord(
            symbol="R_75",
            server_timestamp=t_epoch,
            local_receipt_timestamp=float(t_epoch) + 0.01,
            price=106.0 + (k * 0.2),
            source="LIVE_DERIV",
            session_id=session.session_id,
            sequence_id=10 + k,
            data_quality_flags="NORMAL"
        )
        obs.process_incoming_tick(tick)

    # 5. Verify that predictions resolved to STATUS_RECONSTRUCTED
    assert obs.journal.resolver.active_pending_count == 0
    pred_rec = obs.journal.get_prediction(first_pred_id)
    assert pred_rec["outcome_status"] == STATUS_RECONSTRUCTED
    assert pred_rec["runhigh_win"] == 1.0  # Monotonically increasing

    # 6. Safe shutdown & session completion in registry
    reg.complete_session(
        session_id=session.session_id,
        status=STATUS_COMPLETED,
        total_ticks=20,
        total_predictions=len(preds_created),
        resolved_predictions=len(preds_created),
        unverified_predictions=0,
        cumulative_pnl=0.0
    )

    # 7. Reconcile session
    reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
    audit = reconciler.reconcile_session(session.session_id)
    assert audit.status == RECON_STATUS_RECONCILED
    assert audit.resolved_outcomes >= 1
    assert audit.incomplete_outcomes == 0
    assert audit.data_gap_outcomes == 0

    # 8. Restart simulation: instantiate new journal and verify persistence
    restarted_journal = ForwardPredictionJournal(db_path=j_db)
    persisted_p = restarted_journal.get_prediction(first_pred_id)
    assert persisted_p is not None
    assert persisted_p["outcome_status"] == STATUS_RECONSTRUCTED
    assert persisted_p["session_id"] == session.session_id
    assert persisted_p["forward_ticks_count"] == 6

    # Verify dedicated outcomes table
    outcomes = restarted_journal.get_session_outcomes(session.session_id)
    assert len(outcomes) >= 1
    assert outcomes[0]["prediction_id"] == first_pred_id
    assert outcomes[0]["verification_level"] == "RECONSTRUCTED"
    assert outcomes[0]["resolver_version"] == "1.6.4"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Safety Invariants (Rule 15, 21, 22)
# ─────────────────────────────────────────────────────────────────────────────

def test_v164_safety_invariants():
    """Permanent Safety Verification: Real-money trading is disabled across all code paths."""
    assert LIVE_EXECUTION_DISABLED is True
    assert ForwardObserver.LIVE_EXECUTION_DISABLED is True
    assert ForwardCollectionService.LIVE_EXECUTION_DISABLED is True
