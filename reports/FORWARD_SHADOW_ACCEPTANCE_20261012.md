# Bounded Forward SHADOW Acceptance — 2026-10-12

**Purpose:** Verify broker request-correlation, new forward data acquisition, tick outcome replay and strict cohort reconciliation. **Not** a profitability study.

## Run 1 — Collection smoke test
- Workflow: https://github.com/thulanesigasa/bot_builder/actions/runs/38255281576
- Session: `SESS_20261012_132307_249800`
- Research market: `R_75`
- Runtime: 46.50 seconds
- Genuine ticks logged: 23
- Broker proposal records: 22
- Predictions committed: 152
- Outcomes resolved: 116
- Result: `COMPLETED`; `NO_TRADE`.

## Run 2 — Tick replay and strict evidence
- Workflow: https://github.com/thulanesigasa/bot_builder/actions/runs/38255532824
- Session: `SESS_20261012_132517_1a2375`
- Research market: `R_75`
- Runtime: 46.51 seconds
- Ticks: 23
- Broker proposal records: 23
- Predictions committed: 152
- Outcomes resolved and replayed against persisted broker ticks: 116
- Independent tick replay discrepancies: **0**
- Reconciler Cohort A: 116
- Reconciler Cohort B: 39 (includes Cohort C, and may include pending quotes)
- Reconciler strict Cohort C: **30**
- Reconciler quarantined: 27; 152-116=36 unresolved, including 9 pending quote-associated observations outside the quarantine count
- Status: `TICK_REPLAY_PASS`; `NO_TRADE`.

## Offline regression
- Workflow: https://github.com/thulanesigasa/bot_builder/actions/runs/38255537459
- **457 passed** in 20.75 seconds.
- Stored-session reconciliation and fail-closed six-market historical provenance check also completed.

## Important scientific and operational limitations
- The session was **only R_75 for less than one minute**. No multi-session independence or statistical power has been established.
- `COHORT_C` is a software-evidence classification under the repository's validator, not independent proof of broker settlement, trade fill, or profitability. The current model is a deterministic research baseline.
- The quote response is now attributed using a request identifier and exact original request terms, rather than ambiguous longcodes.
- The collector's broker-origin evidence is connection/capture-based; no external cryptographic attestation of the broker message was produced.
- The six previously quarantined historical CSVs remain unverified.
- No purchases were made; `LIVE_EXECUTION_DISABLED=True`, `NO_TRADE`.

**Next step:** Freeze the software acceptance baseline and preregister longer SHADOW sessions, checking quote coverage, statistical power, missing-data reasons and contract-specific economic returns before any positive-EV claim.
