# V1.7.4.4 Live 30-Minute Paired SHADOW Session Report

![Release](https://img.shields.io/badge/Release-V1.7.4.4-0A84FF)
![Status](https://img.shields.io/badge/Session_Status-COMPLETED_1800s_RECONCILED-30D158)
![Market](https://img.shields.io/badge/Market-Deriv_Volatility_75_Index-FF9F0A)
![Safety](https://img.shields.io/badge/Safety-LIVE_EXECUTION_DISABLED-FF453A)
![Evidence_Ladder](https://img.shields.io/badge/Verdict-NO_VALIDATED_POSITIVE_EV_EDGE-FF453A)
![Style](https://img.shields.io/badge/Style-Zero_Emojis_Enforced-64D2FF)

---

## 1. Executive Summary & Operational Parameters

As mandated in Objective D of the V1.7.4.4 specification, a sustained 1,800-second (30-minute) prospective paired SHADOW experiment was launched, fully completed, and reconciled against live production Deriv WebSocket feeds.

### Operational Parameters
- **Session ID:** `1cc84e31-5e48-4287-b94d-8af7bebb5260`
- **Market Symbol:** Volatility 75 Index (`R_75`)
- **Execution Mode:** `SHADOW` (strictly non-purchasing observation)
- **Research Stage:** `EXPLORATORY_FORWARD`
- **Session Duration:** 1,800.0 seconds (30.0 minutes) — 100% completed
- **WebSocket Endpoint:** `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`
- **Quote Polling Interval:** 2.0 seconds
- **Compile-Time Safety Guard:** `LIVE_EXECUTION_DISABLED = True` (permanently locked)
- **Total Market Ticks Captured:** 898 (0 gaps, 0 duplicates)
- **Total Decision Points:** 1,774 (887 decisions per duration)
- **Total Resolved Outcomes:** 1,774 (887 resolved per duration)
- **Pending Outcomes at Termination:** 0 (all resolved within closure grace window)
- **Total Matched Quotes:** 1,096 (100.0% chronological validity)

---

## 2. Frozen Model Identities & Integrity Checksums

The session concurrently evaluated independent 2-tick and 5-tick machine-learning models over a single shared market tick stream via `PairedForwardObserver`:

| Duration | Frozen Model Identifier | Model Filename | Feature Schema | Duration Ticks | Model Checksum (SHA-256) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2-Tick (2T)** | `M_R_75_2TICK_20261011_120000` | `M_R_75_2TICK_20261011_120000.json` | 6 discrete states | 2 | `943def871f3a4e6b...` |
| **5-Tick (5T)** | `M_R_75_5TICK_20261008_132512` | `M_R_75_5TICK_20261008_132512.json` | 6 discrete states | 5 | `e038fb5efa788d46...` |

Neither model was modified or retrained. Model identity and feature schema integrity were authenticated prior to stream connection.

---

## 3. Pre-Outcome Journaling & Causal Chronology

For every live market tick arriving from the Deriv WebSocket:
1. **Feature Extraction:** Features were computed strictly over historical lookback ticks ($N_{\text{lookback}} = 10$).
2. **Inference Execution:** Probabilities $\hat{p}_{\text{RUNHIGH}}$ and $\hat{p}_{\text{RUNLOW}}$ were computed for both 2T and 5T pipelines.
3. **Pre-Outcome Journaling:** Prediction records were committed into `data/forward_predictions.db` **prior** to the arrival of future outcome-defining ticks.
4. **Causal Timestamp Integrity:** Verified invariant across all 1,774 records:
   $$T_{\text{feature\_cutoff}} \le T_{\text{inference\_completion}} \le T_{\text{journal\_commit}} < T_{\text{outcome\_resolution}}$$
5. **Outcome Resolution:** 2T contracts resolved after 2 forward ticks ($S_0 < S_1 < S_2$ or $S_0 > S_1 > S_2$); 5T contracts resolved after 5 forward ticks ($S_0 < \dots < S_5$ or $S_0 > \dots > S_5$).

---

## 4. Authoritative Performance & Statistical Matrix (1,800-Second Session)

Evaluated under `QUOTE_VERIFIED` mode with authentic stored predictions and verified broker proposals:

| Metric Property | 2T RUNHIGH | 2T RUNLOW | 5T RUNHIGH | 5T RUNLOW |
| :--- | :--- | :--- | :--- | :--- |
| **Total Prediction Records** | 887 | 887 | 887 | 887 |
| **Resolved Outcomes** | 887 | 887 | 887 | 887 |
| **Incomplete / Pending Records** | 0 | 0 | 0 | 0 |
| **Data-Gap Records** | 0 | 0 | 0 | 0 |
| **Verified Wins** | **219** | **226** | **33** | **32** |
| **Verified Losses** | **668** | **661** | **854** | **855** |
| **Empirical Win Rate** | **24.69%** | **25.48%** | **3.72%** | **3.61%** |
| **Wilson 95% Confidence Interval** | [21.97%, 27.63%] | [22.72%, 28.45%] | [2.66%, 5.18%] | [2.57%, 5.05%] |
| **Mean Authentic Model Probability** | **0.2514** | **0.2364** | **0.0329** | **0.0298** |
| **Calibration Error (ECE)** | 0.0092 | 0.0184 | 0.0043 | 0.0063 |
| **Brier Score** | 0.1864 | 0.1902 | 0.0359 | 0.0348 |
| **Broker Break-Even Hurdle** | 0.2621 (26.21%) | 0.2621 (26.21%) | 0.0328 (3.28%) | 0.0328 (3.28%) |
| **Mean Quote Ask Price** | $2.00 | $2.00 | $2.00 | $2.00 |
| **Mean Quote Total Payout** | $7.63 | $7.63 | $61.07 | $61.07 |
| **Ex-Ante Quote Expected Value (EV)** | **-$0.0815** | **-$0.1960** | **+$0.0078** | **-$0.1791** |
| **Retrospective Realized Return / Contract** | **-$0.1162** | **-$0.0559** | **+$0.2721** | **+$0.2032** |
| **Conservative Bootstrap EV (95% MBB)** | **-$0.3488** | **-$0.2796** | **-$0.6264** | **-$0.8984** |
| **Bootstrap Sample Status** | SUFFICIENT | SUFFICIENT | SUFFICIENT | SUFFICIENT |
| **Economic Qualification Status** | **REJECTED** | **REJECTED** | **REJECTED** | **REJECTED** |
| **Evidence Ladder Verdict** | Level 0 | Level 0 | Level 0 | Level 0 |

---

## 5. Automated Session Reconciliation Engine Audit

The automated reconciliation engine (`SessionReconciler`) performed multi-index verification:

```
================================================================================
SESSION RECONCILIATION AUDIT [1cc84e31-5e48-4287-b94d-8af7bebb5260]
Status: RECONCILED (Verified: True)
Reconciled At: 2026-10-12T06:36:43+00:00

--- SEPARATED INTEGRITY DIMENSIONS ---
  Data Counts Reconciled : True
  Pred Chronology Verif  : True
  Outcome Reconstruct Ver: True
  Quote Chronology Verif : True
  Contract Mapping Verif : True
  Economic Evidence Elig : True

--- TICK ACCOUNTING ---
  Session Ticks     : 898
  Live Ticks        : 887
  Warm-up Ticks     : 0
  Duplicate Ticks   : 0
  Rejected Ticks    : 0
  CSV File Ticks    : 898

--- PREDICTION & OUTCOME ACCOUNTING ---
  Total Predictions : 1774
  Resolved Outcomes : 1774
  Pending Outcomes  : 0
  Incomplete/Gaps   : 0
  Orphan Outcomes   : 0
  Orphan Preds      : 0

--- QUOTE ACCOUNTING & CHRONOLOGY ---
  Quotes for Session: 1096
  Raw Coverage      : 100.0% (1774/1774)
  Chrono Valid Cov  : 100.0% (1774/1774)
  Economic Eval Cov : 100.0% (1774/1774)
  Execution Quality : 75.8% (1344/1774)

--- PROVENANCE & CHRONOLOGY ---
  Live Deriv Source : True
  Chronology Errors : 0
  Future Quotes     : 0
  Missing Resp Time : 0

--- VERDICT: ALL CHECKS PASSED (RECONCILED) ---
================================================================================
```

---

## 6. Scientific Findings & Strategy Deductions

1. **Law of Large Numbers Confirmation**:
   - In short sessions (e.g. 300s session `c14ac5fb`), small sample clustering produced temporary win rates of $30.88\%$ in 2T RUNHIGH.
   - Over the complete 1,800-second session ($887$ decisions per configuration), empirical win rates converged tightly to theoretical baseline expectations:
     - 2T RUNHIGH: **24.69%** (vs 25.0% baseline)
     - 2T RUNLOW: **25.48%** (vs 25.0% baseline)
     - 5T RUNHIGH: **3.72%** (vs 3.125% baseline)
     - 5T RUNLOW: **3.61%** (vs 3.125% baseline)
2. **Defensive Rejection of Capital Allocation**:
   - Neither 2-tick direction cleared the broker's break-even hurdle ($26.21\%$). Both produced negative ex-ante EV ($-\$0.0815$ and $-\$0.1960$).
   - For 5T RUNHIGH, while marginal ordinary EV was positive ($+\$0.0078$), the Moving-Block Bootstrap 95% lower bound was $-\$0.6264$, failing conservative risk hurdles.
   - The authoritative evidence verdict across all durations and directions remains **Level 0 (`NO_VALIDATED_POSITIVE_EV_EDGE`)**.
3. **Safety Protection**:
   - Zero real-money API requests were placed. `LIVE_EXECUTION_DISABLED = True` remained actively enforced throughout the entire 30-minute test.
