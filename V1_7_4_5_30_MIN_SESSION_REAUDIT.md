# V1.7.4.5 30-Minute Session Re-Audit: Session 1cc84e31-5e48-4287-b94d-8af7bebb5260

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Session](https://img.shields.io/badge/Session-1cc84e31--5e48--4287--b94d--8af7bebb5260-lightgrey.svg)](https://github.com/thulanesigasa/bot_builder)
[![Duration](https://img.shields.io/badge/Duration-1%2C800s--Paired--SHADOW-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Reconciliation](https://img.shields.io/badge/Reconciliation-100%25--VERIFIED-green.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-lightgrey.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

This report delivers the authoritative, independent forensic re-audit of the 1,800-second live paired forward observation session `1cc84e31-5e48-4287-b94d-8af7bebb5260` conducted on the Deriv Volatility 75 Index (`R_75`).

Every source file, tick sequence, prediction journal row, quote proposal, and outcome resolution event was recalculated directly from persisted databases without modifying original records.

---

## 2. Source File Checksums & Provenance

Before running re-evaluations, SHA-256 checksums of the authoritative persisted artifacts were verified:

| File / Artifact | Path | SHA-256 Checksum | Integrity Status |
| :--- | :--- | :--- | :--- |
| **Raw Live Ticks CSV** | `data/R_75_ticks.csv` | `019318bdf887e49eb72c0c7047fc32d847841fce132cfae8bf664b4c7fcba287` | Authentic |
| **Forward Predictions DB** | `data/forward_predictions.db` | `7ad6500732df37b425b7a701967a33994a34b223fffa1f75355a15ea2cba1c8f` | Authentic |
| **Quotes DB** | `data/quotes.db` | `ad7ea873db8e05cffec99d251bc294c7764dcb96f30d0d82944b207ebaf64ca0` | Authentic |
| **Sessions DB** | `data/sessions.db` | `83907a0c0ad741df74274c4dbbbf26442531d04135eecb7858c8ecb59fb1cead` | Authentic |
| **2-Tick Frozen Model** | `models/M_R_75_2TICK_20261011_120000.json` | `943def871f3a4e6be0380701042ae2341c796cfc39ce151ce20bcb222bbc331d` | Frozen Untouched |
| **5-Tick Frozen Model** | `models/M_R_75_5TICK_20261008_132512.json` | `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a` | Frozen Untouched |

---

## 3. Independent Re-Audit Count Verification

The previous V1.7.4.4 release claims were re-derived from raw database records:

| Audit Quantity | V1.7.4.4 Stated Claim | V1.7.4.5 Verified Fact | Discrepancy | Accounting Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Session Duration** | 1,800 seconds | 1,800.0 seconds | None | Start: `1791785208`, End: `1791787008` |
| **Total Recorded Market Ticks** | 898 ticks | 898 ticks | None | 898 ticks in CSV, 887 decision epochs |
| **Warmup Ticks** | 0 | 0 | None | Full rolling buffer seeded |
| **Decision Epochs** | 887 per duration | 887 per duration | None | Exactly 887 decision points for 2T and 887 for 5T |
| **Duration-Specific Predictions** | 1,774 records | 1,774 records | None | Exactly 887 for 2T + 887 for 5T |
| **Directional Contract Candidates** | 3,548 evaluations | 3,548 evaluations | Clarified | 1,774 decisions * 2 directions = 3,548 candidates |
| **Resolved Outcome Records** | 1,774 records | 1,774 records | None | 887 for 2T + 887 for 5T |
| **Pending / Incomplete Outcomes** | 0 | 0 | None | Zero pending outcomes at session conclusion |
| **Data Gaps** | 0 | 0 | None | Zero data gaps detected ($\Delta t \le 5.0$s across all ticks) |
| **Quotes Linked to Session** | 1,096 quotes | 1,096 quotes | None | Exactly 1,096 proposals collected |
| **Raw Quote Coverage** | 100.0% | 100.0% | None | All 1,774 decisions matched a quote |
| **Execution-Quality Coverage** | 75.8% | 75.76% (1,344/1,774) | Clarified | 1,344 decisions have quote age $\le 5.0$s |

---

## 4. Independent Outcome Reconstruction Audit

Every single prediction record was independently re-evaluated against the raw tick sequence under canonical Deriv broker rules:
- **Total Outcomes Reconstructed**: 1,774 / 1,774 (100.0%)
- **Discrepant Outcomes between Prediction DB and Outcome DB**: 0 (Zero)
- **Discrepant Outcomes between V1.7.4.5 Reconstructed and DB**: 0 (Zero)
- **Reconstruction Status**: 100% Deterministically Verified.

---

## 5. Reconciled Four-Configuration Results for Session 1cc84e31

### 1. 2-Tick RUNHIGH
- **Total Decisions**: 887 | **Resolved**: 887
- **Wins**: 219 | **Losses**: 668 | **Empirical Win Rate**: 24.69%
- **Mean Predicted Probability**: 25.14% | **Break-Even Hurdle**: 26.21%
- **Cohort B (Chrono Quoted, N=887)**: Ex-Ante EV: -$0.0815 | Realized Return: -$0.1187 | MBB 95% Bound: **-$0.3488**
- **Cohort C (Execution Quality, N=671)**: Ex-Ante EV: -$0.0833 | Realized Return: -$0.1349 | MBB 95% Bound: **-$0.3967**
- **Verdict**: `FAILED_ECONOMIC_HURDLE`

### 2. 2-Tick RUNLOW
- **Total Decisions**: 887 | **Resolved**: 887
- **Wins**: 226 | **Losses**: 661 | **Empirical Win Rate**: 25.48%
- **Mean Predicted Probability**: 23.64% | **Break-Even Hurdle**: 26.21%
- **Cohort B (Chrono Quoted, N=887)**: Ex-Ante EV: -$0.1960 | Realized Return: -$0.0585 | MBB 95% Bound: **-$0.2796**
- **Cohort C (Execution Quality, N=687)**: Ex-Ante EV: -$0.1953 | Realized Return: -$0.0441 | MBB 95% Bound: **-$0.2124**
- **Verdict**: `FAILED_ECONOMIC_HURDLE`

### 3. 5-Tick RUNHIGH
- **Total Decisions**: 887 | **Resolved**: 887
- **Wins**: 33 | **Losses**: 854 | **Empirical Win Rate**: 3.72%
- **Mean Predicted Probability**: 3.29% | **Break-Even Hurdle**: 3.28%
- **Cohort B (Chrono Quoted, N=887)**: Ex-Ante EV: +$0.0078 | Realized Return: +$0.2721 | MBB 95% Bound: **-$0.6264**
- **Cohort C (Execution Quality, N=673)**: Ex-Ante EV: +$0.0047 | Realized Return: +$0.0871 | MBB 95% Bound: **-$0.7296**
- **Verdict**: `FAILED_CONSERVATIVE_HURDLE`

### 4. 5-Tick RUNLOW
- **Total Decisions**: 887 | **Resolved**: 887
- **Wins**: 32 | **Losses**: 855 | **Empirical Win Rate**: 3.61%
- **Mean Predicted Probability**: 2.98% | **Break-Even Hurdle**: 3.28%
- **Cohort B (Chrono Quoted, N=887)**: Ex-Ante EV: -$0.1791 | Realized Return: +$0.2032 | MBB 95% Bound: **-$0.8984**
- **Cohort C (Execution Quality, N=677)**: Ex-Ante EV: -$0.1782 | Realized Return: +$0.2520 | MBB 95% Bound: **-$0.8273**
- **Verdict**: `FAILED_ECONOMIC_HURDLE`

---

## 6. Audit Verdict

Across all four contract configurations, under both Cohort B (all chronologically quoted decisions) and Cohort C (strict execution-quality proxy), the Moving-Block Bootstrap 95% conservative lower bound is strictly negative.

Therefore, Session `1cc84e31-5e48-4287-b94d-8af7bebb5260` is conclusively classified as:
**`NO_VALIDATED_POSITIVE_EV_EDGE` (Level 0)**
