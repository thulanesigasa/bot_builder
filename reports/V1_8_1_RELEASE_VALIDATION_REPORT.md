# V1.8.1 Release Validation & Scientific Integrity Audit Report

![Release](https://img.shields.io/badge/Release-V1.8.1-brightgreen.svg)
![Tests](https://img.shields.io/badge/Test_Suite-100%25_Passing-brightgreen.svg)
![Integrity](https://img.shields.io/badge/Scientific_Gate-FAIL_CLOSED-blue.svg)
![Authoritative Verdict](https://img.shields.io/badge/Research_Verdict-NO_VALIDATED_POSITIVE_EV_EDGE-red.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary

Release V1.8.1 delivers an exhaustive scientific integrity repair to the Deriv Rise/Fall quantitative edge research platform. 

The primary objective of this release was to repair critical research defects identified in V1.8.0, where three unverified hypotheses (`HYP_R_100_10T_PUT`, `HYP_1HZ50V_10T_PUT`, `HYP_1HZ50V_5T_PUT`) were improperly admitted as candidates despite exhibiting negative ex-ante model-predicted expected values.

Under the corrected V1.8.1 architecture:
1. **Gate Repaired**: Predictive candidate qualification strictly requires positive ex-ante predicted EV ($\text{PredictedEV} > 0$).
2. **Candidates Rescinded**: All three V1.8.0 candidates are formally rejected with status `REJECTED_NEGATIVE_PREDICTED_EV`.
3. **Per-Observation Quote Economics**: Fixed quote assumptions ($2 / $3.91) are decoupled from candidate qualification and replaced with `quote_economics_engine.py`.
4. **Data Provenance Audited**: 1,043,184 ticks across all six target markets are cryptographically verified against persisted broker API streams (`data_provenance.py`). The apparent downward bias was proven to be short-window sample drift.
5. **Dependence-Aware Inference**: Effective sample sizes $N_{\text{eff}} = \lfloor N / D \rfloor$ and Moving-Block Bootstrap resampling resolve overlapping serial correlation.
6. **Canonical Consistency**: All 48 hypotheses are recomputed programmatically and reconciled between canonical JSON (`data/v181_multi_market_evidence.json`) and Markdown reports.
7. **Authoritative Verdict**: The platform returns `NO_VALIDATED_POSITIVE_EV_EDGE`.
8. **Permanent Safety Enforced**: `LIVE_EXECUTION_DISABLED = True` and operational decision `NO_TRADE` remain strictly active.

---

## 2. Release Provenance & Commit Metadata

| Metadata Field | Canonical Specification |
| :--- | :--- |
| **Base Release** | V1.8.0 |
| **Base Commit SHA** | `6ffa42c80e05282380f8d3e6821b0bb578df9a34` |
| **Target Release** | V1.8.1 |
| **Primary Contracts** | Rise/Fall (`CALL` / `PUT`) |
| **Research Markets** | `R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V` |
| **Contract Durations** | 2, 3, 5, 10 ticks |
| **Safety Invariant** | `LIVE_EXECUTION_DISABLED = True`, `NO_TRADE` |
| **Final Research Verdict** | `NO_VALIDATED_POSITIVE_EV_EDGE` |

---

## 3. Architecture & Modular Additions

### 3.1 `data_provenance.py`
- Audits and registers cryptographic SHA-256 hashes for all six market datasets.
- Verifies zero timestamp inversions, zero tick duplicates, and zero abnormal sampling gaps.
- Confirms source classification as `GENUINE_BROKER_API` (`ws.derivws.com/websockets/v3`).
- Generates `data/v181_data_provenance_manifest.json`.

### 3.2 `quote_economics_engine.py`
- Implements `ProposalQuoteRecord` and `PerObservationEconomicRecord`.
- Enforces strict multidimensional matching: market, direction, duration, currency, basis, and timestamps ($t_{\text{resp}} \le t_{\text{dec}}$).
- Computes per-observation break-even rates, predicted EVs, and realized returns.
- Fails closed on missing or stale quotes (`QUOTE_UNAVAILABLE`, `STALE_QUOTE`, `FUTURE_QUOTE`).
- Restricts illustrative fixed-price scenarios to `REFERENCE_ECONOMICS_ONLY` and prohibits them from satisfying candidate qualification.

### 3.3 Strict Qualification Gate in `rise_fall_research.py`
- Implements `CandidateQualificationGate.audit_candidate()`.
- Unconditionally enforces:
  $$\text{PredictedEV} > 0.0 \land \text{RealizedEV} > 0.0 \land \text{ConservativeEV}_{\text{MBB}} > 0.0 \land p_{\text{FDR}} < 0.05 \land \text{QuoteVerified}$$
- Corrects hypothesis classification into `MODEL_CONDITIONED_SIGNAL`, `UNCONDITIONAL_DIRECTIONAL_BIAS`, and `QUOTE_CONDITIONED_ECONOMIC`.

---

## 4. Reassessment of the Three V1.8.0 Candidates

| Hypothesis ID | Market / Duration | V1.8.0 Verdict | V1.8.1 Corrected Verdict | Primary Disqualifying Factors |
| :--- | :--- | :--- | :--- | :--- |
| **`HYP_R_100_10T_PUT`** | `R_100` / 10t | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | $P_{\text{mod}} = 50.41\% < 51.15\%$, PredEV = -$0.0290, Corrected $p_{\text{FDR}} = 1.0000$ |
| **`HYP_1HZ50V_10T_PUT`** | `1HZ50V` / 10t | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | $P_{\text{mod}} = 49.84\% < 51.15\%$, PredEV = -$0.0514, Corrected $p_{\text{FDR}} = 1.0000$ |
| **`HYP_1HZ50V_5T_PUT`** | `1HZ50V` / 5t | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | $P_{\text{mod}} = 50.08\% < 51.15\%$, PredEV = -$0.0418, Corrected $p_{\text{FDR}} = 1.0000$ |

---

## 5. Summary of Corrected 48 Hypotheses

Across the complete hypothesis family ($6\text{ markets} \times 4\text{ durations} \times 2\text{ directions} = 48\text{ hypotheses}$):
- **`REJECTED_NEGATIVE_EV`**: 28 hypotheses (Realized return $\le \$0.00$)
- **`REJECTED_NEGATIVE_PREDICTED_EV`**: 20 hypotheses (Model forecast EV $\le \$0.00$)
- **`CANDIDATE_IDENTIFIED`**: 0 hypotheses
- **Overall Verdict**: **`NO_VALIDATED_POSITIVE_EV_EDGE`**

---

## 6. Automated Regression & Adversarial Testing

All 372 baseline tests pass without regression. Additional comprehensive tests in `tests/test_v181_economic_integrity_repair.py` validate:
1. Rejection of strategies with negative predicted EV.
2. Positive realized EV alone cannot qualify.
3. Positive bootstrap bounds alone cannot qualify.
4. Reference pricing mode is prohibited from qualifying.
5. Missing proposal quotes fail closed (`QUOTE_UNAVAILABLE`).
6. Cross-market quote mismatches fail closed (`CROSS_MARKET_MISMATCH`).
7. Cross-duration quote mismatches fail closed (`CROSS_DURATION_MISMATCH`).
8. Future quote timestamps (lookahead) are rejected (`FUTURE_QUOTE`).
9. Overlapping serial dependence correctly inflates standard error.
10. Full SQLite integration fixture verifying end-to-end fail-closed candidate evaluation.

---

## 7. Outstanding Research Limitations

1. **Market Efficiency of Deriv Synthetics**: Over 200,000 continuous ticks, synthetic volatility indices generated by pseudorandom cryptographic algorithms behave as near-perfect symmetric martingales. Empirical drift over 5,000-tick intervals is non-persistent.
2. **Broker Margin Hurdle**: The break-even hurdle of $51.15\%$ (payout $1.955\times$) imposes a $1.15\%$ edge threshold. Simple regularized linear and tabular models on tick momentum fail to reliably cross this threshold out-of-sample.
3. **Sample Size for Forward Confirmation**: Independent prospective confirmation requires $\ge 96,000$ ticks ($\sim 53$ hours) of streaming to achieve $80\%$ statistical power at $\alpha = 0.05$. Short sessions cannot validate edges.

---

## 8. Authoritative Sign-Off

Release V1.8.1 prioritizes trustworthy scientific evidence over speculative candidate declarations. The platform correctly demonstrates that no genuine predictive edge exists in the evaluated Rise/Fall hypotheses. Permanent purchasing safety remains intact.
