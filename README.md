# Deriv 5-Tick Quantitative Research & Real-Market Validation Framework (V1.6.3)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Testing](https://img.shields.io/badge/pytest-188%20passed%20(100%25)-0284C7)
![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)
![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)
![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)
![Reconciliation](https://img.shields.io/badge/Reconciliation-6--Dimension%20Automated%20Engine-0284C7)
![Referential Integrity](https://img.shields.io/badge/Database-Foreign%20Keys%20Enforced-0284C7)
![Quote Integrity](https://img.shields.io/badge/Quotes-Session--Linked%20%7C%20Lookahead--Free-0284C7)
![Prediction Pipeline](https://img.shields.io/badge/Prediction%20Activation-Dynamic%20Lookback%20%26%20Warmup%20Preload-0284C7)
![Architecture](https://img.shields.io/badge/Architecture-V1.6.3%20Complete%20System%20Integration-0284C7)

A quantitative research, frozen model inference, and real-market forward observation system engineered for Deriv 5-tick contracts—specifically modeling RUNHIGH (Only Ups) and RUNLOW (Only Downs) where every successive tick after the entry spot must move strictly in the contract direction.

V1.6.3 resolves the zero forward predictions problem through dynamic model lookback, historical feature warm-up preloading, quote-independent SHADOW prediction journaling, authoritative outcome chronology verification, and multi-session provenance accounting.

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
- **Incomplete Sequences**: Evaluates to `OUTCOME_INCOMPLETE`, preventing artificial loss attribution.
- **Data Gap Sequences**: If elapsed time between ticks during observation exceeds $5.0\text{s}$, classified as `OUTCOME_DATA_GAP` and excluded from win-rate metrics.

---

## Empirical Baseline vs Proposal Benchmark

The engine does not assume theoretical random-walk probability ($3.125\%$). It computes the empirical baseline from historical observations:

$$\text{Theoretical Reference} = (0.5)^5 = 0.03125 = 3.125\%$$

$$\text{Deriv Live Proposal Hurdle (\$2.00 Stake } \to \text{\$61.03 Total Payout)} = \frac{\$2.00}{\$61.03} \approx 3.277\%$$

Empirical results on Volatility 75 (`R_75`, 43,184 ticks, 43,178 contract windows):
- **Empirical $P(\text{RUNHIGH})$**: $3.275\%$ ($SE = 0.0009$, $95\%$ Wald CI: $[3.107\%, 3.443\%]$)
- **Empirical $P(\text{RUNLOW})$**: $2.971\%$ ($SE = 0.0008$, $95\%$ Wald CI: $[2.811\%, 3.132\%]$)

---

## V1.6.3 Core Architecture & Pipeline Components

| Component | File | Role |
|---|---|---|
| **Forward Observer** | `forward_observer.py` | Feature buffer, historical warmup preloading, dynamic lookback inference, quote matching |
| **Collection Service** | `forward_collection_service.py` | Sustained WebSocket collection service, auto-reconnect, end-of-session reconciliation |
| **Session Launcher** | `run_forward_session.py` | Operational CLI entry point with preflight checks and `--diagnose` troubleshooting mode |
| **Session Reconciler** | `session_reconciler.py` | 6-dimension automated audit engine verifying provenance, ticks, quotes, and outcome chronology |
| **Session Registry** | `forward_session.py` | Authoritative lifecycle transitions, tick breakdown accounting, dangling session recovery |
| **Prediction Journal** | `forward_journal.py` | Dedicated foreign-key `forward_outcomes` table, immutable predictions, outcome reconstruction |
| **Model Artifact** | `model_artifact.py` | Frozen model schema with dynamic `required_lookback`, cryptographic checksum, and inference |
| **Quote Database** | `quote_database.py` | SQLite proposal quote persistence strictly linked and queried by `session_id` |
| **Quote Recorder** | `quote_recorder.py` | Deriv proposal quote recorder with active `session_id` propagation |
| **Validation Gate** | `forward_validation_gate.py` | Promotion gate requiring `RECONCILED` session status before evaluating statistical edge |
| **Operations Dashboard** | `dashboard.py` | Real-time monitoring UI adhering to 60-30-10 palette, SVG icons, and zero indicator badges |

### End-to-End Auditable Pipeline

```
[Historical Ticks Preload: CSV / Master] ──► Feature Buffer (Pre-warmed, 0 Wait)
                                                      │
[Genuine Deriv Tick: wss://api.derivws.com]           │
         │                                            │
         ├───► LiveTickStreamer ──► ForwardObserver.process_incoming_tick()
         │                               │
         │                               ├──► Rolling Feature Calculation (Parity Verified)
         │                               ├──► Model Inference (Dynamic Lookback, Frozen Checksum)
         │                               ├──► QuoteDatabase.get_latest_quote_before() (Lookahead-Free)
         │                               ├──► PersistentRiskManager.get_state()
         │                               │
         │                               ├──► ForwardPredictionJournal.log_prediction()
         │                               │       [Mandatory session_id, Immutable]
         │                               │
         │                               └──► ForwardPredictionJournal.ingest_forward_tick()
         │                                       │ (Reconstructs S0..S5 Monotonic Movement)
         │                                       └──► Writes to forward_outcomes
         │                                               [Foreign Key -> forward_predictions]
         │
         ├───► DerivQuoteRecorder ──► QuoteDatabase.store_quote() [Tagged with session_id]
         │
         └───► SessionReconciler ──► Audit Report [RECONCILED / is_verified = True]
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
├── forward_collection_service.py       # Long-running collection service with reconciliation
├── forward_journal.py                  # Prediction journal with foreign-key forward_outcomes
├── forward_observer.py                 # Forward observation orchestrator with warmup preload
├── forward_session.py                  # Session registry with authoritative lifecycle statuses
├── forward_validation_gate.py          # Promotion gate requiring RECONCILED session status
├── live_collector.py                   # Live WebSocket tick streaming and gap monitor
├── model_artifact.py                   # Frozen model schema with dynamic required_lookback
├── model_manager.py                    # Model registry, training, and holdout evaluation
├── performance_tracker.py              # Economic PnL attribution engine strictly per session
├── quote_database.py                   # SQLite proposal quote database with session filtering
├── quote_recorder.py                   # Deriv proposal quote recorder with session propagation
├── risk.py                             # SQLite-persisted risk management engine
├── run_edge_research.py                # Statistical edge analysis and hypothesis testing
├── run_forward_session.py              # Primary V1.6.3 CLI entry point with --diagnose flag
├── session_reconciler.py               # Automated session reconciliation engine
├── session_reporter.py                 # Session-specific and daily report generator
├── verify_deriv_connection.py          # WebSocket handshake and latency diagnostic
├── verify_v162_reconciliation.py       # Deterministic two-session offline reconciliation script
├── data/
│   ├── forward_predictions.db          # Persistent SQLite predictions and outcomes tables
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
│   ├── V1_6_3_COMPREHENSIVE_VALIDATION_REPORT.md # Comprehensive V1.6.3 validation report
│   ├── V1_6_2_DATA_INTEGRITY_REPORT.md
│   ├── V1_6_1_FORWARD_ACTIVATION_REPORT.md
│   └── session_*.json                  # Generated forward session audit reports
└── tests/
    ├── test_v163_integration.py        # V1.6.3 dynamic lookback, warmup & lifecycle tests
    ├── test_v162_data_integrity.py     # V1.6.2 data integrity & reconciliation tests
    ├── test_v161_forward_activation.py # V1.6.1 safety and lifecycle regression tests
    └── ...                             # 188 total passing automated unit & integration tests
```

---

## Verified Command Execution Reference

### 1. Run Complete Regression Test Suite (188 Passed)
```powershell
python -m pytest tests/ -q
```

### 2. Operational Pipeline Diagnostics Check
```powershell
python run_forward_session.py --diagnose --symbol R_75
```

### 3. Start Live Forward Observation in SHADOW Mode
```powershell
python run_forward_session.py --mode SHADOW --symbol R_75 --duration 1200
```

### 4. Verify Deriv WebSocket API Connectivity
```powershell
python verify_deriv_connection.py --symbol R_75 --timeout 6.0
```

### 5. Reconcile Any Forward Session
```powershell
python -c "from session_reconciler import SessionReconciler; r = SessionReconciler().reconcile_session('<SESSION_ID>'); print(r.summary_text()); print('Verified:', r.is_verified)"
```

### 6. Inspect Session-Specific Quotes
```powershell
python -c "from quote_database import QuoteDatabase; q = QuoteDatabase(); print(len(q.get_session_quotes('<SESSION_ID>')))"
```

### 7. Inspect Session-Specific Predictions
```powershell
python -c "from forward_journal import ForwardPredictionJournal; j = ForwardPredictionJournal('data/forward_predictions.db'); print(len(j.get_session_predictions('<SESSION_ID>')))"
```

### 8. Launch Unified Web Operations Dashboard
```powershell
python dashboard.py 8088
```
Navigate to `http://127.0.0.1:8088`.

---

## Safety Directives & Final Verdict

- **Real-Money Trading:** Permanently locked to disabled (`LIVE_EXECUTION_DISABLED = True`). Zero buy orders are submitted under any circumstances.
- **Operational Status:** `LIVE_SHADOW_PREDICTIONS_VERIFIED`. Ticks, proposal quotes, model probabilities, and forward predictions are collected, journaled, and reconciled with verified provenance.
- **Model Promotion:** Models remain `RESEARCH_ONLY`. Promotion requires Gate 0 `RECONCILED` session integrity and independent non-overlapping forward evidence exceeding the $3.277\%$ break-even hurdle with conservative positive EV.
