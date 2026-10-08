"""Systematic discovery engine for uninterrupted 5-tick RUNHIGH and RUNLOW runs.

Explores thousands of combinatorial market-state configurations across multiple factor dimensions
to discover whether any measurable state exhibits statistically significant probability lift
over the unconditional baseline and survives out-of-sample validation.
"""
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Optional
import itertools
import numpy as np
import pandas as pd

from quote_engine import QuoteEngine
from probability import (
    calculate_confidence_interval,
    calculate_z_score,
    calculate_ev_ci,
    compute_probability_lift,
    compute_absolute_lift,
    calculate_p_value,
    calculate_adjusted_p_value,
    evaluate_significance_status,
    bonferroni_critical_z
)
from strategy import CONTINUATION_SETUPS, REVERSAL_SETUPS, ALL_SETUPS


@dataclass
class SampleSizeConfig:
    min_discovery_samples: int = 50
    min_validation_samples: int = 20
    min_holdout_samples: int = 20


@dataclass
class EdgeCandidateReport:
    symbol: str
    direction: str  # 'RUNHIGH' or 'RUNLOW'
    state: str
    baseline_probability: float
    conditional_probability: float
    lift: float
    absolute_lift: float
    sample_size: int
    validation_probability: Optional[float]
    holdout_probability: Optional[float]
    brier_score: float
    calibration_error: float
    p_value: float
    adjusted_p_value: float
    break_even_probability: float
    expected_value: float
    confidence_interval: Tuple[float, float]
    status: str  # NO_EDGE, LOW_SAMPLE, NOT_SIGNIFICANT, POOR_CALIBRATION, FAILED_VALIDATION, FAILED_HOLDOUT, NEGATIVE_EV, VALIDATED_EDGE


def determine_edge_status(
    sample_size: int,
    adj_p_value: float,
    expected_value: float,
    conditional_prob: float,
    break_even_prob: float,
    calibration_ok: bool,
    validation_survived: bool,
    holdout_survived: bool,
    sample_config: Optional[SampleSizeConfig] = None,
    alpha: float = 0.05
) -> str:
    """Determines the exact scientific edge status across all evaluation gates.
    
    Status precedence:
    1. LOW_SAMPLE (if sample_size < min_discovery_samples)
    2. NOT_SIGNIFICANT (if adj_p_value > alpha)
    3. NEGATIVE_EV (if expected_value <= 0 or conditional_prob <= break_even_prob)
    4. POOR_CALIBRATION (if calibration_ok is False)
    5. FAILED_VALIDATION (if validation_survived is False)
    6. FAILED_HOLDOUT (if holdout_survived is False)
    7. VALIDATED_EDGE (if and only if ALL gates pass!)
    """
    cfg = sample_config or SampleSizeConfig()
    if sample_size < cfg.min_discovery_samples:
        return "LOW_SAMPLE"
    if adj_p_value > alpha:
        return "NOT_SIGNIFICANT"
    if conditional_prob <= break_even_prob or expected_value <= 0:
        return "NEGATIVE_EV"
    if not calibration_ok:
        return "POOR_CALIBRATION"
    if not validation_survived:
        return "FAILED_VALIDATION"
    if not holdout_survived:
        return "FAILED_HOLDOUT"
    return "VALIDATED_EDGE"


@dataclass
class StateCandidate:
    state_id: str
    factor_cols: Tuple[str, ...]
    factor_vals: Tuple[str, ...]
    sample_size: int
    direction: str  # 'RUNHIGH' or 'RUNLOW'
    wins: int
    prob: float
    baseline_prob: float
    lift: float
    implied_prob: float
    edge: float
    z_score: float
    ev: float
    ci_lower: float
    ci_upper: float
    absolute_lift: float = 0.0
    raw_p_value: float = 1.0
    adjusted_p_value: float = 1.0
    significance_status: str = "NOT_SIGNIFICANT"



