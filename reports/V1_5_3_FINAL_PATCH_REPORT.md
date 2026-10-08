# V1.5.3 FINAL SAFETY & CONNECTIVITY PATCH VALIDATION REPORT
**Deriv 5-Tick RUNHIGH / RUNLOW Quantitative Research & Data System**  
*Evaluation Timestamp: 2026-10-08T16:00:00Z*  
*Target Environment: Synthetic Volatility 75 Index (`R_75`)*  

---

## A. Software Integrity

- **Initial Test Count (Baseline)**: 84 passed (100% pass rate).
- **Final Test Count**: 97 passed (100% pass rate in 8.78s).
- **Automated Test Modules Executed**:
  - `tests/test_merge_ticks.py` (3 tests)
  - `tests/test_no_lookahead.py` (1 test)
  - `tests/test_null_test.py` (1 test)
  - `tests/test_outcome_rule.py` (3 tests)
  - `tests/test_risk_and_validation.py` (3 tests)
  - `tests/test_runhigh_runlow.py` (3 tests)
  - `tests/test_v11_engine.py` (4 tests)
  - `tests/test_v13_edge_discovery.py` (4 tests)
  - `tests/test_v14_edge_validation.py` (18 tests)
  - `tests/test_v151_statistical_integrity.py` (12 tests)
  - `tests/test_v152_live_data_and_forward.py` (11 tests)
  - `tests/test_v153_hotfix_validation.py` (10 tests)
  - `tests/test_v153_final_patch.py` (13 tests)
  - `tests/test_v15_advanced_validation.py` (11 tests)
- **Critical Defects Repaired in Final Patch**:
  1. **Issue A — Theoretical Probability Fallback Elimination**: Removed `rh_pred = 0.03125` and `rl_pred = 0.03125` when model artifacts are absent. Replaced with strictly typed `None`.
  2. **Null-Safe Propagation**: Added complete null safety to `ForwardPredictionRecord`, `ForwardPredictionJournal`, `PaperTrader`, and `decision_gate.py`. Brier scores and financial calculations now gracefully exclude records with missing predictions.
  3. **Issue B — Conservative Expected Value Enforcement**: Centralized trade authorization into `evaluate_paper_trade_eligibility(...)` in `decision_gate.py`. Implemented mandatory check requiring $\text{Conservative EV} > \text{min\_conservative\_ev}$ ($0.0$). A trade is never authorized based solely on ordinary EV.
  4. **Issue C — Deriv WebSocket Endpoint & Schema Alignment**: Identified that legacy endpoints (`ws.derivws.com`, `ws.binaryws.com`) experience timeout / edge blocking. Identified active endpoint `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`. Updated proposal schema to use `"underlying_symbol"` instead of `"symbol"`, resolving Cloudflare timeouts and validation rejections.
  5. **SQLite NOT NULL Constraint Fix**: Modified SQLite schema in `forward_journal.py` to allow `NULL` in `runhigh_pred_prob` and `runlow_pred_prob` columns.
- **Remaining Failures**: Zero (0).

---

## B. Probability Integrity

- **Hard-coded Fallback Removal**: Verified that `ForwardObserver.process_incoming_tick` produces `runhigh_pred_prob = None` and `runlow_pred_prob = None` when no model artifact is provided.
- **Missing Model Behavior**:
  - Model status is logged as `MODEL_NOT_AVAILABLE`.
  - Dependent metrics (`ev_runhigh`, `ev_runlow`, `cons_ev_runhigh`, `cons_ev_runlow`) are strictly `None`.
  - Trade decision evaluates to `NO_TRADE` with reason `MODEL_NOT_AVAILABLE`.
- **Frozen Model Inference**:
  - Validated with frozen artifact `M_R_75_5TICK_20261008_132512.json` (SHA-256 verified).
  - Employs Empirical Bayes conjugate Beta smoothing centered on historical base rates.
  - Generates statistically derived Wilson score interval lower bounds ($\alpha = 0.05$) for conservative EV analysis.
- **Feature Parity**:
  - Canonical feature schema (`v1.5.3`) with canonical ordering: `mom_bin`, `streak_bin`, `vol_bin`, `accel_bin`.
  - 100% parity verified between offline dataframe batch calculations and online sliding-window streaming state representations.

---

## C. Trading Decision Safety

- **Ordinary EV Calculation**:
  $$P_{\text{break-even}} = \frac{\text{Ask Price}}{\text{Total Payout}} = \frac{\$2.00}{\$61.07} \approx 3.275\%$$
  $$\text{EV} = (P_{\text{win}} \times \text{Payout}) - \text{Ask Price}$$
- **Conservative EV Calculation**:
  $$\text{Conservative EV} = (P_{\text{lower\_bound}} \times \text{Payout}) - \text{Ask Price}$$
  where $P_{\text{lower\_bound}}$ is derived from the Wilson score interval lower bound or model uncertainty.
