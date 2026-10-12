# Scheduled Separated Calibration — Activation Record (2026-10-12)

This adds a GitHub Actions **scheduled**, non-purchasing, exploratory calibration collector.

## Immutable prospective capture windows
Eight starts are locked to the following **UTC** times, with GitHub's cron requested at those same times:

- **2026-10-13:** 00:15, 04:15, 08:15, 12:15 UTC
- **2026-10-14:** 00:15, 04:15, 08:15, 12:15 UTC

In South Africa (SAST, UTC+02): 02:15, 06:15, 10:15 and 14:15 on each day.

Each window lasts at most 55 minutes for the **start** of a single 75-second capture. Late or off-calendar runs stop without collection. GitHub Actions cron is best-effort, may be delayed or skipped, and cannot guarantee eight completed sessions. Manual workflow dispatch intentionally skips capture. Any missing session leaves calibration **incomplete**, never silently backfilled.

## Controls
- GitHub workflow: `.github/workflows/separated-calibration.yml`.
- Fixed protocol and model SHA digest derived by `calibration_protocol.frozen_protocol()`.
- R_75, CALL/PUT/RUNHIGH/RUNLOW, 2/5 tick, **SHADOW only**, no buys, `LIVE_EXECUTION_DISABLED=True`, `NO_TRADE`.
- Each scheduled run resolves its UTC slot before connecting, captures ticks/proposals and journals observations, checks independent stored-tick replay and strict quote economics, and uploads the database and results into an index-labeled GitHub artifact.
- This is **calibration**, not powered independent statistical confirmation. No retrospective winners may be promoted.
- Full study completeness, cross-session deduplication, between-day uncertainty and a valid powered sample calculation require subsequent reconciliation of all eight artifacts. A green individual workflow run does not establish study completeness.
- Scheduled workflows run on the default branch after this workflow is merged. GitHub repository Actions policies, runner availability and API access can affect execution. The schedule is not a promise of automatic analysis or a future assistant response.

## Operational note
Actions may be unavailable or disabled by repository configuration. Inspect the repository's Actions tab for the workflow runs and eight evidence artifacts. Do not change the locked clock-time schedule midway through this study or count ad-hoc reruns as preregistered windows.

**Research verdict:** `NO_VALIDATED_POSITIVE_EV_EDGE`.
