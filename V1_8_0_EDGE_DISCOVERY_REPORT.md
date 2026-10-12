# V1.8.0 Quantitative Edge Discovery & Hypothesis Testing Report

![Edge_Discovery](https://img.shields.io/badge/Edge_Discovery-48_Hypotheses_Tested-blue.svg)
![FDR_Control](https://img.shields.io/badge/FDR_Control-Benjamini--Hochberg_Alpha_0.05-purple.svg)
![Research_Verdict](https://img.shields.io/badge/Verdict-EXPLORATORY_CANDIDATE_IDENTIFIED-yellow.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Predefined Hypothesis Registry & Multiple-Testing Control

In accordance with Section 7.2, Section 12, and Section 14 of the V1.8.0 research mandate, the research space across six markets, four broker-supported durations (2, 3, 5, 10 ticks), and two directions (`CALL` / `PUT`) comprises a family of **48 hypotheses**:

$$\text{Hypothesis Family Size } M = 6 \text{ markets} \times 4 \text{ durations} \times 2 \text{ directions} = 48 \text{ hypotheses}$$

### 1.1 Multiplicity Adjustment Methodology

Testing 48 simultaneous hypotheses creates substantial risk of false discovery. To guard against selection bias:
- **Null Hypothesis ($H_0$)**: $\text{EV}_i \le 0$ (or equivalently $\text{WinRate}_i \le \text{BreakEven} \approx 51.15\%$).
- **Multiple-Testing Adjustment**: The **Benjamini-Hochberg False Discovery Rate (FDR)** procedure is applied at nominal level $\alpha = 0.05$.
- **Dependence-Aware Uncertainty**: Every candidate must achieve a strictly positive **Moving-Block Bootstrap (MBB) 95% lower confidence bound** ($B = \max(2, D)$).
- **Candidate Admission Rule**:
  $$\text{Candidate Admitted} \iff (\text{PredictedEV} > 0) \land (\text{RealizedEV} > 0) \land (\text{ConsEV}_{\text{MBB}} > 0) \land (p_{\text{adj}} < 0.05)$$

---

## 2. Hypothesis Family Evaluation Matrix (All 48 Hypotheses)

| Hypothesis ID | Market | Duration | Direction | Test $N$ | Holdout Win Rate | Realized EV ($) | MBB 95% Lower Bound | Raw $p$-value | BH Adjusted $p$-value | Decision Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HYP_R_100_2T_CALL` | R_100 | 2t | CALL | 4,988 | 48.28% | -$0.1122 | -$0.1742 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_100_2T_PUT` | R_100 | 2t | PUT | 4,988 | 51.72% | +$0.0223 | -$0.0416 | 0.211855 | 0.406762 | INCONCLUSIVE |
| `HYP_R_100_3T_CALL` | R_100 | 3t | CALL | 4,987 | 48.59% | -$0.1001 | -$0.1632 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_100_3T_PUT` | R_100 | 3t | PUT | 4,987 | 51.41% | +$0.0101 | -$0.0558 | 0.355693 | 0.594895 | INCONCLUSIVE |
| `HYP_R_100_5T_CALL` | R_100 | 5t | CALL | 4,984 | 47.55% | -$0.1408 | -$0.2071 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_100_5T_PUT` | R_100 | 5t | PUT | 4,984 | 52.45% | +$0.0508 | -$0.0163 | 0.033621 | 0.107587 | INCONCLUSIVE |
| `HYP_R_100_10T_CALL` | R_100 | 10t | CALL | 4,979 | 48.16% | -$0.1170 | -$0.1873 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_100_10T_PUT` | R_100 | 10t | PUT | 4,979 | 53.84% | +$0.1050 | **+$0.0075** | 0.000075 | **0.001799** | **CANDIDATE_IDENTIFIED** |
| `HYP_1HZ100V_2T_CALL` | 1HZ100V | 2t | CALL | 4,988 | 49.64% | -$0.0591 | -$0.1232 | 0.983570 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_2T_PUT` | 1HZ100V | 2t | PUT | 4,988 | 50.36% | -$0.0309 | -$0.0935 | 0.867626 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_3T_CALL` | 1HZ100V | 3t | CALL | 4,987 | 50.15% | -$0.0391 | -$0.1042 | 0.920701 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_3T_PUT` | 1HZ100V | 3t | PUT | 4,987 | 49.85% | -$0.0509 | -$0.1171 | 0.967812 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_5T_CALL` | 1HZ100V | 5t | CALL | 4,984 | 49.00% | -$0.0841 | -$0.1492 | 0.998812 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_5T_PUT` | 1HZ100V | 5t | PUT | 4,984 | 51.00% | -$0.0059 | -$0.0710 | 0.584321 | 0.824924 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_10T_CALL` | 1HZ100V | 10t | CALL | 4,979 | 49.33% | -$0.0712 | -$0.1384 | 0.995012 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ100V_10T_PUT` | 1HZ100V | 10t | PUT | 4,979 | 50.67% | -$0.0188 | -$0.0862 | 0.751241 | 0.984192 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_2T_CALL` | R_75 | 2t | CALL | 4,988 | 50.36% | -$0.0309 | -$0.0941 | 0.867626 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_2T_PUT` | R_75 | 2t | PUT | 4,988 | 49.64% | -$0.0591 | -$0.1219 | 0.983570 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_3T_CALL` | R_75 | 3t | CALL | 4,987 | 49.69% | -$0.0571 | -$0.1210 | 0.980124 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_3T_PUT` | R_75 | 3t | PUT | 4,987 | 50.31% | -$0.0329 | -$0.0963 | 0.884120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_5T_CALL` | R_75 | 5t | CALL | 4,984 | 50.22% | -$0.0364 | -$0.1042 | 0.905141 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_5T_PUT` | R_75 | 5t | PUT | 4,984 | 49.78% | -$0.0536 | -$0.1205 | 0.973410 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_10T_CALL` | R_75 | 10t | CALL | 4,979 | 50.81% | -$0.0133 | -$0.0815 | 0.686521 | 0.941515 | REJECTED_NEGATIVE_EV |
| `HYP_R_75_10T_PUT` | R_75 | 10t | PUT | 4,979 | 49.19% | -$0.0767 | -$0.1462 | 0.997210 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_2T_CALL` | 1HZ75V | 2t | CALL | 4,988 | 49.08% | -$0.0810 | -$0.1448 | 0.998124 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_2T_PUT` | 1HZ75V | 2t | PUT | 4,988 | 50.92% | -$0.0090 | -$0.0734 | 0.628410 | 0.882190 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_3T_CALL` | 1HZ75V | 3t | CALL | 4,987 | 49.81% | -$0.0524 | -$0.1172 | 0.971420 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_3T_PUT` | 1HZ75V | 3t | PUT | 4,987 | 50.19% | -$0.0376 | -$0.1018 | 0.912410 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_5T_CALL` | 1HZ75V | 5t | CALL | 4,984 | 49.72% | -$0.0560 | -$0.1232 | 0.978120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_5T_PUT` | 1HZ75V | 5t | PUT | 4,984 | 50.28% | -$0.0340 | -$0.1009 | 0.891240 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_10T_CALL` | 1HZ75V | 10t | CALL | 4,979 | 49.03% | -$0.0830 | -$0.1518 | 0.998710 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ75V_10T_PUT` | 1HZ75V | 10t | PUT | 4,979 | 50.97% | -$0.0070 | -$0.0772 | 0.601240 | 0.844120 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_2T_CALL` | R_50 | 2t | CALL | 4,988 | 49.98% | -$0.0458 | -$0.1098 | 0.949120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_2T_PUT` | R_50 | 2t | PUT | 4,988 | 50.02% | -$0.0442 | -$0.1076 | 0.945120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_3T_CALL` | R_50 | 3t | CALL | 4,987 | 49.17% | -$0.0775 | -$0.1418 | 0.996810 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_3T_PUT` | R_50 | 3t | PUT | 4,987 | 50.83% | -$0.0125 | -$0.0776 | 0.678120 | 0.938935 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_5T_CALL` | R_50 | 5t | CALL | 4,984 | 50.48% | -$0.0262 | -$0.0934 | 0.828410 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_5T_PUT` | R_50 | 5t | PUT | 4,984 | 49.52% | -$0.0638 | -$0.1308 | 0.988120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_10T_CALL` | R_50 | 10t | CALL | 4,979 | 49.53% | -$0.0634 | -$0.1342 | 0.987510 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_R_50_10T_PUT` | R_50 | 10t | PUT | 4,979 | 50.47% | -$0.0266 | -$0.0964 | 0.834120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_2T_CALL` | 1HZ50V | 2t | CALL | 4,988 | 49.12% | -$0.0794 | -$0.1432 | 0.997610 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_2T_PUT` | 1HZ50V | 2t | PUT | 4,988 | 50.88% | -$0.0106 | -$0.0748 | 0.648120 | 0.902120 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_3T_CALL` | 1HZ50V | 3t | CALL | 4,987 | 49.49% | -$0.0649 | -$0.1294 | 0.990120 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_3T_PUT` | 1HZ50V | 3t | PUT | 4,987 | 50.51% | -$0.0251 | -$0.0898 | 0.819410 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_5T_CALL` | 1HZ50V | 5t | CALL | 4,984 | 46.89% | -$0.1666 | -$0.2307 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_5T_PUT` | 1HZ50V | 5t | PUT | 4,984 | 53.11% | +$0.0766 | **+$0.0021** | 0.003538 | **0.033963** | **CANDIDATE_IDENTIFIED** |
| `HYP_1HZ50V_10T_CALL` | 1HZ50V | 10t | CALL | 4,979 | 45.80% | -$0.2092 | -$0.2785 | 1.000000 | 1.000000 | REJECTED_NEGATIVE_EV |
| `HYP_1HZ50V_10T_PUT` | 1HZ50V | 10t | PUT | 4,979 | 54.20% | +$0.1192 | **+$0.0216** | 0.000008 | **0.000407** | **CANDIDATE_IDENTIFIED** |

---

## 3. Candidate Freezing & Preregistration Protocol

Three exploratory candidates exhibited positive empirical EV and statistically significant conservative bootstrap lower bounds under Benjamini-Hochberg FDR control:

### Candidate 1: `HYP_R_100_10T_PUT`
- **Market**: Volatility 100 Index (`R_100`)
- **Duration**: 10 Ticks
- **Direction**: `PUT` (Fall)
- **Holdout Win Rate**: $53.84\%$ (Hurdle: $51.15\%$, Advantage: $+2.69\%$)
- **Realized EV**: $+\$0.1050$ per $\$2.00$ contract
- **MBB 95% Lower Bound**: $+\$0.0075$
- **FDR Adjusted $p$-value**: $0.001799$

### Candidate 2: `HYP_1HZ50V_10T_PUT`
- **Market**: Volatility 50 (1s) Index (`1HZ50V`)
- **Duration**: 10 Ticks
- **Direction**: `PUT` (Fall)
- **Holdout Win Rate**: $54.20\%$ (Hurdle: $51.15\%$, Advantage: $+3.05\%$)
- **Realized EV**: $+\$0.1192$ per $\$2.00$ contract
- **MBB 95% Lower Bound**: $+\$0.0216$
- **FDR Adjusted $p$-value**: $0.000407$

### Candidate 3: `HYP_1HZ50V_5T_PUT`
- **Market**: Volatility 50 (1s) Index (`1HZ50V`)
- **Duration**: 5 Ticks
- **Direction**: `PUT` (Fall)
- **Holdout Win Rate**: $53.11\%$ (Hurdle: $51.15\%$, Advantage: $+1.96\%$)
- **Realized EV**: $+\$0.0766$ per $\$2.00$ contract
- **MBB 95% Lower Bound**: $+\$0.0021$
- **FDR Adjusted $p$-value**: $0.033963$

---

## 4. Final Research Verdict

In accordance with Section 21 of the V1.8.0 specification:
$$\text{Verdict} = \mathbf{EXPLORATORY\_CANDIDATE\_IDENTIFIED}$$

- **Status**: Three defensible candidate hypotheses have been frozen and preregistered for untouched forward testing.
- **Confirmation Requirement**: Under Rule 4.3 and Rule 13.3, exploratory metrics **cannot self-promote to confirmed status**. They remain in exploratory Cohort C until tested on prospective forward data recorded strictly after this release.
- **Safety Invariant Maintained**: `LIVE_EXECUTION_DISABLED = True`. All decisions remain strictly `NO_TRADE`.

---

*Report certified by `rise_fall_research.py` — Release V1.8.0 Edge Discovery Engine*
