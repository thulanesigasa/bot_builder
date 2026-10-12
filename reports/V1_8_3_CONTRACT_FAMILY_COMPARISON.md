# Deriv Multi-Market V1.8.3 — Contract Family Economic Comparison

![Comparison](https://img.shields.io/badge/Scope-Family%20A%20vs%20Family%20B-blue.svg)
![Status](https://img.shields.io/badge/Conclusion-UNDERPOWERED%20EXPLORATORY-orange.svg)

## 1. Side-by-Side Architectural & Economic Comparison
| Dimension | Family A: Rise / Fall | Family B: Only Ups / Only Downs |
| :--- | :--- | :--- |
| **Contract Directions** | `CALL`, `PUT` | `RUNHIGH`, `RUNLOW` |
| **Durations Evaluated** | 2, 3, 5, 10 ticks | 2, 5 ticks |
| **Outcome Semantics** | Terminal: $S_D > S_0$ or $S_D < S_0$ | Monotonic Path: $S_k > S_{k-1}$ on every tick |
| **Equal Spot Rule** | Strict Loss ($0$) | Strict Loss ($0$) |
| **Broker Stake / Payout (2t)** | $2.00 / $3.91 (Net 95.5%) | $2.00 / $7.63 (Net 281.5%) |
| **Broker Stake / Payout (5t)** | $2.00 / $3.91 (Net 95.5%) | $2.00 / $61.07 (Net 2953.5%) |
| **Implied Break-Even (2t)** | 51.15% | 26.21% |
| **Implied Break-Even (5t)** | 51.15% | 3.28% |
| **Empirical Win Rate (2t)** | CALL: 34.48% / PUT: 62.07% | RUNHIGH: 24.14% |
| **Empirical Win Rate (5t)** | CALL: 30.43% / PUT: 60.87% | RUNHIGH: 0.00% |
| **Sample Size Evaluated** | 104 observations | 52 observations |
| **Research Assessment** | Underpowered | Underpowered |

## 2. Key Economic Takeaway
Neither contract family has demonstrated statistically defensible or repeatable positive expected value.
While Only Ups/Downs offers massive payout multipliers (up to 30x on 5 ticks), the consecutive monotonicity constraint
is exceptionally punitive. Both contract families require extensive sample accumulation under a formal stopping plan.
