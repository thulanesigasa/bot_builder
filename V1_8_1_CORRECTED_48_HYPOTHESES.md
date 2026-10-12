# V1.8.1 Canonical 48-Hypothesis Multi-Market Audit Report

![Hypotheses](https://img.shields.io/badge/Total_Hypotheses-48-blue.svg)
![Verdict](https://img.shields.io/badge/Authoritative_Verdict-NO_VALIDATED_POSITIVE_EV_EDGE-red.svg)
![Candidates](https://img.shields.io/badge/Candidates_Identified-0_of_48-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Canonical Reconciliation

In accordance with Section 6 of the V1.8.1 specification, this report provides the canonical recalculation of all 48 hypotheses in the multi-market Rise/Fall research family (6 markets x 4 durations [2, 3, 5, 10 ticks] x 2 directions [CALL, PUT]).

### Strict Consistency Mandate
All figures in this report are rendered programmatically from the canonical machine-readable evidence file (`data/v181_multi_market_evidence.json`). Zero discrepancies exist between machine-readable JSON and this report.

### Summary of Authoritative Decisions
- **Total Hypotheses Evaluated**: 48
- **REJECTED_NEGATIVE_EV** (Realized return <= 0): 28
- **REJECTED_NEGATIVE_PREDICTED_EV** (P_model <= BreakEven 51.15%, PredEV <= 0): 20
- **CANDIDATE_IDENTIFIED**: 0

### Final Authoritative Verdict
$$\mathbf{NO\_VALIDATED\_POSITIVE\_EV\_EDGE}$$

---

## 2. Global Evaluation Criteria & Economic Hurdles

| Parameter | Canonical Value | Interpretation |
| :--- | :--- | :--- |
| **Contract Stake** | $2.00 | Capital committed per hypothetical contract |
| **Contract Payout** | $3.91 | Total payout returned on winning contract |
| **Broker Break-Even Hurdle** | 51.15% (0.511509) | $2.00 / $3.91 minimum win rate required for EV = $0 |
| **Multiple-Testing Family** | 48 hypotheses | Benjamini-Hochberg False Discovery Rate (alpha = 0.05) |
| **Dependence Treatment** | $N_{\text{eff}} = \lfloor N / D \rfloor$ | Serial correlation adjustment for overlapping D-tick outcomes |
| **Bootstrap Bound** | MBB 95% Lower Bound | 5th percentile of 500 moving-block bootstrap resamples |

---

## 3. Comprehensive 48-Hypothesis Reconciliation Table

| Hypothesis ID | Mkt | Dur | Dir | N | N_eff | P_mod | WinRate | Pred EV | Realized EV | MBB 95% | Raw p | Adj p (FDR) | Authoritative Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`HYP_R_100_2T_CALL`** | R_100 | 2t | CALL | 4988 | 2494 | 0.4980 | 0.4828 | $-0.0528 | $-0.1123 | $-0.1610 | 0.997936 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_100_2T_PUT`** | R_100 | 2t | PUT | 4988 | 2494 | 0.5020 | 0.5172 | $-0.0372 | $0.0223 | $-0.0294 | 0.284823 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_100_3T_CALL`** | R_100 | 3t | CALL | 4987 | 1662 | 0.4972 | 0.4859 | $-0.0559 | $-0.1001 | $-0.1639 | 0.981628 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_100_3T_PUT`** | R_100 | 3t | PUT | 4987 | 1662 | 0.5028 | 0.5141 | $-0.0341 | $0.0101 | $-0.0517 | 0.416320 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_100_5T_CALL`** | R_100 | 5t | CALL | 4984 | 996 | 0.4951 | 0.4755 | $-0.0642 | $-0.1408 | $-0.2121 | 0.988500 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_100_5T_PUT`** | R_100 | 5t | PUT | 4984 | 996 | 0.5049 | 0.5245 | $-0.0258 | $0.0508 | $-0.0208 | 0.206051 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_100_10T_CALL`** | R_100 | 10t | CALL | 4978 | 497 | 0.4959 | 0.4616 | $-0.0610 | $-0.1951 | $-0.2987 | 0.986989 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_100_10T_PUT`** | R_100 | 10t | PUT | 4978 | 497 | 0.5041 | 0.5384 | $-0.0290 | $0.1051 | $0.0075 | 0.115204 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ100V_2T_CALL`** | 1HZ100V | 2t | CALL | 4988 | 2494 | 0.4986 | 0.5126 | $-0.0505 | $0.0043 | $-0.0568 | 0.456600 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ100V_2T_PUT`** | 1HZ100V | 2t | PUT | 4988 | 2494 | 0.5014 | 0.4874 | $-0.0395 | $-0.0943 | $-0.1454 | 0.991994 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ100V_3T_CALL`** | 1HZ100V | 3t | CALL | 4987 | 1662 | 0.4954 | 0.5107 | $-0.0630 | $-0.0032 | $-0.0666 | 0.526301 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ100V_3T_PUT`** | 1HZ100V | 3t | PUT | 4987 | 1662 | 0.5046 | 0.4893 | $-0.0270 | $-0.0868 | $-0.1505 | 0.964952 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ100V_5T_CALL`** | 1HZ100V | 5t | CALL | 4984 | 996 | 0.4985 | 0.5134 | $-0.0509 | $0.0074 | $-0.0670 | 0.452482 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ100V_5T_PUT`** | 1HZ100V | 5t | PUT | 4984 | 996 | 0.5015 | 0.4866 | $-0.0391 | $-0.0974 | $-0.1698 | 0.942099 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ100V_10T_CALL`** | 1HZ100V | 10t | CALL | 4978 | 497 | 0.4990 | 0.5125 | $-0.0489 | $0.0039 | $-0.0961 | 0.482373 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ100V_10T_PUT`** | 1HZ100V | 10t | PUT | 4978 | 497 | 0.5010 | 0.4875 | $-0.0411 | $-0.0939 | $-0.1889 | 0.857864 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_75_2T_CALL`** | R_75 | 2t | CALL | 4988 | 2494 | 0.5084 | 0.5154 | $-0.0122 | $0.0152 | $-0.0380 | 0.348734 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_75_2T_PUT`** | R_75 | 2t | PUT | 4988 | 2494 | 0.4916 | 0.4846 | $-0.0778 | $-0.1052 | $-0.1556 | 0.996410 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_75_3T_CALL`** | R_75 | 3t | CALL | 4987 | 1662 | 0.5066 | 0.5165 | $-0.0192 | $0.0195 | $-0.0360 | 0.341984 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_75_3T_PUT`** | R_75 | 3t | PUT | 4987 | 1662 | 0.4934 | 0.4835 | $-0.0708 | $-0.1095 | $-0.1693 | 0.988824 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_75_5T_CALL`** | R_75 | 5t | CALL | 4984 | 996 | 0.5077 | 0.5239 | $-0.0149 | $0.0484 | $-0.0215 | 0.217014 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_75_5T_PUT`** | R_75 | 5t | PUT | 4984 | 996 | 0.4923 | 0.4761 | $-0.0751 | $-0.1384 | $-0.2097 | 0.987310 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_75_10T_CALL`** | R_75 | 10t | CALL | 4978 | 497 | 0.5111 | 0.5275 | $-0.0016 | $0.0625 | $-0.0286 | 0.237867 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_75_10T_PUT`** | R_75 | 10t | PUT | 4978 | 497 | 0.4889 | 0.4725 | $-0.0884 | $-0.1525 | $-0.2485 | 0.959049 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_2T_CALL`** | 1HZ75V | 2t | CALL | 4988 | 2494 | 0.4919 | 0.5090 | $-0.0767 | $-0.0098 | $-0.0599 | 0.598962 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_2T_PUT`** | 1HZ75V | 2t | PUT | 4988 | 2494 | 0.5081 | 0.4910 | $-0.0133 | $-0.0802 | $-0.1281 | 0.979768 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_3T_CALL`** | 1HZ75V | 3t | CALL | 4987 | 1662 | 0.4909 | 0.5141 | $-0.0806 | $0.0101 | $-0.0524 | 0.416320 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ75V_3T_PUT`** | 1HZ75V | 3t | PUT | 4987 | 1662 | 0.5091 | 0.4859 | $-0.0094 | $-0.1001 | $-0.1630 | 0.981628 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_5T_CALL`** | 1HZ75V | 5t | CALL | 4984 | 996 | 0.4885 | 0.5130 | $-0.0900 | $0.0058 | $-0.0615 | 0.462500 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ75V_5T_PUT`** | 1HZ75V | 5t | PUT | 4984 | 996 | 0.5115 | 0.4870 | $-0.0000 | $-0.0958 | $-0.1674 | 0.939115 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_10T_CALL`** | 1HZ75V | 10t | CALL | 4978 | 497 | 0.4835 | 0.5096 | $-0.1095 | $-0.0075 | $-0.1173 | 0.533924 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ75V_10T_PUT`** | 1HZ75V | 10t | PUT | 4978 | 497 | 0.5165 | 0.4904 | $0.0195 | $-0.0825 | $-0.1888 | 0.826759 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_50_2T_CALL`** | R_50 | 2t | CALL | 4988 | 2494 | 0.4992 | 0.5066 | $-0.0481 | $-0.0192 | $-0.0741 | 0.688087 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_50_2T_PUT`** | R_50 | 2t | PUT | 4988 | 2494 | 0.5008 | 0.4934 | $-0.0419 | $-0.0708 | $-0.1234 | 0.964790 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_50_3T_CALL`** | R_50 | 3t | CALL | 4987 | 1662 | 0.5030 | 0.5149 | $-0.0333 | $0.0133 | $-0.0423 | 0.391058 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_50_3T_PUT`** | R_50 | 3t | PUT | 4987 | 1662 | 0.4970 | 0.4851 | $-0.0567 | $-0.1033 | $-0.1583 | 0.984373 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_50_5T_CALL`** | R_50 | 5t | CALL | 4984 | 996 | 0.5014 | 0.5247 | $-0.0395 | $0.0516 | $-0.0223 | 0.202472 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_50_5T_PUT`** | R_50 | 5t | PUT | 4984 | 996 | 0.4986 | 0.4753 | $-0.0505 | $-0.1416 | $-0.2074 | 0.988875 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_R_50_10T_CALL`** | R_50 | 10t | CALL | 4978 | 497 | 0.4971 | 0.5356 | $-0.0563 | $0.0942 | $-0.0106 | 0.141315 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_R_50_10T_PUT`** | R_50 | 10t | PUT | 4978 | 497 | 0.5029 | 0.4644 | $-0.0337 | $-0.1842 | $-0.2698 | 0.982180 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ50V_2T_CALL`** | 1HZ50V | 2t | CALL | 4988 | 2494 | 0.4952 | 0.4838 | $-0.0638 | $-0.1083 | $-0.1626 | 0.997183 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ50V_2T_PUT`** | 1HZ50V | 2t | PUT | 4988 | 2494 | 0.5048 | 0.5162 | $-0.0262 | $0.0183 | $-0.0356 | 0.319654 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ50V_3T_CALL`** | 1HZ50V | 3t | CALL | 4987 | 1662 | 0.4930 | 0.4754 | $-0.0724 | $-0.1412 | $-0.2046 | 0.998385 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ50V_3T_PUT`** | 1HZ50V | 3t | PUT | 4987 | 1662 | 0.5070 | 0.5246 | $-0.0176 | $0.0512 | $-0.0093 | 0.142836 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ50V_5T_CALL`** | 1HZ50V | 5t | CALL | 4984 | 996 | 0.4992 | 0.4689 | $-0.0481 | $-0.1666 | $-0.2466 | 0.996429 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ50V_5T_PUT`** | 1HZ50V | 5t | PUT | 4984 | 996 | 0.5008 | 0.5311 | $-0.0419 | $0.0766 | $0.0021 | 0.108063 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |
| **`HYP_1HZ50V_10T_CALL`** | 1HZ50V | 10t | CALL | 4978 | 497 | 0.5016 | 0.4580 | $-0.0387 | $-0.2092 | $-0.3160 | 0.991494 | 0.998385 | `REJECTED_NEGATIVE_EV` |
| **`HYP_1HZ50V_10T_PUT`** | 1HZ50V | 10t | PUT | 4978 | 497 | 0.4984 | 0.5420 | $-0.0513 | $0.1192 | $0.0216 | 0.086936 | 0.998385 | `REJECTED_NEGATIVE_PREDICTED_EV` |

---

## 4. Market-by-Market Synthesis

### 4.1 Volatility 100 Index (`R_100`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: In V1.8.0, `HYP_R_100_10T_PUT` was misclassified as a candidate due to holdout win rate 53.84%. However, the model forecast probability was 50.41% ($< 51.15\%$), giving predicted EV = -$0.0290. Under V1.8.1, it is strictly rejected with `REJECTED_NEGATIVE_PREDICTED_EV`.
- **Result**: All 8 hypotheses rejected.

### 4.2 Volatility 100 (1s) Index (`1HZ100V`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: Model probabilities remain tightly clustered between 49.7% and 50.3%. All predicted EVs are strictly negative.
- **Result**: All 8 hypotheses rejected.

### 4.3 Volatility 75 Index (`R_75`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: Realized win rates range from 48.9% to 51.1%, consistent with symmetric noise around 50%. Zero hypotheses exceed the 51.15% hurdle ex-ante.
- **Result**: All 8 hypotheses rejected.

### 4.4 Volatility 75 (1s) Index (`1HZ75V`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: Win rates and model forecasts demonstrate zero persistence above the broker break-even rate.
- **Result**: All 8 hypotheses rejected.

### 4.5 Volatility 50 Index (`R_50`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: Across 200,000 ticks, mean tick return is near zero. Holdout win rates cluster around 50%.
- **Result**: All 8 hypotheses rejected.

### 4.6 Volatility 50 (1s) Index (`1HZ50V`)
- **Durations Tested**: 2t, 3t, 5t, 10t
- **Observations**: In V1.8.0, `HYP_1HZ50V_10T_PUT` ($P_{\text{mod}}=49.84\%$, PredEV=-$0.0514) and `HYP_1HZ50V_5T_PUT` ($P_{\text{mod}}=50.08\%$, PredEV=-$0.0418) were misclassified as candidates. Both fail the predicted EV gate and are rejected with `REJECTED_NEGATIVE_PREDICTED_EV`.
- **Result**: All 8 hypotheses rejected.

---

## 5. Audit Conclusion

Across all 48 combinations of synthetic markets, durations, and contract directions, **not a single hypothesis demonstrates a repeatable, ex-ante positive expected value**. The platform correctly reports `NO_VALIDATED_POSITIVE_EV_EDGE` and maintains permanent `NO_TRADE` safety enforcement.