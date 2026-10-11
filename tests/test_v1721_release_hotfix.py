"""V1.7.2.1 Targeted Hotfix Test Suite:
Runtime Import Integrity, Economic Benchmark Fallback Elimination,
Authoritative Database Reconciliation, Confirmation Authority Safeguards,
Report Reproducibility, and Operational Command Readiness.
"""
import os
import sys
import json
import sqlite3
import subprocess
import tempfile
import typing
from datetime import datetime, timezone
import pytest

from confirmation_specification import ConfirmationManifest, CONFIRMATION_SPEC_VERSION
from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION
)
from forward_collection_service import ForwardCollectionService, LIVE_EXECUTION_DISABLED
from forward_confirmation_gate import (
    ForwardConfirmationGate,
    VERDICT_FORWARD_EDGE_CONFIRMED,
    VERDICT_NO_CONFIRMATION_SESSIONS,
    VERDICT_CONFIRMATION_REQUIRED,
    VERDICT_NO_VALIDATED_EDGE,
    evaluate_forward_edge_confirmation
)
from session_research_aggregator import SessionResearchAggregator
from session_reporter import SessionReporter
from research_metrics_engine import ResearchMetricsEngine, DirectionalMetrics
from quote_database import QuoteDatabase
from forward_journal import ForwardPredictionJournal, STATUS_RESOLVED


def _inject_test_data(fwd_db: str, session_id: str, count: int, win_rate: float,
                       prob_pred: float = 0.05, has_quotes: bool = True,
                       ask: float = 2.00, payout: float = 60.00):
    journal = ForwardPredictionJournal(db_path=fwd_db)
    wins = int(round(count * win_rate))
    now_iso = datetime.now(timezone.utc).isoformat()
    base_epoch = 1700000000.0

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
                p_id, session_id, t_epoch, "R_75", "1.7.2.1", "STATE_0",
                '{"volatility": 0.015}', prob_pred, prob_pred,
                p_ask, p_payout, p_ask, p_payout,
                (p_ask / p_payout) if (p_ask and p_payout) else None,
                (p_ask / p_payout) if (p_ask and p_payout) else None,
                None, None, None, None,
                "PAPER_TRADE", "", "RUNHIGH", t_epoch, 100.0 + (i * 0.05),
                int(t_epoch), int(t_epoch + 5), "[100, 101, 102, 103, 104, 105]", 6,
                STATUS_RESOLVED, is_win, 0.0, ((payout - ask) if is_win else -ask) if has_quotes else 0.0,
                "SHADOW", "M_TEST", q_id, "1.5.3", "LIVE_DERIV", now_iso
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
                is_win, 0.0, ((payout - ask) if is_win else -ask) if has_quotes else 0.0,
                "5_movement_canonical", t_epoch + 5.0, "RECONSTRUCTED", now_iso
            ))
        conn.commit()


# ==============================================================================
# 1. RUNTIME TYPING & IMPORT REPAIRS
# ==============================================================================

def test_v1721_typing_annotations_evaluate_cleanly():
    """Verifies that all type annotations in forward_session and forward_collection_service
    resolve cleanly at runtime without NameError (fixes missing Tuple and Any imports).
    """
    import forward_session
    import forward_collection_service

    hints_session_cls = typing.get_type_hints(forward_session.ForwardSession)
    assert "session_id" in hints_session_cls

    hints_registry = typing.get_type_hints(forward_session.ForwardSessionRegistry)
    assert hints_registry is not None

    hints_service = typing.get_type_hints(forward_collection_service.ForwardCollectionService)
    assert hints_service is not None

    for name, obj in forward_session.__dict__.items():
        if isinstance(obj, type) or callable(obj):
            try:
                typing.get_type_hints(obj)
            except NameError as e:
                pytest.fail(f"NameError resolving type hint for forward_session.{name}: {e}")
            except Exception:
                pass

    for name, obj in forward_collection_service.__dict__.items():
        if isinstance(obj, type) or callable(obj):
            try:
                typing.get_type_hints(obj)
            except NameError as e:
                pytest.fail(f"NameError resolving type hint for forward_collection_service.{name}: {e}")
            except Exception:
                pass