class SystematicStateGridSearch:
    """Systematically evaluates thousands of market-state combinations across multi-scale factors."""

    FACTORS = [
        "streak_bin",
        "mom_bin",
        "vol_bin",
        "accel_bin",
        "range_bin",
        "net5_bin",
        "mom3_bin"
    ]

    def __init__(
        self,
        min_sample_size: int = 30,
        candidate_z_threshold: float = 2.0,
        min_lift_threshold: float = 1.15,
        sample_config: Optional[SampleSizeConfig] = None,
        alpha: float = 0.05
    ):
        self.sample_config = sample_config or SampleSizeConfig()
        self.min_sample_size = min_sample_size if min_sample_size != 30 else self.sample_config.min_discovery_samples
        self.candidate_z_threshold = candidate_z_threshold
        self.min_lift_threshold = min_lift_threshold
        self.alpha = alpha

    def generate_factor_subsets(self, available_cols: List[str]) -> List[Tuple[str, ...]]:
        """Generates 1-factor, 2-factor, 3-factor, and 4-factor subsets."""
        usable = [c for c in self.FACTORS if c in available_cols]
        subsets: List[Tuple[str, ...]] = []

        # 1-factor subsets
        for c in usable:
            subsets.append((c,))

        # 2-factor subsets (all combinations)
        for pair in itertools.combinations(usable, 2):
            subsets.append(pair)

        # 3-factor subsets (selected high-signal combinations)
        high_signal_triplets = [
            ("mom_bin", "streak_bin", "vol_bin"),
            ("mom_bin", "accel_bin", "vol_bin"),
            ("streak_bin", "vol_bin", "accel_bin"),
            ("range_bin", "streak_bin", "vol_bin"),
            ("range_bin", "mom_bin", "vol_bin"),
            ("net5_bin", "vol_bin", "accel_bin"),
            ("net5_bin", "streak_bin", "vol_bin"),
            ("mom3_bin", "streak_bin", "vol_bin"),
            ("mom3_bin", "accel_bin", "vol_bin"),
        ]
        for triplet in high_signal_triplets:
            if all(c in usable for c in triplet) and triplet not in subsets:
                subsets.append(triplet)

        # 4-factor subsets
        high_signal_quads = [
            ("mom_bin", "streak_bin", "vol_bin", "accel_bin"),
            ("mom_bin", "streak_bin", "vol_bin", "range_bin"),
            ("net5_bin", "streak_bin", "vol_bin", "accel_bin"),
        ]
        for quad in high_signal_quads:
            if all(c in usable for c in quad) and quad not in subsets:
                subsets.append(quad)

        return subsets

    def search(
        self,
        train_df: pd.DataFrame,
        quote_engine: QuoteEngine
    ) -> Dict[str, Any]:
        """Conducts systematic grid search across thousands of state combinations."""
        up_quote = quote_engine.get_quote("UP")
        down_quote = quote_engine.get_quote("DOWN")
        be_up = up_quote.implied_probability if up_quote else 0.0328
        be_down = down_quote.implied_probability if down_quote else 0.0328
        up_stake = up_quote.stake if up_quote else 2.0
        up_payout = up_quote.payout if up_quote else 61.03
        down_stake = down_quote.stake if down_quote else 2.0
        down_payout = down_quote.payout if down_quote else 61.03

        # Unconditional empirical baselines
        base_rh = float(train_df["runhigh_win"].mean())
        base_rl = float(train_df["runlow_win"].mean())

        subsets = self.generate_factor_subsets(list(train_df.columns))
        all_evaluations: List[Dict[str, Any]] = []

        for factor_cols in subsets:
            cols_list = list(factor_cols)
            # Groupby aggregates
            agg = train_df.groupby(cols_list, observed=True).agg(
                n=("runhigh_win", "count"),
                rh_wins=("runhigh_win", "sum"),
                rl_wins=("runlow_win", "sum")
            ).reset_index()

            for _, row in agg.iterrows():
                n = int(row["n"])
                if n < self.min_sample_size:
                    continue

                vals = tuple(str(row[c]) for c in factor_cols)
                state_id = " & ".join(f"{c}={v}" for c, v in zip(factor_cols, vals))

                rh_w = int(row["rh_wins"])
                rh_p = rh_w / n
                rh_lift = compute_probability_lift(rh_p, base_rh)
                rh_abs_lift = compute_absolute_lift(rh_p, base_rh)
                rh_edge = rh_p - be_up
                rh_z = calculate_z_score(rh_p, be_up, n)
                rh_ev, _, _ = quote_engine.calculate_expected_value(rh_p, up_stake, up_payout)
                rh_ci_lo, rh_ci_hi = calculate_confidence_interval(rh_w, n)
                rh_raw_p = calculate_p_value(rh_p, be_up, n)

                rl_w = int(row["rl_wins"])
                rl_p = rl_w / n
                rl_lift = compute_probability_lift(rl_p, base_rl)
                rl_abs_lift = compute_absolute_lift(rl_p, base_rl)
                rl_edge = rl_p - be_down
                rl_z = calculate_z_score(rl_p, be_down, n)
                rl_ev, _, _ = quote_engine.calculate_expected_value(rl_p, down_stake, down_payout)
                rl_ci_lo, rl_ci_hi = calculate_confidence_interval(rl_w, n)
                rl_raw_p = calculate_p_value(rl_p, be_down, n)

                all_evaluations.append({
                    "state_id": state_id,
                    "factor_cols": factor_cols,
                    "factor_vals": vals,
                    "n": n,
                    "rh_wins": rh_w,
                    "rh_prob": rh_p,
                    "rh_lift": rh_lift,
                    "rh_abs_lift": rh_abs_lift,
                    "rh_edge": rh_edge,
                    "rh_z": rh_z,
                    "rh_ev": rh_ev,
                    "rh_ci_low": rh_ci_lo,
                    "rh_ci_high": rh_ci_hi,
                    "rh_raw_p": rh_raw_p,
                    "rl_wins": rl_w,
                    "rl_prob": rl_p,
                    "rl_lift": rl_lift,
                    "rl_abs_lift": rl_abs_lift,
                    "rl_edge": rl_edge,
                    "rl_z": rl_z,
                    "rl_ev": rl_ev,
                    "rl_ci_low": rl_ci_lo,
                    "rl_ci_high": rl_ci_hi,
                    "rl_raw_p": rl_raw_p
                })

        total_states_evaluated = max(1, len(all_evaluations))
        bonferroni_z = bonferroni_critical_z(total_states_evaluated, alpha=self.alpha)

        # Populate adjusted p-values and significance statuses
        rh_candidates = []
        rl_candidates = []

        for r in all_evaluations:
            r["rh_adj_p"] = calculate_adjusted_p_value(r["rh_raw_p"], total_states_evaluated)
            r["rl_adj_p"] = calculate_adjusted_p_value(r["rl_raw_p"], total_states_evaluated)
            r["rh_sig_status"] = evaluate_significance_status(r["rh_raw_p"], r["rh_adj_p"], r["n"], min_samples=self.sample_config.min_discovery_samples, alpha=self.alpha)
            r["rl_sig_status"] = evaluate_significance_status(r["rl_raw_p"], r["rl_adj_p"], r["n"], min_samples=self.sample_config.min_discovery_samples, alpha=self.alpha)

            if r["rh_edge"] > 0 and r["rh_z"] >= self.candidate_z_threshold and r["rh_lift"] >= self.min_lift_threshold:
                rh_candidates.append(StateCandidate(
                    state_id=r["state_id"],
                    factor_cols=r["factor_cols"],
                    factor_vals=r["factor_vals"],
                    sample_size=r["n"],
                    direction="RUNHIGH",
                    wins=r["rh_wins"],
                    prob=r["rh_prob"],
                    baseline_prob=base_rh,
                    lift=r["rh_lift"],
                    implied_prob=be_up,
                    edge=r["rh_edge"],
                    z_score=r["rh_z"],
                    ev=r["rh_ev"],
                    ci_lower=r["rh_ci_low"],
                    ci_upper=r["rh_ci_high"],
                    absolute_lift=r["rh_abs_lift"],
                    raw_p_value=r["rh_raw_p"],
                    adjusted_p_value=r["rh_adj_p"],
                    significance_status=r["rh_sig_status"]
                ))

            if r["rl_edge"] > 0 and r["rl_z"] >= self.candidate_z_threshold and r["rl_lift"] >= self.min_lift_threshold:
                rl_candidates.append(StateCandidate(
                    state_id=r["state_id"],
                    factor_cols=r["factor_cols"],
                    factor_vals=r["factor_vals"],
                    sample_size=r["n"],
                    direction="RUNLOW",
                    wins=r["rl_wins"],
                    prob=r["rl_prob"],
                    baseline_prob=base_rl,
                    lift=r["rl_lift"],
                    implied_prob=be_down,
                    edge=r["rl_edge"],
                    z_score=r["rl_z"],
                    ev=r["rl_ev"],
                    ci_lower=r["rl_ci_low"],
                    ci_upper=r["rl_ci_high"],
                    absolute_lift=r["rl_abs_lift"],
                    raw_p_value=r["rl_raw_p"],
                    adjusted_p_value=r["rl_adj_p"],
                    significance_status=r["rl_sig_status"]
                ))

        # Sort top rankings
        top_rh_by_lift = sorted(all_evaluations, key=lambda x: (x["rh_lift"], x["n"]), reverse=True)[:5]
        top_rh_by_edge = sorted(all_evaluations, key=lambda x: (x["rh_edge"], x["n"]), reverse=True)[:5]
        top_rh_by_z = sorted(all_evaluations, key=lambda x: x["rh_z"], reverse=True)[:5]

        top_rl_by_lift = sorted(all_evaluations, key=lambda x: (x["rl_lift"], x["n"]), reverse=True)[:5]
        top_rl_by_edge = sorted(all_evaluations, key=lambda x: (x["rl_edge"], x["n"]), reverse=True)[:5]
        top_rl_by_z = sorted(all_evaluations, key=lambda x: x["rl_z"], reverse=True)[:5]

        return {
            "total_states_evaluated": total_states_evaluated,
            "bonferroni_critical_z": bonferroni_z,
            "baseline_runhigh_prob": base_rh,
            "baseline_runlow_prob": base_rl,
            "implied_break_even": be_up,
            "all_evaluations": all_evaluations,
            "top_runhigh_by_lift": top_rh_by_lift,
            "top_runhigh_by_edge": top_rh_by_edge,
            "top_runhigh_by_z": top_rh_by_z,
            "top_runlow_by_lift": top_rl_by_lift,
            "top_runlow_by_edge": top_rl_by_edge,
            "top_runlow_by_z": top_rl_by_z,
            "runhigh_candidates": rh_candidates,
            "runlow_candidates": rl_candidates
        }


