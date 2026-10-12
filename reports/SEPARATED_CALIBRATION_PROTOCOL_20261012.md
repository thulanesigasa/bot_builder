# Separated Exploratory Calibration — Protocol v1.9.2

## Why this is not confirmation
The prior [four-session pilot](https://github.com/thulanesigasa/bot_builder/blob/main/reports/FOUR_SESSION_SHADOW_FEASIBILITY_20261012.md) collected all four sessions consecutively and yielded only four time clusters. The within-contract hypothetical returns are dependent and the historical sample is insufficient for reliable confidence bounds or a powered independent positive-EV confirmation.

This next protocol covers **eight 75-second non-purchasing R_75 sessions**. They must start at least 60 minutes apart, across at least two distinct UTC dates. The intent is to estimate **strict quote-coverage, per-session variability and preliminary dependence**. Eight windows are a diagnostic design choice, **not a powered sample size**.

The deterministic SHA-256 manifest comes from `calibration_protocol.frozen_protocol()` and binds the model checksum, market, directions, durations, safety rules and collection budget. It does not authorize spending or turn pilot returns into confirmatory evidence.

### Acceptance criteria
1. Each planned start recorded in UTC; no duplicate, missing, reordered or closer-than-hour starts, with at least two UTC dates represented.
2. Require `SHADOW_RESEARCH_ONLY`, `LIVE_EXECUTION_DISABLED=True`, `NO_TRADE`, and **zero real/demo purchases**.
3. Record each session's connected-source proposal request identifiers, response timestamps, proposal ask/payout and all resolved/pending outcomes.
4. Verify exactly 8 session artifact manifests (or label the calibration **incomplete**). Validate unique session IDs and hashes independently.
5. Fail closed on outcome replay discrepancies; count priced/resolved strict observations separately from 2t/5t unresolved, matched/unmatched and quoted/unquoted.
6. Report means and standard deviations **per session and per contract**, quote coverage and between-session differences. Quantify uncertainty cautiously and avoid treating overlapping predictions as independent draws.
7. Never promote a retrospectively selected apparent winner or these calibration windows to a separate confirmation sample.

**Collection status:** `PROTOCOL_PREPARED_NOT_EXECUTED`. The eight windows require elapsed time across distinct days; no asynchronous eight-session campaign has been silently launched here. Do not run all eight in a single rapid GitHub Actions job because that would violate the protocol.

**Research verdict remains:** `NO_VALIDATED_POSITIVE_EV_EDGE`.
