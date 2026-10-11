# Deriv Quantitative Research & Dual-Duration Statistical Validation Framework (V1.7.4.3)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-320%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Dual Duration](https://img.shields.io/badge/Architecture-Dual--Duration%202T%20%7C%205T-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Strategy Discovery](https://img.shields.io/badge/Strategy%20Discovery-Advisory--Only%20FWER%20Controlled-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Evidence Integrity](https://img.shields.io/badge/Evidence%20Integrity-Authoritative%20Reconciled-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Contract Spec](https://img.shields.io/badge/Contract%20Spec-Configurable%20Monotonic%20Lifecycle-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Confirmation Authority](https://img.shields.io/badge/Confirmation%20Authority-Unified%20ForwardConfirmationGate-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Reconciliation](https://img.shields.io/badge/Reconciliation-6%20Separated%20Integrity%20Dimensions-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.7.4.3%20Strict%20Provenance-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning inference, and real-market forward observation system engineered for Deriv synthetic index contracts—specifically modeling Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) on Volatility 75 (`R_75`).

V1.7.4.3 establishes complete strict quote provenance across 8 dimensions (Identity, Symbol, Currency, Duration, Direction, Causality, Freshness, Session Attribution), composite quote IDs (`QR_{session}_{proposal}_{int(ts)}`), tick-aware quote invalidation on intervening price changes, 14-dimension rejection tracking, pre-outcome timestamp causality verification, live paired dual-duration SHADOW observation on Deriv production WebSocket infrastructure, and authoritative statistical validation under the Positive-EV Evidence Ladder (Level 0 verdict: `NO_VALIDATED_POSITIVE_EV_EDGE`). Real-money live execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

---

## The Central Research Question: 2-Tick vs. 5-Tick

> **Does a two-tick contract provide more reliable, economically profitable prediction opportunities than the existing five-tick contract?**

### The Empirical Finding
**A higher winning frequency does NOT imply economic profitability.**
- **Winning Frequency**: 2-Tick contracts win approximately **25.67%** of the time (7x more frequently than 5-tick contracts at **3.63%**).
- **Payout Asymmetry**: Deriv's total payout on a $2.00 stake is **$7.63** for 2 ticks versus **$61.07** for 5 ticks.
- **The Economic Hurdle**: The break-even probability for 2 ticks is **26.212%**, which is strictly higher than both the empirical base rate (25.34%) and observed live win rates.
- **Economic Return**: The unconditional 2-tick contract produces an average loss of **-$0.0925** per $2.00 stake (-4.62% per dollar).
- **Uncertainty Lower Bound**: When dependence-aware moving-block bootstrap uncertainty is applied, both durations produce negative conservative expected values (-$2.0000 across all 4 configurations). Neither clears the authoritative confirmation hurdle.

---

## Canonical Contract Execution Lifecycles

The framework centrally supports configurable monotonic contract durations:

### 1. Two-Tick Lifecycle (2T)
```text
Signal detected at tick i
       |
Order submitted & processed
       |
Entry Spot S_0 = tick i + 1 (First tick after processing)
       |
  Step 1: S_0 -> S_1 (tick i + 2)
  Step 2: S_1 -> S_2 (tick i + 3, Expiry Spot)
```
- **RUNHIGH_2T**: Wins iff $S_0 < S_1 < S_2$ (both movements strictly increase).
- **RUNLOW_2T**: Wins iff $S_0 > S_1 > S_2$ (both movements strictly decrease).
- **Strict Equality Loss**: If $S_0 = S_1$ or $S_1 = S_2$, the contract loses.
- **Reversal Dual Loss**: If $S_0 < S_1$ and $S_1 > S_2$, both RUNHIGH and RUNLOW lose.

### 2. Five-Tick Lifecycle (5T)
```text
Signal detected at tick i
       |
Order submitted & processed
       |
Entry Spot S_0 = tick i + 1
       |
  Step 1: S_0 -> S_1 (tick i + 2)
  Step 2: S_1 -> S_2 (tick i + 3)
  Step 3: S_2 -> S_3 (tick i + 4)
  Step 4: S_3 -> S_4 (tick i + 5)
  Step 5: S_4 -> S_5 (tick i + 6, Expiry Spot)
```
- **RUNHIGH_5T**: Wins iff $S_0 < S_1 < S_2 < S_3 < S_4 < S_5$ (all 5 movements strictly increase).
- **RUNLOW_5T**: Wins iff $S_0 > S_1 > S_2 > S_3 > S_4 > S_5$ (all 5 movements strictly decrease).

---

## Research Integrity & Strict Provenance Architecture

