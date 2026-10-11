# V1.7.4 VIBE-TRADING RESEARCH METHODOLOGY INTEGRATION ASSESSMENT

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Reference-Research](https://img.shields.io/badge/Reference-HKUDS%2FVibe--Trading-blueviolet.svg)](https://github.com/HKUDS/Vibe-Trading)
[![Integration-Status](https://img.shields.io/badge/Integration-Advisory%20Only-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Assessment Mandate

In accordance with Master Development Prompt V1.7.4 Part F Section 16, this report presents a quantitative evaluation of the reference research repository **HKUDS/Vibe-Trading** ([https://github.com/HKUDS/Vibe-Trading.git](https://github.com/HKUDS/Vibe-Trading.git)).

The objective is to identify robust quantitative research methodologies and architectural design patterns suitable for Deriv high-frequency synthetic tick options (`RUNHIGH` / `RUNLOW`), while explicitly rejecting unvetted dependencies and stock-market execution mechanics that would violate project safety invariants.

---

## 2. Reusable Methodological Patterns Identified in Vibe-Trading

Vibe-Trading demonstrates several advanced financial machine-learning research practices that were selectively adapted into V1.7.4:

### 1. Evidence-Grounded Research Run Cards
- **Pattern**: Every strategy backtest produces an immutable, cryptographically verifiable artifact containing exact git commits, dataset checksums, hyperparameters, and confusion matrices.
- **V1.7.4 Adaptation**: Formalized in `models/*.json` and `strategy_discovery.py`, ensuring complete provenance across dataset hashes (`8273d215bf...`), feature schemas, and outcome resolvers.

### 2. Overlapping-Label Purging & Embargoing
- **Pattern**: When consecutive forward contract outcomes share common future prices (e.g. tick $i$ and tick $i+1$ share ticks $i+2..i+6$), standard statistical tests suffer from severe artificial serial correlation. Vibe-Trading enforces label purging across overlapping evaluation windows.
- **V1.7.4 Adaptation**: Implemented in `StrategyDiscoveryEngine.evaluate_all(purge_overlap=True)`, where evaluation points are sampled in non-overlapping steps of $(d + 1)$ ticks.

### 3. Controlled Hypothesis Generation vs. Unrestricted Data Mining
- **Pattern**: Rather than blindly running genetic algorithms or unconstrained searches across thousands of arbitrary indicators (which leads to severe overfitting and p-hacking), Vibe-Trading organizes discovery into structured hypothesis families.
- **V1.7.4 Adaptation**: Formalized in `PredeclaredHypothesis` in `strategy_discovery.py`, requiring predeclared rationale, feature requirements, and statistical hurdles before testing.

### 4. Multiple-Testing Family-Wise Error Rate (FWER) Controls
- **Pattern**: Correcting test statistics for the cardinality of tested strategy variations.
- **V1.7.4 Adaptation**: Enforces Bonferroni multiple-testing adjustments ($p_{\text{adj}} = \min(1.0, p \times M)$) and Benjamini-Hochberg False Discovery Rate (FDR) control across all evaluated hypotheses.

---

## 3. Capabilities and Patterns Explicitly Avoided

| Vibe-Trading Feature | Architectural Rationale for Exclusion in bot_builder |
| :--- | :--- |
| **General-Purpose Stock Broker Execution** | Deriv `RUNHIGH` and `RUNLOW` contracts are fixed-odds binary synthetic contracts with microsecond settlement rules. Stock order routing (limit, market, stop-loss on equity exchanges) is completely inapplicable. |
| **Heavy Unapproved Dependencies** | Vibe-Trading relies on extensive external LLM and scientific dependencies. To maintain stability, zero unapproved dependencies were introduced; all tests, binomial distributions, and bootstrap samplers are implemented in pure Python standard library and existing NumPy/Pandas. |
| **Automated Order Authorization by AI** | Vibe-Trading allows agents to propose and route orders. In `bot_builder`, this is strictly prohibited. AI discovery is locked behind an authoritative advisory firewall. |

---

## 4. The Advisory-Only Research Firewall Architecture

To prevent AI-discovered hypotheses from inadvertently triggering live orders or bypassing confirmation gates, V1.7.4 establishes an impermeable architectural firewall:

```
+-------------------------------------------------------------------------+
|                  AI RESEARCH LAYER (ADVISORY-ONLY)                     |
|                                                                         |
|   strategy_discovery.py:                                               |
|   - Predeclared Hypothesis Families (Streak, Volatility, Reversal)      |
|   - Overlapping-Label Purging (step = duration + 1)                    |
|   - Bonferroni & FDR Multiple-Testing Adjustments                      |
|                                                                         |
|   INVARIANTS:                                                           |
|   IS_ADVISORY_ONLY = True                                              |
|   EXECUTION_AUTHORIZATION_DISABLED = True                               |
+-------------------------------------------------------------------------+
                                    ||
                                    || (Hypothesis Audit Report Only)
                                    \/
+-------------------------------------------------------------------------+
|             CONFIRMATION GATE & NO_TRADE SAFETY INVARIANT               |
|                                                                         |
|   decision_gate.py:                                                     |
|   - Gate 1: SHADOW / DATA_COLLECTION Mode Non-Trading Guard             |
|   - Gate 3: Contract & Duration Verification (2T and 5T)               |
|   - Gate 4: Frozen Model Approval Status (Approved only if confirmed)  |
|   - Gate 6: Quote Timestamps (resp_ts <= decision_ts)                   |
|   - Gate 7 & 9: Positive EV & Break-Even Margin                        |
|                                                                         |
|   PERMANENT SAFETY INVARIANT:                                           |
|   LIVE_EXECUTION_DISABLED = True                                       |
+-------------------------------------------------------------------------+
```

### Institutional Rules Enforced
1. An AI discovery cannot authorize trading.
2. Even if a hypothesis displays a nominal positive win rate, it is labeled `INCONCLUSIVE` unless it clears the Bonferroni significance threshold above the broker's break-even hurdle ($26.212\%$ for 2T).
3. Any provisionally supported hypothesis remains strictly in `EXPLORATORY_FORWARD` and cannot be reclassified into confirmation without a pre-registered, untouched forward session.