def audit_candidates_on_validation(
    val_df: pd.DataFrame,
    candidates: List[StateCandidate],
    quote_engine: QuoteEngine,
    min_val_n: int = 20,
    sample_config: Optional[SampleSizeConfig] = None
) -> List[Dict[str, Any]]:
    """Audits train-discovered candidate states against out-of-sample validation data.
    Enforces validation filters: sufficient sample size, lift > 1.0, and edge > 0.
    """
    cfg = sample_config or SampleSizeConfig()
    eff_min_n = min_val_n if min_val_n != 20 else cfg.min_validation_samples

    audit_results: List[Dict[str, Any]] = []
    base_rh = float(val_df["runhigh_win"].mean())
    base_rl = float(val_df["runlow_win"].mean())

    for cand in candidates:
        mask = pd.Series(True, index=val_df.index)
        for col, val in zip(cand.factor_cols, cand.factor_vals):
            if col in val_df.columns:
                mask = mask & (val_df[col].astype(str) == str(val))
            else:
                mask = pd.Series(False, index=val_df.index)
                break

        sub = val_df.loc[mask]
        n_val = len(sub)
        is_rh = (cand.direction == "RUNHIGH")
        win_col = "runhigh_win" if is_rh else "runlow_win"
        quote = quote_engine.get_quote("UP" if is_rh else "DOWN")
        be = quote.implied_probability if quote else 0.0328
        base_rate = base_rh if is_rh else base_rl

        if n_val == 0:
            audit_results.append({
                "candidate": cand,
                "n_val": 0,
                "val_wins": 0,
                "val_prob": 0.0,
                "val_lift": 0.0,
                "val_abs_lift": -base_rate,
                "val_edge": -be,
                "val_z": 0.0,
                "survived_validation": False,
                "status": "LOW_SAMPLE",
                "reason": "zero_validation_samples"
            })
            continue

        wins = int(sub[win_col].sum())
        wr = wins / n_val
        lift = compute_probability_lift(wr, base_rate)
        abs_lift = compute_absolute_lift(wr, base_rate)
        edge = wr - be
        z = calculate_z_score(wr, be, n_val)
        survived = (n_val >= eff_min_n) and (lift > 1.0) and (edge > 0.0)

        status_val = "passed" if survived else ("LOW_SAMPLE" if n_val < eff_min_n else "FAILED_VALIDATION")

        audit_results.append({
            "candidate": cand,
            "n_val": n_val,
            "val_wins": wins,
            "val_prob": wr,
            "val_lift": lift,
            "val_abs_lift": abs_lift,
            "val_edge": edge,
            "val_z": z,
            "survived_validation": survived,
            "status": status_val,
            "reason": "passed" if survived else ("insufficient_samples" if n_val < eff_min_n else "edge_decayed_to_null")
        })

    return audit_results


