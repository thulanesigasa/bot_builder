# V1.7.4.1 AI STRATEGY DISCOVERY & MULTIPLE-TESTING STATISTICAL AUDIT

[![Version](https://img.shields.io/badge/Version-V1.7.4.1-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Advisory-Firewall](https://img.shields.io/badge/Advisory%20Layer-Execution%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multiple-Testing](https://img.shields.io/badge/Multiple%20Testing-Bonferroni%20%2B%20Monotonic%20BH-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Advisory Mandate

In quantitative finance, unrestricted automated data-mining across hundreds of technical indicators inevitably surfaces spurious "edges" due to selection bias and p-hacking.

Under Master Development Prompt V1.7.4.1 Part 6, the strategy discovery engine (`strategy_discovery.py`) is architected with strict mathematical controls:
1. **Advisory Firewall**: Machine learning and AI hypothesis generators can **NEVER** authorize live or simulated trade execution.
2. **Monotonic Benjamini-Hochberg (FDR)**: Step-up procedure with reverse cumulative minimum enforces proper false discovery control.
3. **Exact Binomial Survival**: Rare-event regimes (5-tick contracts with $p \approx 3.125\%$) are evaluated via exact combinatorial summation rather than flawed normal approximations.
4. **Purged Sampling**: Overlapping contract outcome dependencies are purged via stride $h = \text{duration} + 1$.

---

## 2. Advisory Architecture & Permanent Firewall

```
                       STRATEGY DISCOVERY FIREWALL ARCHITECTURE
                                          │
                 ┌────────────────────────┴────────────────────────┐
                 ▼                                                 ▼
     AI / STATISTICAL RESEARCH ENGINE                 EXECUTION AUTHORIZATION GATE
  ┌──────────────────────────────────────┐         ┌──────────────────────────────────────┐
  │ • Proposes predeclared hypotheses    │         │ • Centralized DecisionGate           │
  │ • Tests purged historical ticks      │ ──X───> │ • ForwardConfirmationGate            │
  │ • Calculates Bonferroni & FDR p-vals │ BLOCKED │ • LIVE_EXECUTION_DISABLED = True     │
  │ Status: ADVISORY RESEARCH ONLY       │         │ Status: ZERO AUTONOMOUS BUY ORDERS   │
  └──────────────────────────────────────┘         └──────────────────────────────────────┘
```

The system strictly enforces:
```python
IS_ADVISORY_ONLY: bool = True
EXECUTION_AUTHORIZATION_DISABLED: bool = True
```
No output, score, or recommendation produced by `StrategyDiscoveryEngine` can bypass the centralized confirmation gate or initiate buy orders.

---

## 3. Multiple-Testing Correction Audit

When testing $m$ candidate hypotheses simultaneously, the probability of at least one false positive (family-wise error) scales as $1 - (1 - \alpha)^m$. To counteract this, two complementary corrections are applied:

### A. Bonferroni Family-Wise Error Rate (FWER)
Controls the probability of making even one Type I error:
$$p_{\text{Bonferroni}, i} = \min(1.0, p_i \times m)$$

### B. Correct Monotonic Benjamini-Hochberg (FDR)
Controls the expected proportion of false discoveries among rejected hypotheses ($\text{FDR} \le q$). The step-up procedure is formally implemented as:

1. **Sort**: Order raw p-values in ascending sequence $p_{(1)} \le p_{(2)} \le \dots \le p_{(m)}$.
2. **Rank Scale**: Compute raw adjusted p-values:
   $$q_{(i)} = \min\left(1.0, p_{(i)} \times \frac{m}{i}\right) \quad \text{for } i = 1, \dots, m$$
3. **Reverse Cumulative Minimum (Step-Up Monotonicity)**:
   $$q'_{(i)} = \min\left(q_{(i)}, q'_{(i+1)}\right) \quad \text{for } i = m-1, m-2, \dots, 1 \quad \text{with } q'_{(m)} = q_{(m)}$$
4. **Bounds Enforcement**: Clamp $q'_{(i)} \in [0.0, 1.0]$.
5. **Restore Ordering**: Map adjusted values back to original hypothesis indices.

#### Verification of Monotonic Correction:
```
Raw p-values:             [0.010,  0.040,  0.030]  (m = 3)
Sorted p-values:          p_(1)=0.010, p_(2)=0.030, p_(3)=0.040
Raw Rank Scaling:         q_(1)=0.030, q_(2)=0.045, q_(3)=0.040  <- Monotonicity violated!
Reverse Cumulative Min:   q'_(3)=0.040, q'_(2)=min(0.045, 0.040)=0.040, q'_(1)=0.030
Final Adjusted FDR:       [0.030,  0.040,  0.040]  <- Verified Monotonic!
```

---

## 4. Rare-Event Binomial Survival vs Normal Approximation

When testing whether an empirical win rate exceeds a baseline or broker hurdle:
$$H_0: P \le P_0 \quad \text{vs} \quad H_1: P > P_0$$

### Critical Mathematical Requirement:
The Gaussian approximation to the binomial distribution relies on the Central Limit Theorem and requires $n \cdot p \ge 5$ and $n \cdot (1-p) \ge 5$.
- For 5-Tick contracts ($p = 0.03125$), a sample of $n = 100$ yields $n \cdot p = 3.125 < 5$.
- In this regime, Gaussian tails understate the true p-value, creating dangerous false positive signals.

### Pure Python Exact Implementation:
`strategy_discovery.py` implements exact combinatorial summation for all $n \le 2000$:
$$P(X \ge k) = \sum_{j=k}^n \binom{n}{j} p^j (1 - p)^{n - j}$$
- Numerically stable evaluation using standard library `math.comb`.
- Returns `(p_val, is_exact)` where `is_exact = True` for $n \le 2000$.
- Continuity-corrected normal approximation is reserved strictly for $n > 2000$, with `is_exact = False`.

---

## 5. Controlled Predeclared Hypothesis Families

Unrestricted data mining is prohibited. The research engine evaluates only five predeclared behavioral hypotheses on `R_75`:

| Hypothesis ID | Target | Duration | Behavioral Thesis | Feature Condition | Economic Hurdle |
| :--- | :---: | :---: | :--- | :--- | :---: |
| `HYP_2T_STREAK_CONT_UP` | RUNHIGH | 2t | Streak momentum continuation | `streak_bin in ('HIGH_UP_STREAK', 'EXTREME_UP_STREAK')` | 26.212% |
| `HYP_2T_STREAK_CONT_DOWN` | RUNLOW | 2t | Downward streak continuation | `streak_bin in ('HIGH_DOWN_STREAK', 'EXTREME_DOWN_STREAK')` | 26.212% |
| `HYP_2T_VOL_REGIME_LOW_UP` | RUNHIGH | 2t | Low-volatility bullish trend | `vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BULL', 'MILD_BULL')` | 26.212% |
| `HYP_2T_VOL_REGIME_LOW_DOWN` | RUNLOW | 2t | Low-volatility bearish trend | `vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BEAR', 'MILD_BEAR')` | 26.212% |
| `HYP_2T_REVERSAL_EXTREME_DROP`| RUNHIGH | 2t | Mean-reverting bounce after drop| `mom_bin == 'STRONG_BEAR' and accel_bin == 'ACCEL_DOWN'` | 26.212% |

### Purging Rule:
To prevent serial correlation, observations are sampled with stride $h = \text{duration} + 1 = 3$ ticks. No adjacent observations share forward price movements.