- **Centralized Gate Enforcement**:
  All 10 safety gates in `decision_gate.py` are evaluated using strict `AND` logic:
  1. Execution Mode (`PAPER` required)
  2. Data Integrity (No tick gaps)
  3. Contract Family (`RUNHIGH` / `RUNLOW`, 5-tick)
  4. Model Artifact (Approved status, sample size $\ge 100$)
  5. Probability Validity ($P \in (0, 1)$, non-null)
  6. Quote Freshness ($\le 60\text{s}$)
  7. Break-even Superiority ($P_{\text{win}} > P_{\text{break-even}}$)
  8. Probability Safety Margin ($P_{\text{win}} - P_{\text{break-even}} \ge \text{margin}$)
  9. Positive Ordinary EV ($\text{EV} > 0$)
  10. Positive Conservative EV ($\text{Conservative EV} > 0$)
- **Institutional Risk Controls**:
  - Max stake $\le \$5.00$
  - Max consecutive losses $\le 3$
  - Max daily drawdown $\le 5\%$
  - Real money trading permanently locked (`LIVE_EXECUTION_DISABLED = True`, `ALLOW_DEMO_EXECUTION = False`).

---

## D. Deriv Connectivity & 8-Stage Diagnostics

Live diagnostics executed via `verify_deriv_connection.py` against `R_75`:

| Stage | Verification Target | Observed Result | Latency / Metric | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1** | DNS Hostname Resolution | Resolved `api.derivws.com` to `104.18.12.218`, `104.18.13.218` | 31.3 ms | **SUCCESS** |
| **Stage 2** | TCP Socket Handshake | Connected to Port 443 | 9.54 ms | **SUCCESS** |
| **Stage 3** | TLS 1.3 Handshake | Negotiated `TLS_AES_256_GCM_SHA384` | 65.36 ms | **SUCCESS** |
| **Stage 4** | WebSocket Upgrade | Handshake completed on `trading/v1/options/ws/public?app_id=1089` | 1804.35 ms | **SUCCESS** |
| **Stage 5** | Deriv API Response | Received `{"ping":"pong"}` & Server Epoch `1791474711` | 731.75 ms | **SUCCESS** |
| **Stage 6** | Tick Subscription | Received genuine live tick for `R_75`: Spot `45732.6103` | 120.4 ms | **SUCCESS** |
| **Stage 7** | Proposal Quotes | Live `RUNHIGH` ($2.00 $\to$ $61.07) & `RUNLOW` ($2.00 $\to$ $61.07) | 185.2 ms | **SUCCESS** |
| **Stage 8** | SQLite Persistence | Verified 2 proposal records written & retrieved from `quotes.db` | 12.1 ms | **SUCCESS** |

**Accurate Error Categorization**:
The diagnostic engine distinguishes among: `DNS_FAILURE`, `TCP_CONNECTION_FAILED`, `TLS_HANDSHAKE_FAILED`, `WEBSOCKET_HANDSHAKE_TIMEOUT`, `HTTP_520`, `HTTP_403`, `HTTP_429`, `INVALID_APP_ID`, `UNSUPPORTED_SYMBOL`, `UNSUPPORTED_CONTRACT`, `PROPOSAL_REQUEST_FAILED`, `QUOTE_VALIDATION_FAILED`, and `CONNECTION_SUCCESS`.

---

## E. Genuine Data & Database Integrity

- **Genuine Live Proposal Quotes**: Recorded and verified in `data/quotes.db`.
  - RUNHIGH Quote: Ask `$2.00`, Payout `$61.07`, Implied Break-Even `3.275%`, Proposal ID `b94a7b0f-5e8c-a725-15e3-db248543b030`.
  - RUNLOW Quote: Ask `$2.00`, Payout `$61.07`, Implied Break-Even `3.275%`, Proposal ID `78ad6720-2bce-1c62-9cb8-474e9ca8dfea`.
- **Source Isolation**: Proposal records explicitly distinguish between `quote_source = 'live_proposal'` and `quote_source = 'offline_fixture'`. Mock data is never reported as live Deriv observations.
- **Round-Trip Persistence**: SQLite commits and lookahead-protected queries (`response_timestamp <= current_epoch`) verified across restart cycles.

---

## F. Final System Status Verdict

### Verdict: **`SHADOW_VALIDATION_READY`** & **`LIVE_DATA_COLLECTION_READY`**

**Scientific Justification**:
1. Live network, WebSocket protocol, tick subscriptions, and genuine RUNHIGH/RUNLOW proposal quotes are fully functional and verified end-to-end.
2. The software correctly eliminates all theoretical fallbacks, benchmark constants, and uncalibrated predictions.
3. The centralized decision gate strictly enforces conservative EV thresholds ($\text{Conservative EV} > 0$).
4. Under empirical research on 43,184 historical ticks of `R_75`, the 5-tick base rate is ~3.288% vs 3.275% break-even, yielding negative conservative EV lower bounds across standard regimes.
5. In accordance with strict statistical standards, the model is classified as `RESEARCH_ONLY`. The forward observer safely transitions to `NO_TRADE` with `CONSERVATIVE_EV_TOO_LOW` / `NO_VALIDATED_EDGE`.
6. Live paper trading execution is withheld until a model demonstrating out-of-sample statistical edge after conservative EV adjustment is approved.
