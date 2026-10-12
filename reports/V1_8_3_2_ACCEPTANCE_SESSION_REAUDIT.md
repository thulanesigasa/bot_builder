# V1.8.3.2 Acceptance Session Re-Audit Report

![Session ID](https://img.shields.io/badge/Session-SESS_20261012_113818_e42816-blue.svg)
![Re-Audit Verdict](https://img.shields.io/badge/Cohort%20C%20Re-Audit-28%2F28%20VERIFIED-brightgreen.svg)
![Lead Time](https://img.shields.io/badge/Mean%20Lead%20Time-%3E1000ms-lightgrey.svg)

## 1. Executive Summary
In V1.8.3.1, a 35.55-second live acceptance session (`SESS_20261012_113818_e42816`) was executed against the Deriv WebSocket API and reported 28 observations in Cohort C.

Under Section 8, this release re-audited all 28 observations using `StrictCohortAuthorityValidator` against physical source records in `data/v1831_acceptance_session.db`.

## 2. Independent Re-Audit Verification Matrix
For all 28 observations:
- **Broker Origin Evidence**: 51 genuine live broker ticks captured with native pip precision.
- **Proposal Quote Verification**: Found in `broker_proposals` table, matching symbol, contract type, duration. Quote age at decision was strictly <= 4.65s (<= 5.0s threshold).
- **Prospective Chronology**: Recorded `journal_commit_timestamp` strictly prior to `first_future_tick_receipt_ts`. Mean lead time: **1,012.4 ms**.
- **Model Provenance**: Model `BASELINE_CAUSAL_MOMENTUM_V1` verified with canonical SHA-256 `2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6`.
- **Contract Outcome Reconstruction**: Terminal comparisons and monotonic sequences reconstructed independently and matched recorded outcomes.
- **Economic Reconciliation**: Hypothetical return equals outcome times payout minus ask, reconciled within 1e-4.

## 3. Authoritative Re-Audited Telemetry
- **Total Committed Observations**: 258
- **Authoritative Cohort A (All Resolved Prospective)**: 204
- **Authoritative Cohort B (Quote-Matched)**: 36
- **Authoritative Cohort C (Strict Prospective Economic Feasibility)**: **28**
- **Quarantined Unresolved Observations**: 46

## 4. Re-Audited Hypothesis Performance Table
| Family | Contract | Duration | Cohort A N | Cohort B N | Cohort C N | Wins | Win Rate | Mean Return |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ONLY_UPS_ONLY_DOWNS` | `RUNHIGH` | 2t | 37 | 8 | 5 | 1 | 20.00% | $-0.4740 |
| `ONLY_UPS_ONLY_DOWNS` | `RUNHIGH` | 5t | 31 | 4 | 3 | 0 | 0.00% | $-2.0000 |
| `RISE_FALL` | `CALL` | 2t | 37 | 5 | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `CALL` | 5t | 31 | 6 | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `PUT` | 2t | 37 | 5 | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `PUT` | 5t | 31 | 8 | 5 | 2 | 40.00% | $-0.4360 |
