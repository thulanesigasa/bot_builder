# V1.8.1 Statistical Dependence & Multiple-Testing Audit Report

![Dependence Handling](https://img.shields.io/badge/Serial_Dependence-MOVING--BLOCK_BOOTSTRAP-brightgreen.svg)
![Sample Size](https://img.shields.io/badge/Effective_Sample_Size-N_eff_%3D_N%2FD-blue.svg)
![FDR Control](https://img.shields.io/badge/Multiple_Testing-Benjamini--Hochberg_(m%3D48)-blue.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Defect Identification

In Release V1.8.0, the statistical significance of trading hypotheses was evaluated using a standard one-sided asymptotic binomial z-test against the break-even hurdle ($p_0 = 0.5115$):
$$\text{se} = \sqrt{\frac{p_0 (1 - p_0)}{N}}, \quad z = \frac{\text{WinRate}_{\text{emp}} - p_0}{\text{se}}$$

While valid for independent Bernoulli trials, **this test assumes zero serial correlation between consecutive observations**. 

In high-frequency tick evaluation, a contract of duration $D$ ticks (e.g., $D = 10$ ticks) evaluated at every tick $t, t+1, t+2, \dots$ creates an overlapping rolling evaluation window where each outcome shares $D-1$ ticks (90% of the price path) with its adjacent neighbors. This creates strong positive serial correlation among outcomes, drastically violating the independence assumption of the standard binomial test.

Release V1.8.1 corrects this statistical vulnerability by implementing:
1. An effective sample size correction: $N_{\text{eff}} = \max(1, \lfloor N / D \rfloor)$.
2. Moving-Block Bootstrap (MBB) resampling for empirical distribution estimation.
3. Family-wise Benjamini-Hochberg False Discovery Rate (FDR) multiple-testing control across all 48 hypotheses.

---

## 2. Mathematical Impact of Overlapping Serial Correlation

### 2.1 Variance Inflation in Overlapping Time Series

Let $Y_t \in \{0, 1\}$ denote the binary contract outcome initiated at tick $t$ with expiry at $t + D$.
The sample mean is:
$$\bar{Y} = \frac{1}{N} \sum_{t=1}^N Y_t$$

Under independent observations, the variance of the sample mean is:
$$\text{Var}_{\text{iid}}(\bar{Y}) = \frac{\sigma^2}{N}$$

However, in the presence of autocovariance $\gamma(k) = \text{Cov}(Y_t, Y_{t+k})$ up to lag $D-1$:
$$\text{Var}_{\text{actual}}(\bar{Y}) = \frac{1}{N^2} \sum_{t=1}^N \sum_{s=1}^N \text{Cov}(Y_t, Y_s) = \frac{\sigma^2}{N} \left[ 1 + 2 \sum_{k=1}^{D-1} \left(1 - \frac{k}{N}\right) \rho(k) \right]$$

For a uniform random walk over $D$ ticks, the autocorrelation between outcomes separated by $k$ ticks is approximately $\rho(k) \approx 1 - \frac{k}{D}$ for $k < D$. The variance inflation factor (VIF) is approximately:
$$\text{VIF} \approx 1 + 2 \sum_{k=1}^{D-1} \left(1 - \frac{k}{D}\right) \approx D$$

Consequently:
$$\text{Actual Standard Error} \approx \sqrt{D} \times \text{se}_{\text{naive}}$$

Using naive sample size $N$ underestimates the standard error by a factor of $\sqrt{D} \approx \sqrt{10} \approx 3.16\times$, artificially inflating the z-statistic by $316\%$ and deflating p-values by multiple orders of magnitude.

---

## 3. Comparative Case Study: The V1.8.0 False Positives

To demonstrate how serial dependence manufactured artificial statistical significance in V1.8.0, consider the three previous candidates:

### 3.1 Candidate A: `HYP_R_100_10T_PUT` ($D = 10$ ticks, $N = 4,978$, $\text{WinRate} = 53.84\%$, $p_0 = 51.15\%$)
- **Naive V1.8.0 Calculation**:
  $$\text{se}_{\text{naive}} = \sqrt{\frac{0.5115 \times 0.4885}{4978}} \approx 0.007086$$
  $$z_{\text{naive}} = \frac{0.5384 - 0.5115}{0.007086} = +3.796 \implies p_{\text{raw}} = 0.000075 \quad (7.5 \times 10^{-5})$$
  Under Benjamini-Hochberg across 48 hypotheses, $p_{\text{FDR}} = 0.001799 < 0.05$ (Falsely declared significant!).
- **Dependence-Aware V1.8.1 Calculation**:
  $$N_{\text{eff}} = \left\lfloor \frac{4978}{10} \right\rfloor = 497$$
  $$\text{se}_{\text{eff}} = \sqrt{\frac{0.5115 \times 0.4885}{497}} \approx 0.02241$$
  $$z_{\text{eff}} = \frac{0.5384 - 0.5115}{0.02241} = +1.200 \implies p_{\text{raw}} = 0.1150$$
  Under Benjamini-Hochberg across 48 hypotheses:
  $$p_{\text{FDR}} = 1.0000 \gg 0.05 \quad (\mathbf{NOT\ SIGNIFICANT})$$

### 3.2 Candidate B: `HYP_1HZ50V_10T_PUT` ($D = 10$ ticks, $N = 4,978$, $\text{WinRate} = 54.20\%$, $p_0 = 51.15\%$)
- **Naive V1.8.0 Calculation**:
  $$z_{\text{naive}} = \frac{0.5420 - 0.5115}{0.007086} = +4.305 \implies p_{\text{raw}} = 8.0 \times 10^{-6}$$
  $$p_{\text{FDR}} = 0.000407 < 0.05 \quad (\text{Falsely declared significant})$$
- **Dependence-Aware V1.8.1 Calculation**:
  $$z_{\text{eff}} = \frac{0.5420 - 0.5115}{0.02241} = +1.361 \implies p_{\text{raw}} = 0.0867$$
  $$p_{\text{FDR}} = 1.0000 \gg 0.05 \quad (\mathbf{NOT\ SIGNIFICANT})$$

### 3.3 Candidate C: `HYP_1HZ50V_5T_PUT` ($D = 5$ ticks, $N = 4,984$, $\text{WinRate} = 53.11\%$, $p_0 = 51.15\%$)
- **Naive V1.8.0 Calculation**:
  $$z_{\text{naive}} = +2.768 \implies p_{\text{raw}} = 0.00283 \implies p_{\text{FDR}} = 0.0339 < 0.05$$
- **Dependence-Aware V1.8.1 Calculation**:
  $$N_{\text{eff}} = \left\lfloor \frac{4984}{5} \right\rfloor = 996$$
  $$\text{se}_{\text{eff}} = 0.01584 \implies z_{\text{eff}} = +1.237 \implies p_{\text{raw}} = 0.1080 \implies p_{\text{FDR}} = 1.0000 \quad (\mathbf{NOT\ SIGNIFICANT})$$

### Summary Comparison Table

| Candidate Hypothesis | Naive z-score | Naive Raw p | Naive FDR p | Effective N ($N_{\text{eff}}$) | Corrected z | Corrected Raw p | Corrected FDR p | True Significance |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HYP_R_100_10T_PUT` | +3.80 | $0.000075$ | $0.001799$ | 497 | **+1.20** | **0.1150** | **1.0000** | **INSIGNIFICANT** |
| `HYP_1HZ50V_10T_PUT` | +4.31 | $0.000008$ | $0.000407$ | 497 | **+1.36** | **0.0867** | **1.0000** | **INSIGNIFICANT** |
| `HYP_1HZ50V_5T_PUT` | +2.77 | $0.002830$ | $0.033963$ | 996 | **+1.24** | **0.1080** | **1.0000** | **INSIGNIFICANT** |

Once serial correlation is properly handled, **not a single one of the three candidates achieves statistical significance even before multiple testing adjustment**, let alone after FDR control across 48 hypotheses.

---

## 4. Moving-Block Bootstrap (MBB) Conservative Bound

To obtain distribution-free, dependence-aware confidence bounds for expected value:
1. Block size $b = \max(2, D)$ preserves intra-block serial dependence.
2. The number of overlapping blocks is $N - b + 1$.
3. $B = 500$ bootstrap replicates are resampled with replacement.
4. The 5th percentile of resampled mean return defines the 95% lower confidence bound $\text{EV}_{\text{cons}}$.
5. If $\text{EV}_{\text{cons}} \le \$0.00$, the strategy fails the economic robustness gate.

---

## 5. Multiple-Testing Family & Benjamini-Hochberg Control

The full hypothesis family comprises:
$$M = 6\text{ markets} \times 4\text{ durations} \times 2\text{ directions} = 48\text{ hypotheses}$$

Benjamini-Hochberg step-up adjustment is applied with false discovery rate parameter $\alpha = 0.05$:
1. Sort raw p-values: $p_{(1)} \le p_{(2)} \le \dots \le p_{(M)}$.
2. Compute adjusted p-values:
   $$p_{\text{adj}(k)} = \min \left( 1.0, \min_{j \ge k} \left\{ \frac{M}{j} p_{(j)} \right\} \right)$$
3. Declare significance iff $p_{\text{adj}} < 0.05$.

Under V1.8.1 dependence-aware testing, every single hypothesis yields $p_{\text{adj}} \ge 0.10$ (the vast majority yielding $1.0000$). Zero hypotheses survive multiple-testing control.

---

## 6. Audit Conclusion

The apparent statistical significance reported in Release V1.8.0 was entirely an artifact of:
1. Ignoring the $10\times$ serial dependence between consecutive tick outcomes.
2. Naively applying i.i.d. binomial formulas to overlapping time-series data.

When dependence-aware inference ($N_{\text{eff}}$ and Moving-Block Bootstrap) is applied, **all empirical evidence collapses to random walk noise**. Zero hypotheses demonstrate statistical significance.
