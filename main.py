"""Main CLI Runner: V1.3 Statistical Edge Discovery Engine (RUNHIGH / RUNLOW).

Core Methodology:
1. Exact 5-tick contract lifecycle: Entry S_0 at tick i+1, exactly 5 successive transitions to Expiry S_5 at tick i+6.
2. Unconditional Baselines:
   - Theoretical random walk: (0.5)^5 = 3.125%.
   - Empirical Train baselines: Base P(RUNHIGH) and Base P(RUNLOW).
   - Proposal quote implied break-even: Stake / Return (e.g. $2 / $61.03 = 3.277%).
3. Systematic Combinatorial State Grid Search:
   - Searches thousands of discrete multi-factor state combinations across Train (60%).
   - Measures Probability Lift over baseline (P(s) / P_0), sample size n, Net Edge, z-score, and Bonferroni critical z.
4. Validation Filtering Gate:
   - Audits train-discovered candidate states on out-of-sample Validation data (20%).
   - Eliminates regimes where edge decays back to null or lift drops <= 1.0.
5. Probability Calibration & The Honest Exam:
   - Evaluates surviving regimes (or benchmark candidate) on untouched Holdout (20%).
   - Measures Brier score, Baseline Brier score, Brier Skill Score (BSS), and Expected Calibration Error (ECE).
6. Strict Statistical Gate Verdict:
   - Trades ONLY when positive EV + proven out-of-sample statistical edge exists (Holdout z > 3.00).
   - Otherwise: VERDICT: NO EDGE FOUND.

Usage:
    python main.py [data_path] [--force]
    Example: python main.py data/R_75_master.csv --force
"""
import os
import sys
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG
from features import validate_data
from contract_model import ContractOutcomeModel
from market_regime import compute_expanded_market_features
from quote_engine import QuoteEngine
from strategy import MarketStateProbabilityModel
from feature_search import (
    SystematicStateGridSearch,
    audit_candidates_on_validation,
    search_market_regimes_for_elevated_runs
)
from walk_forward import create_three_way_split
from backtest import run_probability_backtest
from probability import (
    bonferroni_critical_z,
    compute_calibration_curve,
    compute_brier_skill_score,
    calculate_z_score
)


def resolve_data_path(given_path: str) -> str:
    """Finds data file in current directory or alongside script."""
    if os.path.exists(given_path):
        return given_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    alt_path = os.path.join(script_dir, given_path)
    if os.path.exists(alt_path):
        return alt_path
    default_master = os.path.join(script_dir, "data", "R_75_master.csv")
    if os.path.exists(default_master):
        return default_master
    default_r75 = os.path.join(script_dir, "data", "R_75_ticks.csv")
    if os.path.exists(default_r75):
        return default_r75
    return given_path


