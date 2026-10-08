"""Single Command Master Pipeline: V1.4 EDGE VALIDATION + HISTORICAL EV ENGINE.

Executes the comprehensive, scientifically validated 13-stage research pipeline:
1. Data integrity audit & historical coverage check
2. Exact 5-tick contract window modeling (S_0 at i+1 -> S_5 at i+6)
3. Unconditional empirical baseline calculation (P_0(RUNHIGH), P_0(RUNLOW))
4. Multi-scale feature & discrete state space generation
5. Systematic combinatorial state grid search (Train 60%)
6. Statistical hypothesis testing with Bonferroni multiple-testing control
7. Out-of-sample validation filter audit (Validation 20%)
8. Untouched holdout exam & probability calibration (Holdout 20%)
9. Timestamp-aware quote-outcome joining with lookahead protection
10. True break-even and Expected Value (EV) calculation
11. Final edge ranking with gate-by-gate status attribution
12. Paper trading simulation mode (live/replay evaluation with zero-order execution)
13. Human-readable EDGE RESEARCH REPORT generation

Usage:
    python run_edge_research.py [path_or_symbol] [--all-symbols] [--paper] [--force]
    Example: python run_edge_research.py data/R_75_master.csv
"""
import glob
import os
import sys
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG
from features import validate_data, check_data_coverage, compute_features
from contract_model import ContractOutcomeModel
from market_regime import compute_expanded_market_features
from quote_engine import QuoteEngine, ProposalQuote, QuoteOutcomeJoiner
from strategy import MarketStateProbabilityModel
from feature_search import (
    SystematicStateGridSearch,
    audit_candidates_on_validation,
    build_edge_quality_report,
    SampleSizeConfig,
    EdgeCandidateReport
)
from walk_forward import create_three_way_split, create_purged_three_way_split
from probability import (
    calculate_unconditional_baseline,
    compute_calibration_curve,
    calculate_z_score,
    is_model_calibrated,
    calculate_true_break_even,
    calculate_true_ev,
    calculate_conservative_ev,
    bayesian_smoothed_probability,
    wilson_score_interval,
    calculate_effective_sample_size,
    calculate_fdr_q_values,
    evaluate_significance_status
)
from negative_control import run_negative_control_audit
from backtest import run_probability_backtest
from paper_trader import PaperTrader