def build_edge_quality_report(
    candidate: StateCandidate,
    validation_audit_entry: Optional[Dict[str, Any]] = None,
    holdout_entry: Optional[Dict[str, Any]] = None,
    symbol: str = "R_75",
    sample_config: Optional[SampleSizeConfig] = None,
    alpha: float = 0.05
) -> EdgeCandidateReport:
    """Builds a standardized EdgeCandidateReport with full multi-stage gate attribution."""
    cfg = sample_config or SampleSizeConfig()
    val_prob = validation_audit_entry["val_prob"] if validation_audit_entry else None
    val_survived = bool(validation_audit_entry.get("survived_validation", False)) if validation_audit_entry else False

    holdout_prob = holdout_entry.get("holdout_prob") if holdout_entry else None
    holdout_survived = bool(holdout_entry.get("survived_holdout", False)) if holdout_entry else False
    calibration_ok = bool(holdout_entry.get("calibration_ok", False)) if holdout_entry else False
    brier_score = float(holdout_entry.get("brier_score", 0.0)) if holdout_entry else 0.0
    cal_err = float(holdout_entry.get("calibration_error", 0.0)) if holdout_entry else 0.0

    status = determine_edge_status(
        sample_size=candidate.sample_size,
        adj_p_value=candidate.adjusted_p_value,
        expected_value=candidate.ev,
        conditional_prob=candidate.prob,
        break_even_prob=candidate.implied_prob,
        calibration_ok=calibration_ok,
        validation_survived=val_survived,
        holdout_survived=holdout_survived,
        sample_config=cfg,
        alpha=alpha
    )

    return EdgeCandidateReport(
        symbol=symbol,
        direction=candidate.direction,
        state=candidate.state_id,
        baseline_probability=candidate.baseline_prob,
        conditional_probability=candidate.prob,
        lift=candidate.lift,
        absolute_lift=candidate.absolute_lift,
        sample_size=candidate.sample_size,
        validation_probability=val_prob,
        holdout_probability=holdout_prob,
        brier_score=brier_score,
        calibration_error=cal_err,
        p_value=candidate.raw_p_value,
        adjusted_p_value=candidate.adjusted_p_value,
        break_even_probability=candidate.implied_prob,
        expected_value=candidate.ev,
        confidence_interval=(candidate.ci_lower, candidate.ci_upper),
        status=status
    )


