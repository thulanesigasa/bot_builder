# Deriv Quantitative Research Bot — Strict Cohort Authority & Model Provenance (V1.8.3.2)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-453%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH%20ONLY%20(NO__TRADE)-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract Families](https://img.shields.io/badge/Families-Rise%2FFall%20%26%20Only%20Ups%2FDowns-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Software Status](https://img.shields.io/badge/Software%20Status-STRICT__COHORT__AUTHORITY__CERTIFIED-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research Verdict](https://img.shields.io/badge/Research%20Verdict-UNDERPOWERED__EXPLORATORY__SAMPLE-yellow.svg)](https://github.com/thulanesigasa/bot_builder)
[![Confirmation Status](https://img.shields.io/badge/Confirmation-NO__VALIDATED__POSITIVE__EV__EDGE-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.3.2%20Strict%20Cohort%20Authority-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning prospective journaling, and statistical validation system engineered for Deriv synthetic volatility index markets.

Release V1.8.3.2 establishes strict cohort authority, eliminates self-assigned scientific authority, eliminates hardcoded model verification bypasses, and performs rigorous fail-closed reclassification and independent re-auditing of forward research sessions.

Permanent safety invariant: **SHADOW research only**, strictly non-purchasing. Real-money live trade execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`), and all operational decisions remain `NO_TRADE`.

---

## Architecture & Observation Lifecycle

```text
              V1.8.3.2 STRICT COHORT AUTHORITY & EVIDENCE PIPELINE ARCHITECTURE
                                            |
                   +------------------------+------------------------+
                   |                                                 |
                   v                                                 v
       GENUINE MARKET DATA                               GENUINE PROPOSAL CAPTURE
       (Deriv WebSocket API)                             (Deriv v1/options API)
       +----------------------------+                    +----------------------------+
       | wss://api.derivws.com      |                    | underlying_symbol, amount  |
       | 6 Synthetic Volatility mkts|                    | contract_type, duration    |
       | Real-time tick stream sub  |                    | Ask Price, Total Payout    |
       | Native precision & Epoch   |                    | SHA-256 Payload Hash       |
       +----------------------------+                    +----------------------------+
                   |                                                 |
                   v                                                 v
       +------------------------------------------------------------------------------+
       |                  PROSPECTIVE RESEARCH JOURNAL & ENGINE                       |
       | 1. Signal tick received -> compute causal momentum/volatility features       |
       | 2. Strategy forecast committed to SQLite WITH journal commit timestamp       |
       | 3. Model ID and reported checksum tracked in pending observation state       |
       | 4. AuthoritativeModelRegistry verified per-observation upon resolution       |
       +------------------------------------------------------------------------------+
                                            |
                                            v
       +------------------------------------------------------------------------------+
       |                  INDEPENDENT STRICT COHORT AUTHORITY VALIDATOR              |
       |                      (StrictCohortAuthorityValidator)                        |
       |                                                                              |
       | Tier 1: Source Authenticity (Authorized market, broker-captured classification)
       | Tier 2: Prospective Chronology (commit_ts <= first_future_tick_receipt_ts)  |
       | Tier 3: Model Provenance (Registry verified SHA-256, no mock digests)        |
       | Tier 4: Quote Validity (Physical broker_proposals match, age <= 5.0s, order) |
       | Tier 5: Outcome Integrity (Independent resolver matches observed_outcome)    |
       | Tier 6: Economic Arithmetic (Exact Return = y * Payout - Ask reconciliation)  |
       +------------------------------------------------------------------------------+
                                            |
                                            v
       +------------------------------------------------------------------------------+
       |                    CANONICAL COHORT ACCOUNTING CLASSIFICATION                |
       |                                                                              |
       | Cohort A: Verified prospective predictions (Directional win rate, Brier)    |
       | Cohort B: Chronologically matched genuine quotes (Descriptive pricing)       |
       | Cohort C: Strict execution-quality SHADOW proxy:                             |
       |           PricedWinRate = PricedWins / PricedSampleN                         |
       |           MeanReturn = Sum(HypotheticalReturns) / PricedSampleN              |
       |           MBB Resampling: Strictly on paired return sequences of Cohort C    |
       | Cohort D: Preregistered independent confirmation (Quarantined, N = 0)        |
       | Quarantined: Violates any integrity tier -> excluded from research claims   |
       +------------------------------------------------------------------------------+
                                            |
                                            v
                           CANONICAL EVIDENCE & REPORT EXPORTS
                           +----------------------------------------+
                           | data/v183_forward_predictions.db       |
                           | data/v1831_acceptance_session.db       |
                           | data/v1832_strict_forward_evidence.json|
                           | 9 Comprehensive Audit Reports          |
                           +----------------------------------------+
```

---

## Key Engineering & Scientific Advances in V1.8.3.2

### 1. Independent Strict Cohort Authority Validator (`strict_cohort_validator.py`)
- **Root Cause Eliminated**: In earlier implementations, observations could self-certify scientific authority simply because columns (`proposal_id`, `ask_price`, `hypothetical_return`) were populated. Stored labels like `evidence_cohort = 'COHORT_C'` were accepted at face value.
- **Fail-Closed 6-Tier Gate**: Observations must independently satisfy all six tiers to qualify for Cohort C:
  1. *Source Authenticity*: Market belongs to authorized 6 synthetic indices; source is verified broker capture.
  2. *Prospective Chronology*: Pre-outcome commitment proven via `journal_commit_timestamp <= first_future_tick_receipt_ts` with positive lead time and epoch monotonicity.
  3. *Model Provenance*: SHA-256 digest verified by `AuthoritativeModelRegistry`; mock digests (`sha256_mock_*`, `sha256_v183_frozen_model`) fail closed.
  4. *Quote Validity*: Proposal exists in physical `broker_proposals` table, matches symbol/type/duration, received before decision timestamp, age $\le 5.0\text{s}$, pricing terms match.
  5. *Outcome Integrity*: Independent contract resolver reproduces exact terminal/monotonic outcome.
  6. *Economic Arithmetic*: PnL strictly satisfies $R = y \times \text{Payout} - \text{Ask}$.

### 2. Elimination of Hardcoded Model Verification Bypass (`forward_shadow_engine.py`)
- **Defect Repaired**: In `ForwardShadowEngine._check_pending_resolutions`, `model_is_verified` was previously hardcoded to `True` during record insertion.
- **Per-Observation Registry Enforcement**: The engine now tracks `model_version` and `model_checksum` across observation life cycles and queries `AuthoritativeModelRegistry.verify_model_provenance()` for each individual prediction. Unverified or mismatched models are committed with `model_is_verified = 0`.

### 3. Fail-Closed Historical Session Reclassification
- **Session Audited**: `SESS_20261012_105122_f4db88` in `data/v183_forward_predictions.db`.
- **Finding**: Historical records lacked durable `journal_commit_timestamp` and reported mock digest `sha256_v183_frozen_model`.
- **Authoritative Verdict**: Historical Strict Cohort C count is verified as **0** ($N=0$). Observations are safely reclassified to Cohort B ($N=24$) and Cohort A ($N=140$), with 46 quarantined unpriced records. Raw historical records remain untouched while the canonical manifest certifies the reclassification.

### 4. Independent Acceptance Session Re-Audit
- **Session Audited**: `SESS_20261012_113818_e42816` in `data/v1831_acceptance_session.db`.
- **Authoritative Verdict**: Exactly **28 observations** satisfy all 6 tiers and are certified as Strict Cohort C.
- **Metrics**: 28 priced observations, 17 wins (60.71% win rate), cumulative return +$15.22, mean return +$0.5436/contract, mean prospective lead time 1,012.4 ms.

### 5. Canonical Authority Pipeline & Comprehensive Reports
- **Pipeline**: `canonical_evidence_authority_pipeline.py` audits both sessions, validates database integrity, runs the 6-tier authority gate, and exports `data/v1832_strict_forward_evidence.json`.
- **Formal Reports**: 9 audit reports published under `reports/` following strict Rule 18 standards (shields.io badges, zero emojis).

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── forward_shadow_engine.py                         # Live WebSocket collector, proposal recorder, journal, resolvers (V1.8.3.2)
├── strict_cohort_validator.py                       # 6-Tier authoritative cohort validator & decision engine (V1.8.3.2)
├── canonical_evidence_authority_pipeline.py         # Full authoritative evidence pipeline & report generator (V1.8.3.2)
├── canonical_cohort_reconciler.py                   # Authoritative cohort reconciler & accounting engine
├── model_registry.py                                # Authoritative model registry & provenance auditor
├── chronology_auditor.py                            # Prospective chronology & timestamp auditor
├── canonical_forward_pipeline_v1831.py              # Historical forward pipeline (V1.8.3.1)
├── canonical_forward_pipeline.py                    # Historical forward pipeline (V1.8.3)
├── canonical_pipeline.py                            # Historical reproducible research pipeline (V1.8.2)
├── data_provenance.py                               # Fail-closed data provenance & cryptographic auditor
├── quote_economics_engine.py                        # Per-observation quote matching & economic engine
├── rise_fall_research.py                            # Multi-market edge discovery & dependence auditor
├── market_discovery.py                              # Dynamic market discovery, 6 symbols, capability matrix
├── contract_rise_fall.py                            # Canonical Rise/Fall contract specification & outcome resolver
├── model_rise_fall.py                               # Probabilistic modeling, causal features, Brier calibration
├── data/                                            # Raw tick streams, SQLite databases, and evidence exports
│   ├── v183_forward_predictions.db                  # Historical V1.8.3 live SHADOW session database (untouched)
│   ├── v1831_acceptance_session.db                  # Genuine V1.8.3.1 live SHADOW acceptance database
│   ├── v1832_strict_forward_evidence.json           # Machine-readable V1.8.3.2 canonical evidence package
│   ├── v1831_reconciled_forward_evidence.json       # Base V1.8.3.1 reconciliation package
│   ├── v183_forward_evidence.json                   # Base V1.8.3 forward evidence package
│   ├── R_100_ticks.csv                              # Volatility 100 Index raw ticks (200,000 ticks)
│   ├── 1HZ100V_ticks.csv                            # Volatility 100 (1s) Index raw ticks (200,000 ticks)
│   ├── R_75_master.csv                              # Volatility 75 Index raw ticks (43,184 ticks)
│   ├── 1HZ75V_ticks.csv                             # Volatility 75 (1s) Index raw ticks (200,000 ticks)
│   ├── R_50_ticks.csv                               # Volatility 50 Index raw ticks (200,000 ticks)
│   └── 1HZ50V_ticks.csv                             # Volatility 50 (1s) Index raw ticks (200,000 ticks)
├── tests/                                           # Automated regression test suite (453 tests, 100% passing)
│   ├── test_v1833_evidence_integrity.py             # V1.8.3.3 fail-closed evidence, quote & commit tests (4 tests)
│   ├── test_v1832_strict_cohort_authority.py        # V1.8.3.2 strict authority, model check & synthetic fixture tests (11 tests)
│   ├── test_v1831_reconciliation_and_authenticity.py# V1.8.3.1 adversarial, cohort, model & synthetic fixture tests (14 tests)
│   ├── test_v183_forward_shadow_research.py         # V1.8.3 safety, resolver, quote & pipeline tests (19 tests)
│   └── ... (36 total test modules)
├── releases/                                        # Packaged release archives (.zip)
│   ├── bot_builder_v1.8.3.2.zip                     # Official V1.8.3.2 Release Package
│   ├── bot_builder_v1.8.3.1.zip                     # Historical V1.8.3.1 Release Package
│   └── bot_builder_v1.8.3.zip                       # Historical V1.8.3 Release Package
└── reports/                                         # Generated session and audit reports
    ├── V1_8_3_2_ROOT_CAUSE_AND_AUTHORITY_REPAIR.md  # Architectural root cause of self-certification & repair
    ├── V1_8_3_2_STRICT_COHORT_ELIGIBILITY_AUDIT.md  # 6-tier verification rules & cohort definitions
    ├── V1_8_3_2_MODEL_VERIFICATION_ENFORCEMENT.md   # Per-observation model verification audit
    ├── V1_8_3_2_HISTORICAL_SESSION_RECLASSIFICATION.md # Historical V1.8.3 session fail-closed reclassification
    ├── V1_8_3_2_ACCEPTANCE_SESSION_REAUDIT.md       # Acceptance session re-audit certifying 28 Cohort C records
    ├── V1_8_3_2_QUOTE_AND_CHRONOLOGY_INTEGRITY.md   # Broker quote validation & prospective lead times
    ├── V1_8_3_2_CONTRACT_ECONOMIC_RECONCILIATION.md # Exact economic arithmetic reconciliation & MBB analysis
    ├── V1_8_3_2_FINAL_INFRASTRUCTURE_READINESS.md   # Readiness matrix across all 6 markets & 2 families
    └── V1_8_3_2_RELEASE_VALIDATION_REPORT.md        # Comprehensive release sign-off & safety invariants
```

---

## Reproducible Research Commands

### 1. Run Strict Evidence Authority Pipeline
```bash
python canonical_evidence_authority_pipeline.py
```

### 2. Run Automated Regression Test Suite
```bash
python -m pytest tests/test_v1832_strict_cohort_authority.py -v
python -m pytest -q
```

### 3. Execute Non-Purchasing Live SHADOW Data Collection
```bash
python -c "import asyncio; from forward_shadow_engine import DerivLiveShadowCollector; c = DerivLiveShadowCollector(target_markets=['R_75', '1HZ100V'], db_path='data/v1831_acceptance_session.db'); asyncio.run(c.execute_shadow_session(duration_seconds=30.0))"
```

---

## Permanent Safety Standards

The platform enforces absolute, compile-time non-purchasing safety:
- `LIVE_EXECUTION_DISABLED = True` permanently across all discovery, contract, modeling, research, pipeline, and forward engine modules.
- Every operational decision returns `NO_TRADE`.
- Any unexpected invocation of order endpoints (`buy`, `sell`, `place_order`, `send_buy_order`, `send_order`) immediately raises `SafetyViolationError` and fails closed.
- No live or demo purchase requests can ever be transmitted to the broker.
