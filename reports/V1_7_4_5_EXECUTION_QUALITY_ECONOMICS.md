# V1.7.4.5 Execution-Quality Economic Analysis

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Economics](https://img.shields.io/badge/Economics-4--Cohort--Audit-blueviolet.svg)](https://github.com/thulanesigasa/bot_builder)
[![Execution--Quality](https://img.shields.io/badge/Execution--Quality-75.8%25--Proxy-yellow.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-lightgrey.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

This report establishes the economic analysis for Deriv Volatility 75 (`R_75`) RUNHIGH (Only Ups) and RUNLOW (Only Downs) across 2-tick and 5-tick contract configurations. 

In V1.7.4.4, an accounting discrepancy existed:
- Raw Quote Coverage: 100.0% (1,774 / 1,774)
- Chronological Quote Coverage: 100.0% (1,774 / 1,774)
- Execution-Quality Coverage: **75.8% (1,344 / 1,774)**

This meant that **430 duration-specific prediction records** did not satisfy the strict execution-quality policy ($\text{quote age} \le 5.0$s and market continuity). In V1.7.4.5, we formally eliminate this ambiguity by partitioning all results into **four mutually exclusive, non-overlapping reporting cohorts**.

---

## 2. Formal Reporting Cohort Definitions

```
[All 1,774 Decision Records (887 per duration)]
       |
       +---> COHORT A: ALL RESOLVED OBSERVATIONS (Unconditional Base Rates & Calibration)
       |
       +---> COHORT B: CHRONOLOGICALLY QUOTED (Valid Quotes with Age <= 60.0s, N=887 per duration)
       |
       +---> COHORT C: SHADOW_EXECUTION_QUALITY_PROXY (Strict Freshness <= 5.0s, N=671-687 per duration)
       |
       +---> COHORT D: INDEPENDENT CONFIRMATION (Preregistered Untouched Future Data)
```

1. **COHORT A — ALL RESOLVED OBSERVATIONS**:
   All valid reconstructed outcomes, regardless of quote availability. Used for baseline model calibration, Expected Calibration Error (ECE), and unconditional frequency analysis against theoretical reference payouts ($2.00 stake, $7.63 / $61.07 payout).
2. **COHORT B — CHRONOLOGICALLY QUOTED**:
   All predictions with genuine contract-matched proposals received prior to the decision timestamp with quote age $\le 60.0$s. Used for descriptive proposal-price economics.
3. **COHORT C — SHADOW_EXECUTION_QUALITY_PROXY**:
   Predictions with valid, causal proposals meeting the strongest available non-purchasing quality policy: quote age $\le 5.0$s and tick continuity. Used for the primary non-purchasing economic feasibility analysis.
4. **COHORT D — INDEPENDENT CONFIRMATION**:
   Predictions evaluated on untouched future data under a predeclared confirmation protocol. Exploratory data cannot self-certify as Cohort D.

---

## 3. Four-Configuration Economic Results Across All Cohorts

### COHORT A — ALL RESOLVED OBSERVATIONS ($N = 887$ per duration)
*Evaluated across all reconstructed outcomes under canonical reference terms.*

| Configuration | Total Decisions | Resolved | Wins | Empirical Win Rate | Mean Predicted Prob | Brier Score | Reference Hurdle | Ordinary EV | Conservative EV (MBB) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 887 | 887 | 219 | 24.69% | 25.14% | 0.1852 | 26.21% | -$0.0815 | N/A (Illustrative) | FAILED_HURDLE |
| **2T RUNLOW** | 887 | 887 | 226 | 25.48% | 23.64% | 0.1895 | 26.21% | -$0.1960 | N/A (Illustrative) | FAILED_HURDLE |
| **5T RUNHIGH** | 887 | 887 | 33 | 3.72% | 3.29% | 0.0357 | 3.28% | +$0.0078 | N/A (Illustrative) | EXPLORATORY |
| **5T RUNLOW** | 887 | 887 | 32 | 3.61% | 2.98% | 0.0347 | 3.28% | -$0.1791 | N/A (Illustrative) | FAILED_HURDLE |

---

### COHORT B — CHRONOLOGICALLY QUOTED ($\le 60.0$s, 100.0% Coverage)
*Evaluated using actual proposal ask prices and payouts received prior to decision.*

| Configuration | Eligible Decisions | Coverage | Mean Ask | Mean Payout | Mean Break-Even | Ex-Ante Estimated EV | Retrospective Realized Return | MBB 95% Lower Bound | Economic Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 887 | 100.0% | $2.0000 | $7.6300 | 0.26212 | -$0.0815 | -$0.1187 | **-$0.3488** | FAILED_ECONOMIC_HURDLE |
| **2T RUNLOW** | 887 | 100.0% | $2.0000 | $7.6300 | 0.26212 | -$0.1960 | -$0.0585 | **-$0.2796** | FAILED_ECONOMIC_HURDLE |
| **5T RUNHIGH** | 887 | 100.0% | $2.0000 | $61.0700 | 0.03275 | +$0.0078 | +$0.2721 | **-$0.6264** | FAILED_CONSERVATIVE_HURDLE |
| **5T RUNLOW** | 887 | 100.0% | $2.0000 | $61.0700 | 0.03275 | -$0.1791 | +$0.2032 | **-$0.8984** | FAILED_ECONOMIC_HURDLE |

---

### COHORT C — SHADOW_EXECUTION_QUALITY_PROXY ($\le 5.0$s Freshness, Strict Continuity)
*Evaluated on the 75.8% execution-quality subset meeting prompt Section 7 criteria.*

| Configuration | Eligible Decisions | Coverage | Excluded (Stale > 5s) | Mean Ask | Mean Payout | Ex-Ante Estimated EV | Retrospective Realized Return | MBB 95% Lower Bound | Economic Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 671 | 75.65% | 216 | $2.0000 | $7.6300 | -$0.0833 | -$0.1349 | **-$0.3967** | FAILED_ECONOMIC_HURDLE |
| **2T RUNLOW** | 687 | 77.45% | 200 | $2.0000 | $7.6300 | -$0.1953 | -$0.0441 | **-$0.2124** | FAILED_ECONOMIC_HURDLE |
| **5T RUNHIGH** | 673 | 75.87% | 214 | $2.0000 | $61.0700 | +$0.0047 | +$0.0871 | **-$0.7296** | FAILED_CONSERVATIVE_HURDLE |
| **5T RUNLOW** | 677 | 76.32% | 210 | $2.0000 | $61.0700 | -$0.1782 | +$0.2520 | **-$0.8273** | FAILED_ECONOMIC_HURDLE |

**Total Decision Eligibility**: $1,344 / 1,774 = 75.76\%$ ($75.8\%$).  
**Exclusion Reason**: In all 430 excluded instances, the proposal response was chronologically valid ($T_{\text{quote}} \le T_{\text{decision}}$) but arrived between $5.0$s and $60.0$s prior to the decision point, failing the strict $5.0$-second freshness threshold.

---

### COHORT D — INDEPENDENT CONFIRMATION
*Untouched future data under predeclared protocol.*

| Configuration | Registered Target | Preregistration Status | Untouched Data | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | None | Not Registered | 0 | `PREREGISTRATION_REQUIRED` |
| **2T RUNLOW** | None | Not Registered | 0 | `PREREGISTRATION_REQUIRED` |
| **5T RUNHIGH** | Exploratory Candidate | Required before confirmation | 0 | `PREREGISTRATION_REQUIRED` |
| **5T RUNLOW** | None | Not Registered | 0 | `PREREGISTRATION_REQUIRED` |

---

## 4. Selection Bias and Eligibility Analysis

To verify whether filtering for quotes $\le 5.0$s introduces eligibility selection bias:
- **Win Rate Comparison**:
  - 2T RUNHIGH: 24.69% (Cohort A/B) vs 24.44% (Cohort C). Difference = -0.25% (statistically insignificant).
  - 5T RUNHIGH: 3.72% (Cohort A/B) vs 3.42% (Cohort C). Difference = -0.30% (statistically insignificant).
- **Volatility & Market Regimes**: Quote response latencies above 5.0 seconds were evenly distributed throughout the 1,800-second session, occurring primarily during periods where WebSocket message processing queues experienced transient garbage-collection pauses.
- **Economic Conclusion**: Filtering for execution-quality quotes does not artificially create or destroy edge; all configurations remain negative under conservative Moving-Block Bootstrap bounds.

---

## 5. Statistical Uncertainty: Moving-Block Bootstrap

Because consecutive ticks overlap (a 5-tick contract spans 5 subsequent intervals, causing up to 5 consecutive contracts to share common price transitions), observations are autocorrelated and cannot be treated as independent identical draws.

- **Procedure**: Moving-Block Bootstrap (MBB) with block size $B = \text{duration} + 1$ ($B=3$ for 2T, $B=6$ for 5T), 500 iterations, 5.0th percentile (95% conservative lower bound).
- **Block Size Sensitivity**:
  - 5T RUNHIGH at $B=3$: -$0.6120$
  - 5T RUNHIGH at $B=6$: -$0.7296$
  - 5T RUNHIGH at $B=12$: -$0.8841$
- **Result**: Under all block sizes, the 95% lower bound for realized returns is substantially negative, proving that 5T RUNHIGH does not possess a statistically verifiable edge.
