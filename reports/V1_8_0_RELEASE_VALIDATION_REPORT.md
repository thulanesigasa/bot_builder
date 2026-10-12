# V1.8.0 Release Validation & Scientific Integrity Report

![Release](https://img.shields.io/badge/Release-V1.8.0-blue.svg)
![Tests](https://img.shields.io/badge/Test_Suite-372_Passed_(100%25)-brightgreen.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)
![Verdict](https://img.shields.io/badge/Final_Verdict-EXPLORATORY_CANDIDATE_IDENTIFIED-yellow.svg)

---

## 1. Executive Summary & Release Authority

Release **V1.8.0** elevates `bot_builder` from a single-market Only Ups / Only Downs research system into a multi-market Deriv Rise/Fall (`CALL` / `PUT`) quantitative edge discovery platform.

The release incorporates:
1. Dynamic Deriv market and capability discovery across all six target synthetic volatility indices.
2. Canonical broker Rise/Fall contract specifications with verified strict inequality equality/tie loss handling.
3. Complete resolution of the three V1.7.4.5 audit issues (Cohort denominator accounting, V0 vs V1 entry mapping discrepancy verification, and empty confirmation cohorts).
4. Market-specific probabilistic modeling with causal rolling features and out-of-sample calibration.
5. Multi-market quote economics based on real Deriv proposal responses ($2.00 stake, $3.91 payout, 51.15% hurdle).
6. 48-hypothesis multiple-testing control under Benjamini-Hochberg False Discovery Rate ($\alpha = 0.05$).
7. Moving-Block Bootstrap (MBB) 95% lower confidence bounds for dependence-aware uncertainty.

---

## 2. Regression Test Suite & Verification Results

The test suite executed with 100% green pass rate:
- **Total Passing Tests**: **372 passed in 73.59s**
- **Legacy Test Suite Preserved**: 349 / 349 passed (100% backwards compatibility)
- **New V1.8.0 Tests Added**: 23 / 23 passed in `tests/test_v180_multi_market_rise_fall.py`

### Test Verification Matrix
| Category | Test Suite Module | Status | Description |
| :--- | :--- | :--- | :--- |
| **Safety Invariants** | `test_v180_multi_market_rise_fall.py` | PASS | Permanent `LIVE_EXECUTION_DISABLED = True`, NO_TRADE policy |
| **Market Discovery** | `test_v180_multi_market_rise_fall.py` | PASS | 6 target symbols (`R_100`, `1HZ100V`, `R_75`, `1HZ75V`, `R_50`, `1HZ50V`), pip precision |
| **Capability Matrix** | `test_v180_multi_market_rise_fall.py` | PASS | Durations 1-10t supported with quotes; 20t rejected as `UNSUPPORTED_CONTRACT_COMBINATION` |
| **Rise/Fall Semantics**| `test_v180_multi_market_rise_fall.py` | PASS | `CALL` strictly higher, `PUT` strictly lower; tie is loss for both |
| **Entry Mapping Audit**| `test_v180_multi_market_rise_fall.py` | PASS | V1 next-tick entry vs V0 signal-tick entry disagreement demonstrated |
| **Issue 4.1 Denominators**| `test_v180_multi_market_rise_fall.py` | PASS | Epochs (887), predictions (1,774), candidates (3,548) reconciled |
| **Issue 4.3 Empty Cohort D**| `test_v180_multi_market_rise_fall.py` | PASS | $N=0$, None metrics, `PREREGISTRATION_REQUIRED` strictly enforced |
| **Market Isolation** | `test_v180_multi_market_rise_fall.py` | PASS | Cross-market quote rejection; feature causality; embargo between splits |
| **Calibration & Brier** | `test_v180_multi_market_rise_fall.py` | PASS | Brier score, BSS, ECE, Log Loss, Logistic model convergence |
| **FDR Multiple Testing** | `test_v180_multi_market_rise_fall.py` | PASS | Benjamini-Hochberg adjustment over 48 hypotheses; MBB EV lower bounds |
| **End-to-End SHADOW** | `test_v180_multi_market_rise_fall.py` | PASS | Complete multi-market integration test across realistic schemas |

---

## 3. Resolution of V1.7.4.5 Audit Issues

### Issue 4.1: Cohort Accounting Denominators
- **Defect**: Previous reports mixed duration-specific predictions and directional candidates.
- **Resolution**: Separated into 7 distinct accounting metrics:
  - Unique decision epochs: 887
  - Duration-specific prediction records: 1,774
  - Direction-specific candidate evaluations: 3,548
  - Unique valid proposal quotes: 1,096
  - Chronological quote matches ($\le 60$s): 1,774 (100.0%)
  - Execution-quality quote matches ($\le 5$s): 1,344 (75.76%)
  - Union (887) and intersection (887) of eligible prediction IDs.

### Issue 4.2: Entry Mapping Verification
- **Defect**: Previous reports claimed no outcome differences between V0 signal-tick and V1 next-tick mappings.
- **Resolution**: Independent verification across 5,000 sequential raw ticks per market revealed that **32.5% to 34.3% of 2-tick contracts and 19.4% to 21.8% of 5-tick contracts produce opposite outcomes**. The previous finding was an artifact of symmetric random walk netting. Exported sample records confirm exact tick sequences and outcome reversals.

### Issue 4.3: Empty Confirmation Cohort
- **Defect**: Previous implementation copied exploratory Cohort C metrics into the Cohort D structure before marking unconfirmed.
- **Resolution**: Replaced with clean uninitialized structure: $N=0$, win rate = None, predicted EV = None, realized return = None, bootstrap bound = None, and verdict = `PREREGISTRATION_REQUIRED_FOR_CONFIRMATION`. Zero exploratory metrics are reused as confirmation evidence.

---

## 4. Final Research Verdict & Confirmation Readiness

In accordance with Section 21 of the specification:
$$\mathbf{FINAL\_RESEARCH\_VERDICT = EXPLORATORY\_CANDIDATE\_IDENTIFIED}$$

Three candidates demonstrate exploratory positive EV with statistically significant MBB 95% lower bounds under Benjamini-Hochberg FDR control ($\alpha = 0.05$):
1. `HYP_R_100_10T_PUT` (Win Rate 53.84%, Realized EV +$0.1050, MBB 95% Bound +$0.0075, $p_{\text{adj}} = 0.0018$)
2. `HYP_1HZ50V_10T_PUT` (Win Rate 54.20%, Realized EV +$0.1192, MBB 95% Bound +$0.0216, $p_{\text{adj}} = 0.0004$)
3. `HYP_1HZ50V_5T_PUT` (Win Rate 53.11%, Realized EV +$0.0766, MBB 95% Bound +$0.0021, $p_{\text{adj}} = 0.0340$)

These candidates are **frozen and confirmation-ready**. They cannot self-promote to confirmed status until evaluated on untouched prospective data collected strictly after strategy registration.

---

*Report certified by the V1.8.0 Release Validation Suite*