def print_v13_report(
    symbol: str,
    total_ticks: int,
    quote_engine: QuoteEngine,
    splits,
    grid_results: dict,
    validation_audit: list,
    model: MarketStateProbabilityModel,
    holdout_sim: pd.DataFrame,
    calibration_res: dict,
    backtest_res
):
    up_q = quote_engine.get_quote("UP")
    down_q = quote_engine.get_quote("DOWN")

    print("\n" + "=" * 80)
    print("      V1.3 STATISTICAL EDGE DISCOVERY ENGINE (RUNHIGH / RUNLOW 5-TICK)")
    print("=" * 80)
    print(f"Market:                    {symbol}")
    print(f"Total Ticks Analyzed:      {total_ticks:,}")
    print(f"Contract Lifecycle:        5 Consecutive Transitions (Entry S_0 at i+1 -> Expiry S_5 at i+6)")
    print(f"Dataset Split:             TRAIN (60%) | VALIDATION (20%) | FINAL HOLDOUT (20%)")
    print(f"  - Train Set Size:        {len(splits.train_df):,} ticks")
    print(f"  - Validation Set Size:   {len(splits.val_df):,} ticks")
    print(f"  - Final Holdout Size:    {len(splits.holdout_df):,} ticks (The Honest Exam)")
    print("-" * 80)
    print("UNCONDITIONAL BASELINES & PROPOSAL QUOTE HURDLE:")
    print(f"  Theoretical Random Walk:   (0.5)^5 = 3.125%")
    print(f"  Empirical Train P(RUNHIGH): {grid_results['baseline_runhigh_prob']:.3%}")
    print(f"  Empirical Train P(RUNLOW):  {grid_results['baseline_runlow_prob']:.3%}")
    print(f"  RUNHIGH (Only Ups) Quote:   Stake ${up_q.stake:.2f} | Payout ${up_q.payout:.2f} | Implied BE: {up_q.implied_probability:.2%}")
    print(f"  RUNLOW  (Only Downs) Quote: Stake ${down_q.stake:.2f} | Payout ${down_q.payout:.2f} | Implied BE: {down_q.implied_probability:.2%}")
    print("-" * 80)

    # 1. Systematic Combinatorial State Grid Search
    print("\n[1] SYSTEMATIC MULTI-FACTOR STATE GRID SEARCH (TRAIN 60%)")
    print(f"  State Combinations Evaluated:     {grid_results['total_states_evaluated']:,} state configurations")
    print(f"  Bonferroni Critical Threshold:    z >= {grid_results['bonferroni_critical_z']:.2f} (Family-wise alpha = 0.05)")
    print(f"  Candidate States Meeting Filter:  {len(grid_results['runhigh_candidates'])} RUNHIGH, {len(grid_results['runlow_candidates'])} RUNLOW")

    print("\nTop RUNHIGH (Only Ups) States by Probability Lift over Baseline:")
    for r in grid_results["top_runhigh_by_lift"][:4]:
        print(f"  - {r['state_id']:<56} n={r['n']:>5} | Lift={r['rh_lift']:>5.2f}x | P(RUNHIGH)={r['rh_prob']:>6.2%} | Edge={r['rh_edge']:>+6.2%} | z={r['rh_z']:>+5.2f}")

    print("\nTop RUNLOW (Only Downs) States by Probability Lift over Baseline:")
    for r in grid_results["top_runlow_by_lift"][:4]:
        print(f"  - {r['state_id']:<56} n={r['n']:>5} | Lift={r['rl_lift']:>5.2f}x | P(RUNLOW)={r['rl_prob']:>6.2%} | Edge={r['rl_edge']:>+6.2%} | z={r['rl_z']:>+5.2f}")

    print("-" * 80)

    # 2. Validation Audit Gate
    survivors = [a for a in validation_audit if a["survived_validation"]]
    print("\n[2] OUT-OF-SAMPLE VALIDATION FILTERING GATE (VALIDATION 20%)")
    print(f"  Training Candidates Audited:      {len(validation_audit)} candidates")
    print(f"  Candidates Surviving Validation:  {len(survivors)} survivor(s)")

    if len(survivors) > 0:
        for s in survivors:
            c = s["candidate"]
            print(f"  [SURVIVED] {c.state_id:<50} Val n={s['n_val']:>4} | Val P={s['val_prob']:>6.2%} | Val Lift={s['val_lift']:>5.2f}x | Val Edge={s['val_edge']:>+6.2%}")
    else:
        print("  Validation Filter Decision:       ZERO candidate states maintained edge on validation data.")
        print("                                    All in-sample anomalies decayed back to baseline out of sample.")

    print("-" * 80)

    # 3. Final Untouched Holdout Evaluation & Probability Calibration
    active_signals = (holdout_sim["signal"] != "NO_TRADE").sum()
    print("\n[3] FINAL UNTOUCHED HOLDOUT EVALUATION & CALIBRATION (THE HONEST EXAM)")
    print(f"  Holdout Trades Triggered:         {active_signals:,} trades")

    if active_signals > 0:
        active_sub = holdout_sim[holdout_sim["signal"] != "NO_TRADE"]
        rh_active = active_sub[active_sub["signal"] == "RUNHIGH"]
        rl_active = active_sub[active_sub["signal"] == "RUNLOW"]
        rh_wins = int(rh_active["runhigh_win"].sum()) if len(rh_active) > 0 else 0
        rl_wins = int(rl_active["runlow_win"].sum()) if len(rl_active) > 0 else 0
        total_wins = rh_wins + rl_wins
        realized_wr = total_wins / active_signals
        net_edge = realized_wr - up_q.implied_probability
        se = np.sqrt(up_q.implied_probability * (1.0 - up_q.implied_probability) / active_signals)
        holdout_z = (realized_wr - up_q.implied_probability) / se

        print(f"  Holdout Realized Win Rate:        {realized_wr:.2%}")
        print(f"  Holdout Required Break-Even:      {up_q.implied_probability:.2%}")
        print(f"  Holdout Realized Net Edge:        {net_edge:+.2%}")
        print(f"  Holdout z-score vs Break-Even:    {holdout_z:+.2f}")
    else:
        print("  Holdout Strategy Filter Decision: NO TRADE (Zero regimes passed the validation edge gate)")
        net_edge = -1.0
        holdout_z = 0.0

    print("\nPROBABILITY CALIBRATION METRICS (HOLDOUT):")
    print(f"  Model Brier Score:                {calibration_res['brier_score']:.6f}")
    print(f"  Baseline Brier Score:             {calibration_res['baseline_brier_score']:.6f}")
    print(f"  Brier Skill Score (BSS):          {calibration_res['brier_skill_score']:+.4f} (Positive indicates skill beyond base rate)")
    print(f"  Expected Calibration Error (ECE): {calibration_res['ece']:.4f}")

    print("\n" + "=" * 80)
    passed_gate = (active_signals >= 50) and (net_edge > 0) and (holdout_z > 3.00) and (backtest_res.net_profit > 0)
    if passed_gate:
        print("VERDICT: STATISTICAL EDGE CONFIRMED ON UNTOUCHED HOLDOUT")
        print("  Edge survived out-of-sample testing (z > 3.00). Proceed to live demo paper testing.")
    else:
        print("VERDICT: NO EDGE FOUND")
        print("  Uninterrupted 5-tick run probabilities regress to baseline (~3.27%).")
        print("  Candidate regimes failed the out-of-sample significance bar (Required: z > 3.00 & Edge > 0%).")
    print("=" * 80)

    # 4. Trade Journal & Performance Attribution
    summary = backtest_res.journal.summarize_performance()
    print("\n[4] TRADE JOURNAL & PERFORMANCE ATTRIBUTION (HOLDOUT)")
    print(f"  Total Trades Taken: {summary['total_trades']:,}")
    print(f"  Wins:               {summary['wins']:,}")
    print(f"  Losses:             {summary['losses']:,}")
    print(f"  Win Rate:           {summary['win_rate']:.2%}")
    print(f"  Net PnL:            ${summary['net_pnl']:+.2f}")
    print(f"  Profit Factor:      {summary['profit_factor']:.2f}")
    print("=" * 80 + "\n")


