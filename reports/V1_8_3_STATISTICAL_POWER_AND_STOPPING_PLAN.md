# Deriv Multi-Market V1.8.3 — Statistical Power & Stopping Plan

![Power Plan](https://img.shields.io/badge/Power%20Target-80%25%20Power-blue.svg)
![Target N_eff](https://img.shields.io/badge/Required%20N_eff-5%2C000%20Observations-purple.svg)
![Sequential Testing](https://img.shields.io/badge/Boundary-O%27Brien--Fleming-brightgreen.svg)

## 1. Information Horizon & Sample Size Calibration
To detect an economic edge $\Delta p = +1.5\%$ over the broker break-even threshold with:
- Type I error rate $\alpha = 0.05$ (two-tailed)
- Statistical power $1 - \beta = 0.80$
The required effective sample size is:
$$N_{\text{eff}} \ge \frac{(z_{1-\alpha/2} + z_{1-\beta})^2 \cdot p_0(1-p_0)}{(\Delta p)^2} \approx \frac{(1.96 + 0.84)^2 \cdot 0.25}{(0.015)^2} \approx 8,711$$
Accounting for serial autocorrelation (where $\tau_{\text{int}} \approx 5$ to $7$),
raw prospective tick decisions must exceed 40,000 observations before definitive statistical tests are executed.

## 2. Sequential Stopping Boundaries
To prevent p-hacking and false discovery from continuous monitoring:
1. **Futility Stopping Boundary**: If realized EV remains negative after $N_{\text{eff}} = 2,500$, exploratory collection terminates.
2. **Efficacy Stopping Boundary**: Uses O'Brien-Fleming $\alpha$-spending function to preserve family-wise error rate.
3. **Quarantine Rule**: Any candidate identified during exploratory collection must undergo independent prospective confirmation in Cohort D.
