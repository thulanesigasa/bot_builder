# V1.7.4.4 Corrected Prospective Forward Research Results

![Release](https://img.shields.io/badge/Release-V1.7.4.4-0A84FF)
![Evaluation_Mode](https://img.shields.io/badge/Evaluation_Mode-QUOTE_VERIFIED-30D158)
![Evidence_Class](https://img.shields.io/badge/Evidence_Class-PROSPECTIVE_SHADOW-30D158)
![Zero_Emojis](https://img.shields.io/badge/Style-Zero_Emojis_Enforced-64D2FF)
![Safety](https://img.shields.io/badge/Safety-LIVE_EXECUTION_DISABLED-FF453A)

---

## 1. Executive Summary & Audit Scope

This report supersedes all prior prospective evaluation tables published in V1.7.4.3. The empirical statistics below are recomputed from validated, authoritative records in `data/forward_predictions.db`, `data/forward_outcomes`, and `data/quotes.db` using the canonical schema adapter and strict 3-way classification (`WIN`, `LOSS`, `UNAVAILABLE`).

No theoretical probability baselines are substituted for model predictions, and no incomplete or missing outcomes are coerced into losses.

---

## 2. Session c14ac5fb: 300-Second Paired SHADOW Evaluation

- **Session ID:** `c14ac5fb-afaf-440c-ad4e-1a2187f0c42e`
- **Total Decisions:** 136 decisions (68 concurrent paired decision pairs)
- **Quote Verification Coverage:** 100.0% (136/136 verified quote matches)
- **Evidence Class:** `PROSPECTIVE_SHADOW`

### 2.1 Complete Statistical and Performance Matrix

| Metric Property | 2T RUNHIGH | 2T RUNLOW | 5T RUNHIGH | 5T RUNLOW |
| :--- | :--- | :--- | :--- | :--- |
| **Total Prediction Records** | 136 | 136 | 136 | 136 |
| **Complete Resolved Records** | 136 | 136 | 136 | 136 |
| **Incomplete / Pending Records** | 0 | 0 | 0 | 0 |
| **Data-Gap Records** | 0 | 0 | 0 | 0 |
| **Verified Wins** | **42** | **19** | **10** | **1** |
| **Verified Losses** | **94** | **117** | **126** | **135** |
| **Observed Win Rate** | **30.88%** | **13.97%** | **7.35%** | **0.74%** |
| **Wilson 95% Confidence Interval** | [23.77%, 39.08%] | [9.15%, 20.73%] | [4.04%, 12.99%] | [0.13%, 4.04%] |
| **Mean Authentic Model Probability** | **0.2561** | **0.2374** | **0.0337** | **0.0303** |
| **Theoretical Walk Reference** | 0.2500 | 0.2500 | 0.03125 | 0.03125 |
| **Calibration Error (ECE)** | 0.0527 | 0.0977 | 0.0398 | 0.0229 |
| **Brier Score** | 0.2177 | 0.1293 | 0.0698 | 0.0078 |
| **Brier Skill Score (vs Random Walk)** | -0.1609 | +0.3104 | -1.3060 | +0.7424 |
| **Broker Break-Even Hurdle** | 0.2621 | 0.2621 | 0.0327 | 0.0327 |
| **Mean Quote Ask Price** | $2.00 | $2.00 | $2.00 | $2.00 |
| **Mean Quote Total Payout** | $7.63 | $7.63 | $61.07 | $61.07 |
| **Ex-Ante Quote Expected Value (EV)** | **-$0.0463** | **-$0.1886** | **+$0.0572** | **-$0.1508** |
| **Retrospective Realized Return / Contract** | **+$0.3563** | **-$0.9340** | **+$2.4904** | **-$1.5510** |
| **Conservative Bootstrap EV (95% MBB)** | **-$0.2608** | **-$1.3296** | **-$0.6529** | **-$2.0000** |
| **Bootstrap Sample Status** | SUFFICIENT | SUFFICIENT | SUFFICIENT | SUFFICIENT |
| **Economic Qualification Status** | **REJECTED** | **REJECTED** | **REJECTED** | **REJECTED** |
| **Evidence Ladder Verdict** | Level 0 | Level 0 | Level 0 | Level 0 |

*Note on Wilson Confidence Interval: Wilson score intervals represent descriptive binomial intervals assuming independent observations. For autocorrelated tick streams, Moving-Block Bootstrap (MBB) provides dependence-aware uncertainty bounds.*

---

## 3. Session 7b82fef5: 60-Second Live Preflight Evaluation

- **Session ID:** `7b82fef5-fc65-4b38-9750-251aae55395d`
- **Total Decisions:** 17
- **Quote Verification Coverage:** 100.0% (17/17 verified)
- **Evidence Class:** `PROSPECTIVE_SHADOW`

### 3.1 Preflight Performance Breakdown

| Metric Property | 2T RUNHIGH | 2T RUNLOW | 5T RUNHIGH | 5T RUNLOW |
| :--- | :--- | :--- | :--- | :--- |
| **Resolved Records** | 17 | 17 | 17 | 17 |
| **Verified Wins** | **1** | **7** | **0** | **3** |
| **Verified Losses** | **16** | **10** | **17** | **14** |
| **Observed Win Rate** | **5.88%** | **41.18%** | **0.00%** | **17.65%** |
| **Mean Authentic Model Probability** | **0.2522** | **0.2319** | **0.0323** | **0.0302** |
| **Ex-Ante Quote Expected Value (EV)** | -$0.0759 | -$0.2303 | -$0.0286 | -$0.1568 |
| **Retrospective Realized Return / Contract** | -$1.5512 | +$1.1418 | -$2.0000 | +$8.7771 |
| **Conservative Bootstrap EV (95% MBB)** | UNAVAILABLE ($N < 30$) | UNAVAILABLE ($N < 30$) | UNAVAILABLE ($N < 30$) | UNAVAILABLE ($N < 30$) |
| **Economic Qualification Status** | **REJECTED** | **REJECTED** | **REJECTED** | **REJECTED** |

---

## 4. Key Scientific Deductions

1. **Ex-Ante EV vs Retrospective Return Separation:**
   - In 2T RUNHIGH (session `c14ac5fb`), the retrospective realized return was $+17.81\%$ ($+\$0.3563$/contract) due to a short-run cluster of 42 wins. However, the model's ex-ante predicted probability was only $0.2561$, which is below the broker's break-even hurdle of $0.2621$, resulting in a negative ex-ante expected value ($-\$0.0463$).
   - In 5T RUNHIGH, 10 wins out of 136 yielded an ex-ante EV of $+\$0.0572$ and retrospective realized return of $+\$2.4904$/contract. However, the 30.5x asymmetric payout distribution produces heavy downside volatility, leading to a conservative bootstrap lower bound of $-\$0.6529$.
2. **Defensible Risk Rejection:**
   - Because conservative bootstrap lower bounds are negative across all configurations, **no configuration qualifies for live execution**.
   - The authoritative evidence verdict remains **`NO_VALIDATED_POSITIVE_EV_EDGE` (Level 0)**.
