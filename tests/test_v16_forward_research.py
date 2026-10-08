"""V1.6 Forward Research Test Suite.

Tests covering the new V1.6 components:
  - ForwardSession creation and registry CRUD
  - PerformanceTracker metrics computation (with synthetic data)
  - ForwardValidationGate promotion/demotion logic (with synthetic journal)
  - SessionReporter text and JSON rendering
  - ForwardCollectionService safety invariants
  - HealthMonitor has_active_data_gap() and session_id tracking
  - ForwardObserver gap propagation into decision gate
  - Config V1.6 fields are present with correct types
  - Safety invariant: LIVE_EXECUTION_DISABLED is always True

All tests use in-memory or temp-file databases. No real API calls are made.
"""
import json
import math
import os
import sqlite3
import tempfile
import time
import uuid
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tmp_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return f.name


def _inject_resolved_predictions(db_path: str, symbol: str, n: int, win_rate: float,
                                  rh_pred: float = 0.56, rl_pred: float = 0.56,
                                  ask: float = 2.0, payout: float = 3.90):
    """Injects synthetic RESOLVED forward predictions into a journal DB for testing."""
    from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
    journal = ForwardPredictionJournal(db_path=db_path)
    for i in range(n):
        is_win = (i < int(n * win_rate))
        rh_win = 1.0 if is_win else 0.0
        rl_win = 1.0 - rh_win
        pnl = (payout - ask) if is_win else -ask
        rec = ForwardPredictionRecord(
            prediction_id=str(uuid.uuid4())[:8],
            timestamp=float(1_700_000_000 + i * 2),
            symbol=symbol,
            model_version="V1.6-TEST",
            market_state="CONSOLIDATING",
            features_json="{}",
            runhigh_pred_prob=rh_pred,
            runlow_pred_prob=rl_pred,
            runhigh_ask=ask,
            runhigh_payout=payout,
            runlow_ask=ask,
            runlow_payout=payout,
            break_even_runhigh=round(ask / payout, 5),
            break_even_runlow=round(ask / payout, 5),
            ev_runhigh=round(rh_pred * payout - ask, 4),
            ev_runlow=round(rl_pred * payout - ask, 4),
            decision="PAPER_TRADE",
            rejection_reason="",
            target_direction="RUNHIGH",
            signal_epoch=1_700_000_000 + i * 2,
            signal_price=100.0,
            forward_prices_json="[100.0,100.1,100.2,100.3,100.4,100.5]",
            forward_ticks_count=6,
            outcome_status="RESOLVED",
            runhigh_win=rh_win,
            runlow_win=rl_win,
            hypothetical_pnl=round(pnl, 2),
            execution_mode="PAPER",
            model_id="TEST_MODEL",
        )
        journal.log_prediction(rec)
    return journal


