# Deriv Quantitative Research & Dual-Duration Statistical Validation Framework (V1.7.4.4)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-328%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Dual Duration](https://img.shields.io/badge/Architecture-Dual--Duration%202T%20%7C%205T-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Schema Integrity](https://img.shields.io/badge/Schema%20Integrity-Authoritative%20Adapter%20Verified-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Outcome Reconstruction](https://img.shields.io/badge/Outcome%20Reconstruction-Zero%20Discrepancies%20Audited-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Confirmation Authority](https://img.shields.io/badge/Confirmation%20Authority-Unified%20ForwardConfirmationGate-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.7.4.4%20Schema%20Integrity-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning inference, and real-market forward observation system engineered for Deriv synthetic index contracts—specifically modeling Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) on Volatility 75 (`R_75`).

V1.7.4.4 resolves the prospective evaluation database-schema mismatch by introducing a canonical record adaptation layer (`ResearchObservation`), enforcing strict 3-way outcome classification (`WIN`, `LOSS`, `UNAVAILABLE`), prohibiting synthetic zero defaults and theoretical probability fallbacks, independently reconstructing all historical live outcomes with zero discrepancies from raw ticks, recalculating authentic quote-verified economics, and conducting prospective paired SHADOW verification on Deriv production WebSocket infrastructure. Real-money live execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

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
- **Verdict**: Authoritative Positive-EV Evidence Ladder Level 0 (`NO_VALIDATED_POSITIVE_EV_EDGE`).

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

## Prospective Evidence & Schema Integrity Architecture (V1.7.4.4)

```text
                           PROSPECTIVE EVIDENCE PIPELINE (V1.7.4.4)
                                              |
       +-------------------+-------------------+-------------------+-------------------+
       |                   |                   |                   |                   |
       v                   v                   v                   v                   v
CANONICAL ADAPTER   THREE-WAY OUTCOME   PROBABILITY GUARD   RECONSTRUCTION AUDIT  PROSPECTIVE AUTHORITY
+--------------+    +----------------+  +-----------------+ +-------------------+ +---------------------+
|Typed Record  |    |WIN: 1.0        |  |Authentic [0, 1] | |Raw Tick Replay    | |Feature Cutoff       |
|runhigh_win   |    |LOSS: 0.0       |  |Preserve 0.0     | |Zero Discrepancies | |Inference Timestamp  |
|runlow_win    |    |UNAVAILABLE:    |  |Prohibit 0.25    | |Cross-Table Join   | |Journal Commit       |
|pred_prob     |    |Pending/Gaps    |  |Fallback Banned  | |Monotonic Check    | |T_feat <= T_inf <= T |
+--------------+    +----------------+  +-----------------+ +-------------------+ +---------------------+
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
├── dual_duration_research.py                        # Canonical adapter, 3-way outcomes & prospective evaluator
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
│   └── v1744_session_evidence.json                  # Sanitized machine-readable prospective evidence
│
├── models/
│   ├── M_R_75_5TICK_20261008_132512.json            # Preserved authoritative 5-tick frozen model
│   └── M_R_75_2TICK_20261011_120000.json            # Preserved independent 2-tick frozen model
│
├── tests/
│   ├── test_v1744_schema_repair_and_reconstruction.py # 8 V1.7.4.4 schema repair & regression tests
│   ├── test_v1743_strict_provenance_and_live_shadow.py # 16 V1.7.4.3 strict provenance & shadow tests
│   ├── test_v1742_quote_economics_and_paired_shadow.py # 16 V1.7.4.2 regression & adversarial tests
│   ├── test_v1741_integrity_and_reconciliation.py   # 14 V1.7.4.1 regression & adversarial tests
│   ├── test_v174_dual_duration_and_discovery.py     # 17 V1.7.4 regression tests
│   ├── test_v173_chronology_and_audit.py            # V1.7.3 chronology & audit tests
│   ├── test_v1721_reconciliation.py                 # V1.7.2.1 integrity & confirmation tests
│   └── ... (328 total passing tests)
│
└── Authoritative Research Reports:
    ├── V1_7_4_4_ROOT_CAUSE_REPORT.md                # Schema mismatch root cause analysis & audit
    ├── V1_7_4_4_INDEPENDENT_OUTCOME_AUDIT.md        # Raw-tick independent reconstruction & zero discrepancies
    ├── V1_7_4_4_CORRECTED_FORWARD_RESULTS.md        # Corrected prospective empirical results & metrics
    ├── V1_7_4_4_QUOTE_ECONOMICS_AUDIT.md            # Recalculated quote EV and retrospective returns
    ├── V1_7_4_4_STRATEGY_EDGE_ASSESSMENT.md        # Statistical edge assessment & Evidence Ladder verdict
    ├── V1_7_4_4_30_MIN_LIVE_SESSION_REPORT.md       # Live paired prospective SHADOW session audit
    └── V1_7_4_4_RELEASE_VALIDATION_REPORT.md        # Release audit & package verification
```

---

## Test Suite Execution

Execute the full automated test suite:

```bash
python -m pytest -q
```

Expected result:
```text
328 passed in ~73s (100% green)
```

---

## Permanent Safety Invariants

1. **`LIVE_EXECUTION_DISABLED = True`**: Hardcoded invariant. Real-money purchases are permanently disabled across all modules.
2. **Startup Safety Preflight**: System blocks execution if any live trading environment variable (`DERIV_LIVE_EXECUTION`, `DERIV_REAL_EXECUTION`, `DERIV_ACCOUNT_TYPE=real`) is detected.
3. **No Real-Money Endpoints**: The software contains zero real-money order routing code.
4. **`IS_ADVISORY_ONLY = True`**: AI strategy discovery is locked behind an advisory firewall.
5. **Authoritative NO_TRADE**: Every observation in SHADOW mode resolves to `decision: NO_TRADE`.
6. **Strict 3-Way Outcomes**: Missing or unresolved outcomes are marked `UNAVAILABLE` and never coerced to losses.
7. **No Fallback Probabilities**: Model probabilities must be authentic floating-point values; random-walk fallbacks are prohibited.