# Backward-compatible helper for existing test suites
def search_market_regimes_for_elevated_runs(
    features_df: pd.DataFrame,
    quote_engine: QuoteEngine,
    regime_col: str = "market_regime",
    min_n: int = 50
) -> Dict[str, Any]:
    """Audits discrete market regimes to identify where P(RUNHIGH) or P(RUNLOW) exceeds baseline."""
    base_rh = float(features_df["runhigh_win"].mean())
    base_rl = float(features_df["runlow_win"].mean())

    up_quote = quote_engine.get_quote("UP")
    down_quote = quote_engine.get_quote("DOWN")
    be_up = up_quote.implied_probability if up_quote else 0.0328
    be_down = down_quote.implied_probability if down_quote else 0.0328

    regime_reports = []
    for reg, grp in features_df.groupby(regime_col):
        n = len(grp)
        if n < min_n:
            continue

        rh_w = int(grp["runhigh_win"].sum())
        rh_p = rh_w / n
        rh_z = calculate_z_score(rh_p, be_up, n)
        rh_edge = rh_p - be_up
        rh_ev = (rh_p * up_quote.payout - up_quote.stake) if up_quote else 0.0

        rl_w = int(grp["runlow_win"].sum())
        rl_p = rl_w / n
        rl_z = calculate_z_score(rl_p, be_down, n)
        rl_edge = rl_p - be_down
        rl_ev = (rl_p * down_quote.payout - down_quote.stake) if down_quote else 0.0

        regime_reports.append({
            "regime": reg,
            "n": n,
            "rh_prob": rh_p,
            "rh_edge": rh_edge,
            "rh_z": rh_z,
            "rh_ev": rh_ev,
            "rl_prob": rl_p,
            "rl_edge": rl_edge,
            "rl_z": rl_z,
            "rl_ev": rl_ev
        })

    top_rh = sorted(regime_reports, key=lambda x: x["rh_edge"], reverse=True)[:5]
    top_rl = sorted(regime_reports, key=lambda x: x["rl_edge"], reverse=True)[:5]

    return {
        "baseline_runhigh_prob": base_rh,
        "baseline_runlow_prob": base_rl,
        "implied_break_even": be_up,
        "all_regimes_evaluated": len(regime_reports),
        "top_runhigh_regimes": top_rh,
        "top_runlow_regimes": top_rl
    }