def resolve_target_file(target: str) -> str:
    """Finds target data file in current directory or data/."""
    if os.path.isfile(target):
        return target
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, target),
        os.path.join(script_dir, "data", target),
        os.path.join(script_dir, "data", f"{target}.csv"),
        os.path.join(script_dir, "data", f"{target}_ticks.csv"),
        os.path.join(script_dir, "data", f"{target}_master.csv"),
        os.path.join(script_dir, "data", "R_75_master.csv"),
        os.path.join(script_dir, "data", "R_75_ticks.csv"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return target


def run_single_symbol_pipeline(
    csv_path: str,
    quote_engine: Optional[QuoteEngine] = None,
    sample_config: Optional[SampleSizeConfig] = None,
    alpha: float = 0.05,
    force: bool = False,
    run_paper: bool = False
) -> Dict[str, Any]:
    """Runs the complete 13-stage edge validation pipeline on a single symbol dataset."""
    symbol_name = os.path.basename(csv_path).replace("_master.csv", "").replace("_ticks.csv", "").replace(".csv", "")
    df_raw = pd.read_csv(csv_path)

    # 1. Data Integrity & Historical Coverage Audit
    is_valid, issues = validate_data(df_raw)
    coverage = check_data_coverage(df_raw, duration_ticks=5)

    if not is_valid and not force:
        return {
            "symbol": symbol_name,
            "status": "DATA_INTEGRITY_FAILED",
            "issues": issues,
            "coverage": coverage
        }

    # 2. Quote Engine Setup
    if quote_engine is None:
        quote_engine = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)

    up_quote = quote_engine.get_quote("UP")
    down_quote = quote_engine.get_quote("DOWN")
    be_up = up_quote.implied_probability if up_quote else 0.0328
    up_stake = up_quote.stake if up_quote else 2.0
    up_payout = up_quote.payout if up_quote else 61.03
    down_stake = down_quote.stake if down_quote else 2.0
    down_payout = down_quote.payout if down_quote else 61.03

    # 3. Contract Modeling (Exact 5 Transitions: S_0 at i+1 -> S_5 at i+6)
    contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    outcomes = contract_model.compute_contract_outcomes(df_raw)

    # 4. Unconditional Baseline Calculation
    baselines = calculate_unconditional_baseline(outcomes, symbol=symbol_name)
    base_rh = baselines["RUNHIGH"]
    base_rl = baselines["RUNLOW"]

    # 5. Feature Engineering & Multi-Scale Regime Partitioning
    features = compute_expanded_market_features(df_raw)
    for col in ["entry_price", "exit_price", "runhigh_win", "runlow_win", "only_ups_win", "only_downs_win", "rise_win", "fall_win", "is_tie"]:
        if col in outcomes.columns:
            features[col] = outcomes[col]
    features = features.dropna()

    # 6. 3-Way Dataset Split with Boundary Purging (6-tick purge gap prevents boundary window leakage)
    splits = create_purged_three_way_split(features, train_pct=0.60, val_pct=0.20, purge_gap=6)
    train_df, val_df, holdout_df = splits.train_df, splits.val_df, splits.holdout_df

    # 7. Systematic Combinatorial State Grid Search (Train 60%)
    cfg = sample_config or SampleSizeConfig()
    grid_searcher = SystematicStateGridSearch(
        sample_config=cfg,
        candidate_z_threshold=2.0,
        min_lift_threshold=1.15,
        alpha=alpha
    )
    grid_res = grid_searcher.search(train_df, quote_engine)

    # 8. Out-of-Sample Validation Filter Audit (Validation 20%)
    all_candidates = grid_res["runhigh_candidates"] + grid_res["runlow_candidates"]
    val_audits = audit_candidates_on_validation(
        val_df=val_df,
        candidates=all_candidates,
        quote_engine=quote_engine,
        sample_config=cfg
    )
    val_audit_map = {a["candidate"].state_id: a for a in val_audits}
    surviving_candidates = [a["candidate"] for a in val_audits if a["survived_validation"]]

    # 9. Fit Probability Model on Train and Filter by Validation Survivors
    model = MarketStateProbabilityModel(min_sample_size=cfg.min_discovery_samples, z_threshold=2.0)
    model.fit(train_df, quote_engine)

    surviving_ids = {c.state_id for c in surviving_candidates}
    filtered_profiles = {}
    for reg_name, prof in model.profiles.items():
        if prof.has_positive_edge and reg_name in surviving_ids:
            filtered_profiles[reg_name] = prof
    model.profiles = filtered_profiles

    # 10. Untouched Holdout Evaluation & Probability Calibration (Holdout 20%)
    holdout_sim = holdout_df.copy()
    pred_df = model.predict_signals(holdout_sim)
    holdout_sim["signal"] = pred_df["signal"]
    holdout_sim["estimated_prob"] = pred_df["estimated_prob"]
    holdout_sim["expected_value"] = pred_df["expected_value"]

    # Select best candidate state for telemetry attribution
    best_candidate = None
    if grid_res["runhigh_candidates"]:
        best_candidate = sorted(grid_res["runhigh_candidates"], key=lambda c: (c.lift, c.sample_size), reverse=True)[0]
    elif grid_res["top_runhigh_by_lift"]:
        top_eval = grid_res["top_runhigh_by_lift"][0]
        best_candidate = StateCandidate(
            state_id=top_eval["state_id"],
            factor_cols=top_eval["factor_cols"],
            factor_vals=top_eval["factor_vals"],
            sample_size=top_eval["n"],
            direction="RUNHIGH",
            wins=top_eval["rh_wins"],
            prob=top_eval["rh_prob"],
            baseline_prob=base_rh.empirical_prob,
            lift=top_eval["rh_lift"],
            implied_prob=be_up,
            edge=top_eval["rh_edge"],
            z_score=top_eval["rh_z"],
            ev=top_eval["rh_ev"],
            ci_lower=top_eval["rh_ci_low"],
            ci_upper=top_eval["rh_ci_high"],
            absolute_lift=top_eval.get("rh_abs_lift", 0.0)
        )

    # V1.5 Advanced Probability Estimators & Safeguards
    bayesian_prob = 0.0
    wilson_ci = (0.0, 0.0)
    conservative_ev = 0.0
    effective_n = 0.0
    if best_candidate is not None:
        bayesian_prob = bayesian_smoothed_probability(best_candidate.wins, best_candidate.sample_size, baseline_prob=base_rh.empirical_prob)
        wilson_ci = wilson_score_interval(best_candidate.wins, best_candidate.sample_size)
        conservative_ev = calculate_conservative_ev(wilson_ci[0], up_stake, up_payout)
        effective_n = calculate_effective_sample_size(best_candidate.sample_size, duration_ticks=5)

    # Evaluate best candidate on holdout
    holdout_entry = {}
    if best_candidate is not None:
        mask_holdout = pd.Series(True, index=holdout_df.index)
        for c, v in zip(best_candidate.factor_cols, best_candidate.factor_vals):
            if c in holdout_df.columns:
                mask_holdout = mask_holdout & (holdout_df[c].astype(str) == str(v))
            else:
                mask_holdout = pd.Series(False, index=holdout_df.index)
                break
        sub_hold = holdout_df.loc[mask_holdout]
        n_hold = len(sub_hold)
        w_hold = int(sub_hold["runhigh_win"].sum()) if n_hold > 0 else 0
        p_hold = (w_hold / n_hold) if n_hold > 0 else 0.0
        edge_hold = p_hold - be_up
        z_hold = calculate_z_score(p_hold, be_up, n_hold)
        survived_hold = (n_hold >= cfg.min_holdout_samples) and (edge_hold > 0.0) and (z_hold > 3.00)

        # Calibration on holdout
        y_true_hold = holdout_df["runhigh_win"].values
        y_prob_hold = np.where(mask_holdout, best_candidate.prob, base_rh.empirical_prob)
        cal = compute_calibration_curve(y_true_hold, y_prob_hold, n_bins=5, baseline_prob=base_rh.empirical_prob)
        cal_ok = is_model_calibrated(cal, max_ece=0.05, min_bss=0.0)

        holdout_entry = {
            "holdout_n": n_hold,
            "holdout_wins": w_hold,
            "holdout_prob": p_hold,
            "holdout_edge": edge_hold,
            "holdout_z": z_hold,
            "survived_holdout": survived_hold,
            "brier_score": cal["brier_score"],
            "baseline_brier_score": cal["baseline_brier_score"],
            "brier_skill_score": cal["brier_skill_score"],
            "calibration_error": cal["ece"],
            "calibration_ok": cal_ok
        }

    # 11. Build Formal Edge Candidate Report
    edge_report = None
    if best_candidate is not None:
        val_entry = val_audit_map.get(best_candidate.state_id)
        edge_report = build_edge_quality_report(
            candidate=best_candidate,
            validation_audit_entry=val_entry,
            holdout_entry=holdout_entry,
            symbol=symbol_name,
            sample_config=cfg,
            alpha=alpha
        )

    # 12. Timestamp-Aware Quote-Outcome Joining & Backtest
    joined_quotes_df = QuoteOutcomeJoiner.join(
        observations_df=holdout_sim,
        quote_engine=quote_engine,
        symbol=symbol_name
    )

    backtest_res = run_probability_backtest(
        df=holdout_sim,
        quote_engine=quote_engine,
        mode="research",
        symbol=symbol_name
    )

    # 13. Research Negative Control Audit
    neg_control = run_negative_control_audit(
        features_df=train_df,
        quote_engine=quote_engine,
        num_permutations=2,
        sample_config=cfg
    )

    # 14. Paper Trading Mode Simulation (if requested)
    paper_summary = None
    if run_paper:
        paper_trader = PaperTrader(quote_engine=quote_engine, symbol=symbol_name)
        prices_list = df_raw["price"].tolist()
        epochs_list = df_raw["epoch"].tolist() if "epoch" in df_raw.columns else list(range(len(prices_list)))
        for i in range(len(holdout_sim) - 7):
            row = holdout_sim.iloc[i]
            sig = str(row.get("signal", "NO_TRADE"))
            prob_est = float(row.get("estimated_prob", 0.0))
            ep = int(row.get("epoch", epochs_list[i]))
            paper_trader.evaluate_opportunity(
                epoch=ep,
                signal=sig,
                estimated_prob=prob_est,
                is_calibrated=holdout_entry.get("calibration_ok", False),
                is_validated=bool(len(surviving_candidates) > 0),
                is_holdout_passed=holdout_entry.get("survived_holdout", False),
                prices_window=prices_list[i:i + 8],
                signal_idx=0,
                conservative_ev=conservative_ev
            )
        paper_summary = paper_trader.summarize()

    return {
        "symbol": symbol_name,
        "total_ticks": len(df_raw),
        "coverage": coverage,
        "quote_engine": quote_engine,
        "up_quote": up_quote,
        "down_quote": down_quote,
        "base_runhigh": base_rh,
        "base_runlow": base_rl,
        "splits": splits,
        "grid_results": grid_res,
        "validation_audits": val_audits,
        "surviving_candidates": surviving_candidates,
        "holdout_entry": holdout_entry,
        "edge_report": edge_report,
        "joined_quotes_df": joined_quotes_df,
        "backtest_res": backtest_res,
        "paper_summary": paper_summary,
        "negative_control": neg_control,
        "bayesian_prob": bayesian_prob,
        "wilson_ci": wilson_ci,
        "conservative_ev": conservative_ev,
        "effective_n": effective_n,
        "final_status": edge_report.status if edge_report else "NO_EDGE"
    }


