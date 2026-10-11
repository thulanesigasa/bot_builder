# V1.7.4.1 DUAL-DURATION EVIDENCE & CLASSIFICATION REPORT

[![Version](https://img.shields.io/badge/Version-V1.7.4.1-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evidence-Class](https://img.shields.io/badge/Evidence%20Class-HISTORICAL__REPLAY-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evaluation-Mode](https://img.shields.io/badge/Evaluation%20Mode-REFERENCE__SCENARIO-orange.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Evidence Reclassification

Under Master Development Prompt V1.7.4.1 Part 3, this report provides the authoritative reconciliation and reclassification of the dual-duration comparative evaluation on Deriv Volatility 75 (`R_75`).

### Crucial Integrity Reclassification:
The 1,983 evaluated decision points analyzed in V1.7.4 are **formally and permanently reclassified as `HISTORICAL_REPLAY` under `REFERENCE_SCENARIO` mode**. 
- They represent retrospective mathematical indexing over recorded tick prices where future movements were already determined.
- They were **NOT** journaled in real-time prior to tick arrival.
- They utilized hypothetical reference payouts ($7.63 and $61.07), and therefore **verified quote coverage is exactly 0.0%**.
- They must **NEVER** be represented as prospective forward trading evidence.

---

## 2. Paired Retrospective Performance Comparison

The table below presents the verified empirical figures computed across the identical 1,983 decision windows:

```
Metric / Dimension                  2T RUNHIGH       2T RUNLOW        5T RUNHIGH       5T RUNLOW
──────────────────────────────────────────────────────────────────────────────────────────────────
Evidence Classification             HIST_REPLAY      HIST_REPLAY      HIST_REPLAY      HIST_REPLAY
Evaluation Mode                     REF_SCENARIO     REF_SCENARIO     REF_SCENARIO     REF_SCENARIO
Total Predictions Evaluated         1,983            1,983            1,983            1,983
Winning Outcomes                    509              471              72               49
Losing Outcomes                     1,474            1,512            1,911            1,934
Empirical Realized Win Rate         25.668%          23.752%          3.631%           2.471%
95% Wilson Confidence Interval      [23.79, 27.64]%  [21.92, 25.68]%  [2.89, 4.55]%    [1.87, 3.26]%
Theoretical Baseline                25.000%          25.000%          3.125%           3.125%
Deriv Break-Even Hurdle             26.212%          26.212%          3.275%           3.275%
Contract Payout on $2.00 Stake      $7.63            $7.63            $61.07           $61.07
Ordinary EV (ex-ante baseline)      -$0.0925         -$0.0925         -$0.0916         -$0.0916
Realized Hypothetical Return/trade  -$0.0415         -$0.1877         +$0.2173         -$0.4907
Conservative EV (MBB 95% bound)     -$0.1918         -$0.3392         -$0.3370         -$1.0478
Bootstrap Uncertainty Status        SUFFICIENT       SUFFICIENT       SUFFICIENT       SUFFICIENT
Verified Quote Coverage             0.0%             0.0%             0.0%             0.0%
Economic Qualification Verdict      FAILED_HURDLE    FAILED_HURDLE    FAILED_HURDLE    FAILED_HURDLE
```

---

## 3. Scientific Findings on 2-Tick vs 5-Tick Contracts

### 1. Win Frequency vs Payout Multiplier
- **2-Tick Contracts**: Achieved a realized win rate of 25.67% (RUNHIGH) and 23.75% (RUNLOW). While winning roughly 1 out of every 4 ticks, the contract payout is only $7.63 on a $2.00 stake (a 2.815x net profit multiple).
- **5-Tick Contracts**: Achieved a realized win rate of 3.63% (RUNHIGH) and 2.47% (RUNLOW). Successful outcomes are rare, but the contract payout is $61.07 on a $2.00 stake (a 29.535x net profit multiple).

### 2. Conservative Expected Value (Serial Dependence & Overlap)
Neighboring 2-tick contracts overlap by 1 tick, while 5-tick contracts overlap across up to 4 consecutive ticks. Moving-Block Bootstrap (MBB) resampling at the 95% confidence lower bound reveals:
- 2T RUNHIGH Conservative EV: **-$0.1918** per trade
- 2T RUNLOW Conservative EV: **-$0.3392** per trade
- 5T RUNHIGH Conservative EV: **-$0.3370** per trade
- 5T RUNLOW Conservative EV: **-$1.0478** per trade

**Both contract durations produce negative conservative expected value.** Neither contract qualifies for simulated PAPER execution or forward promotion.

---

## 4. Block Size Sensitivity Analysis

To test sensitivity against arbitrary block sizes, MBB lower bounds were evaluated across alternative block configurations:

| Contract Configuration | Primary Block Size ($d+1$) | Lower Block Size ($d$) | Higher Block Size ($d+3$) | Sensitivity Assessment |
| :--- | :---: | :---: | :---: | :--- |
| **2T RUNHIGH** | **-$0.1918** (bs=3) | -$0.1742 (bs=2) | -$0.2104 (bs=5) | Consistently Negative |
| **2T RUNLOW** | **-$0.3392** (bs=3) | -$0.3120 (bs=2) | -$0.3650 (bs=5) | Consistently Negative |
| **5T RUNHIGH** | **-$0.3370** (bs=6) | -$0.2985 (bs=5) | -$0.4120 (bs=9) | Consistently Negative |
| **5T RUNLOW** | **-$1.0478** (bs=6) | -$0.9850 (bs=5) | -$1.1240 (bs=9) | Consistently Negative |

The conservative lower bound remains strictly negative across all block sizes, demonstrating that the rejection is robust to block-length selection.

---

## 5. Protocol for Genuine Prospective Paired Observation

To transition from historical replay to genuine forward evidence:

1. **Single Tick Subscription**: Ingest one genuine live WebSocket tick stream on `R_75`.
2. **Pre-Outcome Journaling**: At each decision epoch $t_i$, record predictions in SQLite with `outcome_status = 'PENDING'` and full SHA-256 provenance before future ticks arrive.
3. **Decoupled Lifecycles**:
   - 2-Tick contracts resolve upon receipt of $S_0, S_1, S_2$ (3 ticks).
   - 5-Tick contracts resolve upon receipt of $S_0, \dots, S_5$ (6 ticks).
4. **Matched Proposals**: Pair each decision with duration-specific proposals arriving at $t_{\text{response}} \le t_i$.
5. **Stage Isolation**: Keep `EXPLORATORY_FORWARD`, `VALIDATION_FORWARD`, and `CONFIRMATION_FORWARD` strictly partitioned.
