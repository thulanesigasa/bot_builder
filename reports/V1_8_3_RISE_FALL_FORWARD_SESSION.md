# Deriv Multi-Market V1.8.3 — Rise/Fall Forward SHADOW Session Report

![Contract Family](https://img.shields.io/badge/Family-Rise%2FFall%20(CALL%2FPUT)-blue.svg)
![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH-lightgrey.svg)
![Session Status](https://img.shields.io/badge/Session-COMPLETED-brightgreen.svg)
![Safety Decision](https://img.shields.io/badge/Decision-NO%20TRADE-orange.svg)

## 1. Executive Summary
This report presents empirical prospective telemetry for the Rise/Fall contract family (`CALL` and `PUT`)
captured live during forward SHADOW session `SESS_20261012_105122_f4db88`.
All observations were journaled prior to outcome resolution.

## 2. Rise/Fall Empirical Performance Matrix
| Contract Type | Duration | Sample N | Wins | Win Rate | Break-Even Hurdle | Mean Return | MBB 95% Bound |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `CALL` | 2t | 29 | 10 | 34.48% | 51.15% | $-0.4360 | $-2.0000 |
| `CALL` | 5t | 23 | 7 | 30.43% | 51.15% | $-2.0000 | $-2.0000 |
| `PUT` | 2t | 29 | 18 | 62.07% | 51.15% | $0.9325 | $-0.0450 |
| `PUT` | 5t | 23 | 14 | 60.87% | 51.15% | $1.9100 | $1.9100 |

## 3. Analysis & Key Findings
1. In the short sample window, random price drift produced temporary directional skew:
   - `PUT` achieved 60.87% - 62.07% win rate during downward price momentum.
   - `CALL` achieved 30.43% - 34.48% win rate over the same interval.
2. Invariant Warning: As mandated by the scientific directive, short-horizon exploratory win rates
   must NEVER be interpreted as proof of repeatable positive EV.
3. The overall Rise/Fall sample is classified as `UNDERPOWERED_EXPLORATORY_SAMPLE`.