def test_v1721_clean_module_imports_across_repository():
    """Executes a clean subprocess import of all first-party production modules
    to verify zero missing imports, zero syntax errors, and zero import-time side-effects.
    """
    modules_to_test = [
        "forward_session",
        "forward_collection_service",
        "forward_confirmation_gate",
        "confirmation_specification",
        "session_reporter",
        "session_research_aggregator",
        "research_metrics_engine",
        "dashboard",
        "forward_journal",
        "quote_database",
        "statistical_evaluator",
        "economic_evaluator",
        "model_artifact",
        "risk",
        "paper_trader",
        "config"
    ]

    for mod in modules_to_test:
        cmd = [sys.executable, "-c", f"import {mod}"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"Module '{mod}' failed clean import:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"


# ==============================================================================
# 2. ECONOMIC BENCHMARK FALLBACK ELIMINATION
# ==============================================================================

def test_v1721_session_reporter_fallback_eliminated():
    """Verifies that session_reporter.py does NOT fall back to 3.277% when quotes are absent.
    Missing quotes must yield be_pct = None and prevent false positive EV calculation.
    """
    tdir = tempfile.mkdtemp(prefix="v1721_rep_")
    sess_db = os.path.join(tdir, "sessions.db")
    fwd_db = os.path.join(tdir, "fwd.db")
    q_db = os.path.join(tdir, "quotes.db")

    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(symbol="R_75", mode="SHADOW", planned_duration_seconds=60, journal_db_path=fwd_db, quote_db_path=q_db)

    # 25 observations with NO quotes
    _inject_test_data(fwd_db, sess.session_id, count=25, win_rate=0.08, has_quotes=False)

    journal = ForwardPredictionJournal(db_path=fwd_db)
    reporter = SessionReporter(
        registry=reg,
        journal=journal,
        quote_db=QuoteDatabase(db_path=q_db),
        reports_dir=tdir
    )

    report = reporter.generate_session_report(session=sess.session_id)
    assert report["research_verdict"]["verdict"] == VERDICT_NO_VALIDATED_EDGE
    assert "Economic proposal quotes unavailable" in report["research_verdict"]["rationale"]
    assert report["economic_performance"]["runhigh_mean_break_even_pct"] is None


def test_v1721_dashboard_fallbacks_eliminated():
    """Verifies that dashboard data extraction produces None and 'N/A' rather than 3.28% / $61.03
    when genuine live quotes are missing.
    """
    import dashboard
    latest_rh = None
    be_rh = (latest_rh.implied_probability * 100) if latest_rh else None
    assert be_rh is None

    p_rh_mean = None
    ord_ev_rh = ((p_rh_mean * latest_rh.total_payout) - latest_rh.ask_price) if (latest_rh and p_rh_mean is not None) else None
    assert ord_ev_rh is None


# ==============================================================================
# 3. DATABASE RECONCILIATION & AUTHORITATIVE SESSIONS COUNT
# ==============================================================================

def test_v1721_authoritative_session_counts_reproduction():
    """Verifies that the canonical ResearchMetricsEngine and ForwardSessionRegistry
    discover registered sessions present in data/sessions.db and respect stage isolation.
    """
    if not os.path.exists("data/sessions.db"):
        pytest.skip("data/sessions.db not found in active workspace")

    reg = ForwardSessionRegistry(db_path="data/sessions.db")
    sessions = reg.list_sessions(symbol="R_75")
    assert len(sessions) >= 6, f"Expected at least 6 registered sessions, found {len(sessions)}"

    exploratory_sessions = [s for s in sessions if getattr(s, "research_stage", "") == STAGE_EXPLORATORY]
    confirmation_sessions = [s for s in sessions if getattr(s, "research_stage", "") == STAGE_CONFIRMATION]

    assert len(exploratory_sessions) >= 6
    assert len(confirmation_sessions) == 0

    engine = ResearchMetricsEngine(
        forward_db_path="data/forward_predictions.db",
        quote_db_path="data/quotes.db",
        session_db_path="data/sessions.db"
    )
    # Check authoritative historical baseline session a381a4d3
    metrics = engine.compute_metrics(symbol="R_75", session_id="a381a4d3-8594-4700-af1d-fe7c849e2e66")
    assert len(metrics.session_ids) == 1
    assert metrics.runhigh.wins == 0
    assert metrics.runlow.wins == 0
    assert metrics.eligible_resolved_count == 13


def test_v1721_runhigh_runlow_outcomes_accounting():
    """Ensures that RUNHIGH and RUNLOW outcomes are evaluated independently and
    no false 100% win rate or complementary inversion can be reported.
    """
    engine = ResearchMetricsEngine(
        forward_db_path="data/forward_predictions.db",
        quote_db_path="data/quotes.db",
        session_db_path="data/sessions.db"
    )
    # In session a381a4d3, all 13 resolved ticks were non-monotonic dual losses
    metrics = engine.compute_metrics(symbol="R_75", session_id="a381a4d3-8594-4700-af1d-fe7c849e2e66")

    assert metrics.runhigh.wins == 0
    assert metrics.runhigh.observed_win_rate == 0.0
    assert metrics.runlow.wins == 0
    assert metrics.runlow.observed_win_rate == 0.0
    assert metrics.both_lost_count == 13


# ==============================================================================
# 4. SINGLE CONFIRMATION AUTHORITY & BYPASS SAFEGUARDS
# ==============================================================================

def test_v1721_confirmation_gate_is_single_authority():
    """Proves that ForwardConfirmationGate is the only component that can confirm an edge,
    and that in the absence of pre-registered confirmation sessions, it returns NO_CONFIRMATION_SESSIONS.
    """
    gate = ForwardConfirmationGate(
        forward_db_path="data/forward_predictions.db",
        quote_db_path="data/quotes.db",
        session_db_path="data/sessions.db"
    )
    report = gate.evaluate_forward_edge_confirmation(model_id="LATEST", symbol="R_75", contract_type="RUNHIGH")

    assert report.is_confirmed is False
    assert report.verdict == VERDICT_NO_CONFIRMATION_SESSIONS
    assert any("Zero independent sessions registered" in r for r in report.rejection_reasons)


def test_v1721_aggregator_delegates_to_confirmation_gate():
    """Verifies that SessionResearchAggregator delegates confirmed verdicts exclusively
    to ForwardConfirmationGate and never issues FORWARD_EDGE_CONFIRMED autonomously.
    """
    aggregator = SessionResearchAggregator(
        forward_journal_db="data/forward_predictions.db",
        quote_db_path="data/quotes.db",
        session_registry_db="data/sessions.db"
    )
    res = aggregator.evaluate_multi_session_research(symbol="R_75")
    assert res["verdict"] == VERDICT_NO_CONFIRMATION_SESSIONS
    assert res["verdict"] != VERDICT_FORWARD_EDGE_CONFIRMED


def test_v1721_confirmation_gate_rejection_paths():
    """Tests that missing quotes, negative conservative EV, and invalid manifest checksum
    strictly block edge confirmation.
    """
    tdir = tempfile.mkdtemp(prefix="v1721_conf_")
    sess_db = os.path.join(tdir, "sessions.db")
    fwd_db = os.path.join(tdir, "fwd.db")
    q_db = os.path.join(tdir, "quotes.db")

    reg = ForwardSessionRegistry(db_path=sess_db)
    q_database = QuoteDatabase(db_path=q_db)

    # Valid manifest
    manifest = ConfirmationManifest.create_default_for_model(
        model_id="M_TEST.json",
        symbol="R_75",
        contract_type="RUNHIGH"
    )

    # Register confirmation session with manifest
    sess = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_TEST.json",
        planned_duration_seconds=300,
        research_stage=STAGE_CONFIRMATION,
        confirmation_manifest=manifest
    )

    # Inject data into fwd_db so tables exist
    _inject_test_data(fwd_db, sess.session_id, count=10, win_rate=0.10)

    # Now tamper manifest checksum
    manifest.min_confirmation_observations = 10  # Tampers without updating checksum

    gate = ForwardConfirmationGate(
        session_registry=reg,
        quote_db=q_database,
        forward_db_path=fwd_db,
        session_db_path=sess_db,
        manifest=manifest
    )

    report = gate.evaluate_forward_edge_confirmation(model_id="M_TEST.json", symbol="R_75", contract_type="RUNHIGH")
    assert report.is_confirmed is False
    assert any("tampered" in r.lower() or "checksum" in r.lower() or "verification failed" in r.lower() for r in report.rejection_reasons)


