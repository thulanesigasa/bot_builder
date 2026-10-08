"""Session and Daily Report Generator (V1.6).

Generates structured research reports at two cadences:
  1. SESSION REPORT: produced at the end of each ForwardSession.
  2. DAILY REPORT: summarises all sessions from the most recent UTC calendar day.

Each report includes:
  - Session metadata (ID, symbol, mode, model, duration)
  - Tick collection health (total ticks, gap rate, duplicate rate)
  - Quote health (success rate, coverage)
  - Forward prediction summary (totals, pending, resolved, unverified)
  - Economic performance metrics (win rate, PnL, drawdown, Brier)
  - Validation gate status
  - Safety invariant declaration (live money disabled)

Reports are saved as JSON (machine-readable) and plain text (human-readable)
to the reports/ directory with timestamped filenames.

No trading or API interactions are performed by this module.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from forward_journal import ForwardPredictionJournal
from forward_session import ForwardSessionRegistry, ForwardSession
from forward_validation_gate import ForwardValidationGate
from health_monitor import GLOBAL_HEALTH_MONITOR
from model_manager import ModelManager
from performance_tracker import PerformanceTracker

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


class SessionReporter:
    """Generates end-of-session and daily research reports."""

    def __init__(
        self,
        reports_dir: Optional[str] = None,
        journal: Optional[ForwardPredictionJournal] = None,
        registry: Optional[ForwardSessionRegistry] = None,
        tracker: Optional[PerformanceTracker] = None,
        gate: Optional[ForwardValidationGate] = None
    ):
        self.reports_dir = reports_dir or REPORTS_DIR
        os.makedirs(self.reports_dir, exist_ok=True)
        self.journal = journal or ForwardPredictionJournal()
        self.registry = registry or ForwardSessionRegistry()
        self.tracker = tracker or PerformanceTracker()
        self.gate = gate or ForwardValidationGate()

    def _utc_now_str(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _safe_round(self, val, digits: int = 4):
        try:
            return round(float(val), digits) if val is not None else None
        except (TypeError, ValueError):
            return None

    def generate_session_report(
        self,
        session: ForwardSession,
        health_snapshot: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generates a complete session report dictionary."""
        # Accuracy metrics from journal
        accuracy = self.journal.get_accuracy_metrics(symbol=session.symbol)

        # Economic performance
        perf = self.tracker.compute_performance(
            symbol=session.symbol,
            mode=session.mode
        )

        # Health telemetry
        health = health_snapshot or GLOBAL_HEALTH_MONITOR.get_health_summary()

        # Model info
        mgr = ModelManager()
        model_path = mgr.get_latest_model_for_symbol(session.symbol)
        model_info = {}
        if model_path:
            try:
                from model_artifact import ModelArtifact
                art = ModelArtifact.load(model_path)
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
            },
            "safety": {
                "live_money_trading_disabled": True,
                "purchasing_allowed": False,
                "declaration": "All financial metrics are hypothetical paper-trading simulations only."
            },
            "model": model_info,
            "tick_health": health.get("ticks", {}),
            "quote_health": health.get("quotes", {}),
            "connectivity": health.get("connectivity", {}),
            "predictions": {
                "total": accuracy.get("total_predictions", 0),
                "resolved": accuracy.get("resolved_predictions", 0),
                "pending": accuracy.get("pending_predictions", 0),
                "unverified": accuracy.get("unverified_predictions", 0),
                "brier_score_runhigh": accuracy.get("brier_score_runhigh"),
                "brier_score_runlow": accuracy.get("brier_score_runlow"),
                "realized_runhigh_win_rate": accuracy.get("realized_runhigh_win_rate"),
                "realized_runlow_win_rate": accuracy.get("realized_runlow_win_rate"),
            },
            "economic_performance": perf.to_dict(),
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

        report = {
            "report_type": "DAILY",
            "period_utc": f"{now.strftime('%Y-%m-%d')} (last 24h)",
            "generated_at": self._utc_now_str(),
            "safety": {
                "live_money_trading_disabled": True,
                "purchasing_allowed": False,
                "declaration": "All financial metrics are hypothetical paper-trading simulations only."
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
            "aggregate_predictions": {
                "total": accuracy.get("total_predictions", 0),
                "resolved": accuracy.get("resolved_predictions", 0),
                "unverified": accuracy.get("unverified_predictions", 0),
                "brier_score_runhigh": accuracy.get("brier_score_runhigh"),
                "brier_score_runlow": accuracy.get("brier_score_runlow"),
                "realized_runhigh_win_rate": accuracy.get("realized_runhigh_win_rate"),
                "realized_runlow_win_rate": accuracy.get("realized_runlow_win_rate"),
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
        lines.append(f"Safety: Live money trading DISABLED. All metrics are hypothetical.")
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

        pred = report.get("predictions") or report.get("aggregate_predictions", {})
        lines.append("--- PREDICTIONS ---")
        lines.append(f"  Total          : {pred.get('total', 0)}")
        lines.append(f"  Resolved       : {pred.get('resolved', 0)}")
        lines.append(f"  Unverified     : {pred.get('unverified', 0)}")
        lines.append(f"  Brier RH       : {pred.get('brier_score_runhigh')}")
        lines.append(f"  Brier RL       : {pred.get('brier_score_runlow')}")
        lines.append(f"  RH Win Rate    : {pred.get('realized_runhigh_win_rate')}")
        lines.append(f"  RL Win Rate    : {pred.get('realized_runlow_win_rate')}")
        lines.append("")

        perf_key = "economic_performance" if "economic_performance" in report else "aggregate_economic_performance"
        perf = report.get(perf_key, {})
        lines.append("--- ECONOMIC PERFORMANCE (HYPOTHETICAL) ---")
        lines.append(f"  Paper Trade Signals : {perf.get('paper_trade_signals', 0)}")
        lines.append(f"  Resolved Trades     : {perf.get('resolved_trades', 0)}")
        lines.append(f"  Win Rate            : {perf.get('win_rate')}")
        lines.append(f"  Cumulative PnL      : {perf.get('cumulative_pnl')}")
        lines.append(f"  Mean PnL/Trade      : {perf.get('mean_pnl_per_trade')}")
        lines.append(f"  Sharpe Ratio        : {perf.get('sharpe_ratio')}")
        lines.append(f"  Max Drawdown        : {perf.get('max_drawdown')}")
        lines.append(f"  Quote Coverage      : {perf.get('quote_coverage_pct')}%")
        lines.append(f"  Predicted EV Mean   : {perf.get('predicted_ev_mean')}")
        lines.append(f"  Realized EV Mean    : {perf.get('realized_ev_mean')}")
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
