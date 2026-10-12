# Preregistered SHADOW Collection Plan — Draft / Not Yet Activated

**Purpose:** Determine whether frozen, causal baseline probabilities have positive expected hypothetical value after authentic Deriv proposal pricing on synthetic indices.

**Status:** `DRAFT_NOT_PREREGISTERED`. Publication of this draft does not imply an experiment has begun or has been statistically confirmed. The campaign must be frozen to a specific commit and plan checksum *before* collection starts.

## Safety and scope
- `LIVE_EXECUTION_DISABLED = True`, `NO_TRADE`; no buy/sell/order calls, including demo.
- Deriv synthetic indices only: `R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`, subject to independently confirmed proposal support.
- CALL/PUT and RUNHIGH/RUNLOW, durations 2t and 5t, with frozen deterministic baseline `BASELINE_CAUSAL_MOMENTUM_V1` (genuine hash recorded at experiment freeze).
- Predeclare a primary market and hypothesis before data acquisition. The remaining configurations are descriptive or belong to a declared multiplicity-adjusted family. Do not use historical wins to choose a primary outcome then call those data independent confirmation.

## Prospective contract mapping and provenance
Each observation must retain real wire-received tick identifiers and broker epochs, proposal request identifier, matched `req_id` and `echo_req`, actual request send and response receive timestamps, model/config SHA-256, durable post-write journal marker, quote expiry/freshness, model probability, ask, payout, resolved outcome and individual hypothetical return. Verify contract directions, spot precision, monotonically ordered ticks, and exact entry-to-expiry mapping. No imputed request timestamps or artificially generated network latency.

Reject missing source evidence, cross-session or cross-contract proposals, stale quotes, unverified model artifacts, incomplete tick paths and unproven pre-outcome journal commits. Calculate primary economics exclusively from strictly qualified, resolved observations. Store raw captures or adequate cryptographically hashed wire-frame lineage where permitted.

## Statistical plan (must freeze numerically before live campaign)
- Primary estimand: mean quote-matched hypothetical return per unit stake for a **single preregistered contract-market-duration candidate**, with its predicted EV recorded before outcome.
- Null: expected net hypothetical return is nonpositive. Alternative: greater than zero.
- No profitability claim unless both mean pre-outcome predicted EV and conservative, dependence-aware lower confidence bound on mean hypothetical return are greater than zero and there is an independent holdout cohort.
- Apply a prospectively selected familywise or FDR correction to secondary hypotheses; no post-hoc winning-configuration selection.
- Use dependence-aware blocks that respect overlapping tick contracts and session boundaries. Track effective sample size.
- Freeze sample-size calculations using a separately justified effect size, payout variability, dependence estimates, Type I error, desired power, and quote-coverage rate. No made-up power threshold; if inputs are unavailable, perform an explicitly exploratory feasibility pilot rather than claiming a powered confirmation.
- Freeze stopping rules in advance (fixed qualified observation count and maximum wall-clock/session budget, with safety/quality exception stops only). No optional stopping at a favorable realized return.
- Keep exploration and independent confirmation datasets separated by acquisition time and preregistration ID.
- Publish all candidate observations and exclusions, including unresolved and quoted-but-unresolved records, in the canonical denominator audit.

## Acceptance gates before activating campaign
1. Run tests and independent broker-tick replay on fresh capture.
2. Verify exact outstanding proposal requests, non-imputed send/receive times and quote freshness.
3. Reconcile strict Cohort C and prospective cohort count by contract.
4. Confirm all endpoints are non-purchasing and the code is still `NO_TRADE`.
5. Freeze model, analysis code, configuration and preregistration with commit SHA and checksums.
6. A short acceptance session is **not** an independent confirmation sample.

**Current research decision:** `NO_VALIDATED_POSITIVE_EV_EDGE`.
