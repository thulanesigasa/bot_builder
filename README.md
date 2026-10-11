# Deriv Quantitative Research & Dual-Duration Statistical Validation Framework (V1.7.4)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Testing](https://img.shields.io/badge/pytest-274%20passed%20(100%25)-0284C7)
![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)
![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)
![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)
![Dual Duration](https://img.shields.io/badge/Architecture-Dual--Duration%202T%20%7C%205T-0284C7)
![Strategy Discovery](https://img.shields.io/badge/Strategy%20Discovery-Advisory--Only%20FWER%20Controlled-0284C7)
![Evidence Integrity](https://img.shields.io/badge/Evidence%20Integrity-Authoritative%20Reconciled-brightgreen.svg)
![Contract Spec](https://img.shields.io/badge/Contract%20Spec-Configurable%20Monotonic%20Lifecycle-0284C7)
![Confirmation Authority](https://img.shields.io/badge/Confirmation%20Authority-Unified%20ForwardConfirmationGate-0284C7)
![Reconciliation](https://img.shields.io/badge/Reconciliation-6%20Separated%20Integrity%20Dimensions-0284C7)
![Version](https://img.shields.io/badge/Version-V1.7.4%20Dual--Duration%20Research-0284C7)

A quantitative financial research, machine-learning inference, and real-market forward observation system engineered for Deriv synthetic index contracts—specifically modeling Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) on Volatility 75 (`R_75`).

V1.7.4 establishes dual-duration 2-tick versus 5-tick paired research, evidence-grounded research reporting inspired by HKUDS/Vibe-Trading, an advisory-only strategy discovery engine with Bonferroni multiple-testing control, overlapping-label purging, independent frozen model management, and full reconciliation of historical probability and expected value statistics. Real-money live execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

---

## The Central Research Question: 2-Tick vs. 5-Tick

> **Does a two-tick contract provide more reliable, economically profitable prediction opportunities than the existing five-tick contract?**

### The Empirical Finding
**A higher winning frequency does NOT imply economic profitability.**
- **Winning Frequency**: 2-Tick contracts win approximately **25.67%** of the time (7x more frequently than 5-tick contracts at **3.63%**).
- **Payout Asymmetry**: Deriv's total payout on a $2.00 stake is **$7.63** for 2 ticks versus **$61.07** for 5 ticks.
- **The Economic Hurdle**: The break-even probability for 2 ticks is **26.212%**, which is strictly higher than both the empirical base rate (25.34%) and the observed live win rate (25.67%).
- **Economic Return**: The unconditional 2-tick contract produces an average loss of **-$0.0667** per $2.00 stake.
- **Uncertainty Lower Bound**: When dependence-aware moving-block bootstrap uncertainty is applied, both durations produce negative conservative expected values. Neither clears the authoritative confirmation hurdle.

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
- **RUNHIGH_5T**: Wins iff $S_0 < S_1 < S_2 < S_3 < S_4 < S_5$.
- **RUNLOW_5T**: Wins iff $S_0 > S_1 > S_2 > S_3 > S_4 > S_5$.

### Universal Settlement Rules
- **Equality Rule**: Any flat movement ($S_k = S_{k-1}$) results in an immediate contract loss.
- **Reversal Rule**: Any opposing directional movement results in an immediate contract loss.
- **Dual Loss Reality**: In oscillating sequences, both RUNHIGH and RUNLOW lose simultaneously.
- **Incomplete Sequences**: Classified as `OUTCOME_INCOMPLETE`, strictly excluded from win rates.
- **Data Gap Sequences**: Inter-tick gaps $> 5.0\text{s}$ classified as `OUTCOME_DATA_GAP` and excluded.

---

## Empirical Baselines vs. Live Proposal Hurdle

The engine evaluates conditional model probabilities against exact broker quotes:

$$\text{BreakEven} = \frac{\text{AskPrice}}{\text{TotalPayout}}$$
$$\text{ExpectedValue} = \text{PredictedProbability} \times \text{TotalPayout} - \text{AskPrice}$$

| Contract Configuration | Theoretical Symmetric Rate | Empirical Base Rate (R_75) | Deriv Proposal ($2 Stake) | Break-Even Hurdle | Unconditional Ordinary EV |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RUNHIGH (2 Ticks)** | 25.000% ($(0.5)^2$) | 25.341% | $7.63 | **26.212%** | **-$0.0665** |
| **RUNLOW (2 Ticks)** | 25.000% ($(0.5)^2$) | 24.752% | $7.63 | **26.212%** | **-$0.1114** |
| **RUNHIGH (5 Ticks)** | 3.125% ($(0.5)^5$) | 3.277% | $61.07 | **3.275%** | **+$0.0013** |
| **RUNLOW (5 Ticks)** | 3.125% ($(0.5)^5$) | 2.973% | $61.07 | **3.275%** | **-$0.1812** |

---

## AI-Assisted Strategy Discovery Architecture

Inspired by the research methodology of HKUDS/Vibe-Trading, V1.7.4 introduces `strategy_discovery.py`:

```
+-------------------------------------------------------------------------+
|                  AI RESEARCH LAYER (ADVISORY-ONLY)                     |
|                                                                         |
|   strategy_discovery.py:                                               |
|   - Predeclared Hypothesis Families (Streak, Volatility, Reversal)      |
|   - Overlapping-Label Purging (step = duration + 1)                    |
|   - Bonferroni & FDR Multiple-Testing Adjustments                      |
|                                                                         |
|   INVARIANTS:                                                           |
|   IS_ADVISORY_ONLY = True                                              |
|   EXECUTION_AUTHORIZATION_DISABLED = True                               |
+-------------------------------------------------------------------------+
                                    ||
                                    || (Hypothesis Audit Report Only)
                                    \/
+-------------------------------------------------------------------------+
|             CONFIRMATION GATE & NO_TRADE SAFETY INVARIANT               |
|                                                                         |
|   decision_gate.py:                                                     |
|   - Gate 1: SHADOW / DATA_COLLECTION Mode Non-Trading Guard             |
|   - Gate 3: Contract & Duration Verification (2T and 5T)               |
|   - Gate 4: Frozen Model Approval Status (Approved only if confirmed)  |
|   - Gate 6: Quote Timestamps (resp_ts <= decision_ts)                   |
|   - Gate 7 & 9: Positive EV & Break-Even Margin                        |
|                                                                         |
|   PERMANENT SAFETY INVARIANT:                                           |
|   LIVE_EXECUTION_DISABLED = True                                       |
+-------------------------------------------------------------------------+
```

### Discovery Guardrails
1. **Advisory-Only Firewall**: An AI-generated hypothesis CANNOT authorize order placement.
2. **Controlled Hypothesis Families**: Replaces unconstrained data mining with pre-registered feature conditions (consecutive streaks, volatility regimes, extreme acceleration).
3. **Overlapping-Label Purging**: Eliminates artificial serial correlation by sampling evaluations at $(d + 1)$ tick intervals.
4. **Multiple-Testing Correction**: Applies Bonferroni ($p_{\text{adj}} = \min(1.0, p \times M)$) and Benjamini-Hochberg FDR adjustments.

---

## V1.7.4 Core Architecture & Module Inventory

| Component | File | Role |
|---|---|---|
| **2-Tick Model Trainer** | `model_2tick.py` | Independent 2-tick state conditioning, empirical Bayes shrinkage, Wilson intervals |
| **Strategy Discovery Engine** | `strategy_discovery.py` | Advisory hypothesis discovery, label purging, Bonferroni FWER controls |
| **Dual-Duration Research** | `dual_duration_research.py` | Paired stream evaluator, moving-block bootstrap, economic ranking |
| **Contract Specification** | `contract_specification.py` | Canonical 2T and 5T specs, monotonic evaluation, equality loss rules |
| **Outcome Resolver** | `outcome_resolver.py` | Duration-aware multi-pending resolution, inter-tick gap tracking ($S_0..S_d$) |
| **Prediction Journal** | `forward_journal.py` | Duration-aware schema, duplicate write prevention, forward outcomes table |
| **Central Decision Gate** | `decision_gate.py` | 11-gate centralized evaluation, cross-duration quote/model rejection, NO_TRADE |
| **Quote Database** | `quote_database.py` | SQLite proposal storage with duration filtering and strict causal timestamp bounds |
| **Quote Quoting Engine** | `quote_engine.py` | Direction and duration-specific live/historical quote retrieval |
| **Model Manager** | `model_manager.py` | Multi-duration model discovery, schema verification, and cryptographic loading |
| **Forward Observer** | `forward_observer.py` | Duration-aware observation, tick buffer, live boundary anchoring |
| **Research Metrics Engine** | `research_metrics_engine.py` | Single-source data analysis, referential joins, dataset checksum validation |
| **Confirmation Gate** | `forward_confirmation_gate.py` | Unified confirmation gate enforcing 13 mandatory categories via strict AND logic |
| **Session Reconciler** | `session_reconciler.py` | 6-dimension automated audit engine verifying provenance, ticks, quotes, outcomes |
| **Risk Manager** | `risk.py` | Persistent SQLite risk state tracking and daily loss limit enforcement |

---

## Project Directory Structure

```
bot_builder/
├── .gitignore                                      # Excludes scratch, .agents, pycache
├── README.md                                       # Architectural documentation and specs
├── requirements.txt                                # Python dependencies (zero unapproved additions)
├── config.py                                       # System configuration defaults
│
├── contract_specification.py                       # Canonical 2T and 5T monotonic specs
├── contract_model.py                               # Vectorized contract lifecycle engine
├── contract_lifecycle.py                           # Demo settlement verification harness
│
├── model_artifact.py                               # ModelArtifact schema and JSON serialization
├── model_manager.py                                # Model discovery, loading, and duration routing
├── model_2tick.py                                  # Independent 2-tick model implementation
│
├── feature_schema.py                               # Canonical feature definitions and lookback
├── features.py                                     # Feature computation utilities
├── probability.py                                  # Statistical distributions & Wilson score intervals
│
├── quote_recorder.py                               # Deriv proposal quote recorder
├── quote_database.py                               # Indexed SQLite proposal quote storage
├── quote_engine.py                                 # Quoting engine with duration support
│
├── outcome_resolver.py                             # Duration-aware multi-pending outcome resolver
├── forward_journal.py                              # Immutable forward prediction journal
├── forward_observer.py                             # Live stream observer and sliding buffer
├── forward_session.py                              # Session registry and lifecycle states
├── session_reconciler.py                           # 6-dimension audit reconciler
├── run_forward_session.py                          # Forward research CLI runner
│
├── decision_gate.py                                # Centralized 11-gate paper decision gate
├── forward_confirmation_gate.py                    # Authoritative confirmation gate
├── confirmation_specification.py                   # Pre-registered confirmation manifests
├── risk.py                                         # Institutional persistent risk engine
│
├── strategy_discovery.py                           # Advisory-only hypothesis testing engine
├── dual_duration_research.py                       # Paired 2T vs 5T research comparison engine
├── research_metrics_engine.py                      # Research metrics aggregation engine
│
├── data/
│   ├── R_75_master.csv                             # Canonical training dataset (43,184 ticks)
│   ├── R_75_live_ticks.csv                         # Live market stream (2,014 ticks)
│   ├── deriv_2t_5t_availability.json               # Live Deriv API 2T & 5T proposal records
│   ├── forward_predictions.db                      # SQLite prediction & outcome journal
│   ├── quotes.db                                   # SQLite proposal quotes database
│   ├── sessions.db                                 # SQLite session registry
│   └── risk_state.db                               # SQLite persistent risk limits
│
├── models/
│   ├── M_R_75_5TICK_20261008_132512.json           # Preserved authoritative 5-tick frozen model
│   └── M_R_75_2TICK_20261011_120000.json           # Independent 2-tick frozen model
│
├── tests/
│   ├── test_v174_dual_duration_and_discovery.py    # 17 new V1.7.4 regression tests
│   ├── test_v173_chronology_and_settlement.py      # V1.7.3 chronology & settlement tests
│   ├── test_v172_research_integrity.py             # V1.7.2 integrity & confirmation tests
│   └── ... (274 total passing tests)
│
└── V1_7_4 Deliverable Reports:
    ├── V1_7_4_EVIDENCE_CORRECTION_REPORT.md        # Reconciled historical probabilities & EV
    ├── V1_7_4_DERIV_2T_AVAILABILITY_REPORT.md       # Live Deriv 2T contract availability
    ├── V1_7_4_VIBE_TRADING_RESEARCH_ASSESSMENT.md  # Vibe-Trading methodology assessment
    ├── V1_7_4_DUAL_DURATION_MODEL_REPORT.md        # Independent 2T & 5T model report
    ├── V1_7_4_DUAL_DURATION_FORWARD_COMPARISON.md  # Paired 2T vs 5T empirical comparison
    └── V1_7_4_RELEASE_VALIDATION_REPORT.md         # Release audit & safety verification
```

---

## Test Suite & Verification Execution

Execute the full automated test suite:

```bash
python -m pytest -q
```

Expected result:
```
274 passed in ~68s (100% green)
```

---

## Permanent Safety Invariants

1. **`LIVE_EXECUTION_DISABLED = True`**: Hardcoded invariant. Real-money purchases are permanently disabled across all modules.
2. **No Real-Money Endpoints**: The software contains zero real-money order routing code.
3. **`IS_ADVISORY_ONLY = True`**: AI strategy discovery is locked behind an advisory firewall.
4. **Authoritative NO_TRADE**: Every observation in SHADOW mode resolves to `decision: NO_TRADE`.
5. **No Lookahead**: Strict causal timestamp enforcement: $\text{QuoteResponse} \le \text{DecisionTime}$.
