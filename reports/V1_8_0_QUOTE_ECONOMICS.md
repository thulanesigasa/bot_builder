# V1.8.0 Quote Economics & Expected Value Analysis

![Economics](https://img.shields.io/badge/Quote_Economics-Authentic_Broker_Proposals-blue.svg)
![Broker_Terms](https://img.shields.io/badge/Stake%2FPayout-$2.00%20%2F%20$3.91-brightgreen.svg)
![Hurdle](https://img.shields.io/badge/Break--Even_Hurdle-51.15%25-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Broker Pricing Mechanics

In Release V1.8.0, economic edge discovery is governed strictly by **real broker proposal economics**, verified against the Deriv WebSocket API (`api.derivws.com/trading/v1/options/ws/public?app_id=1089`). Theoretical or fixed reference assumptions are strictly prohibited from quote-verified reporting cohorts.

For all six synthetic volatility markets (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`) across all supported durations (2, 3, 5, 10 ticks):
- **Requested Stake**: $\$2.00$ USD
- **Broker Quoted Payout**: $\$3.91$ USD
- **Potential Net Profit**: $\$1.91$ USD (Return on Stake: $+95.5\%$)
- **Quote-Specific Break-Even Hurdle**:
  $$\text{BreakEven} = \frac{\text{AskPrice}}{\text{TotalPayout}} = \frac{2.00}{3.91} = 51.1509\% \approx 51.15\%$$

---

## 2. Formal Research Cohort Architecture

To eliminate retrospective selection bias and ensure execution-quality integrity, V1.8.0 organizes observations into four reporting cohorts:

1. **Cohort A — All Resolved Observations**:
   - Used for raw prediction scoring and unconditional frequency benchmarks.
2. **Cohort B — Chronologically Quoted Observations ($\le 60$s freshness)**:
   - Evaluates descriptive quote economics where broker quotes were collected chronologically prior to decision epoch.
3. **Cohort C — Strict SHADOW Execution-Quality Proxy ($\le 5$s freshness)**:
   - Primary economic feasibility cohort. Requires that proposal quotes were received strictly within 5 seconds prior to signal commitment.
4. **Cohort D — Untouched Preregistered Confirmation**:
   - Reserved strictly for untouched prospective sessions recorded after strategy preregistration.
   - **Mandatory Integrity Invariant (Resolving Audit Issue 4.3)**: When no preregistered confirmation session exists, Cohort D contains **zero observations, unestimated win rate/EV metrics, and status `PREREGISTRATION_REQUIRED`**. Exploratory metrics are never recycled into Cohort D.

---

## 3. Multi-Market Quote Economics Summary Table

Below is the comparative economics table across all six markets and durations evaluated against authentic Deriv proposals:

| Market Symbol | Duration | Direction | Ask Price | Payout | Break-Even Hurdle | Holdout Win Rate | Predicted EV ($) | Realized EV ($) | MBB 95% Lower Bound | Economic Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`R_100`** | 2 Ticks | CALL | $2.00 | $3.91 | 51.15% | 48.28% | -$0.0528 | -$0.1122 | -$0.1742 | Negative EV |
| **`R_100`** | 2 Ticks | PUT | $2.00 | $3.91 | 51.15% | 51.72% | +$0.0528 | +$0.0223 | -$0.0416 | Inconclusive |
| **`R_100`** | 5 Ticks | CALL | $2.00 | $3.91 | 51.15% | 47.55% | -$0.0528 | -$0.1408 | -$0.2071 | Negative EV |
| **`R_100`** | 5 Ticks | PUT | $2.00 | $3.91 | 51.15% | 52.45% | +$0.0528 | +$0.0508 | -$0.0163 | Inconclusive |
| **`R_100`** | 10 Ticks | CALL | $2.00 | $3.91 | 51.15% | 48.16% | -$0.0528 | -$0.1170 | -$0.1873 | Negative EV |
| **`R_100`** | 10 Ticks | PUT | $2.00 | $3.91 | 51.15% | 53.84% | +$0.0528 | +$0.1050 | **+$0.0075** | Exploratory Candidate |
| **`1HZ100V`** | 2 Ticks | CALL | $2.00 | $3.91 | 51.15% | 49.64% | -$0.0450 | -$0.0591 | -$0.1232 | Negative EV |
| **`1HZ100V`** | 2 Ticks | PUT | $2.00 | $3.91 | 51.15% | 50.36% | +$0.0450 | -$0.0309 | -$0.0935 | Negative EV |
| **`1HZ100V`** | 5 Ticks | CALL | $2.00 | $3.91 | 51.15% | 49.00% | -$0.0450 | -$0.0841 | -$0.1492 | Negative EV |
| **`1HZ100V`** | 5 Ticks | PUT | $2.00 | $3.91 | 51.15% | 51.00% | +$0.0450 | -$0.0059 | -$0.0710 | Negative EV |
| **`R_75`** | 2 Ticks | CALL | $2.00 | $3.91 | 51.15% | 50.36% | -$0.0450 | -$0.0309 | -$0.0941 | Negative EV |
| **`R_75`** | 2 Ticks | PUT | $2.00 | $3.91 | 51.15% | 49.64% | +$0.0450 | -$0.0591 | -$0.1219 | Negative EV |
| **`R_75`** | 5 Ticks | CALL | $2.00 | $3.91 | 51.15% | 50.22% | -$0.0450 | -$0.0364 | -$0.1042 | Negative EV |
| **`R_75`** | 5 Ticks | PUT | $2.00 | $3.91 | 51.15% | 49.78% | +$0.0450 | -$0.0536 | -$0.1205 | Negative EV |
| **`1HZ75V`** | 2 Ticks | CALL | $2.00 | $3.91 | 51.15% | 49.08% | -$0.0450 | -$0.0810 | -$0.1448 | Negative EV |
| **`1HZ75V`** | 2 Ticks | PUT | $2.00 | $3.91 | 51.15% | 50.92% | +$0.0450 | -$0.0090 | -$0.0734 | Negative EV |
| **`R_50`** | 2 Ticks | CALL | $2.00 | $3.91 | 51.15% | 49.98% | -$0.0450 | -$0.0458 | -$0.1098 | Negative EV |
| **`R_50`** | 2 Ticks | PUT | $2.00 | $3.91 | 51.15% | 50.02% | +$0.0450 | -$0.0442 | -$0.1076 | Negative EV |
| **`1HZ50V`** | 5 Ticks | CALL | $2.00 | $3.91 | 51.15% | 46.89% | -$0.0450 | -$0.1666 | -$0.2307 | Negative EV |
| **`1HZ50V`** | 5 Ticks | PUT | $2.00 | $3.91 | 51.15% | 53.11% | +$0.0450 | +$0.0766 | **+$0.0021** | Exploratory Candidate |
| **`1HZ50V`** | 10 Ticks | CALL | $2.00 | $3.91 | 51.15% | 45.80% | -$0.0450 | -$0.2092 | -$0.2785 | Negative EV |
| **`1HZ50V`** | 10 Ticks | PUT | $2.00 | $3.91 | 51.15% | 54.20% | +$0.0450 | +$0.1192 | **+$0.0216** | Exploratory Candidate |

---

## 4. Economic Synthesis & Findings

1. **Market Asymmetry vs Noise**: The majority of directional combinations yield negative expected value relative to the $51.15\%$ broker hurdle.
2. **Exploratory Outliers**: Three combinations (`R_100` 10T PUT, `1HZ50V` 5T PUT, `1HZ50V` 10T PUT) demonstrated modest exploratory positive returns with 95% bootstrap lower bounds marginally exceeding zero.
3. **Mandatory Confirmation Requirement**: Under research integrity rules, exploratory positive EV cannot be reported as validated until confirmed on untouched, future prospective data.

---

*Report certified by `rise_fall_research.py` — Release V1.8.0 Quantitative Economics Suite*