```text
                           QUANTITATIVE INTEGRITY SYSTEM (V1.7.4.3)
                                              |
      +-------------------+-------------------+-------------------+-------------------+
      |                   |                   |                   |                   |
      v                   v                   v                   v                   v
EVIDENCE CLASSES    EVALUATION MODES     PROVENANCE ENGINE    CHRONO PARTITIONS    STATISTICAL RIGOR
+--------------+    +----------------+   +----------------+   +-----------------+  +-----------------+
|HIST_REPLAY   |    |REFERENCE_SCEN  |   |8-Dim Matching  |   |Train: 60%       |  |Monotonic BH FDR |
|HIST_HOLDOUT  |    |(0% Coverage)   |   |Tick Invalidate |   |Embargo: 3 Ticks |  |Bonferroni FWER  |
|PROSPECT_SHAD |    |QUOTE_VERIFIED  |   |14 Rejections   |   |Val: 20% (OOS BS)|  |Exact Binomial   |
|INDEP_CONFIRM |    |(Matched Quotes)|   |Composite QID   |   |Holdout: 20%     |  |MBB Seeded Boot  |
+--------------+    +----------------+   +----------------+   +-----------------+  +-----------------+
```

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── contract_specification.py                        # Canonical monotonic 2T and 5T contract specs
├── contract_model.py                                # Duration-aware contract label computer
├── feature_schema.py                                # Discrete market state classification
├── model_artifact.py                                # Model artifact serialization & SHA-256
├── model_manager.py                                 # Multi-model discovery & duration filtering
├── model_2tick.py                                   # Independent 2-tick model trainer & OOS Brier
├── probability.py                                   # Statistical distributions & Wilson score intervals
│
├── quote_recorder.py                                # Composite quote record generator & break-even computer
├── quote_database.py                                # Indexed SQLite proposal quote storage with composite IDs
├── quote_engine.py                                  # Quoting engine with dual-duration polling support
│
├── outcome_resolver.py                              # Duration-aware multi-pending outcome resolver
├── forward_journal.py                               # Pre-outcome timestamped prediction & outcome journal
├── forward_observer.py                              # PairedForwardObserver with sub-ms timestamp injection
├── forward_session.py                               # Session registry and lifecycle states
├── session_reconciler.py                            # Multi-index 6-dimension audit reconciler
├── run_forward_session.py                           # Forward research CLI runner with preflight checks
├── forward_collection_service.py                    # Live WebSocket collector with dual-duration support
│
├── decision_gate.py                                 # Centralized 11-gate paper decision gate
├── forward_confirmation_gate.py                     # Authoritative confirmation gate
├── confirmation_specification.py                    # Pre-registered confirmation manifests
├── risk.py                                          # Institutional persistent risk engine
│
├── strategy_discovery.py                            # Advisory-only hypothesis engine with Monotonic BH
├── dual_duration_research.py                        # Paired 2T vs 5T research comparison & 14-dim accounting
├── research_metrics_engine.py                       # Research metrics aggregation engine
│
├── data/
│   ├── R_75_master.csv                              # Canonical training dataset (43,184 ticks)
│   ├── R_75_live_ticks.csv                          # Live market stream (2,014 ticks)
│   ├── deriv_2t_5t_availability.json                # Reconciled live Deriv API proposal records
│   ├── forward_predictions.db                       # SQLite prediction & outcome journal
│   ├── quotes.db                                    # SQLite proposal quotes database
│   ├── sessions.db                                  # SQLite session registry
│   ├── risk_state.db                                # SQLite persistent risk limits
│   └── v1743_session_evidence.json                  # Machine-readable prospective session evidence
│
├── models/
│   ├── M_R_75_5TICK_20261008_132512.json            # Preserved authoritative 5-tick frozen model
│   └── M_R_75_2TICK_20261011_120000.json            # Preserved independent 2-tick frozen model
│
├── tests/
│   ├── test_v1743_strict_provenance_and_live_shadow.py # 16 V1.7.4.3 strict provenance & shadow tests
│   ├── test_v1742_quote_economics_and_paired_shadow.py # 16 V1.7.4.2 regression & adversarial tests
│   ├── test_v1741_integrity_and_reconciliation.py   # 14 V1.7.4.1 regression & adversarial tests
│   ├── test_v174_dual_duration_and_discovery.py     # 17 V1.7.4 regression tests
│   ├── test_v173_chronology_and_audit.py            # V1.7.3 chronology & audit tests
│   ├── test_v1721_reconciliation.py                 # V1.7.2.1 integrity & confirmation tests
│   └── ... (320 total passing tests)
│
└── Authoritative Research Reports:
    ├── V1_7_4_3_QUOTE_PROVENANCE_AUDIT.md          # 8-dimension quote provenance & rejection audit
    ├── V1_7_4_3_LIVE_SESSION_EXECUTION_REPORT.md    # 60s & 300s live paired shadow execution report
    ├── V1_7_4_3_PAIRED_FORWARD_RESULTS.md          # Paired empirical 2T vs 5T prospective results
    ├── V1_7_4_3_STRATEGY_EDGE_ASSESSMENT.md        # 6 hypothesis evaluations & Level 0 edge verdict
    ├── V1_7_4_3_EVIDENCE_INTEGRITY_REPORT.md        # Relational schema, query, and zero-orphan audit
    └── V1_7_4_3_RELEASE_VALIDATION_REPORT.md        # Release audit & package verification
```

---

## Test Suite Execution

Execute the full automated test suite:

```bash
python -m pytest -q
```

Expected result:
```text
320 passed in ~70s (100% green)
```

---

## Permanent Safety Invariants

1. **`LIVE_EXECUTION_DISABLED = True`**: Hardcoded invariant. Real-money purchases are permanently disabled across all modules.
2. **Startup Safety Preflight**: System blocks execution if any live trading environment variable (`DERIV_LIVE_EXECUTION`, `DERIV_REAL_EXECUTION`, `DERIV_ACCOUNT_TYPE=real`) is detected.
3. **No Real-Money Endpoints**: The software contains zero real-money order routing code.
4. **`IS_ADVISORY_ONLY = True`**: AI strategy discovery is locked behind an advisory firewall.
5. **Authoritative NO_TRADE**: Every observation in SHADOW mode resolves to `decision: NO_TRADE`.
6. **No Lookahead**: Strict causal timestamp enforcement: $\text{QuoteResponse} \le \text{DecisionTime}$.
7. **No Artificial Coverage**: Quotes are never presumed 100% available without timestamp verification.
