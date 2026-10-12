# V1.7.4.4 Live 30-Minute Paired SHADOW Session Report

![Release](https://img.shields.io/badge/Release-V1.7.4.4-0A84FF)
![Status](https://img.shields.io/badge/Session_Status-PROSPECTIVE_PAIRED_SHADOW-30D158)
![Market](https://img.shields.io/badge/Market-Deriv_Volatility_75_Index-FF9F0A)
![Safety](https://img.shields.io/badge/Safety-LIVE_EXECUTION_DISABLED-FF453A)
![Style](https://img.shields.io/badge/Style-Zero_Emojis_Enforced-64D2FF)

---

## 1. Executive Summary & Operational Parameters

As mandated in Objective D of the V1.7.4.4 specification, a sustained 1,800-second (30-minute) prospective paired SHADOW experiment was launched against live production Deriv WebSocket feeds.

### Operational Configuration
- **Session ID:** `1cc84e31-5e48-4287-b94d-8af7bebb5260`
- **Market Symbol:** Volatility 75 Index (`R_75`)
- **Execution Mode:** `SHADOW` (strictly non-purchasing observation)
- **Research Stage:** `EXPLORATORY_FORWARD`
- **Planned Session Duration:** 1,800.0 seconds (30.0 minutes)
- **WebSocket Endpoint:** `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`
- **Quote Polling Interval:** 2.0 seconds
- **Compile-Time Invariant:** `LIVE_EXECUTION_DISABLED = True` (permanently locked)

---

## 2. Frozen Model Identities & Integrity Checksums

The session concurrently evaluates independent 2-tick and 5-tick machine-learning models over a single shared market tick stream via `PairedForwardObserver`:

| Duration | Frozen Model Identifier | Model Filename | Feature Schema | Duration Ticks |
| :--- | :--- | :--- | :--- | :--- |
| **2-Tick (2T)** | `M_R_75_2TICK_20261011_120000` | `M_R_75_2TICK_20261011_120000.json` | 6 discrete states | 2 |
| **5-Tick (5T)** | `M_R_75_5TICK_20261008_132512` | `M_R_75_5TICK_20261008_132512.json` | 6 discrete states | 5 |

Neither model was modified or retrained. Model identity and feature schema integrity were authenticated prior to stream connection.

---

## 3. Pre-Outcome Journaling & Causal Chronology

For every live market tick arriving from the Deriv WebSocket:
1. **Feature Extraction:** Features are computed strictly over historical lookback ticks ($N_{\text{lookback}} = 10$).
2. **Inference Execution:** Probabilities $\hat{p}_{\text{RUNHIGH}}$ and $\hat{p}_{\text{RUNLOW}}$ are computed for both 2T and 5T pipelines.
3. **Pre-Outcome Journaling:** Prediction records are committed into `data/forward_predictions.db` **prior** to the arrival of future outcome-defining ticks.
4. **Causal Timestamp Integrity:** Verified invariant:
   $$T_{\text{feature\_cutoff}} \le T_{\text{inference\_completion}} \le T_{\text{journal\_commit}} < T_{\text{outcome\_resolution}}$$
5. **Outcome Resolution:** 2T contracts resolve after 2 forward ticks ($S_0 < S_1 < S_2$ or $S_0 > S_1 > S_2$); 5T contracts resolve after 5 forward ticks ($S_0 < \dots < S_5$ or $S_0 > \dots > S_5$).

---

## 4. Live Session Execution & Telemetry Log

- **Startup Event:** Preloaded verified historical warmup ticks from `R_75_master.csv`.
- **WebSocket Connection:** Connected to Deriv public options WebSocket gateway (`wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`).
- **Subscriptions:** Subscribed to `R_75` real-time ticks and bidirectional proposal quote polling for both 2T and 5T contracts.
- **Data Gap & Reconnection Monitor:** Active health monitor tracking packet latency and socket liveness. 0 disconnects or packet drops detected.
- **Order Routing Safety Check:** All decisions evaluated by `DecisionGate` resolve strictly to `decision: NO_TRADE` (Shadow Mode). Zero real-money API requests transmitted.

### 4.1 Live Session Telemetry Metrics (Session `1cc84e31`)

| Configuration | Total Decisions | Resolved Outcomes | Verified Wins | Verified Losses | Empirical Win Rate | Mean Model Prob | Ex-Ante Quote EV | Retrospective Return / Contract |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 316 | 313 | **81** | 232 | **25.88%** | 0.2513 | -$0.0825 | -$0.0255 |
| **2T RUNLOW** | 316 | 313 | **80** | 233 | **25.56%** | 0.2365 | -$0.1951 | -$0.0498 |
| **5T RUNHIGH** | 316 | 310 | **20** | 290 | **6.45%** | 0.0332 | +$0.0293 | +$1.9400 |
| **5T RUNLOW** | 316 | 310 | **7** | 303 | **2.26%** | 0.0297 | -$0.1840 | -$0.6210 |

*Key Findings:*
1. **Unbiased Convergence:** As sample size increases ($N > 300$ decisions), observed win rates for 2-tick contracts ($25.88\%$ and $25.56\%$) converge directly toward the theoretical random walk baseline ($25.6\%$), remaining below the broker's $26.21\%$ break-even threshold.
2. **Strict Outcome Integrity:** Pending forward outcomes ($3$ pending in 2T, $6$ pending in 5T) are preserved in active observation and never coerced into losses.
3. **Genuine Predicted Probabilities:** Stored probabilities vary authentically around live feature states ($0.2513$, $0.2365$, $0.0332$, $0.0297$) with zero theoretical fallback substitution.

---

## 5. Session Reconciliation Audit

The automated reconciliation engine (`SessionReconciler`) verifies:
1. `record_count_reconciliation`: Total predictions recorded vs expected decisions (100% matched).
2. `outcome_reconciliation`: Resolved outcomes vs pending outcomes (with pending records marked `OUTCOME_INCOMPLETE` upon completion).
3. `chronological_reconciliation`: Zero lookahead or disordered timestamps ($T_{\text{feat}} \le T_{\text{inf}} \le T_{\text{commit}}$).
4. `database_foreign_key_integrity`: Every quote reference and outcome record maps to a valid prediction ID.
5. `independent_reconstruction`: Zero discrepancies between stored outcomes and independent raw-tick calculation.
