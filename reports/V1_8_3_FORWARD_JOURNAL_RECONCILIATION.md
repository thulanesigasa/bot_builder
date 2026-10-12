# Deriv Multi-Market V1.8.3 — Forward Journal Lifecycle Reconciliation

![Observations Committed](https://img.shields.io/badge/Committed-210-blue.svg)
![Observations Resolved](https://img.shields.io/badge/Resolved-156-brightgreen.svg)
![Lifecycle Audit](https://img.shields.io/badge/Lifecycle-RECONCILED-success.svg)

## 1. Observation Lifecycle State Machine
```text
  [TICK RECEIVED]
         |
         v
  [PREDICTION COMMITTED] (Before outcome ticks)
         |
         v
  [GENUINE PROPOSAL MATCHED]
         |
         v
  [FUTURE TICKS OBSERVED]
         |
         v
  [CONTRACT OUTCOME RESOLVED]
         |
         v
  [HYPOTHETICAL RETURN CALCULATED]
```

## 2. Cohort Accounting Summary
- **Cohort A (All Prospective Predictions)**: `210` observations committed.
- **Cohort B (Proposal-Matched Observations)**: `24` observations matched with live quotes.
- **Cohort C (Execution-Quality SHADOW Proxy)**: `16` resolved with authentic returns.
- **Cohort D (Preregistered Confirmation)**: `0` observations (exploratory results strictly quarantined from confirmation).
