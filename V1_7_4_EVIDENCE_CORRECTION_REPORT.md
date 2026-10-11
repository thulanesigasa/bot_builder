# V1.7.4 RESEARCH EVIDENCE CORRECTION & RECONCILIATION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Integrity-Audit](https://img.shields.io/badge/Integrity-Authoritative%20Audit-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evidence-Status](https://img.shields.io/badge/Evidence-Reconciled-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Trading-Status](https://img.shields.io/badge/Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Audit Mandate

In accordance with Master Development Prompt V1.7.4 Part B, this report investigates and resolves conflicting probability statistics, erroneous Expected Value (EV) claims, and illustrative timestamps discovered in prior V1.7.3 forward-evidence documentation.

Target Session Under Audit:
- **Session UUID**: `413bbee4-0291-455a-abbe-60257b547b4b`
- **Market Symbol**: Volatility 75 Index (`R_75`)
- **Execution Mode**: `SHADOW` (Non-trading forward research)
- **Database Source**: `data/forward_predictions.db`
- **Quote Source**: `data/quotes.db`
- **Total Ingested Predictions**: 134 records
- **Complete Reconstructed Outcomes**: 129 records (5 pending at cutoff)

---

## 2. Root Cause Analysis of Probability Discrepancies

### Prior Inconsistent Claims in V1.7.3 Documentation
In earlier V1.7.3 reports, conflicting statistics were presented for the same forward research session:
1. **Earlier Summary Report**: Stated ex-ante model predicted probabilities of **3.277%** for RUNHIGH and **2.978%** for RUNLOW.
2. **Forward Evidence Report**: Stated mean predicted probability of **3.84%** for RUNHIGH and **3.84%** for RUNLOW.

### Database Extraction & Mathematical Reconciliation
An independent programmatic audit was conducted directly on the persisted SQLite records in `data/forward_predictions.db`:

```sql
SELECT 
    AVG(runhigh_pred_prob) AS mean_model_rh,
    AVG(runlow_pred_prob)  AS mean_model_rl,
    AVG(runhigh_win)       AS realized_winrate_rh,
    AVG(runlow_win)        AS realized_winrate_rl,
    COUNT(*)               AS resolved_count
FROM forward_predictions
WHERE session_id = '413bbee4-0291-455a-abbe-60257b547b4b'
  AND outcome_status IN ('RESOLVED', 'OUTCOME_RECONSTRUCTED', 'OUTCOME_VERIFIED');
```

### Exact Reconciled Audit Results

| Metric | RUNHIGH (Only Ups) | RUNLOW (Only Downs) | Calculation Basis | Audit Verdict |
| :--- | :---: | :---: | :--- | :--- |
| **Eligible Records (Denominator)** | 129 | 129 | Fully resolved 5-movement outcomes | Authoritative |
| **Ex-Ante Model Mean Probability** | **3.2773%** (0.032773) | **2.9782%** (0.029782) | Stored `runhigh_pred_prob`, `runlow_pred_prob` | **Authoritative Ground Truth** |
| **Observed Realized Wins** | 5 wins | 5 wins | Confirmed 5-tick monotonic sequences | Authoritative |
| **Realized Win Rate** | **3.8760%** (5 / 129) | **3.8760%** (5 / 129) | Realized sample win frequency | **Source of Error** |
| **Prior Reported "Model Mean"** | 3.84% | 3.84% | Confused realized win rate with model probability | **SUPERSEDED / ERRONEOUS** |

### The Root Cause Identified
The previous report author mistakenly took the realized sample win rate (approximately 3.84% to 3.88%), attributed it symmetrically to both contract directions, and mistakenly labeled it as the "mean predicted probability" of the frozen model. 

The original stored predictions in `data/forward_predictions.db` were NOT modified. The model checksum (`8273d215bf...`) remained intact throughout. The error was purely a retrospective reporting reporting error where ex-post realized frequency was substituted for ex-ante model expectation.

---

## 3. Recalculation of Expected Value & Economic Integrity

### Erroneous Prior EV Claim
In V1.7.3, an ordinary EV of approximately **+$0.345** was reported based on the fabricated 3.84% model probability:
$$\text{Erroneous EV} = 0.0384 \times 61.07 - 2.00 = +\$0.3451$$

