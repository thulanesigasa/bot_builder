# Deriv Multi-Market Rise/Fall V1.8.2 — Forward Research Readiness Plan

![Readiness Status](https://img.shields.io/badge/Forward%20Research-READY%20FOR%20SHADOW-blue.svg)
![Safety Invariant](https://img.shields.io/badge/Live%20Purchasing-DISABLED-red.svg)
![Protocol](https://img.shields.io/badge/Protocol-SHADOW%20COLLECTION-lightgrey.svg)

## 1. Objective of Prospective Forward Research
To transition from retrospective historical research to authoritative prospective research,
the platform requires genuine, simultaneous proposal quote streams for Rise/Fall contracts.

## 2. Required Infrastructure for Next Stage
1. **Live Quote Recorder (`quote_recorder.py`) Enhancement**:
   Extend continuous WebSocket subscription to request live `proposal` objects for:
   - Symbols: `R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`
   - Contracts: `CALL`, `PUT`
   - Durations: `2`, `3`, `5`, `10` ticks
2. **Synchronous Observation Pairing**:
   Store exact broker proposal ask price, payout, quote timestamp, and proposal ID alongside incoming spot ticks.
3. **Automated Journaling**:
   Every prospective signal must journal its entry quote, subsequent settlement ticks, and realized economic outcome in `forward_journal.db`.

## 3. Non-Purchasing SHADOW Protocol
- All prospective collection operates strictly with `LIVE_EXECUTION_DISABLED = True`.
- No trades will be purchased.
- Minimum data collection hurdle: 5,000 paired quote observations per symbol/duration before prospective qualification is attempted.
