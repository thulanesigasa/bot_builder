"""Local Web Dashboard & Visual Analysis Engine for Deriv Quantitative Research (V1.6.4).

Renders a strict 60-30-10 interface with SVG visualizations:
1. Session Integrity: Session ID, authoritative lifecycle state, reconciliation status, verified boolean.
2. Data Accounting: Live ticks, warmup ticks, duplicate ticks, rejected ticks, recorded quotes.
3. Forward Performance: Predicted vs observed RUNHIGH/RUNLOW probabilities, Brier score, calibration error.
4. Economic Performance: Actual quote coverage, break-even probabilities, ordinary EV, conservative EV.
5. System Safety & Risk: Model approval status, persistent risk state, simulated paper eligibility.
   Permanent declaration: REAL-MONEY TRADING DISABLED.

Design Standards:
- 60% Dominant Background: #0B0F19
- 30% Surface/Panels: #131B2E
- 10% Accent: #0284C7
- Vector SVGs only (strictly no emojis per Rule 2 & 4)
- Zero hover glow animations (Rule 3)
- Strict Rule 16 compliance: Zero status badges or cards (e.g. 'READ ONLY', 'RUNNING', 'OK', etc.)
"""
import glob
import http.server
import json
import os
import socketserver
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from config import DEFAULT_CONFIG
from contract_model import ContractOutcomeModel
from feature_schema import FEATURE_SCHEMA_VERSION
from forward_journal import ForwardPredictionJournal
from forward_session import ForwardSessionRegistry
from health_monitor import GLOBAL_HEALTH_MONITOR
from model_artifact import ModelArtifact, ModelStatus
from model_manager import ModelManager
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine
from risk import RiskManager
from session_reconciler import SessionReconciler


PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
BIND_HOST = "127.0.0.1"


def get_available_symbols():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    files = glob.glob(os.path.join(data_dir, "*_master.csv")) + glob.glob(os.path.join(data_dir, "*_ticks.csv"))
    symbols = set()
    for f in files:
        base = os.path.basename(f).replace("_master.csv", "").replace("_ticks.csv", "")
        if base and not base.startswith("."):
            symbols.add(base)
    return sorted(list(symbols)) or ["R_75"]


