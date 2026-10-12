# Deriv Multi-Market Forward SHADOW Research — Economic Reconciliation & Authenticity (V1.8.3.1)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-438%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH%20ONLY%20(NO__TRADE)-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract Families](https://img.shields.io/badge/Families-Rise%2FFall%20%26%20Only%20Ups%2FDowns-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Software Status](https://img.shields.io/badge/Software%20Status-FORWARD__EVIDENCE__RECONCILED-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research Verdict](https://img.shields.io/badge/Research%20Verdict-UNDERPOWERED__EXPLORATORY__SAMPLE-yellow.svg)](https://github.com/thulanesigasa/bot_builder)
[![Confirmation Status](https://img.shields.io/badge/Confirmation-NO__VALIDATED__POSITIVE__EV__EDGE-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.3.1%20Economic%20Reconciliation-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning prospective journaling, and statistical validation system engineered for Deriv synthetic volatility index markets.

Release V1.8.3.1 audits, repairs, and mathematically reconciles the forward research architecture established in V1.8.3. It eliminates mixed economic denominators by introducing canonical cohort separation, replaces mock checksum strings with an authoritative model registry, enforces prospective authority via immutable timestamp auditing, and validates the entire lifecycle through a genuine live SHADOW acceptance test.

Permanent safety invariant: **SHADOW research only**, strictly non-purchasing. Real-money live trade execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`), and all operational decisions remain `NO_TRADE`.

---

## Architecture & Observation Lifecycle

```text
              V1.8.3.1 CANONICAL FORWARD SHADOW RECONCILIATION ARCHITECTURE
                                            |
                  +-------------------------+-------------------------+
                  |                                                   |
                  v                                                   v
      GENUINE MARKET DATA                                 GENUINE PROPOSAL CAPTURE
      (Deriv WebSocket API)                               (Deriv v1/options API)
      +-----------------------------+                     +-----------------------------+
      | wss://api.derivws.com       |                     | underlying_symbol, amount   |
      | 6 Synthetic Volatility mkts |                     | contract_type, duration     |
      | Real-time tick stream sub   |                     | Ask Price, Total Payout     |
      | Native precision & Epoch    |                     | SHA-256 Payload Hash        |
      +-----------------------------+                     +-----------------------------+
                  |                                                   |
                  v                                                   v
      +---------------------------------------------------------------------------------+
      |                 PROSPECTIVE RESEARCH JOURNAL & CHRONOLOGY AUDITOR               |
      | 1. Signal tick received -> compute causal momentum/volatility features          |
      | 2. Strategy forecast committed to SQLite WITH durable journal commit timestamp  |
      | 3. ChronologyAuditor validates: commit_ts <= first_future_tick_receipt_ts       |
      | 4. AuthoritativeModelRegistry tags true SHA-256 and model provenance            |
      +---------------------------------------------------------------------------------+
                                            |
                                            v
      +---------------------------------------------------------------------------------+
      |                     INDEPENDENT CONTRACT OUTCOME RESOLVERS                      |
      |                                                                                 |
      | Family A: Rise / Fall (CALL / PUT)       Family B: Only Ups / Downs (RUNHIGH)   |
      | Terminal spot rule:                      Consecutive monotonic path rule:       |
      | - Win iff S_expiry > S_entry (CALL)      - Win iff S_k > S_{k-1} on every tick  |
      | - Equal spot (S_D == S_0) is a loss      - Any equal spot or dip terminates loss|
      +---------------------------------------------------------------------------------+
                                            |
                                            v
      +---------------------------------------------------------------------------------+
      |                 CANONICAL COHORT ACCOUNTING & ECONOMIC ENGINE                   |
      | Cohort A: All resolved prospective predictions (Directional win rate, Brier)    |
      | Cohort B: Chronologically matched genuine quotes (Descriptive pricing)          |
      | Cohort C: Strict execution-quality SHADOW proxy:                                |
      |           PricedWinRate = PricedWins / PricedSampleN                            |
      |           MeanReturn = Sum(HypotheticalReturns) / PricedSampleN                 |
      |           MBB Resampling: Strictly on paired return sequences of Cohort C       |
      | Cohort D: Preregistered independent confirmation (Quarantined, N = 0)           |
      +---------------------------------------------------------------------------------+
                                            |
                                            v
                             CANONICAL EVIDENCE & REPORT EXPORTS
                             +----------------------------------------+
                             | data/v183_forward_predictions.db       |
                             | data/v1831_acceptance_session.db       |
                             | data/v1831_reconciled_forward_evidence |
                             | 8 Comprehensive Markdown Reports       |
                             +----------------------------------------+
```

---

## Key Engineering & Scientific Advances in V1.8.3.1

### 1. Elimination of Mixed Economic Denominators (`canonical_cohort_reconciler.py`)
- **Root Cause**: In V1.8.3 reporting queries, SQL `AVG(hypothetical_return)` evaluated only non-NULL records, while `COUNT(*)` included unpriced records. This caused unpriced sample sizes (e.g. $N=23$ or $N=29$) to be reported beside priced average returns derived from only 1 to 5 rows.
- **Architectural Solution**: Four mutually exclusive cohorts are independently reported:
  - **Cohort A**: Pure predictive metrics (directional win rate, Brier score, ECE) over all $N=156$ resolved predictions.
  - **Cohort B**: Descriptive broker quote metrics over all $N=24$ proposal-matched predictions.
  - **Cohort C**: Realized economics over all $N=16$ strictly priced observations, with win rate $\frac{\text{Wins}}{N_{\text{priced}}}$ and mean return $\frac{\sum \text{Return}_i}{N_{\text{priced}}}$.
  - **Cohort D**: Preregistered confirmation ($N=0$).

### 2. Authoritative Model Registry & Provenance (`model_registry.py`)
- **Elimination of Mock Checksums**: Completely eliminates placeholder digests (`sha256_mock_a8f9c1e2`, `sha256_mock_e4d3c2b1`, `sha256_v183_frozen_model`).
- **Classification Hierarchy**: Strictly categorizes prediction sources into `TRAINED_FROZEN_MODEL`, `DETERMINISTIC_CAUSAL_BASELINE`, `CONSTANT_PROBABILITY_BASELINE`, and `UNVERIFIED_MODEL_SOURCE`.
- **Verified Digests**:
  - `M_R_75_2TICK_20261011_120000`: `943def871f3a4e6be0380701042ae2341c796cfc39ce151ce20bcb222bbc331d`.
  - `M_R_75_5TICK_20261008_132512`: `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a`.
  - `BASELINE_CAUSAL_MOMENTUM_V1`: Deterministic causal baseline with canonical spec hash `347bbca473b6ef1ee0bb2144fa506f36802e3b4a24f21db597621c1729c15e86`.

### 3. Prospective Authority & Chronology Auditor (`chronology_auditor.py`)
- **Immutable Timestamp Audit**: Evaluates eight discrete timestamps per prediction, proving pre-outcome commitment:
  $$\text{Lead Time} = \text{first\_future\_tick\_receipt\_ts} - \text{journal\_commit\_timestamp} > 0$$
- **Monotonicity**: Enforces $\text{first\_future\_tick\_epoch} > \text{signal\_epoch}$ and $\text{expiry\_epoch} \ge \text{first\_future\_tick\_epoch}$.
- **Fail-Closed Classification**: Reclassifies historical records lacking commit timestamps as `PROSPECTIVE_AUTHORITY_UNVERIFIED`. Observations violating lead times are flagged as `PROSPECTIVE_CHRONOLOGY_VIOLATION`.

### 4. Contract Outcome Resolver Verification
- **Rise/Fall**: Win iff strictly higher (CALL) or strictly lower (PUT). Equal spot ($S_{\text{expiry}} == S_{\text{entry}}$) is evaluated strictly as a loss (0).
- **Only Ups/Downs**: Consecutive monotonicity verified across every single intermediate tick. Any reversal, downward tick, or equal spot results in an immediate loss.
- **Golden Vectors**: 8 independent adversarial test vectors verified.

### 5. Genuine Live Acceptance Session Execution
- **Session ID**: `SESS_20261012_113818_e42816`
- **Telemetry**: 51 genuine broker ticks, 15 proposal quotes, 258 committed predictions, 204 resolved observations, 28 strictly priced Cohort C observations.
- **Verified Lead Time**: Mean prospective lead time of 1,012.4 ms before future tick arrival.
- **Broker Safety**: Zero order purchase requests transmitted.

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── forward_shadow_engine.py                         # Live WebSocket collector, proposal recorder, journal, resolvers (V1.8.3.1)
├── canonical_forward_pipeline_v1831.py              # Canonical reconciliation pipeline & report generator (V1.8.3.1)
├── canonical_cohort_reconciler.py                   # Single authoritative cohort accounting & economic reconciler
├── model_registry.py                                # Authoritative model registry & provenance auditor
├── chronology_auditor.py                            # Prospective chronology & timestamp auditor
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
│   ├── v1831_reconciled_forward_evidence.json       # Machine-readable V1.8.3.1 canonical reconciliation package
│   ├── v183_forward_evidence.json                   # Base V1.8.3 forward evidence package
│   ├── R_100_ticks.csv                              # Volatility 100 Index raw ticks (200,000 ticks)
│   ├── 1HZ100V_ticks.csv                            # Volatility 100 (1s) Index raw ticks (200,000 ticks)
│   ├── R_75_master.csv                              # Volatility 75 Index raw ticks (43,184 ticks)
│   ├── 1HZ75V_ticks.csv                             # Volatility 75 (1s) Index raw ticks (200,000 ticks)
│   ├── R_50_ticks.csv                               # Volatility 50 Index raw ticks (200,000 ticks)
│   └── 1HZ50V_ticks.csv                             # Volatility 50 (1s) Index raw ticks (200,000 ticks)
├── tests/                                           # Automated regression test suite (438 tests, 100% passing)
│   ├── test_v1831_reconciliation_and_authenticity.py# V1.8.3.1 adversarial, cohort, model & synthetic fixture tests (14 tests)
│   ├── test_v183_forward_shadow_research.py         # V1.8.3 safety, resolver, quote & pipeline tests (19 tests)
│   └── ... (34 total test modules)
├── releases/                                        # Packaged release archives (.zip)
│   ├── bot_builder_v1.8.3.1.zip                     # Official V1.8.3.1 Release Package
│   └── bot_builder_v1.8.3.zip                       # Base V1.8.3 Release Package
└── reports/                                         # Generated session and audit reports
    ├── V1_8_3_1_ECONOMIC_DENOMINATOR_AUDIT.md       # Root cause, cohort architecture & SQL denominator separation
    ├── V1_8_3_1_FORWARD_SESSION_REAUDIT.md          # Immutable re-audit of V1.8.3 session records
    ├── V1_8_3_1_MODEL_AUTHENTICITY_AUDIT.md         # Genuine model registry, elimination of mock hashes
    ├── V1_8_3_1_PROSPECTIVE_CHRONOLOGY_AUDIT.md     # Verification of commit timing & future tick boundaries
    ├── V1_8_3_1_CONTRACT_RESOLUTION_AUDIT.md        # Rise/Fall & Only Ups/Downs resolver verification & golden vectors
    ├── V1_8_3_1_QUOTE_ECONOMICS_RECONCILIATION.md   # Per-observation pricing, individual returns, MBB bounds
    ├── V1_8_3_1_LIVE_ACCEPTANCE_SESSION.md          # 35-second live acceptance test telemetry & verification
    └── V1_8_3_1_RELEASE_VALIDATION_REPORT.md        # Comprehensive sign-off, safety invariants & verdicts
```

---

## Reproducible Research Commands

### 1. Execute Non-Purchasing Live SHADOW Data Collection
```bash
python -c "import asyncio; from forward_shadow_engine import DerivLiveShadowCollector; c = DerivLiveShadowCollector(target_markets=['R_75', '1HZ100V'], db_path='data/v1831_acceptance_session.db'); asyncio.run(c.execute_shadow_session(duration_seconds=30.0))"
```

### 2. Execute Authoritative Reconciliation Pipeline
```bash
python canonical_forward_pipeline_v1831.py
```

### 3. Run Automated Regression Test Suite
```bash
python -m pytest tests/test_v1831_reconciliation_and_authenticity.py -v
```

---

## Permanent Safety Standards

The platform enforces absolute, compile-time non-purchasing safety:
- `LIVE_EXECUTION_DISABLED = True` permanently across all discovery, contract, modeling, research, pipeline, and forward engine modules.
- Every operational decision returns `NO_TRADE`.
- Any unexpected invocation of order endpoints (`buy`, `sell`, `place_order`, `send_buy_order`, `send_order`) immediately raises `SafetyViolationError` and fails closed.
- No live or demo purchase requests can ever be transmitted to the broker.
