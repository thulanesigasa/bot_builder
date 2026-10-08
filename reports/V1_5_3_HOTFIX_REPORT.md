# DERIV ONLY UPS / ONLY DOWNS BOT — V1.5.3 VALIDATION & HOTFIX REPORT
## Frozen Model Integration, Quote Integrity & Live API Verification

**Date / Time (UTC):** 2026-10-08T15:16:03.351299+00:00
**Version:** V1.5.3 Hotfix
**Target Symbol:** R_75

---

### A. SOFTWARE INTEGRITY
- **Test Suite:** 84 passed automated tests (74 regression baseline + 10 V1.5.3 integration tests).
- **Regression Fix A:** `runhigh_observed_win_rate` and `runhigh_brier_score` metrics fully restored in `forward_journal.py`.
- **Regression Fix B:** `inspect_recent()` restored in `forward_journal.py` returning safe, non-sensitive records.
- **Failures Discovered:** 0 runtime errors, 0 software regressions.
- **Execution Safety:** `LIVE_EXECUTION_DISABLED = True` strictly enforced.

### B. FROZEN MODEL INTEGRATION
- **Loaded Model ID:** M_R_75_5TICK_20261008_132512
- **Model Status:** RESEARCH_ONLY
- **Feature Schema Version:** 1.5.3 (Feature names: mom_bin, streak_bin, vol_bin, accel_bin).
- **Deterministic Parity:** Offline training features and online live sliding buffer verified identical.
- **Placeholder Removal:** Arbitrary fixed probabilities (0.0680, 0.03275) completely removed; probabilities are strictly evaluated from the loaded ModelArtifact.

### C. QUOTE INTEGRITY & EV ENFORCEMENT
- **Quote Database:** `data/quotes.db` (Indexed SQLite storage).
- **Recorded Real Quotes:** 0 (0 RUNHIGH, 0 RUNLOW).
- **Fallback Removal:** All historical benchmark quote fallbacks ($2 -> $61.03) completely removed from forward decisions and EV calculations.
- **Strict QUOTE_UNAVAILABLE Semantics:** Missing quotes return null ask, payout, break-even probability, and EV, strictly forcing NO_TRADE.

### D. LIVE DERIV API CONNECTIVITY
- **Diagnostic Tool:** `verify_deriv_connection.py` with multi-stage network pre-flight.
- **DNS Resolution:** Verified working (IPv4 addresses resolved).
- **TCP Handshake:** Port 443 socket connection verified (< 15 ms).
- **TLS Handshake:** Strict TLS 1.3 negotiation verified without insecure bypasses.
- **WebSocket Handshake:** Classified as `HTTP_EDGE_ERROR_520` (Cloudflare edge origin error in current environment). No false success claimed.

### E. FORWARD OBSERVATION MODES
- **Three-Mode Architecture:** DATA_COLLECTION_ONLY, SHADOW, and PAPER explicitly separated.
- **Shadow Mode Restriction:** RESEARCH_ONLY models journal shadow predictions but are strictly barred from trading.
- **Outcome Reconstruction:** Incomplete forward tick sequences marked `OUTCOME_UNVERIFIED` and never counted as losses.

### F. FINAL READINESS VERDICT
- **Verdict:** SOFTWARE_READY_API_UNVERIFIED
- **Evidence Summary:** All software systems, frozen model inference, quote integrity gates, feature parity, and safety locks are verified and pass all 84 automated tests. Live API WebSocket connection is currently blocked by Cloudflare HTTP 520 edge origin errors, preventing live quote stream collection until network access to Deriv's WebSocket gateway is restored.
