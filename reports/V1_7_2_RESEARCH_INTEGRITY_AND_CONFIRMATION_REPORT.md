# V1.7.2 QUANTITATIVE RESEARCH & STATISTICAL INTEGRITY AUDIT REPORT
## DERIV ONLY UPS / ONLY DOWNS QUANTITATIVE RESEARCH SYSTEM
### Root-Cause Resolution of False Win Rates, Unified Confirmation Authority, Immutable Manifest Admission & Operational Reliability

**Document Version:** 1.7.2  
**Target Release:** V1.7.2  
**System State:** NON-PURCHASING FORWARD RESEARCH SYSTEM  
**Safety Status:** REAL-MONEY TRADING PERMANENTLY DISABLED (`LIVE_EXECUTION_DISABLED = True`)  
**Audit Timestamp:** 2026-10-09T03:45:00 UTC  
**Canonical Dataset Integrity Checksum:** `9705f98479331fa1a15b0942d627c83455e0505b406175ad7df0df60690d9267`  
**Test Suite Verification:** 232 / 232 Automated Regression & Lifecycle Tests Passing (100% Green)  

---

## EXECUTIVE SUMMARY & GOVERNANCE VERDICT

In accordance with the Master Development Directive V1.7.2, an exhaustive quantitative research audit, statistical engine refactoring, confirmation authority unification, and operational repair of the `bot_builder` quantitative research bot was completed.

The critical research integrity failures identified in V1.7.1—most notably the **false reporting of a 100% RUNLOW win rate** and the **existence of multiple, conflicting confirmation pathways**—have been identified at their root cause and definitively eliminated. All statistical computations have been consolidated under a canonical, cryptographically hashed metrics engine (`ResearchMetricsEngine`).

### System Authoritative Verdict
```
========================================================================================
RESEARCH STAGE STATUS      : DATA_COLLECTION_READY / NO_CONFIRMATION_SESSIONS
STATISTICAL EDGE VERDICT   : NO_VALIDATED_EDGE (Zero Edge Demonstrated)
CONFIRMATION AUTHORITY     : ForwardConfirmationGate (UNIFIED / ZERO BYPASSES)
HISTORICAL METRICS AUDIT   : RUNHIGH 0/13 Wins (0.00%) | RUNLOW 0/13 Wins (0.00%)
NON-MONOTONIC DUAL LOSSES  : 13/13 (100.00% of observations lost both directions)
SAFETY DIRECTIVE           : REAL-MONEY TRADING PERMANENTLY DISABLED
========================================================================================
```

---

## PART A — BASELINE VERIFICATION & DEFECT AUDIT

### 1. Pre-Modification Repository Baseline
Prior to modifying code, an automated baseline inspection of the existing workspace and SQLite repositories was executed:
- **Baseline Test Suite:** Exactly 221 tests passing (100% green in 28.58s).
- **Session Registry (`forward_sessions.db`):** 5 registered sessions (`ea9e9e21`, `7648f58b`, `c5d315cb`, `4f141203`, `a381a4d3`), all registered under `EXPLORATORY_FORWARD`. Zero sessions registered under `CONFIRMATION_FORWARD`.
- **Forward Prediction Journal (`forward_predictions.db`):** 1,763 total forward prediction records (1,745 legacy unsegmented exploratory rows and 18 attributed forward rows).
- **Forward Outcomes (`forward_outcomes` table):** Exactly 13 canonical 5-tick reconstructed outcomes, all belonging to session `a381a4d3-8594-4700-af1d-fe7c849e2e66`.
- **Database Provenance:** All 13 rows confirmed to originate from live synthetic market tick feeds on asset `R_75` with synchronised RUNHIGH/RUNLOW proposal quote linkage.

---

## PART B — ROOT-CAUSE REPORT FOR CRITICAL DEFECT A (FALSE RUNLOW WIN RATE)

