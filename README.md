# Deriv Multi-Market Rise/Fall Quantitative Edge Discovery & Research Framework (V1.8.2)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-405%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v3%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract](https://img.shields.io/badge/Contracts-Rise%2FFall%20(CALL%2FPUT)-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multiple Testing](https://img.shields.io/badge/Hypothesis%20Control-Benjamini--Hochberg%20FDR%20(48%20Hypotheses)-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Authoritative Verdict](https://img.shields.io/badge/Authoritative%20Verdict-INSUFFICIENT__QUOTE__VERIFIED__EVIDENCE-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Baseline Verdict](https://img.shields.io/badge/Baseline%20Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.2%20Evidence%20Integration-0284C7)](https://github.com/thulanesigasa/bot_builder)

A rigorous quantitative financial research, probabilistic machine-learning inference, and statistical validation system engineered for Deriv synthetic volatility index markets.

Release V1.8.2 delivers end-to-end economic evidence integration, data provenance enforcement, dependence-aware statistical auditing, and a single reproducible canonical research pipeline across all six target research markets:
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
                           V1.8.2 CANONICAL REPRODUCIBLE RESEARCH PIPELINE
                                                  |
         +-------------------+--------------------+--------------------+--------------------+
         |                   |                    |                    |                    |
         v                   v                    v                    v                    v
  DATA PROVENANCE     QUOTE INTEGRATION     PROBABILISTIC MODELS  SERIAL DEPENDENCE    STATISTICAL GATE
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
  |Fail-Closed Audit| |QUOTE_VERIFIED Mode| |Causal Features:   |  |Empirical rho(k)  | |Predicted EV > 0|
  |SHA-256 Checksums| |Zero-Quote Fail    | Returns, Momentum,  |  |tau_int Autocorr  | |Realized EV > 0 |
  |Decoupled Status | |Ref Mode Disallowed| Realized Volatility |  |N_eff Inflation   | |MBB 95% Bound >0|
  |Lineage Verified | |24-Field Records   | Chrono Purge/Embargo|  |5-Method Audit    | |BH FDR Control  |
  +-----------------+ +-------------------+ +-------------------+  +------------------+ +------------------+
                                                  |
                                                  v
                              CANONICAL EVIDENCE & ARTIFACT EXPORTS
                              +---------------------------------------+
                              | data/v182_data_provenance_manifest.json|
                              | data/v182_multi_market_evidence.json   |
                              | 8 Comprehensive Markdown Reports      |
                              +---------------------------------------+
