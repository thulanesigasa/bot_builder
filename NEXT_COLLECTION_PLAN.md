# NEXT COLLECTION PLAN
## DERIV ONLY UPS / ONLY DOWNS QUANTITATIVE RESEARCH BOT
### Phased Protocol for Sustained Bounded SHADOW Data Collection & Independent Confirmation

[![Protocol Status](https://img.shields.io/badge/Protocol_Status-APPROVED_RESEARCH_PLAN-success)](#)
[![Validation Target](https://img.shields.io/badge/Validation_Sample_Target-N_%E2%89%A5_500-blue)](#)
[![Confirmation Target](https://img.shields.io/badge/Confirmation_Sample_Target-N_%E2%89%A5_2%2C000-orange)](#)
[![Confirmation Authority](https://img.shields.io/badge/Confirmation_Gate-EXCLUSIVE_SINGLE_AUTHORITY-brightgreen)](#)
[![Real-Money Status](https://img.shields.io/badge/Purchases-STRICTLY_DISABLED-red)](#)

---

## 1. Objective & Research Roadmap

The controlled forward execution of session `413bbee4` proved that the software infrastructure is operationally sound: live ticks stream, proposals are audited, predictions are journaled, outcomes resolve, and databases reconcile.

However, proving the presence or absence of a statistical edge in rare-event markets ($p \approx 0.033$) demands substantial empirical evidence. This document outlines the rigorous, multi-session observation plan designed to collect untainted market evidence across varying market regimes without risking capital or contaminating test data.

---

## 2. Statistical Sample-Size Determination

### 2.1 The Rare-Event Challenge
In high-frequency five-tick binary options, the base success rate is approximately $p \approx 3.28\%$. Because wins occur infrequently (on average once every 30 ticks), small samples suffer from extreme binomial variance:
- In a sample of $N = 100$, observing 1 win ($1\%$) vs 5 wins ($5\%$) is completely attributable to chance.
- At $N = 129$, the moving-block bootstrap confidence interval spanned $[0.78\%, 7.75\%]$, which easily spans the broker break-even threshold ($3.275\%$).

### 2.2 Formal Power Calculations
To detect a minimum economically meaningful edge $\Delta = +0.005$ (+0.50% edge above the $3.275\%$ break-even hurdle) with standard $80\%$ statistical power ($\beta = 0.20$) at significance level $\alpha = 0.05$:

$$N = \frac{\left(z_{\alpha/2}\sqrt{2 \bar{p}(1-\bar{p})} + z_{\beta}\sqrt{p_1(1-p_1) + p_0(1-p_0)}\right)^2}{\Delta^2}$$

Setting $p_0 = 0.0328$, $p_1 = 0.0378$, $\Delta = 0.005$:
$$N \approx \frac{(1.96 \cdot 0.254 + 0.842 \cdot 0.257)^2}{0.000025} \approx \frac{(0.498 + 0.216)^2}{0.000025} \approx \frac{0.510}{0.000025} \approx 20,400 \text{ observations}$$

Accounting for overlapping 5-tick autocorrelation ($N_{\text{eff}} \approx 0.75 \times N$), the repository establishes a three-tiered research milestone progression:

| Research Tier | Target Sample ($N$) | Effective Sample ($N_{\text{eff}}$) | Objective |
| :--- | :--- | :--- | :--- |
| **Tier 1: Exploratory Benchmark** | 500 resolved ticks | $\ge 100$ | Calibration stability, feature parity audit |
| **Tier 2: Forward Validation** | 2,000 resolved ticks | $\ge 400$ | Candidate edge qualification, EV convergence |
| **Tier 3: Authoritative Confirmation** | 5,000+ resolved ticks | $\ge 1,000$ | Final out-of-sample thesis confirmation |

---

## 3. Recommended Phased Observation Schedule

To prevent overfitting to any single time-of-day volatility regime, data collection must be partitioned into bounded sessions distributed across different market periods:

### Phase A: Exploratory Forward Sessions (Current Stage)
- **Target:** 4 distinct sessions of 30 minutes each (1,800 seconds per session).
- **Session Duration:** 1,800s (~900 ticks per session, ~850 predictions).
- **Scheduling:**
  - **Session 1:** Early Morning UTC (02:00 – 02:30 UTC)
  - **Session 2:** European Market Open (08:00 – 08:30 UTC)
  - **Session 3:** US Market Overlap (14:00 – 14:30 UTC)
  - **Session 4:** Asia-Pacific Active (20:00 – 20:30 UTC)
- **Stage Tag:** `EXPLORATORY_FORWARD`

### Phase B: Pre-Registration of Confirmation Manifest
Before running any confirmation sessions, the quantitative engineer must freeze the hypothesis:
1. Generate an immutable `ConfirmationSpecification` linking the model checksum `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a`.
2. Define target observation count ($N = 2,000$), allowed symbols (`R_75`), and minimum quote freshness.
3. Commit the manifest to `data/confirmation_manifest.json`.

### Phase C: Confirmation Forward Sessions (Untouched Future Data)
- **Target:** 6 distinct sessions of 30 minutes each conducted strictly after manifest registration.
- **Stage Tag:** `CONFIRMATION_FORWARD` (enforces admission checking).
- **Rule:** Zero code modifications, zero parameter tuning, zero model retuning between sessions.

---

## 4. Operator CLI Execution Guide

The system operator should execute the following sequence using the supported CLI:

### Step 1: Run a Bounded 30-Minute SHADOW Forward Session
```powershell
python forward_collection_service.py R_75 `
  --mode SHADOW `
  --stage EXPLORATORY_FORWARD `
  --duration 1800 `
  --interval 2.0 `
  --notes "Phase A Exploratory Session 1 - Morning UTC"
```

### Step 2: Reconcile and Audit the Collected Session
Immediately following session termination, inspect session health:
```powershell
python session_reporter.py R_75 --session <SESSION_ID>
```

### Step 3: Run Multi-Session Aggregation & Authoritative Confirmation Gate
Evaluate cumulative multi-session evidence across all registered sessions:
```powershell
# Multi-Session Aggregator
python session_research_aggregator.py R_75

# Authoritative Confirmation Gate
python forward_confirmation_gate.py R_75
```

---

## 5. Non-Negotiable Research Invariants

1. **`LIVE_EXECUTION_DISABLED = True` Permanent Hard-Lock:**
   Zero live buy orders can be placed. All sessions run in `SHADOW` mode.
2. **Zero Synthetic / Replay Records in Live Databases:**
   `data/sessions.db`, `data/forward_predictions.db`, and `data/quotes.db` must contain only genuine live Deriv market observations.
3. **Stage Segregation:**
   Exploratory data can never be retrospectively relabeled as confirmation data.
4. **Single Confirmation Authority:**
   Only `ForwardConfirmationGate` can issue `FORWARD_EDGE_CONFIRMED`. No secondary dashboard or script has this authority.
5. **Zero Historical Fallbacks:**
   If quotes are missing, EV must evaluate to `None`. No $61.03 / $2.00 placeholders are permitted.
