# Request-Correlated Fresh SHADOW Acceptance — October 12, 2026

**Evidence:** [Live GitHub Actions run](https://github.com/thulanesigasa/bot_builder/actions/runs/38258381211), [artifact ZIP](https://github.com/thulanesigasa/bot_builder/actions/runs/38258381211/artifacts/11751266707).

## Acquired live session

Session `SESS_20261012_134926_73f625` collected non-purchasing Deriv R_75 data for 76.31 seconds.

- 38 market ticks; 38 proposal response records, all with distinct proposal IDs.
- 272 prospective prediction rows; 236 resolved; 36 unresolved.
- Read-only independent outcome replay: **236 / 236 match the persisted broker tick sequence**; no mismatches or missing replay ticks.
- Current request-correlation implementation and strict cohort validator report **60 strictly eligible priced, resolved observations**, plus 8 pending with matched quotes.
- The 38 recorded proposal request-to-response latencies are **positive, nonconstant**, ranging approximately **0.0790 to 0.1850 seconds**; 36 distinct differences to four decimals. This eliminates the identical 0.1s timestamp anomaly found in the earlier October 12 session.
- Real matched request attribution still relies on local captured records and request IDs, not an external signed broker attestation.
- The attached SQLite DB remains an artifact, not a committed historical dataset.

## Quote-matched economics (USD, $2 illustrative stake, not purchases)

| Direction | Duration | Strict priced N | Wins | Mean model-predicted EV ($) | Mean hypothetical return ($) |
|---|---:|---:|---:|---:|---:|
| CALL | 2 ticks | 8 | 4 | -0.074325 | -0.0450 |
| CALL | 5 ticks | 6 | 1 | -0.045000 | -1.3483 |
| PUT | 2 ticks | 8 | 5 | -0.045000 | +0.4438 |
| PUT | 5 ticks | 7 | 4 | -0.019864 | +0.2343 |
| RUNHIGH | 2 ticks | 8 | 2 | -0.111575 | -0.0925 |
| RUNHIGH | 5 ticks | 8 | 0 | -0.080875 | -2.0000 |
| RUNLOW | 2 ticks | 8 | 3 | -0.092500 | +0.8613 |
| RUNLOW | 5 ticks | 7 | 0 | -0.088509 | -2.0000 |

Each row uses the **same priced, resolved observation population** for wins, predicted EV and hypothetical mean return. Contract group observations overlap in tick time and cannot be treated as independent repetitions.

**All eight mean model-predicted EV values are negative**. Some tiny observed hypothetical returns are positive but do not validate a positive-EV trading edge.

## Research status

- Software: small, correlated-request live SHADOW lifecycle and repeatable price-level economics passed.
- Statistical status: `UNDERPOWERED_EXPLORATORY_SAMPLE`.
- Broker attestation: not independently signed.
- Hypothesis confirmation: none; `NO_VALIDATED_POSITIVE_EV_EDGE`.
- Long campaign: **not activated**. Draft preregistration must first freeze primary hypothesis, model checksum, significance threshold, dependence-aware power/stopping plan, and confirmation holdout design.
- Safety: `LIVE_EXECUTION_DISABLED = True`, `NO_TRADE`. No real or demo purchases.

These results must not be represented as execution-equivalent returns or guaranteed profits.