def evaluate_setup_edge(
    features_df: pd.DataFrame,
    condition_mask: pd.Series,
    direction: str,
    quote_engine: QuoteEngine
) -> Dict[str, Any]:
    """Calculates win rate, z-score, edge, and EV against exact direction-specific quote."""
    sub = features_df.loc[condition_mask]
    n = len(sub)
    dir_norm = direction.lower()
    quote = quote_engine.get_quote(dir_norm)

    if quote is None:
        return {
            "n": n,
            "wins": 0,
            "win_rate": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "implied_prob": 0.0,
            "edge": 0.0,
            "z_score": 0.0,
            "ev": 0.0,
            "ev_ci_low": 0.0,
            "ev_ci_high": 0.0
        }

    if dir_norm in ("runhigh", "only_ups", "rise", "up"):
        win_col = "runhigh_win" if "runhigh_win" in sub.columns else ("only_ups_win" if "only_ups_win" in sub.columns else "rise_win")
    else:
        win_col = "runlow_win" if "runlow_win" in sub.columns else ("only_downs_win" if "only_downs_win" in sub.columns else "fall_win")

    if n == 0 or win_col not in sub.columns:
        return {
            "n": 0,
            "wins": 0,
            "win_rate": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "implied_prob": quote.implied_probability,
            "edge": 0.0,
            "z_score": 0.0,
            "ev": 0.0,
            "ev_ci_low": 0.0,
            "ev_ci_high": 0.0
        }

    wins = int(sub[win_col].sum())
    wr = wins / n
    ci_low, ci_high = calculate_confidence_interval(wins, n)
    z = calculate_z_score(wr, quote.implied_probability, n)
    edge = wr - quote.implied_probability
    ev, ev_ci_low, ev_ci_high = calculate_ev_ci(wr, n, quote.payout_ratio, quote.stake)

    return {
        "n": n,
        "wins": wins,
        "win_rate": wr,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "implied_prob": quote.implied_probability,
        "edge": edge,
        "z_score": z,
        "ev": ev,
        "ev_ci_low": ev_ci_low,
        "ev_ci_high": ev_ci_high
    }


def compare_continuation_vs_reversal(
    features_df: pd.DataFrame,
    quote_engine: QuoteEngine
) -> Dict[str, Any]:
    """Scans continuation and reversal setups against RUNHIGH/RUNLOW outcomes."""
    cont_results = []
    for name, (fn, side) in CONTINUATION_SETUPS.items():
        res = evaluate_setup_edge(features_df, fn(features_df), side, quote_engine)
        res["name"] = name
        res["type"] = "continuation"
        res["side"] = side
        cont_results.append(res)

    rev_results = []
    for name, (fn, side) in REVERSAL_SETUPS.items():
        res = evaluate_setup_edge(features_df, fn(features_df), side, quote_engine)
        res["name"] = name
        res["type"] = "reversal"
        res["side"] = side
        rev_results.append(res)

    cont_valid = [r for r in cont_results if r["n"] >= 30]
    rev_valid = [r for r in rev_results if r["n"] >= 30]

    avg_cont_edge = np.mean([r["edge"] for r in cont_valid]) if cont_valid else 0.0
    avg_rev_edge = np.mean([r["edge"] for r in rev_valid]) if rev_valid else 0.0

    return {
        "continuation_setups": cont_results,
        "reversal_setups": rev_results,
        "avg_continuation_edge": avg_cont_edge,
        "avg_reversal_edge": avg_rev_edge,
        "verdict": (
            "CONTINUATION DOMINANT" if avg_cont_edge > avg_rev_edge + 0.005 else
            "REVERSAL DOMINANT" if avg_rev_edge > avg_cont_edge + 0.005 else
            "NO SIGNIFICANT ASYMMETRY (RANDOM WALK)"
        )
    }
