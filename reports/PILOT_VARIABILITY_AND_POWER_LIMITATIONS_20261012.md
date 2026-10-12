# Pilot return variability and independent-confirmation power limitations

Evidence: [4-session artifact 11752902458](https://github.com/thulanesigasa/bot_builder/actions/runs/38261705196/artifacts/11752902458). Downloaded source SQLite and quote-economics manifests were analyzed from the actual artifact.

**Total strict priced resolved observations: 234.** All observations arose from four consecutive ~75-second R_75 SHADOW sessions. Market outcomes and proposal economics are shared in time across contract types and durations, so rows cannot be assumed independent.

| Contract | Duration | Priced n | Sample return standard deviation ($ / $2 hypothetical stake) | Session mean hypothetical returns ($) |
|---|---:|---:|---:|---|
| CALL | 2 ticks | 31 | 1.986 | -1.022, +0.444, +0.932, -0.883 |
| CALL | 5 ticks | 27 | 1.991 | -0.324, -0.324, +1.258, -0.324 |
| PUT | 2 ticks | 28 | 1.970 | -0.324, +0.793, -1.511, -0.045 |
| PUT | 5 ticks | 31 | 1.978 | -0.045, +0.444, +0.234, -0.045 |
| RUNHIGH | 2 ticks | 32 | 3.593 | +1.815, +1.815, -1.046, -1.046 |
| RUNHIGH | 5 ticks | 28 | 0.000 | -2.000, -2.000, -2.000, -2.000 |
| RUNLOW | 2 ticks | 32 | 3.682 | +0.861, -1.046, +2.769, -0.093 |
| RUNLOW | 5 ticks | 25 | 0.000 | -2.000, -2.000, -2.000, -2.000 |

These are **descriptive sample standard deviations**, not valid independent-observation standard errors or a block-bootstrap power analysis. In particular, zero observed wins on 5-tick contracts **does not mean zero underlying outcome variance**. Four consecutive session clusters do not establish stable intersession variation, decorrelation time, or exchange-regime coverage.

## Research gate

1. `CONFIRMATION_NOT_AUTHORIZED` remains required. No defensible powered sample size or alpha-spending plan has been established.
2. The first longer data-acquisition step, if desired, must be declared **separate exploratory variance/quote-throughput calibration**, not independent confirmatory testing. Freeze its budget and stop rules before starting.
3. Do not retrospectively nominate the best-performing pilot direction as a primary hypothesis and treat these same records as holdout confirmation.
4. Preserve broker-source authenticity limitations, correct quote-matched denominators, and `LIVE_EXECUTION_DISABLED = True` / `NO_TRADE`.
5. Run `python tools/pilot_variability_diagnostics.py --pilot-dir <unzipped-pilot-artifact> --output pilot-variability.json` to reproduce these sample summaries from the four authenticated-to-repository evidence databases; keep the original artifact ZIP and its provenance separately.

**Current verdict:** `NO_VALIDATED_POSITIVE_EV_EDGE`.