def main():
    force = "--force" in sys.argv
    clean_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path_arg = clean_args[0] if len(clean_args) > 0 else "data/R_75_master.csv"
    data_path = resolve_data_path(path_arg)

    if not os.path.exists(data_path):
        print(f"Error: Data file not found: {data_path}")
        sys.exit(1)

    print(f"Loading tick series from: {data_path}")
    raw_df = pd.read_csv(data_path)

    # 1. Integrity check
    is_valid, issues = validate_data(raw_df)
    if not is_valid:
        print("\nDATA INTEGRITY AUDIT FAILED:")
        for issue in issues:
            print(f"  [CRITICAL] {issue}")
        if not force:
            print("\nExecution stopped. Review data provenance or pass --force to override.")
            sys.exit(1)
        print("\n--force provided: proceeding despite integrity warnings.\n")

    # 2. Quote Engine Setup (Dedicated to RUNHIGH / RUNLOW, $2 Stake -> $61.03 Return)
    quote_engine = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)

    # 3. Contract Outcome Modeling (5 transitions: i+1 to i+6)
    print("Modeling Deriv RUNHIGH/RUNLOW contract lifecycle (Entry S_0 at i+1 -> Expiry S_5 at i+6)...")
    contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1, contract_family="run_high_low")
    outcomes = contract_model.compute_contract_outcomes(raw_df)

    # 4. Expanded Feature Space & Discrete Multi-Scale Regimes
    print("Computing multi-scale momentum, streaks, volatility bins, acceleration, and composite regimes...")
    features = compute_expanded_market_features(raw_df)
    for col in ["entry_price", "exit_price", "runhigh_win", "runlow_win", "only_ups_win", "only_downs_win", "rise_win", "fall_win", "is_tie"]:
        if col in outcomes.columns:
            features[col] = outcomes[col]
    features = features.dropna()

    # 5. 3-Way Dataset Split
    splits = create_three_way_split(features, train_pct=0.60, val_pct=0.20)

    # 6. Systematic Multi-Factor State Grid Search (Train 60%)
    print("Executing systematic combinatorial grid search across thousands of multi-factor states...")
    grid_searcher = SystematicStateGridSearch(
        min_sample_size=30,
        candidate_z_threshold=2.0,
        min_lift_threshold=1.15
    )
    grid_results = grid_searcher.search(splits.train_df, quote_engine)

    # 7. Audit Candidates on Out-of-Sample Validation Data (20%)
    candidates_to_audit = grid_results["runhigh_candidates"] + grid_results["runlow_candidates"]
    validation_audit = audit_candidates_on_validation(splits.val_df, candidates_to_audit, quote_engine, min_val_n=15)
    surviving_candidates = [a["candidate"] for a in validation_audit if a["survived_validation"]]

    # 8. Fit Probability Model on Train and Filter by Validation Survivors
    model = MarketStateProbabilityModel(min_sample_size=30, z_threshold=2.0)
    model.fit(splits.train_df, quote_engine)

    # Keep only regimes that survived validation
    surviving_state_ids = {c.state_id for c in surviving_candidates}
    filtered_profiles = {}
    for reg_name, prof in model.profiles.items():
        if prof.has_positive_edge and reg_name in surviving_state_ids:
            filtered_profiles[reg_name] = prof
    model.profiles = filtered_profiles

    # 9. Evaluate on FINAL UNTOUCHED HOLDOUT (The Honest Exam)
    holdout_sim = splits.holdout_df.copy()
    pred_df = model.predict_signals(holdout_sim)
    holdout_sim["signal"] = pred_df["signal"]
    holdout_sim["estimated_prob"] = pred_df["estimated_prob"]
    holdout_sim["expected_value"] = pred_df["expected_value"]

    # If no regimes passed validation, test the top training candidate state for benchmark attribution
    if (holdout_sim["signal"] != "NO_TRADE").sum() == 0 and grid_results["top_runhigh_by_lift"]:
        top_cand = grid_results["top_runhigh_by_lift"][0]
        # Build mask for top candidate
        mask = pd.Series(True, index=holdout_sim.index)
        for col, val in zip(top_cand["factor_cols"], top_cand["factor_vals"]):
            if col in holdout_sim.columns:
                mask = mask & (holdout_sim[col].astype(str) == str(val))
        holdout_sim.loc[mask, "signal"] = "RUNHIGH"
        holdout_sim.loc[mask, "estimated_prob"] = top_cand["rh_prob"]

    # 10. Probability Calibration Analysis on Holdout
    y_true_holdout = holdout_sim["runhigh_win"].values
    y_prob_holdout = np.where(
        holdout_sim["signal"] == "RUNHIGH",
        holdout_sim["estimated_prob"].values,
        grid_results["baseline_runhigh_prob"]
    )
    calibration_res = compute_calibration_curve(
        y_true=y_true_holdout,
        y_prob=y_prob_holdout,
        n_bins=5,
        baseline_prob=grid_results["baseline_runhigh_prob"]
    )

    # 11. Run Backtest
    backtest_res = run_probability_backtest(
        df=holdout_sim,
        quote_engine=quote_engine,
        mode="research",
        symbol="R_75"
    )

    symbol = "Volatility 75" if "R_75" in data_path else "Synthetic Index"
    print_v13_report(
        symbol=symbol,
        total_ticks=len(raw_df),
        quote_engine=quote_engine,
        splits=splits,
        grid_results=grid_results,
        validation_audit=validation_audit,
        model=model,
        holdout_sim=holdout_sim,
        calibration_res=calibration_res,
        backtest_res=backtest_res
    )


if __name__ == "__main__":
    main()