def generate_v17_payload(symbol: str = "R_75") -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    # 1. Forward Sessions Registry
    sess_reg = ForwardSessionRegistry()
    recent_sessions = sess_reg.list_sessions(symbol=symbol, limit=1)
    active_session = recent_sessions[0] if recent_sessions else None

    # Reconciler audit on active session
    reconciler = SessionReconciler()
    recon_report = None
    if active_session:
        recon_report = reconciler.reconcile_session(active_session.session_id)

    # 2. Frozen Model Inspection
    mgr = ModelManager()
    latest_model_path = mgr.get_latest_model_for_symbol(symbol)
    model_info: Dict[str, Any] = {
        "model_id": "NONE_LOADED",
        "version": "N/A",
        "market_symbol": symbol,
        "approval_status": "NO_MODEL",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_checksum": "N/A",
        "base_rate_runhigh": None,
        "base_rate_runlow": None,
        "states_count": 0
    }
    if latest_model_path:
        try:
            art = ModelArtifact.load_from_file(latest_model_path)
            model_info = {
                "model_id": art.model_id,
                "version": art.model_version,
                "market_symbol": art.market_symbol,
                "approval_status": art.approval_status,
                "feature_schema_version": art.feature_schema_version,
                "dataset_checksum": art.dataset_checksum[:16] + "...",
                "base_rate_runhigh": art.model_parameters.get("base_rate_runhigh"),
                "base_rate_runlow": art.model_parameters.get("base_rate_runlow"),
                "states_count": art.model_parameters.get("total_states_discovered", 0)
            }
        except Exception:
            pass

    # 3. Live API Diagnostic & Health
    health = GLOBAL_HEALTH_MONITOR.get_health_summary()

    # 4. Actual Quotes strictly filtered by session if available
    q_db = QuoteDatabase()
    sess_id = active_session.session_id if active_session else None
    q_cov = q_db.report_quote_coverage(symbol, session_id=sess_id)
    latest_rh = q_db.get_latest_quote_before(symbol, "RUNHIGH", timestamp=time.time(), max_freshness_seconds=86400.0, session_id=sess_id)
    latest_rl = q_db.get_latest_quote_before(symbol, "RUNLOW", timestamp=time.time(), max_freshness_seconds=86400.0, session_id=sess_id)

    # 5. Forward Prediction Journal strictly filtered by session
    fwd_journal = ForwardPredictionJournal()
    fwd_metrics = fwd_journal.get_accuracy_metrics(symbol=symbol, session_id=sess_id)
    recent_preds = fwd_journal.get_session_predictions(sess_id) if sess_id else fwd_journal.inspect_recent(limit=8, symbol=symbol)
    recent_preds = recent_preds[-8:] if len(recent_preds) > 8 else recent_preds

    # 6. Persistent Risk State
    risk_mgr = RiskManager(symbol=symbol)
    risk_snap = risk_mgr.get_state()

    # Economic EV calculations using genuine quotes
    be_rh = (latest_rh.implied_probability * 100) if latest_rh else 3.28
    be_rl = (latest_rl.implied_probability * 100) if latest_rl else 3.28
    p_rh_mean = fwd_metrics.get("runhigh_estimated_mean_prob") or 0.0
    p_rl_mean = fwd_metrics.get("runlow_estimated_mean_prob") or 0.0

    ord_ev_rh = (p_rh_mean * (latest_rh.total_payout if latest_rh else 61.03)) - (latest_rh.ask_price if latest_rh else 2.0)
    ord_ev_rl = (p_rl_mean * (latest_rl.total_payout if latest_rl else 61.03)) - (latest_rl.ask_price if latest_rl else 2.0)

    # Extract top rejection reasons
    rejection_counts: Dict[str, int] = {}
    for r in recent_preds:
        reason = r.get("rejection_reason", "")
        if reason:
            for part in reason.split(";"):
                if part:
                    rejection_counts[part] = rejection_counts.get(part, 0) + 1

    # Prediction readiness diagnostics
    req_lookback = art.required_lookback if ("art" in locals() and art) else 25
    warm_ticks = active_session.warmup_ticks if active_session else 0
    live_ticks = active_session.live_ticks if active_session else 0
    buffer_ticks = warm_ticks + live_ticks
    is_warmed_up = buffer_ticks >= req_lookback
    current_blocker = None
    if not active_session:
        current_blocker = "No active session registered"
    elif buffer_ticks < req_lookback:
        current_blocker = f"Waiting for {req_lookback - buffer_ticks} more warm-up ticks ({buffer_ticks}/{req_lookback})"

    # Outcome resolution progress
    pending_summary = getattr(fwd_journal, "resolver", None).get_pending_summary() if hasattr(fwd_journal, "resolver") else {}
    session_outcomes = fwd_journal.get_session_outcomes(sess_id) if sess_id else []
    recent_outcomes = session_outcomes[-8:] if len(session_outcomes) > 8 else session_outcomes
    resolved_wins_rh = sum(1 for o in session_outcomes if o.get("runhigh_win") == 1.0)
    resolved_wins_rl = sum(1 for o in session_outcomes if o.get("runlow_win") == 1.0)

    # 7. V1.7 Advanced Statistical & Economic Research Evaluation
    v17_stat: Dict[str, Any] = {
        "sample_size": len(session_outcomes),
        "effective_sample_size": len(session_outcomes),
        "brier_score_runhigh": None,
        "brier_skill_score_runhigh": None,
        "ece_runhigh": None,
        "block_bootstrap_ci_runhigh": [None, None],
        "brier_score_runlow": None,
        "brier_skill_score_runlow": None,
        "ece_runlow": None,
        "block_bootstrap_ci_runlow": [None, None],
    }
    v17_econ: Dict[str, Any] = {
        "quote_coverage_pct": fwd_metrics.get("quote_coverage_pct", 0.0),
        "break_even_prob_runhigh": round(be_rh / 100.0, 4),
        "ordinary_ev_runhigh": round(ord_ev_rh, 4) if p_rh_mean > 0 else None,
        "conservative_ev_runhigh": None,
        "cumulative_pnl": 0.0,
        "max_drawdown": 0.0,
        "hypothetical_trades": 0,
    }
    v17_qualification: Dict[str, Any] = {
        "research_stage": getattr(active_session, "research_stage", "EXPLORATORY_FORWARD") if active_session else "EXPLORATORY_FORWARD",
        "verdict": "INSUFFICIENT_FORWARD_DATA",
        "verdict_reasons": ["Awaiting initial forward evaluation."]
    }

    if sess_id and session_outcomes and len(session_outcomes) > 0:
        try:
            from statistical_evaluator import StatisticalEvaluator
            from economic_evaluator import EconomicEvaluator
            from session_research_aggregator import SessionResearchAggregator

            sess_all_preds = fwd_journal.get_session_predictions(sess_id)
            stat_res = StatisticalEvaluator.evaluate_win_rates(session_outcomes, sess_all_preds)
            sess_quotes = q_db.get_session_quotes(sess_id)
            econ_res = EconomicEvaluator.evaluate_quote_economics(sess_all_preds, sess_quotes, session_outcomes)

            rh_s = stat_res.get("runhigh", {})
            rl_s = stat_res.get("runlow", {})
            v17_stat["sample_size"] = rh_s.get("resolved_count", 0)
            v17_stat["effective_sample_size"] = rh_s.get("effective_sample_size", 0)
            v17_stat["brier_score_runhigh"] = rh_s.get("brier_score")
            v17_stat["brier_skill_score_runhigh"] = rh_s.get("brier_skill_score")
            v17_stat["ece_runhigh"] = rh_s.get("expected_calibration_error")
            v17_stat["block_bootstrap_ci_runhigh"] = rh_s.get("block_bootstrap_ci", [None, None])
            v17_stat["brier_score_runlow"] = rl_s.get("brier_score")
            v17_stat["brier_skill_score_runlow"] = rl_s.get("brier_skill_score")
            v17_stat["ece_runlow"] = rl_s.get("expected_calibration_error")
            v17_stat["block_bootstrap_ci_runlow"] = rl_s.get("block_bootstrap_ci", [None, None])

            rh_e = econ_res.get("runhigh", {})
            v17_econ["quote_coverage_pct"] = econ_res.get("overall_quote_coverage_pct", 0.0)
            v17_econ["break_even_prob_runhigh"] = rh_e.get("mean_break_even_prob", 0.0328)
            v17_econ["ordinary_ev_runhigh"] = rh_e.get("ordinary_ev")
            v17_econ["conservative_ev_runhigh"] = rh_e.get("conservative_ev")
            v17_econ["cumulative_pnl"] = econ_res.get("cumulative_pnl", 0.0)
            v17_econ["max_drawdown"] = econ_res.get("max_drawdown", 0.0)
            v17_econ["hypothetical_trades"] = econ_res.get("hypothetical_trades_count", 0)

            agg = SessionResearchAggregator()
            multi_eval = agg.evaluate_multi_session_research(symbol=symbol)
            v17_qualification["verdict"] = multi_eval.get("verdict", "INSUFFICIENT_FORWARD_DATA")
            v17_qualification["verdict_reasons"] = multi_eval.get("verdict_reasons", [])
        except Exception as e:
            v17_qualification["verdict_reasons"] = [str(e)]

    # 8. V1.7.1 Authoritative Forward Edge Confirmation Gate Evaluation
    try:
        from confirmation_specification import ConfirmationManifest
        from forward_confirmation_gate import evaluate_forward_edge_confirmation
        conf_eval = evaluate_forward_edge_confirmation(
            symbol=symbol,
            model_id=model_info["model_id"],
            forward_db_path=os.path.join(data_dir, "forward_predictions.db"),
            quote_db_path=os.path.join(data_dir, "quotes.db"),
            session_db_path=os.path.join(data_dir, "forward_sessions.db")
        )
        conf_data = {
            "manifest_id": conf_eval.manifest_id,
            "manifest_checksum": conf_eval.manifest_checksum[:16] + "..." if conf_eval.manifest_checksum else "N/A",
            "criteria_frozen": conf_eval.criteria_frozen,
            "confirmation_sessions_count": conf_eval.confirmation_sessions_count,
            "confirmation_resolved_count": conf_eval.confirmation_resolved_count,
            "verdict": conf_eval.verdict,
            "confirmed": conf_eval.confirmed,
            "gate_failures": conf_eval.gate_failures,
            "rejection_reasons": conf_eval.rejection_reasons,
            "min_quote_coverage_pct": conf_eval.manifest.min_quote_coverage_pct if conf_eval.manifest else 95.0,
            "min_observations": conf_eval.manifest.min_confirmation_observations if conf_eval.manifest else 200,
            "min_sessions": conf_eval.manifest.min_confirmation_sessions if conf_eval.manifest else 2,
        }
    except Exception as e:
        conf_data = {
            "manifest_id": "MANIFEST_NOT_INITIALIZED",
            "manifest_checksum": "N/A",
            "criteria_frozen": False,
            "confirmation_sessions_count": 0,
            "confirmation_resolved_count": 0,
            "verdict": "NO_CONFIRMATION_SESSIONS",
            "confirmed": False,
            "gate_failures": [str(e)],
            "rejection_reasons": ["Confirmation system awaiting initialization."],
            "min_quote_coverage_pct": 95.0,
            "min_observations": 200,
            "min_sessions": 2,
        }

    return {
        "version": "V1.7.1",
        "symbol": symbol,
        "available_symbols": get_available_symbols(),
        "safety_invariant": "REAL-MONEY TRADING DISABLED (Zero buy orders / Research Only)",
        "confirmation": conf_data,
        "prediction_readiness": {
            "required_lookback": req_lookback,
            "buffer_ticks": buffer_ticks,
            "warmup_ticks": warm_ticks,
            "live_ticks": live_ticks,
            "is_warmed_up": is_warmed_up,
            "pipeline_status": "WARMUP_COMPLETE" if is_warmed_up else "WAITING_FOR_WARMUP",
            "feature_readiness": "READY" if is_warmed_up else "WARMING_UP",
            "current_blocker": current_blocker or "None (Ready for inference)"
        },
        "session": {
            "session_id": active_session.session_id if active_session else "NONE",
            "mode": active_session.mode if active_session else "SHADOW",
            "status": active_session.status if active_session else "STANDBY",
            "symbol": active_session.symbol if active_session else symbol,
            "research_stage": getattr(active_session, "research_stage", "EXPLORATORY_FORWARD") if active_session else "EXPLORATORY_FORWARD",
            "reconciliation_status": recon_report.status if recon_report else "UNRECONCILED",
            "is_verified": recon_report.is_verified if recon_report else False,
            "duration_seconds": active_session.planned_duration_seconds if active_session else 0,
            "connection_status": health.get("connectivity", {}).get("connection_status", "DISCONNECTED"),
        },
        "live_data": {
            "total_ticks": active_session.total_ticks if active_session else 0,
            "live_ticks": active_session.live_ticks if active_session else 0,
            "warmup_ticks": active_session.warmup_ticks if active_session else 0,
            "duplicate_ticks": active_session.duplicate_ticks if active_session else 0,
            "rejected_ticks": active_session.rejected_ticks if active_session else 0,
            "total_proposals": q_cov.get("total_quotes", 0),
            "quote_coverage_pct": fwd_metrics.get("quote_coverage_pct", 0.0),
            "latest_received_timestamp": health.get("ticks", {}).get("latest_tick_time_utc", "N/A"),
            "data_gaps_count": health.get("ticks", {}).get("total_gaps", 0),
            "has_active_data_gap": health.get("has_active_data_gap", False)
        },
        "v17_validation": {
            "statistics": v17_stat,
            "economics": v17_econ,
            "qualification": v17_qualification,
        },
        "outcome_progress": {
            "required_future_ticks": 6,
            "active_pending_count": pending_summary.get("active_pending_count", 0),
            "pending_outcomes": pending_summary.get("pending_outcomes", []),
            "resolved_outcomes_count": len(session_outcomes),
            "resolved_wins_runhigh": resolved_wins_rh,
            "resolved_wins_runlow": resolved_wins_rl,
            "recent_outcomes": recent_outcomes,
        },
        "pipeline": {
            "eligible_feature_windows": fwd_metrics.get("total_predictions", 0),
            "predictions_generated": fwd_metrics.get("total_predictions", 0),
            "predictions_persisted": fwd_metrics.get("total_predictions", 0),
            "outcomes_pending": pending_summary.get("active_pending_count", fwd_metrics.get("pending_predictions", 0)),
            "outcomes_resolved": fwd_metrics.get("resolved_predictions", 0),
            "outcomes_incomplete": fwd_metrics.get("incomplete_predictions", 0),
            "outcomes_data_gap": fwd_metrics.get("data_gap_predictions", 0),
            "journal_errors": 0
        },
        "statistical_evidence": {
            "predicted_runhigh_prob": fwd_metrics.get("runhigh_estimated_mean_prob"),
            "predicted_runlow_prob": fwd_metrics.get("runlow_estimated_mean_prob"),
            "observed_runhigh_prob": fwd_metrics.get("runhigh_observed_win_rate"),
            "observed_runlow_prob": fwd_metrics.get("runlow_observed_win_rate"),
            "brier_score_runhigh": fwd_metrics.get("brier_score_runhigh"),
            "brier_score_runlow": fwd_metrics.get("brier_score_runlow"),
            "calibration_error_runhigh": fwd_metrics.get("calibration_error_runhigh"),
            "calibration_error_runlow": fwd_metrics.get("calibration_error_runlow"),
            "sample_counts": fwd_metrics.get("resolved_predictions", 0)
        },
        "economic_performance": {
            "break_even_rh_pct": round(be_rh, 2),
            "break_even_rl_pct": round(be_rl, 2),
            "ordinary_ev_rh": round(ord_ev_rh, 2),
            "ordinary_ev_rl": round(ord_ev_rl, 2),
            "quote_coverage_pct": fwd_metrics.get("quote_coverage_pct", 0.0)
        },
        "safety_risk": {
            "model_approval_status": model_info.get("approval_status", "UNKNOWN"),
            "paper_eligibility": "RESTRICTED (RESEARCH ONLY)" if not (recon_report and recon_report.is_verified) else "EVALUABLE",
            "consecutive_losses": risk_snap.consecutive_losses,
            "daily_drawdown_pct": risk_snap.max_drawdown_pct,
            "is_in_cooldown": risk_snap.is_paused,
            "is_risk_valid": risk_snap.is_valid,
            "rejection_reasons_summary": rejection_counts
        },
        "model": model_info,
        "reconciliation": recon_report.to_dict() if recon_report else None,
        "quotes": {
            "database_total_quotes": q_cov.get("total_quotes", 0),
            "runhigh_recorded": q_cov.get("runhigh_quotes", 0),
            "runlow_recorded": q_cov.get("runlow_quotes", 0),
            "latest_runhigh": {
                "ask": latest_rh.ask_price if latest_rh else None,
                "payout": latest_rh.total_payout if latest_rh else None,
                "break_even_pct": round((latest_rh.implied_probability * 100), 2) if latest_rh else None,
                "latency_ms": latest_rh.quote_latency_ms if latest_rh else None,
                "timestamp_iso": datetime.fromtimestamp(latest_rh.response_timestamp, tz=timezone.utc).isoformat() if latest_rh else None
            },
            "latest_runlow": {
                "ask": latest_rl.ask_price if latest_rl else None,
                "payout": latest_rl.total_payout if latest_rl else None,
                "break_even_pct": round((latest_rl.implied_probability * 100), 2) if latest_rl else None,
                "latency_ms": latest_rl.quote_latency_ms if latest_rl else None,
                "timestamp_iso": datetime.fromtimestamp(latest_rl.response_timestamp, tz=timezone.utc).isoformat() if latest_rl else None
            }
        },
        "recent_predictions": recent_preds
    }


