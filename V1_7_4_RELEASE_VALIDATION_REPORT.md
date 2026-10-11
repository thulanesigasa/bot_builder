# V1.7.4 RELEASE VALIDATION & VERIFICATION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Build-Status](https://img.shields.io/badge/Build-Passing%20274%2F274-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Coverage](https://img.shields.io/badge/Regression-100%25%20Verified-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Release Overview & Engineering Mission

This report provides the authoritative release validation for version **V1.7.4** of the Deriv Only Ups / Only Downs quantitative research system (`bot_builder`).

- **Target Release**: V1.7.4
- **Previous Release**: V1.7.3
- **Base Inspected Commit**: `1570b4fca0a445d39012daa558bf2062df019498`
- **Target Branch**: `main`
- **Primary Research Focus**: Evidence integrity correction, Vibe-Trading research methodology integration, and dual-duration (2-Tick vs 5-Tick) empirical evaluation on Volatility 75 (`R_75`).

---

## 2. Test Suite Execution & Verification

### Test Suite Execution Summary
- **Test Framework**: `pytest-9.1.1` under Python 3.14.6 (Windows 64-bit)
- **Baseline Test Count Claimed (V1.7.3)**: 257 passing tests
- **Baseline Test Count Verified**: **257 / 257 passed (100% green)**
- **New V1.7.4 Regression Tests Added**: 17 tests in `tests/test_v174_dual_duration_and_discovery.py`
- **Total Test Suite Count**: **274 tests**
- **Final Test Result**: **274 passed, 0 failed (100% green)** in 68.95s

### Verified Test Areas
1. Monotonic 2-tick RUNHIGH wins ($S_0 < S_1 < S_2$)
2. Monotonic 2-tick RUNLOW wins ($S_0 > S_1 > S_2$)
3. 2-tick dual losses on reversals and flat movements
4. 2-tick equality handling (strict loss on ties)
5. 5-tick backward compatibility
6. Duration-aware OutcomeResolver lifecycle and database schema
7. Duration-specific QuoteDatabase lookups
8. Decision Gate duration matching (Gate 3) and cross-duration rejection (Gate 4 & 6)
9. Mathematical expected value equations without fallbacks
10. Predeclared hypothesis evaluation and Bonferroni multiple-testing control
11. Overlapping-label purging
12. Permanent safety invariants (`LIVE_EXECUTION_DISABLED = True`, `IS_ADVISORY_ONLY = True`, `NO_TRADE` enforcement)

---

## 3. Comprehensive File Modification Inventory

### New Core Modules & Artifacts Created
1. `model_2tick.py`: Independent 2-tick model implementation, feature conditioner, and trainer.
2. `strategy_discovery.py`: Advisory-only hypothesis discovery engine with Bonferroni correction and overlapping-label purging.
3. `dual_duration_research.py`: Paired forward comparison engine with moving-block bootstrap uncertainty modeling.
4. `models/M_R_75_2TICK_20261011_120000.json`: Frozen 2-tick empirical model artifact with full dataset provenance (`8273d215bf...`).
5. `tests/test_v174_dual_duration_and_discovery.py`: 17 dedicated V1.7.4 regression tests.
6. `data/deriv_2t_5t_availability.json`: Live Deriv WebSocket contract availability and proposal quote record.

### Existing Core Modules Updated
1. `contract_specification.py`: Extended canonical specs to support both 2t and 5t durations; generalized monotonic evaluation functions.
2. `outcome_resolver.py`: Added duration-aware `PendingOutcome` tracking, `contract_duration` database schema migration, and dynamic sequence resolution ($S_0..S_d$).
3. `forward_journal.py`: Added `contract_duration` field to `ForwardPredictionRecord`, schema migration, and journal persistence.
4. `decision_gate.py`: Updated Gate 3 to accept both 2t and 5t contracts; enforced cross-duration quote and model rejection.
5. `quote_database.py`: Parameterized `get_latest_quote_before` to support optional duration filtering.
6. `quote_engine.py`: Parameterized `get_quote` and `get_quote_status` with `duration`.
7. `model_manager.py`: Generalized `get_latest_model_for_symbol` and `train_and_export_baseline_model` to accept `duration_ticks`.
8. `forward_observer.py`: Added `contract_duration` parameter, filtering model discovery and validation by duration to prevent cross-duration mismatch.

### Mandated Reports Produced
1. `V1_7_4_EVIDENCE_CORRECTION_REPORT.md`
2. `V1_7_4_DERIV_2T_AVAILABILITY_REPORT.md`
3. `V1_7_4_VIBE_TRADING_RESEARCH_ASSESSMENT.md`
4. `V1_7_4_DUAL_DURATION_MODEL_REPORT.md`
5. `V1_7_4_DUAL_DURATION_FORWARD_COMPARISON.md`
6. `V1_7_4_RELEASE_VALIDATION_REPORT.md`

---

## 4. Operational Safety & Permanent Invariants Verification

| Safety Gate / Invariant | Status | Verification Evidence |
| :--- | :---: | :--- |
| **`LIVE_EXECUTION_DISABLED = True`** | **ENFORCED** | Hardcoded invariant across `decision_gate.py`, `forward_observer.py`, and test suite. |
| **Real-Money Orders Prohibited** | **ENFORCED** | Zero real-money API buy calls exist; endpoint disabled. |
| **AI Strategy Discovery Advisory-Only** | **ENFORCED** | `IS_ADVISORY_ONLY = True` invariant enforced in `strategy_discovery.py`. |
| **Confirmation Gate Bypasses Prohibited** | **ENFORCED** | Gating logic rejects any trade without confirmed approval status and fresh causal quote. |
| **NO_TRADE Enforcement** | **ENFORCED** | All forward sessions in SHADOW mode correctly resolve to `decision: NO_TRADE`. |
| **Lookahead Protection** | **ENFORCED** | Strict causal quote rule: `quote_response <= decision_timestamp`. |

---

## 5. Known Limitations & Research Recommendations

### Known Limitations
1. **Unconditional Negative Edge on 2-Tick Contracts**: Despite winning ~25% of the time, 2-tick contracts fail the broker's 26.212% break-even hurdle ($Ask=\$2.00, Payout=\$7.63$), resulting in an average ordinary loss of -$0.0665 per $2.00 stake.
2. **Serial Correlation Among Overlapping Predictions**: Moving-block bootstrap confirms that when serial dependence is taken into account, conservative lower bounds remain negative for both 2-tick and 5-tick contracts.
3. **Throttled Quoting During Volatile Periods**: WebSocket proposal requests occasionally experience 300-500ms socket latency during sharp tick bursts.

### Explicit Recommendation
- **Further Live Trading**: Strictly **NOT JUSTIFIED**. Real-money trading must remain permanently disabled.
- **Further SHADOW Collection**: **JUSTIFIED** for sustained exploratory data collection under bounded sessions (30-60 min) to observe whether extreme conditional streak or volatility filters can reliably sustain out-of-sample win rates above 26.212%.
