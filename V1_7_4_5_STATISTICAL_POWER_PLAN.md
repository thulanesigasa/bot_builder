# V1.7.4.5 Statistical Power & Future Evidence Plan

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Power--Analysis](https://img.shields.io/badge/Power--Analysis-Rigorous--Dependence--Aware-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research--Standards](https://img.shields.io/badge/Standards-Independent--Multi--Session-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety--Status](https://img.shields.io/badge/Safety-LIVE__EXECUTION__DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

This plan provides rigorous statistical power analysis and prospective sample size calculations for evaluating Deriv Volatility 75 (`R_75`) Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) contracts.

A fundamental flaw in naive quantitative backtests is assuming consecutive tick decisions are independent and identically distributed ($i.i.d.$). For a 5-tick contract evaluated at every tick, up to 5 consecutive contracts overlap across the exact same price path, generating substantial serial autocorrelation.

This document models the variance inflation factor (VIF), computes effective degrees of freedom, and establishes evidence requirements to test a minimal economically meaningful edge with 95% confidence and 80% statistical power.

---

## 2. Autocorrelation & Effective Sample Size Analysis

### 2.1 Overlapping Contract Dependence
When evaluating contracts of duration $K$ ticks on a tick-by-tick basis:
- Consecutive contracts share $K - 1$ price movements.
- The theoretical lag-1 autocorrelation for overlapping random walk increments is:
  $$\rho_1 \approx \frac{K - 1}{K}$$
  For $K = 2$: $\rho_1 \approx 0.50$  
  For $K = 5$: $\rho_1 \approx 0.80$

### 2.2 Empirical Autocorrelation on Session 1cc84e31
Over the 887 decision epochs of session `1cc84e31`:
- 2T Contract Outcomes: $\hat{\rho}_1 = 0.442$, $\hat{\rho}_2 = 0.185$, $\hat{\rho}_k \approx 0$ for $k \ge 3$.
- 5T Contract Outcomes: $\hat{\rho}_1 = 0.768$, $\hat{\rho}_2 = 0.584$, $\hat{\rho}_3 = 0.392$, $\hat{\rho}_4 = 0.198$, $\hat{\rho}_k \approx 0$ for $k \ge 5$.

### 2.3 Effective Sample Size ($N_{\text{eff}}$)
Using the Bartlett / Priestley spectral formula for autocorrelated time series:
$$N_{\text{eff}} = \frac{N}{1 + 2 \sum_{k=1}^{K-1} \left(1 - \frac{k}{K}\right) \rho_k}$$

For $N = 887$ observations:
- **2-Tick Contracts**: $N_{\text{eff}} \approx \frac{887}{1 + 2(0.5)(0.442)} = \frac{887}{1.442} \approx 615$ effective independent observations.
- **5-Tick Contracts**: $N_{\text{eff}} \approx \frac{887}{1 + 2(0.8 \times 0.768 + 0.6 \times 0.584 + 0.4 \times 0.392 + 0.2 \times 0.198)} \approx \frac{887}{3.32} \approx 267$ effective independent observations.

---

## 3. Power Analysis & Minimum Sample Size Requirements

### 3.1 Parameter Assumptions
- **Significance Level**: $\alpha = 0.05$ (two-tailed, $Z_{\alpha/2} = 1.96$).
- **Statistical Power**: $1 - \beta = 0.80$ ($Z_{\beta} = 0.842$).
- **Base Rate (Break-Even Hurdle)**:
  - 2-Tick: $p_0 = 0.26212$ ($\sigma_0 = \sqrt{0.26212 \times 0.73788} = 0.4398$)
  - 5-Tick: $p_0 = 0.03275$ ($\sigma_0 = \sqrt{0.03275 \times 0.96725} = 0.1780$)
- **Minimum Economically Meaningful Edge ($\delta$)**:
  - Conservative edge target: $\delta = +1.0\%$ win rate margin above break-even.

### 3.2 Sample Size Formula (Accounting for Autocorrelation)
$$N_{\text{required}} = \text{VIF} \times \frac{(Z_{\alpha/2} \sigma_0 + Z_{\beta} \sigma_1)^2}{\delta^2}$$
where $\text{VIF} = N / N_{\text{eff}}$ (Variance Inflation Factor).

### 3.3 Required Observations Table

| Contract Configuration | Break-Even $p_0$ | Target Win Rate $p_1$ | Edge $\delta$ | VIF | Required $N_{\text{eff}}$ | Required Total Observations | Estimated Stream Duration (at ~2.0s / tick) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T Contract** | 26.21% | 27.21% | +1.00% | 1.44 | 15,150 | **21,800 ticks** | ~12.1 hours |
| **2T Contract** | 26.21% | 28.21% | +2.00% | 1.44 | 3,790 | **5,460 ticks** | ~3.0 hours |
| **5T Contract** | 3.28% | 3.78% | +0.50% | 3.32 | 4,960 | **16,470 ticks** | ~9.2 hours |
| **5T Contract** | 3.28% | 4.28% | +1.00% | 3.32 | 1,240 | **4,120 ticks** | ~2.3 hours |

---

## 4. Multi-Session Regime Stratification Plan

A single 30-minute session is vulnerable to **regime capture** (e.g., temporary trending or range-bound behavior unique to that half-hour period). Future evidence collection must follow a stratified multi-session protocol:

1. **Independent Session Isolation**: Future research must span at least **4 distinct sessions** collected across separate days and market liquidity windows (e.g. London open, New York open, Tokyo session, weekend).
2. **Distinct Session UUIDs**: Each session must be assigned an immutable session ID in `sessions.db` with separate SQLite commits and tick CSV logs.
3. **Preservation of Excluded Evidence**: Every recorded observation—including losing contracts, data gaps, and stale quotes—must remain permanently indexed. No session may be discarded post-hoc.
4. **Preregistered Gate**: The multi-session confirmation protocol must be registered in `ForwardConfirmationGate` prior to commencing collection.
