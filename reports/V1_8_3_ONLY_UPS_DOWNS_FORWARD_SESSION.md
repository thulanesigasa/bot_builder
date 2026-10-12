# Deriv Multi-Market V1.8.3 — Only Ups / Only Downs Forward SHADOW Session Report

![Contract Family](https://img.shields.io/badge/Family-Only%20Ups%2FOnly%20Downs-blue.svg)
![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH-lightgrey.svg)
![Contract Semantics](https://img.shields.io/badge/Semantics-Monotonic%20Path-purple.svg)
![Safety Decision](https://img.shields.io/badge/Decision-NO%20TRADE-orange.svg)

## 1. Executive Summary
This report presents empirical prospective telemetry for the Only Ups / Only Downs contract family (`RUNHIGH` and `RUNLOW`)
captured live during forward SHADOW session `SESS_20261012_105122_f4db88`.
Contracts require consecutive successive movements on every tick.

## 2. Only Ups / Only Downs Empirical Performance Matrix
| Contract Type | Duration | Sample N | Wins | Win Rate | Break-Even Hurdle | Mean Return | MBB 95% Bound |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `RUNHIGH` | 2t | 29 | 7 | 24.14% | 26.21% | $0.5433 | $-2.0000 |
| `RUNHIGH` | 5t | 23 | 0 | 0.00% | 3.27% | $-2.0000 | $-2.0000 |

## 3. Analysis & Key Findings
1. `RUNHIGH` 2-tick:
   - Empirical win rate: 24.14% vs break-even hurdle of 26.21% ($2.00 / $7.63).
   - Realized average return: +$0.5433 (small sample variance).
2. `RUNHIGH` 5-tick:
   - Empirical win rate: 0.00% (0 wins in 23 observations) vs break-even hurdle of 3.28% ($2.00 / $61.07).
   - Realized average return: -$2.0000.
   - Requiring 5 strictly successive upward ticks without a single reversal or equal spot is a severe hurdle.
3. The contract family remains classified as `UNDERPOWERED_EXPLORATORY_SAMPLE`.