def print_edge_research_report(res: Dict[str, Any]):
    """Prints the human-readable EDGE RESEARCH REPORT formatted to the exact user specification."""
    sym = res["symbol"]
    up_q = res["up_quote"]
    base_rh = res["base_runhigh"]
    base_rl = res["base_runlow"]
    edge_rep = res.get("edge_report")
    hold = res.get("holdout_entry", {})
    cov = res.get("coverage", {})
    nc = res.get("negative_control", {})

    print("\n" + "=" * 80)
    print("                     EDGE RESEARCH REPORT (V1.5)")
    print("=" * 80)
    print(f"Symbol:                 {sym}")
    print(f"Contract:               RUNHIGH (Only Ups) & RUNLOW (Only Downs)")
    print(f"Duration:               5 ticks (S_0 at i+1 -> S_5 at i+6, 5 consecutive transitions)")
    print(f"Historical Coverage:    {cov.get('total_ticks', 0):,} ticks | {cov.get('duration_days', 0.0):.2f} days ({cov.get('usable_contract_windows', 0):,} contract windows)")
    if cov.get("warnings"):
        for w in cov["warnings"]:
            print(f"  [COVERAGE WARNING]   {w}")
    print("-" * 80)

    print("Baseline:")
    print(f"  Theoretical Benchmark:   3.125% ((0.5)^5)")
    print(f"  Empirical P(RUNHIGH):    {base_rh.empirical_prob:.3%} [95% CI: {base_rh.ci_lower:.3%}, {base_rh.ci_upper:.3%}] (SE: {base_rh.standard_error:.4f}, n={base_rh.observations:,})")
    print(f"  Empirical P(RUNLOW):     {base_rl.empirical_prob:.3%} [95% CI: {base_rl.ci_lower:.3%}, {base_rl.ci_upper:.3%}] (SE: {base_rl.standard_error:.4f}, n={base_rl.observations:,})")
    print(f"  Live Proposal Hurdle:    {up_q.implied_probability:.3%} (Stake ${up_q.stake:.2f} -> Payout ${up_q.payout:.2f})")
    print("-" * 80)

    if edge_rep is not None:
        print(f"Best Discovered State:  {edge_rep.state}")
        print(f"\nTraining (60% Purged):")
        print(f"  Sample Size (n):      {edge_rep.sample_size:,} (Effective N_eff: {res.get('effective_n', 0.0):.1f} adj. for 5-tick overlap)")
        print(f"  P(RUNHIGH | state):   {edge_rep.conditional_probability:.2%}")
        print(f"  Bayesian Smoothed P:  {res.get('bayesian_prob', 0.0):.2%} (Beta prior shrinkage toward base rate)")
        print(f"  Relative Lift:        {edge_rep.lift:.2f}x over empirical baseline")
        print(f"  Absolute Lift:        {edge_rep.absolute_lift:+.2%}")
        print(f"  Statistical Edge:     {edge_rep.conditional_probability - edge_rep.break_even_probability:+.2%}")
        print(f"  Wilson 95% CI:        [{res.get('wilson_ci', (0.0, 0.0))[0]:.2%}, {res.get('wilson_ci', (0.0, 0.0))[1]:.2%}]")
        print(f"  Wald 95% CI:          [{edge_rep.confidence_interval[0]:.2%}, {edge_rep.confidence_interval[1]:.2%}]")
        print(f"  Raw p-value:          {edge_rep.p_value:.6f}")
        print(f"  Adjusted p-value:     {edge_rep.adjusted_p_value:.6f} (Bonferroni across {res['grid_results']['total_states_evaluated']:,} tests)")
        print(f"  Significance Status:  {evaluate_significance_status(edge_rep.p_value, edge_rep.adjusted_p_value, edge_rep.sample_size)}")

        print(f"\nValidation (20% Purged):")
        val_p = edge_rep.validation_probability
        if val_p is not None:
            val_edge = val_p - edge_rep.break_even_probability
            print(f"  P(RUNHIGH | state):   {val_p:.2%}")
            print(f"  Realized Edge:        {val_edge:+.2%}")
            print(f"  Validation Status:    {'SURVIVED' if val_edge > 0 and val_p > base_rh.empirical_prob else 'FAILED_VALIDATION'}")
        else:
            print("  Validation Status:    ZERO_SAMPLES / FAILED_VALIDATION")

        print(f"\nHoldout (20% - The Honest Exam):")
        hold_p = edge_rep.holdout_probability
        if hold_p is not None:
            print(f"  P(RUNHIGH | state):   {hold_p:.2%}")
            print(f"  Sample Size (n):      {hold.get('holdout_n', 0):,}")
            print(f"  Realized Edge:        {hold.get('holdout_edge', -edge_rep.break_even_probability):+.2%}")
            print(f"  Holdout z-score:      {hold.get('holdout_z', 0.0):+.2f} (Required: z > 3.00)")
            print(f"  Holdout Status:       {'SURVIVED' if hold.get('survived_holdout') else 'FAILED_HOLDOUT'}")
        else:
            print("  Holdout Status:       ZERO_SAMPLES / FAILED_HOLDOUT")

        print(f"\nBreak-even:")
        print(f"  Required Win Rate:    {edge_rep.break_even_probability:.2%}")
        print(f"\nExpected Value Engine:")
        print(f"  Point-Estimate EV:    ${edge_rep.expected_value:+.2f} (${edge_rep.expected_value / up_q.stake:+.3f} per $1 stake)")
        print(f"  Conservative EV:      ${res.get('conservative_ev', 0.0):+.2f} (evaluated at lower 95% CI bound)")

        print(f"\nCalibration:")
        print(f"  Model Brier Score:    {hold.get('brier_score', 0.0):.6f}")
        print(f"  Baseline Brier Score: {hold.get('baseline_brier_score', 0.0):.6f}")
        print(f"  Brier Skill Score:    {hold.get('brier_skill_score', -1.0):+.4f} (Positive required for true forecast skill)")
        print(f"  Calibration ECE:      {hold.get('calibration_error', 1.0):.4f}")
        print(f"  Calibration Status:   {'ACCEPTABLE' if hold.get('calibration_ok') else 'POOR_CALIBRATION'}")

        print(f"\nResearch Negative Controls:")
        print(f"  Permuted False Positives: {nc.get('total_null_validated_edges', 0)} / {nc.get('total_null_candidates_discovered', 0)}")
        print(f"  Empirical Null FPR:       {nc.get('empirical_false_positive_rate', 0.0):.2%}")
        print(f"  Control Gate Status:      {'PASSED (Zero false edges on noise)' if nc.get('passed_negative_control') else 'FAILED'}")

        print(f"\nStatistical Significance:")
        print(f"  Family-wise Threshold: z >= {res['grid_results']['bonferroni_critical_z']:.2f}")
        print(f"  Holistic Status:      {edge_rep.status}")
    else:
        print("Best Discovered State:  NONE (Zero candidate states qualified)")

    print("-" * 80)
    print("Final Status:")
    final_status = res.get("final_status", "NO_EDGE")
    if final_status == "VALIDATED_EDGE":
        print("  STATUS: [VALIDATED_RESEARCH_EDGE]")
        print("  An authentic statistical edge survived discovery, multiple-testing correction,")
        print("  validation gating, holdout examination, probability calibration, and EV filtering.")
        print("  Eligible for DEMO / PAPER mode execution.")
    else:
        print(f"  STATUS: [{final_status}] -> NO EDGE FOUND")
        print("  The statistical evidence does NOT demonstrate an exploitable edge after realistic")
        print("  Deriv payout conditions are applied. The bot will NOT trade (Strict NO_TRADE state).")
    print("=" * 80 + "\n")