```

---

## Key Scientific Repairs in V1.8.2

### 1. Elimination of Reference Quote Masquerade
- **Defect Resolved**: Previous iterations permitted loose reference tuples `(2.0, 3.91)` to evaluate under `QUOTE_VERIFIED` mode, allowing unverified quotes to masquerade as authentic execution evidence.
- **Repair**: Passing a reference price tuple under `QUOTE_VERIFIED` mode now strictly raises an immediate `ValueError`. If proposal quotes are absent from broker evidence, the hypothesis fails closed to `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE`. Reference pricing is segregated to `REFERENCE_ECONOMICS_ONLY` mode and permanently disqualified from satisfying candidate qualification.
- **Audit Outcome**: With zero proposal quotes present in evidence for Rise/Fall contracts, all 48 hypotheses evaluate as `INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE`.

### 2. Fail-Closed Data Provenance Enforcement (`data_provenance.py`)
- **Defect Resolved**: Provenance auditing previously defaulted open on missing or unparseable metadata.
- **Repair**: Default classification is strictly `UNVERIFIED_SOURCE`. Missing or malformed companion metadata files fail closed to `UNVERIFIED_SOURCE` or `CORRUPTED_SOURCE`. Decoupled independent verification dimensions: `file_integrity_status` (`FILE_INTEGRITY_VERIFIED`), `source_authenticity_status` (`SOURCE_AUTHENTICITY_VERIFIED`), and `transformation_lineage_status` (`TRANSFORMATION_LINEAGE_VERIFIED`).

### 3. Empirical Serial Dependence Auditor (`SerialDependenceAuditor`)
- **Defect Resolved**: Heuristic sample size divisors ($N / D$) did not reflect sequence-specific autocorrelation structures.
- **Repair**: Implemented empirical autocorrelation $\rho(k)$, integrated autocorrelation time $\tau_{\text{int}} = 1 + 2 \sum_{k=1}^M \rho(k)$, and empirical effective sample size $N_{\text{eff, empirical}} = \max(1, \lfloor N / \tau_{\text{int}} \rfloor)$. Compared across 5 distinct dependence methods (Naive i.i.d., Duration heuristic, Empirical $\tau_{\text{int}}$, Moving Block Bootstrap, and Decimation).
- **Result**: Demonstrated that naive z-statistics (e.g. $z \approx -7.04$) collapse by over 60% (e.g. $z \approx -2.64$) once autocorrelation is properly accounted for.

### 4. Unified Canonical Pipeline (`canonical_pipeline.py`)
- **Integration**: A single, reproducible pipeline executes all stages deterministically from raw CSV tick ingestion to final report rendering.
- **Evidence Exports**:
  - `data/v182_data_provenance_manifest.json`: Full 6-market provenance audit manifest.
  - `data/v182_multi_market_evidence.json`: Complete canonical evidence package containing all 48 hypotheses under both quote-verified and reference modes.
  - Eight formal markdown reports rendered programmatically under `reports/`.

### 5. Final Authoritative Verdicts
- **Authoritative Economic Verdict (`QUOTE_VERIFIED`)**:
  $$\mathbf{INSUFFICIENT\_QUOTE\_VERIFIED\_EVIDENCE}$$
- **Baseline Benchmarking Verdict (`REFERENCE_ECONOMICS_ONLY`)**:
  $$\mathbf{NO\_VALIDATED\_POSITIVE\_EV\_EDGE}$$
- **Strategy Candidates Promoted to Trading**: $\mathbf{0}$

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── canonical_pipeline.py                            # Unified reproducible canonical research pipeline (V1.8.2)
├── data_provenance.py                               # Fail-closed data provenance & cryptographic auditor (V1.8.2)
├── quote_economics_engine.py                        # Per-observation quote matching & economic engine (V1.8.2)
├── rise_fall_research.py                            # Multi-market edge discovery & dependence auditor (V1.8.2)
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
│   ├── quotes.db                                    # Historical proposal quote database (Run-High/Run-Low only)
│   ├── v182_data_provenance_manifest.json           # V1.8.2 fail-closed provenance audit manifest
│   ├── v182_multi_market_evidence.json              # V1.8.2 canonical reproducible evidence package
│   ├── v181_multi_market_evidence.json              # Historical V1.8.1 evidence package
│   └── v180_multi_market_evidence.json              # Historical V1.8.0 baseline evidence
├── tests/                                           # Automated regression test suite (405 tests, 100% passing)
│   ├── test_v182_evidence_integration.py            # V1.8.2 evidence integration, provenance & dependence tests (16 tests)
│   ├── test_v181_economic_integrity_repair.py       # V1.8.1 economic integrity, gate & SQLite tests (17 tests)
│   ├── test_v180_multi_market_rise_fall.py          # V1.8.0 multi-market Rise/Fall comprehensive tests (23 tests)
│   └── ... (32 total test modules)
├── releases/                                        # Packaged release archives (.zip)
└── reports/                                         # Generated session and audit reports
    ├── V1_8_2_END_TO_END_PIPELINE_AUDIT.md          # End-to-end pipeline architecture and execution audit
    ├── V1_8_2_DATA_AUTHENTICITY_REASSESSMENT.md     # Data authenticity and fail-closed provenance report
    ├── V1_8_2_QUOTE_EVIDENCE_INTEGRATION.md         # Proposal quote integration and inventory audit
    ├── V1_8_2_CORRECTED_48_HYPOTHESES.md            # Corrected 48-hypothesis empirical results under both modes
    ├── V1_8_2_STATISTICAL_INFERENCE_AUDIT.md        # Serial dependence, tau_int, and test statistic deflation audit
    ├── V1_8_2_CANDIDATE_REASSESSMENT.md             # Reassessment and disqualification of historical candidates
    ├── V1_8_2_FORWARD_RESEARCH_READINESS.md         # Prospective SHADOW data collection readiness plan
    └── V1_8_2_RELEASE_VALIDATION_REPORT.md          # Comprehensive V1.8.2 sign-off and validation report
```

---

## Permanent Safety Standards

The platform enforces absolute, compile-time non-purchasing safety:
- `LIVE_EXECUTION_DISABLED = True` across all discovery, contract, modeling, research, pipeline, and quote modules.
- Every operational decision returns `NO_TRADE`.
- No real-money trades, demo account orders, or broker buy requests can ever be instantiated.
