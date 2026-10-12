# Four-Session SHADOW Feasibility Pilot — 2026-10-12

## Evidence and scope
- Executed [GitHub Actions run 38261705196](https://github.com/thulanesigasa/bot_builder/actions/runs/38261705196) with fixed protocol SHA-256 `9d8146997e74d398ff5e17c93abf1befbce29214880c0ae4fed599a0738119dc`.
- Captured four consecutive **75-second R_75 sessions**, all `COMPLETED`; no purchases (`SHADOW_RESEARCH_ONLY`, `NO_TRADE`).
- Original SQLite databases and per-session replay/economic JSON: [evidence artifact 11752902458](https://github.com/thulanesigasa/bot_builder/actions/runs/38261705196/artifacts/11752902458).
- This is an exploratory feasibility pilot, **not a powered test or an independent confirmation cohort**.

## Counts

| Metric | Session 1 | Session 2 | Session 3 | Session 4 | Total |
|---|---:|---:|---:|---:|---:|
| Captured ticks | 38 | 38 | 38 | 37 | 151 |
| Proposal records | 37 | 37 | 38 | 37 | 149 |
| Predictions journaled | 272 | 272 | 272 | 264 | 1,080 |
| Outcomes resolved | 236 | 236 | 236 | 228 | 936 |
| Replay matches | 236 | 236 | 236 | 228 | 936 |
| Strict quoted/resolved | 59 | 59 | 60 | 56 | 234 |
| Unresolved observations | 36 | 36 | 36 | 36 | 144 |

All 936 resolved outcomes match broker tick records stored in the corresponding SQLite session. Local database consistency does not provide independent cryptographic broker authentication. Quote and contract criteria are those of the current validator. Do not treat overlapping predictions as 234 independent trials.

## Pooled exploratory economics

USD per quoted hypothetical $2 stake. Each average weights the matching strict-priced/resolved records in the same contract-duration group; **model-predicted EV is averaged over exactly those observations**.

| Contract | Duration | Eligible N | Wins | Mean model-predicted EV ($) | Mean hypothetical return ($) |
|---|---:|---:|---:|---:|---:|
| RUNHIGH | 2t | 32 | 10 | -0.0830 | +0.3844 |
| RUNHIGH | 5t | 28 | 0 | -0.0885 | -2.0000 |
| RUNLOW | 2t | 32 | 11 | -0.1020 | +0.6228 |
| RUNLOW | 5t | 25 | 0 | -0.0873 | -2.0000 |
| CALL | 2t | 31 | 15 | -0.0545 | -0.1081 |
| CALL | 5t | 27 | 14 | -0.0428 | +0.0274 |
| PUT | 2t | 28 | 12 | -0.0408 | -0.3243 |
| PUT | 5t | 31 | 17 | -0.0582 | +0.1442 |

All eight groups show **negative average model-predicted EV**. Three groups show positive pooled hypothetical realized return; these are small exploratory groups with overlapping observations, not statistically confirmed positive expectation. The zero-win RUNHIGH/RUNLOW 5t groups may also warrant research scrutiny, but a short run is insufficient for a robust edge/no-edge claim.

## Scientific decision and next gate

- **Pilot feasibility:** `PASS` — four live sessions, successful request/tick capture, complete stored outcome replay, nonzero strict quote coverage.
- **Confirmed profitable strategy:** `NO_VALIDATED_POSITIVE_EV_EDGE`.
- **Trading authority:** `NONE`, with `LIVE_EXECUTION_DISABLED = True` and `NO_TRADE`.
- Do not pick RUNLOW 2t (or any apparent winner) after looking at these results and call the same observations independent confirmation.
- Before a longer statistically powered campaign, choose a primary hypothesis **prospectively**, estimate realistic effective sample size and dependence from genuinely independent exploration, fix multiple-comparison treatment and stopping rules, record model/source checksums and isolate an independent confirmation horizon.
- The six historical CSVs with mismatched provenance remain excluded from authoritative research.

This file reports actual session logs and strict-cohort calculations, not purchase-equivalent P&L.
