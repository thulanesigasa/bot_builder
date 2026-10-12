# Deriv Multi-Market Rise/Fall V1.8.2 — Historical Candidate Reassessment Report

![Candidate Status](https://img.shields.io/badge/Candidate%20Status-ALL%20DISQUALIFIED-red.svg)
![Live Execution](https://img.shields.io/badge/Live%20Execution-PERMANENTLY%20DISABLED-critical.svg)
![Integrity Standard](https://img.shields.io/badge/Standard-FAIL%20CLOSED-success.svg)

## 1. Historical Candidate Background
In Release V1.8.0, exploratory screening identified three potential strategy candidates:
1. `HYP_R_100_10T_PUT`
2. `HYP_1HZ50V_10T_PUT`
3. `HYP_1HZ50V_5T_PUT`

In V1.8.1, these candidates were placed in probationary quarantine due to reliance on reference pricing.
In V1.8.2, they have been comprehensively re-evaluated under strict fail-closed standards.

## 2. Candidate Reassessment Matrix
| Candidate Hypothesis | N | Win Rate | Realized EV (Ref) | Predicted EV (Ref) | Quote-Verified Verdict | Reference Verdict | Final Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HYP_R_100_10T_PUT` | 4978 | 53.84% | $0.1050 | $-0.0394 | `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE` | `REJECTED_NEGATIVE_PREDICTED_EV` | **REJECTED** |
| `HYP_1HZ50V_10T_PUT` | 4978 | 54.20% | $0.1192 | $-0.0477 | `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE` | `REJECTED_NEGATIVE_PREDICTED_EV` | **REJECTED** |
| `HYP_1HZ50V_5T_PUT` | 4984 | 53.11% | $0.0766 | $-0.0439 | `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE` | `REJECTED_NEGATIVE_PREDICTED_EV` | **REJECTED** |

## 3. Disqualification Rationale
1. **Zero Proposal Quote Evidence**:
   None of the three candidates have genuine broker proposal quotes in evidence. Under authoritative `QUOTE_VERIFIED` evaluation, all fail immediately as `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE`.
2. **Negative Model-Predicted EV**:
   Even under reference economics ($2.00 stake, $3.91 payout), all three candidates have negative predicted EV (`predicted_ev < 0.00`). The underlying feature probabilities do not support a sustainable edge over the 51.15% break-even threshold.
3. **Serial Dependence Correction**:
   Accounting for overlapping contract intervals reduces their effective sample size and deflates test statistics well below significance hurdles.
4. **Conclusion**:
   All three historical candidates are permanently rejected and disqualified from trading.
