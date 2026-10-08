"""Local Web Dashboard & Visual Analysis Engine for Deriv Quantitative Research (V1.5.3).

Renders a 60-30-10 interface with SVG visualizations:
1. Frozen Model Status: Model ID, version, approval status, schema version, calibration metrics.
2. Live API Connectivity: Connection status, endpoint diagnostic results, latency, error details.
3. Actual Quotes: RUNHIGH & RUNLOW ask, payout, quote freshness, break-even probability (Null when unavailable).
4. Forward Predictions: Calibrated probabilities, shadow predictions, resolved vs unverified outcomes, Brier score.
5. System Safety: Permanent declaration that real-money trading is strictly disabled.

Design Standard:
- 60% Dominant Background: #0B0F19
- 30% Surface/Panels: #131B2E
- 10% Accent: #0284C7
- Vector SVGs (no emojis per Rule 2 & 4)
- Zero hover glow animations (Rule 3)
- Strict Rule 16 compliance: Zero development status tags/badges
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
from health_monitor import GLOBAL_HEALTH_MONITOR
from model_artifact import ModelArtifact, ModelStatus
from model_manager import ModelManager
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine


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


def generate_v153_payload(symbol: str = "R_75") -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    # 1. Historical Dataset
    candidates = [
        os.path.join(data_dir, f"{symbol}_master.csv"),
        os.path.join(data_dir, f"{symbol}_ticks.csv"),
        os.path.join(data_dir, "R_75_master.csv"),
        os.path.join(data_dir, "R_75_ticks.csv")
    ]
    target_path = next((c for c in candidates if os.path.exists(c)), None)
    total_ticks = 0
    if target_path:
        try:
            raw_df = pd.read_csv(target_path)
            total_ticks = len(raw_df)
        except Exception:
            pass

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

    # 3. Live API Diagnostic State
    diag_file = os.path.join(script_dir, "reports", "deriv_api_diagnostic.json")
    api_diag: Dict[str, Any] = {
        "status": "DIAGNOSTIC_NOT_RUN",
        "endpoint": "wss://ws.derivws.com/websockets/v3",
        "timestamp": "N/A",
        "details": "Run python verify_deriv_connection.py to generate live diagnostic telemetry."
    }
    if os.path.exists(diag_file):
        try:
            with open(diag_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                api_diag = {
                    "status": d.get("status", "UNKNOWN"),
                    "endpoint": d.get("endpoint_url", "wss://ws.derivws.com/websockets/v3"),
                    "timestamp": d.get("timestamp_utc", "N/A"),
                    "details": d.get("error_details") or "Connection diagnostic completed."
                }
        except Exception:
            pass

    # 4. Actual Quotes (Null when missing, NO benchmark fallbacks)
    q_db = QuoteDatabase()
    q_cov = q_db.report_quote_coverage(symbol)
    latest_rh = q_db.get_latest_quote_before(symbol, "RUNHIGH", timestamp=time.time(), max_freshness_seconds=86400.0)
    latest_rl = q_db.get_latest_quote_before(symbol, "RUNLOW", timestamp=time.time(), max_freshness_seconds=86400.0)

    # 5. Forward Prediction Journal
    fwd_journal = ForwardPredictionJournal()
    fwd_metrics = fwd_journal.get_accuracy_metrics(symbol=symbol)
    recent_preds = fwd_journal.inspect_recent(limit=5, symbol=symbol)

    # 6. Global Health Telemetry
    health = GLOBAL_HEALTH_MONITOR.get_health_summary()

    return {
        "version": "V1.5.3",
        "symbol": symbol,
        "available_symbols": get_available_symbols(),
        "total_historical_ticks": total_ticks,
        "safety_invariant": "REAL-MONEY TRADING DISABLED (Zero buy orders / Research Only)",
        "model": model_info,
        "api_connectivity": api_diag,
        "health": health,
        "quotes": {
            "database_total_quotes": q_cov.get("total_quotes", 0),
            "runhigh_recorded": q_cov.get("runhigh_quotes", 0),
            "runlow_recorded": q_cov.get("runlow_quotes", 0),
            "time_span_hours": q_cov.get("time_span_hours", 0.0),
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
        "forward_predictions": fwd_metrics,
        "recent_predictions": recent_preds
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deriv 5-Tick Quantitative Research & Live Data Dashboard — V1.5.3</title>
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
  .container { max-width: 1280px; margin: 0 auto; }
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
  
  .grid-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 16px;
  }
  .card-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .card-label svg { width: 14px; height: 14px; fill: var(--accent); }
  .card-val {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
  }
  .card-desc { font-size: 12px; color: var(--text-secondary); }

  .panel {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .panel-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .panel-title svg { width: 18px; height: 18px; fill: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
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
        <h1>Deriv Only Ups / Only Downs Research Dashboard</h1>
        <div class="subtitle">V1.5.3 Hotfix — Model Integration, Quote Integrity & Forward Observation</div>
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
    <div>REAL-MONEY TRADING DISABLED — Research, Shadow Observation & Non-Purchasing Simulation Mode Only</div>
  </div>

  <div class="grid-metrics">
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/></svg>
        Frozen Model ID
      </div>
      <div class="card-val" id="model-id" style="font-size: 15px; font-family: monospace;">Loading...</div>
      <div class="card-desc" id="model-desc">Status: Checking...</div>
    </div>

    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14h2v2h-2v-2zm0-10h2v8h-2V6z"/></svg>
        API Diagnostic
      </div>
      <div class="card-val" id="api-status">Checking...</div>
      <div class="card-desc" id="api-desc">Endpoint: wss://ws.derivws.com</div>
    </div>

    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
        Genuine Quotes In DB
      </div>
      <div class="card-val" id="quotes-total">0</div>
      <div class="card-desc" id="quotes-breakdown">RUNHIGH: 0 | RUNLOW: 0</div>
    </div>

    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
        Forward Predictions
      </div>
      <div class="card-val" id="fwd-total">0</div>
      <div class="card-desc" id="fwd-desc">Resolved: 0 | Unverified: 0</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-title">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
      Actual Market Proposal Quotes (Strictly No Benchmark Fallbacks)
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
      Recent Forward Shadow Predictions (Append-Only Journal)
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
          <th>Rejection Reason</th>
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
  // Populate symbols dropdown
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

  // Model card
  const m = data.model || {};
  document.getElementById("model-id").textContent = m.model_id || "NONE";
  document.getElementById("model-desc").textContent = `Approval: ${m.approval_status} | Schema: v${m.feature_schema_version}`;

  // API Diagnostic card
  const api = data.api_connectivity || {};
  document.getElementById("api-status").textContent = api.status;
  document.getElementById("api-desc").textContent = api.details || api.endpoint;

  // Quotes card
  const q = data.quotes || {};
  document.getElementById("quotes-total").textContent = (q.database_total_quotes || 0).toLocaleString();
  document.getElementById("quotes-breakdown").textContent = `RUNHIGH: ${q.runhigh_recorded || 0} | RUNLOW: ${q.runlow_recorded || 0}`;

  // Forward predictions card
  const fwd = data.forward_predictions || {};
  document.getElementById("fwd-total").textContent = (fwd.total_predictions || 0).toLocaleString();
  document.getElementById("fwd-desc").textContent = `Resolved: ${fwd.resolved_predictions || 0} | Unverified: ${fwd.unverified_predictions || 0}`;

  // Quotes table
  const qtb = document.getElementById("quotes-table-body");
  qtb.innerHTML = "";
  const rh = q.latest_runhigh || {};
  const rl = q.latest_runlow || {};

  if (!rh.ask && !rl.ask) {
    qtb.innerHTML = '<tr><td colspan="6" style="color: var(--text-secondary); text-align: center;">QUOTE_UNAVAILABLE — No active quotes in SQLite store (Fallbacks Prohibited)</td></tr>';
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
      ptb.innerHTML += `<tr>
        <td style="font-family: monospace;">${r.prediction_id}</td>
        <td>${dt}</td>
        <td>${r.market_state}</td>
        <td>${(r.runhigh_pred_prob * 100).toFixed(2)}%</td>
        <td>${(r.runlow_pred_prob * 100).toFixed(2)}%</td>
        <td><strong>${r.decision}</strong></td>
        <td style="color: var(--text-secondary);">${r.rejection_reason || "NONE"}</td>
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
            payload = generate_v153_payload(sym)
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
        print(f"      DERIV RESEARCH & OBSERVATION DASHBOARD (V1.5.3)")
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
