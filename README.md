# Deriv Quantitative Research & Dual-Duration Statistical Validation Framework (V1.7.4.1)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-288%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Dual Duration](https://img.shields.io/badge/Architecture-Dual--Duration%202T%20%7C%205T-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Strategy Discovery](https://img.shields.io/badge/Strategy%20Discovery-Advisory--Only%20FWER%20Controlled-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Evidence Integrity](https://img.shields.io/badge/Evidence%20Integrity-Authoritative%20Reconciled-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Contract Spec](https://img.shields.io/badge/Contract%20Spec-Configurable%20Monotonic%20Lifecycle-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Confirmation Authority](https://img.shields.io/badge/Confirmation%20Authority-Unified%20ForwardConfirmationGate-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Reconciliation](https://img.shields.io/badge/Reconciliation-6%20Separated%20Integrity%20Dimensions-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.7.4.1%20Research%20Integrity-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning inference, and real-market forward observation system engineered for Deriv synthetic index contracts—specifically modeling Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) on Volatility 75 (`R_75`).

V1.7.4.1 establishes surgical research-integrity corrections: granular multi-tier quote coverage, separation of reference scenario payouts from verified quotes, strict conservative EV hurdles ($\ge 0.0$), small-sample bootstrap protection, explicit evidence classes, chronological 60/20/20 train/val/holdout partitions with 3-tick embargoes, out-of-sample Brier scoring, monotonic Benjamini-Hochberg FDR control, exact binomial survival, and complete provenance reconciliation. Real-money live execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

---

## The Central Research Question: 2-Tick vs. 5-Tick

> **Does a two-tick contract provide more reliable, economically profitable prediction opportunities than the existing five-tick contract?**

### The Empirical Finding
**A higher winning frequency does NOT imply economic profitability.**
- **Winning Frequency**: 2-Tick contracts win approximately **25.67%** of the time (7x more frequently than 5-tick contracts at **3.63%**).
- **Payout Asymmetry**: Deriv's total payout on a $2.00 stake is **$7.63** for 2 ticks versus **$61.07** for 5 ticks.
- **The Economic Hurdle**: The break-even probability for 2 ticks is **26.212%**, which is strictly higher than both the empirical base rate (25.34%) and the observed live win rate (25.67%).
- **Economic Return**: The unconditional 2-tick contract produces an average loss of **-$0.0667** per $2.00 stake.
- **Uncertainty Lower Bound**: When dependence-aware moving-block bootstrap uncertainty is applied, both durations produce negative conservative expected values (-$0.1918 for 2T, -$0.3370 for 5T). Neither clears the authoritative confirmation hurdle.

---

## Canonical Contract Execution Lifecycles

The framework centrally supports configurable monotonic contract durations:

### 1. Two-Tick Lifecycle (2T)
```
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
```
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

## V1.7.4.1 Research Integrity Architecture

```
                          QUANTITATIVE INTEGRITY SYSTEM
                                        │
      ┌──────────────────┬──────────────┴──────────────┬──────────────────┐
      ▼                  ▼                             ▼                  ▼
EVIDENCE CLASSES    EVALUATION MODES            CHRONO PARTITIONS    STATISTICAL RIGOR
┌──────────────┐   ┌───────────────────────┐   ┌─────────────────┐  ┌─────────────────┐
│HIST_REPLAY   │   │REFERENCE_SCENARIO     │   │Train: 60%       │  │Monotonic BH FDR │
│HIST_HOLDOUT  │   │(0% Quote Coverage)    │   │Embargo: 3 Ticks │  │Bonferroni FWER  │
│PROSPECT_SHAD │   │QUOTE_VERIFIED         │   │Val: 20% (OOS BS)│  │Exact Binomial   │
│INDEP_CONFIRM │   │(Real Matched Quotes)  │   │Holdout: 20%     │  │MBB Seeded Boot  │
└──────────────┘   └───────────────────────┘   └─────────────────┘  └─────────────────┘
```

---

## Directory Structure

