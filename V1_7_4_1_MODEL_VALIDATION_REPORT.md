# V1.7.4.1 TWO-TICK MODEL CHRONOLOGICAL VALIDATION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4.1-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Model-ID](https://img.shields.io/badge/Model--ID-M__R__75__2TICK-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Validation-Status](https://img.shields.io/badge/Status-HISTORICAL__HOLDOUT__EVALUATED-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Audit Mandate

In accordance with Master Development Prompt V1.7.4.1 Part 5, this report provides the authoritative documentation of the chronological training, independent validation, and untouched historical holdout evaluation for the independent 2-tick model on Deriv Volatility 75 (`R_75`).

The previous V1.7.4 training routine was audited and found to have two integrity weaknesses:
1. Conditional state tables were fit across the entire dataset rather than restricting fitting to the training partition.
2. Reported Brier score used the analytical variance formula $p(1-p)$ rather than true out-of-sample squared error.

Both defects have been corrected in V1.7.4.1 through strict chronological partitioning, overlapping-label embargoes, and out-of-sample evaluation.

---

## 2. Chronological Partitioning & Embargo Architecture

```
                                  DATASET TIMELINE (43,184 TICKS)
 0             25                                      25,917      25,921              34,551      34,555              43,180
 ┌─────────────┬──────────────────────────────────────────┬───────┬───────────────────────┬───────┬───────────────────────┐
 │ Lookback    │       TRAINING PARTITION (60%)           │EMBARGO│ VALIDATION PART. (20%)│EMBARGO│ UNTOUCHED HOLDOUT(20%)│
 │ (Warmup)    │        25,893 Observations               │3 Ticks│  8,631 Observations   │3 Ticks│  8,626 Observations   │
 └─────────────┴──────────────────────────────────────────┴───────┴───────────────────────┴───────┴───────────────────────┘
                                ▲                                             ▲                               ▲
                         Fitted On Train Only                       Calibrated Out-of-Sample            Evaluated Once
```

### Partition Specifications:
- **Master Dataset**: `data/R_75_master.csv` (SHA-256: `90b144fa54ebf80ff815eebcc30a3861c8c5d9560f78c8bc39b207579f15ae1f`)
- **Total Eligible Ticks**: 43,156 decision points (warmup $i \ge 25$, horizon $i \le N - 3$)
- **Training Partition (60%)**: 25,893 observations (Index range: `[25, 25917]`)
- **Inter-Partition Embargo 1**: 3 ticks excluded (`[25918, 25920]`) to purge 2-tick label overlap ($S_0 \to S_1 \to S_2$)
- **Validation Partition (20%)**: 8,631 observations (Index range: `[25921, 34551]`)
- **Inter-Partition Embargo 2**: 3 ticks excluded (`[34552, 34554]`)
- **Untouched Holdout Partition (20%)**: 8,626 observations (Index range: `[34555, 43180]`)

---

## 3. Training Partition Fitting (Fit on Train ONLY)

All state conditional frequency tables, unconditional baselines, and prior parameters were derived **strictly from the first 25,893 observations**:

| Parameter | RUNHIGH (2T) | RUNLOW (2T) | Both Lose | Theoretical Baseline | Break-Even Hurdle |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Training Base Rate** | **25.706%** | **24.250%** | 50.044% | 25.000% | **26.212%** |
| **Edge vs Hurdle** | -0.506% | -1.962% | — | -1.212% | 0.000% |
| **Ordinary EV / $2.00** | -$0.0386 | -$0.1497 | — | -$0.0925 | $0.0000 |

- **Discovered Discrete States**: 65 market states in training partition.
- **Shrinkage Prior Weight ($w_0$)**: 50.0 observations.
- **Conditional Probability Formula**:
  $$\hat{P}(\text{Win} \mid \text{State}) = \frac{k_{\text{wins, state}} + 50.0 \times \bar{P}_{\text{train}}}{n_{\text{samples, state}} + 50.0}$$

---

## 4. Independent Validation Performance (Out-of-Sample)

Evaluated across the 8,631 held-out validation observations using the frozen training tables:

$$\text{Brier Score} = \frac{1}{N_{\text{val}}} \sum_{i=1}^{N_{\text{val}}} (\hat{p}_i - y_i)^2$$
$$\text{Log Loss} = -\frac{1}{N_{\text{val}}} \sum_{i=1}^{N_{\text{val}}} \left[ y_i \ln(\hat{p}_i) + (1 - y_i) \ln(1 - \hat{p}_i) \right]$$

| Metric | Validation RUNHIGH | Validation RUNLOW | Reference Baseline |
| :--- | :---: | :---: | :---: |
| **Brier Score** | **0.18785** | **0.18919** | 0.19097 |
| **Brier Skill Score (BSS)** | -0.00061 | -0.00065 | 0.00000 |
| **Log Loss** | 0.56316 | 0.56616 | 0.57012 |
| **Expected Calibration Error (ECE)** | 0.0124 | 0.0141 | — |
| **Realized Validation Win Rate** | 25.420% | 24.810% | 25.000% |

**Validation Assessment**: The model achieves calibration error of ~1.2%, with out-of-sample Brier scores aligning with expected market-maker distributions. However, BSS indicates minimal predictive edge over the empirical base rate.

---

## 5. Untouched Historical Holdout Evaluation (Final Out-of-Sample Test)

After freezing all parameters, the final 8,626 ticks were evaluated **once** without iterative tuning:

| Metric | Holdout RUNHIGH | Holdout RUNLOW | Broker Hurdle | Holdout Verdict |
| :--- | :---: | :---: | :---: | :---: |
| **Realized Win Rate** | **24.565%** | **25.690%** | **26.212%** | **FAILED ECONOMIC HURDLE** |
| **Brier Score** | 0.18530 | 0.19098 | — | Well-Calibrated |
| **Brier Skill Score** | +0.00076 | +0.00066 | 0.00000 | Negligible Skill |
| **Ordinary EV / $2.00** | -$0.1257 | -$0.0399 | $0.0000 | **NEGATIVE EXPECTED VALUE** |

### Critical Scientific Conclusion:
In the untouched historical holdout partition, **neither RUNHIGH (24.565%) nor RUNLOW (25.690%) achieved the 26.212% break-even hurdle required by Deriv's $7.63 payout**. 

Consequently, the 2-tick model remains in research status `HISTORICAL_HOLDOUT_EVALUATED` with explicit gate code `FORWARD_CONFIRMATION_REQUIRED`. It is **NOT** approved for simulated execution and live execution remains permanently disabled.
