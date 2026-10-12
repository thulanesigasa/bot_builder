# V1.8.1 Root Cause & Gate Repair Report: Negative Predicted EV Defect Resolution

![Gate Status](https://img.shields.io/badge/Gate_Status-REPAIRED_FAIL_CLOSED-brightgreen.svg)
![Predicted EV Rule](https://img.shields.io/badge/Predicted_EV_Rule-P_model_%3E_BreakEven-blue.svg)
![V1.8.0 Candidates](https://img.shields.io/badge/V1.8.0_Candidates-ALL_REJECTED-red.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary

In Release V1.8.0, an exploratory multi-market quantitative research engine was introduced to discover potential positive-expected-value (EV) opportunities across six synthetic volatility indices (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`) and four contract durations (2, 3, 5, 10 ticks).

The previous release reported three exploratory candidate hypotheses:
1. `HYP_R_100_10T_PUT`
2. `HYP_1HZ50V_10T_PUT`
3. `HYP_1HZ50V_5T_PUT`

An independent audit of the qualification logic revealed a critical architectural defect: **the candidate qualification gate admitted trading strategies whose ex-ante model-predicted expected value was negative.** The strategies qualified solely because retrospective holdout sample win rates happened to exceed the broker's break-even hurdle ($51.15\%$).

Release V1.8.1 repairs this flaw by establishing an authoritative, centralized gate requiring strictly positive predicted EV ($\text{PredictedEV} > 0$) alongside positive realized return, positive conservative bootstrap bounds, dependence-aware statistical significance, and authentic quote verification.

---

## 2. Mathematical Definition of the V1.8.0 Defect

In Rise/Fall binary options on Deriv:
- Contract Stake: $\text{AskPrice} = \$2.00$
- Contract Payout: $\text{TotalPayout} = \$3.91$
- Broker Break-Even Probability:
  $$\text{BreakEven} = \frac{\text{AskPrice}}{\text{TotalPayout}} = \frac{2.00}{3.91} \approx 0.51150895 \quad (51.15\%)$$

The model forecasts an ex-ante probability $P_{\text{model}}$ before the contract commences.
- Model Predicted Expected Value:
  $$\text{PredictedEV} = (P_{\text{model}} \times \text{TotalPayout}) - \text{AskPrice} = 3.91 \times P_{\text{model}} - 2.00$$
- Empirical Realized Expected Value:
  $$\text{RealizedEV} = (\text{WinRate}_{\text{emp}} \times \text{TotalPayout}) - \text{AskPrice} = 3.91 \times \text{WinRate}_{\text{emp}} - 2.00$$

### The Defective V1.8.0 Gate Logic

In V1.8.0 `rise_fall_research.py` (lines 220–223), candidate admission was decided by:
```python
is_pos = (raw["realized_ev"] > 0 and cons_ev is not None and cons_ev > 0)
if is_sig and is_pos:
    verdict = "CANDIDATE_IDENTIFIED"
```

Notice that `raw["predicted_ev"]` was calculated but **completely omitted from the qualification condition**.

As a consequence, when a model predicted a probability below the break-even hurdle ($P_{\text{model}} < 51.15\%$, $\text{PredictedEV} < 0$), but the test sample experienced a short-window downward drift resulting in an empirical win rate above $51.15\%$, the gate declared `CANDIDATE_IDENTIFIED`.

### The Three Falsely Qualified V1.8.0 Candidates

| Hypothesis ID | Market | Duration | Direction | Model Prob ($P_{\text{mod}}$) | Break-Even Hurdle | Predicted EV | Realized Win Rate | Realized EV | MBB 95% Bound | V1.8.0 Verdict | Actual Economic Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`HYP_R_100_10T_PUT`** | `R_100` | 10 ticks | `PUT` | 50.41% | 51.15% | **-$0.0290** | 53.84% | +$0.1050 | +$0.0075 | `CANDIDATE_IDENTIFIED` | **REJECTED_NEGATIVE_PREDICTED_EV** |
| **`HYP_1HZ50V_10T_PUT`** | `1HZ50V` | 10 ticks | `PUT` | 49.84% | 51.15% | **-$0.0514** | 54.20% | +$0.1192 | +$0.0216 | `CANDIDATE_IDENTIFIED` | **REJECTED_NEGATIVE_PREDICTED_EV** |
| **`HYP_1HZ50V_5T_PUT`** | `1HZ50V` | 5 ticks | `PUT` | 50.08% | 51.15% | **-$0.0418** | 53.11% | +$0.0766 | +$0.0021 | `CANDIDATE_IDENTIFIED` | **REJECTED_NEGATIVE_PREDICTED_EV** |

In all three instances, **the model itself forecast negative expected value**. Had a trader consulted the model ex-ante, the model's explicit recommendation would have been **NO TRADE**. Retrospectively crediting the model with the sample win rate violated fundamental principles of predictive causal modeling.

---

## 3. Repaired Authoritative Gate Architecture (V1.8.1)

In V1.8.1, the qualification logic has been completely restructured within `CandidateQualificationGate` and `MultiMarketEdgeDiscovery`:

### Explicit Gate Invariants

For any candidate strategy to qualify as `CANDIDATE_IDENTIFIED`, all of the following seven gates must simultaneously evaluate to `True`:

1. **Gate 1: Authentic Pre-Outcome Forecast Availability**
   - The forecast $P_{\text{model}}$ must be computed strictly prior to decision epoch $t_{\text{dec}}$ without future tick leakage.
2. **Gate 2: Positive Ex-Ante Predicted EV**
   - $\text{PredictedEV} = (P_{\text{model}} \times \text{Payout}) - \text{Ask} > 0.0$ ($P_{\text{model}} > \text{BreakEven}$).
   - Any model with $\text{PredictedEV} \le 0.0$ fails closed with `REJECTED_NEGATIVE_PREDICTED_EV`.
3. **Gate 3: Positive Prospective Realized EV**
   - $\text{RealizedEV} = (\text{WinRate}_{\text{emp}} \times \text{Payout}) - \text{Ask} > 0.0$.
4. **Gate 4: Dependence-Aware Conservative Economic Bound**
   - Moving-Block Bootstrap (MBB) 95% lower confidence bound $\text{EV}_{\text{cons}} > 0.0$.
5. **Gate 5: Multiple-Testing Controlled Significance**
   - Benjamini-Hochberg False Discovery Rate adjusted p-value $p_{\text{FDR}} < 0.05$ across all 48 hypotheses.
6. **Gate 6: Authentic Quote Verification**
   - Must match authentic broker proposal responses. Fixed sample quotes or illustrative modes are classified as `REFERENCE_ECONOMICS_ONLY` and strictly prohibited from qualifying.
7. **Gate 7: Adequate Sample Size**
   - Effective sample size $N_{\text{eff}} = \max(1, \lfloor N / D \rfloor) \ge 50$.

### Authoritative Implementation (`rise_fall_research.py`)

```python
is_pred_pos = (raw["predicted_ev"] > 0.0)
is_real_pos = (raw["realized_ev"] > 0.0)
is_cons_pos = (cons_ev is not None and cons_ev > 0.0)
is_pos = (is_pred_pos and is_real_pos and is_cons_pos)

if raw["evaluation_mode"] == "REFERENCE_ECONOMICS_ONLY":
    verdict = STATUS_REFERENCE_ECONOMICS_ONLY
    rejection_reason = "REFERENCE_PRICING_INELIGIBLE_FOR_CANDIDATE_QUALIFICATION"
elif is_sig and is_real_pos and is_cons_pos and is_pred_pos:
    verdict = STATUS_CANDIDATE_IDENTIFIED
    rejection_reason = None
elif not is_pred_pos and is_real_pos:
    verdict = STATUS_REJECTED_NEGATIVE_PREDICTED_EV
    rejection_reason = "MODEL_FORECAST_EV_NON_POSITIVE"
elif raw["realized_ev"] <= 0.0:
    verdict = STATUS_REJECTED_NEGATIVE_EV
    rejection_reason = "REALIZED_RETURN_NON_POSITIVE"
elif not is_cons_pos:
    verdict = STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV
    rejection_reason = "CONSERVATIVE_BOOTSTRAP_BOUND_NON_POSITIVE"
elif not is_sig:
    verdict = STATUS_REJECTED_STATISTICAL_INSUFFICIENCY
    rejection_reason = "FDR_MULTIPLE_TESTING_INSIGNIFICANT"
```

---

## 4. Separation of Hypothesis Research Classes

To prevent conflating unconditional market drift with conditional predictive modeling, V1.8.1 establishes explicit hypothesis taxonomies:

1. **`MODEL_CONDITIONED_SIGNAL_HYPOTHESIS`**
   - Conditioned on causal rolling indicators (volatility, momentum, streaks).
   - Decision rule: Must satisfy $\text{PredictedEV} > 0$ and all gates.
2. **`UNCONDITIONAL_DIRECTIONAL_BIAS_HYPOTHESIS`**
   - Investigates structural market asymmetry independent of rolling indicators.
   - Requires training-set predeclared empirical base-rate estimation. Holdout win rates cannot be retrospectively substituted for model forecasts.
3. **`QUOTE_CONDITIONED_ECONOMIC_HYPOTHESIS`**
   - Exploits genuine broker price variations (e.g., mispriced payouts).
   - Requires per-observation proposal timestamp matching.

---

## 5. Audit Conclusion

Under the corrected V1.8.1 gating architecture:
- All three previous candidate hypotheses (`HYP_R_100_10T_PUT`, `HYP_1HZ50V_10T_PUT`, `HYP_1HZ50V_5T_PUT`) are **unanimously rejected** with status `REJECTED_NEGATIVE_PREDICTED_EV`.
- Across all 48 tested combinations, zero strategies show positive predicted EV and positive conservative bounds.
- The overall platform verdict is updated to:
  $$\mathbf{NO\_VALIDATED\_POSITIVE\_EV\_EDGE}$$
