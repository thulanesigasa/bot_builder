# V1.8.0 Rise/Fall Contract Specification & Entry Mapping Audit

![Contract](https://img.shields.io/badge/Contract-Rise%2FFall_(CALL%2FPUT)-blue.svg)
![Broker_API](https://img.shields.io/badge/Deriv_API-Verified-green.svg)
![Mapping_Audit](https://img.shields.io/badge/V0_vs_V1_Disagreement-33%25_at_2T-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Objective

This audit establishes the formal broker specification, equality mechanics, and non-purchasing proxy definitions for **Rise/Fall (`CALL` / `PUT`) contracts** across all six Deriv synthetic volatility markets (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`) in Release V1.8.0.

Furthermore, this report directly resolves **Audit Issue 4.2 (Section 4.2)**: independently verifying whether outcome differences exist between the signal-tick proxy (`MAPPING_V0_SIGNAL_TICK_ENTRY`) and the canonical broker next-tick proxy (`MAPPING_V1_NEXT_TICK_ENTRY`).

---

## 2. Broker Contract Semantics & Equality Rules

### 2.1 Canonical Broker Definitions

From live Deriv API WebSocket queries (`api.derivws.com/trading/v1/options/ws/public?app_id=1089`) requesting proposal contracts on all target markets:
- **Rise (`CALL`)**:
  *API Longcode*: `"Win payout if Volatility Index after D ticks is strictly higher than entry spot."`
  *Mathematical Condition*:
  $$\text{Outcome}_{\text{CALL}} = \begin{cases} 1 & \text{if } S_{\text{expiry}} > S_{\text{entry}} \\ 0 & \text{if } S_{\text{expiry}} \le S_{\text{entry}} \end{cases}$$

- **Fall (`PUT`)**:
  *API Longcode*: `"Win payout if Volatility Index after D ticks is strictly lower than entry spot."`
  *Mathematical Condition*:
  $$\text{Outcome}_{\text{PUT}} = \begin{cases} 1 & \text{if } S_{\text{expiry}} < S_{\text{entry}} \\ 0 & \text{if } S_{\text{expiry}} \ge S_{\text{entry}} \end{cases}$$

### 2.2 Equality / Tie Handling

A critical finding from the API verification:
$$\text{If } S_{\text{expiry}} == S_{\text{entry}} \implies \text{Outcome} = 0 \text{ (LOSS for both CALL and PUT)}$$

Standard Deriv Rise/Fall contracts require **strict inequality**. They do not refund the stake or pay out on ties.
(Note: Deriv maintains separate contract types named `CALLE` and `PUTE` for Equal Rise / Equal Fall which win on tie; however, standard `CALL` / `PUT` contracts strictly lose on tie).

---

## 3. Entry Mapping Verification (Resolving Audit Issue 4.2)

### 3.1 Proxy Definitions

1. **`MAPPING_V0_SIGNAL_TICK_ENTRY` (Legacy Research Proxy)**:
   - Assumes immediate fill at the signal decision tick $P_{\text{sig}} = S_0$.
   - Outcome is evaluated at forward tick $D$ relative to signal: $S_{\text{expiry}} = P_{t+D}$.
2. **`MAPPING_V1_NEXT_TICK_ENTRY` (Canonical Broker Settlement Proxy)**:
   - Broker fills order at the next incoming tick after transmission: $S_{\text{entry}} = P_{t+1}$.
   - Expiry spot occurs $D$ ticks after entry: $S_{\text{expiry}} = P_{t+1+D}$.

### 3.2 Empirical Discrepancy Rates Across 6 Markets

Evaluating 5,000 sequential tick intervals per market on genuine raw broker data confirms that **individual contract outcomes disagree substantially**:

| Market Symbol | 2 Ticks Disagreement | 3 Ticks Disagreement | 5 Ticks Disagreement | 10 Ticks Disagreement |
| :--- | :--- | :--- | :--- | :--- |
| **`R_100`** | 32.95% (1,646 / 4,995) | 26.73% (1,335 / 4,994) | 21.27% (1,062 / 4,992) | 13.27% (662 / 4,987) |
| **`1HZ100V`** | 33.05% (1,651 / 4,995) | 26.31% (1,314 / 4,994) | 20.59% (1,028 / 4,992) | 14.14% (705 / 4,987) |
| **`R_75`** | 32.45% (1,621 / 4,995) | 26.09% (1,303 / 4,994) | 19.69% (983 / 4,992) | 13.94% (695 / 4,987) |
| **`1HZ75V`** | 34.27% (1,712 / 4,995) | 27.27% (1,362 / 4,994) | 21.39% (1,068 / 4,992) | 14.22% (709 / 4,987) |
| **`R_50`** | 33.55% (1,676 / 4,995) | 26.61% (1,329 / 4,994) | 19.37% (967 / 4,992) | 13.66% (681 / 4,987) |
| **`1HZ50V`** | 33.83% (1,690 / 4,995) | 27.55% (1,376 / 4,994) | 21.75% (1,086 / 4,992) | 15.18% (757 / 4,987) |

### 3.3 Root Cause of the Previous V1.7.4.5 Conclusion

The previous V1.7.4.5 report observed identical aggregate win counts (e.g. 219 wins out of 887) and incorrectly inferred that V0 and V1 produced zero outcome differences.
In reality:
- On a discrete random walk, the number of contracts that transition from WIN to LOSS under a 1-tick phase shift approximately balances the number transitioning from LOSS to WIN.
- However, **at the individual prediction level, approximately 33% of 2-tick contracts and 20% of 5-tick contracts produce opposite outcomes**.
- Therefore, V1 (`MAPPING_V1_NEXT_TICK_ENTRY`) is strictly maintained as the canonical broker proxy for all quantitative evaluations in V1.8.0.

---

## 4. Exported Sample Discrepancy Records

Below are authentic sample records demonstrating how the two entry mappings diverge on real price sequences:

### Sample 1: Volatility 100 Index (`R_100`) — 2-Tick CALL
- **Signal Tick Price**: `1431.8983`
- **Forward Ticks**: `[1431.4889, 1431.7454, 1433.0212, 1433.5968]`
- **V0 Mapping**: Entry = `1431.8983`, Expiry = `1431.7454` (Delta = -0.1529) $\implies$ **Outcome = LOSS (0)**
- **V1 Mapping**: Entry = `1431.4889`, Expiry = `1433.0212` (Delta = +1.5323) $\implies$ **Outcome = WIN (1)**
- **Audit Result**: `outcomes_disagree = True`.

### Sample 2: Volatility 100 Index (`R_100`) — 2-Tick PUT
- **Signal Tick Price**: `1431.8983`
- **Forward Ticks**: `[1431.4889, 1431.7454, 1433.0212, 1433.5968]`
- **V0 Mapping**: Entry = `1431.8983`, Expiry = `1431.7454` (Delta = -0.1529) $\implies$ **Outcome = WIN (1)**
- **V1 Mapping**: Entry = `1431.4889`, Expiry = `1433.0212` (Delta = +1.5323) $\implies$ **Outcome = LOSS (0)**
- **Audit Result**: `outcomes_disagree = True`.

### Sample 3: Volatility 75 Index (`R_75`) — 2-Tick CALL
- **Signal Tick Price**: `44075.1600`
- **Forward Ticks**: `[44080.7800, 44081.2700, 44071.8000, 44068.5000]`
- **V0 Mapping**: Entry = `44075.1600`, Expiry = `44081.2700` (Delta = +6.1100) $\implies$ **Outcome = WIN (1)**
- **V1 Mapping**: Entry = `44080.7800`, Expiry = `44071.8000` (Delta = -8.9800) $\implies$ **Outcome = LOSS (0)**
- **Audit Result**: `outcomes_disagree = True`.

---

## 5. Non-Purchasing Proxy Limitations & Latency Caveats

1. **SHADOW Execution Only**: Real broker order execution is permanently disabled (`LIVE_EXECUTION_DISABLED = True`).
2. **Network and Order-Routing Latency**: In real broker purchasing, order transmission latency (typically 50ms–250ms) could cause the fill to occur at tick $t+2$ or $t+3$ during periods of high tick arrival frequency (particularly on 1-second indices).
3. **No Execution Guarantee**: Proxy outcomes represent theoretical settlement under ideal 1-tick delay and must never be cited as realized broker account statements.

---

*Report certified by `contract_rise_fall.py` — Release V1.8.0 Quantitative Audit Suite*