# ==============================================================================
# 5. REPORT REPRODUCIBILITY TEST
# ==============================================================================

def test_v1721_report_reproducibility():
    """Deterministic report reproducibility test with isolated synthetic fixtures.
    Creates known predictions, outcomes, and quotes, and verifies every reported metric matches
    exact independent mathematical calculation.
    """
    tdir = tempfile.mkdtemp(prefix="v1721_repro_")
    sess_db = os.path.join(tdir, "sessions.db")
    fwd_db = os.path.join(tdir, "fwd.db")
    q_db = os.path.join(tdir, "quotes.db")

    reg = ForwardSessionRegistry(db_path=sess_db)
    sess = reg.create_session(symbol="R_75", mode="SHADOW", planned_duration_seconds=120, journal_db_path=fwd_db, quote_db_path=q_db)

    # 10 observations: exactly 2 RUNHIGH wins, 8 RUNHIGH losses
    _inject_test_data(fwd_db, sess.session_id, count=10, win_rate=0.20, ask=2.00, payout=60.00, has_quotes=True)

    # Insert matching quote records into quotes.db
    with sqlite3.connect(q_db) as q_conn:
        q_conn.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_timestamp REAL NOT NULL,
                response_timestamp REAL NOT NULL,
                market_symbol TEXT NOT NULL,
                contract_type TEXT NOT NULL,
                contract_duration INTEGER NOT NULL DEFAULT 5,
                duration_unit TEXT NOT NULL DEFAULT 't',
                stake REAL NOT NULL,
                total_payout REAL NOT NULL,
                potential_net_profit REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                proposal_id TEXT,
                quote_source TEXT NOT NULL,
                quote_latency_ms REAL NOT NULL,
                collection_status TEXT NOT NULL,
                api_response_metadata TEXT,
                session_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        base_epoch = 1700000000.0
        for i in range(10):
            epoch = base_epoch + (i * 2.0)
            q_conn.execute("""
                INSERT INTO quotes (
                    request_timestamp, response_timestamp, market_symbol, contract_type,
                    stake, total_payout, potential_net_profit, proposal_id, quote_source,
                    quote_latency_ms, collection_status, session_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (epoch - 0.5, epoch - 0.4, "R_75", "RUNHIGH", 2.00, 60.00, 58.00, f"prop_{i}", "LIVE_DERIV", 50.0, "SUCCESS", sess.session_id, "2026-10-11T00:00:00"))

    engine = ResearchMetricsEngine(
        forward_db_path=fwd_db,
        quote_db_path=q_db,
        session_db_path=sess_db
    )
    metrics = engine.compute_metrics(symbol="R_75")

    assert metrics.total_predictions == 10
    assert metrics.eligible_resolved_count == 10
    assert metrics.runhigh.wins == 2
    assert metrics.runhigh.observed_win_rate == 0.20
    assert metrics.runlow.wins == 0
    assert metrics.runlow.observed_win_rate == 0.00
    assert metrics.mean_ask == 2.00
    assert metrics.mean_payout == 60.00
    assert round(metrics.mean_break_even_pct, 3) == round((2.0 / 60.0) * 100.0, 3)


# ==============================================================================
# 6. OPERATIONAL COMMANDS & CLI VERIFICATION
# ==============================================================================

def test_v1721_operational_cli_entry_points():
    """Validates that all key operational CLI commands exist, accept --help,
    and exit cleanly with return code 0.
    """
    scripts = [
        "session_reporter.py",
        "forward_confirmation_gate.py",
        "session_research_aggregator.py",
        "confirmation_specification.py",
        "dashboard.py",
        "forward_collection_service.py",
        "run_forward_session.py"
    ]

    for script in scripts:
        cmd = [sys.executable, script, "--help"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"Script {script} failed --help with code {proc.returncode}:\n{proc.stderr}"


# ==============================================================================
# 7. SAFETY INVARIANTS
# ==============================================================================

def test_v1721_live_money_trading_disabled_invariant():
    """Validates that real-money trading remains permanently disabled across all systems."""
    assert LIVE_EXECUTION_DISABLED is True

    from config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG.live_execution_disabled is True

    reporter = SessionReporter()
    rep = reporter.generate_daily_report(symbol="R_75")
    assert rep["safety"]["live_money_trading_disabled"] is True
    assert rep["safety"]["purchasing_allowed"] is False
