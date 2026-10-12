# V1.8.0 Market-Specific Model Comparison & Calibration Report

![Model_Audit](https://img.shields.io/badge/Model_Comparison-6_Markets_Trained-blue.svg)
![Methodology](https://img.shields.io/badge/Partitioning-Chronological_60%2F20%2F20_with_Embargo-purple.svg)
![Calibration](https://img.shields.io/badge/Brier_Score-~0.250_(Coin_Flip)-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary

This report establishes the market-specific modeling benchmarks for Rise/Fall (`CALL` / `PUT`) contracts across all six Deriv synthetic volatility index markets:
1. `R_100` — Volatility 100 Index
2. `1HZ100V` — Volatility 100 (1s) Index
3. `R_75` — Volatility 75 Index
4. `1HZ75V` — Volatility 75 (1s) Index
5. `R_50` — Volatility 50 Index
6. `1HZ50V` — Volatility 50 (1s) Index

Every model was evaluated using strict chronological partitioning:
- **Training Set**: First 60% of sequence
- **Purge/Embargo**: $D + 5$ ticks purged between partitions to prevent future-window leakage
- **Validation Set**: Next 20% of sequence
- **Holdout Test Set**: Final untouched 20% of sequence (evaluated only once)

---

## 2. Model Architecture & Baselines Evaluated

1. **Naive 50/50 Reference**: Unconditional expectation $P(\text{Rise}) = 0.50$.
2. **Unconditional Empirical Base Rate**: $P(\text{Rise}) = \bar{y}_{\text{train}}$, computed on training data.
3. **Regularized Logistic Regression**: Feature-conditioned model trained with L2 regularization on standardized causal features (1, 2, 3, 5-tick returns, 3-tick momentum, acceleration, rolling 10-tick realized volatility, directional streak length).

---

## 3. Holdout Calibration & Performance Comparison Table

| Market | Duration | Test $N$ | Observed Win Rate | Naive Brier | Base-Rate Brier | Model Brier | Model Brier Skill (BSS) | Model ECE | Model vs Hurdle (51.15%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`R_100`** | 2 Ticks | 4,988 | 48.28% | 0.250000 | 0.249920 | 0.249849 | -0.000586 | 0.0152 | -2.87% (Below Hurdle) |
| **`R_100`** | 3 Ticks | 4,987 | 48.59% | 0.250000 | 0.249920 | 0.250013 | -0.000853 | 0.0113 | -2.56% (Below Hurdle) |
| **`R_100`** | 5 Ticks | 4,984 | 47.55% | 0.250000 | 0.249942 | 0.249970 | -0.002280 | 0.0218 | -3.60% (Below Hurdle) |
| **`R_100`** | 10 Ticks | 4,979 | 48.16% | 0.250000 | 0.249959 | 0.250106 | -0.001859 | 0.0183 | -2.99% (Below Hurdle) |
| **`1HZ100V`** | 2 Ticks | 4,988 | 49.64% | 0.250000 | 0.249999 | 0.249997 | -0.000045 | 0.0036 | -1.51% (Below Hurdle) |
| **`1HZ100V`** | 3 Ticks | 4,987 | 50.15% | 0.250000 | 0.249998 | 0.250064 | -0.000266 | 0.0028 | -1.00% (Below Hurdle) |
| **`1HZ100V`** | 5 Ticks | 4,984 | 49.00% | 0.250000 | 0.249990 | 0.249993 | -0.000373 | 0.0099 | -2.15% (Below Hurdle) |
| **`1HZ100V`** | 10 Ticks | 4,979 | 49.33% | 0.250000 | 0.249996 | 0.250007 | -0.000204 | 0.0068 | -1.82% (Below Hurdle) |
| **`R_75`** | 2 Ticks | 4,988 | 50.36% | 0.250000 | 0.249987 | 0.249988 | -0.000002 | 0.0036 | -0.79% (Below Hurdle) |
| **`R_75`** | 3 Ticks | 4,987 | 49.69% | 0.250000 | 0.249990 | 0.249988 | -0.000031 | 0.0031 | -1.46% (Below Hurdle) |
| **`R_75`** | 5 Ticks | 4,984 | 50.22% | 0.250000 | 0.249995 | 0.249993 | -0.000033 | 0.0023 | -0.93% (Below Hurdle) |
| **`R_75`** | 10 Ticks | 4,979 | 50.81% | 0.250000 | 0.249934 | 0.249942 | -0.000031 | 0.0081 | -0.34% (Below Hurdle) |
| **`1HZ75V`** | 2 Ticks | 4,988 | 49.08% | 0.250000 | 0.249916 | 0.249952 | -0.000146 | 0.0092 | -2.07% (Below Hurdle) |
| **`1HZ75V`** | 3 Ticks | 4,987 | 49.81% | 0.250000 | 0.249996 | 0.250004 | -0.000032 | 0.0019 | -1.34% (Below Hurdle) |
| **`1HZ75V`** | 5 Ticks | 4,984 | 49.72% | 0.250000 | 0.249992 | 0.250014 | -0.000088 | 0.0028 | -1.43% (Below Hurdle) |
| **`1HZ75V`** | 10 Ticks | 4,979 | 49.03% | 0.250000 | 0.249906 | 0.249929 | -0.000092 | 0.0097 | -2.12% (Below Hurdle) |
| **`R_50`** | 2 Ticks | 4,988 | 49.98% | 0.250000 | 0.250000 | 0.249988 | +0.000048 | 0.0003 | -1.17% (Below Hurdle) |
| **`R_50`** | 3 Ticks | 4,987 | 49.17% | 0.250000 | 0.249931 | 0.249942 | -0.000044 | 0.0083 | -1.98% (Below Hurdle) |
| **`R_50`** | 5 Ticks | 4,984 | 50.48% | 0.250000 | 0.249977 | 0.249980 | -0.000012 | 0.0048 | -0.67% (Below Hurdle) |
| **`R_50`** | 10 Ticks | 4,979 | 49.53% | 0.250000 | 0.249978 | 0.249998 | -0.000080 | 0.0047 | -1.62% (Below Hurdle) |
| **`1HZ50V`** | 2 Ticks | 4,988 | 49.12% | 0.250000 | 0.249924 | 0.249943 | -0.000076 | 0.0088 | -2.03% (Below Hurdle) |
| **`1HZ50V`** | 3 Ticks | 4,987 | 49.49% | 0.250000 | 0.249740 | 0.249742 | -0.000008 | 0.0051 | -1.66% (Below Hurdle) |
| **`1HZ50V`** | 5 Ticks | 4,984 | 49.88% | 0.250000 | 0.249999 | 0.250020 | -0.000084 | 0.0013 | -1.27% (Below Hurdle) |
| **`1HZ50V`** | 10 Ticks | 4,979 | 49.85% | 0.250000 | 0.249998 | 0.249998 | +0.000000 | 0.0015 | -1.30% (Below Hurdle) |

---

## 4. Key Quantitative Insights

1. **Brier Score Near Theoretical Unpredictability**: Across all 24 evaluated market-duration combinations, the holdout Brier Score ranges between $0.2497$ and $0.2501$, showing that tick movements behave as an almost ideal Martingale difference sequence ($p \approx 0.50$).
2. **Negative / Zero Brier Skill Score**: The regularized logistic regression model exhibits Brier Skill Scores near zero ($BSS \in [-0.0022, +0.00005]$), confirming that rolling returns, momentum, and streak features provide negligible predictive edge over a naive 50/50 baseline.
3. **The Unforgiving Broker Hurdle**: While models achieve calibration with low ECE ($<0.02$), **not a single combination achieves an out-of-sample directional win rate exceeding the real broker break-even hurdle ($51.15\%$)**. The deficit ranges between $-0.34\%$ and $-3.60\%$.
4. **Research Conclusion**: Without structural market friction or predictable microstructural alpha, directional Rise/Fall contracts on Deriv synthetic indices are economically non-viable.

---

*Report certified by `model_rise_fall.py` — Release V1.8.0 Quantitative Modeling Suite*
