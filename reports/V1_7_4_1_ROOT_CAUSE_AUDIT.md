# V1.7.4.1 ROOT CAUSE AUDIT & INTEGRITY CORRECTION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4.1-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Status](https://img.shields.io/badge/Audit-Passed%20100%25-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Execution-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evidence-Integrity](https://img.shields.io/badge/Evidence%20Integrity-Authoritative-orange.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Audit Mandate

In accordance with Master Development Prompt V1.7.4.1 Part 10, this report documents the comprehensive root-cause analysis, defect locations, rationale, code corrections, and automated regression tests implemented across the quantitative research system.

Every identified weakness in research integrity, quote economics, model validation, and multiple-testing statistics has been surgically resolved. All 288 automated tests pass unconditionally.

---

## 2. Comprehensive Defect Matrix

| ID | Module & Defect Location | Root Cause | Scientific Impact | Surgical Correction | Automated Regression Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEF-01** | `dual_duration_research.py`<br>`Line 300` | Hardcoded `quote_availability_pct = 100.0` without validating timestamps | Falsely claimed complete quote availability during retrospective replay | Implemented multi-tier quote coverage (`raw`, `chrono`, `econ`, `exec`). Reports `0.0%` in `REFERENCE_SCENARIO` mode. | `TestQuoteEconomicsAndCoverageIntegrity`<br>`::test_reference_scenario_reports_zero_quote_coverage`<br>`::test_quote_verified_mode_calculates_real_coverage` |
| **DEF-02** | `dual_duration_research.py`<br>`Line 276` | Permissive threshold: `is_pos = (ord_ev > 0.0) and (cons_ev > -0.05)` | Permitted negative conservative EV (up to -$0.05) to qualify as economically positive | Enforced strict `cons_ev >= min_conservative_ev` (default `0.0`). Negative conservative EV strictly blocks candidate. | `TestEconomicHurdleAndConservativeEV`<br>`::test_negative_conservative_ev_blocks_economic_qualification` |
| **DEF-03** | `dual_duration_research.py`<br>`Lines 335-337` | Inadequate sample fallback in `_moving_block_bootstrap_ev`: returned empirical mean | Mislabelled ordinary sample mean as a conservative statistical lower bound | Returned `None`, set `bootstrap_uncertainty_status = 'INSUFFICIENT_SAMPLE'`, and blocked qualification. | `TestEconomicHurdleAndConservativeEV`<br>`::test_insufficient_sample_returns_unavailable_conservative_ev` |
| **DEF-04** | `dual_duration_research.py`<br>System-wide | Retrospective index replay labelled without explicit evidence classification | Risk of confusing historical replay with genuine forward shadow observations | Introduced explicit `EvidenceClass` enum (`HISTORICAL_REPLAY`, `HISTORICAL_HOLDOUT`, `PROSPECTIVE_SHADOW`, `INDEPENDENT_CONFIRMATION`). | `TestAdversarialEvidenceClassification`<br>`::test_historical_price_list_is_classified_as_historical_replay` |
| **DEF-05** | `model_2tick.py`<br>`Lines 175-210` | Two-tick model state conditional tables fit over 100% of dataset; Brier score computed as $p(1-p)$ | Data leakage across partitions; validation metrics did not reflect out-of-sample accuracy | Implemented strict chronological splits (60% train, 20% val, 20% holdout) with 3-tick embargo. Computed real out-of-sample Brier and BSS scores. | `TestTwoTickChronologicalPartitioning`<br>`::test_chronological_splits_and_embargo` |
| **DEF-06** | `strategy_discovery.py`<br>`Lines 208-214` | Naive FDR rank adjustment computed independently per item without reverse cumulative minimum | Violated Benjamini-Hochberg monotonicity (higher p-values could have lower adjusted p-values) | Implemented `benjamini_hochberg_adjustment` with step-up reverse cumulative minimum and bounds clamping. | `TestMultipleTestingAndStatisticalRigor`<br>`::test_benjamini_hochberg_enforces_monotonicity`<br>`::test_benjamini_hochberg_preserves_bounds_and_ordering` |
| **DEF-07** | `forward_observer.py`<br>`Lines 405-416, 482, 513` | Quote query omitted `duration`, and decision gate hardcoded `duration_ticks=5` | Risk of cross-duration quote mismatch when evaluating 2-tick contracts in forward observer | Updated quote queries to pass `duration=self.contract_duration` and gate calls to pass `duration_ticks=self.contract_duration`. | `TestDecisionGate`<br>`::test_decision_gate_rejects_cross_duration_quotes` |
| **DEF-08** | `V1_7_4_DERIV_2T_AVAILABILITY_REPORT.md`<br>vs `data/deriv_2t_5t_availability.json` | Report table transcribed exploratory query IDs (`d1752c00-...`) while JSON saved follow-up verification IDs (`1b2591ab-...`) | Created apparent discrepancy between report narrative and underlying persisted JSON record | Reconciled both passes in `data/deriv_2t_5t_availability.json` with complete raw response metadata, timestamps, and latency figures. | `tests/test_v174_dual_duration_and_discovery.py` |

