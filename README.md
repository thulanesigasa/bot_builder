# Deriv 5-Tick Quantitative Research & Statistical Validation Framework (V1.7.1)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Testing](https://img.shields.io/badge/pytest-221%20passed%20(100%25)-0284C7)
![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)
![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)
![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)
![Confirmation Gate](https://img.shields.io/badge/Confirmation%20Gate-13--Category%20Authoritative%20AND%20Logic-0284C7)
![Manifest Integrity](https://img.shields.io/badge/Manifest-Pre--Registered%20SHA--256%20Frozen-0284C7)
![Statistical Evaluator](https://img.shields.io/badge/Statistics-Brier%20Skill%20%7C%20ECE%20%7C%20Block%20Bootstrap-0284C7)
![Economic Evaluator](https://img.shields.io/badge/Economics-Proposal%20Hurdle%20%7C%20Conservative%20EV-0284C7)
![Research Aggregator](https://img.shields.io/badge/Research-Stage%20Segregation%20(Exploratory%2FVal%2FConf)-0284C7)
![Reconciliation](https://img.shields.io/badge/Reconciliation-6--Dimension%20Automated%20Engine-0284C7)
![Architecture](https://img.shields.io/badge/Architecture-V1.7.1%20Confirmation%20Gate%20Hardening-0284C7)

A rigorous quantitative research, frozen model inference, and real-market forward observation system engineered for Deriv 5-tick contracts—specifically modeling RUNHIGH (Only Ups) and RUNLOW (Only Downs) where every successive tick after the entry spot must move strictly in the contract direction.

V1.7.1 hardens the statistical confirmation gate, permanently eliminates benchmark payout fallbacks (`3.277%`), establishes pre-registered cryptographically signed confirmation manifests, and enforces 13 independent categories linked by strict AND logic before any model can receive edge confirmation.

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
- **Data Gap Sequences**: If elapsed time between consecutive ticks during observation exceeds $5.0\text{s}$, classified as `OUTCOME_DATA_GAP` and excluded from win-rate metrics.

---

## Empirical Baseline vs Genuine Proposal Hurdle

The engine does not assume theoretical random-walk probability ($3.125\%$). It computes the empirical baseline from historical observations:

$$\text{Theoretical Reference} = (0.5)^5 = 0.03125 = 3.125\%$$

$$\text{Deriv Live Proposal Hurdle (\$2.00 Stake } \to \text{\$61.03 Total Payout)} = \frac{\$2.00}{\$61.03} \approx 3.277\%$$

Empirical results on Volatility 75 (`R_75`, canonical historical dataset):
- **Empirical $P(\text{RUNHIGH})$**: $3.275\%$ ($SE = 0.0009$, $95\%$ Wald CI: $[3.107\%, 3.443\%]$)
- **Empirical $P(\text{RUNLOW})$**: $2.971\%$ ($SE = 0.0008$, $95\%$ Wald CI: $[2.811\%, 3.132\%]$)

---

## V1.7.1 Core Architecture & Pipeline Components

| Component | File | Role |
|---|---|---|
| **Confirmation Manifest** | `confirmation_specification.py` | Pre-registered, canonical JSON SHA-256 hashed confirmation criteria and parameter manifests |
| **Confirmation Gate** | `forward_confirmation_gate.py` | Authoritative forward edge confirmation gate enforcing 13 mandatory categories via strict AND logic |
| **Statistical Evaluator** | `statistical_evaluator.py` | Wilson CIs, Brier Score, Brier Skill Score, rare-event ECE, moving block bootstrap ($L=5$), effective sample size ($N_{\text{eff}}$), non-overlapping subsampling, conditional lift |
| **Economic Evaluator** | `economic_evaluator.py` | Break-even hurdle ($P_{\text{be}} = \text{Ask}/\text{Payout}$), Ordinary EV, Conservative EV (strictly requires lower bound), hypothetical PnL/drawdown, pricing stress analysis |
| **Research Aggregator** | `session_research_aggregator.py` | Multi-session stage aggregator with hardened absent-session handling and 0% benchmark fallbacks |
| **Outcome Resolver** | `outcome_resolver.py` | Dedicated multi-pending outcome resolution tracking consecutive inter-tick gaps and full 6-tick sequences ($S_0 \to S_5$) |
| **Forward Observer** | `forward_observer.py` | Feature buffer, historical warmup anchored strictly before first live tick, prediction cutoff controls |
| **Collection Service** | `forward_collection_service.py` | Sustained WebSocket collection service, auto-reconnect, target prediction milestones, research stage tagging |
| **Session Launcher** | `run_forward_session.py` | Operational CLI launcher supporting extended duration, `--stage`, and `--target-resolved` milestones |
| **Session Reconciler** | `session_reconciler.py` | 6-dimension automated audit engine verifying provenance, ticks, quotes, and outcome chronology |
| **Session Registry** | `forward_session.py` | Authoritative lifecycle transitions, research stage tracking, tick breakdown accounting |
| **Prediction Journal** | `forward_journal.py` | Integrated `OutcomeResolver`, immutable prediction logging, dedicated `forward_outcomes` table |
| **Model Artifact** | `model_artifact.py` | Frozen model schema with dynamic `required_lookback`, cryptographic checksum, and inference |
| **Model Promotion Gate** | `forward_validation_gate.py` | Promotion gate requiring independent confirmation pass before authorizing paper execution |
| **Quote Database** | `quote_database.py` | SQLite proposal quote persistence strictly linked and queried by `session_id` |
| **Quote Recorder** | `quote_recorder.py` | Deriv proposal quote recorder with active `session_id` propagation |
| **Risk Engine** | `risk.py` | Persistent SQLite risk state tracking and NO_TRADE enforcement |
| **Operations Dashboard** | `dashboard.py` | Web monitoring UI with V1.7.1 Authoritative Confirmation Gate panel (60-30-10 palette, SVG only) |

### End-to-End Auditable Pipeline

```
[Historical Ticks Preload: CSV / Master] ──► Anchored Strictly Preceding First Live Tick
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
         │                               └──► OutcomeResolver.ingest_tick()
         │                                       │ (Consecutive Tick Gaps Checked vs last_epoch)
         │                                       │ (Reconstructs S0..S5 Monotonic Movement)
         │                                       └──► Writes to forward_outcomes
         │                                               [Foreign Key -> forward_predictions]
         │
         ├───► DerivQuoteRecorder ──► QuoteDatabase.store_quote() [Tagged with session_id]
         │
         ├───► SessionReconciler ──► Audit Report [RECONCILED / is_verified = True]
         │
         ├───► ConfirmationManifest ──► Cryptographic Criteria Freezing (Canonical SHA-256)
         │
         └───► ForwardConfirmationGate ──► Authoritative 13-Gate AND Logic Evaluation
```

---

## Directory Structure

```
bot_builder/
├── .env.example                                  # Environment variables template
├── .gitignore                                    # Git ignore specification (.agents protected)
├── README.md                                     # Architectural documentation and CLI reference
├── confirmation_specification.py                 # Pre-registered SHA-256 confirmation manifests
├── contract_lifecycle.py                         # Canonical 5-tick contract execution model
├── dashboard.py                                  # Web dashboard (60-30-10 palette, SVG only)
├── decision_gate.py                              # Centralized multi-gate eligibility engine
├── economic_evaluator.py                         # Genuine proposal EV, break-even hurdles, stress tests
├── feature_schema.py                             # Canonical feature extraction schema
├── forward_collection_service.py                 # Long-running collection service with milestones & stages
├── forward_confirmation_gate.py                  # Authoritative 13-condition confirmation gate
├── forward_journal.py                            # Prediction journal delegating to OutcomeResolver
├── forward_observer.py                           # Forward observation orchestrator with anchored warmup
├── forward_session.py                            # Session registry with research stage tracking
├── forward_validation_gate.py                    # Promotion gate requiring RECONCILED session status
├── health_monitor.py                             # Process and network health diagnostics
├── live_collector.py                             # Live WebSocket tick streaming and gap monitor
├── model_artifact.py                             # Frozen model schema with dynamic required_lookback
├── model_manager.py                              # Model registry, training, and holdout evaluation
├── outcome_resolver.py                           # Multi-pending outcome tracking & canonical resolution
├── performance_tracker.py                        # Economic PnL attribution engine strictly per session
├── quote_database.py                             # SQLite proposal quote database with session filtering
├── quote_recorder.py                             # Deriv proposal quote recorder with session propagation
├── risk.py                                       # SQLite-persisted risk management engine
├── run_edge_research.py                          # Statistical edge analysis and hypothesis testing
├── run_forward_session.py                        # Operational V1.7.1 CLI launcher with stage & target flags
├── session_reconciler.py                         # Automated session reconciliation engine
├── session_reporter.py                           # Session-specific and daily report generator with V1.7.1 metrics
├── session_research_aggregator.py                # Multi-session stage aggregator & authoritative verdicts
├── statistical_evaluator.py                      # Calibration, BSS, rare-event ECE, bootstrap, Neff
├── verify_deriv_connection.py                    # WebSocket handshake and latency diagnostic
├── verify_v162_reconciliation.py                 # Deterministic two-session offline reconciliation script
├── data/
│   ├── forward_predictions.db                    # Persistent SQLite predictions and outcomes tables
│   ├── quotes.db                                 # Persistent SQLite proposal quotes database
│   ├── risk_state.db                             # Persistent SQLite risk state database
│   ├── sessions.db                               # Persistent SQLite forward sessions database
│   ├── validation_gate.db                        # Model promotion and audit trail database
│   ├── R_75_master.csv                           # Canonical historical tick dataset
│   └── quarantine/
│       ├── .gitkeep
│       └── quarantine_log.json
├── models/
│   └── M_R_75_5TICK_20261008_132512.json           # Frozen baseline research model artifact
├── reports/
│   ├── V1_7_1_CONFIRMATION_AND_FORWARD_EVIDENCE_REPORT.md # Comprehensive V1.7.1 validation report
│   ├── V1_7_FORWARD_STATISTICAL_VALIDATION_REPORT.md # Comprehensive V1.7 validation report
│   ├── V1_6_4_FORWARD_OUTCOME_VALIDATION_REPORT.md   # Comprehensive V1.6.4 validation report
│   └── session_*.json                            # Generated forward session audit reports
└── tests/
    ├── test_v171_confirmation_hardening.py       # V1.7.1 manifest, cases A-F, benchmark fallback removal
    ├── test_v17_statistical_validation.py        # V1.7 calibration, dependence, economics & stages
    ├── test_v164_outcome_resolution.py           # V1.6.4 outcome resolver, gap fix & e2e acceptance
    ├── test_v163_integration.py                  # V1.6.3 dynamic lookback, warmup & lifecycle tests
    ├── test_v162_data_integrity.py               # V1.6.2 data integrity & reconciliation tests
    ├── test_v161_forward_activation.py           # V1.6.1 safety and lifecycle regression tests
    └── ...                                       # 221 total passing automated unit & integration tests
```

---

## Verified Command Execution Reference

### 1. Run Complete Regression Test Suite (221 Passed)
```powershell
python -m pytest tests/ -v
```

### 2. Run V1.7.1 Confirmation Gate Hardening Tests
```powershell
python -m pytest tests/test_v171_confirmation_hardening.py -v
```

### 3. Pre-Register and Freeze Confirmation Manifest
```powershell
python -c "from confirmation_specification import ConfirmationManifest; m = ConfirmationManifest.create_default_for_model('M_R_75_5TICK', 'sha256_model_hash', 'R_75'); m.save_to_file('data/manifest_r75_v171.json'); print('Frozen manifest checksum:', m.specification_checksum)"
```

### 4. Start Live Forward Observation Session with Stage and Target
```powershell
python run_forward_session.py --mode SHADOW --symbol R_75 --duration 3600 --stage CONFIRMATION_FORWARD --target-resolved 1000
```

### 5. Verify Deriv WebSocket API Connectivity
```powershell
python verify_deriv_connection.py --symbol R_75 --timeout 6.0
```

### 6. Evaluate Authoritative Confirmation Gate
```powershell
python -c "from forward_confirmation_gate import evaluate_forward_edge_confirmation; rep = evaluate_forward_edge_confirmation('R_75', 'M_R_75_5TICK'); print('Verdict:', rep.verdict); print('Confirmed:', rep.is_confirmed)"
```

### 7. Generate Multi-Session Research Report
```powershell
python -c "from session_research_aggregator import SessionResearchAggregator; agg = SessionResearchAggregator(); print(agg.generate_markdown_report('R_75'))"
```

### 8. Launch Unified Web Operations Dashboard
```powershell
python dashboard.py 8088
```
Navigate to `http://127.0.0.1:8088`.

---

## Safety Directives & Final Verdict

- **Real-Money Trading:** Permanently locked to disabled (`LIVE_EXECUTION_DISABLED = True`). Zero buy orders are submitted under any circumstances.
- **Operational Status:** `DATA_COLLECTION_READY`. The software infrastructure is fully validated, auditable, and ready for extended forward observation.
- **Research Verdict:** `NO_CONFIRMATION_SESSIONS`. Zero independent sessions have been registered under `CONFIRMATION_FORWARD` stage. The platform honestly reports absent confirmation studies as `NO_CONFIRMATION_SESSIONS` with null financial metrics, eliminating premature edge declarations and benchmark fallbacks.