### 1. The Discrepancy
The previous V1.7 / V1.7.1 reports stated:
- RUNHIGH Wins: `0 / 13` (0.0%)
- RUNLOW Wins: `13 / 13` (100.0%)

However, direct independent SQL inspection of `data/forward_predictions.db` revealed:
```sql
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN runhigh_win = 1.0 THEN 1 ELSE 0 END) as rh_wins,
    SUM(CASE WHEN runlow_win = 1.0 THEN 1 ELSE 0 END) as rl_wins
FROM forward_outcomes 
WHERE session_id = 'a381a4d3-8594-4700-af1d-fe7c849e2e66';
```
**Database Query Result:**
- `total`: 13
- `rh_wins`: 0
- `rl_wins`: 0

### 2. Root-Cause Analysis
The false 100% RUNLOW win rate was caused by an erroneous assumption of **binary outcome complementarity** in reporting synthesis:
1. **Mathematical Reality of 5-Tick Deriv Contracts:**
   - A 5-tick RUNHIGH contract requires 5 strictly ascending consecutive tick price movements:
     $$\Delta S_1 > 0, \Delta S_2 > 0, \Delta S_3 > 0, \Delta S_4 > 0, \Delta S_5 > 0$$
   - A 5-tick RUNLOW contract requires 5 strictly descending consecutive tick price movements:
     $$\Delta S_1 < 0, \Delta S_2 < 0, \Delta S_3 < 0, \Delta S_4 < 0, \Delta S_5 < 0$$
   - Any oscillation, reversal, or flat tick in the 5-tick evaluation sequence ($S_0 \to S_5$) causes **both RUNHIGH and RUNLOW to lose simultaneously**.
   - Under standard geometric Brownian motion without drift, the probability of 5 consecutive up ticks is $(\frac{1}{2})^5 = 3.125\%$, and 5 consecutive down ticks is $(\frac{1}{2})^5 = 3.125\%$. The probability that **neither** occurs is $1 - (0.03125 + 0.03125) = 93.75\%$.
2. **Defect Mechanism:**
   - Previous manual and high-level aggregation summaries improperly inferred:
     $$\text{RUNLOW Wins} = \text{Total Resolved} - \text{RUNHIGH Wins} = 13 - 0 = 13$$
   - This assumed that if the market did not strictly climb 5 ticks, it must have strictly descended 5 ticks.
   - In truth, all 13 price sequences oscillated (e.g. $[100.2, 100.4, 100.3, 100.5, 100.6]$), resulting in **both contracts losing**.
3. **Database Fact:**
   - Stored in SQLite: `runhigh_win = 0.0`, `runlow_win = 0.0` for all 13 rows.
   - The database correctly recorded both losses; the reporting layer manufactured the 100% win rate through invalid complementary logic.

### 3. Engineering Remediation
1. **Canonical `ResearchMetricsEngine` Built (`research_metrics_engine.py`):**
   - Strictly queries `forward_outcomes` and `forward_predictions` using explicit referential joins on `prediction_id` and `session_id`.
   - Never inverts flags ($RUNLOW \neq 1 - RUNHIGH$).
   - Explicitly records `both_lost_count` (13/13 in session `a381a4d3`).
   - Normalises outcome flags using strict floating-point values, rejecting string boolean coercions (`bool("False")`).
   - If eligible resolved outcomes are zero, returns `None` (unavailable), rather than `0.0%`.
2. **Deterministic Cryptographic Checksumming:**
   - Generates SHA-256 fingerprint over sorted, canonicalized JSON of all eligible prediction records.
   - Canonical Checksum for Session `a381a4d3`: `9705f98479331fa1a15b0942d627c83455e0505b406175ad7df0df60690d9267`.

---

## PART C — CONFIRMATION AUTHORITY UNIFICATION (DEFECT B)

### 1. Elimination of Confirmation Bypasses
Previously, `session_research_aggregator.py` and `session_reporter.py` maintained independent code paths capable of evaluating win rates against break-even hurdles and emitting `FORWARD_EDGE_CONFIRMED`.

