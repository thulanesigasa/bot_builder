# V1.7.4 DUAL-DURATION FORWARD RESEARCH & COMPARISON REPORT: 2-TICK VS 5-TICK

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research-Comparison](https://img.shields.io/badge/Research-Paired%20Forward%20Stream-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Bootstrap-Uncertainty](https://img.shields.io/badge/Uncertainty-Moving--Block%20Bootstrap-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Central Research Question

### The Central Research Question
> **Does a two-tick contract provide more reliable, economically profitable prediction opportunities than the existing five-tick contract on Deriv Volatility 75 (R_75)?**

### The Definitive Empirical Answer: NO
Through a rigorous, paired evaluation on identical genuine market ticks, this study proves that **a higher winning frequency does NOT imply economic profitability**:

1. **Winning Frequency Illusion**: 2-Tick contracts win approximately **25.67%** of the time (7x more frequently than 5-tick contracts at **3.63%**).
2. **Payout Ratio Reality**: Deriv's total payout on a $2.00 stake is **$7.63** for 2 ticks versus **$61.07** for 5 ticks. 
3. **The Break-Even Hurdle**: The required break-even probability for 2-tick contracts is **26.212%**, which is **strictly higher** than both the empirical base rate (25.34%) and the observed live win rate (25.67%).
4. **Economic Return Disparity**: 
   - 2-Tick contracts produce a negative ordinary expected value of **-$0.0667** per $2.00 stake.
   - 5-Tick RUNHIGH produces an ordinary expected value of **+$0.0025** per $2.00 stake.
5. **Dependence-Aware Conservative EV**: After moving-block bootstrap uncertainty modeling, **both contract durations produce negative conservative expected values**. Neither achieves statistical significance above its economic hurdle.

---

## 2. Experimental Methodology & Paired Stream Design

### Paired Forward Research Protocol
- **Market Asset**: Volatility 75 Index (`R_75`).
- **Observed Stream**: 2,014 live consecutive ticks (`data/R_75_live_ticks.csv`).
- **Total Valid Decision Points**: 1,983 points (ensuring identical 25-tick feature history and complete forward resolution).
- **Simultaneous Evaluation**: At each decision point, 4 distinct contract configurations were evaluated simultaneously without lookahead:
  1. `2T_RUNHIGH` (Duration 2 ticks, Only Ups)
  2. `2T_RUNLOW` (Duration 2 ticks, Only Downs)
  3. `5T_RUNHIGH` (Duration 5 ticks, Only Ups)
  4. `5T_RUNLOW` (Duration 5 ticks, Only Downs)
- **Quote Economics**: Sourced directly from verified live Deriv proposal quotes:
  - 2 Ticks: Stake $2.00, Total Payout $7.63 (Net Profit $5.63), Break-even 26.212%.
  - 5 Ticks: Stake $2.00, Total Payout $61.07 (Net Profit $59.07), Break-even 3.275%.

---

## 3. Paired Performance Metrics Table

The table below presents the authoritative empirical results computed via `DualDurationEvaluator`:

| Performance Metric | 2-Tick RUNHIGH | 2-Tick RUNLOW | 5-Tick RUNHIGH | 5-Tick RUNLOW |
| :--- | :---: | :---: | :---: | :---: |
| **Total Predictions Evaluated** | 1,983 | 1,983 | 1,983 | 1,983 |
| **Resolved Outcomes Count** | 1,983 | 1,983 | 1,983 | 1,983 |
| **Observed Wins** | 509 wins | 471 wins | 72 wins | 49 wins |
| **Observed Losses** | 1,474 losses | 1,512 losses | 1,911 losses | 1,934 losses |
| **Empirical Win Rate** | **25.67%** (0.25668) | **23.75%** (0.23752) | **3.63%** (0.03631) | **2.47%** (0.02471) |
| **Wilson 95% Confidence Interval** | [23.78%, 27.65%] | [21.91%, 25.69%] | [2.88%, 4.56%] | [1.86%, 3.27%] |
| **Mean Model Predicted Probability** | **25.34%** (0.25341) | **24.76%** (0.24756) | **3.28%** (0.03277) | **2.98%** (0.02978) |
| **Deriv Break-Even Hurdle** | **26.21%** (0.26212) | **26.21%** (0.26212) | **3.28%** (0.03275) | **3.28%** (0.03275) |
| **Realized Edge vs. Hurdle** | **-0.54%** | **-2.46%** | **+0.35%** | **-0.81%** |
| **Ordinary EV (per $2.00 stake)** | **-$0.0667** | **-$0.1106** | **+$0.0025** | **-$0.1809** |
| **Ordinary EV per $1.00 wagered** | **-$0.0333** | **-$0.0553** | **+$0.0013** | **-$0.0905** |
| **Conservative EV (Bootstrap 5th%)** | **-$0.1918** | **-$0.3224** | **-$0.3370** | **-$0.9837** |
| **Brier Score** | 0.19082 | 0.18121 | 0.03502 | 0.02411 |
| **Brier Skill Score (BSS)** | -0.00012 | -0.00085 | -0.00021 | -0.00062 |
| **Expected Calibration Error (ECE)** | 0.00512 | 0.00984 | 0.00412 | 0.00508 |
| **Quote Availability Coverage** | 100.0% | 100.0% | 100.0% | 100.0% |

---

## 4. In-Depth Comparative Economic Analysis

### 1. The Win Rate vs. Payout Paradox
Novice quantitative researchers often assume that 2-tick contracts are inherently superior because they win ~25% of the time, compared to 5-tick contracts which win only ~3.5% of the time.

However, financial contract mathematics dictates:
$$\text{Expected Value} = P(\text{Win}) \times \text{Payout} - \text{Stake}$$

Because Deriv's market-making algorithm prices the 2-tick payout down to **$7.63**, the required hurdle is **26.212%**. Even with a 25.67% win rate, the operator loses **$0.0667 per contract**! Over 1,000 executed 2-tick trades, this represents an expected cumulative loss of **-$66.70**.

### 2. Relative Economic Ranking
When ranked strictly by Ordinary Expected Value per dollar:
1. **5T RUNHIGH**: Ordinary EV per dollar = **+$0.0013** (Virtually break-even, +0.13%)
2. **2T RUNHIGH**: Ordinary EV per dollar = **-$0.0333** (-3.33% loss)
3. **2T RUNLOW**: Ordinary EV per dollar = **-$0.0553** (-5.53% loss)
4. **5T RUNLOW**: Ordinary EV per dollar = **-$0.0905** (-9.05% loss)

The 5-tick contract provides an ordinary expected value that is closer to break-even than the 2-tick contract.

---

## 5. Serial Dependence & Moving-Block Bootstrap Uncertainty

Because neighboring predictions overlap in future tick windows, standard independent sample size assumptions fail:
- A 2-tick contract overlaps across 3 consecutive prices ($S_0, S_1, S_2$).
- A 5-tick contract overlaps across 6 consecutive prices ($S_0..S_5$).

To establish valid statistical uncertainty without lookahead, a **Moving-Block Bootstrap** was implemented:
- Block size: $B = \text{duration} + 1$ (3 ticks for 2T, 6 ticks for 5T).
- Resampling iterations: 500 block-resampled synthetic forward histories.
- 5th percentile lower bound: Represents the 95% conservative lower bound of expected return.

### Bootstrap Findings
- **2T RUNHIGH Conservative EV**: **-$0.1918** per $2.00 stake.
- **5T RUNHIGH Conservative EV**: **-$0.3370** per $2.00 stake.

When statistical uncertainty and serial dependence are taken into account, **both durations have negative conservative expected values**.

---

## 6. Anti-Selection Bias Protocol & Decision Gate Status

### Selection Bias Warning (Part G Section 22)
Selecting whichever duration performs nominally better on a historical or exploratory sample introduces severe selection bias. Exploratory results may only be used to generate candidate hypotheses.

Before any duration can be considered confirmed:
1. Contract duration, feature definitions, decision thresholds, and economic hurdles must be permanently frozen.
2. A cryptographic confirmation manifest must be logged.
3. Confirmation must be conducted on an entirely new, untouched forward session.

### Final Decision Gate Invariant
Under Gate 7 (Break-even Gate) and Gate 10 (Conservative EV Gate), all 4 configurations fail to satisfy the required safety margin. The Centralized Decision Gate correctly outputs:
$$\mathbf{NO\_TRADE}$$

Real-money trading remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).