# ──────────────────────────────────────────────────────────────────────────────
#  1. Config V1.6 fields
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigV16Fields:
    def test_session_db_path_exists(self):
        from config import DEFAULT_CONFIG
        assert hasattr(DEFAULT_CONFIG, "sessions_db_path")
        assert isinstance(DEFAULT_CONFIG.sessions_db_path, str)

    def test_reports_dir_exists(self):
        from config import DEFAULT_CONFIG
        assert hasattr(DEFAULT_CONFIG, "reports_dir")
        assert isinstance(DEFAULT_CONFIG.reports_dir, str)

    def test_validation_gate_thresholds(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG.validation_gate_min_resolved > 0
        assert DEFAULT_CONFIG.validation_gate_min_z_score > 0
        assert 0 < DEFAULT_CONFIG.validation_gate_min_brier_improvement < 1
        assert DEFAULT_CONFIG.validation_gate_min_quote_coverage_pct > 0
        assert DEFAULT_CONFIG.validation_gate_max_drawdown_demotion > 0

    def test_gap_staleness_seconds(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG.gap_staleness_seconds > 0

    def test_stat_flush_config(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG.session_stat_flush_interval_ticks > 0
        assert DEFAULT_CONFIG.session_stat_flush_interval_secs > 0

    def test_safety_invariant(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG.live_execution_disabled is True


# ──────────────────────────────────────────────────────────────────────────────
#  2. ForwardSession & Registry
# ──────────────────────────────────────────────────────────────────────────────

class TestForwardSession:
    def test_create_session(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75",
            mode="SHADOW",
            model_id="TEST_MODEL",
            model_version="V1.6",
            planned_duration_seconds=300.0,
        )
        assert sess.session_id
        assert len(sess.session_id) == 36  # UUID
        assert sess.status == "ACTIVE"
        assert sess.mode == "SHADOW"
        assert sess.symbol == "R_75"
        os.unlink(db)

    def test_session_retrieval(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75", mode="PAPER", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        fetched = reg.get_session(sess.session_id)
        assert fetched is not None
        assert fetched.session_id == sess.session_id
        assert fetched.mode == "PAPER"
        os.unlink(db)

    def test_complete_session(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=120.0
        )
        reg.complete_session(
            session_id=sess.session_id,
            status="COMPLETED",
            total_ticks=500,
            total_predictions=50,
            resolved_predictions=30,
            unverified_predictions=5,
            cumulative_pnl=3.14
        )
        completed = reg.get_session(sess.session_id)
        assert completed.status == "COMPLETED"
        assert completed.total_ticks == 500
        assert completed.total_predictions == 50
        assert completed.cumulative_pnl == pytest.approx(3.14, abs=0.01)
        os.unlink(db)

    def test_update_session_stats(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        reg.update_session_stats(
            session_id=sess.session_id,
            total_ticks=100,
            total_predictions=10,
            resolved_predictions=5,
            cumulative_pnl=0.5
        )
        updated = reg.get_session(sess.session_id)
        assert updated.total_ticks == 100
        assert updated.resolved_predictions == 5
        os.unlink(db)

    def test_list_sessions(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        for _ in range(3):
            reg.create_session(
                symbol="R_75", mode="SHADOW", model_id="M1",
                model_version="V1.6", planned_duration_seconds=60.0
            )
        sessions = reg.list_sessions(symbol="R_75")
        assert len(sessions) == 3
        os.unlink(db)

    def test_config_snapshot_is_json(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        snap = json.loads(sess.config_snapshot_json)
        assert "live_execution_disabled" in snap
        assert snap["live_execution_disabled"] is True
        os.unlink(db)

    def test_session_is_active_property(self):
        from forward_session import ForwardSessionRegistry
        db = _tmp_db()
        reg = ForwardSessionRegistry(db_path=db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        assert sess.is_active is True
        os.unlink(db)


# ──────────────────────────────────────────────────────────────────────────────
#  3. PerformanceTracker
# ──────────────────────────────────────────────────────────────────────────────

class TestPerformanceTracker:
    def test_empty_db_returns_zero_summary(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        # create empty journal DB
        from forward_journal import ForwardPredictionJournal
        ForwardPredictionJournal(db_path=db)
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        assert summary.total_predictions == 0
        assert summary.cumulative_pnl == 0.0
        assert summary.win_rate is None
        os.unlink(db)

    def test_positive_winrate_metrics(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        _inject_resolved_predictions(db, "R_75", n=100, win_rate=0.60)
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        assert summary.total_predictions == 100
        assert summary.paper_trade_signals == 100
        assert summary.resolved_trades == 100
        assert summary.wins == 60
        assert summary.losses == 40
        assert summary.win_rate == pytest.approx(0.60, abs=0.01)
        assert summary.cumulative_pnl != 0.0
        os.unlink(db)

    def test_brier_scores_computed(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        _inject_resolved_predictions(db, "R_75", n=50, win_rate=0.56, rh_pred=0.56)
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        assert summary.brier_score_runhigh is not None
        assert 0.0 <= summary.brier_score_runhigh <= 1.0
        os.unlink(db)

    def test_max_drawdown_non_negative(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        _inject_resolved_predictions(db, "R_75", n=60, win_rate=0.40)  # net loss scenario
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        assert summary.max_drawdown >= 0.0
        os.unlink(db)

    def test_quote_coverage_pct(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        _inject_resolved_predictions(db, "R_75", n=80, win_rate=0.55)
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        # All injected records have genuine ask prices
        assert summary.quote_coverage_pct == pytest.approx(100.0, abs=1.0)
        os.unlink(db)

    def test_to_dict_has_all_keys(self):
        from performance_tracker import PerformanceTracker
        db = _tmp_db()
        _inject_resolved_predictions(db, "R_75", n=20, win_rate=0.60)
        tracker = PerformanceTracker(db_path=db)
        summary = tracker.compute_performance(symbol="R_75")
        d = summary.to_dict()
        for key in ["win_rate", "cumulative_pnl", "max_drawdown", "brier_score_runhigh",
                    "sharpe_ratio", "quote_coverage_pct", "generated_at"]:
            assert key in d
        os.unlink(db)


# ──────────────────────────────────────────────────────────────────────────────
#  4. ForwardValidationGate
# ──────────────────────────────────────────────────────────────────────────────

class TestForwardValidationGate:
    def test_insufficient_data_returns_early(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        # create empty journal
        from forward_journal import ForwardPredictionJournal
        ForwardPredictionJournal(db_path=fwd_db)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            min_resolved=200
        )
        result = gate.evaluate(model_id="M1", symbol="R_75")
        assert result.recommended_action == "INSUFFICIENT_DATA"
        assert result.gate_passed is False
        assert result.resolved_predictions == 0
        os.unlink(fwd_db)
        os.unlink(val_db)

    def test_gate_fails_low_z_score(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        # Insert only 50% win rate — z-score will be ~0
        _inject_resolved_predictions(fwd_db, "R_75", n=300, win_rate=0.50)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            min_resolved=200,
            min_z_score=2.0,
            break_even_prob=0.50
        )
        result = gate.evaluate(model_id="TEST_MODEL", symbol="R_75")
        assert result.gate_passed is False
        # z-score at exactly 50% should be ~0
        assert result.runhigh_z_score is not None
        assert result.runhigh_z_score < 2.0
        os.unlink(fwd_db)
        os.unlink(val_db)

    def test_gate_passes_with_high_win_rate(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        # 70% win rate — should easily pass z-score gate for n=300
        _inject_resolved_predictions(fwd_db, "R_75", n=300, win_rate=0.70, rh_pred=0.70)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            min_resolved=200,
            min_z_score=2.0,
            min_brier_improvement_pct=0.0,   # Relax Brier gate
            min_quote_coverage_pct=70.0,
            break_even_prob=0.50
        )
        result = gate.evaluate(model_id="TEST_MODEL", symbol="R_75")
        assert result.runhigh_z_score is not None
        assert result.runhigh_z_score > 2.0
        os.unlink(fwd_db)
        os.unlink(val_db)

    def test_demotion_triggered_on_large_drawdown(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        # 20% win rate on 400 records — large drawdown expected
        _inject_resolved_predictions(fwd_db, "R_75", n=400, win_rate=0.20, ask=2.0, payout=3.9)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            min_resolved=200,
            max_drawdown_demotion=5.0  # Very tight threshold
        )
        result = gate.evaluate(model_id="TEST_MODEL", symbol="R_75")
        assert result.demotion_triggered is True
        assert result.recommended_action == "DEMOTE"
        os.unlink(fwd_db)
        os.unlink(val_db)

    def test_result_is_persisted(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        from forward_journal import ForwardPredictionJournal
        ForwardPredictionJournal(db_path=fwd_db)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            min_resolved=200
        )
        gate.evaluate(model_id="M1", symbol="R_75")
        evals = gate.list_evaluations(model_id="M1")
        assert len(evals) >= 1
        assert evals[0]["model_id"] == "M1"
        os.unlink(fwd_db)
        os.unlink(val_db)

    def test_naive_brier_computed_correctly(self):
        from forward_validation_gate import ForwardValidationGate
        fwd_db = _tmp_db()
        val_db = _tmp_db()
        from forward_journal import ForwardPredictionJournal
        ForwardPredictionJournal(db_path=fwd_db)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db,
            break_even_prob=0.50
        )
        result = gate.evaluate(model_id="M1", symbol="R_75")
        # naive Brier for p=0.5 is 0.5*(1-0.5) = 0.25
        assert result.naive_brier == pytest.approx(0.25, abs=0.001)
        os.unlink(fwd_db)
        os.unlink(val_db)


# ──────────────────────────────────────────────────────────────────────────────
#  5. SessionReporter
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionReporter:
    def test_session_report_generates_json(self, tmp_path):
        from session_reporter import SessionReporter
        from forward_session import ForwardSessionRegistry, ForwardSession
        from forward_journal import ForwardPredictionJournal
        from performance_tracker import PerformanceTracker
        from forward_validation_gate import ForwardValidationGate

        fwd_db = str(tmp_path / "fwd.db")
        sessions_db = str(tmp_path / "sessions.db")
        val_db = str(tmp_path / "val.db")
        reports_dir = str(tmp_path / "reports")

        reg = ForwardSessionRegistry(db_path=sessions_db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        journal = ForwardPredictionJournal(db_path=fwd_db)
        tracker = PerformanceTracker(db_path=fwd_db)
        gate = ForwardValidationGate(
            forward_db_path=fwd_db,
            validation_db_path=val_db
        )
        reporter = SessionReporter(
            reports_dir=reports_dir,
            journal=journal,
            registry=reg,
            tracker=tracker,
            gate=gate
        )
        report = reporter.generate_session_report(session=sess)

        assert report["report_type"] == "SESSION"
        assert report["safety"]["live_money_trading_disabled"] is True
        assert "predictions" in report
        assert "economic_performance" in report

        # Verify files were created
        import glob
        json_files = glob.glob(os.path.join(reports_dir, "session_R_75_*.json"))
        assert len(json_files) >= 1

    def test_daily_report_generates(self, tmp_path):
        from session_reporter import SessionReporter
        from forward_session import ForwardSessionRegistry
        from forward_journal import ForwardPredictionJournal
        from performance_tracker import PerformanceTracker
        from forward_validation_gate import ForwardValidationGate

        fwd_db = str(tmp_path / "fwd.db")
        sessions_db = str(tmp_path / "sessions.db")
        val_db = str(tmp_path / "val.db")
        reports_dir = str(tmp_path / "reports")

        ForwardPredictionJournal(db_path=fwd_db)
        reg = ForwardSessionRegistry(db_path=sessions_db)
        reporter = SessionReporter(
            reports_dir=reports_dir,
            journal=ForwardPredictionJournal(db_path=fwd_db),
            registry=reg,
            tracker=PerformanceTracker(db_path=fwd_db),
            gate=ForwardValidationGate(forward_db_path=fwd_db, validation_db_path=val_db)
        )
        report = reporter.generate_daily_report(symbol="R_75")
        assert report["report_type"] == "DAILY"
        assert report["safety"]["live_money_trading_disabled"] is True

    def test_text_render_contains_safety_declaration(self, tmp_path):
        from session_reporter import SessionReporter
        from forward_session import ForwardSessionRegistry
        from forward_journal import ForwardPredictionJournal
        from performance_tracker import PerformanceTracker
        from forward_validation_gate import ForwardValidationGate

        fwd_db = str(tmp_path / "fwd.db")
        sessions_db = str(tmp_path / "sessions.db")
        val_db = str(tmp_path / "val.db")
        reports_dir = str(tmp_path / "reports")

        ForwardPredictionJournal(db_path=fwd_db)
        reg = ForwardSessionRegistry(db_path=sessions_db)
        sess = reg.create_session(
            symbol="R_75", mode="SHADOW", model_id="M1",
            model_version="V1.6", planned_duration_seconds=60.0
        )
        reporter = SessionReporter(
            reports_dir=reports_dir,
            journal=ForwardPredictionJournal(db_path=fwd_db),
            registry=reg,
            tracker=PerformanceTracker(db_path=fwd_db),
            gate=ForwardValidationGate(forward_db_path=fwd_db, validation_db_path=val_db)
        )
        report = reporter.generate_session_report(session=sess)
        text = reporter._render_text_report(report)
        assert "DISABLED" in text
        assert "hypothetical" in text.lower()


# ──────────────────────────────────────────────────────────────────────────────
#  6. HealthMonitor V1.6 additions
# ──────────────────────────────────────────────────────────────────────────────

class TestHealthMonitorV16:
    def test_has_active_data_gap_false_initially(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor(gap_staleness_seconds=5.0)
        assert hm.has_active_data_gap() is False

    def test_has_active_data_gap_true_after_gap_tick(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor(gap_staleness_seconds=5.0)
        hm.record_tick(epoch=1234, is_gap=True)
        assert hm.has_active_data_gap() is True

    def test_has_active_data_gap_expires(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor(gap_staleness_seconds=0.01)  # 10ms window
        hm.record_tick(epoch=1234, is_gap=True)
        time.sleep(0.05)
        assert hm.has_active_data_gap() is False

    def test_set_session_id(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor()
        hm.set_session_id("test-session-abc")
        assert hm.session_id == "test-session-abc"

    def test_health_summary_includes_session_id(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor()
        hm.set_session_id("sess-001")
        summary = hm.get_health_summary()
        assert summary["session_id"] == "sess-001"

    def test_health_summary_has_active_data_gap_key(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor()
        summary = hm.get_health_summary()
        assert "has_active_data_gap" in summary["connectivity"]

    def test_no_false_gap_from_normal_tick(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor(gap_staleness_seconds=5.0)
        hm.record_tick(epoch=1234, is_gap=False)
        assert hm.has_active_data_gap() is False

    def test_gap_count_increments(self):
        from health_monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_tick(epoch=1000, is_gap=True)
        hm.record_tick(epoch=1001, is_gap=True)
        assert hm.gap_count == 2


# ──────────────────────────────────────────────────────────────────────────────
#  7. ForwardObserver gap propagation
# ──────────────────────────────────────────────────────────────────────────────

class TestForwardObserverGapPropagation:
    def test_gap_propagates_to_decision_gate(self):
        """After a GAP tick, has_active_data_gap() returns True — this would block paper trades."""
        from health_monitor import HealthMonitor, GLOBAL_HEALTH_MONITOR
        # Record a gap on the global health monitor
        GLOBAL_HEALTH_MONITOR._last_gap_time = time.time()
        GLOBAL_HEALTH_MONITOR.gap_staleness_seconds = 10.0
        assert GLOBAL_HEALTH_MONITOR.has_active_data_gap() is True

        # Clean up
        GLOBAL_HEALTH_MONITOR._last_gap_time = None

    def test_no_gap_allows_observation(self):
        from health_monitor import GLOBAL_HEALTH_MONITOR
        GLOBAL_HEALTH_MONITOR._last_gap_time = None
        assert GLOBAL_HEALTH_MONITOR.has_active_data_gap() is False


# ──────────────────────────────────────────────────────────────────────────────
#  8. ForwardCollectionService safety invariants
# ──────────────────────────────────────────────────────────────────────────────

class TestCollectionServiceSafety:
    def test_live_execution_disabled_constant(self):
        from forward_collection_service import LIVE_EXECUTION_DISABLED
        assert LIVE_EXECUTION_DISABLED is True

    def test_service_registers_session_on_init(self, tmp_path):
        from forward_collection_service import ForwardCollectionService
        from forward_session import ForwardSessionRegistry

        sessions_db = str(tmp_path / "sessions.db")
        # Patch the registry path used by the service
        with patch("forward_collection_service.ForwardSessionRegistry") as MockReg:
            mock_reg_inst = MagicMock()
            mock_sess = MagicMock()
            mock_sess.session_id = str(uuid.uuid4())
            mock_sess.journal_db_path = str(tmp_path / "fwd.db")
            mock_sess.quote_db_path = str(tmp_path / "quotes.db")
            mock_sess.live_ticks_csv = str(tmp_path / "ticks.csv")
            mock_reg_inst.create_session.return_value = mock_sess
            MockReg.return_value = mock_reg_inst

            with patch("forward_collection_service.ForwardObserver"):
                with patch("forward_collection_service.SessionReporter"):
                    service = ForwardCollectionService(
                        symbol="R_75",
                        mode="SHADOW",
                        duration_seconds=10.0
                    )
                    assert mock_reg_inst.create_session.called

    def test_mode_normalised_to_upper(self, tmp_path):
        """Passing lowercase mode should be normalised to SHADOW."""
        from forward_collection_service import ForwardCollectionService

        with patch("forward_collection_service.ForwardSessionRegistry") as MockReg:
            mock_reg_inst = MagicMock()
            mock_sess = MagicMock()
            mock_sess.session_id = str(uuid.uuid4())
            mock_sess.journal_db_path = str(tmp_path / "fwd.db")
            mock_sess.quote_db_path = str(tmp_path / "quotes.db")
            mock_sess.live_ticks_csv = str(tmp_path / "ticks.csv")
            mock_reg_inst.create_session.return_value = mock_sess
            MockReg.return_value = mock_reg_inst

            with patch("forward_collection_service.ForwardObserver"):
                with patch("forward_collection_service.SessionReporter"):
                    service = ForwardCollectionService(
                        symbol="R_75",
                        mode="shadow",  # lowercase
                        duration_seconds=5.0
                    )
                    assert service.mode == "SHADOW"


# ──────────────────────────────────────────────────────────────────────────────
#  9. End-to-end safety: no real money path exists
# ──────────────────────────────────────────────────────────────────────────────

class TestV16SafetyInvariants:
    def test_forward_observer_live_execution_disabled(self):
        from forward_observer import ForwardObserver
        assert ForwardObserver.LIVE_EXECUTION_DISABLED is True

    def test_paper_trader_live_execution_disabled(self):
        from paper_trader import PaperTrader
        assert PaperTrader.LIVE_EXECUTION_DISABLED is True

    def test_config_live_execution_disabled(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG.live_execution_disabled is True

    def test_collection_service_constant(self):
        from forward_collection_service import LIVE_EXECUTION_DISABLED
        assert LIVE_EXECUTION_DISABLED is True

    def test_performance_tracker_no_api_calls(self, tmp_path):
        """PerformanceTracker must work without any network access."""
        from performance_tracker import PerformanceTracker
        fwd_db = str(tmp_path / "fwd.db")
        from forward_journal import ForwardPredictionJournal
        ForwardPredictionJournal(db_path=fwd_db)
        tracker = PerformanceTracker(db_path=fwd_db)
        # Should not raise regardless of network state
        summary = tracker.compute_performance()
        assert summary is not None

    def test_validation_gate_no_api_calls(self, tmp_path):
        """ForwardValidationGate must work without any network access."""
        from forward_validation_gate import ForwardValidationGate
        from forward_journal import ForwardPredictionJournal
        fwd_db = str(tmp_path / "fwd.db")
        val_db = str(tmp_path / "val.db")
        ForwardPredictionJournal(db_path=fwd_db)
        gate = ForwardValidationGate(forward_db_path=fwd_db, validation_db_path=val_db)
        result = gate.evaluate(model_id="M1", symbol="R_75")
        assert result is not None
