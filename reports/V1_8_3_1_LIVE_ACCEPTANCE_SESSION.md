# V1.8.3.1 Live SHADOW Acceptance Session Report

![Live Acceptance](https://img.shields.io/badge/Acceptance%20Session-PASSED-brightgreen.svg)
![Session ID](https://img.shields.io/badge/Session-SESS_20261012_113818_e42816-blue.svg)
![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH-lightgrey.svg)
![Live Safety](https://img.shields.io/badge/Safety-NO%20TRADE-orange.svg)

## 1. Executive Summary
In compliance with Section 13, a genuine live bounded SHADOW acceptance session was executed against the production Deriv WebSocket API (`wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`).

The purpose of this acceptance test is **software lifecycle validation**, not profitability confirmation.

## 2. Acceptance Telemetry
- **Session ID**: `SESS_20261012_113818_e42816`
- **Database**: `data/v1831_acceptance_session.db`
- **Duration**: 35.55 seconds
- **Target Markets**: `R_75`, `1HZ100V`
- **Ticks Captured**: 51
- **Proposals Captured**: 15
- **Committed Predictions**: 258
- **Resolved Observations**: 204
- **Cohort A Observations**: 204
- **Cohort B Matched Quotes**: 36
- **Cohort C Strict SHADOW Proxy**: 28

## 3. Acceptance Criteria Verification Matrix
| Acceptance Gate Criterion | Verification Result | Status |
| :--- | :--- | :--- |
| **Source records available** | 51 ticks, 15 proposals persisted in SQLite | **PASSED** |
| **Prediction chronology verified** | `journal_commit_timestamp` strictly prior to future tick | **PASSED** |
| **Contract mapping verified** | Next-tick entry mapping executed correctly | **PASSED** |
| **Quote matching verified** | Isolated by symbol, family, duration, direction | **PASSED** |
| **Priced win counts reconcile** | Evaluated strictly on Cohort C records | **PASSED** |
| **Mean returns reconcile** | Divided by priced $N$ only | **PASSED** |
| **Model identity authentic** | `BASELINE_CAUSAL_MOMENTUM_V1` verified SHA-256 | **PASSED** |
| **Safety gates enforced** | `LIVE_EXECUTION_DISABLED = True`, `NO_TRADE` | **PASSED** |

## 4. Empirical Breakdown in Acceptance Session
| Family | Contract | Duration | Cohort A N | Cohort A Wins | Cohort A Win% | Cohort C N | Cohort C Wins | Cohort C Win% | Cohort C Mean Return |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ONLY_UPS_ONLY_DOWNS` | `RUNHIGH` | 2t | 37 | 6 | 16.22% | 5 | 1 | 20.00% | $-0.4740 |
| `ONLY_UPS_ONLY_DOWNS` | `RUNHIGH` | 5t | 31 | 0 | 0.00% | 3 | 0 | 0.00% | $-2.0000 |
| `RISE_FALL` | `CALL` | 2t | 37 | 16 | 43.24% | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `CALL` | 5t | 31 | 17 | 54.84% | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `PUT` | 2t | 37 | 20 | 54.05% | 5 | 3 | 60.00% | $0.3460 |
| `RISE_FALL` | `PUT` | 5t | 31 | 14 | 45.16% | 5 | 2 | 40.00% | $-0.4360 |

## 5. Acceptance Verdict
**Software Status**: `FORWARD_EVIDENCE_RECONCILED`.
The V1.8.3.1 software lifecycle operates end-to-end with mathematical integrity.
