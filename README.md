# Deriv 5-Tick Quantitative Research & Statistical Validation Framework (V1.7.3)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Testing](https://img.shields.io/badge/pytest-257%20passed%20(100%25)-0284C7)
![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)
![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)
![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)
![Quote Chronology](https://img.shields.io/badge/Quote%20Chronology-Strict%200.0s%20Tolerance-0284C7)
![Contract Spec](https://img.shields.io/badge/Contract%20Spec-Canonical%205--Movement%20Monotonic-0284C7)
![Quote Coverage](https://img.shields.io/badge/Quote%20Coverage-4%20Distinct%20Categories-0284C7)
![Confirmation Authority](https://img.shields.io/badge/Confirmation%20Authority-Unified%20ForwardConfirmationGate-0284C7)
![Reconciliation](https://img.shields.io/badge/Reconciliation-6%20Separated%20Integrity%20Dimensions-0284C7)
![Architecture](https://img.shields.io/badge/Architecture-V1.7.3%20Strict%20Chronology%20%26%20Settlement-0284C7)

A rigorous quantitative research, frozen model inference, and real-market forward observation system engineered for Deriv 5-tick contracts—specifically modeling RUNHIGH (Only Ups) and RUNLOW (Only Downs) where every successive tick after the entry spot must move strictly in the contract direction.

V1.7.3 establishes strict causal quote chronology (0.0s future-quote allowance eliminated), taxonomic quote rejection reasons, canonical 5-movement contract outcome specification (`contract_specification.py`), 6 separated reconciliation integrity dimensions, and 4 distinct quote coverage categories. Real-money live execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

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
- **Dual Loss Reality**: In oscillating sequences, both RUNHIGH and RUNLOW lose simultaneously (~93.75% theoretical non-monotonic rate). RUNLOW is never inferred from RUNHIGH ($RUNLOW \neq 1 - RUNHIGH$).
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

## V1.7.2 Core Architecture & Pipeline Components

| Component | File | Role |
|---|---|---|
| **Research Metrics Engine** | `research_metrics_engine.py` | Canonical single-source data-analysis interface, referential SQLite joins, directional independence, SHA-256 integrity checksums |
| **Confirmation Gate** | `forward_confirmation_gate.py` | Single authoritative confirmed-edge decision gate enforcing 13 mandatory categories via strict AND logic |
| **Confirmation Manifest** | `confirmation_specification.py` | Pre-registered, canonical JSON SHA-256 hashed confirmation criteria and parameter manifests |
| **Statistical Evaluator** | `statistical_evaluator.py` | Wilson CIs, Brier Score, Brier Skill Score, rare-event ECE, moving block bootstrap ($L=5$), effective sample size ($N_{\text{eff}}$) |
| **Economic Evaluator** | `economic_evaluator.py` | Break-even hurdle ($P_{\text{be}} = \text{Ask}/\text{Payout}$), Ordinary EV, Conservative EV (strictly requires lower bound), hypothetical PnL/drawdown |
| **Research Aggregator** | `session_research_aggregator.py` | Multi-session stage aggregator delegating all confirmation decisions strictly to `ForwardConfirmationGate` |
| **Outcome Resolver** | `outcome_resolver.py` | Dedicated multi-pending outcome resolution tracking consecutive inter-tick gaps and full 6-tick sequences ($S_0 \to S_5$) |
| **Forward Observer** | `forward_observer.py` | Feature buffer, historical warmup anchored strictly before first live tick, prediction cutoff controls |
| **Collection Service** | `forward_collection_service.py` | Sustained WebSocket collection service, auto-reconnect, target prediction milestones, research stage admission enforcement |
| **Session Launcher** | `run_forward_session.py` | Operational CLI launcher supporting extended duration, `--stage`, `--manifest`, and `--target-resolved` milestones |
| **Session Reconciler** | `session_reconciler.py` | 6-dimension automated audit engine verifying provenance, ticks, quotes, and outcome chronology |
| **Session Registry** | `forward_session.py` | Authoritative lifecycle transitions, mandatory confirmation admission validation, immutable stage enforcement |
| **Prediction Journal** | `forward_journal.py` | Integrated `OutcomeResolver`, immutable prediction logging, dedicated `forward_outcomes` table |
| **Model Artifact** | `model_artifact.py` | Frozen model schema with dynamic `required_lookback`, cryptographic checksum, and inference |
| **Model Promotion Gate** | `forward_validation_gate.py` | Promotion gate requiring independent confirmation pass before authorizing paper execution |
| **Quote Database** | `quote_database.py` | SQLite proposal quote persistence strictly linked and queried by `session_id` |
| **Quote Recorder** | `quote_recorder.py` | Deriv proposal quote recorder with active `session_id` propagation |
| **Risk Engine** | `risk.py` | Persistent SQLite risk state tracking and NO_TRADE enforcement |
| **Operations Dashboard** | `dashboard.py` | Web monitoring UI consuming `ResearchMetricsEngine` with dataset checksum display (60-30-10 palette, SVG only) |

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
         ├───► ResearchMetricsEngine ──► Canonical Directional Metrics & SHA-256 Checksum
         │
         ├───► ConfirmationManifest ──► Cryptographic Criteria Freezing (Canonical SHA-256)
         │
         └───► ForwardConfirmationGate ──► Sole Authoritative Confirmation Decision (13 Mandatory Gates)
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
├── dashboard.py                                  # Web dashboard (60-30-10 palette, SVG only, argparse CLI)
├── decision_gate.py                              # Centralized multi-gate eligibility engine
├── economic_evaluator.py                         # Genuine proposal EV, break-even hurdles, stress tests
├── feature_schema.py                             # Canonical feature extraction schema
├── forward_collection_service.py                 # Long-running collection service with milestones & admission
├── forward_confirmation_gate.py                  # Single authoritative 13-condition confirmation gate
├── forward_journal.py                            # Prediction journal delegating to OutcomeResolver
├── forward_observer.py                           # Forward observation orchestrator with anchored warmup
├── forward_session.py                            # Session registry with immutable stages & admission checks
├── forward_validation_gate.py                    # Promotion gate requiring RECONCILED session status
├── health_monitor.py                             # Process and network health diagnostics
├── live_collector.py                             # Live WebSocket tick streaming and gap monitor
├── model_artifact.py                             # Frozen model schema with dynamic required_lookback
├── model_manager.py                              # Model registry, training, and holdout evaluation
├── outcome_resolver.py                           # Multi-pending outcome tracking & canonical resolution
├── performance_tracker.py                        # Economic PnL attribution engine strictly per session
├── quote_database.py                             # SQLite proposal quote database with session filtering
├── quote_recorder.py                             # Deriv proposal quote recorder with session propagation
├── research_metrics_engine.py                    # Canonical data analysis engine with SHA-256 integrity checksums
├── risk.py                                       # SQLite-persisted risk management engine
├── run_edge_research.py                          # Statistical edge analysis and hypothesis testing
├── run_forward_session.py                        # Operational V1.7.2 CLI launcher with --manifest admission
├── session_reconciler.py                         # Automated session reconciliation engine
├── session_reporter.py                           # Session and daily report generator with argparse CLI
├── session_research_aggregator.py                # Multi-session stage aggregator delegating to gate
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
│   ├── V1_7_2_RESEARCH_INTEGRITY_AND_CONFIRMATION_REPORT.md # Comprehensive V1.7.2 audit report
│   ├── V1_7_1_CONFIRMATION_AND_FORWARD_EVIDENCE_REPORT.md # Historical V1.7.1 validation report
│   ├── V1_7_FORWARD_STATISTICAL_VALIDATION_REPORT.md # Historical V1.7 validation report
│   ├── V1_6_4_FORWARD_OUTCOME_VALIDATION_REPORT.md   # Historical V1.6.4 validation report
│   └── session_*.json                            # Generated forward session audit reports
└── tests/
    ├── test_v172_research_integrity.py           # V1.7.2 Defect A-D regression, bypass and admission tests
    ├── test_v171_confirmation_hardening.py       # V1.7.1 manifest, cases A-F, benchmark fallback removal
    ├── test_v17_statistical_validation.py        # V1.7 calibration, dependence, economics & stages
    ├── test_v164_outcome_resolution.py           # V1.6.4 outcome resolver, gap fix & e2e acceptance
    ├── test_v163_integration.py                  # V1.6.3 dynamic lookback, warmup & lifecycle tests
    ├── test_v162_data_integrity.py               # V1.6.2 data integrity & reconciliation tests
    ├── test_v161_forward_activation.py           # V1.6.1 safety and lifecycle regression tests
    └── ...                                       # 232 total passing automated unit & integration tests
```

---

## Verified Command Execution Reference

### 1. Run Complete Regression Test Suite (232 Passed)
```powershell
python -m pytest tests/ -v
```

### 2. Run V1.7.2 Research Integrity & Confirmation Gate Tests
```powershell
python -m pytest tests/test_v172_research_integrity.py -v
```

### 3. Run Pipeline Diagnostics Without Streaming
```powershell
python run_forward_session.py --diagnose --symbol R_75
```

### 4. Run Bounded Live Smoke Test (30 seconds)
```powershell
python run_forward_session.py --symbol R_75 --duration 30 --smoke-test
```

### 5. Pre-Register and Freeze Confirmation Manifest
```powershell
python -c "from confirmation_specification import ConfirmationManifest; m = ConfirmationManifest.create_default_for_model('M_R_75_5TICK', 'sha256_model_hash', 'R_75'); m.save_to_file('data/manifest_r75_v172.json'); print('Frozen manifest checksum:', m.specification_checksum)"
```

### 6. Start Authorized Confirmation Session (Admission Enforced)
```powershell
python run_forward_session.py --mode SHADOW --symbol R_75 --duration 3600 --stage CONFIRMATION --manifest data/manifest_r75_v172.json --target-resolved 500
```

### 7. Verify Deriv WebSocket API Connectivity
```powershell
python verify_deriv_connection.py --symbol R_75 --timeout 6.0
```

### 8. Compute Canonical Research Metrics and Checksum
```powershell
python -c "from research_metrics_engine import ResearchMetricsEngine; eng = ResearchMetricsEngine(); m = eng.compute_metrics('R_75'); print('RH Wins:', m.runhigh.wins, 'RL Wins:', m.runlow.wins, 'Dual Losses:', m.both_lost_count, 'Checksum:', m.integrity_checksum)"
```

### 9. Evaluate Authoritative Confirmation Gate
```powershell
python -c "from forward_confirmation_gate import evaluate_forward_edge_confirmation; rep = evaluate_forward_edge_confirmation('R_75', 'M_R_75_5TICK'); print('Verdict:', rep.verdict); print('Confirmed:', rep.is_confirmed)"
```

### 10. Generate Session and Daily Reports
```powershell
# Daily report
python session_reporter.py R_75

# Session report
python session_reporter.py R_75 --session <session_id>
```

### 11. Launch Web Operations Dashboard
```powershell
python dashboard.py --port 8088
```
Navigate to `http://127.0.0.1:8088`.

---

## Authoritative V1.7.3 Quantitative Audit & Validation Package

The following reports document the V1.7.3 mathematical verification and causal audit:
- [V1_7_3_QUOTE_CHRONOLOGY_AUDIT.md](file:///d:/workspace_programming/bot_builder/V1_7_3_QUOTE_CHRONOLOGY_AUDIT.md): Causal quote availability audit, zero future quotes, root cause analysis of Deriv proposal ID reuse, and 4 distinct quote coverage metrics.
- [V1_7_3_CONTRACT_OUTCOME_AUDIT.md](file:///d:/workspace_programming/bot_builder/V1_7_3_CONTRACT_OUTCOME_AUDIT.md): Official Deriv documentation references, canonical 5-movement monotonic contract definition, and 0-discrepancy raw tick re-computation.
- [V1_7_3_FORWARD_EVIDENCE_REPORT.md](file:///d:/workspace_programming/bot_builder/V1_7_3_FORWARD_EVIDENCE_REPORT.md): Recomputed probability calibration, dependence-aware block-bootstrap uncertainty ($0.52\%$ lower bound), genuine quote-based EV, and 0 PAPER approvals.
- [V1_7_3_RELEASE_VALIDATION_REPORT.md](file:///d:/workspace_programming/bot_builder/V1_7_3_RELEASE_VALIDATION_REPORT.md): Complete test suite results (257 passing tests), clean ZIP extraction verification, and operational readiness.

## Controlled Forward Research Evidence Package

The following authoritative reports document the live operational execution and statistical audit of session `413bbee4`:
- [FORWARD_SESSION_EXECUTION_REPORT.md](file:///d:/workspace_programming/bot_builder/FORWARD_SESSION_EXECUTION_REPORT.md): Live WebSocket streaming, 145 ticks, 134 predictions, 129 resolved outcomes, and graceful shutdown lifecycle.
- [SESSION_DATA_INTEGRITY_REPORT.md](file:///d:/workspace_programming/bot_builder/SESSION_DATA_INTEGRITY_REPORT.md): Referential database audit across all 8 sessions, 1,897 predictions, zero chronology errors, and independent win/loss accounting.
- [FORWARD_PROBABILITY_REPORT.md](file:///d:/workspace_programming/bot_builder/FORWARD_PROBABILITY_REPORT.md): Frozen-model calibration, moving-block bootstrap (Block L=5), effective sample size $N_{\text{eff}} = 96.45$, and empirical win rates.
- [QUOTE_BASED_EV_REPORT.md](file:///d:/workspace_programming/bot_builder/QUOTE_BASED_EV_REPORT.md): Live broker proposal quotes ($2.00 stake $\to$ $61.07 payout), break-even hurdle ($3.275\%$), conservative EV (-$0.29), and risk filtering.
- [NEXT_COLLECTION_PLAN.md](file:///d:/workspace_programming/bot_builder/NEXT_COLLECTION_PLAN.md): Multi-session phased collection roadmap, statistical power targets, and manifest pre-registration protocols.

---

## Safety Directives & Final Verdict

- **Real-Money Trading:** Permanently locked to disabled (`LIVE_EXECUTION_DISABLED = True`). Zero buy orders are submitted under any circumstances.
- **Operational Status:** `LIVE_COLLECTION_VERIFIED`. The software infrastructure has been empirically verified under live WebSocket streaming and is operationally ready for multi-session forward research.
- **Research Verdict:** `NO_CONFIRMATION_SESSIONS` / `INSUFFICIENT_FORWARD_EVIDENCE`. Zero independent sessions have been registered under `CONFIRMATION_FORWARD` stage. The platform honestly reports absent confirmation studies as `NO_CONFIRMATION_SESSIONS` with null financial metrics, eliminating premature edge declarations and false win rates.
