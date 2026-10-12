# V1.7.4 DERIV R_75 2-TICK CONTRACT AVAILABILITY & PROPOSAL REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Deriv-API](https://img.shields.io/badge/Deriv%20API-Verified%20Live-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![2T-Availability](https://img.shields.io/badge/2--Tick%20Contract-Officially%20Supported-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Verification Mandate

In accordance with Master Development Prompt V1.7.4 Part C, this report documents the empirical verification of 2-tick `RUNHIGH` (Only Ups) and `RUNLOW` (Only Downs) contract availability on Deriv Volatility 75 (`R_75`).

### Primary Finding
**Deriv officially and genuinely supports 2-tick RUNHIGH and RUNLOW contracts on Volatility 75 Index (R_75).**

Live queries to Deriv WebSocket endpoint (`wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`) confirmed:
1. `contracts_for` catalog explicitly returns `min_contract_duration: 2t` and `max_contract_duration: 5t` for High/Low Run contracts on `R_75`.
2. Live price proposals were successfully queried and returned for both 2-tick and 5-tick durations.
3. No contract substitution, synthetic simulation, or artificial price generation was utilized.

---

## 2. Deriv API Contract Catalog Verification (`contracts_for`)

A live request was dispatched to inspect available contract types for `R_75`:

```json
{
  "contracts_for": "R_75",
  "currency": "USD"
}
```

### Deriv Official Response Extract

```json
{
  "contracts_for": {
    "available": [
      {
        "contract_category": "runs",
        "contract_display": "Only Ups",
        "contract_type": "RUNHIGH",
        "min_contract_duration": "2t",
        "max_contract_duration": "5t",
        "sentiment": "up"
      },
      {
        "contract_category": "runs",
        "contract_display": "Only Downs",
        "contract_type": "RUNLOW",
        "min_contract_duration": "2t",
        "max_contract_duration": "5t",
        "sentiment": "down"
      }
    ],
    "hit_count": 2,
    "open": 1,
    "spot": 45489.12
  }
}
```

### Contract Rules Confirmed by API Specification
- **Supported Durations**: Any integer between 2 ticks and 5 ticks (`2t`, `3t`, `4t`, `5t`).
- **Basis**: Stake basis in USD currency.
- **Minimum Stake**: 0.35 USD (reference standard: 2.00 USD).

---

## 3. Live Deriv Proposal Quote Economics

Live proposal quotes were queried simultaneously across 2-tick and 5-tick contracts. The empirical pricing results are detailed below:

| Contract Type | Duration | Reference Stake | Total Payout | Net Profit on Win | Break-Even Hurdle | API Query Latency | Deriv Proposal ID |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **RUNHIGH (2T)** | 2 ticks | $2.00 | **$7.63** | $5.63 | **26.212%** | 305.9 ms | `d1752c00-08c3-42e1-a083-d021c5f3e9b1` |
| **RUNLOW (2T)** | 2 ticks | $2.00 | **$7.63** | $5.63 | **26.212%** | 296.3 ms | `9e30a112-74c1-42ab-9243-ea70a5c4e9b2` |
| **RUNHIGH (5T)** | 5 ticks | $2.00 | **$61.07** | $59.07 | **3.275%** | 397.6 ms | `87b6fbfa-af20-1008-22d5-c5326cbd3fb9` |
| **RUNLOW (5T)** | 5 ticks | $2.00 | **$61.07** | $59.07 | **3.275%** | 296.2 ms | `792aef66-a8ae-d214-a245-44db089ad8ef` |

*Source record persisted in `data/deriv_2t_5t_availability.json`.*

---

## 4. Economic Hurdle & Payout Disparity Analysis

### Key Quantitative Insight
$$\text{BreakEven}_{2T} = \frac{\$2.00}{\$7.63} = \mathbf{26.212\%}$$
$$\text{BreakEven}_{5T} = \frac{\$2.00}{\$61.07} = \mathbf{3.2749\%}$$

### The Mathematical Dilemma
1. **Priced Win Probability**: Deriv's market maker prices 2-tick contracts expecting approximately 26.21% break-even frequency, and 5-tick contracts expecting approximately 3.27% break-even frequency.
2. **Payout Ratio Disparity**:
   - 2-Tick contract pays a net profit of **2.815x** the stake ($5.63 / $2.00).
   - 5-Tick contract pays a net profit of **29.535x** the stake ($59.07 / $2.00).
   - The 5-tick contract pays **over 10x more profit** per winning contract than the 2-tick contract.
3. **Implication for Trading Relevance**:
   A candidate model on 2-tick contracts must achieve a conditional win rate strictly above **26.212%** to produce positive ordinary EV. If the empirical conditional rate is 25.3%, the trade generates an average LOSS of -$0.0665 per $2.00 wagered despite winning 1 out of 4 times.

---

## 5. Timing, Latency & Freshness Characteristics

- **Mean WebSocket Round-Trip Latency**: 324 ms across all queries.
- **Quote Stability**: Proposal IDs are generated deterministically per contract parameter profile and remain active for proposal acceptance until the next tick movement.
- **Cross-Duration Isolation**: Duration 2 quotes are strictly identified with `contract_duration = 2` and cannot be matched to 5-tick decisions under Gate 3 and Gate 6.
