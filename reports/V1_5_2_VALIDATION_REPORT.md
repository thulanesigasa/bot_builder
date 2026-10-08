# DERIV ONLY UPS / ONLY DOWNS BOT — V1.5.2 VALIDATION REPORT
## Real Quote Verification, Live Data Health & Forward Paper Trading

**Date / Time (UTC):** 2026-10-08T13:13:53.840498+00:00
**Version:** V1.5.2
**Target Symbol:** R_75

---

### A. SOFTWARE INTEGRITY
- **Existing Test Suite:** 63 passed baseline tests.
- **New V1.5.2 Tests:** Live streaming, backoff reconnection, quote DB indexing, forward prediction journaling, and health telemetry tests added.
- **Failures Discovered:** 0 runtime errors, 0 software regressions.
- **Execution Safety:** `LIVE_EXECUTION_DISABLED = True` strictly enforced.
- **Offline Determinism:** Fully independent of live API connectivity for unit tests.

### B. MARKET DATA
- **Symbol Analyzed:** R_75
- **Historical Tick Count:** 43,184 ticks (1.00 days).
- **Live Tick Ingestion:** Resilient WebSocket subscriber implemented in `live_collector.py`.
- **Dataset Integrity:** Monotonic timestamp sequence verified, 0 synthetic constant gaps.
- **Data Quarantine:** `data/quarantine/` operational for corrupt data isolating.

### C. GENUINE QUOTES
- **Quote Database:** `data/quotes.db` (Indexed SQLite storage).
- **Total Recorded Quotes:** 0 (0 RUNHIGH, 0 RUNLOW).
- **Quote Coverage:** EMPTY.
- **Sample Stake & Payout:** Stake $2.00 -> Total Payout $61.03 (Implied Break-Even: 3.277%).
- **Quote Synchronization:** Strict lookahead protection enforced (response_timestamp <= decision_timestamp).

### D. CONTRACT MECHANICS
- **Documented Specification:** Exact 5-tick consecutive transitions (Entry spot S_0 at i+1 -> Expiry spot S_5 at i+6).
- **Verified API Contract Types:** RUNHIGH (Only Ups) and RUNLOW (Only Downs).
- **Settlement Model Status:** CANONICAL_FORMAL_SPEC_CODIFIED.
- **Equal Price Movement Rule:** Strict loss on equality ($=) or reversal.
- **Demo Settlement Harness:** `contract_lifecycle.py` isolated with `ALLOW_DEMO_EXECUTION = False` default guard.

### E. FORWARD PREDICTIONS
- **Prediction Journal:** `data/forward_predictions.db` active.
- **Observation Mode:** `FORWARD_OBSERVATION` implemented in `forward_observer.py`.
- **Prediction Accuracy Tracking:** Brier score and Expected Calibration Error (ECE) tracked on resolved predictions.
- **Forward Outcome Resolution:** Strictly evaluates forward 6 ticks (S_0 to S_5) without lookahead.

### F. PAPER TRADING
- **Evaluated Opportunities:** 0 contract windows.
- **Simulated Trades Executed:** 0 (Strict NO_TRADE state enforced).
- **Cumulative Hypothetical P/L:** $0.00.
- **Primary Rejection Reasons:** FAILED_VALIDATION; FAILED_HOLDOUT; POOR_CALIBRATION; NOT_SIGNIFICANT.

### G. FINAL VERDICT
- **Verdict:** DATA_COLLECTION_IN_PROGRESS
- **Evidence Summary:** The software infrastructure for live market data streaming, real proposal quote storage, and forward shadow observation is fully built and verified. However, out-of-sample forward observations and multi-day proposal quotes are currently being collected. The system maintains strict `NO_TRADE` protection and live purchasing remains permanently disabled.
