# V1.7.3 FORWARD EVIDENCE & STATISTICAL RECALCULATION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.3-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research-Stage](https://img.shields.io/badge/Research%20Stage-EXPLORATORY-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Paper-Trade-Status](https://img.shields.io/badge/PAPER%20Trade%20Approval-0%20(REJECTED)-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Real--Money%20Trading-DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Verified Session Scope & Evidence Accounting

This report presents the recalibrated empirical and statistical findings from the authoritative live Deriv forward observation session.

| Parameter | Authoritative Value | Audit Status |
| :--- | :--- | :--- |
| **Session ID** | `413bbee4-0291-455a-abbe-60257b547b4b` | Verified Live Deriv SHADOW |
| **Market Symbol** | `R_75` (Volatility 75 Index) | High-frequency synthetic index |
| **Total Captured Ticks** | 145 ticks | Verified against CSV tick journal |
| **Total Forward Predictions** | 134 predictions | Evaluated sequentially on live ticks |
| **Resolved Outcomes** | 129 observations | 5 remaining predictions were incomplete at session termination |
| **Incomplete Observations** | 5 observations | Correctly excluded from win rate denominator |
| **Quote Coverage (Chrono-Valid)** | **100.0% (134 / 134)** | Quotes received $\le$ decision time |
| **Research Stage Classification** | **EXPLORATORY ONLY** | Pre-confirmation exploratory stage |

---

## 2. Forward Probability & Calibration Statistics

Observations are evaluated on the 129 complete 5-movement forward outcomes:

| Statistical Metric | RUNHIGH ("Only Ups") | RUNLOW ("Only Downs") | Baseline Benchmark |
| :--- | :---: | :---: | :---: |
| **Resolved Sample Size ($N$)** | 129 | 129 | 129 |
| **Directional Wins** | 5 | 5 | — |
| **Directional Losses** | 124 | 124 | — |
| **Observed Win Rate** | **3.876%** | **3.876%** | Theoretical random walk: ~3.125% |
| **Mean Model Probability** | **0.0384 (3.84%)** | **0.0384 (3.84%)** | Frozen logistic model |
| **Calibration Error (Obs - Pred)** | **+0.00036 (+0.04%)** | **+0.00036 (+0.04%)** | Extremely well-calibrated mean |
| **Brier Score** | **0.0373** | **0.0373** | Low Brier score |
| **Brier Skill Score (BSS)** | **+0.0081** | **+0.0081** | Modest positive skill over naive climatology |

---

## 3. Dependence-Aware Uncertainty Analysis

> **Critical Methodological Standard:** Consecutive 5-tick contract windows overlap by up to 4 ticks. Treating overlapping predictions as independent observations creates an artificial appearance of statistical significance.

1. **Independent Wilson 95% Confidence Interval (Naive):**
   $$\text{Naive } 95\% \text{ CI: } [1.67\%, 8.78\%]$$
   Lower bound exceeds break-even (3.275%) only if independence is erroneously assumed.

2. **Dependence-Aware Block-Bootstrap (Cluster Size = 5 ticks):**
   $$\text{Effective Sample Size: } N_{\text{eff}} \approx \frac{129}{5} \approx 25.8 \text{ blocks}$$
   $$\text{Dependence-Aware } 95\% \text{ Lower Bound: } \mathbf{0.52\%}$$
   $$\text{Dependence-Aware } 95\% \text{ Upper Bound: } \mathbf{9.40\%}$$

Because the lower bound ($0.52\%$) falls substantially below the break-even threshold ($3.275\%$), there is **no statistically proven positive edge** under conservative uncertainty bounds.

---

## 4. Recomputed Genuine Quote-Based EV

Expected Value is computed using only genuine, chronologically verified live proposal quotes from the Deriv WebSocket API (stake = \$2.00, payout = \$61.07):

$$\text{Break-Even Probability} = \frac{\text{Ask Price}}{\text{Total Payout}} = \frac{\$2.00}{\$61.07} = \mathbf{3.275\%}$$

$$\text{Ordinary EV} = P_{\text{model}} \times \text{Payout} - \text{Ask} = 0.0384 \times \$61.07 - \$2.00 = \mathbf{+\$0.345}$$

$$\text{Retrospective Empirical EV} = P_{\text{obs}} \times \text{Payout} - \text{Ask} = 0.03876 \times \$61.07 - \$2.00 = \mathbf{+\$0.367}$$

$$\text{Conservative EV} = P_{\text{lower, dep-aware}} \times \text{Payout} - \text{Ask} = 0.0052 \times \$61.07 - \$2.00 = \mathbf{-\$1.682}$$

### Decision Gate Financial Conclusion:
1. **Ordinary EV** is slightly positive (+\$0.345) based on the point estimate.
2. **Conservative EV** is severely negative (-\$1.682) when factoring in clustering and dependency uncertainty.
3. **Paper Trade Authorization:** **REJECTED (0 Approvals)**. Gate 7 requires `Conservative_EV > 0.0`.

---

## 5. Authoritative Confirmation Gate Status

In accordance with V1.7.3 Part G Section 23:
- **Confirmation Sessions Registered:** 0
- **Candidate Frozen:** `model_v1_baseline`
- **Confirmation Gate Result:** **BLOCKED**
- **Action Required:** Exploratory observations must never be retrospectively converted into confirmation data. An immutable candidate manifest must be registered prior to initiating prospective confirmation runs.
