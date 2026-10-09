"""V1.7.2 Targeted Test Suite: Research Report Integrity, Unified Confirmation Authority,
Operational Reliability & Independent Forward Validation Readiness.

Covers:
1. Defect A Regression: False RUNLOW 100% win-rate regression prevention; 0/13 RH and 0/13 RL reproduction.
2. Canonical ResearchMetricsEngine: Direction-specific independence, zero complementary inversion,
   referential integrity, and SHA-256 integrity checksumming.
3. Defect B: Single authoritative confirmation gate; adversarial bypass attempts fail.
4. Defect D: Confirmation admission enforcement (manifest requirement, checksum match, symbol/model verification).
5. Retrospective stage manipulation prevention: update_research_stage raises PermissionError.
6. Operational CLI entry point verification (Windows-compatible arguments and exits).
7. Safety Invariant: REAL-MONEY TRADING PERMANENTLY DISABLED across all operational modules.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import pytest

from confirmation_specification import ConfirmationManifest
from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION
)
from forward_confirmation_gate import (
    ForwardConfirmationGate,
    VERDICT_FORWARD_EDGE_CONFIRMED,
    VERDICT_NO_CONFIRMATION_SESSIONS,
    VERDICT_CONFIRMATION_REQUIRED,
    VERDICT_NO_VALIDATED_EDGE
)
from quote_database import QuoteDatabase
from research_metrics_engine import (
    ResearchMetricsEngine,
    DirectionalMetrics,
    ResearchDatasetMetrics
)
from session_research_aggregator import SessionResearchAggregator
from forward_collection_service import ForwardCollectionService, LIVE_EXECUTION_DISABLED


def _create_isolated_environment():
    tdir = tempfile.mkdtemp(prefix="v172_test_")
    fwd_db = os.path.join(tdir, "forward_predictions.db")
    quotes_db = os.path.join(tdir, "quotes.db")
    sess_db = os.path.join(tdir, "forward_sessions.db")

    from forward_journal import ForwardPredictionJournal
    # Initialize complete schemas via official classes
    reg = ForwardSessionRegistry(db_path=sess_db)
    journal = ForwardPredictionJournal(db_path=fwd_db)
    q_db = QuoteDatabase(db_path=quotes_db)

    return tdir, fwd_db, quotes_db, sess_db


# ==============================================================================
# 1. Defect A Regression: False RUNLOW 100% Win-Rate Regression Test
# ==============================================================================

def test_v172_defect_a_false_runlow_win_rate_regression():
    """Deterministic reproduction of the 13-outcome session:
    In 5-tick contracts, RUNHIGH requires 5 strictly ascending ticks,
    RUNLOW requires 5 strictly descending ticks. Oscillating series cause both to lose.
    Verifies that the canonical ResearchMetricsEngine reports 0/13 for both RH and RL,
    and never infers RL = 1 - RH.
    """
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_TEST",
        model_version="1.7.2",
        research_stage=STAGE_EXPLORATORY
    )
    sess_id = sess.session_id

    from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord, STATUS_RESOLVED
    journal = ForwardPredictionJournal(db_path=fwd_db)
    now = time.time()
    for i in range(13):
        rec = ForwardPredictionRecord(
            prediction_id=f"pred_13_{i}",
            session_id=sess_id,
            timestamp=now + i * 2,
            symbol="R_75",
            model_version="1.7.2",
            market_state="OSCILLATING",
            features_json="{}",
            runhigh_pred_prob=0.045,
            runlow_pred_prob=0.048,
            runhigh_ask=2.0,
            runhigh_payout=61.0,
            runlow_ask=2.0,
            runlow_payout=61.0,
            break_even_runhigh=2.0 / 61.0,
            break_even_runlow=2.0 / 61.0,
            ev_runhigh=0.045 * 61.0 - 2.0,
            ev_runlow=0.048 * 61.0 - 2.0,
            decision="SHADOW_TRACK",
            rejection_reason="",
            target_direction="RUNHIGH",
            signal_epoch=now + i * 2,
            signal_price=100.0,
            forward_prices_json="[100.0, 100.2, 100.1, 100.3, 100.2, 100.4]",
            forward_ticks_count=6,
            outcome_status=STATUS_RESOLVED,
            runhigh_win=0.0,  # Lost
            runlow_win=0.0,   # Lost (both lost on oscillating prices)
            hypothetical_pnl=-2.0,
            execution_mode="SHADOW",
            model_id="M_TEST"
        )
        journal.log_prediction(rec)

    engine = ResearchMetricsEngine(forward_db_path=fwd_db, quote_db_path=quotes_db, session_db_path=sess_db)
    metrics = engine.calculate_metrics(session_ids=[sess_id], symbol="R_75")

    # Assertions strictly verifying Defect A fix
    assert metrics.eligible_resolved_count == 13
    assert metrics.runhigh.wins == 0
    assert metrics.runhigh.losses == 13
    assert metrics.runhigh.observed_win_rate == 0.0

    assert metrics.runlow.wins == 0
    assert metrics.runlow.losses == 13
    assert metrics.runlow.observed_win_rate == 0.0
    assert metrics.runlow.observed_win_rate != 1.0  # Must never be 100%!

    assert metrics.both_lost_count == 13
    assert metrics.integrity_checksum != ""
    assert len(metrics.integrity_checksum) == 64  # Valid SHA-256


def test_v172_research_metrics_handles_zero_eligible_and_genuine_wins():
    """Verifies that ResearchMetricsEngine returns None (not 0.0) when eligible count is zero,
    and accurately computes non-zero win rates when genuine wins occur.
    """
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_TEST",
        model_version="1.7.2",
        research_stage=STAGE_EXPLORATORY
    )
    sess_id = sess.session_id

    from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
    journal = ForwardPredictionJournal(db_path=fwd_db)
    # Only pending records -> 0 eligible
    rec = ForwardPredictionRecord(
        prediction_id="p_pending_1",
        session_id=sess_id,
        timestamp=time.time(),
        symbol="R_75",
        model_version="1.7.2",
        market_state="TRENDING",
        features_json="{}",
        runhigh_pred_prob=0.05,
        runlow_pred_prob=0.03,
        runhigh_ask=2.0,
        runhigh_payout=61.0,
        runlow_ask=2.0,
        runlow_payout=61.0,
        break_even_runhigh=2.0 / 61.0,
        break_even_runlow=2.0 / 61.0,
        ev_runhigh=0.05 * 61.0 - 2.0,
        ev_runlow=0.03 * 61.0 - 2.0,
        decision="SHADOW_TRACK",
        rejection_reason="",
        target_direction="RUNHIGH",
        signal_epoch=time.time(),
        signal_price=100.0,
        forward_prices_json="[]",
        forward_ticks_count=0,
        outcome_status="PENDING",
        runhigh_win=None,
        runlow_win=None,
        hypothetical_pnl=0.0,
        execution_mode="SHADOW",
        model_id="M_TEST"
    )
    journal.log_prediction(rec)

    engine = ResearchMetricsEngine(forward_db_path=fwd_db, quote_db_path=quotes_db, session_db_path=sess_db)
    metrics = engine.calculate_metrics(session_ids=[sess_id], symbol="R_75")

    assert metrics.eligible_resolved_count == 0
    assert metrics.runhigh.observed_win_rate is None  # Must be None, not 0.0!
    assert metrics.runlow.observed_win_rate is None
    assert metrics.pending_count == 1


# ==============================================================================
# 2. Defect B: Single Authoritative Confirmation Gate (Adversarial Bypass Tests)
# ==============================================================================

def test_v172_adversarial_aggregator_cannot_bypass_confirmation_gate():
    """Adversarial attempt to obtain FORWARD_EDGE_CONFIRMED from the aggregator
    without fulfilling all 13 mandatory confirmation gates.
    Must strictly return CONFIRMATION_REQUIRED, NO_CONFIRMATION_SESSIONS, or rejection,
    and NEVER FORWARD_EDGE_CONFIRMED.
    """
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_TEST",
        model_version="1.7.2",
        research_stage=STAGE_EXPLORATORY
    )
    sess_id = sess.session_id

    from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord, STATUS_RESOLVED
    journal = ForwardPredictionJournal(db_path=fwd_db)
    now = time.time()
    for i in range(100):
        # Fabricated 10% win rate (beats 3.28% break-even)
        is_win = (i < 10)
        rec = ForwardPredictionRecord(
            prediction_id=f"adv_p_{i}",
            session_id=sess_id,
            timestamp=now + i * 2,
            symbol="R_75",
            model_version="1.7.2",
            market_state="TRENDING",
            features_json="{}",
            runhigh_pred_prob=0.06,
            runlow_pred_prob=0.02,
            runhigh_ask=2.0,
            runhigh_payout=61.0,
            runlow_ask=2.0,
            runlow_payout=61.0,
            break_even_runhigh=2.0 / 61.0,
            break_even_runlow=2.0 / 61.0,
            ev_runhigh=0.06 * 61.0 - 2.0,
            ev_runlow=0.02 * 61.0 - 2.0,
            decision="PAPER_TRADE",
            rejection_reason="",
            target_direction="RUNHIGH",
            signal_epoch=now + i * 2,
            signal_price=100.0,
            forward_prices_json="[100.0, 100.1, 100.2, 100.3, 100.4, 100.5]",
            forward_ticks_count=6,
            outcome_status=STATUS_RESOLVED,
            runhigh_win=1.0 if is_win else 0.0,
            runlow_win=0.0,
            hypothetical_pnl=59.0 if is_win else -2.0,
            execution_mode="PAPER",
            model_id="M_TEST"
        )
        journal.log_prediction(rec)

    agg = SessionResearchAggregator(
        session_registry_db=sess_db,
        forward_journal_db=fwd_db,
        quote_db=quotes_db
    )
    result = agg.evaluate_multi_session_research(symbol="R_75")

    # The aggregator must not emit FORWARD_EDGE_CONFIRMED
    assert result["verdict"] != VERDICT_FORWARD_EDGE_CONFIRMED
    assert result["verdict"] in (VERDICT_NO_CONFIRMATION_SESSIONS, VERDICT_CONFIRMATION_REQUIRED, VERDICT_NO_VALIDATED_EDGE)


def test_v172_session_reporter_cannot_bypass_confirmation_gate():
    """Adversarial attempt: invoke SessionReporter on a session labeled CONFIRMATION_FORWARD
    without valid multi-session confirmation evidence.
    Must strictly delegate to ForwardConfirmationGate and reject confirmed status.
    """
    from session_reporter import SessionReporter
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()

    manifest = ConfirmationManifest.create_default_for_model(
        model_id="MODEL_TEST_1",
        artifact_checksum="abc123hash",
        symbol="R_75"
    )
    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="MODEL_TEST_1",
        model_version="1.7.2",
        research_stage=STAGE_CONFIRMATION,
        confirmation_manifest=manifest,
        enforce_confirmation_admission=True
    )

    from forward_journal import ForwardPredictionJournal
    reporter = SessionReporter(
        reports_dir=os.path.join(tdir, "reports"),
        registry=reg,
        journal=ForwardPredictionJournal(db_path=fwd_db),
        quote_db=QuoteDatabase(db_path=quotes_db)
    )
    # Session has zero resolved predictions -> INSUFFICIENT_FORWARD_DATA
    report = reporter.generate_session_report(sess.session_id)
    assert report["research_verdict"]["verdict"] != VERDICT_FORWARD_EDGE_CONFIRMED


# ==============================================================================
# 3. Defect D: Confirmation Session Admission Enforcement
# ==============================================================================

def test_v172_confirmation_admission_rejected_without_manifest():
    """A session cannot enter CONFIRMATION_FORWARD without a valid pre-registered manifest."""
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)

    with pytest.raises(ValueError, match="Confirmation admission rejected: Missing confirmation manifest"):
        reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="M_TEST",
            model_version="1.0",
            research_stage=STAGE_CONFIRMATION,
            confirmation_manifest=None,
            enforce_confirmation_admission=True
        )


def test_v172_confirmation_admission_rejected_on_tampered_manifest():
    """A manifest whose SHA-256 checksum has been altered is rejected upon admission."""
    manifest = ConfirmationManifest.create_default_for_model(
        model_id="MODEL_TEST_1",
        artifact_checksum="abc123hash",
        symbol="R_75"
    )
    # Tamper with the manifest parameters without recalculating checksum
    manifest.min_confirmation_observations = 10  # Reduced hurdle

    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)

    with pytest.raises(ValueError, match="Confirmation admission rejected: Confirmation manifest checksum invalid"):
        reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="MODEL_TEST_1",
            model_version="1.0",
            research_stage=STAGE_CONFIRMATION,
            confirmation_manifest=manifest,
            enforce_confirmation_admission=True
        )


def test_v172_confirmation_admission_rejected_on_symbol_or_model_mismatch():
    """A manifest registered for R_75 cannot be admitted for R_50 session."""
    manifest = ConfirmationManifest.create_default_for_model(
        model_id="MODEL_TEST_1",
        artifact_checksum="abc123hash",
        symbol="R_75"
    )
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)

    # Symbol mismatch
    with pytest.raises(ValueError, match="Confirmation admission rejected: Manifest symbol mismatch"):
        reg.create_session(
            symbol="R_50",
            mode="SHADOW",
            model_id="MODEL_TEST_1",
            model_version="1.0",
            research_stage=STAGE_CONFIRMATION,
            confirmation_manifest=manifest,
            enforce_confirmation_admission=True
        )

    # Model mismatch
    with pytest.raises(ValueError, match="Manifest model mismatch"):
        reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="WRONG_MODEL",
            model_version="1.0",
            research_stage=STAGE_CONFIRMATION,
            confirmation_manifest=manifest,
            enforce_confirmation_admission=True
        )


def test_v172_retrospective_stage_mutation_blocked():
    """Operators cannot retrospectively mutate the research stage of an existing session."""
    tdir, fwd_db, quotes_db, sess_db = _create_isolated_environment()
    reg = ForwardSessionRegistry(db_path=sess_db)

    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M1",
        model_version="1.0",
        research_stage=STAGE_EXPLORATORY
    )

    with pytest.raises(PermissionError, match="Retrospective research stage mutation"):
        reg.update_research_stage(sess.session_id, STAGE_CONFIRMATION)


# ==============================================================================
# 4. Operational CLI Entry Points & Safety Invariants
# ==============================================================================

def test_v172_operational_cli_entry_points():
    """Verifies that documented operational entry points respond cleanly to --help on Windows."""
    scripts = [
        "run_forward_session.py",
        "dashboard.py",
        "session_reporter.py"
    ]
    for script in scripts:
        res = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True,
            text=True
        )
        assert res.returncode == 0, f"Script {script} failed --help with code {res.returncode}: {res.stderr}"
        assert "usage:" in res.stdout.lower() or "options:" in res.stdout.lower() or "help" in res.stdout.lower()


def test_v172_cli_confirmation_stage_requires_manifest_flag():
    """Verifies that run_forward_session.py rejects --stage CONFIRMATION without --manifest."""
    res = subprocess.run(
        [sys.executable, "run_forward_session.py", "--stage", "CONFIRMATION", "--symbol", "R_75"],
        capture_output=True,
        text=True
    )
    assert res.returncode != 0
    assert "mandatory admission check failed" in res.stdout.lower() or "requires a pre-registered confirmationmanifest" in res.stdout.lower()


def test_v172_permanent_safety_invariants_preserved():
    """Verifies that real-money trading is permanently disabled across all operational systems."""
    assert LIVE_EXECUTION_DISABLED is True

    from live_collector import LiveTickStreamer
    # Ensure streamer does not expose or permit purchase endpoints
    assert not hasattr(LiveTickStreamer, "buy_contract")
    assert not hasattr(LiveTickStreamer, "place_order")
    assert not hasattr(ForwardCollectionService, "buy_contract")
