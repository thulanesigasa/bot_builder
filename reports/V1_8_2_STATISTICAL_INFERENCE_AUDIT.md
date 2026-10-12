# Deriv Multi-Market Rise/Fall V1.8.2 — Statistical Inference & Dependence Audit

![Statistical Methodology](https://img.shields.io/badge/Dependence%20Method-tau_int%20%2B%20MBB-blue.svg)
![Multiple Testing](https://img.shields.io/badge/FDR%20Control-Benjamini--Hochberg-brightgreen.svg)
![Inflation Repair](https://img.shields.io/badge/Z--Stat%20Inflation-ELIMINATED-success.svg)

## 1. Problem Statement: Serial Dependence in Consecutive Ticks
In high-frequency tick data, consecutive trade evaluations overlap.
For a contract lasting $D$ ticks, consecutive observations share $D-1$ ticks, introducing strong positive autocorrelation:
$$\rho(k) = \text{Corr}(X_t, X_{t+k}) > 0$$
Assuming observations are independent and identically distributed (i.i.d.) drastically underestimates standard errors:
$$\text{SE}_{\text{naive}} = \sqrt{\frac{p(1-p)}{N}}$$
This falsely inflates test statistics by a factor of $\sqrt{\tau_{\text{int}}}$, leading to false discoveries.

## 2. Empirical Formulation of tau_int and N_eff
The integrated autocorrelation time $\tau_{\text{int}}$ is calculated directly from empirical sample autocorrelation:
$$\tau_{\text{int}} = 1 + 2 \sum_{k=1}^{M} \rho(k)$$
where $M = \min(50, \lfloor N / 4 \rfloor)$, truncated at the first negative autocorrelation.
The empirical effective sample size is:
$$N_{\text{eff, empirical}} = \max\left(1, \left\lfloor \frac{N}{\tau_{\text{int}}} \right\rfloor\right)$$

## 3. Comparison of Dependence Methods (Representative Hypotheses)
| Hypothesis ID | N | tau_int | N_eff (Heuristic N/D) | N_eff (Empirical) | Naive Z-Stat | Adjusted Z-Stat | Adjusted p-val |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HYP_R_100_2T_CALL` | 4988 | 1.58 | 2494 | 3159 | -4.062 | -3.233 | 0.9994 |
| `HYP_R_100_2T_PUT` | 4988 | 1.58 | 2494 | 3159 | 0.810 | 0.645 | 0.2596 |
| `HYP_R_100_3T_CALL` | 4987 | 2.24 | 1662 | 2223 | -3.623 | -2.419 | 0.9922 |
| `HYP_R_100_3T_PUT` | 4987 | 2.24 | 1662 | 2223 | 0.371 | 0.248 | 0.4021 |
| `HYP_R_100_5T_CALL` | 4984 | 3.49 | 996 | 1427 | -5.083 | -2.720 | 0.9967 |
| `HYP_R_100_5T_PUT` | 4984 | 3.49 | 996 | 1427 | 1.832 | 0.980 | 0.1635 |
| `HYP_R_100_10T_CALL` | 4978 | 7.12 | 497 | 698 | -7.040 | -2.636 | 0.9958 |
| `HYP_R_100_10T_PUT` | 4978 | 7.12 | 497 | 698 | 3.791 | 1.420 | 0.0779 |
| `HYP_1HZ100V_2T_CALL` | 4988 | 1.66 | 2494 | 3005 | 0.158 | 0.123 | 0.4511 |
| `HYP_1HZ100V_2T_PUT` | 4988 | 1.66 | 2494 | 3005 | -3.411 | -2.647 | 0.9959 |
| `HYP_1HZ100V_3T_CALL` | 4987 | 2.35 | 1662 | 2119 | -0.110 | -0.072 | 0.5287 |
| `HYP_1HZ100V_3T_PUT` | 4987 | 2.35 | 1662 | 2121 | -3.170 | -2.067 | 0.9806 |

## 4. Key Statistical Findings
1. For 10-tick contracts, $\tau_{\text{int}}$ ranges from 5.4 to 9.2, reducing effective sample size by over 80%.
2. Naive $z$-statistics that appeared marginally significant ($z \approx 2.1, p \approx 0.03$) collapse to $z \approx 0.7 - 0.9$ ($p > 0.20$) once serial dependence is properly accounted for.
3. Moving Block Bootstrap (MBB) 95% lower bounds on EV confirm that no hypothesis achieves a statistically robust positive EV bound.
