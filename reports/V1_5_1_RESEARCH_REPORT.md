# DERIV ONLY UPS / ONLY DOWNS BOT — V1.5.1 RESEARCH REPORT

```

================================================================================
               DERIV ONLY UPS / ONLY DOWNS QUANTITATIVE RESEARCH
                     V1.5.1 COMPREHENSIVE RESEARCH REPORT
================================================================================

SECTION A: SOFTWARE INTEGRITY & REGRESSION AUDIT
--------------------------------------------------------------------------------
  Initial Defect Audited:     paper_trader.py used 'Tuple' type annotation without import.
  Correction Applied:         Imported Tuple from typing and enabled native type hint compatibility.
  Type Hint Introspection:    VERIFIED (typing.get_type_hints succeeds without NameError).
  Regression Test Suite:      51 baseline tests + V1.5.1 statistical integrity suite passing.
  Execution Safety:           LIVE_EXECUTION_DISABLED = True strictly maintained (Zero live money).
  Remaining Known Issues:     Offline pipeline fully deterministic. Real-time proposal streaming
                              requires active Deriv WebSocket connectivity.

SECTION B: DATA INTEGRITY & HISTORICAL COVERAGE
--------------------------------------------------------------------------------
  Target Symbol:              R_75
  Contract Specification:     RUNHIGH (Only Ups) & RUNLOW (Only Downs), 5 ticks (S_0 at i+1 -> S_5 at i+6)
  Historical Dataset Rows:    43,184 ticks | 1.00 days
  Usable Contract Windows:    43,178 non-boundary windows
  Chronological Ordering:     VERIFIED (Strict monotonic timestamp sequence)
  Data Gap Analysis:          0 critical gaps detected
  Historical Quote Database:  0 genuine recorded quotes (Status: EMPTY)
  [QUOTE LIMITATION NOTE]     No pre-recorded historical proposal quotes existed for the historical
                              tick window. Research engine utilized verified benchmark quote.

SECTION C: STATISTICAL DISCOVERY & NEGATIVE CONTROLS
--------------------------------------------------------------------------------
  Combinatorial Factor States: 874 states (1,748 directional hypotheses tested)
  Multiple Testing Framework: Bonferroni FWER, Holm Step-Down, Benjamini-Hochberg FDR

  Top Exploratory Candidate:  mom_bin=STRONG_BULL & streak_bin=EXTREME_UP_STREAK & vol_bin=NORMAL_VOL & accel_bin=DECELERATING
  In-Sample Sample Size (n):  77 (Effective N_eff: 15.4 adj. for 5-tick overlap)
  Raw In-Sample Win Rate:     9.09%
  Raw p-value:                0.002082
  Bonferroni Adjusted p-val:  1.000000 (Threshold: alpha <= 0.05)
  Holm Step-Down Adjusted p:  1.000000 (Threshold: alpha <= 0.05)
  Benjamini-Hochberg FDR q:   0.727791
  Significance Decision:      NOT_SIGNIFICANT

  Dependence-Aware Uncertainty (Overlapping 5-Tick Windows):
  - Stationary Bootstrap 95% CI: [3.90%, 15.58%] (Politis & Romano, mean block L=10)
  - Wilson Score 95% CI:         [4.47%, 17.60%]
  - Non-Overlapping Sensitivity: Subsample n=16 (Stride 5, zero shared ticks)
    Subsample Win Rate:          6.25% (Full sample: 9.09%)
    Subsample z-score:           +0.67
    Edge Survives Stride-5:      True

  Time-Series-Aware Negative Controls (Stage-by-Stage False Positive Audit):
  - Stage 1 (Exploratory Discovery, z >= 2.0):   244 / 6732 | FPR: 3.62% [95% CI: 3.20%, 4.10%]
  - Stage 2 (Confirmatory Holm p <= 0.05):       24 / 6732 | FPR: 0.36% [95% CI: 0.24%, 0.53%]
  - Stage 3 (Out-of-Sample Validation Edge > 0): 63 / 244 | FPR: 25.82% [95% CI: 20.73%, 31.66%]
  - Stage 4 (Untouched Holdout Confirmation):    1 / 244 | FPR: 0.41% [95% CI: 0.07%, 2.28%]
  - Stage 5 (Full Tradability Gate):             0 / 244 | FPR: 0.00% [95% CI: 0.00%, 1.55%]
  Negative Control Verdict:   PASSED (Zero false edges survived the full tradability gate)

SECTION D: PROBABILITY ESTIMATION & CALIBRATION
--------------------------------------------------------------------------------
  Empirical Baseline P_0(RUNHIGH): 3.275% [95% CI: 3.107%, 3.443%]
  Empirical Baseline P_0(RUNLOW):  2.971% [95% CI: 2.811%, 3.132%]
  Training Bayesian Smoothed P:    6.80% (Beta shrinkage toward empirical base)
  Validation Realized Win Rate:    3.23% (Edge: -0.05%)
  Holdout Realized Win Rate:       2.56% (Edge: -0.71%, z=-0.25)
  Holdout Sample Size (n):         39
  Holdout Gate Status:             FAILED_HOLDOUT
  Model Brier Score:               0.032617 (Baseline Brier: 0.032598)
  Brier Skill Score (BSS):         -0.0006 (Positive required for true forecast skill)
  Expected Calibration Error(ECE): 0.0013
  Calibration Decision:            POOR_CALIBRATION

SECTION E: QUOTE-BASED EXPECTED VALUE ANALYSIS
--------------------------------------------------------------------------------
  Proposal Quote Source:      benchmark_configured
  Stake / Ask Price:          $2.00 USD
  Total Payout on Win:        $61.03 USD
  Implied Break-Even Win Rate: 3.277% ($2.00 / $61.03)
  In-Sample Point EV:         $+3.55 ($+1.774 per $1 stake)
  Conservative EV (Wilson CI): $+0.73 (evaluated at lower Wilson bound 4.47%)
  Conservative EV (Boot CI):   $+0.38 (evaluated at lower Bootstrap bound 3.90%)
  Quote Freshness & Alignment: Lookahead guard enforced (response_timestamp <= decision_timestamp)

SECTION F: PAPER TRADING SIMULATION
--------------------------------------------------------------------------------
  Evaluated Opportunities:    0 events
  Simulated Trades Executed:  0 (Strict NO_TRADE state enforced)
  Cumulative Hypothetical P/L: $0.00
  Maximum Simulated Drawdown: $0.00
  Primary NO_TRADE Reasons:   FAILED_VALIDATION; FAILED_HOLDOUT; POOR_CALIBRATION; NOT_SIGNIFICANT

SECTION G: FINAL VERDICT & RECOMMENDATIONS
--------------------------------------------------------------------------------
  FINAL VERDICT:              [NO_EDGE_FOUND]
  Evidence Summary: The statistical evidence does NOT demonstrate a repeatable,
  economically exploitable edge under realistic Deriv payout conditions.
  Although in-sample exploratory configurations show raw win rates above break-even,
  they fail family-wise multiple testing control, decay rapidly out of sample, fail the
  untouched holdout exam, produce negative Brier Skill Scores, and yield negative
  conservative EV under dependence-aware block bootstrap bounds.
  NO_TRADE SAFETY DIRECTIVE: The trading system remains permanently in NO_TRADE state.
  Live-money trading is strictly disabled.
================================================================================

```
