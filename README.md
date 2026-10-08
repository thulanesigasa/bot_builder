# Deriv 5-Tick Quantitative Research & Real-Market Validation Framework (V1.6.1)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Testing](https://img.shields.io/badge/pytest-162%20passed%20(100%25)-success)
![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-blue)
![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-brightgreen)
![Safety](https://img.shields.io/badge/Safety-Zero%20Arbitrary%20Fallbacks-teal)
![Quote Integrity](https://img.shields.io/badge/Quotes-Lookahead--Free%20%7C%20Timestamp%20Enforced-orange)
![Risk Engine](https://img.shields.io/badge/Risk-SQLite--Persisted%20Circuit%20Breaker-purple)
![Live Trading](https://img.shields.io/badge/Live%20Money-DISABLED%20(Zero%20Buy%20Orders)-red)
![Architecture](https://img.shields.io/badge/Architecture-V1.6.1%20Forward%20Observation%20Activation-navy)

A quantitative research, frozen model inference, and real-market forward observation system engineered for Deriv 5-tick contracts—specifically modeling RUNHIGH (Only Ups) and RUNLOW (Only Downs) where every successive tick after the entry spot must move strictly in the contract direction. The system enforces scientific reproducibility, eliminates research placeholders, verifies genuine Deriv quote handling, and enforces non-purchasing observation protocols.

---

## Canonical 5-Tick Contract Execution Lifecycle

The production framework enforces a single canonical contract duration implementation:

```
Signal detected at tick i
       |
Order submitted & processed
       |
Entry Spot S_0 = tick i + 1 (First tick after processing)
       |
  Step 1: S_0 -> S_1 (tick i + 2)
  Step 2: S_1 -> S_2 (tick i + 3)
  Step 3: S_2 -> S_3 (tick i + 4)
  Step 4: S_3 -> S_4 (tick i + 5)
  Step 5: S_4 -> S_5 (tick i + 6, Expiry Spot)
```

### Strict Settlement Rules
- **RUNHIGH (Only Ups)**: Wins if and only if $S_1 > S_0 \land S_2 > S_1 \land S_3 > S_2 \land S_4 > S_3 \land S_5 > S_4$.
- **RUNLOW (Only Downs)**: Wins if and only if $S_1 < S_0 \land S_2 < S_1 \land S_3 < S_2 \land S_4 < S_3 \land S_5 < S_4$.
- **Equality Rule**: Any equality ($=$) at any step results in an immediate contract loss.
- **Reversal Rule**: Any opposing directional tick results in an immediate contract loss.
- **Incomplete Sequences**: Evaluates to `OUTCOME_INCOMPLETE` or `OUTCOME_UNVERIFIED`, preventing artificial loss attribution.
- **Data Gap Sequences**: If time between ticks during the window exceeds $5.0\text{s}$, marked as `OUTCOME_DATA_GAP` and excluded from win-rate metrics.

---

## Empirical Baseline vs Proposal Benchmark

The engine does not assume theoretical random-walk probability ($3.125\%$). It computes the empirical baseline from historical observations:

$$\text{Theoretical Reference} = (0.5)^5 = 0.03125 = 3.125\%$$

$$\text{Deriv Live Proposal Hurdle (\$2.00 Stake } \to \text{\$61.03 Total Payout)} = \frac{\$2.00}{\$61.03} \approx 3.277\%$$

Empirical results on Volatility 75 (`R_75`, 43,184 ticks, 43,178 contract windows):
- **Empirical $P(\text{RUNHIGH})$**: $3.275\%$ ($SE = 0.0009$, $95\%$ Wald CI: $[3.107\%, 3.443\%]$)
- **Empirical $P(\text{RUNLOW})$**: $2.971\%$ ($SE = 0.0008$, $95\%$ Wald CI: $[2.811\%, 3.132\%]$)

---

## V1.6.1 Forward Observation Architecture

V1.6.1 activates sustained live-market forward observation, journals genuine predictions, and resolves empirical outcomes.

### Architecture Highlights

| Component | File | Role |
|---|---|---|
| **Forward Launcher & Preflight** | `run_forward_session.py` | Top-level CLI with safety validation, smoke testing, and grace handling |
| **Centralized Decision Gate** | `decision_gate.py` | Zero arbitrary fallbacks; mandates uncertainty bounds, timestamps, risk state |
| **Persistent Risk Manager** | `risk.py` | SQLite-persisted consecutive loss and drawdown tracker across restarts |
| **Prediction Journal** | `forward_journal.py` | Persists predictions before outcomes; reconstructs 5-movement resolution |
| **Forward Observer** | `forward_observer.py` | Connects tick streamer, quote recorder, model inference, and decision gate |
| **Collection Service** | `forward_collection_service.py` | Long-running auto-reconnecting background daemon |
| **Session Registry** | `forward_session.py` | SQLite session lifecycle registry with telemetry and configuration snapshots |
| **Validation Gate** | `forward_validation_gate.py` | Dependence-aware model promotion/demotion engine ($N_{\text{eff}} \ge 200$) |
| **Session Reporter** | `session_reporter.py` | Generates structured JSON and plain-text session audit summaries |
| **Operations Dashboard** | `dashboard.py` | Real-time monitoring UI adhering to 60-30-10 palette and SVG-only standards |

### End-to-End Data Flow

```
[Live WebSocket: api.derivws.com]
         │
         ├───► LiveTickStreamer ──► ForwardObserver.process_incoming_tick()
         │                               │
         │                               ├──► extract_discrete_market_state() [Lookback >= 25]
         │                               ├──► model_artifact.predict_probabilities()
         │                               ├──► QuoteDatabase.get_latest_quote_before()
         │                               ├──► PersistentRiskManager.get_state()
         │                               ├──► evaluate_paper_trade_eligibility()
         │                               │
         │                               ├──► ForwardPredictionJournal.log_prediction() [PENDING]
         │                               │
         │                               └──► ForwardPredictionJournal.ingest_forward_tick()
         │                                       │ (Accumulates 6 ticks: S0..S5)
         │                                       └──► Reconstruct canonical outcome [RESOLVED]
         │
         └───► DerivQuoteRecorder ──► QuoteDatabase.store_quote()
```

---

## Directory Structure

```
bot_builder/
├── .env.example                        # Environment variables template
├── .gitignore                          # Git ignore specification (.agents protected)
├── README.md                           # Architectural documentation and CLI reference
├── contract_lifecycle.py               # Canonical 5-tick contract execution model
├── dashboard.py                        # Web dashboard (60-30-10 palette, SVG only)
├── decision_gate.py                    # Centralized multi-gate eligibility engine
├── forward_collection_service.py       # Long-running collection service
├── forward_journal.py                  # Forward prediction journal and resolution engine
├── forward_observer.py                 # Forward observation orchestrator
├── forward_session.py                  # Persistent session registry
├── forward_validation_gate.py          # Model promotion and demotion gate
├── live_collector.py                   # Live WebSocket tick streaming and gap monitor
├── model_artifact.py                   # Frozen model schema, checksum, and inference
├── model_manager.py                    # Model registry, training, and holdout evaluation
├── performance_tracker.py              # Economic PnL attribution engine
├── quote_database.py                   # SQLite proposal quote persistence
├── quote_recorder.py                   # Deriv proposal quote recorder
├── risk.py                             # SQLite-persisted risk management engine
├── run_edge_research.py                # Statistical edge analysis and hypothesis testing
├── run_forward_session.py              # Primary V1.6.1 CLI entry point
├── session_reporter.py                 # Session and daily report generator
├── verify_deriv_connection.py          # WebSocket handshake and latency diagnostic
├── data/
│   ├── forward_predictions.db          # Persistent SQLite forward predictions database
│   ├── quotes.db                       # Persistent SQLite proposal quotes database
│   ├── risk_state.db                   # Persistent SQLite risk state database
│   ├── sessions.db                     # Persistent SQLite forward sessions database
│   ├── validation_gate.db              # Model promotion and audit trail database
│   ├── R_75_master.csv                 # Canonical historical tick dataset
│   └── quarantine/
│       ├── .gitkeep
│       └── quarantine_log.json
├── models/
│   └── M_R_75_5TICK_20261008_132512.json # Frozen baseline research model artifact
├── reports/
│   ├── V1_6_1_FORWARD_ACTIVATION_REPORT.md # Comprehensive V1.6.1 validation report
│   └── session_*.json                  # Generated forward session audit reports
└── tests/
    ├── test_v161_forward_activation.py # V1.6.1 safety and lifecycle regression tests
    └── ...                             # 144 baseline automated unit tests
```

---

## Verified Command Execution Reference

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Run Complete Regression Test Suite (162 Passed)
```powershell
python -m pytest tests/ -q
```

### 3. Inspect Frozen Model Artifacts
```powershell
python model_manager.py --inspect models/M_R_75_5TICK_20261008_132512.json
```

### 4. Verify Deriv WebSocket API Connectivity
```powershell
python verify_deriv_connection.py --symbol R_75 --timeout 6.0
```

### 5. Inspect Recorded Proposal Quotes
```powershell
python quote_database.py --inspect
```

### 6. Start DATA_COLLECTION_ONLY Mode
```powershell
python run_forward_session.py --symbol R_75 --mode DATA_COLLECTION_ONLY --duration 3600
```

### 7. Start Live Forward Observation in SHADOW Mode
```powershell
python run_forward_session.py --symbol R_75 --mode SHADOW --duration 3600 --quote-interval 2.0
```

### 8. Inspect Recent Forward Predictions and Outcomes
```powershell
python -c "from forward_journal import ForwardPredictionJournal; j = ForwardPredictionJournal('data/forward_predictions.db'); print(j.inspect_recent(limit=5))"
```

### 9. Inspect Unresolved or Dangling Predictions
```powershell
python -c "import sqlite3; conn = sqlite3.connect('data/forward_predictions.db'); print(conn.execute(\"SELECT prediction_id, outcome_status, forward_ticks_count FROM forward_predictions WHERE outcome_status IN ('PENDING', 'OUTCOME_PENDING')\").fetchall())"
```

### 10. Generate Session Audit Reports
```powershell
python -c "from session_reporter import SessionReporter; from forward_journal import ForwardPredictionJournal; from forward_session import ForwardSessionRegistry; from quote_database import QuoteDatabase; rep = SessionReporter('reports', ForwardPredictionJournal('data/forward_predictions.db'), ForwardSessionRegistry('data/sessions.db'), QuoteDatabase('data/quotes.db')); print(rep.generate_daily_summary())"
```

### 11. Generate Statistical Calibration & Accuracy Metrics
```powershell
python -c "from forward_journal import ForwardPredictionJournal; import json; j = ForwardPredictionJournal('data/forward_predictions.db'); print(json.dumps(j.get_accuracy_metrics('R_75'), indent=2))"
```

### 12. Launch Unified Web Operations Dashboard
```powershell
python dashboard.py 8088
```
Navigate to `http://127.0.0.1:8088`.

---

## Safety Directives & Final Verdict

- **Real-Money Trading:** Permanently locked to disabled (`LIVE_EXECUTION_DISABLED = True`). Zero buy orders are submitted under any circumstances.
- **Operational Status:** `LIVE_SHADOW_COLLECTION_VERIFIED`. The system records and resolves genuine forward predictions with sub-second accuracy.
- **Model Promotion:** Baseline models remain `RESEARCH_ONLY`. Promotion to `APPROVED_FOR_PAPER` requires independent non-overlapping out-of-sample evidence exceeding the break-even hurdle ($3.277\%$) with statistically significant conservative expected value.
