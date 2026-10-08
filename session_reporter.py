"""Session and Daily Report Generator (V1.6.1).

Generates structured research reports at two cadences:
  1. SESSION REPORT: produced at the end of each ForwardSession.
  2. DAILY REPORT: summarises all sessions from the most recent UTC calendar day.

Each report includes all V1.6.1 Section 17 audit metrics:
  - Session metadata (ID, symbol, mode, model, duration)
  - Number of ticks received
  - Number of quotes recorded
  - Number of eligible feature windows
  - Number of predictions generated & persisted
  - Number of outcomes resolved, pending, incomplete, data gaps
  - RUNHIGH / RUNLOW estimated win probabilities
  - RUNHIGH / RUNLOW observed win probabilities
  - Brier scores and Expected Calibration Errors (ECE)
  - Genuine quote coverage %
  - Economic performance metrics (hypothetical PnL, drawdown)
  - Validation gate status and recommendations
  - Safety invariant declaration (live money disabled)

Reports are saved as JSON (machine-readable) and plain text (human-readable)
to the reports/ directory with timestamped filenames.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from forward_journal import ForwardPredictionJournal
from forward_session import ForwardSessionRegistry, ForwardSession
from forward_validation_gate import ForwardValidationGate
from health_monitor import GLOBAL_HEALTH_MONITOR
from model_manager import ModelManager
from performance_tracker import PerformanceTracker
from probability import stationary_block_bootstrap_ci, non_overlapping_sensitivity_analysis
from quote_database import QuoteDatabase
from session_reconciler import SessionReconciler

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


class SessionReporter:
    """Generates end-of-session and daily research reports."""

    def __init__(
        self,
        reports_dir: Optional[str] = None,
        journal: Optional[ForwardPredictionJournal] = None,
        registry: Optional[ForwardSessionRegistry] = None,
        tracker: Optional[PerformanceTracker] = None,
        gate: Optional[ForwardValidationGate] = None,
        quote_db: Optional[QuoteDatabase] = None,
        reconciler: Optional[SessionReconciler] = None
    ):
        self.reports_dir = reports_dir or REPORTS_DIR
        os.makedirs(self.reports_dir, exist_ok=True)
        self.journal = journal or ForwardPredictionJournal()
        self.registry = registry or ForwardSessionRegistry()
        self.tracker = tracker or PerformanceTracker()
        self.gate = gate or ForwardValidationGate()
        self.quote_db = quote_db or QuoteDatabase()
        self.reconciler = reconciler or SessionReconciler(
            registry_db_path=self.registry.db_path,
            journal_db_path=self.journal.db_path,
            quote_db_path=self.quote_db.db_path
        )

    def _utc_now_str(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _safe_round(self, val, digits: int = 4):
        try:
            return round(float(val), digits) if val is not None else None
        except (TypeError, ValueError):
            return None

    def generate_session_report(
        self,
        session: Any,
        health_snapshot: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generates a complete session report dictionary adhering to V1.6.2 Section 16 & 17."""
        if isinstance(session, str):
            sess_obj = self.registry.get_session(session)
            if not sess_obj:
                raise ValueError(f"Session '{session}' not found in registry.")
            session = sess_obj
        else:
            # Refresh session from registry to get latest tick accounting and status
            refreshed = self.registry.get_session(session.session_id)
            if refreshed:
                session = refreshed

        # Run automated reconciliation engine (V1.6.2 Section 12)
        recon_report = self.reconciler.reconcile_session(session.session_id)

        # Accuracy metrics from journal strictly filtered by session_id (V1.6.2 Section 10)
        accuracy = self.journal.get_accuracy_metrics(symbol=session.symbol, session_id=session.session_id)

        # Economic performance strictly filtered by session_id
        perf = self.tracker.compute_performance(
            symbol=session.symbol,
            mode=session.mode,
            session_id=session.session_id
        )

        # Health telemetry
        health = health_snapshot or GLOBAL_HEALTH_MONITOR.get_health_summary()

        # Quotes count strictly filtered by session_id
        quote_cov = self.quote_db.report_quote_coverage(session.symbol, session_id=session.session_id)
        quotes_recorded = quote_cov.get("total_quotes", 0)

        # Model info
        mgr = ModelManager()
        model_path = mgr.get_latest_model_for_symbol(session.symbol)
        model_info = {}
        if model_path:
            try:
                from model_artifact import ModelArtifact
                art = ModelArtifact.load_from_file(model_path)
                model_info = {
                    "model_id": art.model_id,
                    "model_version": art.model_version,
                    "approval_status": art.approval_status,
                    "validation_sample_count": art.validation_sample_count,
                }
            except Exception:
                pass

        # Validation gate snapshot
        gate_result = None
        if session.model_id and session.model_id != "NONE":
            try:
                g = self.gate.evaluate(model_id=session.model_id, symbol=session.symbol)
                gate_result = g.to_dict()
            except Exception:
                pass

        # Dependence-aware uncertainty (V1.6.2 Section 17)
        session_preds = self.journal.get_session_predictions(session.session_id)
        rh_wins = [float(r["runhigh_win"]) for r in session_preds if r.get("runhigh_win") is not None]
        rl_wins = [float(r["runlow_win"]) for r in session_preds if r.get("runlow_win") is not None]

        rh_boot_ci = None
        rl_boot_ci = None
        rh_non_overlapping = None
        rl_non_overlapping = None

        if len(rh_wins) >= 5:
            rh_boot_ci = stationary_block_bootstrap_ci(np.array(rh_wins), num_resamples=500, mean_block_length=5)
            rh_non_overlapping = non_overlapping_sensitivity_analysis(pd.Series(rh_wins), stride=5)
        if len(rl_wins) >= 5:
            rl_boot_ci = stationary_block_bootstrap_ci(np.array(rl_wins), num_resamples=500, mean_block_length=5)
            rl_non_overlapping = non_overlapping_sensitivity_analysis(pd.Series(rl_wins), stride=5)

        total_preds = accuracy.get("total_predictions", 0)

        report = {
            "report_type": "SESSION",
            "generated_at": self._utc_now_str(),
            "session": {
                "session_id": session.session_id,
                "symbol": session.symbol,
                "mode": session.mode,
                "model_id": session.model_id,
                "status": session.status,
                "start_time_utc": session.start_datetime_utc,
                "planned_duration_seconds": session.planned_duration_seconds,
                "actual_duration_seconds": session.actual_duration_seconds,
                "reconciliation_status": recon_report.status,
                "is_verified": recon_report.is_verified,
            },
            "reconciliation": recon_report.to_dict(),
            "safety": {
                "live_money_trading_disabled": True,
                "purchasing_allowed": False,
                "declaration": "REAL-MONEY TRADING DISABLED. All metrics are non-purchasing forward research observations."
            },
            "model": model_info,
            "predictions": {
                "total": total_preds,
                "resolved": accuracy.get("resolved_predictions", 0),
                "pending": accuracy.get("pending_predictions", 0),
                "unverified": accuracy.get("unverified_predictions", 0),
                "brier_score_runhigh": accuracy.get("brier_score_runhigh"),
                "brier_score_runlow": accuracy.get("brier_score_runlow"),
                "realized_runhigh_win_rate": accuracy.get("realized_runhigh_win_rate"),
                "realized_runlow_win_rate": accuracy.get("realized_runlow_win_rate"),
            },
            "lifecycle_counts": {
                "ticks_received": session.total_ticks,
                "live_ticks": session.live_ticks,
                "warmup_ticks": session.warmup_ticks,
                "duplicate_ticks": session.duplicate_ticks,
                "rejected_ticks": session.rejected_ticks,
                "quotes_recorded": quotes_recorded,
                "eligible_feature_windows": total_preds,
                "predictions_generated": total_preds,
                "predictions_persisted": total_preds,
                "outcomes_resolved": accuracy.get("resolved_predictions", 0),
                "outcomes_pending": accuracy.get("pending_predictions", 0),
                "outcomes_incomplete": accuracy.get("incomplete_predictions", 0),
                "outcomes_data_gap": accuracy.get("data_gap_predictions", 0),
                "outcomes_unverified": accuracy.get("unverified_predictions", 0),
            },
            "statistical_evidence": {
                "runhigh_estimated_win_prob": accuracy.get("runhigh_estimated_mean_prob"),
                "runlow_estimated_win_prob": accuracy.get("runlow_estimated_mean_prob"),
                "runhigh_observed_win_prob": accuracy.get("runhigh_observed_win_rate"),
                "runlow_observed_win_prob": accuracy.get("runlow_observed_win_rate"),
                "brier_score_runhigh": accuracy.get("brier_score_runhigh"),
                "brier_score_runlow": accuracy.get("brier_score_runlow"),
                "calibration_error_runhigh": accuracy.get("calibration_error_runhigh"),
                "calibration_error_runlow": accuracy.get("calibration_error_runlow"),
                "genuine_quote_coverage_pct": accuracy.get("quote_coverage_pct", 0.0),
                "dependence_aware_uncertainty": {
                    "method": "Politis & Romano Stationary Block Bootstrap (mean block length = 5)",
                    "runhigh_bootstrap_95_ci": list(rh_boot_ci) if rh_boot_ci else None,
                    "runlow_bootstrap_95_ci": list(rl_boot_ci) if rl_boot_ci else None,
                    "runhigh_non_overlapping_sensitivity": rh_non_overlapping,
                    "runlow_non_overlapping_sensitivity": rl_non_overlapping,
                }
            },
            "economic_performance": perf.to_dict(),
            "health_telemetry": {
                "ticks": health.get("ticks", {}),
                "quotes": health.get("quotes", {}),
                "connectivity": health.get("connectivity", {}),
            },
            "validation_gate": gate_result,
        }

        # Persist both JSON and text
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sid_short = session.session_id[:8]
        json_path = os.path.join(
            self.reports_dir, f"session_{session.symbol}_{sid_short}_{ts}.json"
        )
        txt_path = os.path.join(
            self.reports_dir, f"session_{session.symbol}_{sid_short}_{ts}.txt"
        )
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._render_text_report(report))

        return report

    def generate_daily_report(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Generates a daily summary over all sessions from the past 24h UTC."""
        now = datetime.now(timezone.utc)
        day_start = (now - timedelta(days=1)).timestamp()

        all_sessions = self.registry.list_sessions(symbol=symbol, limit=100)
        day_sessions = [s for s in all_sessions if s.start_time >= day_start]

        accuracy = self.journal.get_accuracy_metrics(symbol=symbol)
        perf = self.tracker.compute_performance(symbol=symbol)
        health = GLOBAL_HEALTH_MONITOR.get_health_summary()
        quote_cov = self.quote_db.report_quote_coverage(symbol or "R_75")

        total_preds = accuracy.get("total_predictions", 0)

        report = {
            "report_type": "DAILY",
            "period_utc": f"{now.strftime('%Y-%m-%d')} (last 24h)",
            "generated_at": self._utc_now_str(),
            "safety": {
                "live_money_trading_disabled": True,
                "purchasing_allowed": False,
                "declaration": "REAL-MONEY TRADING DISABLED. All metrics are non-purchasing forward research observations."
            },
            "sessions_today": len(day_sessions),
            "session_summary": [
                {
                    "session_id": s.session_id[:8],
                    "mode": s.mode,
                    "status": s.status,
                    "ticks": s.total_ticks,
                    "predictions": s.total_predictions,
                    "resolved": s.resolved_predictions,
                    "pnl": s.cumulative_pnl,
                }
                for s in day_sessions
            ],
            "lifecycle_counts": {
                "quotes_recorded": quote_cov.get("total_quotes", 0),
                "predictions_generated": total_preds,
                "predictions_persisted": total_preds,
                "outcomes_resolved": accuracy.get("resolved_predictions", 0),
                "outcomes_pending": accuracy.get("pending_predictions", 0),
                "outcomes_incomplete": accuracy.get("incomplete_predictions", 0),
                "outcomes_data_gap": accuracy.get("data_gap_predictions", 0),
                "outcomes_unverified": accuracy.get("unverified_predictions", 0),
            },
            "statistical_evidence": {
                "runhigh_estimated_win_prob": accuracy.get("runhigh_estimated_mean_prob"),
                "runlow_estimated_win_prob": accuracy.get("runlow_estimated_mean_prob"),
                "runhigh_observed_win_prob": accuracy.get("runhigh_observed_win_rate"),
                "runlow_observed_win_prob": accuracy.get("runlow_observed_win_rate"),
                "brier_score_runhigh": accuracy.get("brier_score_runhigh"),
                "brier_score_runlow": accuracy.get("brier_score_runlow"),
                "calibration_error_runhigh": accuracy.get("calibration_error_runhigh"),
                "calibration_error_runlow": accuracy.get("calibration_error_runlow"),
                "genuine_quote_coverage_pct": accuracy.get("quote_coverage_pct", 0.0),
            },
            "aggregate_economic_performance": perf.to_dict(),
            "system_health": {
                "ticks": health.get("ticks", {}),
                "quotes": health.get("quotes", {}),
                "connectivity": health.get("connectivity", {}),
            },
        }

        ts = now.strftime("%Y%m%d")
        sym_tag = symbol or "ALL"
        json_path = os.path.join(self.reports_dir, f"daily_{sym_tag}_{ts}.json")
        txt_path = os.path.join(self.reports_dir, f"daily_{sym_tag}_{ts}.txt")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._render_text_report(report))

        return report

    def _render_text_report(self, report: Dict[str, Any]) -> str:
        """Converts a report dict to a human-readable plain-text format."""
        lines = []
        rtype = report.get("report_type", "REPORT")
        lines.append(f"=== DERIV QUANTITATIVE RESEARCH — {rtype} REPORT ===")
        lines.append(f"Generated at: {report.get('generated_at', '')}")
        lines.append("Safety: REAL-MONEY TRADING DISABLED (Zero buy orders / Research Only)")
        lines.append("")

        if rtype == "SESSION":
            sess = report.get("session", {})
            lines.append(f"Session ID   : {sess.get('session_id', '')[:8]}")
            lines.append(f"Symbol       : {sess.get('symbol', '')}")
            lines.append(f"Mode         : {sess.get('mode', '')}")
            lines.append(f"Model ID     : {sess.get('model_id', '')}")
            lines.append(f"Status       : {sess.get('status', '')}")
            lines.append(f"Start UTC    : {sess.get('start_time_utc', '')}")
            lines.append(f"Duration (s) : {sess.get('actual_duration_seconds', 'N/A')}")
            lines.append("")

        counts = report.get("lifecycle_counts", {})
        lines.append("--- LIFECYCLE & OBSERVATION COUNTS ---")
        lines.append(f"  Ticks Received      : {counts.get('ticks_received', 'N/A')}")
        lines.append(f"  Live Genuine Ticks  : {counts.get('live_ticks', 0)}")
        lines.append(f"  Warm-up Ticks       : {counts.get('warmup_ticks', 0)}")
        lines.append(f"  Duplicate Ticks     : {counts.get('duplicate_ticks', 0)}")
        lines.append(f"  Rejected Ticks      : {counts.get('rejected_ticks', 0)}")
        lines.append(f"  Quotes Recorded     : {counts.get('quotes_recorded', 0)}")
        lines.append(f"  Predictions Total   : {counts.get('predictions_persisted', 0)}")
        lines.append(f"  Outcomes Resolved   : {counts.get('outcomes_resolved', 0)}")
        lines.append(f"  Outcomes Pending    : {counts.get('outcomes_pending', 0)}")
        lines.append(f"  Outcomes Incomplete : {counts.get('outcomes_incomplete', 0)}")
        lines.append(f"  Outcomes Data Gap   : {counts.get('outcomes_data_gap', 0)}")
        lines.append(f"  Outcomes Unverified : {counts.get('outcomes_unverified', 0)}")
        lines.append("")

        recon = report.get("reconciliation")
        if recon:
            lines.append("--- DATA INTEGRITY & RECONCILIATION ---")
            lines.append(f"  Reconciliation Status: {recon.get('status')}")
            lines.append(f"  Statistically Verified: {recon.get('is_verified')}")
            lines.append(f"  Live Deriv Provenance : {recon.get('provenance', {}).get('is_live_deriv')}")
            lines.append(f"  Chronology Violations : {recon.get('chronology', {}).get('chronology_errors', 0)}")
            lines.append(f"  Future Quote Violations: {recon.get('chronology', {}).get('future_quote_errors', 0)}")
            if recon.get("issues"):
                lines.append("  Integrity Issues:")
                for iss in recon["issues"]:
                    lines.append(f"    [X] {iss}")
            lines.append("")

        stat = report.get("statistical_evidence", {})
        lines.append("--- STATISTICAL EVIDENCE ---")
        lines.append(f"  RUNHIGH Est Prob    : {stat.get('runhigh_estimated_win_prob')}")
        lines.append(f"  RUNLOW Est Prob     : {stat.get('runlow_estimated_win_prob')}")
        lines.append(f"  RUNHIGH Obs Prob    : {stat.get('runhigh_observed_win_prob')}")
        lines.append(f"  RUNLOW Obs Prob     : {stat.get('runlow_observed_win_prob')}")
        lines.append(f"  Brier RH            : {stat.get('brier_score_runhigh')}")
        lines.append(f"  Brier RL            : {stat.get('brier_score_runlow')}")
        lines.append(f"  Calib Error RH      : {stat.get('calibration_error_runhigh')}")
        lines.append(f"  Calib Error RL      : {stat.get('calibration_error_runlow')}")
        lines.append(f"  Quote Coverage      : {stat.get('genuine_quote_coverage_pct')}%")
        dep_unc = stat.get("dependence_aware_uncertainty", {})
        if dep_unc and dep_unc.get("runhigh_bootstrap_95_ci"):
            rh_ci = dep_unc.get("runhigh_bootstrap_95_ci")
            lines.append(f"  RH Block Boot 95% CI: [{rh_ci[0]:.2%}, {rh_ci[1]:.2%}] (Politis & Romano, L=5)")
        lines.append("")

        perf_key = "economic_performance" if "economic_performance" in report else "aggregate_economic_performance"
        perf = report.get(perf_key, {})
        lines.append("--- ECONOMIC PERFORMANCE (HYPOTHETICAL) ---")
        lines.append(f"  Paper Trade Signals : {perf.get('paper_trade_signals', 0)}")
        lines.append(f"  Resolved Trades     : {perf.get('resolved_trades', 0)}")
        lines.append(f"  Win Rate            : {perf.get('win_rate')}")
        lines.append(f"  Cumulative PnL      : {perf.get('cumulative_pnl')}")
        lines.append(f"  Mean PnL/Trade      : {perf.get('mean_pnl_per_trade')}")
        lines.append(f"  Max Drawdown        : {perf.get('max_drawdown')}")
        lines.append("")

        gate = report.get("validation_gate")
        if gate:
            lines.append("--- VALIDATION GATE ---")
            lines.append(f"  Gate Passed         : {gate.get('gate_passed')}")
            lines.append(f"  Recommended Action  : {gate.get('recommended_action')}")
            lines.append(f"  Demotion Triggered  : {gate.get('demotion_triggered')}")
            for r in gate.get("gate_reasons", []):
                lines.append(f"    - {r}")

        return "\n".join(lines) + "\n"


def run_daily_report(symbol: Optional[str] = None):
    """Convenience entry-point to generate and print a daily report."""
    reporter = SessionReporter()
    report = reporter.generate_daily_report(symbol=symbol)
    print(reporter._render_text_report(report))
    return report


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else None
    run_daily_report(symbol=sym)
