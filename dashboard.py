"""Local Web Dashboard & Visual Analysis Engine for Deriv Quantitative Research (V1.6.1).

Renders a strict 60-30-10 interface with SVG visualizations:
1. Forward Session: Session ID, current mode, session duration, active symbol, connection status.
2. Live Data: Total ticks, total genuine proposals, quote coverage, latest received timestamp, data gaps.
3. Prediction Pipeline: Eligible feature windows, predictions generated, predictions persisted, outcomes pending, outcomes resolved, journal errors.
4. Statistical Evidence: Predicted RUNHIGH/RUNLOW probabilities, observed probabilities, Brier score, calibration, sample counts.
5. System Safety & Risk: Model approval status, persistent risk state, conservative EV availability, NO_TRADE reasons.
   Permanent declaration: REAL-MONEY TRADING DISABLED.

Design Standards:
- 60% Dominant Background: #0B0F19
- 30% Surface/Panels: #131B2E
- 10% Accent: #0284C7
- Vector SVGs only (strictly no emojis per Rule 2 & 4)
- Zero hover glow animations (Rule 3)
- Strict Rule 16 compliance: Zero status badges or cards (e.g. 'READ ONLY', 'RUNNING', etc.)
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


def generate_v161_payload(symbol: str = "R_75") -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    # 1. Forward Sessions Registry
    sess_reg = ForwardSessionRegistry()
    recent_sessions = sess_reg.list_sessions(symbol=symbol, limit=1)
    active_session = recent_sessions[0] if recent_sessions else None

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

    # 4. Actual Quotes
    q_db = QuoteDatabase()
    q_cov = q_db.report_quote_coverage(symbol)
    latest_rh = q_db.get_latest_quote_before(symbol, "RUNHIGH", timestamp=time.time(), max_freshness_seconds=86400.0)
    latest_rl = q_db.get_latest_quote_before(symbol, "RUNLOW", timestamp=time.time(), max_freshness_seconds=86400.0)

    # 5. Forward Prediction Journal
    fwd_journal = ForwardPredictionJournal()
    fwd_metrics = fwd_journal.get_accuracy_metrics(symbol=symbol)
    recent_preds = fwd_journal.inspect_recent(limit=8, symbol=symbol)

    # 6. Persistent Risk State
    risk_mgr = RiskManager(symbol=symbol)
    risk_snap = risk_mgr.get_state()

    # Live ticks count from CSV if exists
    live_ticks_csv = os.path.join(data_dir, f"{symbol}_live_ticks.csv")
    live_ticks_count = 0
    if os.path.exists(live_ticks_csv):
        try:
            with open(live_ticks_csv, "r", encoding="utf-8") as f:
                live_ticks_count = max(0, sum(1 for _ in f) - 1)
        except Exception:
            pass

    # Extract top rejection reasons
    rejection_counts: Dict[str, int] = {}
    for r in recent_preds:
        reason = r.get("rejection_reason", "")
        if reason:
            for part in reason.split(";"):
                if part:
                    rejection_counts[part] = rejection_counts.get(part, 0) + 1

    return {
        "version": "V1.6.1",
        "symbol": symbol,
        "available_symbols": get_available_symbols(),
        "safety_invariant": "REAL-MONEY TRADING DISABLED (Zero buy orders / Research Only)",
        "session": {
            "session_id": active_session.session_id if active_session else "NONE",
            "mode": active_session.mode if active_session else "SHADOW",
            "status": active_session.status if active_session else "STANDBY",
            "symbol": active_session.symbol if active_session else symbol,
            "duration_seconds": active_session.planned_duration_seconds if active_session else 0,
            "connection_status": health.get("connectivity", {}).get("connection_status", "DISCONNECTED"),
        },
        "live_data": {
            "total_ticks": live_ticks_count or active_session.total_ticks if active_session else 0,
            "total_proposals": q_cov.get("total_quotes", 0),
            "quote_coverage_pct": fwd_metrics.get("quote_coverage_pct", 0.0),
            "latest_received_timestamp": health.get("ticks", {}).get("latest_tick_time_utc", "N/A"),
            "data_gaps_count": health.get("ticks", {}).get("total_gaps", 0),
            "has_active_data_gap": health.get("has_active_data_gap", False)
        },
        "pipeline": {
            "eligible_feature_windows": fwd_metrics.get("total_predictions", 0),
            "predictions_generated": fwd_metrics.get("total_predictions", 0),
            "predictions_persisted": fwd_metrics.get("total_predictions", 0),
            "outcomes_pending": fwd_metrics.get("pending_predictions", 0),
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
        "safety_risk": {
            "model_approval_status": model_info.get("approval_status", "UNKNOWN"),
            "conservative_ev_availability": "AVAILABLE" if model_info.get("approval_status") == ModelStatus.FORWARD_VALIDATED else "UNCERTAINTY_UNAVAILABLE",
            "consecutive_losses": risk_snap.consecutive_losses,
            "daily_drawdown_pct": risk_snap.max_drawdown_pct,
            "is_in_cooldown": risk_snap.is_paused,
            "is_risk_valid": risk_snap.is_valid,
            "rejection_reasons_summary": rejection_counts
        },
        "model": model_info,
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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deriv 5-Tick Quantitative Research & Forward Observation Dashboard — V1.6.1</title>
<style>
  :root {
    --bg-main: #0B0F19;
    --bg-surface: #131B2E;
    --border-subtle: #1E293B;
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --accent: #0284C7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background-color: var(--bg-main);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 1320px; margin: 0 auto; }
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
  
  .grid-5 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
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
        <h1>Deriv Only Ups / Only Downs Forward Observation Dashboard</h1>
        <div class="subtitle">V1.6.1 — Statistical Safety, Forward Prediction Lifecycle & Evidence Collection</div>
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

  <div class="grid-5">
    <!-- 1. Forward Session -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14h2v2h-2v-2zm0-10h2v8h-2V6z"/></svg>
        Forward Session
      </div>
      <div class="card-val" id="sess-id">STANDBY</div>
      <div class="card-desc" id="sess-desc">Mode: SHADOW | Connection: Active</div>
    </div>

    <!-- 2. Live Data -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
        Live Market Feed
      </div>
      <div class="card-val" id="live-ticks">0 Ticks</div>
      <div class="card-desc" id="live-quotes">Proposals: 0 | Coverage: 0%</div>
    </div>

    <!-- 3. Prediction Pipeline -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
        Prediction Pipeline
      </div>
      <div class="card-val" id="pipe-total">0 Logged</div>
      <div class="card-desc" id="pipe-desc">Resolved: 0 | Pending: 0</div>
    </div>

    <!-- 4. Statistical Evidence -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/></svg>
        Statistical Calibration
      </div>
      <div class="card-val" id="stat-brier">Brier: N/A</div>
      <div class="card-desc" id="stat-rates">RH Win: N/A | RL Win: N/A</div>
    </div>

    <!-- 5. Safety & Risk -->
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>
        Safety & Risk State
      </div>
      <div class="card-val" id="risk-status">RESEARCH_ONLY</div>
      <div class="card-desc" id="risk-desc">Losses: 0 | DD: 0.0%</div>
    </div>
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
        <tr><td colspan="8" style="color: var(--text-secondary); text-align: center;">No forward predictions logged</td></tr>
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

  // 1. Forward Session card
  const s = data.session || {};
  document.getElementById("sess-id").textContent = s.session_id !== "NONE" ? s.session_id.substring(0, 8) : "STANDBY";
  document.getElementById("sess-desc").textContent = `Mode: ${s.mode} | Symbol: ${s.symbol} | Status: ${s.connection_status}`;

  // 2. Live Data card
  const ld = data.live_data || {};
  document.getElementById("live-ticks").textContent = `${(ld.total_ticks || 0).toLocaleString()} Ticks`;
  document.getElementById("live-quotes").textContent = `Proposals: ${ld.total_proposals || 0} | Coverage: ${ld.quote_coverage_pct || 0}% | Gaps: ${ld.data_gaps_count || 0}`;

  // 3. Prediction Pipeline card
  const pipe = data.pipeline || {};
  document.getElementById("pipe-total").textContent = `${pipe.predictions_persisted || 0} Logged`;
  document.getElementById("pipe-desc").textContent = `Resolved: ${pipe.outcomes_resolved || 0} | Pending: ${pipe.outcomes_pending || 0} | Inc: ${pipe.outcomes_incomplete || 0}`;

  // 4. Statistical Evidence card
  const stat = data.statistical_evidence || {};
  const brierStr = stat.brier_score_runhigh ? `Brier: ${stat.brier_score_runhigh}` : "Brier: N/A";
  document.getElementById("stat-brier").textContent = brierStr;
  const rhRate = stat.observed_runhigh_prob !== null ? `${(stat.observed_runhigh_prob * 100).toFixed(1)}%` : "N/A";
  const rlRate = stat.observed_runlow_prob !== null ? `${(stat.observed_runlow_prob * 100).toFixed(1)}%` : "N/A";
  document.getElementById("stat-rates").textContent = `Obs RH: ${rhRate} | Obs RL: ${rlRate} (N=${stat.sample_counts || 0})`;

  // 5. Safety & Risk card
  const sr = data.safety_risk || {};
  document.getElementById("risk-status").textContent = sr.model_approval_status || "UNKNOWN";
  document.getElementById("risk-desc").textContent = `Losses: ${sr.consecutive_losses || 0} | Drawdown: ${((sr.daily_drawdown_pct || 0) * 100).toFixed(1)}% | ConsEV: ${sr.conservative_ev_availability}`;

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
            payload = generate_v161_payload(sym)
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
        print(f"      DERIV RESEARCH & OBSERVATION DASHBOARD (V1.6.1)")
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
