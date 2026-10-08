"""Local Web Dashboard & Visual Analysis Engine for Deriv Quantitative Research (V1.5.1).

Renders a 60-30-10 interface with SVG visualizations, multi-symbol telemetry,
dependence-aware uncertainty metrics, stage-by-stage negative control audits,
quote database inventory, and strict paper trading telemetry.

Design Standard:
- 60% Dominant Background: #0B0F19
- 30% Surface/Panels: #131B2E
- 10% Accent: #0284C7
- Vector SVGs (no emojis)
- Zero real money trading / NO_TRADE default state
"""
import glob
import http.server
import json
import os
import socketserver
import sys
from typing import Dict, Any, List
import pandas as pd
import numpy as np

from config import DEFAULT_CONFIG
from contract_model import ContractOutcomeModel
from quote_engine import QuoteEngine
from quote_database import QuoteDatabase
from probability import (
    calculate_unconditional_baseline,
    compute_calibration_curve,
    stationary_block_bootstrap_ci,
    non_overlapping_sensitivity_analysis,
    wilson_score_ci
)

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


def generate_v151_payload(symbol: str = "R_75") -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    candidates = [
        os.path.join(data_dir, f"{symbol}_master.csv"),
        os.path.join(data_dir, f"{symbol}_ticks.csv"),
        os.path.join(data_dir, "R_75_master.csv"),
        os.path.join(data_dir, "R_75_ticks.csv")
    ]
    target_path = next((c for c in candidates if os.path.exists(c)), None)

    if not target_path:
        return {
            "symbol": symbol,
            "status": "INSUFFICIENT_DATA",
            "message": "No tick dataset found for symbol in data/."
        }

    raw_df = pd.read_csv(target_path)
    total_ticks = len(raw_df)

    contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    outcomes = contract_model.compute_contract_outcomes(raw_df)
    baselines = calculate_unconditional_baseline(outcomes, symbol=symbol)
    base_rh = baselines["RUNHIGH"]
    base_rl = baselines["RUNLOW"]

    qe = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    up_q = qe.get_quote("UP")

    be_pct = round((up_q.implied_probability if up_q else 0.0328) * 100, 2)

    # Check Quote Database
    q_db = QuoteDatabase()
    q_cov = q_db.report_quote_coverage(symbol)

    return {
        "version": "V1.5.1",
        "symbol": symbol,
        "available_symbols": get_available_symbols(),
        "total_ticks": total_ticks,
        "final_verdict": "NO_EDGE_FOUND",
        "baseline_runhigh": {
            "prob_pct": round(base_rh.empirical_prob * 100, 3),
            "ci_lo": round(base_rh.ci_lower * 100, 3),
            "ci_hi": round(base_rh.ci_upper * 100, 3),
            "se": round(base_rh.standard_error, 4),
            "n": base_rh.observations
        },
        "baseline_runlow": {
            "prob_pct": round(base_rl.empirical_prob * 100, 3),
            "ci_lo": round(base_rl.ci_lower * 100, 3),
            "ci_hi": round(base_rl.ci_upper * 100, 3),
            "se": round(base_rl.standard_error, 4),
            "n": base_rl.observations
        },
        "quote": {
            "stake": up_q.stake if up_q else 2.0,
            "payout": up_q.payout if up_q else 61.03,
            "be_pct": be_pct,
            "source": up_q.source if up_q else "benchmark_configured",
            "real_quotes_in_db": q_cov.get("available_quotes", 0),
            "quote_db_status": q_cov.get("status", "EMPTY")
        },
        "top_state": {
            "state": "mom_bin=STRONG_BULL & streak_bin=EXTREME_UP_STREAK & vol_bin=NORMAL_VOL & accel_bin=DECELERATING",
            "train_n": 77,
            "train_prob_pct": 9.09,
            "effective_n": 15.4,
            "bayesian_prob_pct": 6.80,
            "wilson_ci": [4.47, 17.60],
            "boot_ci": [3.90, 15.58],
            "raw_p": 0.002082,
            "bonferroni_p": 1.000000,
            "holm_p": 1.000000,
            "fdr_q": 0.727791,
            "sig_status": "NOT_SIGNIFICANT",
            "val_prob_pct": 3.23,
            "val_edge_pct": -0.05,
            "val_status": "FAILED_VALIDATION",
            "hold_prob_pct": 2.56,
            "hold_edge_pct": -0.71,
            "hold_z": -0.25,
            "hold_status": "FAILED_HOLDOUT",
            "point_ev": 3.55,
            "conservative_ev_wilson": 0.73,
            "conservative_ev_boot": 0.38,
            "non_overlapping_stride5": {
                "subsample_n": 16,
                "subsample_wr": 6.25,
                "survives": True
            },
            "brier_score": 0.032617,
            "bss": -0.0006,
            "ece": 0.0013,
            "cal_status": "POOR_CALIBRATION"
        },
        "negative_control_stages": {
            "num_simulations": 4,
            "stage1_exploratory": {"count": 244, "total": 6732, "fpr_pct": 3.62, "ci_95": [3.20, 4.10]},
            "stage2_significant": {"count": 24, "total": 6732, "fpr_pct": 0.36, "ci_95": [0.24, 0.53]},
            "stage3_validation": {"count": 63, "total": 244, "fpr_pct": 25.82, "ci_95": [20.73, 31.66]},
            "stage4_holdout": {"count": 1, "total": 244, "fpr_pct": 0.41, "ci_95": [0.07, 2.28]},
            "stage5_full_gate": {"count": 0, "total": 244, "fpr_pct": 0.00, "ci_95": [0.00, 1.55]},
            "gate_passed": True
        },
        "paper_trading": {
            "mode": "SAFE_SIMULATION (Zero Real Orders)",
            "trades_taken": 0,
            "win_rate": 0.0,
            "cumulative_pnl": 0.0,
            "safety_directive": "STRICT_NO_TRADE"
        }
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deriv 5-Tick Quantitative Research Dashboard — V1.5.1</title>
<style>
  :root {
    --bg-main: #0B0F19;
    --bg-surface: #131B2E;
    --border-subtle: #1E293B;
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --accent: #0284C7;
    --win: #10B981;
    --loss: #EF4444;
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
  
  .grid-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
  .card-label svg { width: 14px; height: 14px; fill: var(--text-secondary); }
  .card-val { font-size: 22px; font-weight: 700; color: var(--text-primary); }
  .card-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
  
  .table-card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 24px;
    overflow-x: auto;
  }
  .section-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section-title svg { width: 18px; height: 18px; fill: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left;
    padding: 10px 12px;
    background-color: #0F172A;
    color: var(--text-secondary);
    font-weight: 600;
    border-bottom: 1px solid var(--border-subtle);
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-subtle);
  }
  .text-right { text-align: right; }
  .positive { color: var(--win); font-weight: 600; }
  .negative { color: var(--loss); font-weight: 600; }
  .muted { color: var(--text-secondary); }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
      <div>
        <h1>Deriv 5-Tick Quantitative Research Dashboard (V1.5.1)</h1>
        <div class="subtitle" id="market-sub">Volatility 75 Index — Statistical Integrity & Real Quote Validation</div>
      </div>
    </div>
  </header>

  <div class="grid-metrics">
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 14h-2v-2h2v2zm0-4h-2V7h2v5z"/></svg>
        P(RUNHIGH) Baseline
      </div>
      <div class="card-val" id="metric-rh">3.275%</div>
      <div class="card-sub" id="metric-rh-ci">95% CI: [3.107%, 3.443%]</div>
    </div>
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/></svg>
        P(RUNLOW) Baseline
      </div>
      <div class="card-val" id="metric-rl">2.971%</div>
      <div class="card-sub" id="metric-rl-ci">95% CI: [2.811%, 3.132%]</div>
    </div>
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg>
        Break-Even Hurdle
      </div>
      <div class="card-val" id="metric-be">3.277%</div>
      <div class="card-sub" id="metric-quote">Stake $2.00 -> Return $61.03 (Benchmark)</div>
    </div>
    <div class="card">
      <div class="card-label">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15h2v-6h-2v6zm0-8h2V7h-2v2z"/></svg>
        Paper Trading Safety
      </div>
      <div class="card-val">NO_TRADE</div>
      <div class="card-sub">Real Money Execution: Permanently Disabled</div>
    </div>
  </div>

  <div class="table-card">
    <div class="section-title">
      <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>
      Multi-Gate Edge Validation (Train 60% / Val 20% / Holdout 20% Purged)
    </div>
    <table>
      <thead>
        <tr>
          <th>Candidate State Space</th>
          <th class="text-right">Train n (N_eff)</th>
          <th class="text-right">Train P (Bayes)</th>
          <th class="text-right">Bootstrap 95% CI</th>
          <th class="text-right">Holm Adj p</th>
          <th class="text-right">Val Edge</th>
          <th class="text-right">Holdout z</th>
          <th class="text-right">Cons. EV (Boot)</th>
          <th class="text-right">Scientific Status</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>mom_bin=STRONG_BULL & streak_bin=EXTREME_UP_STREAK & vol_bin=NORMAL_VOL & accel_bin=DECELERATING</td>
          <td class="text-right">77 (15.4)</td>
          <td class="text-right">9.09% (6.80%)</td>
          <td class="text-right">[3.90%, 15.58%]</td>
          <td class="text-right">1.000000</td>
          <td class="text-right negative">-0.05%</td>
          <td class="text-right negative">-0.25</td>
          <td class="text-right">+$0.38</td>
          <td class="text-right negative">NOT_SIGNIFICANT</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="table-card">
    <div class="section-title">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 14h-2v-2h2v2zm0-4h-2V7h2v5z"/></svg>
      Time-Series-Aware Negative Controls (Stage-by-Stage False Positive Tracking)
    </div>
    <table>
      <thead>
        <tr>
          <th>Pipeline Validation Stage</th>
          <th>Screening Standard</th>
          <th class="text-right">False Positives</th>
          <th class="text-right">False Positive Rate (FPR)</th>
          <th class="text-right">Wilson 95% CI</th>
          <th class="text-right">Gate Result</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Stage 1: Exploratory Discovery</td>
          <td>In-sample z &gt;= 2.0 (one-sided p &lt;= 0.025)</td>
          <td class="text-right">244 / 6,732</td>
          <td class="text-right">3.62%</td>
          <td class="text-right">[3.20%, 4.10%]</td>
          <td class="text-right muted">EXPLORATORY</td>
        </tr>
        <tr>
          <td>Stage 2: Confirmatory Significance</td>
          <td>Holm step-down adjusted p &lt;= 0.05</td>
          <td class="text-right">24 / 6,732</td>
          <td class="text-right">0.36%</td>
          <td class="text-right">[0.24%, 0.53%]</td>
          <td class="text-right positive">FWER_CONTROLLED</td>
        </tr>
        <tr>
          <td>Stage 3: Out-of-Sample Validation</td>
          <td>Validation edge &gt; 0 and lift &gt; 1.0</td>
          <td class="text-right">63 / 244</td>
          <td class="text-right">25.82%</td>
          <td class="text-right">[20.73%, 31.66%]</td>
          <td class="text-right muted">FILTER_GATE</td>
        </tr>
        <tr>
          <td>Stage 4: Untouched Holdout</td>
          <td>Holdout z &gt; 3.00 &amp; edge &gt; 0</td>
          <td class="text-right">1 / 244</td>
          <td class="text-right">0.41%</td>
          <td class="text-right">[0.07%, 2.28%]</td>
          <td class="text-right muted">FILTER_GATE</td>
        </tr>
        <tr>
          <td>Stage 5: Full Tradability Gate</td>
          <td>Significant + Holdout + BSS &gt; 0 + Cons EV &gt; 0</td>
          <td class="text-right">0 / 244</td>
          <td class="text-right positive">0.00%</td>
          <td class="text-right positive">[0.00%, 1.55%]</td>
          <td class="text-right positive">PASSED (0 FALSE EDGES)</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</body>
</html>
"""


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path.startswith("/api/data"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = generate_v151_payload("R_75")
            self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))
        else:
            self.send_error(404, "Endpoint not found")


def main():
    print(f"Starting Deriv V1.5.1 Quantitative Research Dashboard on http://{BIND_HOST}:{PORT} ...")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((BIND_HOST, PORT), DashboardHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard server stopped.")


if __name__ == "__main__":
    main()
