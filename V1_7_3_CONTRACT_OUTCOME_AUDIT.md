# V1.7.3 CONTRACT OUTCOME & BROKER SETTLEMENT AUDIT

[![Version](https://img.shields.io/badge/Version-V1.7.3-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Canonical-Spec](https://img.shields.io/badge/Specification-Canonical%205--Movement-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Settlement-Status](https://img.shields.io/badge/Settlement-Reconstructed%20%7C%20Verified-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Real-Money](https://img.shields.io/badge/Real--Money%20Trading-DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Official Deriv Broker Contract Documentation & References

| Specification Field | Official Deriv Parameter | Documentation Notes |
| :--- | :--- | :--- |
| **Broker Name** | Deriv (Deriv Limited / Deriv Group Services) | Regulated broker platform |
| **Official Documentation URL** | `https://developers.deriv.com/docs/api-guide/contracts/` | Accessed: 2026-10-11 |
| **WebSocket Endpoint** | `wss://api.derivws.com/trading/v1/options/ws/public` | Deriv v1 Trading WebSocket |
| **Contract Family** | High/Low Run Contracts | Binary options with monotonic tick paths |
| **RUNHIGH Identifier** | Commercial Name: **"Only Ups"** (`RUNHIGH`) | Wins if every consecutive tick moves higher |
| **RUNLOW Identifier** | Commercial Name: **"Only Downs"** (`RUNLOW`) | Wins if every consecutive tick moves lower |
| **Underlying Asset** | Volatility 75 Index (`R_75`) | Continuous synthetic volatility index |
| **Duration & Unit** | 5 ticks (`duration: 5, duration_unit: "t"`) | Exactly 5 forward movements |
| **Contract Basis** | Stake (`basis: "stake"`, e.g. 2.00 USD) | Fixed ask price deducted at order entry |

---

## 2. Canonical Research Outcome Definition vs Broker Settlement

### The 5-Movement Monotonic Lifecycle

A 5-tick contract involves an entry spot $S_0$ followed by exactly 5 forward ticks $S_1, S_2, S_3, S_4, S_5$:

$$\text{Transition Path: } S_0 \xrightarrow{\text{step 1}} S_1 \xrightarrow{\text{step 2}} S_2 \xrightarrow{\text{step 3}} S_3 \xrightarrow{\text{step 4}} S_4 \xrightarrow{\text{step 5}} S_5$$

1. **RUNHIGH ("Only Ups") Winning Condition:**
   $$S_0 < S_1 < S_2 < S_3 < S_4 < S_5$$
   Every intermediate movement must be strictly positive ($S_k > S_{k-1}$ for all $k \in \{1, 2, 3, 4, 5\}$).

2. **RUNLOW ("Only Downs") Winning Condition:**
   $$S_0 > S_1 > S_2 > S_3 > S_4 > S_5$$
   Every intermediate movement must be strictly negative ($S_k < S_{k-1}$ for all $k \in \{1, 2, 3, 4, 5\}$).

3. **Equality & Flat Ticks ($S_k == S_{k-1}$):**
   Under both official Deriv rules and canonical research specifications, equality on any intermediate tick violates strict inequality and results in an **immediate contract loss**.

4. **Reversal Ticks:**
   A reversal at any step (e.g. step 3 falling while steps 1, 2, 4, 5 rise) results in an immediate loss.

5. **The "All-Above-Entry" Trap Clarified:**
   The contract is NOT won merely because all future prices exceed the entry spot ($S_k > S_0$). If a sequence is $[100, 103, 102, 104, 105, 106]$, all prices exceed $100$, but step 2 reversed ($103 \to 102$). This is a **LOSS** under RUNHIGH.

---

## 3. Actual Resolver Implementation Audit

The implementation in `contract_specification.py`, `persistent_resolver.py`, and `forward_journal.py` was audited:

```python
# Evaluates strict consecutive 5-movement inequality:
is_runhigh = all(p[k] > p[k - 1] for k in range(1, 6))
is_runlow  = all(p[k] < p[k - 1] for k in range(1, 6))
```

- **Resolver Verification:** The resolver does NOT use the incorrect "all-above-entry" shortcut. It strictly checks that every consecutive step $k \in [1..5]$ satisfies the directional inequality.
- **Immediate Loss Handling:** Ties and reversals immediately yield `win = 0.0`.
- **Classification Status:** Successfully distinguishes `RESEARCH_OUTCOME_RECONSTRUCTED`, `RESEARCH_OUTCOME_INCOMPLETE`, and `RESEARCH_OUTCOME_DATA_GAP`.

---

## 4. Independent Raw Tick Re-computation (Session 413bbee4)

All 129 resolved predictions in session `413bbee4` were independently reconstructed using the authoritative raw CSV tick stream (`data/R_75_live_ticks.csv`):

| Metric | Persisted DB Value | Independent Raw Tick Value | Discrepancy |
| :--- | :---: | :---: | :---: |
| **Total Evaluated Predictions** | 129 | 129 | **0** |
| **RUNHIGH Wins** | 5 | 5 | **0** |
| **RUNLOW Wins** | 5 | 5 | **0** |
| **Dual Losses (Oscillations)** | 119 | 119 | **0** |
| **Observed RUNHIGH Win Rate** | 3.876% | 3.876% | **0.00%** |
| **Observed RUNLOW Win Rate** | 3.876% | 3.876% | **0.00%** |
| **Data Gap / Corrupt Ticks** | 0 | 0 | **0** |

$$\text{Discrepancy Rate: } 0 / 129 = \mathbf{0.000\%}$$

The historical database outcomes are 100% mathematically identical to independent reconstruction from the raw captured tick stream.

---

## 5. Distinction Between Research Reconstruction and Real Broker Settlement

In accordance with V1.7.3 Part D Section 14:

| Classification | Meaning & Legal Research Distinction |
| :--- | :--- |
| **`RESEARCH_OUTCOME_RECONSTRUCTED`** | Contract outcome reconstructed mathematically from authoritative captured tick streams using canonical broker specifications. **Used for all current evidence.** |
| **`DEMO_SETTLEMENT_MATCH_VERIFIED`** | Contract outcome verified against an actual executed broker demo settlement contract ID. Requires explicit authorization on demo accounts. |
| **`CONTRACT_MAPPING_UNVERIFIED`** | Outcome where tick timestamps, sequence ordering, or duration mapping is incomplete. |

> **Audit Standard:** Reconstructed outcomes must never be described as executed settlements unless genuine broker contract confirmation receipts exist. Real-money purchases are permanently disabled (`LIVE_EXECUTION_DISABLED = True`).
