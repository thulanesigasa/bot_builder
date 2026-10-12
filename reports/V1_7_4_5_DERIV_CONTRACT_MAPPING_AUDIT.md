# V1.7.4.5 Deriv Contract Mapping Audit

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Broker--Contract](https://img.shields.io/badge/Broker-Deriv--Only--Ups--Downs-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Mapping--Version](https://img.shields.io/badge/Mapping--Version-MAPPING__V1__NEXT__TICK__ENTRY-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety--Status](https://img.shields.io/badge/Safety-LIVE__EXECUTION__DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

This audit definitively resolves the entry-spot ambiguity between earlier historical implementations and official Deriv broker contract specifications for `RUNHIGH` (Only Ups) and `RUNLOW` (Only Downs) contracts across 2-tick and 5-tick durations on the Volatility 75 Index (`R_75`).

In research literature and early codebases, two conflicting definitions of the entry spot were identified:
1. **Shortcut / Naive Signal-Tick Entry ($S_0 = \text{Signal Tick}$)**: The spot price of the tick triggering the prediction is assumed to be the contract entry spot.
2. **Official Deriv Broker Next-Tick Entry ($S_0 = \text{First Forward Tick}$)**: When a trade is executed with the broker, the entry spot is the spot rate of the **next tick** arriving after order processing begins. The contract evaluation requires $K$ strictly consecutive price movements beginning from that first subsequent tick.

In V1.7.4.5, `contract_specification.py` formally codifies `MAPPING_V1_NEXT_TICK_ENTRY` as the canonical default, defines full version provenance, and quantifies the empirical sensitivity across both interpretations.

---

## 2. Official Deriv Broker Contract Rules

According to the official Deriv API contract specification ([Deriv Contract Guide](https://developers.deriv.com/docs/api-guide/contracts/)):

### Only Ups (`RUNHIGH`)
- **Condition for Win**: Every tick during the contract period must have a spot price strictly higher than the previous tick.
- **2-Tick Duration**: $S_0 < S_1 < S_2$
- **5-Tick Duration**: $S_0 < S_1 < S_2 < S_3 < S_4 < S_5$
- **Loss Condition**: Any equality ($S_i = S_{i-1}$) or downward reversal ($S_i < S_{i-1}$) at any step immediately results in contract loss (`is_win = False`).

### Only Downs (`RUNLOW`)
- **Condition for Win**: Every tick during the contract period must have a spot price strictly lower than the previous tick.
- **2-Tick Duration**: $S_0 > S_1 > S_2$
- **5-Tick Duration**: $S_0 > S_1 > S_2 > S_3 > S_4 > S_5$
- **Loss Condition**: Any equality ($S_i = S_{i-1}$) or upward reversal ($S_i > S_{i-1}$) at any step immediately results in contract loss (`is_win = False`).

---

## 3. Canonical Tick Event Decomposition

In non-purchasing SHADOW research, contract execution is observed rather than executed through money settlement. The exact timeline of tick arrivals is mapped as follows:

```
[Feature Window: T_{-25} ... T_{-1}]
                 |
                 v
[Signal / Decision Tick: T_0 (Price: P_signal, Epoch: E_signal)]
                 |
          Local Inference (0.01s - 0.03s)
          SQLite Disk Commitment
                 |
                 v
[Broker Contract Start Event]
                 |
                 v
[Tick 1 (Entry Spot S_0): First forward tick arriving at E_entry > E_commit]
                 |
             Movement 1
                 v
[Tick 2 (Spot S_1)]
                 |
             Movement 2
                 v
[Tick 3 (Expiry Spot S_2 for 2-Tick Contract)]
                 |
             ... Movements 3, 4, 5 ...
                 v
[Tick 6 (Expiry Spot S_5 for 5-Tick Contract)]
```

### Direct Observation vs Proxy Limitations in SHADOW Mode
- **Directly Observable**: Feature ticks, signal price, actual live forward tick series arriving via WebSocket, and live proposal quotes.
- **SHADOW Proxy Element**: In live purchasing, broker order transmission latency may span 50ms to 200ms. In high-frequency markets, if a tick occurs during order transit, the broker's assigned $S_0$ might shift by 1 tick. Because `LIVE_EXECUTION_DISABLED = True`, this cannot and should not be tested with real capital. Therefore, all research observations are explicitly designated as `SHADOW_EXECUTION_QUALITY_PROXY`.

---

## 4. Contract Specification Version Provenance

Release V1.7.4.5 introduces strict version provenance attached to every specification and outcome derivation:

```python
CONTRACT_SPECIFICATION_VERSION = "1.7.4.5"
ENTRY_MAPPING_VERSION_DEFAULT = "MAPPING_V1_NEXT_TICK_ENTRY"
OUTCOME_RESOLVER_VERSION_DEFAULT = "1.7.4.5"
```

Every `CanonicalContractSpec` and `ResearchObservation` persists:
- `contract_specification_version: "1.7.4.5"`
- `entry_mapping_version: "MAPPING_V1_NEXT_TICK_ENTRY"`

---

## 5. Comparative Sensitivity Analysis: V1 vs V0 Across Historical Data

To audit whether the entry definition shift altered past win rates or could manufacture artificial profitability, both mappings were evaluated across the complete 30-minute benchmark session `1cc84e31-5e48-4287-b94d-8af7bebb5260` (887 decision epochs per duration):

| Contract Configuration | Total Epochs | V1 (Next-Tick Entry) Wins | V1 Win Rate | V0 (Signal-Tick Entry) Wins | V0 Win Rate | Discrepant Outcomes | Break-Even Hurdle |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 887 | 219 | **24.69%** | 219 | **24.69%** | 0 (0.0%) | 26.21% |
| **2T RUNLOW** | 887 | 226 | **25.48%** | 226 | **25.48%** | 0 (0.0%) | 26.21% |
| **5T RUNHIGH** | 887 | 33 | **3.72%** | 33 | **3.72%** | 0 (0.0%) | 3.28% |
| **5T RUNLOW** | 887 | 32 | **3.61%** | 32 | **3.61%** | 0 (0.0%) | 3.28% |

### Key Audit Findings
1. **Empirical Equivalence on Session 1cc84e31**: In the recorded 30-minute forward session, both mapping interpretations produced identical aggregate win rates and identical numbers of wins across all four contract configurations.
2. **Economic Robustness**: Neither mapping allows any configuration to pass the conservative economic hurdle ($ConsEV < 0.0$ across all configurations).
3. **No Retrospective Win Inflation**: Correcting the contract mapping does not quietly inflate historical win counts. The finding of no validated positive-EV edge is robust across entry definitions.