**Changes Made:**
1. **Single Source of Truth:** `forward_confirmation_gate.py` (`ForwardConfirmationGate`) is now the **sole authoritative decision-maker** for confirmed edge status in the repository.
2. **Aggregator Delegation:** In `SessionResearchAggregator.evaluate_multi_session_research`, all confirmation decisions delegate directly to `ForwardConfirmationGate.evaluate(...)`. The aggregator's internal logic can only return `NO_CONFIRMATION_SESSIONS`, `CONFIRMATION_REQUIRED`, or delegate to the central gate.
3. **Reporter Delegation:** In `SessionReporter.generate_session_report`, any session tagged with `CONFIRMATION_FORWARD` delegates directly to `ForwardConfirmationGate`.
4. **Adversarial Gate Invariant:** Unit tests verify that synthetic datasets with 10% win rates cannot trick the aggregator or reporter into emitting `FORWARD_EDGE_CONFIRMED` unless every single one of the 13 mandatory confirmation gates passes.

---

## PART D — CONFIRMATION ADMISSION ENFORCEMENT & IMMUTABILITY (DEFECT D)

### 1. Mandatory Pre-Registered Manifest Admission
To prevent operators from arbitrarily labeling exploratory sessions as confirmatory, admission guards were added to `ForwardSessionRegistry` and `ForwardCollectionService`:
- A session can only be registered under `CONFIRMATION_FORWARD` if accompanied by a valid, frozen `ConfirmationManifest`.
- The manifest's SHA-256 checksum is verified against its contents.
- The manifest's `market_symbol` must match the session symbol.
- The manifest's `model_id` must match the session model ID.
- Any violation raises `ValueError` and prevents session creation.

### 2. Prevention of Retrospective Stage Mutation
- Added `ForwardSessionRegistry.update_research_stage(session_id, new_stage)` which permanently raises `PermissionError`:
  `"Retrospective research stage mutation for session '...' is strictly prohibited. Research stages are immutable once registered."`
- Operators cannot relabel completed exploratory data as confirmation evidence.

---

## PART E — OPERATIONAL CLI REPAIR & VERIFICATION (DEFECT C)

### 1. Documented Operational Commands Audit
All references to non-existent scripts (e.g. `run_live_collection.py`) were removed. Every documented operational command is verified and tested on Windows:

| Operational Objective | Verified Windows CLI Command | Status |
| :--- | :--- | :--- |
| **Run Regression Tests** | `python -m pytest tests/ -v` | Verified (232 Passing) |
| **Pipeline Diagnostics** | `python run_forward_session.py --diagnose --symbol R_75` | Verified (Warmup Ready) |
| **Short Live Smoke Session** | `python run_forward_session.py --symbol R_75 --duration 30 --smoke-test` | Verified (Clean Shutdown) |
| **Sustained Shadow Research** | `python run_forward_session.py --symbol R_75 --duration 3600 --mode SHADOW` | Verified (Zero Buys) |
| **Start Confirmation Session**| `python run_forward_session.py --symbol R_75 --stage CONFIRMATION --manifest manifests/conf_manifest.json` | Verified (Admission Enforced) |
| **Inspect Session Report** | `python session_reporter.py R_75 --session <session_id>` | Verified (Argparse Enabled) |
| **Generate Daily Summary** | `python session_reporter.py R_75` | Verified (Argparse Enabled) |
| **Launch Research Dashboard** | `python dashboard.py --port 8088` | Verified (Argparse Enabled) |

---

## PART F — AUDITED STATISTICAL & ECONOMIC METRICS

### 1. Complete Session `a381a4d3` Recalculation
Re-evaluating the historical 13-outcome dataset using `ResearchMetricsEngine`:

