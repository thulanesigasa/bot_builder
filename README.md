# Deriv Multi-Market Rise/Fall Quantitative Edge Discovery & Research Framework (V1.8.0)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-372%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract](https://img.shields.io/badge/Contracts-Rise%2FFall%20(CALL%2FPUT)-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multiple Testing](https://img.shields.io/badge/Hypothesis%20Control-Benjamini--Hochberg%20FDR%20(48%20Hypotheses)-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-EXPLORATORY__CANDIDATE__IDENTIFIED-yellow.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.0%20Multi--Market%20Rise%2FFall-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, probabilistic machine-learning inference, and market-data forward observation system engineered for Deriv synthetic volatility index markets.

Release V1.8.0 evolves `bot_builder` from single-market Only Ups/Only Downs modeling into a multi-market Rise/Fall (`CALL` / `PUT`) edge-discovery platform spanning six synthetic volatility markets:
1. `R_100` — Volatility 100 Index (Standard 2s ticks)
2. `1HZ100V` — Volatility 100 (1s) Index (1s ticks)
3. `R_75` — Volatility 75 Index (Standard 2s ticks)
4. `1HZ75V` — Volatility 75 (1s) Index (1s ticks)
5. `R_50` — Volatility 50 Index (Standard 2s ticks)
6. `1HZ50V` — Volatility 50 (1s) Index (1s ticks)