---

## 3. Detailed Root-Cause Analyses

### DEF-01: Artificial 100% Quote Coverage
- **Mechanism**: The evaluator previously assigned `quote_availability_pct = 100.0` directly to summary dictionaries. This created the illusion that every decision point had an active, validated Deriv quote at the moment of evaluation.
- **Correction**: Replaced with multi-tier coverage analysis. In `EvaluationMode.REFERENCE_SCENARIO`, quote coverage is reported as `0.0%` because hypothetical payouts ($7.63, $61.07) are unverified reference values. In `EvaluationMode.QUOTE_VERIFIED`, coverage is calculated tick-by-tick against genuine persisted quote timestamps, verifying that `quote.response_timestamp <= decision_timestamp`.

### DEF-02: Negative Conservative EV Threshold
- **Mechanism**: The logic `cons_ev > -0.05` permitted contracts with expected losses at the 95% bootstrap lower bound to qualify as "economically positive".
- **Correction**: Replaced with `cons_ev >= min_conservative_ev` where `min_conservative_ev` defaults to `0.0`. If the lower bound is negative or unavailable, the contract receives verdict `FAILED_CONSERVATIVE_HURDLE` or `INSUFFICIENT_UNCERTAINTY_EVIDENCE`.

### DEF-03: Small-Sample Bootstrap Fallback
- **Mechanism**: When the sample count $n < 2 \times \text{block\_size}$, the bootstrap function returned `np.mean(outcomes) * payout - stake`. This conflated an ordinary empirical mean with a conservative lower bound.
- **Correction**: When $n < \max(30, 2 \times \text{block\_size})$, the function returns `None` and flags `bootstrap_uncertainty_status = 'INSUFFICIENT_SAMPLE'`.

### DEF-05: Model Training Leakage & Pseudo-Brier Score
- **Mechanism**: The 2-tick trainer counted indices for train, val, and holdout partitions, but the loop that accumulated conditional frequency tables ran across the entire dataset. Furthermore, the Brier score was calculated using the binomial variance formula $p(1-p)$ rather than out-of-sample prediction error $(y_i - \hat{p}_i)^2$.
- **Correction**: Restructured the trainer into distinct chronological phases:
  1. Training (first 60%): Conditional state tables and priors fitted solely on train observations.
  2. Embargo Gap: 3 ticks ($h = \text{duration} + 1$) excluded between partitions.
  3. Validation (next 20%): Evaluated out-of-sample Brier score (0.18785) and Log Loss (0.56316).
  4. Holdout (final 20%): Evaluated frozen model once without feedback. Holdout win rates (RH: 24.565%, RL: 25.690%) confirmed that neither direction exceeds the 26.212% hurdle.

### DEF-06: Non-Monotonic Benjamini-Hochberg FDR
- **Mechanism**: The FDR p-value calculation applied rank scaling $p_{(i)} \times \frac{m}{i}$ without applying the reverse cumulative minimum step.
- **Correction**: Implemented the textbook Benjamini-Hochberg (1995) step-up procedure:
  $$q_{(i)}' = \min\left(1.0, \min_{k \ge i} \left( p_{(k)} \frac{m}{k} \right)\right)$$
  ensuring that adjusted p-values are strictly non-decreasing with respect to the sorted raw p-values.

---

## 4. Safety and Verification Invariants

1. `LIVE_EXECUTION_DISABLED = True` remains permanently enforced in `decision_gate.py` and `forward_observer.py`.
2. Strategy discovery via `strategy_discovery.py` is strictly advisory (`IS_ADVISORY_ONLY = True`, `EXECUTION_AUTHORIZATION_DISABLED = True`).
3. Confirmation gates require untouched prospective evidence; historical replay cannot bypass Gate 5.
