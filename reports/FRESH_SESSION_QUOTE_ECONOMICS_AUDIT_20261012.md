# Fresh Session Quote Economics — Provenance-Limited Audit

**Session:** `SESS_20261012_132358_cbae3d` (2026-10-12, R_75, 76.22 seconds)  
**Original evidence:** [GitHub Actions artifact 11749712071](https://github.com/thulanesigasa/bot_builder/actions/runs/38255379407/artifacts/11749712071).  
**Status:** `EXPLORATORY_QUOTE_ARITHMETIC_VERIFIED__BROKER_REQUEST_PROVENANCE_UNVERIFIED`.

## Data examined
I downloaded the actual 303,104-byte SQLite file from the unmodified artifact and inspected its `broker_ticks`, `broker_proposals`, `forward_observations` and `session_metadata` tables.

- Ticks: **38**; proposal records: **38**.
- Predictions: **272**; resolved outcomes: **236**; pending: **36**.
- Resolved records with matching stored proposal ID: **60** (not 236).
- All 60 satisfy straightforward per-observation quote-field, market/contract/duration/session, recorded timestamp, model-checksum, and hypothetical-return arithmetic comparisons.
- A prior read-only tick replay matched all **236/236** outcomes.
- No execution occurred; `SHADOW_RESEARCH_ONLY`, `NO_TRADE`.

## Priced resolved exploratory observations

| Contract | Duration | Priced N | Wins | Mean hypothetical return ($ per $2 stake) | Mean model-predicted EV ($) |
|---|---:|---:|---:|---:|---:|
| CALL | 2t | 8 | 6 | +0.9325 | -0.0597 |
| CALL | 5t | 6 | 1 | -1.3483 | -0.0450 |
| PUT | 2t | 8 | 0 | -2.0000 | -0.0303 |
| PUT | 5t | 7 | 6 | +1.3514 | -0.0534 |
| RUNHIGH | 2t | 8 | 1 | -1.0463 | -0.0734 |
| RUNHIGH | 5t | 8 | 0 | -2.0000 | -0.0862 |
| RUNLOW | 2t | 8 | 3 | +0.8612 | -0.1307 |
| RUNLOW | 5t | 7 | 0 | -2.0000 | -0.0824 |

Per-observation equations:
`break_even = proposal.ask_price / proposal.total_payout`
`predicted_ev = predicted_prob * proposal.total_payout - proposal.ask_price`
`hypothetical_return = observed_outcome * proposal.total_payout - proposal.ask_price`.

## Critical source-authority limitation

Every stored proposal's `response_timestamp - request_timestamp` is exactly **0.1 seconds**. The recorded times alone therefore do not establish a genuinely observed request/response round trip. Moreover, a later repository merge (#102) explicitly introduced stronger outstanding-request correlation, **after** this artifact was captured.

Consequently, these 60 observations are **descriptive priced SHADOW records**, not certified strict, independently attributable broker quotes. This report does not claim that broker authenticity has been independently established by having the values in SQLite. The acquired record contains hashes of selected broker payload objects, not independently signed raw frames.

**Do not silently add this session to Cohort C or D.** Collect a new session using the current correlated-request code and apply the same denominator and evidence checks.

## Research verdict
All eight groups show **negative mean model-predicted EV**. Apparent positive hypothetical returns are from tiny, overlapping samples and are not a positive-EV edge. 

`NO_VALIDATED_POSITIVE_EV_EDGE` — `INSUFFICIENT_INDEPENDENT_CONFIRMATION`.

Historical six-market CSVs remain explicitly quarantined for checksum mismatches. Never replace their companion SHA-256 values to manufacture eligibility.