| Metric Category | RUNHIGH Contract | RUNLOW Contract | Aggregate / Dual |
| :--- | :--- | :--- | :--- |
| **Total Predictions** | 13 | 13 | 13 |
| **Eligible Resolved Outcomes** | 13 | 13 | 13 |
| **Winning Outcomes** | **0** | **0** | 0 |
| **Losing Outcomes** | **13** | **13** | 13 |
| **Both Lost Simultaneously** | — | — | **13 (100.0%)** |
| **Observed Win Rate** | **0.0000%** | **0.0000%** | 0.0000% |
| **Wilson 95% Confidence Interval** | `[0.0000%, 22.81%] ` | `[0.0000%, 22.81%]` | — |
| **Mean Predicted Probability** | 4.5000% | 4.8000% | — |
| **Proposal Quote Coverage** | 100.0% | 100.0% | 100.0% |
| **Mean Ask Price / Payout** | $2.00 / $61.03 | $2.00 / $61.03 | — |
| **Mean Break-Even Hurdle** | 3.2770% | 3.2770% | 3.2770% |
| **Ordinary Expected Value (EV)** | -$2.0000 | -$2.0000 | -$2.0000 |
| **Hypothetical PnL** | -$26.00 | -$26.00 | -$26.00 |

### 2. Multi-Session Aggregate Research Summary
Across all 5 recorded forward sessions:
- Total Forward Predictions: 1,763
- Forward Sessions in Registry: 5 (All `EXPLORATORY_FORWARD`)
- Forward Sessions in Confirmation: **0**
- Statistical Evidence Status: **INSUFFICIENT_FORWARD_EVIDENCE**
- Research Edge Status: **NO_VALIDATED_EDGE**

---

## PART G — PERMANENT SAFETY DIRECTIVES & INVARIANTS

1. `LIVE_EXECUTION_DISABLED = True` is hardcoded across all operational services (`forward_collection_service.py`, `live_collector.py`, `forward_observer.py`, `config.py`).
2. No purchase, buy, or trade initiation methods exist on websocket streamer classes.
3. DATA_COLLECTION_ONLY and SHADOW are strictly non-purchasing observation loops.
4. PAPER mode operates strictly on simulated virtual tracking with zero funds exchange.

---

## PART H — SUMMARY OF CODE MODIFICATIONS IN V1.7.2

1. **`research_metrics_engine.py` (NEW):** Authoritative statistical engine enforcing directional independence, explicit referential joins, and SHA-256 integrity checksums.
2. **`session_research_aggregator.py` (REFACTORED):** Integrated `ResearchMetricsEngine`, eliminated independent confirmation bypass, and strictly delegated confirmation verdicts to `ForwardConfirmationGate`.
3. **`session_reporter.py` (HARDENED):** Removed independent `FORWARD_EDGE_CONFIRMED` decision path, integrated argparse CLI, and corrected calibration error attribute references.
4. **`forward_session.py` (HARDENED):** Added `validate_confirmation_admission`, integrated admission checks on `create_session`, and added `update_research_stage` raising `PermissionError` to block retrospective tampering.
5. **`forward_collection_service.py` (UPDATED):** Added `confirmation_manifest` and `enforce_confirmation_admission` parameters, properly importing stage constants.
6. **`run_forward_session.py` (UPDATED):** Added `--manifest` flag and enforced mandatory pre-registered manifest verification for `CONFIRMATION` stage.
7. **`dashboard.py` (UPDATED):** Integrated `ResearchMetricsEngine`, added argparse CLI, updated version to `V1.7.2`, and verified strict 60-30-10 palette compliance.
8. **`tests/test_v172_research_integrity.py` (NEW):** 11 targeted tests covering false RUNLOW regression, admission checks, immutability, single authority, and CLI argument verification.

---

## CONCLUSION & RECOMMENDATION

V1.7.2 successfully repairs all research integrity vulnerabilities. The false 100% win-rate claim has been corrected to its true 0.0% database reality. Confirmation authority has been unified under `ForwardConfirmationGate`, and the system is operationally verified and ready for independent forward evidence collection.
