# V1.7.4.2 Release Validation & Audit Report

[![Release](https://img.shields.io/badge/Release-V1.7.4.2-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Baseline Commit](https://img.shields.io/badge/Base%20Commit-d3881e31dbbbcb4934ea1ebfa0257f42e982164e-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Tests Passing](https://img.shields.io/badge/pytest-304%20passed%20(100%25)-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Safety Invariant](https://img.shields.io/badge/Safety-Real--Money%20Trading%20Permanently%20Disabled-0F172A)](https://github.com/thulanesigasa/bot_builder)
[![Quote Economics](https://img.shields.io/badge/Quote%20Economics-Per--Decision%20Ask%20%26%20Payout-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Qualification Gate](https://img.shields.io/badge/Research%20Qualification-Fail--Closed%20Strict-0284C7)](https://github.com/thulanesigasa/bot_builder)
[![Prospective Shadow](https://img.shields.io/badge/Prospective%20Shadow-Paired%202T%20%26%205T%20Verified-0284C7)](https://github.com/thulanesigasa/bot_builder)

---

## Executive Summary

V1.7.4.2 is a surgical quantitative research integrity, economic specification, and prospective observation release for the Deriv Only Ups (`RUNHIGH`) and Only Downs (`RUNLOW`) research system on Volatility 75 (`R_75`).

The release addresses the critical economic-provenance defect identified in prior versions where expected value (EV) in `QUOTE_VERIFIED` mode inadvertently fell back to fixed reference payout parameters. In V1.7.4.2, every verified EV calculation operates strictly over individually matched quote ask prices and total payouts, with zero synthetic substitution. Furthermore, reference scenarios fail-closed into `REFERENCE_SCENARIO_ONLY` and can never receive economic candidate qualification or execution authorization. Finally, genuine prospective paired dual-duration observation is established via `PairedForwardObserver`, enabling concurrent 2-tick and 5-tick forward prediction and pre-outcome journaling over a single live `R_75` tick stream.

---

## Baseline and Provenance Audit

- **Primary Repository**: `https://github.com/thulanesigasa/bot_builder.git`
- **Base Release**: V1.7.4.1
- **Inspected Base Commit**: `d3881e31dbbbcb4934ea1ebfa0257f42e982164e`
- **Target Release**: V1.7.4.2
- **Target Release Commit**: `6c3e02c01f25f5a9989467b40690505ce33eac55`
- **Test Suite Evolution**:
  - Baseline Test Count: **288 passed**
  - New Adversarial & Regression Tests: **+16 passed**
  - Final Test Count: **304 passed** (0 failures, 0 errors, 100% green)
- **Model Artifacts Preserved (Zero Retraining / Zero Weights Mutated)**:
  - 2-Tick Frozen Model: `models/M_R_75_2TICK_20261011_120000.json` (SHA-256: `a9d1872199bcf8e18df04e6c38217f7b243b9c7080a221f582046399c56ca5e0`)
  - 5-Tick Frozen Model: `models/M_R_75_5TICK_20261008_132512.json` (SHA-256: `9558cf41f6ca1701389e6ebda1922c0e768e7ec89f89efec473ecf7344a19ef5`)

---

## Inventory of Modified & Added Files

| File Path | Role in V1.7.4.2 Release | Change Type |
| :--- | :--- | :--- |
| `dual_duration_research.py` | Per-decision quote matching, actual ask/payout EV computation, fail-closed `REFERENCE_SCENARIO_ONLY` gate, realized return moving-block bootstrap | Modified |
| `forward_observer.py` | Added explicit `contract_duration` propagation and implemented `PairedForwardObserver` for concurrent 2T/5T observation on single tick stream | Modified |
| `quote_recorder.py` | Duration-parameterized quote polling (`fetch_single_direction_quote`, `record_quotes_session` with `durations=[2, 5]`) | Modified |
| `forward_collection_service.py` | CLI `--dual-duration` support, `PairedForwardObserver` integration, multi-duration quote background polling loop | Modified |
| `forward_journal.py` | Added `contract_duration` filtering to `get_accuracy_metrics` to ensure cross-duration isolation | Modified |
| `tests/test_v1742_quote_economics_and_paired_shadow.py` | 16 comprehensive regression tests covering Adversarial Tests A-G, variable ask/payout economics, lookahead rejection, fail-closed gates | Added |
| `V1_7_4_2_QUOTE_SPECIFIC_EV_AUDIT.md` | Formal audit of quote-specific economic calculations, 8-dimension matching, break-even distributions, and zero-fallback policy | Added |
| `V1_7_4_2_REFERENCE_QUALIFICATION_AUDIT.md` | Audit of fail-closed qualification taxonomy, decoupling of research candidate status from execution authorization, and adversarial proofs | Added |
| `V1_7_4_2_PROSPECTIVE_DUAL_DURATION_READINESS.md` | Technical verification of single-tick-stream dual-duration observation, pre-outcome journaling, and outcome resolution | Added |
| `V1_7_4_2_RELEASE_VALIDATION_REPORT.md` | Master release validation, test results, packaging verification, safety invariants, and operational roadmap | Added |
| `README.md` | Architecture, badges, dual-duration documentation, and updated test suite verification counts | Modified |

---

## Test Execution Results

### 1. Pre-Modification Baseline Test Run
```text
Platform: Windows-11-10.0.26100-SP0 (Python 3.12.3)
Test Suite: pytest
Result: 288 passed in 58.42s
```

### 2. Post-Modification Full Test Run
```text
Platform: Windows-11-10.0.26100-SP0 (Python 3.12.3)
Test Suite: pytest
Command: python -m pytest -q
Result: 304 passed in 94.98s (100% green)
```

### 3. Detailed Breakdown of New Tests (`tests/test_v1742_quote_economics_and_paired_shadow.py`)

1. `test_adversarial_a_variable_payouts_and_asks_used_in_ev`: Verifies that predictions matched to different quotes compute EV from actual ask and payout values rather than reference constants.
2. `test_adversarial_b_positive_reference_ev_cannot_qualify`: Verifies that hypothetical reference scenarios with positive point-estimate and conservative EV receive `REFERENCE_SCENARIO_ONLY` and cannot be marked economically qualified.
3. `test_adversarial_c_missing_quotes_yield_none_ev`: Verifies that absent quote records in `QUOTE_VERIFIED` mode yield `None` EV, 0.0% coverage, and `INSUFFICIENT_QUOTE_COVERAGE` verdict.
4. `test_adversarial_d_future_quote_rejected_strictly`: Verifies that a quote arriving even 0.001 seconds after decision timestamp is rejected with `response_after_decision`.
5. `test_adversarial_e_cross_duration_quote_mismatch_rejected`: Verifies that supplying a 2-tick quote to a 5-tick prediction is rejected with `duration_mismatch`.
6. `test_adversarial_f_prospective_lifecycle_pre_outcome_journaling`: Verifies that predictions are journaled as `PENDING` prior to future tick arrival and resolve only when full tick window arrives ($S_0 \dots S_2$).
7. `test_adversarial_g_cli_and_service_cannot_issue_live_orders`: Verifies that `LIVE_EXECUTION_DISABLED = True` is invariant across all entrypoints and modules.
8. `test_quote_break_even_probability_distribution`: Validates per-decision break-even calculation $BE_i = Ask_i / Payout_i$ and statistical distribution tracking.
9. `test_wrong_direction_quote_rejected`: Validates rejection of RUNLOW quote matched to RUNHIGH prediction with `direction_mismatch`.
10. `test_wrong_symbol_quote_rejected`: Validates rejection of non-R_75 quote with `symbol_mismatch`.
11. `test_stale_quote_rejected`: Validates rejection of quote older than 60 seconds with `stale_quote`.
12. `test_invalid_quote_prices_rejected`: Validates rejection of negative ask price or ask $\ge$ payout with `invalid_prices`.
13. `test_missing_conservative_bound_blocks_qualification`: Validates that undefined bootstrap lower bound blocks candidate qualification.
14. `test_valid_quote_verified_candidate_qualification`: Validates that a signal satisfying 100% quote match, positive EV, positive conservative EV, and sample threshold receives `QUOTE_VERIFIED_RESEARCH_CANDIDATE`.
15. `test_paired_forward_observer_independent_predictions`: Validates concurrent independent 2T and 5T prediction generation on a single shared tick stream.
16. `test_forward_journal_duration_isolation`: Validates that `ForwardJournal.get_accuracy_metrics(contract_duration=...)` properly isolates 2T from 5T records.

---

## Clean Extraction & Package Verification

A clean distribution archive `bot_builder_v1.7.4.2.zip` was built excluding temporary directories, git metadata, and local state. The archive was extracted into a pristine temporary verification directory and validated independently:

1. **Archive Content Integrity**:
   - Source code files verified.
   - Frozen model artifacts present and bitwise identical:
     - `models/M_R_75_2TICK_20261011_120000.json`
     - `models/M_R_75_5TICK_20261008_132512.json`
   - Canonical dataset present (`data/R_75_master.csv`).
   - All 4 authoritative V1.7.4.2 research reports present.
2. **Clean Extraction Test Suite Execution**:
   - `python -m pytest -q` executed inside clean extraction folder.
   - **Result: 304 passed** (Bitwise reproducible test environment).
3. **Safety Verification in Packaged Code**:
   - `LIVE_EXECUTION_DISABLED = True` verified.
   - Zero real-money API endpoints verified.

---

## Safety Invariant Compliance Audit

| Safety Invariant | Implementation Mechanism | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| Permanent Real-Money Block | Hardcoded `LIVE_EXECUTION_DISABLED = True` in `config.py` and `forward_collection_service.py` | Static code scan + Automated Test G | Verified Compliant |
| Non-Purchasing Paper Decisions | `ForwardDecisionGate` enforces `decision: NO_TRADE` on all prospective ticks | Journal inspection + Unit tests | Verified Compliant |
| Advisory Strategy Discovery | `IS_ADVISORY_ONLY = True` firewall prevents automated promotion | Static scan + Strategy discovery tests | Verified Compliant |
| Anti-Lookahead Timestamping | $t_{\text{resp}} \le t_{\text{dec}}$ strictly checked; no future tolerance | Automated Test D + Per-decision matching | Verified Compliant |
| Cross-Duration Isolation | Strict contract duration matching on quotes and model inference | Automated Test E + Dual-duration engine | Verified Compliant |
| Fail-Closed Qualification | Reference scenarios classified as `REFERENCE_SCENARIO_ONLY`, $EV = None$ on missing quotes | Automated Tests B & C + Dual-duration engine | Verified Compliant |

---

## Known Operational Limitations

1. **Synthetic Index Non-Stationarity**: Deriv Volatility 75 index is generated by a PRNG with changing statistical regimes. Point estimates obtained during short observation windows are subject to sampling variance.
2. **Real Broker Quote Latency**: Live network round-trip time between WebSocket client and Deriv servers typically ranges between 150ms and 450ms. A quote requested concurrently with a signal tick will be valid for subsequent decision ticks once received.
3. **Historical Quote Non-Availability**: Historical tick datasets (e.g., `R_75_master.csv`) do not record synchronous Deriv proposal responses. They are permanently classified as `HISTORICAL_REPLAY` evaluated under `REFERENCE_SCENARIO` mode and can never be upgraded to `QUOTE_VERIFIED`.

---

## Next Operational Step: 30-Minute Paired Prospective SHADOW Session

With V1.7.4.2 verified and packaged, the system is ready for a genuine, prospective, non-purchasing paired SHADOW research session on `R_75`:

```powershell
# Execute 30-minute dual-duration paired forward collection session
python run_forward_session.py `
  --session-id "SHADOW_PAIRED_R75_30MIN_$(Get-Date -Format 'yyyyMMdd_HHmmss')" `
  --duration-minutes 30 `
  --dual-duration `
  --record-quotes `
  --quote-durations 2 5 `
  --symbol R_75
```

### Operational Checklist for Local Execution:
1. Verify active internet connection and Deriv WebSocket reachability.
2. Confirm session runs in `SHADOW` mode (zero purchases).
3. Monitor terminal output for dual 2T and 5T prediction generation and proposal responses.
4. At session completion, verify database integrity using `session_reconciler.py`.
5. Execute `dual_duration_research.py` in `QUOTE_VERIFIED` mode to evaluate genuine per-decision economics.