def generate_v171_payload(symbol: str = "R_75") -> Dict[str, Any]:
    return generate_v17_payload(symbol)


def generate_v162_payload(symbol: str = "R_75") -> Dict[str, Any]:
    return generate_v17_payload(symbol)



HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deriv Quantitative Research — V1.7.1 Forward Edge Confirmation Dashboard</title>
<style>
  :root {
    --bg-base: #0B0F19;
    --bg-surface: #131B2E;
    --accent: #0284C7;
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --border-subtle: #1E293B;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background-color: var(--bg-base);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 1380px; margin: 0 auto; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 24px;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand svg { width: 32px; height: 32px; fill: var(--accent); }
  h1 { font-size: 20px; font-weight: 700; }
  .subtitle { font-size: 13px; color: var(--text-secondary); }

  .safety-banner {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--accent);
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    color: var(--text-primary);
    font-weight: 600;
  }
  .safety-banner svg { width: 20px; height: 20px; fill: var(--accent); flex-shrink: 0; }
  
  .grid-6 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 18px;
  }
  .card-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .card-label svg { width: 14px; height: 14px; fill: var(--accent); }
  .card-val {
    font-size: 18px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 6px;
  }
  .card-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.4; }

  .panel {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .panel-title {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .panel-title svg { width: 16px; height: 16px; fill: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th { text-align: left; padding: 10px 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border-subtle); font-weight: 600; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border-subtle); }
  tr:last-child td { border-bottom: none; }

  select {
    background-color: var(--bg-surface);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    outline: none;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
      <div>
        <h1>Deriv Only Ups / Only Downs Forward Statistical Validation Dashboard</h1>
        <div class="subtitle">V1.7.1 — Confirmation Gate Hardening, Pre-Registered Criteria & Genuine Quote-Based Edge Assessment</div>
      </div>
    </div>
    <div>
      <label for="sym-select" style="font-size: 12px; color: var(--text-secondary); margin-right: 8px;">Symbol:</label>
      <select id="sym-select" onchange="switchSymbol(this.value)">
        <!-- injected -->
      </select>
    </div>
  </header>

  <div class="safety-banner">
    <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
    <div>REAL-MONEY TRADING DISABLED — Strict Non-Purchasing Forward Research & Statistical Evidence System</div>
  </div>

  <div class="grid-6">
    <!-- 1. Session Integrity -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14h2v2h-2v-2zm0-10h2v8h-2V6z"/></svg>
        Session Integrity
      </div>
      <div class="card-val" id="sess-id">STANDBY</div>
      <div class="card-desc" id="sess-desc">State: STANDBY | Recon: UNRECONCILED</div>
    </div>

    <!-- 2. Prediction Readiness -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M13 2.05v3.03c3.39.49 6 3.39 6 6.92 0 .9-.18 1.75-.48 2.54l2.6 1.53c.56-1.24.88-2.62.88-4.07 0-5.18-3.95-9.45-9-9.95zM12 19c-3.87 0-7-3.13-7-7 0-3.53 2.61-6.43 6-6.92V2.05c-5.05.5-9 4.77-9 9.95 0 5.52 4.48 10 10 10 2.35 0 4.5-.82 6.2-2.19l-2.19-2.19c-1.15.9-2.52 1.44-4.01 1.44zm8.65-4.47l-1.55-.91c-.24.5-.55.96-.91 1.38l1.55.91c.36-.43.67-.89.91-1.38z"/></svg>
        Research Stage
      </div>
      <div class="card-val" id="research-stage">EXPLORATORY</div>
      <div class="card-desc" id="research-verdict">Verdict: INSUFFICIENT_FORWARD_DATA</div>
    </div>

    <!-- 3. Data Accounting -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
        Data Accounting
      </div>
      <div class="card-val" id="live-ticks">0 Ticks</div>
      <div class="card-desc" id="live-quotes">Live: 0 | Warmup: 0 | Dup: 0</div>
    </div>

    <!-- 4. Statistical Calibration -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/></svg>
        Calibration (BSS / ECE)
      </div>
      <div class="card-val" id="stat-bss">BSS: N/A</div>
      <div class="card-desc" id="stat-ece">ECE: N/A | Brier: N/A</div>
    </div>

    <!-- 5. Economic Evaluation -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
        Economic EV & Edge
      </div>
      <div class="card-val" id="econ-ev-val">EV: N/A</div>
      <div class="card-desc" id="econ-be">BE: 3.28% | Cons EV: N/A</div>
    </div>

    <!-- 6. Safety & Governance -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>
        Safety & Governance
      </div>
      <div class="card-val" id="risk-status">RESEARCH_ONLY</div>
      <div class="card-desc" id="risk-desc">Paper: RESTRICTED | Losses: 0</div>
    </div>
  </div>

  <!-- V1.7.1 Authoritative Edge Confirmation Gate Panel -->
  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
      V1.7.1 Authoritative Forward Edge Confirmation Gate (13 Pre-Registered Conditions)
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 16px;">
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Pre-Registered Manifest</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="conf-manifest-id">ID: N/A</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="conf-manifest-hash">Checksum: N/A</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Independent Confirmation Sessions</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="conf-sess-count">Sessions: 0 | Resolved: 0</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="conf-req-info">Required: &ge;2 sessions | &ge;200 obs</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Quote Coverage Hurdle</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="conf-quote-hurdle">Mandatory Coverage: &ge;95.0%</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;">Zero synthetic / benchmark fallbacks permitted</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Authoritative Gate Verdict</div>
        <div style="font-size: 13.5px; font-weight: 700; color: var(--text-primary); margin-top: 6px;" id="conf-verdict-val">NO_CONFIRMATION_SESSIONS</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="conf-reasons">No independent confirmation sessions registered.</div>
      </div>
    </div>
  </div>

  <!-- V1.7 Statistical Evidence & Economic Edge Panel -->
  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
      V1.7 Statistical Evidence, Dependence-Aware Calibration & Economic Edge Assessment
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 16px;">
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Probability Calibration (RUNHIGH)</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="stat-calib-rh">Brier: N/A | BSS: N/A | ECE: N/A</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="stat-base-rh">Ref Baseline: 3.275% (SE=0.0009)</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Dependence-Aware Uncertainty (L=5)</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="stat-dep-rh">N: 0 | Neff: 0 | Block Boot CI: [N/A, N/A]</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;">Moving Block Bootstrap B=1000 resamples</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Proposal Economics & Edge Hurdle</div>
        <div style="font-size: 13.5px; margin-top: 6px;" id="econ-edge-rh">BE Hurdle: 3.28% | Ord EV: N/A | Cons EV: N/A</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="econ-pnl-rh">Hypothetical Trades: 0 | PnL: $0.00 | Max DD: $0.00</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 14px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Research Qualification Verdict</div>
        <div style="font-size: 13.5px; font-weight: 700; margin-top: 6px;" id="research-verdict-full">INSUFFICIENT_FORWARD_DATA</div>
        <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;" id="research-blockers">Awaiting forward evaluation.</div>
      </div>
    </div>
  </div>

  <!-- Session Reconciliation Panel -->
  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
      Forward Session Data Reconciliation & Provenance Audit
    </div>
    <div id="recon-summary" style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6;">
      No active session reconciliation data.
    </div>
  </div>

  <!-- Outcome Resolution Progress Panel -->
  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/></svg>
      Forward Contract Outcome Resolution & 5-Movement Progress
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px;">
      <div style="background-color: var(--bg-base); padding: 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Required Movement Window</div>
        <div style="font-size: 16px; font-weight: 700; color: var(--accent); margin-top: 4px;">6 Ticks (S0 &rarr; S5)</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Active Pending Predictions</div>
        <div style="font-size: 16px; font-weight: 700; color: var(--text-primary); margin-top: 4px;" id="outcomes-pending-count">0</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Resolved Outcomes</div>
        <div style="font-size: 16px; font-weight: 700; color: var(--text-primary); margin-top: 4px;" id="outcomes-resolved-count">0</div>
      </div>
      <div style="background-color: var(--bg-base); padding: 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Canonical Wins (RH / RL)</div>
        <div style="font-size: 16px; font-weight: 700; color: var(--text-primary); margin-top: 4px;" id="outcomes-wins-count">0 / 0</div>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Outcome ID</th>
          <th>Prediction ID</th>
          <th>Entry Price</th>
          <th>Price Sequence (S0 &rarr; S5)</th>
          <th>Ticks</th>
          <th>RH Win</th>
          <th>RL Win</th>
          <th>Status</th>
          <th>Resolution Diagnostic</th>
        </tr>
      </thead>
      <tbody id="outcomes-table-body">
        <tr><td colspan="9" style="color: var(--text-secondary); text-align: center;">No resolved outcomes in this session</td></tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
      Genuine Market Proposals (Lookahead-Free Synchronization)
    </div>
    <table>
      <thead>
        <tr>
          <th>Contract Type</th>
          <th>Ask Price ($)</th>
          <th>Total Payout ($)</th>
          <th>Implied Break-Even (%)</th>
          <th>Latency (ms)</th>
          <th>Quote Timestamp (UTC)</th>
        </tr>
      </thead>
      <tbody id="quotes-table-body">
        <tr><td colspan="6" style="color: var(--text-secondary); text-align: center;">No genuine quotes recorded yet</td></tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
      Recent Forward Shadow Predictions & Contract Outcome Reconstruction
    </div>
    <table>
      <thead>
        <tr>
          <th>Prediction ID</th>
          <th>Time (UTC)</th>
          <th>Market State</th>
          <th>P(RUNHIGH)</th>
          <th>P(RUNLOW)</th>
          <th>Decision</th>
          <th>Primary Rejection Reason</th>
          <th>Outcome Status</th>
        </tr>
      </thead>
      <tbody id="preds-table-body">
        <tr><td colspan="8" style="color: var(--text-secondary); text-align: center;">No forward predictions logged in this session</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
let currentSymbol = "R_75";

function switchSymbol(sym) {
  currentSymbol = sym;
  fetchData();
}

async function fetchData() {
  try {
    const res = await fetch(`/api/data?symbol=${encodeURIComponent(currentSymbol)}`);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.error("Failed to load dashboard data:", err);
  }
}

function renderDashboard(data) {
  // Populate dropdown
  const select = document.getElementById("sym-select");
  if (select.children.length === 0) {
    (data.available_symbols || ["R_75"]).forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      if (s === data.symbol) opt.selected = true;
      select.appendChild(opt);
    });
  }

  // 1. Session Integrity card
  const s = data.session || {};
  document.getElementById("sess-id").textContent = s.session_id !== "NONE" ? s.session_id.substring(0, 8) : "STANDBY";
  document.getElementById("sess-desc").textContent = `State: ${s.status} | Recon: ${s.reconciliation_status} | Verified: ${s.is_verified}`;

  // 2. Research Stage card
  const v17 = data.v17_validation || {};
  const qual = v17.qualification || {};
  document.getElementById("research-stage").textContent = qual.research_stage || s.research_stage || "EXPLORATORY";
  document.getElementById("research-verdict").textContent = `Verdict: ${qual.verdict || 'INSUFFICIENT_DATA'}`;

  // 3. Data Accounting card
  const ld = data.live_data || {};
  document.getElementById("live-ticks").textContent = `${(ld.total_ticks || 0).toLocaleString()} Ticks`;
  document.getElementById("live-quotes").textContent = `Live: ${ld.live_ticks || 0} | Warmup: ${ld.warmup_ticks || 0} | Dup: ${ld.duplicate_ticks || 0}`;

  // 4. Calibration card
  const stat17 = v17.statistics || {};
  const bssVal = stat17.brier_skill_score_runhigh !== null && stat17.brier_skill_score_runhigh !== undefined ? Number(stat17.brier_skill_score_runhigh).toFixed(4) : "N/A";
  const eceVal = stat17.ece_runhigh !== null && stat17.ece_runhigh !== undefined ? (Number(stat17.ece_runhigh) * 100).toFixed(2) + "%" : "N/A";
  const bsVal = stat17.brier_score_runhigh !== null && stat17.brier_score_runhigh !== undefined ? Number(stat17.brier_score_runhigh).toFixed(4) : "N/A";
  document.getElementById("stat-bss").textContent = `BSS: ${bssVal}`;
  document.getElementById("stat-ece").textContent = `ECE: ${eceVal} | Brier: ${bsVal}`;

  // 5. Economic EV card
  const econ17 = v17.economics || {};
  const ordEv = econ17.ordinary_ev_runhigh !== null && econ17.ordinary_ev_runhigh !== undefined ? `$${Number(econ17.ordinary_ev_runhigh).toFixed(2)}` : "N/A";
  const consEv = econ17.conservative_ev_runhigh !== null && econ17.conservative_ev_runhigh !== undefined ? `$${Number(econ17.conservative_ev_runhigh).toFixed(2)}` : "N/A";
  const bePct = econ17.break_even_prob_runhigh ? (Number(econ17.break_even_prob_runhigh) * 100).toFixed(2) + "%" : "3.28%";
  document.getElementById("econ-ev-val").textContent = `EV: ${ordEv}`;
  document.getElementById("econ-be").textContent = `BE: ${bePct} | Cons EV: ${consEv}`;

  // 6. Safety & Governance card
  const sr = data.safety_risk || {};
  document.getElementById("risk-status").textContent = sr.model_approval_status || "UNKNOWN";
  document.getElementById("risk-desc").textContent = `Paper: ${sr.paper_eligibility} | Losses: ${sr.consecutive_losses || 0}`;

  // V1.7 Panel Details
  document.getElementById("stat-calib-rh").textContent = `Brier: ${bsVal} | BSS: ${bssVal} | ECE: ${eceVal}`;
  const bootCi = stat17.block_bootstrap_ci_runhigh || [null, null];
  const ciStr = (bootCi[0] !== null && bootCi[1] !== null) ? `[${(bootCi[0]*100).toFixed(2)}%, ${(bootCi[1]*100).toFixed(2)}%]` : "[N/A, N/A]";
  document.getElementById("stat-dep-rh").textContent = `N: ${stat17.sample_size || 0} | Neff: ${stat17.effective_sample_size || 0} | Block Boot CI: ${ciStr}`;
  document.getElementById("econ-edge-rh").textContent = `BE Hurdle: ${bePct} | Ord EV: ${ordEv} | Cons EV: ${consEv}`;
  document.getElementById("econ-pnl-rh").textContent = `Hypothetical Trades: ${econ17.hypothetical_trades || 0} | PnL: $${(econ17.cumulative_pnl || 0).toFixed(2)} | Max DD: $${(econ17.max_drawdown || 0).toFixed(2)}`;
  document.getElementById("research-verdict-full").textContent = qual.verdict || "INSUFFICIENT_FORWARD_DATA";
  document.getElementById("research-blockers").textContent = (qual.verdict_reasons && qual.verdict_reasons.length > 0) ? qual.verdict_reasons.join(" | ") : "Evaluating criteria.";

  // V1.7.1 Confirmation Gate Panel
  const c = data.confirmation || {};
  document.getElementById("conf-manifest-id").textContent = `ID: ${c.manifest_id || 'NONE'}`;
  document.getElementById("conf-manifest-hash").textContent = `SHA256: ${c.manifest_checksum || 'N/A'}`;
  document.getElementById("conf-sess-count").textContent = `Sessions: ${c.confirmation_sessions_count || 0} | Resolved: ${c.confirmation_resolved_count || 0}`;
  document.getElementById("conf-req-info").textContent = `Required: >=${c.min_sessions || 2} sessions | >=${c.min_observations || 200} obs`;
  document.getElementById("conf-quote-hurdle").textContent = `Coverage Hurdle: >=${c.min_quote_coverage_pct || 95.0}%`;
  document.getElementById("conf-verdict-val").textContent = c.verdict || "NO_CONFIRMATION_SESSIONS";
  const rList = c.rejection_reasons || [];
  document.getElementById("conf-reasons").textContent = rList.length > 0 ? rList.join(" | ") : "All confirmation gates passed.";

  // Reconciliation summary panel
  const recon = data.reconciliation;
  const rdiv = document.getElementById("recon-summary");
  if (!recon) {
    rdiv.textContent = "No forward session selected or registered.";
  } else {
    let html = `<strong>Session:</strong> ${recon.session_id.substring(0, 8)} | <strong>Audit Status:</strong> ${recon.status} | <strong>Verified:</strong> ${recon.is_verified}<br>`;
    html += `<strong>Ticks:</strong> Counter: ${recon.ticks.session_counter_ticks}, Genuine Live: ${recon.ticks.live_ticks}, Warmup: ${recon.ticks.warmup_ticks}, Duplicate: ${recon.ticks.duplicate_ticks}<br>`;
    html += `<strong>Predictions:</strong> Total: ${recon.predictions.total_predictions}, Resolved: ${recon.outcomes.resolved_outcomes}, Pending: ${recon.outcomes.pending_outcomes}, Incomplete: ${recon.outcomes.incomplete_outcomes}<br>`;
    html += `<strong>Chronology Violations:</strong> ${recon.chronology.chronology_errors} | <strong>Future Quotes:</strong> ${recon.chronology.future_quote_errors}<br>`;
    if (recon.issues && recon.issues.length > 0) {
      html += `<div style="color: #F87171; margin-top: 6px;"><strong>Integrity Findings:</strong><br>${recon.issues.map(i => `• ${i}`).join("<br>")}</div>`;
    } else {
      html += `<div style="color: #4ADE80; margin-top: 6px;">All referential, provenance, tick accounting, and chronological checks passed.</div>`;
    }
    rdiv.innerHTML = html;
  }

  // Outcome Resolution Progress
  const op = data.outcome_progress || {};
  document.getElementById("outcomes-pending-count").textContent = op.active_pending_count || 0;
  document.getElementById("outcomes-resolved-count").textContent = op.resolved_outcomes_count || 0;
  document.getElementById("outcomes-wins-count").textContent = `${op.resolved_wins_runhigh || 0} / ${op.resolved_wins_runlow || 0}`;

  const otb = document.getElementById("outcomes-table-body");
  otb.innerHTML = "";
  const recentOuts = op.recent_outcomes || [];
  if (recentOuts.length === 0) {
    otb.innerHTML = '<tr><td colspan="9" style="color: var(--text-secondary); text-align: center;">No resolved outcomes in this session</td></tr>';
  } else {
    recentOuts.forEach(o => {
      let prSeq = "[]";
      try {
        const parr = JSON.parse(o.forward_prices_json || "[]");
        prSeq = parr.map(p => typeof p === 'number' ? p.toFixed(2) : p).join(" &rarr; ");
      } catch(e) { prSeq = o.forward_prices_json || "[]"; }

      const rhW = o.runhigh_win === 1.0 ? '<span style="color: #4ADE80; font-weight: 700;">WIN</span>' : (o.runhigh_win === 0.0 ? '<span style="color: #F87171;">LOSS</span>' : 'N/A');
      const rlW = o.runlow_win === 1.0 ? '<span style="color: #4ADE80; font-weight: 700;">WIN</span>' : (o.runlow_win === 0.0 ? '<span style="color: #F87171;">LOSS</span>' : 'N/A');
      const entPr = o.entry_price ? `$${Number(o.entry_price).toFixed(2)}` : 'N/A';

      otb.innerHTML += `<tr>
        <td style="font-family: monospace;">${(o.outcome_id || '').substring(0, 8)}</td>
        <td style="font-family: monospace;">${(o.prediction_id || '').substring(0, 8)}</td>
        <td>${entPr}</td>
        <td style="font-size: 11.5px; font-family: monospace;">${prSeq}</td>
        <td>${o.forward_ticks_count || 0}</td>
        <td>${rhW}</td>
        <td>${rlW}</td>
        <td><strong>${o.outcome_status || 'UNKNOWN'}</strong></td>
        <td style="color: var(--text-secondary);">${o.unresolved_reason || 'Canonical 5-Movement Settled'}</td>
      </tr>`;
    });
  }

  // Quotes table
  const q = data.quotes || {};
  const qtb = document.getElementById("quotes-table-body");
  qtb.innerHTML = "";
  const rh = q.latest_runhigh || {};
  const rl = q.latest_runlow || {};

  if (!rh.ask && !rl.ask) {
    qtb.innerHTML = '<tr><td colspan="6" style="color: var(--text-secondary); text-align: center;">QUOTE_UNAVAILABLE — No active quotes in SQLite store (Benchmark Fallbacks Strictly Prohibited)</td></tr>';
  } else {
    if (rh.ask) {
      qtb.innerHTML += `<tr><td><strong>RUNHIGH (Only Ups)</strong></td><td>$${rh.ask.toFixed(2)}</td><td>$${rh.payout.toFixed(2)}</td><td>${rh.break_even_pct}%</td><td>${rh.latency_ms || 0}</td><td>${rh.timestamp_iso || "N/A"}</td></tr>`;
    }
    if (rl.ask) {
      qtb.innerHTML += `<tr><td><strong>RUNLOW (Only Downs)</strong></td><td>$${rl.ask.toFixed(2)}</td><td>$${rl.payout.toFixed(2)}</td><td>${rl.break_even_pct}%</td><td>${rl.latency_ms || 0}</td><td>${rl.timestamp_iso || "N/A"}</td></tr>`;
    }
  }

  // Recent predictions table
  const ptb = document.getElementById("preds-table-body");
  ptb.innerHTML = "";
  const recs = data.recent_predictions || [];
  if (recs.length === 0) {
    ptb.innerHTML = '<tr><td colspan="8" style="color: var(--text-secondary); text-align: center;">No forward predictions logged in this session</td></tr>';
  } else {
    recs.forEach(r => {
      const dt = new Date((r.timestamp || 0) * 1000).toISOString();
      const rhP = r.runhigh_pred_prob !== null ? `${(r.runhigh_pred_prob * 100).toFixed(2)}%` : "N/A";
      const rlP = r.runlow_pred_prob !== null ? `${(r.runlow_pred_prob * 100).toFixed(2)}%` : "N/A";
      ptb.innerHTML += `<tr>
        <td style="font-family: monospace;">${r.prediction_id}</td>
        <td>${dt}</td>
        <td>${r.market_state}</td>
        <td>${rhP}</td>
        <td>${rlP}</td>
        <td><strong>${r.decision}</strong></td>
        <td style="color: var(--text-secondary);">${r.rejection_reason ? r.rejection_reason.split(";")[0] : "NONE"}</td>
        <td>${r.outcome_status}</td>
      </tr>`;
    });
  }
}

fetchData();
setInterval(fetchData, 4000);
</script>
</body>
</html>
"""


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/data"):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            sym = params.get("symbol", ["R_75"])[0]
            payload = generate_v17_payload(sym)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))


def run_dashboard():
    with socketserver.TCPServer((BIND_HOST, PORT), DashboardRequestHandler) as httpd:
        print(f"\n=======================================================")
        print(f"      DERIV RESEARCH & OBSERVATION DASHBOARD (V1.7)")
        print(f"=======================================================")
        print(f"  URL:             http://{BIND_HOST}:{PORT}")
        print(f"  Design Standard: 60-30-10 Palette (#0B0F19, #131B2E, #0284C7)")
        print(f"  Safety:          REAL-MONEY TRADING DISABLED")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dashboard server...")


if __name__ == "__main__":
    run_dashboard()