### Authoritative Recalculation Using Real Stored Data
Using authoritative equations mandated in Part B Section 4:
$$\text{BreakEven} = \frac{\text{AskPrice}}{\text{TotalPayout}} = \frac{2.00}{61.07} = \mathbf{3.2749\%}$$
$$\text{ExpectedValue} = \text{PredictedProbability} \times \text{TotalPayout} - \text{AskPrice}$$

| Contract Direction | Mean Predicted Prob | Total Payout | Ask Price | Break-Even Hurdle | Real Model Ordinary EV | Erroneous Prior Claim |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RUNHIGH (5T)** | 3.2773% | $61.07 | $2.00 | 3.2749% | **+$0.0014** | +$0.3451 (Superseded) |
| **RUNLOW (5T)** | 2.9782% | $61.07 | $2.00 | 3.2749% | **-$0.1812** | +$0.3451 (Superseded) |

### Key Economic Conclusions
1. The prior claim of **+$0.345** ordinary EV is **formally superseded and retracted**.
2. RUNHIGH's real ex-ante model EV is approximately **+$0.0014** per $2.00 stake (virtually break-even, statistically indistinguishable from zero).
3. RUNLOW's real ex-ante model EV is **-$0.1812** per $2.00 stake (substantially negative).
4. After accounting for dependence-aware uncertainty, conservative EV is negative for both directions.
5. Zero trade authorizations occurred; NO_TRADE was correctly enforced.

---

## 4. Elimination of Illustrative Synthetic Data from Audit Tables

In V1.7.3, Table 7 in `V1_7_3_QUOTE_CHRONOLOGY_AUDIT.md` displayed illustrative timestamps around epoch `1700000025.10` with mock quote IDs `63503254`. These timestamps did not correspond to the actual October 2026 session.

In accordance with Part B Section 5, all illustrative rows have been eliminated from authoritative sections and replaced with actual recorded rows from `data/forward_predictions.db` and `data/quotes.db`.

### Authoritative Stored Evidence Sample (Session 413bbee4)

| Index | Prediction ID | Prediction Epoch (UTC) | Proposal Quote ID | Quote Response Epoch | Quote Age | Chronology Causal Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | `b5653a3f` | 1791730992.00 | `87b6fbfa-af20-1008-22d5-c5326cbd3fb9` | 1791730990.46 | 1.54s | Causal Prior (Valid) |
| **2** | `e35d1364` | 1791730994.00 | `87b6fbfa-af20-1008-22d5-c5326cbd3fb9` | 1791730990.46 | 3.54s | Causal Prior (Valid) |
| **3** | `7c255a31` | 1791730996.00 | `87b6fbfa-af20-1008-22d5-c5326cbd3fb9` | 1791730990.46 | 5.54s | Causal Prior (Valid) |
| **10** | `64a8c22c` | 1791731010.00 | `f6e16b08-b5de-11b0-e103-99ad17589a5d` | 1791731005.70 | 4.30s | Causal Prior (Valid) |
| **50** | `938687d1` | 1791731090.00 | `fbe7007d-3318-4fac-acdc-2d5efb8bf594` | 1791731085.28 | 4.72s | Causal Prior (Valid) |
| **100** | `dc11fb88` | 1791731196.00 | `6e90c046-201a-79d0-7b5a-0038c5cf1e05` | 1791731195.36 | 0.64s | Causal Prior (Valid) |
| **134** | `ceddfbd7` | 1791731264.00 | `792aef66-a8ae-d214-a245-44db089ad8ef` | 1791731262.95 | 1.05s | Causal Prior (Valid) |

---

## 5. Statistical Calibration & Brier Score Audit

| Metric | RUNHIGH (5T) | RUNLOW (5T) | Evaluation Benchmark |
| :--- | :---: | :---: | :--- |
| **Model Brier Score** | 0.037461 | 0.037362 | Lower is better |
| **Reference Baseline Brier Score** | 0.037257 | 0.037257 | Unconditional sample base rate |
| **Brier Skill Score (BSS)** | **-0.00545** | **-0.00281** | Positive indicates outperformance over base rate |
| **Calibration Error (ECE)** | 0.00599 | 0.00898 | Equal probability bins |

### Audit Finding
The negative Brier Skill Scores (-0.00545 for RUNHIGH and -0.00281 for RUNLOW) demonstrate that the 5-tick model does NOT outperform the empirical baseline in forward out-of-sample data. This confirms that the model possessed no validated statistical edge, and the decision gate's refusal to authorize trades was completely justified.
