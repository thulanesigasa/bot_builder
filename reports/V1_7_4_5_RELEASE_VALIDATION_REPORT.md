# V1.7.4.5 Release Validation Report

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Tests](https://img.shields.io/badge/Tests-349%20Passing-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evidence--Authority](https://img.shields.io/badge/Evidence--Authority-Verified-green.svg)](https://github.com/thulanesigasa/bot_builder)
[![Contract--Mapping](https://img.shields.io/badge/Contract--Mapping-MAPPING__V1__NEXT__TICK-purple.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety--Status](https://img.shields.io/badge/Safety-LIVE__EXECUTION__DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-lightgrey.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

Release V1.7.4.5 delivers the final scientific integrity, evidence authority, contract mapping, and execution-quality economic research upgrades for the `bot_builder` quantitative research system on the Deriv Volatility 75 Index (`R_75`).

The release addresses the four mandatory prompt objectives:
1. **Prospective Evidence Authority**: Eliminated the timestamp validation defect. All prospective records now require complete, verifiable pre-outcome timestamps ($T_{\text{feat}} \le T_{\text{inf}} \le T_{\text{commit}} < T_{\text{entry}} \le T_{\text{expiry}} \le T_{\text{res}}$). Unverified sessions are strictly classified as `PROSPECTIVE_AUTHORITY_UNVERIFIED`.
2. **Broker-Accurate Contract Mapping**: Formally codified `MAPPING_V1_NEXT_TICK_ENTRY` as the canonical broker mapping ($S_0$ is the first forward tick arriving after contract start). Provenance versioning is stamped on all specs and reconstructed outcomes.
3. **Execution-Quality Quote Economics**: Established four mutually exclusive reporting cohorts (Cohort A: All Resolved, Cohort B: Chrono Quoted $\le 60$s, Cohort C: Execution Quality Proxy $\le 5$s, Cohort D: Independent Confirmation). Reconciled the 75.8% execution-quality coverage (1,344 / 1,774 decisions).
4. **Independent Positive-EV Research & Re-Audit**: Independently verified all 1,774 decisions, 898 ticks, and 1,096 quotes from benchmark session `1cc84e31-5e48-4287-b94d-8af7bebb5260`. Evaluated all hypotheses under conservative Moving-Block Bootstrap bounds. Concluded with evidence-backed verdict `NO_VALIDATED_POSITIVE_EV_EDGE` (Level 0).

---

## 2. Release Provenance & Commit Metadata

- **Base Release**: V1.7.4.4
- **Previously Inspected HEAD Commit**: `23f6df82e9362fd59ff89b522c22d21b8fd09fc2`
- **Target Release**: V1.7.4.5
- **Operating Mode**: `SHADOW` (strictly non-purchasing research)
- **Safety Invariant**: `LIVE_EXECUTION_DISABLED = True` (permanently locked)
- **Market Evaluated**: Deriv Volatility 75 Index (`R_75`)
- **Durations**: 2 Ticks and 5 Ticks (Paired Evaluation)

---

## 3. Modified & Added Files

| File | Status | Description of Changes |
| :--- | :--- | :--- |
| `contract_specification.py` | Modified | Added `ContractEntryMappingVersion` enum (`MAPPING_V1_NEXT_TICK_ENTRY`, `MAPPING_V0_SIGNAL_TICK_ENTRY`), version constants, and `compare_entry_mappings` analysis function. |
| `dual_duration_research.py` | Modified | Added `ResearchCohort` enum, `has_mandatory_chronology` check in `adapt_prediction_record`, 4-cohort metric computation (`cohort_metrics`), and `PROSPECTIVE_AUTHORITY_UNVERIFIED` classification. |
| `tests/test_v1744_schema_repair_and_reconstruction.py` | Modified | Accepted `PROSPECTIVE_AUTHORITY_UNVERIFIED` in authority rejection test. |
| `tests/test_v1745_evidence_authority_and_contract_mapping.py` | Added | 21 new adversarial tests covering missing timestamps, causal inversion, entry mappings, cohort freshness, and full SQLite fixture integration. |
| `data/v1745_session_evidence.json` | Added | Sanitized machine-readable evidence package with all checksums, cohorts, and metrics. |
| `V1_7_4_5_PROSPECTIVE_AUTHORITY_AUDIT.md` | Added | Audit of timestamp fields, clock domains, and causal inequalities. |
| `V1_7_4_5_DERIV_CONTRACT_MAPPING_AUDIT.md` | Added | Audit of official Deriv broker rules, entry tick mapping, and sensitivity. |
| `V1_7_4_5_EXECUTION_QUALITY_ECONOMICS.md` | Added | Economic analysis separated into Cohorts A, B, C, and D. |
| `V1_7_4_5_30_MIN_SESSION_REAUDIT.md` | Added | Forensic re-audit of benchmark session `1cc84e31-5e48-4287-b94d-8af7bebb5260`. |
| `V1_7_4_5_STRATEGY_CONFIRMATION_READINESS.md` | Added | Hypothesis evaluation, cherry-picking audit, and Level 0 verdict. |
| `V1_7_4_5_STATISTICAL_POWER_PLAN.md` | Added | Autocorrelation analysis ($N_{\text{eff}}$) and multi-session power plan. |
| `V1_7_4_5_RELEASE_VALIDATION_REPORT.md` | Added | This validation report. |
| `README.md` | Modified | Updated release version badges, architecture, and documentation (zero emojis). |

---

## 4. Frozen Model Checksum Verification

Both machine learning models remained strictly frozen throughout all integrity audits:

| Model ID | File Path | Expected SHA-256 Checksum | Verified Current SHA-256 | Status |
| :--- | :--- | :--- | :--- | :--- |
| **2-Tick Frozen Model** | `models/M_R_75_2TICK_20261011_120000.json` | `943def871f3a4e6be0380701042ae2341c796cfc39ce151ce20bcb222bbc331d` | `943def871f3a4e6be0380701042ae2341c796cfc39ce151ce20bcb222bbc331d` | Untouched |
| **5-Tick Frozen Model** | `models/M_R_75_5TICK_20261008_132512.json` | `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a` | `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a` | Untouched |

---

## 5. Full Automated Test Results

- **Command**: `python -m pytest -q`
- **Total Test Count**: **349 Passed, 0 Failed, 0 Skipped** (100% Green)
- **Execution Time**: 72.09s
- **Baseline Test Preservation**: All 328 previous tests passed without modification or regression.
- **New Regression Test Coverage**: 21 new adversarial tests added in `test_v1745_evidence_authority_and_contract_mapping.py`.

---

## 6. Permanent Safety Invariant Enforcement

- `LIVE_EXECUTION_DISABLED = True` is declared as a compile-time invariant in `dual_duration_research.py`, `forward_observer.py`, and `model_manager.py`.
- No real-money trade execution endpoints can be accessed.
- Strategy discovery modules cannot override `NO_TRADE`.
- Authoritative verdict remains Level 0 (`NO_VALIDATED_POSITIVE_EV_EDGE`).

---

## 7. Known Remaining Research Limitations

1. **Autocorrelation-Driven Effective Sample Bounds**: Due to serial overlapping of 5-tick contracts, 887 observations provide approximately 267 effective independent samples. Statistical validation of a +0.50% edge requires at least 16,400 observations (~9.2 hours of live ticks).
2. **Single-Session Market Regime**: The 30-minute session `1cc84e31` represents an exploratory regime. Confirmation must await future multi-session collection under an untouched preregistered protocol.
3. **Execution Latency Proxy**: Because real-money trading is permanently prohibited, actual fill prices and latency slippage can only be approximated via live proposal quote streams (`SHADOW_EXECUTION_QUALITY_PROXY`).
