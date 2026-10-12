# Fresh SHADOW Acceptance and Tick Replay — 2026-10-12

This document records GitHub Actions outputs on commit `fc75ba1533c7f4cd482cf6a57d7fae4e172b3052`.

## Offline audits
- Full pytest suite: **453 passing** (see [offline workflow](https://github.com/thulanesigasa/bot_builder/actions/runs/38255385990)).
- Historical forward prediction DB: **156/156** resolved outcomes reconstruct from stored broker ticks; 54 remain pending.
- Previous acceptance DB: **204/204** resolved outcomes reconstruct from stored broker ticks; 54 remain pending.
- This is internal source-table replay, **not independent authentication** of the market data.

## Fresh live, non-purchasing SHADOW session
- Workflow: [live acceptance run](https://github.com/thulanesigasa/bot_builder/actions/runs/38255379407)
- Session ID: `SESS_20261012_132358_cbae3d`
- Start: `2026-10-12T13:23:58.261889+00:00`
- End: `2026-10-12T13:25:14.477996+00:00`
- Runtime: **76.22 seconds**
- Target market: `R_75`
- Captured market ticks: **38**
- Proposal response records: **38**
- Predictions journaled: **272**
- Resolved hypothetical outcomes: **236**
- Unresolved at session termination: **36**
- Independent replay: **236/236 matching**, **0 mismatches**, **0 unverifiable**.
- Operating mode: `SHADOW_RESEARCH_ONLY`; decision `NO_TRADE`.
- Evidence artifact: [fresh-shadow-acceptance](https://github.com/thulanesigasa/bot_builder/actions/runs/38255379407/artifacts/11749712071).

The run demonstrates a fresh connected tick/proposal/journal lifecycle and internal tick-based outcome reconciliation. It **does not** establish individually valid quote matches, Cohort C counts, exchange-independent source authentication, execution-equivalent settlement, statistically meaningful positive EV or profitability. Those must be assessed separately from the captured evidence.

## Required next gate
1. Independently replay quoted observations against raw request/response context and verify quote freshness, contract parameters, prices, model identity, and durable prediction commitment.
2. Quantify strict Cohort C eligible observations, and report both quote coverage and contract-by-contract hypothetical EV.
3. Freeze a preregistered sampling and stopping plan before any long campaign.
4. Historical tick CSVs with mismatched companion SHA-256 remain quarantined. Never retrofit their stored provenance.
5. This pipeline **must not** execute real or demo purchases.