Operating mode: **SHADOW**, strictly non-purchasing. Real-money live trade execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`), and all generated decisions remain `NO_TRADE`.

---

## Architecture & System Overview

```text
                           V1.8.0 MULTI-MARKET QUANTITATIVE RESEARCH PLATFORM
                                                  |
         +-------------------+--------------------+--------------------+--------------------+
         |                   |                    |                    |                    |
         v                   v                    v                    v                    v
  MARKET DISCOVERY    RISE/FALL CONTRACTS   PROBABILISTIC MODELS  QUOTE ECONOMICS      MULTIPLE TESTING
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
  |6 Target Markets | |CALL: Strictly Higher| |Causal Features:   |  |Ask: $2.00        | |48 Hypotheses     |
  |Pip Precision 2/4| |PUT: Strictly Lower  | Returns, Momentum,  |  |Payout: $3.91     | Benjamini-Hochberg |
  |Durations 1-10t  | |Tie: Strict LOSS (0) | Realized Volatility |  |Hurdle: 51.15%    | FDR Control        |
  |20t: Unsupported | |V1 Next-Tick Entry   | Chrono Purge/Embargo|  |Cohort A/B/C/D    | MBB 95% Bound      |
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
```

---

## Key Research Findings in V1.8.0

### 1. Market Capability Matrix
- **Tick Durations 1 to 10**: Fully supported with live proposal quotes across all six markets.
- **Duration 20 Ticks**: Deriv contract rules limit tick contracts to a maximum of 10 ticks (`Number of ticks must be between 1 and 10`). Rejection is classified as `UNSUPPORTED_CONTRACT_COMBINATION` and not a strategy failure.

### 2. Rise/Fall Broker Semantics & Equality
- **Strict Inequality Verified**: Deriv longcode confirms `CALL` requires strictly higher than entry spot and `PUT` requires strictly lower. Equal prices ($S_{\text{expiry}} == S_{\text{entry}}$) result in a **broker loss (0) for both contracts**.
- **Entry Mapping Audit (Issue 4.2)**: Independent verification across 5,000 raw ticks per market shows that **32.5% to 34.3% of 2-tick contracts and 19.4% to 21.8% of 5-tick contracts reverse outcomes** between V0 signal-tick and V1 next-tick entry. V1 is maintained as canonical broker proxy.

### 3. Probabilistic Calibration
- **Brier Scores Near 0.250**: Across all markets, Brier scores range between 0.2497 and 0.2501, showing that raw tick movements approximate a Martingale difference sequence.
- **Brier Skill Scores**: Regularized logistic models achieve Brier Skill Scores near zero ($[-0.002, +0.00005]$), confirming that short-term returns and momentum provide minimal unconditional predictive edge.

### 4. Hypothesis Testing & Multiple-Testing Control
- **48 Predefined Hypotheses**: 6 markets $\times$ 4 durations (2, 3, 5, 10 ticks) $\times$ 2 directions (`CALL`, `PUT`).
- **Benjamini-Hochberg FDR ($\alpha = 0.05$)**: Controls family-wise false discoveries.
- **Verdict Summary**: 28 Hypotheses Rejected (Negative EV), 17 Inconclusive (Insufficient bootstrap lower bound), 3 Exploratory Candidates Identified (`HYP_R_100_10T_PUT`, `HYP_1HZ50V_10T_PUT`, `HYP_1HZ50V_5T_PUT`).
- **Research Status**: `EXPLORATORY_CANDIDATE_IDENTIFIED` / `CONFIRMATION_READY`. Candidates require untouched prospective confirmation before validation.

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── market_discovery.py                              # Dynamic market discovery, 6 symbols, capability matrix (V1.8.0)
├── contract_rise_fall.py                            # Canonical Rise/Fall contract specification & outcome resolver (V1.8.0)
├── model_rise_fall.py                               # Probabilistic modeling, causal features, Brier calibration (V1.8.0)
├── rise_fall_research.py                            # 48-hypothesis edge discovery, MBB bootstrap, BH-FDR engine (V1.8.0)
├── contract_specification.py                        # Canonical contract specs with mapping versions (V1.7.4.5)
├── dual_duration_research.py                        # Paired dual-duration research engine & empty Cohort D (V1.8.0)
├── session_reconciler.py                            # Automated session reconciler with separated cohort accounting (V1.8.0)
├── forward_session.py                               # Prospective session lifecycle & SQLite registry
├── probability.py                                   # Statistical distributions, Wilson score intervals
├── data/                                            # Raw tick streams, SQLite databases, and evidence exports
│   ├── R_100_ticks.csv                              # Volatility 100 Index raw ticks (200,000 ticks)
│   ├── 1HZ100V_ticks.csv                            # Volatility 100 (1s) Index raw ticks (200,000 ticks)
│   ├── R_75_master.csv                              # Volatility 75 Index raw ticks (43,184 ticks)
│   ├── 1HZ75V_ticks.csv                             # Volatility 75 (1s) Index raw ticks (200,000 ticks)
│   ├── R_50_ticks.csv                               # Volatility 50 Index raw ticks (200,000 ticks)
│   ├── 1HZ50V_ticks.csv                             # Volatility 50 (1s) Index raw ticks (200,000 ticks)
│   ├── forward_predictions.db                       # Journaled prospective predictions
│   ├── quotes.db                                    # Genuine Deriv proposal quotes
│   ├── sessions.db                                  # Forward session registry
│   ├── v180_multi_market_evidence.json              # V1.8.0 machine-readable evidence export package
│   ├── v180_live_proposal_capabilities.json         # Live WebSocket proposal capability matrix
│   ├── v180_entry_mapping_audit.json                # V0 vs V1 entry mapping discrepancy statistics
│   ├── v180_multi_market_data_audit.json            # 6-market stream continuity audit
│   └── v180_model_comparison.json                   # Cross-market model calibration benchmarks
├── tests/                                           # Automated regression test suite
│   ├── test_v180_multi_market_rise_fall.py          # V1.8.0 multi-market Rise/Fall comprehensive tests (23 tests)
│   ├── test_v1745_evidence_authority_and_contract_mapping.py
│   ├── test_v173_chronology_and_settlement.py
│   ├── test_v162_data_integrity.py
│   └── ...                                          # Total 372 automated passing tests
├── V1_8_0_MARKET_CAPABILITY_MATRIX.md               # 6-market capability matrix report
├── V1_8_0_RISE_FALL_CONTRACT_AUDIT.md               # Rise/Fall broker semantics & entry mapping audit
├── V1_8_0_MULTI_MARKET_DATA_AUDIT.md                # 1,043,184-tick data & clock integrity audit
├── V1_8_0_MODEL_COMPARISON.md                       # Out-of-sample model calibration & Brier comparison
├── V1_8_0_QUOTE_ECONOMICS.md                        # Real proposal quote economics & break-even hurdle
├── V1_8_0_EDGE_DISCOVERY_REPORT.md                  # 48-hypothesis multiple testing & candidate ranking
├── V1_8_0_FORWARD_VALIDATION_REPORT.md              # SHADOW session telemetry & empty Cohort D validation
├── V1_8_0_RELEASE_VALIDATION_REPORT.md              # Complete release validation & test pass certification
└── README.md                                        # System documentation & architectural reference
```

---

## Running the System

### 1. Execute Regression Tests
```bash
python -m pytest -q
```
*Expected Output: `372 passed in ~73s (100% green)`*

### 2. Generate Market Capability Matrix
```bash
python -c "from market_discovery import MarketDiscovery; print(MarketDiscovery().export_capability_matrix_markdown())"
```

### 3. Run Multi-Market Edge Discovery
```bash
python scratch/run_edge_discovery.py
```

---

## Safety & Research Integrity Invariants

1. **`LIVE_EXECUTION_DISABLED = True`**: Hardcoded compile-time constant across all research modules.
2. **`NO_TRADE`**: All generated decision signals remain strictly advisory and non-purchasing.
3. **No Automatic Confirmation Promotion**: Exploratory candidates remain frozen and unconfirmed until verified on prospective data recorded strictly after preregistration.
4. **Honest Reporting**: When no statistically credible edge survives conservative bootstrap bounds and FDR correction, the authoritative result is reported as `NO_VALIDATED_POSITIVE_EV_EDGE`.

---

*Release V1.8.0 Quantitative Research Platform — Certified 100% Green*
