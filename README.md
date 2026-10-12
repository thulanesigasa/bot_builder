# Deriv Multi-Market Rise/Fall Quantitative Edge Discovery & Research Framework (V1.8.1)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-389%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract](https://img.shields.io/badge/Contracts-Rise%2FFall%20(CALL%2FPUT)-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multiple Testing](https://img.shields.io/badge/Hypothesis%20Control-Benjamini--Hochberg%20FDR%20(48%20Hypotheses)-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.1%20Economic%20Integrity%20Repair-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, probabilistic machine-learning inference, and statistical validation system engineered for Deriv synthetic volatility index markets.

Release V1.8.1 implements comprehensive economic integrity repairs across all six research markets:
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
                           V1.8.1 ECONOMIC INTEGRITY & VALIDATION PLATFORM
                                                  |
         +-------------------+--------------------+--------------------+--------------------+
         |                   |                    |                    |                    |
         v                   v                    v                    v                    v
  DATA PROVENANCE     RISE/FALL CONTRACTS   PROBABILISTIC MODELS  QUOTE ECONOMICS      STATISTICAL GATE
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
  |1,043,184 Ticks  | |CALL: Strictly Higher| |Causal Features:   |  |Per-Observation   | |Predicted EV > 0|
  |SHA-256 Verified | |PUT: Strictly Lower  | Returns, Momentum,  |  |Timestamp Matching| |Realized EV > 0 |
  |Zero Clock Gaps  | |Tie: Strict LOSS (0) | Realized Volatility |  |Fail-Closed Policy| |MBB 95% Bound >0|
  |Genuine Broker WS| |V1 Next-Tick Entry   | Chrono Purge/Embargo|  |Ref Mode Disallow | |N_eff Dependence|
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
```

---

## Key Scientific Repairs in V1.8.1

### 1. Mandatory Positive Predicted EV Gate
- **Defect Resolved**: In V1.8.0, three hypotheses (`HYP_R_100_10T_PUT`, `HYP_1HZ50V_10T_PUT`, `HYP_1HZ50V_5T_PUT`) were falsely admitted because retrospective holdout win rates exceeded $51.15\%$, even though the model itself forecast negative expected value ex-ante.
- **Repair**: Candidate qualification now strictly requires $\text{PredictedEV} > 0.0$ ($P_{\text{model}} > \text{BreakEven}$). All three V1.8.0 candidates are formally rejected with `REJECTED_NEGATIVE_PREDICTED_EV`.

### 2. Per-Observation Quote Economics Engine (`quote_economics_engine.py`)
- **Defect Resolved**: Fixed $\$2.00 / \$3.91$ quote assumptions masked real broker execution friction and timing.
- **Repair**: Every observation is matched to authentic proposal responses under strict multidimensional requirements (market, direction, duration, currency, basis, and chronological receipt $t_{\text{resp}} \le t_{\text{dec}}$ within $5\text{s}$). Reference prices are classified as `REFERENCE_ECONOMICS_ONLY` and prohibited from satisfying candidate qualification.

### 3. Data Provenance & Cryptographic Audit (`data_provenance.py`)
- **Audit**: All 1,043,184 raw historical ticks across all six markets are verified against persisted Deriv WebSocket v3 APIs (`ws.derivws.com`).
- **Directional Bias Investigation**: Analysis proved that apparent downward drift was a short-window 5,000-tick sample fluctuation. Across the full 200,000 ticks, price dynamics follow symmetric random walks (`R_100` 50.07% CALL / 49.93% PUT; `1HZ50V` 49.91% CALL / 50.07% PUT).

### 4. Overlapping Outcome Serial Dependence
- **Defect Resolved**: Evaluating 10-tick contracts on every tick creates strong serial correlation, inflating naive binomial z-scores by $\approx \sqrt{10} \approx 3.16\times$.
- **Repair**: Implemented effective sample size $N_{\text{eff}} = \max(1, \lfloor N / D \rfloor)$ and Moving-Block Bootstrap resampling. Corrected p-values under Benjamini-Hochberg FDR control collapse all hypotheses to random walk noise ($p_{\text{FDR}} = 1.0000$).

### 5. Final Authoritative Verdict
$$\mathbf{NO\_VALIDATED\_POSITIVE\_EV\_EDGE}$$

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── data_provenance.py                               # Cryptographic data provenance & stream audit engine (V1.8.1)
├── quote_economics_engine.py                        # Per-observation quote matching & economic engine (V1.8.1)
├── rise_fall_research.py                            # Candidate qualification gate & 48-hypothesis engine (V1.8.1)
├── market_discovery.py                              # Dynamic market discovery, 6 symbols, capability matrix
├── contract_rise_fall.py                            # Canonical Rise/Fall contract specification & outcome resolver
├── model_rise_fall.py                               # Probabilistic modeling, causal features, Brier calibration
├── contract_specification.py                        # Canonical contract specs with mapping versions
├── dual_duration_research.py                        # Paired dual-duration research engine & empty Cohort D
├── session_reconciler.py                            # Automated session reconciler with separated cohort accounting
├── forward_session.py                               # Prospective session lifecycle & SQLite registry
├── probability.py                                   # Statistical distributions, Wilson score intervals
├── data/                                            # Raw tick streams, SQLite databases, and evidence exports
│   ├── R_100_ticks.csv                              # Volatility 100 Index raw ticks (200,000 ticks, SHA-256 verified)
│   ├── 1HZ100V_ticks.csv                            # Volatility 100 (1s) Index raw ticks (200,000 ticks, SHA-256 verified)
│   ├── R_75_master.csv                              # Volatility 75 Index raw ticks (43,184 ticks, SHA-256 verified)
│   ├── 1HZ75V_ticks.csv                             # Volatility 75 (1s) Index raw ticks (200,000 ticks, SHA-256 verified)
│   ├── R_50_ticks.csv                               # Volatility 50 Index raw ticks (200,000 ticks, SHA-256 verified)
│   ├── 1HZ50V_ticks.csv                             # Volatility 50 (1s) Index raw ticks (200,000 ticks, SHA-256 verified)
│   ├── forward_predictions.db                       # Journaled prospective predictions
│   ├── quotes.db                                    # Genuine Deriv proposal quotes
│   ├── sessions.db                                  # Forward session registry
│   ├── v181_data_provenance_manifest.json           # V1.8.1 cryptographic data manifest
│   ├── v181_multi_market_evidence.json              # V1.8.1 canonical machine-readable evidence package
│   ├── v180_multi_market_evidence.json              # Historical V1.8.0 baseline evidence
│   └── v180_model_comparison.json                   # Cross-market model calibration benchmarks
├── tests/                                           # Automated regression test suite (389 tests, 100% passing)
│   ├── test_v181_economic_integrity_repair.py       # V1.8.1 economic integrity, gate & SQLite tests (17 tests)
│   ├── test_v180_multi_market_rise_fall.py          # V1.8.0 multi-market Rise/Fall comprehensive tests (23 tests)
│   ├── test_v1745_evidence_authority_and_contract_mapping.py
│   └── ... (31 total test modules)
└── reports/                                         # Generated session and audit reports
    ├── V1_8_1_ROOT_CAUSE_AND_GATE_REPAIR.md         # Root cause analysis of negative predicted EV defect
    ├── V1_8_1_DATA_PROVENANCE_AUDIT.md              # Cryptographic hash audit & stream integrity
    ├── V1_8_1_QUOTE_LEVEL_ECONOMICS.md              # Per-observation quote matching and fail-closed rules
    ├── V1_8_1_CORRECTED_48_HYPOTHESES.md            # Programmatically rendered 48-hypothesis table
    ├── V1_8_1_STATISTICAL_DEPENDENCE_AUDIT.md       # Serial dependence, N_eff, and FDR adjustment
    ├── V1_8_1_CANDIDATE_REASSESSMENT.md             # Reassessment of previous 3 candidates (all rejected)
    ├── V1_8_1_FORWARD_SESSION_REPORT.md             # Forward observation status & sample power analysis
    └── V1_8_1_RELEASE_VALIDATION_REPORT.md          # Complete V1.8.1 sign-off report
```

---

## Permanent Safety Standards

The platform enforces absolute, compile-time non-purchasing safety:
- `LIVE_EXECUTION_DISABLED = True` across all discovery, contract, modeling, research, and quote modules.
- Every operational decision returns `NO_TRADE`.
- No real-money trades, demo account orders, or broker buy requests can ever be instantiated.