```
bot_builder/
├── config.py                                        # Global application configuration
├── contract_specification.py                        # Canonical monotonic 2T and 5T contract specs
├── contract_model.py                                # Duration-aware contract label computer
├── feature_schema.py                                # Discrete market state classification
├── model_artifact.py                                # Model artifact serialization & SHA-256
├── model_manager.py                                 # Multi-model discovery & duration filtering
├── model_2tick.py                                   # Independent 2-tick model trainer & OOS Brier
├── probability.py                                   # Statistical distributions & Wilson score intervals
│
├── quote_recorder.py                                # Deriv proposal quote recorder
├── quote_database.py                                # Indexed SQLite proposal quote storage
├── quote_engine.py                                  # Quoting engine with duration support
│
├── outcome_resolver.py                              # Duration-aware multi-pending outcome resolver
├── forward_journal.py                               # Immutable forward prediction journal
├── forward_observer.py                              # Live stream observer and sliding buffer
├── forward_session.py                               # Session registry and lifecycle states
├── session_reconciler.py                            # 6-dimension audit reconciler
├── run_forward_session.py                           # Forward research CLI runner
│
├── decision_gate.py                                 # Centralized 11-gate paper decision gate
├── forward_confirmation_gate.py                     # Authoritative confirmation gate
├── confirmation_specification.py                    # Pre-registered confirmation manifests
├── risk.py                                          # Institutional persistent risk engine
│
├── strategy_discovery.py                            # Advisory-only hypothesis engine with Monotonic BH
├── dual_duration_research.py                        # Paired 2T vs 5T research comparison engine
├── research_metrics_engine.py                       # Research metrics aggregation engine
│
├── data/
│   ├── R_75_master.csv                              # Canonical training dataset (43,184 ticks)
│   ├── R_75_live_ticks.csv                          # Live market stream (2,014 ticks)
│   ├── deriv_2t_5t_availability.json                # Reconciled live Deriv API proposal records
│   ├── forward_predictions.db                       # SQLite prediction & outcome journal
│   ├── quotes.db                                    # SQLite proposal quotes database
│   ├── sessions.db                                  # SQLite session registry
│   └── risk_state.db                                # SQLite persistent risk limits
│
├── models/
│   ├── M_R_75_5TICK_20261008_132512.json            # Preserved authoritative 5-tick frozen model
│   └── M_R_75_2TICK_20261011_120000.json            # Independent 2-tick chronological frozen model
│
├── tests/
│   ├── test_v1741_integrity_and_reconciliation.py   # 14 new V1.7.4.1 regression & adversarial tests
│   ├── test_v174_dual_duration_and_discovery.py     # 17 V1.7.4 regression tests
│   ├── test_v173_chronology_and_audit.py            # V1.7.3 chronology & audit tests
│   ├── test_v1721_reconciliation.py                 # V1.7.2.1 integrity & confirmation tests
│   └── ... (288 total passing tests)
│
└── Authoritative Research Reports:
    ├── V1_7_4_1_ROOT_CAUSE_AUDIT.md                 # Complete defect audit & surgical corrections
    ├── V1_7_4_1_QUOTE_ECONOMICS_REPORT.md           # Separation of reference vs quote-verified economics
    ├── V1_7_4_1_MODEL_VALIDATION_REPORT.md          # Chronological partitions & OOS holdout evaluation
    ├── V1_7_4_1_DUAL_DURATION_EVIDENCE_REPORT.md    # Evidence classification & empirical comparison
    ├── V1_7_4_1_STRATEGY_DISCOVERY_AUDIT.md         # Multiple-testing corrections & exact binomials
    └── V1_7_4_1_RELEASE_VALIDATION_REPORT.md        # Release audit & package verification
```

---

## Test Suite Execution

Execute the full automated test suite:

```bash
python -m pytest -q
```

Expected result:
```
288 passed in ~60s (100% green)
```

---

## Permanent Safety Invariants

1. **`LIVE_EXECUTION_DISABLED = True`**: Hardcoded invariant. Real-money purchases are permanently disabled across all modules.
2. **No Real-Money Endpoints**: The software contains zero real-money order routing code.
3. **`IS_ADVISORY_ONLY = True`**: AI strategy discovery is locked behind an advisory firewall.
4. **Authoritative NO_TRADE**: Every observation in SHADOW mode resolves to `decision: NO_TRADE`.
5. **No Lookahead**: Strict causal timestamp enforcement: $\text{QuoteResponse} \le \text{DecisionTime}$.
6. **No Artificial Coverage**: Quotes are never presumed 100% available without timestamp verification.
