# V1.7.4.4 Statistical Strategy & Positive-EV Edge Assessment

![Release](https://img.shields.io/badge/Release-V1.7.4.4-0A84FF)
![Edge_Verdict](https://img.shields.io/badge/Verdict-NO_VALIDATED_POSITIVE_EV_EDGE-FF453A)
![Ladder_Level](https://img.shields.io/badge/Ladder_Level-Level_0-grey)
![Style](https://img.shields.io/badge/Style-Zero_Emojis_Enforced-64D2FF)
![Safety](https://img.shields.io/badge/Safety-LIVE_EXECUTION_DISABLED-FF453A)

---

## 1. Executive Summary & Authoritative Verdict

Following the comprehensive repair of the prospective schema pipeline, the independent reconstruction of historical market outcomes, and quote-matched economic valuation, the quantitative trading models across both 2-tick and 5-tick durations on the Deriv Volatility 75 Index (`R_75`) were reassessed against the Positive-EV Evidence Ladder.

### Authoritative Scientific Verdict
**`NO_VALIDATED_POSITIVE_EV_EDGE` (Level 0)**

Under no circumstances has an exploitable trading edge cleared the statistical and risk hurdles required for production trading or capital risk. Real-money trade execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).

---

## 2. Hypothesis Reassessment Protocol

Three predeclared research hypotheses were evaluated across empirical forward observations:

### Hypothesis H1: 2-Tick Directional Asymmetry Edge
- **Premise:** Short-duration tick inertia on `R_75` creates predictable momentum in either `RUNHIGH` or `RUNLOW` that exceeds the broker hurdle of $26.21\%$.
- **Empirical Findings:**
  - In session `c14ac5fb`, 2T RUNHIGH exhibited an observed win rate of $30.88\%$ ($42/136$), but the model's ex-ante predicted probability was only $0.2561$, yielding an ordinary EV of $-\$0.0463$ and a conservative 95% bootstrap lower bound of $-\$0.2608$.
  - 2T RUNLOW exhibited an observed win rate of only $13.97\%$ ($19/136$), substantially below the break-even hurdle ($-\$0.1886$ EV).
- **Hypothesis Status:** **REJECTED.** No sustained directional momentum edge exceeds broker transaction costs.

### Hypothesis H2: 5-Tick Long-Tail Run Edge
- **Premise:** Long-tail consecutive tick trends on `R_75` yield win rates exceeding the $3.27\%$ break-even hurdle for 5-tick contracts.
- **Empirical Findings:**
  - In session `c14ac5fb`, 5T RUNHIGH experienced $10$ wins out of $136$ ($7.35\%$), generating positive ex-ante EV ($+\$0.0572$) and high retrospective returns ($+\$2.4904$/contract).
  - However, because the contract pays $30.5\times$ the stake with an infrequent win rate, the distribution exhibits extreme payoff skewness. The Moving-Block Bootstrap (MBB) 95% lower bound for expected return is $-\$0.6529$.
- **Hypothesis Status:** **UNCONFIRMED & REJECTED FOR CAPITAL ALLOCATION.** High variance invalidates risk qualification.

### Hypothesis H3: Historical vs Forward Generalization
- **Premise:** Feature distributions and conditional probability estimates calibrated on historical CSV ticks translate directly to live WebSocket forward tick streams.
- **Empirical Findings:**
  - Brier Skill Scores against naive random walk baselines showed negative skill for 2T RUNHIGH ($-0.1609$) and 5T RUNHIGH ($-1.3060$), indicating that the models suffered from probability miscalibration during live market conditions.
- **Hypothesis Status:** **UNSUPPORTED.** Model forecasts require dynamic calibration refinement before forward deployment.

---

## 3. Positive-EV Evidence Ladder Evaluation

| Level | Evidence Classification | Required Criteria | Current System Status |
| :--- | :--- | :--- | :--- |
| **Level 0** | **NO_VALIDATED_POSITIVE_EV_EDGE** | Fails ordinary EV or conservative MBB hurdle | **ACTIVE / ENFORCED** |
| **Level 1** | **EXPLORATORY_POSITIVE_EV_SIGNAL** | Ord EV $> 0$ in unconfirmed exploratory sample | Not qualified due to conservative risk failure |
| **Level 2** | **QUOTE_VERIFIED_RESEARCH_CANDIDATE** | 100% quote verified, MBB $\ge 0$ over $N \ge 100$ | Not qualified |
| **Level 3** | **CONFIRMATION_REGISTERED** | Registered with `ForwardConfirmationGate` prior to session | Not reached |
| **Level 4** | **POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED** | Pass qualification on untouched confirmation stream | Not reached |

---

## 4. Methodological Guards & Anti-Overfitting Controls

1. **Dependence-Aware Uncertainty:** Standard binomial Wilson intervals assume independent, identically distributed trials. Because market ticks exhibit serial correlation, all qualification decisions enforce Moving-Block Bootstrap (MBB) resampling.
2. **Multiple-Testing Corrections:** Evaluated across 4 simultaneous configurations without post-hoc cherry-picking.
3. **No Retrospective Edge Promotion:** Short-term lucky winning runs (such as the 42 wins in 2T RUNHIGH) are not promoted as validated edges when ex-ante models did not forecast an edge.
4. **Permanent Compile-Time Safety Guard:**
   ```python
   LIVE_EXECUTION_DISABLED: bool = True
   ```
   No automated order routing exists in the codebase.
