# V1.7.4.1 QUOTE ECONOMICS & PROVENANCE INTEGRITY REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4.1-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Quote-Economics](https://img.shields.io/badge/Quote%20Economics-Verified%20Lookahead--Free-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Mode-Separation](https://img.shields.io/badge/Mode%20Separation-Enforced-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Core Mandate

In quantitative research, assuming that a theoretical or historical reference payout is actively executable at every decision timestamp introduces severe selection bias and phantom profitability.

Under Master Development Prompt V1.7.4.1 Part 2, this report formally decouples **Reference Scenario Valuation** from **Quote-Verified Economic Evidence**. It provides the authoritative mathematical equations, coverage definitions, and rejection taxonomy required for reproducible research on Deriv's `RUNHIGH` and `RUNLOW` contracts.

---

## 2. Dual Evaluation Modes

```
                                      EVALUATION ARCHITECTURE
                                                 │
                   ┌─────────────────────────────┴─────────────────────────────┐
                   ▼                                                           ▼
     REFERENCE_SCENARIO MODE                                      QUOTE_VERIFIED MODE
  ┌─────────────────────────────────────┐                     ┌─────────────────────────────────────┐
  │ Uses fixed hypothetical payouts:    │                     │ Requires genuine persisted quotes:  │
  │ • 2-Tick Payout: $7.63 on $2.00     │                     │ • Quote response <= Decision epoch  │
  │ • 5-Tick Payout: $61.07 on $2.00    │                     │ • Matched symbol, duration & type   │
  │ • Coverage: STRICTLY 0.0%           │                     │ • Freshness <= 60.0 seconds         │
  │ Status: ILLUSTRATIVE ONLY           │                     │ Status: AUTHORITATIVE EVIDENCE      │
  └─────────────────────────────────────┘                     └─────────────────────────────────────┘
```

### A. Reference Scenario Mode (`REFERENCE_SCENARIO`)
- **Purpose**: Evaluates candidate models against canonical market-maker pricing hurdles for exploratory screening.
- **Rules**:
  1. Uses supplied reference payouts: $\$7.63$ (2T) and $\$61.07$ (5T) for a $\$2.00$ reference stake.
  2. Implied break-even hurdles:
     $$\text{BreakEven}_{2T} = \frac{\$2.00}{\$7.63} \approx 26.212\%$$
     $$\text{BreakEven}_{5T} = \frac{\$2.00}{\$61.07} \approx 3.275\%$$
  3. **Verified Quote Coverage is reported as 0.0%**: The system never claims that quotes were verified or available during historical replay.
  4. All associated EV metrics are explicitly flagged as illustrative and cannot authorize model promotion.

### B. Quote-Verified Mode (`QUOTE_VERIFIED`)
- **Purpose**: Evaluates prospective SHADOW and forward confirmation observations using strictly matched, real-time proposal records.
- **Rules**:
  1. Every decision record $i$ at epoch $t_i$ must match an individual quote record $q$.
  2. Lookahead protection requires $t_{\text{response}}(q) \le t_i$.
  3. Freshness requirement requires $t_i - t_{\text{response}}(q) \le 60.0\text{ s}$.
  4. Contract duration, direction, currency, and symbol must match strictly.
  5. If quote evidence is unavailable, EV is declared `None` (unavailable).

---

## 3. Multi-Tier Granular Quote Coverage Framework

To prevent the recurrence of artificial 100% quote availability claims, coverage is computed across four distinct tiers:

$$\text{Coverage}_{\text{Tier}} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Decision } i \text{ satisfies Tier Criteria})}{N} \times 100\%$$

| Coverage Tier | Validation Criteria | Interpretation |
| :--- | :--- | :--- |
| **1. Raw Association** | Quote record exists with matching symbol, duration, and direction | Establishes basic database record presence |
| **2. Chronological Validity** | $t_{\text{response}}(q) \le t_{\text{decision}}$ | Lookahead-free guarantee; quote preceded decision |
| **3. Economic Validity** | $\text{AskPrice}(q) > 0$ and $\text{TotalPayout}(q) > 0$ | Ensures non-zero, valid pricing mechanics |
| **4. Execution Quality** | $(t_{\text{decision}} - t_{\text{response}}) \le 60.0\text{ s}$ and duration match | Practical freshness; suitable for research decisions |

---

## 4. Expected Value Formulation & Interpretation

The system strictly distinguishes three distinct economic figures:

### 1. Ex-Ante Predicted Expected Value ($\text{EV}_{\text{ex-ante}}$)
Computed prior to outcome observation using the model's calibrated probability estimate:
$$\text{EV}_{\text{ex-ante}} = \hat{P}_{\text{model}}(\text{Win}) \times \text{TotalPayout} - \text{AskPrice}$$
- For 2T baseline ($P = 25.0\%$, Payout = $\$7.63$, Ask = $\$2.00$):
  $$\text{EV} = 0.25 \times 7.63 - 2.00 = -\$0.0925\text{ (per contract)}$$
- For 5T baseline ($P = 3.125\%$, Payout = $\$61.07$, Ask = $\$2.00$):
  $$\text{EV} = 0.03125 \times 61.07 - 2.00 = -\$0.0916\text{ (per contract)}$$

### 2. Retrospective Realized Return ($\text{Return}_{\text{realized}}$)
Computed after outcomes are resolved across $N$ observations:
$$\text{Return}_{\text{realized}} = \frac{N_{\text{wins}} \times \text{TotalPayout} - N \times \text{AskPrice}}{N}$$
This represents hypothetical historical P&L and must never be represented as an ex-ante probability or predictive edge.

### 3. Dependence-Aware Conservative Expected Value ($\text{EV}_{\text{cons}}$)
Computed via Moving-Block Bootstrap (MBB) 95% lower bound to account for overlapping contract paths:
$$\text{EV}_{\text{cons}} = \text{Percentile}_{5\%}\left(\left\{ \text{EV}_b \right\}_{b=1}^B\right)$$
- If sample size $N < \max(30, 2 \times \text{block\_size})$, $\text{EV}_{\text{cons}}$ is **UNAVAILABLE (`None`)**.
- The system never substitutes the empirical point estimate as a conservative bound.

---

## 5. Decision Gate Quote Rejection Taxonomy

When evaluating decisions in Gate 6 of `decision_gate.py`, quotes are rejected under the following hierarchy:

| Rejection Code | Trigger Condition | System Action |
| :--- | :--- | :--- |
| `QUOTE_UNAVAILABLE` | No quote record found in database for decision epoch | Decision blocked (`NO_TRADE`) |
| `QUOTE_PRICE_INVALID` | $\text{AskPrice} \le 0$ or $\text{TotalPayout} \le 0$ | Decision blocked (`NO_TRADE`) |
| `QUOTE_WRONG_DURATION` | Quote contract duration $\ne$ decision contract duration | Cross-duration rejected (`NO_TRADE`) |
| `QUOTE_WRONG_SYMBOL` | Quote symbol $\ne$ evaluated symbol (`R_75`) | Decision blocked (`NO_TRADE`) |
| `QUOTE_STALE` | Quote age $(t_{\text{decision}} - t_{\text{response}}) > 60.0\text{ s}$ | Decision blocked (`NO_TRADE`) |
| `QUOTE_LOOKAHEAD_REJECTED` | Quote response timestamp $> t_{\text{decision}}$ | Lookahead rejected (`NO_TRADE`) |
| `NEGATIVE_CONSERVATIVE_EV` | $\text{EV}_{\text{cons}} < 0.0$ or $\text{EV}_{\text{cons}}$ is `None` | Decision blocked (`NO_TRADE`) |
