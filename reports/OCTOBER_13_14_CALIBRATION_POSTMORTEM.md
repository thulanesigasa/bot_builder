# October 13–14 Calibration: Actual Execution Audit (October 15, 2026)

**Verdict: INCOMPLETE_EXPLORATORY_CALIBRATION.** The eight-window study did not complete.

GitHub Actions workflow history reveals **four scheduled attempts** rather than eight successful captures. Three attempts failed the prescribed 55-minute post-slot start deadline. One accepted window (#6, 2026-10-14 04:15 UTC) completed.

| GitHub workflow run | Created UTC | Outcome | Valid slot |
|---|---|---|---|
| [38358486223](https://github.com/thulanesigasa/bot_builder/actions/runs/38358486223) | Oct 13 06:45 | Window rejected | None |
| [38426253633](https://github.com/thulanesigasa/bot_builder/actions/runs/38426253633) | Oct 13 15:55 | Window rejected | None |
| [38513360880](https://github.com/thulanesigasa/bot_builder/actions/runs/38513360880) | Oct 14 04:49 | Completed | 6 |
| [38573916404](https://github.com/thulanesigasa/bot_builder/actions/runs/38573916404) | Oct 14 13:41 | Window rejected | None |

The **single accepted** capture (session `SESS_20261014_044928_4d4a85`) recorded 38 ticks, 37 proposals, 272 committed predictions, 236 resolved outcomes, all 236 internally replay-matched, 60 strictly quote-eligible resolved observations, and 36 unresolved. Original evidence is [artifact 11870398170](https://github.com/thulanesigasa/bot_builder/actions/runs/38513360880/artifacts/11870398170).

Its eight quoted contract groups have negative average *predicted* EV, notwithstanding some positive short-sample hypothetical returns. The one session cannot estimate between-day or between-session dependence. No winning contract has been confirmed.

**Study accounting:** 1/8 accepted windows, 7/8 without accepted evidence. The GitHub run listing contains 4 attempts; absence of a run for the other windows is not independent proof that no lower-level scheduler attempt occurred. There is no permissible retroactive backfill into the expired slots. The 2026 schedule has been removed from the workflow to avoid an unintended repeat in October 2027.

## Root cause and options

GitHub Actions `schedule` is best-effort and does not guarantee that a workflow will start near its cron time. With the locked start deadline, arbitrarily delayed scheduled workflows are **correctly rejected**. Increasing the allowable delay after seeing the outcomes would violate the frozen protocol. A new prospective calibration needs a reliable externally controlled trigger and a **new** preregistration identifier, checksums, start slots and audit process; it must not mix missing old slots with future captures.

The independent confirmation gate remains **not authorized**, historical six-market CSVs remain unverified, and real/demo purchases remain disabled.

## Reconciliation

`python tools/reconcile_scheduled_calibration.py` reads [the historical run ledger](calibration_20261013_14_run_ledger.json), verifies unique accepted slots and evidence pointers, and returns an explicit incomplete verdict. The ledger is a repository snapshot grounded in the GitHub run logs, not externally signed attestation.
