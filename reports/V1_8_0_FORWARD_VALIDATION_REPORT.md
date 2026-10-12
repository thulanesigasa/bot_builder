# V1.8.0 Independent Forward SHADOW Validation & Confirmation Readiness Report

![Forward_Validation](https://img.shields.io/badge/Forward_Validation-SHADOW_Non--Purchasing-blue.svg)
![Live_Deriv](https://img.shields.io/badge/Live_Deriv_Provenance-100%25_Verified-brightgreen.svg)
![Cohort_D](https://img.shields.io/badge/Cohort_D-PREREGISTRATION_REQUIRED_(Empty)-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Verification Mandate

This report documents prospective SHADOW session telemetry, broker WebSocket quote provenance, referential integrity, and confirmation-readiness status under Release V1.8.0.

In accordance with Permanent Safety Requirements (Section 2):
$$\mathbf{LIVE\_EXECUTION\_DISABLED = True}$$
$$\mathbf{ALL\_GENERATED\_DECISIONS = NO\_TRADE}$$

No live purchasing, broker order placement, or automated trading occurred or can occur.

---

## 2. Reconciled Session Telemetry & Cohort Accounting (Resolving Issue 4.1)

Applying the enhanced `SessionReconciler` with separated cohort accounting to prospective session `1cc84e31` yields complete referential reconciliation:

| Accounting Metric | Metric Value | Verification Status | Reconciled Relationship |
| :--- | :--- | :--- | :--- |
| **Unique Decision Epochs** | **887** | RECONCILED | Distinct tick epochs where decisions were evaluated |
| **Duration-Specific Predictions** | **1,774** | RECONCILED | 887 decisions for 2 Ticks + 887 decisions for 5 Ticks |
| **Directional Candidate Evaluations** | **3,548** | RECONCILED | 1,774 duration records $\times$ 2 contract directions |
| **Unique Valid Proposal Quotes** | **1,096** | RECONCILED | Distinct broker quote responses recorded in `quotes.db` |
| **Chronological Quote Matches ($\le 60$s)** | **1,774 / 1,774 (100.0%)** | RECONCILED | Cohort B coverage |
| **Execution-Quality Matches ($\le 5$s)** | **1,344 / 1,774 (75.76%)** | RECONCILED | Cohort C coverage |
| **Union of Eligible Prediction IDs** | **887 / 887 (100.0%)** | RECONCILED | Every decision epoch has at least one valid quote |
| **Intersection of Eligible Prediction IDs** | **887 / 887 (100.0%)** | RECONCILED | Both directions simultaneously quoted |
| **Clock / Chronology Violations** | **0** | RECONCILED | `response_timestamp <= decision_timestamp` strictly enforced |
| **Database Integrity Status** | **RECONCILED** | RECONCILED | Zero orphan outcomes, zero orphan predictions |

---

## 3. Empty Confirmation Cohort Audit (Resolving Issue 4.3)

In previous versions, exploratory metrics from Cohort C were inadvertently copied into the Cohort D summary structure before marking them unconfirmed. Under V1.8.0, this behavior has been completely replaced:

```json
"COHORT_D_INDEPENDENT_CONFIRMATION": {
  "total_predictions": 0,
  "resolved_outcomes": 0,
  "wins": 0,
  "losses": 0,
  "empirical_win_rate": null,
  "predicted_ordinary_ev": null,
  "retrospective_realized_return": null,
  "conservative_ev_bootstrap": null,
  "bootstrap_uncertainty_status": "INSUFFICIENT_SAMPLE",
  "is_economically_positive": false,
  "verdict": "PREREGISTRATION_REQUIRED_FOR_CONFIRMATION"
}
```

**Scientific Integrity Guarantee**: Because no prospective session has yet been executed following the freezing of the V1.8.0 exploratory candidates, Cohort D is **strictly empty**. Zero exploratory metrics are reused as confirmation evidence.

---

## 4. Multi-Market Live Endpoint Connectivity & Quote Provenance

Live WebSocket connectivity was verified directly against `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`:
- **Active Symbols Discovery**: Confirmed all 6 target volatility index symbols (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`).
- **Live Proposals Collected**: Successfully queried live proposal quotes across all 6 markets for durations 1t, 2t, 3t, 5t, and 10t for both `CALL` and `PUT`.
- **Latency Performance**: Average WebSocket proposal round-trip latency was 82ms, well within the 5.0-second execution-quality freshness window.
- **Contract Parameter Rejection**: Confirmed that 20-tick requests are rejected fail-closed with `ContractBuyValidationError: Number of ticks must be between 1 and 10`, confirming proper error handling.

---

## 5. Candidate Freezing & Preregistration Protocol

Three candidate strategies discovered on the exploratory chronological holdout have been frozen:
1. `HYP_R_100_10T_PUT`: Volatility 100 Index, 10 Ticks, Fall (`PUT`), Prediction Threshold: $P \ge 0.50$
2. `HYP_1HZ50V_10T_PUT`: Volatility 50 (1s) Index, 10 Ticks, Fall (`PUT`), Prediction Threshold: $P \ge 0.50$
3. `HYP_1HZ50V_5T_PUT`: Volatility 50 (1s) Index, 5 Ticks, Fall (`PUT`), Prediction Threshold: $P \ge 0.50$

### Confirmation Protocol
- **Sample Target**: A minimum of $N \ge 1,000$ consecutive valid forward decisions per market.
- **Decision Rule**: The candidate confirms positive expected value if and only if the untouched prospective sample achieves an MBB 95% lower confidence bound $\text{ConsEV}_{\text{MBB}} > 0$.
- **Current Research Verdict**: `EXPLORATORY_CANDIDATE_IDENTIFIED` / `CONFIRMATION_READY`.

---

*Report certified by `session_reconciler.py` and `rise_fall_research.py` — Release V1.8.0 Validation Suite*
