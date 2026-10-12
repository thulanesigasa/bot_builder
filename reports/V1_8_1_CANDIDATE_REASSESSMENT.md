# V1.8.1 Independent Candidate Reassessment Report

![Candidate A](https://img.shields.io/badge/HYP__R__100__10T__PUT-REJECTED_NEGATIVE_PREDICTED_EV-red.svg)
![Candidate B](https://img.shields.io/badge/HYP__1HZ50V__10T__PUT-REJECTED_NEGATIVE_PREDICTED_EV-red.svg)
![Candidate C](https://img.shields.io/badge/HYP__1HZ50V__5T__PUT-REJECTED_NEGATIVE_PREDICTED_EV-red.svg)
![Overall Status](https://img.shields.io/badge/Candidate_Count-0_Qualified-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Audit Mandate

In Release V1.8.0, three Rise/Fall trading hypotheses were tentatively classified with verdict `CANDIDATE_IDENTIFIED`:
1. **Candidate A**: `HYP_R_100_10T_PUT`
2. **Candidate B**: `HYP_1HZ50V_10T_PUT`
3. **Candidate C**: `HYP_1HZ50V_5T_PUT`

The V1.8.1 specification explicitly mandates:
> *"These are unverified exploratory hypotheses, not validated profitable strategies. Do not preserve their candidate status unless independent, corrected calculations justify it. The priority is trustworthy evidence, not a positive verdict. Do not force any candidate to pass."*

Following complete re-evaluation under V1.8.1 criteria (strictly positive predicted EV, dependence-aware inference, and post-hoc selection analysis), **all three candidates are rejected**. None qualify for independent prospective confirmation or live trading.

---

## 2. In-Depth Re-Assessment of Candidate A: `HYP_R_100_10T_PUT`

### 2.1 Specification & Invariants
- **Hypothesis Identifier**: `HYP_R_100_10T_PUT`
- **Market Symbol**: `R_100` (Volatility 100 Index, 2s ticks)
- **Contract Type**: `PUT` (Fall)
- **Duration**: 10 ticks
- **Contract Mapping**: `MAPPING_V1_NEXT_TICK_ENTRY` (strictly higher/lower, tie is a broker loss)
- **Underlying Data Provenance**: `data/R_100_ticks.csv` (200,000 ticks, SHA-256 `1183d491...`, `GENUINE_BROKER_API`, 0 gaps)

### 2.2 Recomputed Economics & Statistics
- **Sample Size ($N$)**: 4,978 test observations
- **Effective Sample Size ($N_{\text{eff}}$)**: $\lfloor 4978 / 10 \rfloor = 497$
- **Model Forecast Probability ($P_{\text{mod}}$)**: **50.41%** (0.5041)
- **Broker Break-Even Hurdle**: **51.15%** (0.5115)
- **Probability Advantage ($\Delta p$)**: $0.5041 - 0.5115 = \mathbf{-0.74\%}$
- **Model-Predicted EV**: $0.5041 \times 3.91 - 2.00 = \mathbf{-\$0.0290}$
- **Empirical Holdout Win Rate**: 53.84% (0.5384)
- **Realized Return**: $0.5384 \times 3.91 - 2.00 = +\$0.1050$
- **Moving-Block Bootstrap (MBB 95% Bound)**: +$0.0075
- **Dependence-Aware Significance**:
  - $z_{\text{eff}} = (0.5384 - 0.5115) / 0.02241 = +1.200$
  - Raw p-value: $0.1150$ ($> 0.05$, Insignificant)
  - Benjamini-Hochberg Adjusted p-value (FDR): $1.0000$ ($> 0.05$, Insignificant)

### 2.3 Verdict & Justification
- **V1.8.0 Verdict**: `CANDIDATE_IDENTIFIED`
- **V1.8.1 Authoritative Verdict**: **`REJECTED_NEGATIVE_PREDICTED_EV`**
- **Detailed Findings**:
  1. The model's own forecast predicted that every $\$2.00$ bet had an expected loss of $\$0.0290$.
  2. The positive holdout return (+$0.1050$) was retrospective sample drift over a 5,000-tick window, not an advance predictive edge. Across the full 200,000-tick dataset, `R_100` 10-tick PUT win rate is exactly 49.93% (a loss).
  3. Under dependence-aware testing, the raw p-value is 0.1150 and FDR p-value is 1.0000. It is statistically indistinguishable from chance.
  4. Preregistration for forward confirmation is **unjustified**.

---

## 3. In-Depth Re-Assessment of Candidate B: `HYP_1HZ50V_10T_PUT`

### 3.1 Specification & Invariants
- **Hypothesis Identifier**: `HYP_1HZ50V_10T_PUT`
- **Market Symbol**: `1HZ50V` (Volatility 50 (1s) Index, 1s ticks)
- **Contract Type**: `PUT` (Fall)
- **Duration**: 10 ticks
- **Contract Mapping**: `MAPPING_V1_NEXT_TICK_ENTRY`
- **Underlying Data Provenance**: `data/1HZ50V_ticks.csv` (200,000 ticks, SHA-256 `277f6c2c...`, `GENUINE_BROKER_API`, 0 gaps)

### 3.2 Recomputed Economics & Statistics
- **Sample Size ($N$)**: 4,978 test observations
- **Effective Sample Size ($N_{\text{eff}}$)**: $\lfloor 4978 / 10 \rfloor = 497$
- **Model Forecast Probability ($P_{\text{mod}}$)**: **49.84%** (0.4984)
- **Broker Break-Even Hurdle**: **51.15%** (0.5115)
- **Probability Advantage ($\Delta p$)**: $0.4984 - 0.5115 = \mathbf{-1.31\%}$
- **Model-Predicted EV**: $0.4984 \times 3.91 - 2.00 = \mathbf{-\$0.0514}$
- **Empirical Holdout Win Rate**: 54.20% (0.5420)
- **Realized Return**: $0.5420 \times 3.91 - 2.00 = +\$0.1192$
- **Moving-Block Bootstrap (MBB 95% Bound)**: +$0.0216$
- **Dependence-Aware Significance**:
  - $z_{\text{eff}} = (0.5420 - 0.5115) / 0.02241 = +1.361$
  - Raw p-value: $0.0867$ ($> 0.05$, Insignificant)
  - Benjamini-Hochberg Adjusted p-value (FDR): $1.0000$ ($> 0.05$, Insignificant)

### 3.3 Verdict & Justification
- **V1.8.0 Verdict**: `CANDIDATE_IDENTIFIED`
- **V1.8.1 Authoritative Verdict**: **`REJECTED_NEGATIVE_PREDICTED_EV`**
- **Detailed Findings**:
  1. The model explicitly predicted a loss of $-\$0.0514$ per contract.
  2. The full-dataset tick return on `1HZ50V` is symmetric (PUT win rate 50.07% on 200,000 ticks), proving the 54.20% holdout win rate was short-window sample-selection noise.
  3. Fails both the predicted EV gate and dependence-aware multiple-testing significance.
  4. Preregistration for forward confirmation is **unjustified**.

---

## 4. In-Depth Re-Assessment of Candidate C: `HYP_1HZ50V_5T_PUT`

### 4.1 Specification & Invariants
- **Hypothesis Identifier**: `HYP_1HZ50V_5T_PUT`
- **Market Symbol**: `1HZ50V` (Volatility 50 (1s) Index, 1s ticks)
- **Contract Type**: `PUT` (Fall)
- **Duration**: 5 ticks
- **Contract Mapping**: `MAPPING_V1_NEXT_TICK_ENTRY`
- **Underlying Data Provenance**: `data/1HZ50V_ticks.csv` (200,000 ticks, SHA-256 `277f6c2c...`, `GENUINE_BROKER_API`, 0 gaps)

### 4.2 Recomputed Economics & Statistics
- **Sample Size ($N$)**: 4,984 test observations
- **Effective Sample Size ($N_{\text{eff}}$)**: $\lfloor 4984 / 5 \rfloor = 996$
- **Model Forecast Probability ($P_{\text{mod}}$)**: **50.08%** (0.5008)
- **Broker Break-Even Hurdle**: **51.15%** (0.5115)
- **Probability Advantage ($\Delta p$)**: $0.5008 - 0.5115 = \mathbf{-1.07\%}$
- **Model-Predicted EV**: $0.5008 \times 3.91 - 2.00 = \mathbf{-\$0.0418}$
- **Empirical Holdout Win Rate**: 53.11% (0.5311)
- **Realized Return**: $0.5311 \times 3.91 - 2.00 = +\$0.0766$
- **Moving-Block Bootstrap (MBB 95% Bound)**: +$0.0021$
- **Dependence-Aware Significance**:
  - $z_{\text{eff}} = (0.5311 - 0.5115) / 0.01584 = +1.237$
  - Raw p-value: $0.1080$ ($> 0.05$, Insignificant)
  - Benjamini-Hochberg Adjusted p-value (FDR): $1.0000$ ($> 0.05$, Insignificant)

### 4.3 Verdict & Justification
- **V1.8.0 Verdict**: `CANDIDATE_IDENTIFIED`
- **V1.8.1 Authoritative Verdict**: **`REJECTED_NEGATIVE_PREDICTED_EV`**
- **Detailed Findings**:
  1. Model predicted EV is negative ($-\$0.0418$).
  2. Conservative lower bound (+$0.0021$) is virtually zero, demonstrating zero robust margin of safety.
  3. Corrected raw p-value is 0.1080, failing standard alpha = 0.05 significance.
  4. Preregistration for forward confirmation is **unjustified**.

---

## 5. Post-Hoc Selection Confirmation

All three hypotheses were selected post-hoc in V1.8.0 by scanning holdout empirical win rates rather than pre-registering positive model signals. 

When the model itself fails to forecast an edge, and the full market history demonstrates symmetric random-walk behavior, treating short-window holdout fluctuations as tradeable edges is a classic manifestation of the **Data Snooping Bias** (White, 2000).

---

## 6. Synthesis & Reassessment Conclusion

| Candidate ID | V1.8.0 Decision | V1.8.1 Corrected Decision | Primary Rejection Reason |
| :--- | :--- | :--- | :--- |
| `HYP_R_100_10T_PUT` | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | Model EV -$0.0290, FDR p = 1.0000 |
| `HYP_1HZ50V_10T_PUT` | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | Model EV -$0.0514, FDR p = 1.0000 |
| `HYP_1HZ50V_5T_PUT` | `CANDIDATE_IDENTIFIED` | **`REJECTED_NEGATIVE_PREDICTED_EV`** | Model EV -$0.0418, FDR p = 1.0000 |

None of the three hypotheses satisfy the standards required for confirmation readiness. All three candidates are **formally rescinded and rejected**.