def main():
    args = sys.argv[1:]
    force = "--force" in args
    run_paper = "--paper" in args
    all_symbols = "--all-symbols" in args
    clean_args = [a for a in args if not a.startswith("--")]

    if all_symbols:
        # Scan data directory for all master/ticks CSV files
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "data")
        csv_files = sorted(glob.glob(os.path.join(data_dir, "*_ticks.csv")) + glob.glob(os.path.join(data_dir, "*_master.csv")))
        # Exclude duplicate base files if master exists
        seen_syms = set()
        dedup_files = []
        for f in csv_files:
            sym = os.path.basename(f).replace("_master.csv", "").replace("_ticks.csv", "")
            if sym not in seen_syms:
                seen_syms.add(sym)
                dedup_files.append(f)

        print(f"Running multi-symbol edge research across {len(dedup_files)} independent symbol(s)...")
        results_list = []
        for f in dedup_files:
            r = run_single_symbol_pipeline(f, force=force, run_paper=run_paper)
            results_list.append(r)
            if r.get("status") != "DATA_INTEGRITY_FAILED":
                print_edge_research_report(r)

        # Multi-Symbol Master Ranking Table
        print("\n" + "=" * 90)
        print("                    MULTI-SYMBOL RESEARCH SUMMARY RANKINGS")
        print("=" * 90)
        print(f"{'SYMBOL':<14} {'TICKS':>10} {'BASE RUNHIGH':>14} {'BASE RUNLOW':>13} {'TOP STATE STATUS':>22} {'FINAL VERDICT':>14}")
        print("-" * 90)
        for r in results_list:
            if r.get("status") == "DATA_INTEGRITY_FAILED":
                print(f"{r['symbol']:<14} {'FAILED':>10} {'N/A':>14} {'N/A':>13} {'INTEGRITY_FAIL':>22} {'NO_EDGE':>14}")
            else:
                sym = r["symbol"]
                n_t = r["total_ticks"]
                brh = f"{r['base_runhigh'].empirical_prob:.3%}"
                brl = f"{r['base_runlow'].empirical_prob:.3%}"
                st = r.get("final_status", "NO_EDGE")
                verdict = "VALIDATED" if st == "VALIDATED_EDGE" else "NO_EDGE"
                print(f"{sym:<14} {n_t:>10,} {brh:>14} {brl:>13} {st:>22} {verdict:>14}")
        print("=" * 90 + "\n")
        return

    # Single symbol execution
    target_arg = clean_args[0] if len(clean_args) > 0 else "data/R_75_master.csv"
    target_path = resolve_target_file(target_arg)

    if not os.path.exists(target_path):
        print(f"Error: Data file not found: {target_path}")
        sys.exit(1)

    print(f"Executing V1.4 Edge Validation & Historical EV Engine on: {target_path}")
    res = run_single_symbol_pipeline(target_path, force=force, run_paper=run_paper)
    if res.get("status") == "DATA_INTEGRITY_FAILED":
        print("\nDATA INTEGRITY AUDIT FAILED:")
        for issue in res["issues"]:
            print(f"  [CRITICAL] {issue}")
        print("Use --force to override.\n")
        sys.exit(1)

    print_edge_research_report(res)


if __name__ == "__main__":
    main()
