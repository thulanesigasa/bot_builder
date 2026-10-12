# V1.8.3.1 Economic Denominator & Cohort Separation Audit

![Cohort Separation](https://img.shields.io/badge/Accounting-COHORTS%20A%2CB%2CC%2CD-blue.svg)
![SQL Discipline](https://img.shields.io/badge/SQL%20Discipline-PRICED%20DENOMINATOR-brightgreen.svg)
![Safety Status](https://img.shields.io/badge/Execution-LIVE%20DISABLED-red.svg)
![Decision Invariant](https://img.shields.io/badge/Decision-NO%20TRADE-orange.svg)

## 1. Executive Summary & Root Cause Analysis
During the V1.8.3 release audit, a critical statistical defect was discovered in the forward economic reporting pipeline:
**The reporting queries mixed populations across unpriced and priced observations.**

In SQL:
`AVG(hypothetical_return)` evaluates only records where `hypothetical_return IS NOT NULL`, while `COUNT(*)` and `SUM(observed_outcome)` evaluate all records matching the `WHERE` clause.
Consequently:
- Total resolved sample size $N$ (e.g. 23 or 29) included observations with no quotes.
- Wins and win rates included unpriced observations.
- Mean hypothetical return was computed exclusively over a tiny subset of 1 to 5 priced observations.
- Displaying unpriced sample size $N$ alongside priced average returns created the illusion that the entire population participated in the quoted economics.

## 2. Canonical Four-Cohort Accounting Framework
To eliminate mixed economic denominators permanently, V1.8.3.1 introduces strict cohort separation:

1. **Cohort A — All Resolved Prospective Predictions**:
   - Evaluates pure directional accuracy, Brier scores, and unpriced calibration.
   - Never used for broker quote economics unless every single observation is priced.
2. **Cohort B — Chronologically Matched Broker Proposals**:
   - Genuine proposal quotes received at or before decision time matching market, contract, and duration.
3. **Cohort C — Strict Execution-Quality SHADOW Proxy**:
   - Requires valid quote, verified prospective commitment, resolved outcome, and valid entry mapping.
   - Denominator invariant: $\text{PricedWinRate} = \frac{\text{PricedWins}}{\text{PricedSampleN}}$, $\text{MeanReturn} = \frac{\sum \text{HypotheticalReturns}}{\text{PricedSampleN}}$.
4. **Cohort D — Preregistered Independent Confirmation**:
   - Quarantined for untouched forward campaigns ($N = 0$).

## 3. Discrepancy Matrix: V1.8.3 Historical Session Re-Audit
Across session `SESS_20261012_105122_f4db88` (156 resolved observations), **140 observations were unpriced**.

| Contract | Duration | Cohort A N | Cohort A Wins | Cohort A Win% | Cohort C Priced N | Cohort C Wins | Cohort C Win% | Cohort C Mean Return | Unpriced N | Unpriced Wins |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `RUNHIGH` | 2t | 29 | 7 | 24.14% | 3 | 1 | 33.33% | $0.5433 | 26 | 6 |
| `RUNHIGH` | 5t | 23 | 0 | 0.00% | 1 | 0 | 0.00% | $-2.0000 | 22 | 0 |
| `CALL` | 2t | 29 | 10 | 34.48% | 5 | 2 | 40.00% | $-0.4360 | 24 | 8 |
| `CALL` | 5t | 23 | 7 | 30.43% | 1 | 0 | 0.00% | $-2.0000 | 22 | 7 |
| `PUT` | 2t | 29 | 18 | 62.07% | 4 | 3 | 75.00% | $0.9325 | 25 | 15 |
| `PUT` | 5t | 23 | 14 | 60.87% | 2 | 2 | 100.00% | $1.9100 | 21 | 12 |

## 4. Specific Resolution of Discrepancies
- **`PUT 5t`**: V1.8.3 reported $N = 23$, Wins = 14, Mean Return = +$1.91.
  - *Reality*: Out of 23 resolved records, exactly **2 observations were priced**, both won (+$1.91 each).
  - The remaining 21 observations had no quote. Displaying $N=23$ next to +$1.91 was misleading.
  - Corrected accounting: Cohort A $N=23$ (Win rate: 60.87%), Cohort C Priced $N=2$ (Win rate: 100%, Mean return: +$1.9100).
- **`CALL 5t`**: V1.8.3 reported $N = 23$, Wins = 7, Mean Return = -$2.00.
  - *Reality*: Exactly **1 observation was priced** (0 wins, return -$2.00). 22 observations were unpriced.
- **`RUNHIGH 2t`**: V1.8.3 reported $N = 29$, Wins = 7, Mean Return = +$0.5433.
  - *Reality*: Exactly **3 observations were priced** (1 win, 2 losses, return: $\frac{5.63 - 2.00 - 2.00}{3} = +\$0.5433$). 26 observations were unpriced.

## 5. Architectural Verification
The single authoritative accounting layer `CanonicalCohortReconciler` now calculates all cohort metrics, preventing ad-hoc SQL divergence.
