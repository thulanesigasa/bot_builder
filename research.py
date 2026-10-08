"""Multi-Symbol Quantitative Research Engine & Statistical Gate Evaluator.
Evaluates all 13 setups across multiple Deriv symbols (R_10, R_25, R_50, R_75, R_100, and 1HZ variants),
producing the master Symbol x Setup cross-sectional table and enforcing gate criteria.

Usage:
    python research.py [file_or_dir] [--force]
    Example: python research.py data/ 0.953
"""
import glob
import os
import sys
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG, get_real_payout
from features import compute_features, validate_data
from strategy import SETUPS
from probability import evaluate_setup, calculate_break_even, bonferroni_critical_z


def run_symbol_evaluation(csv_path: str, payout_ratio: float, force: bool = False):
    symbol_name = os.path.basename(csv_path).replace("_ticks.csv", "").replace(".csv", "")
    df = pd.read_csv(csv_path)

    is_valid, issues = validate_data(df)
    if not is_valid and not force:
        print(f"Skipping {symbol_name}: Data integrity validation failed ({len(issues)} flags). Use --force to override.")
        return None

    f = compute_features(df, duration_ticks=DEFAULT_CONFIG.duration_ticks)
    cut = int(len(f) * DEFAULT_CONFIG.train_split)
    train_df = f.iloc[:cut]
    test_df = f.iloc[cut:]

    results = []
    for name, (fn, side) in SETUPS.items():
        tr = evaluate_setup(train_df, fn(train_df), side, payout_ratio, name)
        te = evaluate_setup(test_df, fn(test_df), side, payout_ratio, name)
        results.append({
            "symbol": symbol_name,
            "setup": name,
            "side": side,
            "train": tr,
            "test": te
        })
    return results


def main():
    args = sys.argv[1:]
    force_mode = "--force" in args
    clean_args = [a for a in args if not a.startswith("--")]

    target = clean_args[0] if len(clean_args) > 0 else "data"
    payout = float(clean_args[1]) if len(clean_args) > 1 else DEFAULT_CONFIG.up_payout_ratio
    be = calculate_break_even(payout)
    k = len(SETUPS)
    crit_z = bonferroni_critical_z(k, alpha=DEFAULT_CONFIG.bonferroni_alpha)

    # Locate CSV files
    if os.path.isdir(target):
        csv_files = sorted(glob.glob(os.path.join(target, "*_ticks.csv")))
    elif os.path.isfile(target):
        csv_files = [target]
    else:
        # Default scan in data directory
        csv_files = sorted(glob.glob("data/*_ticks.csv"))

    if not csv_files:
        print(f"No tick CSV files found in '{target}'. Run collector.py to download datasets.")
        sys.exit(1)

    print(f"Evaluating {len(csv_files)} symbol dataset(s)...")
    all_results = []
    for p in csv_files:
        res = run_symbol_evaluation(p, payout, force=force_mode)
        if res:
            all_results.extend(res)

    if not all_results:
        print("No valid datasets evaluated.")
        sys.exit(1)

    # Master Table: Symbol x Setup
    print("\n" + "=" * 135)
    print("                    MASTER CROSS-SECTIONAL RESEARCH TABLE (SYMBOL x SETUP)")
    print("=" * 135)
    print(f"Payout Ratio: {payout:.3f} | Break-even Win Rate: {be:.2%} | Bonferroni Guard: k={k}, critical z={crit_z:.2f}")
    print("-" * 135)
    hdr = f"{'SYMBOL':10s} {'SETUP':38s} {'TRAIN wr':>9s} | {'TEST n':>7s} {'TEST wr':>8s} {'95% CI':>17s} {'z vs BE':>8s} {'EV / $1 (95% CI)':>26s}"
    print(hdr)
    print("-" * 135)

    passed_candidates = []
    for r in all_results:
        sym = r["symbol"]
        setup = r["setup"]
        tr = r["train"]
        te = r["test"]
        ev_str = f"${te.expected_value:+.3f} [{te.ev_ci_lower:+.3f},{te.ev_ci_upper:+.3f}]"
        print(f"{sym:10s} {setup:38s} {tr.win_rate:8.2%}  | {te.sample_size:7d} {te.win_rate:8.2%} "
              f"[{te.ci_lower:6.2%}, {te.ci_upper:6.2%}] {te.z_score:+7.2f} {ev_str:>26s}")

        if te.z_score > 3.00 and tr.win_rate > be and te.win_rate > be:
            passed_candidates.append(r)
    print("-" * 135)

    # Statistical Gate Check
    print("\n" + "=" * 70)
    print("                     STATISTICAL GATE CHECK")
    print("=" * 70)
    # Check if any setup passed on >= 2 symbols
    setup_pass_counts = {}
    for c in passed_candidates:
        setup_pass_counts[c["setup"]] = setup_pass_counts.get(c["setup"], 0) + 1

    qualified_setups = [s for s, count in setup_pass_counts.items() if count >= 2]

    if qualified_setups:
        print("GATE PASSED: The following setup(s) met all statistical criteria across >= 2 symbols:")
        for s in qualified_setups:
            print(f"  [PASS] {s} (passed on {setup_pass_counts[s]} symbols)")
        print("You may proceed to build trader.py on DEMO account with risk limits.")
    else:
        print("GATE FAILED: NO EDGE FOUND ACROSS TESTED SYMBOLS")
        print("  - Multiple-testing threshold (test z > 3.00) and out-of-sample edge (> 51.2%)")
        print("    were not satisfied across >= 2 symbols.")
        print("  - Do NOT build live or demo trading bots until an authentic edge is verified.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
