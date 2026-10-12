# Deriv Multi-Market Genuine Forward SHADOW Research & Economic Validation (V1.8.3)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/thulanesigasa/bot_builder)
[![Testing](https://img.shields.io/badge/pytest-424%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Dependencies](https://img.shields.io/badge/Dependencies-websockets%20%7C%20pandas%20%7C%20numpy%20%7C%20pytest%20%7C%20sqlite3-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![API](https://img.shields.io/badge/API-Deriv%20WebSocket%20v1%2Foptions%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety](https://img.shields.io/badge/Safety-Real--Money%20Trading%20DISABLED-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Operating Mode](https://img.shields.io/badge/Mode-SHADOW%20RESEARCH%20ONLY%20(NO__TRADE)-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Multi-Market](https://img.shields.io/badge/Markets-6%20Target%20Indices%20(V100%2C%20V75%2C%20V50)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Contract Families](https://img.shields.io/badge/Families-Rise%2FFall%20%26%20Only%20Ups%2FDowns-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Software Status](https://img.shields.io/badge/Software%20Status-FORWARD__PIPELINE__VALIDATED-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Research Verdict](https://img.shields.io/badge/Research%20Verdict-INSUFFICIENT__PROSPECTIVE__EVIDENCE-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Version](https://img.shields.io/badge/Version-V1.8.3%20Forward%20SHADOW%20Research-0284C7)](https://github.com/thulanesigasa/bot_builder)

A quantitative financial research, machine-learning prospective journaling, and statistical validation system engineered for Deriv synthetic volatility index markets.

Release V1.8.3 transitions the bot from retrospective historical analysis to **genuine forward SHADOW research**. It establishes real-time Deriv WebSocket connectivity, captures genuine broker proposal quotes, journals prospective strategy forecasts before future ticks arrive, resolves hypothetical contract outcomes under independent broker rules, and calculates individual observation economics.

Operating mode: **SHADOW**, strictly non-purchasing. Real-money live trade execution remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`), and all operational decisions remain `NO_TRADE`.

---

## Architecture & Observation Lifecycle

```text
               V1.8.3 GENUINE FORWARD SHADOW RESEARCH SYSTEM ARCHITECTURE
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
      |                           PROSPECTIVE RESEARCH JOURNAL                          |
      | 1. Signal tick received -> compute causal momentum/volatility features          |
      | 2. Strategy forecast generated -> committed to SQLite BEFORE future ticks       |
      | 3. Matched against latest chronologically eligible genuine proposal quote       |
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
      |                        PER-OBSERVATION ECONOMIC ENGINE                          |
      | BreakEven_i = Ask_i / Payout_i                                                  |
      | PredictedEV_i = P_model_i * Payout_i - Ask_i                                    |
      | HypotheticalReturn_i = Outcome_i * Payout_i - Ask_i                             |
      | Moving Block Bootstrap (MBB): serial dependence-aware 95% confidence intervals  |
      +---------------------------------------------------------------------------------+
                                            |
                                            v
      +---------------------------------------------------------------------------------+
      |                      EVIDENCE COHORTS & AUDIT RECONCILIATION                    |
      | Cohort A: All prospective predictions (Predictive scoring)                      |
      | Cohort B: Chronologically matched genuine quotes (Descriptive economics)        |
      | Cohort C: Strict execution-quality SHADOW proxy (Realized hypothetical return)  |
      | Cohort D: Preregistered confirmation (Strictly quarantined from exploratory)    |
      +---------------------------------------------------------------------------------+
                                            |
                                            v
                             CANONICAL EVIDENCE & REPORT EXPORTS
                             +-----------------------------------+
                             | data/v183_forward_predictions.db  |
                             | data/v183_forward_evidence.json   |
                             | 8 Comprehensive Markdown Reports  |
                             +-----------------------------------+
```

---

## Key Scientific Advances in V1.8.3

### 1. Genuine Live Tick Collection & Metadata Discovery (`forward_shadow_engine.py`)
- **WebSocket Verification**: Connects to `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089` via TLS 1.3 (`TLS_AES_256_GCM_SHA384`, latency 509 ms).
- **Capability Matrix**: Discovered and confirmed that all six research markets (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`) support both:
  - Rise/Fall: `CALL`, `PUT` across 2, 3, 5, 10 ticks.
  - Only Ups/Downs: `RUNHIGH`, `RUNLOW` across 2, 5 ticks.
- **Payload Integrity**: Preserves raw broker timestamps, pip precision, and SHA-256 payload digests.

### 2. Genuine Broker Proposal Quote Capture
- **Real-Time Sampling**: Automatically issues paced non-purchasing proposal requests to Deriv Options API.
- **Strict Isolation**: Enforces zero cross-market, cross-family, cross-direction, or cross-duration quote leakage.
- **Freshness & Chronology**: Rejects quotes older than 5.0 seconds from the decision timestamp or post-dating the decision.
- **No Reference Fallback**: If a quote is absent, the observation remains unpriced (`ask_price = None`, `hypothetical_return = None`).

### 3. Prospective Prediction Journaling Prior to Outcome Ticks
- **Anti-Lookahead Guarantee**: Strategy forecasts and predictions are committed to SQLite *before* subsequent entry or outcome ticks arrive.
- **Tamper Evidence**: Uses SHA-256 model checksums and causal feature snapshots.
- **Chronology Audit**: Decisions occurring after tick arrival fail closed as `PROSPECTIVE_AUTHORITY_UNVERIFIED`.

### 4. Independent Contract Outcome Resolvers
- **Rise/Fall Resolver**:
  - `CALL`: Win (1) iff $S_D > S_0$; Loss (0) otherwise.
  - `PUT`: Win (1) iff $S_D < S_0$; Loss (0) otherwise.
  - Equal spot ($S_D == S_0$) is strictly evaluated as a Loss (0) with zero payout.
- **Only Ups / Only Downs Resolver**:
  - `RUNHIGH`: Win (1) iff $S_k > S_{k-1}$ for all $k \in \{1 \dots D\}$. Any equal spot ($S_k == S_{k-1}$) or downward spot terminates immediately as a Loss (0).
  - `RUNLOW`: Win (1) iff $S_k < S_{k-1}$ for all $k \in \{1 \dots D\}$. Any equal spot or upward spot terminates immediately as a Loss (0).

### 5. Observation-Level Economics & Moving Block Bootstrap
- **Individual Return Valuation**: Computes exact economic returns for each observation based on its specific matched broker ask and payout:
  $$\text{Return}_i = \text{Outcome}_i \times \text{Payout}_i - \text{Ask}_i$$
- **Dependence-Aware Uncertainty**: Applies Moving Block Bootstrap (MBB) resampling to paired return sequences to produce conservative 95% confidence intervals that preserve temporal autocorrelation.

### 6. Evidence Cohort Quarantine
- **Cohort A**: All prospective predictions (210 committed in baseline live session).
- **Cohort B**: Proposal-matched predictions (24 matched).
- **Cohort C**: Execution-quality SHADOW proxy observations (16 resolved with genuine broker prices).
- **Cohort D**: Preregistered confirmation reserved exclusively for frozen strategies (strictly quarantined, 0 observations).

### 7. Authoritative Release Verdicts
- **Software Pipeline Status**:
  $$\mathbf{FORWARD\_PIPELINE\_VALIDATED}$$
- **Research Evidence Verdict**:
  $$\mathbf{INSUFFICIENT\_PROSPECTIVE\_EVIDENCE}$$
  *(Classified as `UNDERPOWERED_EXPLORATORY_SAMPLE` due to exploratory sample size $N < 5,000$)*
- **Live Execution Orders**: $\mathbf{0}$ (Strict `NO_TRADE` compile-time invariant)

---

## Directory Structure

```text
bot_builder/
├── config.py                                        # Global application configuration & safety preflight
├── forward_shadow_engine.py                         # Live WebSocket collector, proposal recorder, journal, resolvers (V1.8.3)
├── canonical_forward_pipeline.py                    # Unified canonical forward evidence pipeline & report generator (V1.8.3)
├── canonical_pipeline.py                            # Historical reproducible research pipeline (V1.8.2)
├── data_provenance.py                               # Fail-closed data provenance & cryptographic auditor
├── quote_economics_engine.py                        # Per-observation quote matching & economic engine
├── rise_fall_research.py                            # Multi-market edge discovery & dependence auditor
├── market_discovery.py                              # Dynamic market discovery, 6 symbols, capability matrix
├── contract_rise_fall.py                            # Canonical Rise/Fall contract specification & outcome resolver
├── model_rise_fall.py                               # Probabilistic modeling, causal features, Brier calibration
├── contract_specification.py                        # Canonical contract specs with mapping versions
├── dual_duration_research.py                        # Paired dual-duration research engine
├── session_reconciler.py                            # Automated session reconciler with separated cohort accounting
├── forward_session.py                               # Prospective session lifecycle & SQLite registry
├── probability.py                                   # Statistical distributions, Wilson score intervals
├── data/                                            # Raw tick streams, SQLite databases, and evidence exports
│   ├── v183_forward_predictions.db                  # Genuine V1.8.3 live SHADOW session SQLite database
│   ├── v183_forward_evidence.json                   # Machine-readable V1.8.3 canonical forward evidence package
│   ├── R_100_ticks.csv                              # Volatility 100 Index raw ticks (200,000 ticks)
│   ├── 1HZ100V_ticks.csv                            # Volatility 100 (1s) Index raw ticks (200,000 ticks)
│   ├── R_75_master.csv                              # Volatility 75 Index raw ticks (43,184 ticks)
│   ├── 1HZ75V_ticks.csv                             # Volatility 75 (1s) Index raw ticks (200,000 ticks)
│   ├── R_50_ticks.csv                               # Volatility 50 Index raw ticks (200,000 ticks)
│   ├── 1HZ50V_ticks.csv                             # Volatility 50 (1s) Index raw ticks (200,000 ticks)
│   ├── quotes.db                                    # Historical proposal quote database
│   ├── v182_data_provenance_manifest.json           # V1.8.2 provenance audit manifest
│   └── v182_multi_market_evidence.json              # V1.8.2 canonical evidence package
├── tests/                                           # Automated regression test suite (424 tests, 100% passing)
│   ├── test_v183_forward_shadow_research.py         # Comprehensive V1.8.3 safety, resolver, quote & pipeline tests (19 tests)
│   ├── test_v182_evidence_integration.py            # V1.8.2 evidence integration & provenance tests (16 tests)
│   ├── test_v181_economic_integrity_repair.py       # V1.8.1 economic integrity tests (17 tests)
│   ├── test_v180_multi_market_rise_fall.py          # V1.8.0 multi-market Rise/Fall tests (23 tests)
│   └── ... (33 total test modules)
├── releases/                                        # Packaged release archives (.zip)
│   ├── bot_builder_v1.8.3.zip                       # Official V1.8.3 Release Package
│   └── bot_builder_v1.8.2.zip                       # Base V1.8.2 Release Package
└── reports/                                         # Generated session and audit reports
    ├── V1_8_3_LIVE_CONNECTIVITY_AUDIT.md            # Live WebSocket connection, TLS 1.3, latency & capability matrix
    ├── V1_8_3_RISE_FALL_FORWARD_SESSION.md          # Genuine Rise/Fall SHADOW telemetry, win rates & empirical returns
    ├── V1_8_3_ONLY_UPS_DOWNS_FORWARD_SESSION.md     # Genuine Only Ups/Downs monotonic path telemetry & returns
    ├── V1_8_3_QUOTE_CAPTURE_AUDIT.md                # Genuine broker proposal quotes, inventory & isolation rules
    ├── V1_8_3_FORWARD_JOURNAL_RECONCILIATION.md     # Pre-outcome journaling lifecycle & cohort accounting
    ├── V1_8_3_CONTRACT_FAMILY_COMPARISON.md         # Side-by-side economic comparison of both contract families
    ├── V1_8_3_STATISTICAL_POWER_AND_STOPPING_PLAN.md# N_eff sample size horizon & sequential stopping boundaries
    └── V1_8_3_RELEASE_VALIDATION_REPORT.md          # Comprehensive V1.8.3 sign-off, safety invariants & verdicts
```

---

## Reproducible Research Commands

### 1. Execute Non-Purchasing Live SHADOW Data Collection
```bash
python -c "import asyncio; from forward_shadow_engine import DerivLiveShadowCollector; c = DerivLiveShadowCollector(target_markets=['R_75', '1HZ100V']); asyncio.run(c.execute_shadow_session(duration_seconds=30.0))"
```

### 2. Execute Canonical Forward Evidence Pipeline
```bash
python canonical_forward_pipeline.py
```

### 3. Run Automated Regression Test Suite
```bash
python -m pytest tests/test_v183_forward_shadow_research.py -v
```

---

## Permanent Safety Standards

The platform enforces absolute, compile-time non-purchasing safety:
- `LIVE_EXECUTION_DISABLED = True` across all discovery, contract, modeling, research, pipeline, and forward engine modules.
- Every operational decision returns `NO_TRADE`.
- Any unexpected invocation of order endpoints (`buy`, `sell`, `place_order`, `send_buy_order`, `send_order`) immediately raises `SafetyViolationError` and fails closed.
- No live or demo purchase requests can ever be transmitted to the broker.
