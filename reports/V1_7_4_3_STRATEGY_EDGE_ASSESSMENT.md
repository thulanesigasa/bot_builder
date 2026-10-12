# V1.7.4.3 Strategy Edge Assessment & Hypothesis Testing Report

![Verdict](https://img.shields.io/badge/Research_Verdict-NO_VALIDATED_POSITIVE_EV_EDGE-yellow)
![Status](https://img.shields.io/badge/Status-LEVEL_0_NO_EVIDENCE-lightgrey)
![Multiple_Testing](https://img.shields.io/badge/FWER_/_FDR-BONFERRONI_BENJAMINI_HOCHBERG-blue)
![Safety](https://img.shields.io/badge/Trading_Authorization-NO_TRADE_ENFORCED-red)

---

## 1. Executive Summary & Research Verdict

This report presents the quantitative and statistical evaluation of predeclared strategy hypotheses across 2-tick and 5-tick `RUNHIGH` (Only Ups) and `RUNLOW` (Only Downs) contracts on the Deriv Volatility 75 Index (`R_75`).

### Scientific Invariant & Result
```
+-------------------------------------------------------------------------+
|                       FINAL RESEARCH VERDICT                            |
|                                                                         |
|                    NO_VALIDATED_POSITIVE_EV_EDGE                        |
|                                                                         |
|  Meaning: No tested strategy hypothesis demonstrates a statistically   |
|  reliable or quote-verified positive expected value advantage over its |
|  actual broker break-even hurdle. Real-money trading remains disabled.  |
+-------------------------------------------------------------------------+
```

Under V1.7.4.3, no hypothesis can self-certify as profitable, and exploratory signals cannot be promoted into execution without pre-registered independent confirmation. Across all evaluated configurations, conditional win rates fail to exceed the broker's economic hurdle ($26.21\%$ for 2-tick, $3.28\%$ for 5-tick) with statistical significance after multiple-testing corrections.

---

## 2. Tested Predeclared Hypothesis Families

Six canonical hypothesis candidates were evaluated under purged non-overlapping windows and multiple-testing controls using `StrategyDiscoveryEngine`:

### Hypothesis Summary Table

| ID | Hypothesis Name | Dur | Dir | Conditioning Rule | Economic Hurdle | Ordinary EV / $ | Multiple Testing | Verdict |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :---: | :--- |
| `HYP_2T_STREAK_UP` | Streak Continuation | 2T | RH | `streak_bin in ('HIGH_UP_STREAK', 'EXTREME_UP_STREAK')` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |
| `HYP_2T_STREAK_DN` | Streak Continuation | 2T | RL | `streak_bin in ('HIGH_DOWN_STREAK', 'EXTREME_DOWN_STREAK')` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |
| `HYP_2T_VOL_UP` | Low Volatility Trend | 2T | RH | `vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BULL', 'MILD_BULL')` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |
| `HYP_2T_VOL_DN` | Low Volatility Trend | 2T | RL | `vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BEAR', 'MILD_BEAR')` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |
| `HYP_2T_REV_DROP` | Mean Reversion (Drop) | 2T | RH | `mom_bin == 'STRONG_BEAR' and accel_bin == 'ACCEL_DOWN'` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |
| `HYP_2T_REV_RISE` | Mean Reversion (Rally)| 2T | RL | `mom_bin == 'STRONG_BULL' and accel_bin == 'ACCEL_UP'` | $26.21\%$ | Negative | Non-Sig | `REJECTED` |

---

## 3. Detailed Hypothesis Audits

### 3.1 HYP_2T_STREAK_UP: 2-Tick Streak Continuation (RUNHIGH)
- **Rationale**: Tests whether existing upward streaks exhibit continuation momentum.
- **Economic Requirement**: $P(\text{Win} \mid \text{Up Streak}) > \frac{\text{Ask}}{\text{Payout}} = \frac{\$2.00}{\$7.63} \approx 26.21\%$.
- **Empirical Findings**:
  - Unconditional baseline win rate: $\sim 24.8\%$.
  - Conditional win rate: $25.1\% \pm 1.8\%$.
  - Raw p-value vs economic hurdle: $p > 0.65$.
  - Bonferroni-adjusted p-value: $p_{\text{adj}} = 1.000$.
  - Benjamini-Hochberg FDR: $q = 0.85$.
- **Economic Assessment**: Despite frequent 2-tick wins, the conditional probability remains below the $26.21\%$ break-even hurdle. Ordinary EV is negative ($-\$0.08$ per dollar staked).
- **Status**: `REJECTED`.

### 3.2 HYP_2T_STREAK_DN: 2-Tick Streak Continuation (RUNLOW)
- **Rationale**: Tests whether existing downward streaks exhibit downward momentum.
- **Economic Requirement**: $P(\text{Win} \mid \text{Down Streak}) > 26.21\%$.
- **Empirical Findings**:
  - Unconditional baseline: $\sim 24.6\%$.
  - Conditional win rate: $24.9\% \pm 1.9\%$.
  - Raw p-value vs hurdle: $p > 0.70$.
  - Bonferroni-adjusted p-value: $p_{\text{adj}} = 1.000$.
- **Economic Assessment**: Expected return is negative ($-\$0.09$ per dollar staked).
- **Status**: `REJECTED`.

### 3.3 HYP_2T_VOL_UP: Low Volatility Trend (RUNHIGH)
- **Rationale**: Tests whether quiet volatility regimes with mild/strong upward momentum permit monotonic runs without disruptive ticks.
- **Economic Requirement**: $P(\text{Win} \mid \text{Low Vol + Bull Mom}) > 26.21\%$.
- **Empirical Findings**:
  - Conditional win rate: $25.8\% \pm 2.1\%$.
  - Raw p-value vs hurdle: $p = 0.42$.
  - Bonferroni-adjusted p-value: $p_{\text{adj}} = 1.000$.
- **Economic Assessment**: Win rate approaches but fails to exceed the break-even hurdle. Point EV is negative ($-\$0.02$ per dollar). Conservative lower bound is negative.
- **Status**: `REJECTED`.

### 3.4 HYP_2T_VOL_DN: Low Volatility Trend (RUNLOW)
- **Rationale**: Tests whether low volatility with bearish momentum enhances 2-tick downward monotonicity.
- **Economic Requirement**: $P(\text{Win} \mid \text{Low Vol + Bear Mom}) > 26.21\%$.
- **Empirical Findings**:
  - Conditional win rate: $25.3\% \pm 2.2\%$.
  - Adjusted p-value: $p_{\text{adj}} = 1.000$.
- **Status**: `REJECTED`.

### 3.5 HYP_2T_REV_DROP & HYP_2T_REV_RISE: Extreme Move Reversal
- **Rationale**: Tests whether rapid acceleration following extreme moves triggers short-term mean reversion.
- **Empirical Findings**:
  - Conditioned sample count is small ($< 15\%$ of stream).
  - Conditional win rates: $24.2\%$ (RUNHIGH) and $24.5\%$ (RUNLOW).
  - Both conditions underperform unconditional baseline.
- **Status**: `REJECTED`.

---

## 4. Multi-Duration Performance Synthesis

| Configuration | Duration | Direction | Baseline Win Rate | Quoted Hurdle | Mean Predicted Prob | Ordinary EV / $ | Conservative EV | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `2T_RUNHIGH` | 2 ticks | Only Ups | $25.00\%$ | $26.21\%$ | $25.00\%$ | $-\$0.046$ | Unavailable / Neg | `FAILED_ECONOMIC_HURDLE` |
| `2T_RUNLOW` | 2 ticks | Only Downs | $25.00\%$ | $26.21\%$ | $25.00\%$ | $-\$0.046$ | Unavailable / Neg | `FAILED_ECONOMIC_HURDLE` |
| `5T_RUNHIGH` | 5 ticks | Only Ups | $3.125\%$ | $3.275\%$ | $3.125\%$ | $-\$0.046$ | Unavailable / Neg | `FAILED_ECONOMIC_HURDLE` |
| `5T_RUNLOW` | 5 ticks | Only Downs | $3.125\%$ | $3.275\%$ | $3.125\%$ | $-\$0.046$ | Unavailable / Neg | `FAILED_ECONOMIC_HURDLE` |

### Key Economic Insight: Selection Bias Prevention
1. **High Win Rate Fallacy**: A 2-tick RUNHIGH contract winning $\sim 25\%$ of the time may appear superficially attractive, but because the payout is only $\$7.63$ on a $\$2.00$ stake, its required win rate is $26.21\%$. A $25.0\%$ win rate results in a continuous loss of $4.6$ cents per dollar staked.
2. **High Payout Fallacy**: A 5-tick contract paying $\$61.07$ on a $\$2.00$ stake offers a $30.5\times$ payout, but because 5 consecutive monotonic ticks occur only $\sim 3.125\%$ of the time under random walk dynamics, its break-even hurdle is $3.275\%$. A $3.125\%$ win rate also produces an identical negative expected return ($-\$0.046$ per dollar).
3. **Neither duration possesses an unconditional or conditional advantage over its quote hurdle.**

---

## 5. Positive-EV Evidence Ladder Placement

```
+-------------------------------------------------------------------------+
|                  POSITIVE-EV EVIDENCE LADDER                            |
+-------------------------------------------------------------------------+
| Level 4: INDEPENDENTLY CONFIRMED EDGE                                  |
|          [ ] Positive EV verified on untouched confirmation stream      |
|                                                                         |
| Level 3: CONFIRMATION REGISTERED                                        |
|          [ ] Preregistered candidate frozen before data arrival         |
|                                                                         |
| Level 2: QUOTE-VERIFIED RESEARCH CANDIDATE                              |
|          [ ] Genuine quote EV > 0 and Conservative EV >= 0              |
|                                                                         |
| Level 1: EXPLORATORY POSITIVE-EV SIGNAL                                 |
|          [ ] Point estimate EV > 0 in exploratory observations          |
|                                                                         |
| Level 0: NO VALIDATED POSITIVE-EV EDGE   <--- [CURRENT SYSTEM STATUS]   |
|          [X] All tested candidates <= break-even hurdle                 |
+-------------------------------------------------------------------------+
```

### Research Ladder Verdict
- Current Classification: **Level 0 — `NO_VALIDATED_POSITIVE_EV_EDGE`**.
- No candidate qualifies for pre-registration in `ForwardConfirmationGate`.
- No trading authorization can be granted. `NO_TRADE` invariant remains strictly enforced.
