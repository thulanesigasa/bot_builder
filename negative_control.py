"""Research Negative Control Engine for Deriv 5-Tick RUNHIGH / RUNLOW (V1.5.1).

Evaluates whether the edge discovery engine can distinguish genuine predictive signal
from noise by subjecting the discovery pipeline to time-series-aware negative controls:
1. Permuted / randomized market-state factor labels (breaks state-to-outcome mapping).
2. Circular shifts (rolls outcomes relative to states by random offset tau, perfectly
   preserving exact time-series autocorrelation, volatility clustering, and run-lengths).
3. Stationary block-shuffled price increments (preserves local volatility and variance distribution).

CRITICAL V1.5.1 METHODOLOGICAL DISTINCTION:
Disentangles exploratory candidate discovery (Stage 1) from confirmatory significance (Stage 2),
out-of-sample validation survival (Stage 3), untouched holdout confirmation (Stage 4), and
the full tradability gate (Stage 5).

Calculates empirical False Positive Rates (FPR) with Wilson score 95% confidence intervals
at EACH stage separately. Under proper statistical controls, zero false-positive edges
should survive the full tradability gate.
"""
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

from quote_engine import QuoteEngine
from contract_model import ContractOutcomeModel
from feature_search import (
    SystematicStateGridSearch,
    audit_candidates_on_validation,
    SampleSizeConfig,
    StateCandidate
)
from walk_forward import create_purged_three_way_split
from probability import (
    wilson_score_ci,
    calculate_z_score,
    calculate_adjusted_p_value,
    calculate_holm_adjusted_p,
    calculate_conservative_ev,
    compute_calibration_curve,
    is_model_calibrated
)


def generate_permuted_state_series(
    features_df: pd.DataFrame,
    random_seed: int = 42
) -> pd.DataFrame:
    """Randomly permutes market state features while keeping outcomes in place.
    Breaks any causal or predictive connection between observable state and outcome,
    while preserving the exact marginal frequencies of states and outcomes.
    """
    rng = np.random.default_rng(random_seed)
    df_null = features_df.copy()

    state_cols = [c for c in df_null.columns if c.endswith("_bin") or c in ("market_regime", "market_state")]
    for col in state_cols:
        vals = df_null[col].to_numpy()
        rng.shuffle(vals)
        df_null[col] = vals

    return df_null


def generate_circular_shift_series(
    features_df: pd.DataFrame,
    shift_ticks: Optional[int] = None,
    random_seed: int = 42
) -> pd.DataFrame:
    """Performs circular shift (rolling) of outcome columns relative to features.
    
    Preserves:
    - Exact time-series autocorrelation and run lengths of outcomes.
    - Exact multi-scale factor dependencies and volatility regimes of features.
    - Exact marginal distributions of all variables.
    
    Destroys:
    - Temporal alignment between market state and contract outcomes.
    """
    rng = np.random.default_rng(random_seed)
    n = len(features_df)
    if n <= 200:
        shift = n // 2
    else:
        shift = shift_ticks if shift_ticks is not None else int(rng.integers(100, n - 100))

    df_shifted = features_df.copy()
    target_cols = [c for c in df_shifted.columns if c.endswith("_win") or c in ("entry_price", "exit_price", "is_tie")]

    for col in target_cols:
        vals = df_shifted[col].to_numpy()
        df_shifted[col] = np.roll(vals, shift)

    return df_shifted


def generate_block_shuffled_increments(
    raw_df: pd.DataFrame,
    block_size: int = 20,
    random_seed: int = 42
) -> pd.DataFrame:
    """Performs stationary block-shuffling on price increments.
    
    Preserves local volatility and variance distribution within blocks of length block_size,
    but destroys long-range sequence dependencies and macroscopic regime structure.
    """
    rng = np.random.default_rng(random_seed)
    p = raw_df["price"].to_numpy(dtype=float)
    deltas = np.diff(p)
    n_deltas = len(deltas)

    # Partition deltas into blocks
    num_blocks = n_deltas // block_size
    blocks = [deltas[i * block_size:(i + 1) * block_size] for i in range(num_blocks)]
    remainder = deltas[num_blocks * block_size:]

    # Shuffle block order
    rng.shuffle(blocks)
    shuffled_deltas = np.concatenate(blocks) if num_blocks > 0 else np.array([])
    if len(remainder) > 0:
        shuffled_deltas = np.concatenate([shuffled_deltas, remainder]) if len(shuffled_deltas) > 0 else remainder

    # Reconstruct prices from initial price
    recon_prices = np.empty(len(raw_df))
    recon_prices[0] = p[0]
    recon_prices[1:] = p[0] + np.cumsum(shuffled_deltas)

    df_shuffled = raw_df.copy()
    df_shuffled["price"] = recon_prices
    return df_shuffled


def evaluate_null_candidates_across_stages(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    holdout_df: pd.DataFrame,
    quote_engine: QuoteEngine,
    sample_config: SampleSizeConfig,
    base_rate_rh: float = 0.03275,
    base_rate_rl: float = 0.02971,
    alpha: float = 0.05
) -> Dict[str, Any]:
    """Evaluates candidate states across all 5 statistical pipeline stages under null data.
    
    Stage 1: Exploratory Candidate Discovery (Train z >= 2.0, Lift >= 1.15, n >= min_discovery_samples)
    Stage 2: Confirmatory Significance (Holm step-down adjusted p <= 0.05 across full family M)
    Stage 3: Out-of-Sample Validation Survival (Val Lift > 1.0, Edge > 0.0, n_val >= min_validation_samples)
    Stage 4: Untouched Holdout Confirmation (Holdout z > 3.00, Edge > 0.0, n_hold >= min_holdout_samples)
    Stage 5: Full Tradability Gate (Stage 4 Pass + Positive Calibration Skill BSS > 0 + Conservative EV > 0)
    """
    searcher = SystematicStateGridSearch(
        min_sample_size=sample_config.min_discovery_samples,
        candidate_z_threshold=2.0,
        min_lift_threshold=1.15,
        sample_config=sample_config,
        alpha=alpha
    )
    search_res = searcher.search(train_df, quote_engine)
    total_states_evaluated = search_res.get("total_states_evaluated", 1)
    # Family of tested hypotheses includes both RUNHIGH and RUNLOW directions
    total_hypotheses = total_states_evaluated * 2

    all_candidates: List[StateCandidate] = search_res.get("runhigh_candidates", []) + search_res.get("runlow_candidates", [])
    stage1_exploratory_count = len(all_candidates)

    # Stage 2: Confirmatory Significance via Holm step-down
    all_evals = search_res.get("all_evaluations", [])
    raw_p_list = []
    for ev in all_evals:
        raw_p_list.append(ev.get("rh_raw_p", 1.0))
        raw_p_list.append(ev.get("rl_raw_p", 1.0))

    holm_p_list = calculate_holm_adjusted_p(raw_p_list)
    stage2_significant_count = sum(1 for p in holm_p_list if p <= alpha)

    if stage1_exploratory_count == 0:
        return {
            "total_hypotheses_tested": total_hypotheses,
            "stage1_exploratory": 0,
            "stage2_significant": 0,
            "stage3_validation": 0,
            "stage4_holdout": 0,
            "stage5_full_gate": 0,
            "candidates": []
        }

    # Stage 3: Validation Audit
    val_audits = audit_candidates_on_validation(
        val_df=val_df,
        candidates=all_candidates,
        quote_engine=quote_engine,
        sample_config=sample_config
    )
    val_survived = [a for a in val_audits if a.get("survived_validation", False)]
    stage3_val_count = len(val_survived)

    # Stage 4 & 5: Evaluate surviving validation candidates on Holdout
    stage4_holdout_count = 0
    stage5_full_gate_count = 0

    up_q = quote_engine.get_quote("UP")
    down_q = quote_engine.get_quote("DOWN")
    be_up = up_q.implied_probability if up_q else 0.0328
    be_down = down_q.implied_probability if down_q else 0.0328
    stake = up_q.stake if up_q else 2.0
    payout = up_q.payout if up_q else 61.03

    for v_entry in val_survived:
        cand: StateCandidate = v_entry["candidate"]
        is_rh = (cand.direction == "RUNHIGH")
        win_col = "runhigh_win" if is_rh else "runlow_win"
        base_rate = base_rate_rh if is_rh else base_rate_rl
        be = be_up if is_rh else be_down

        # Construct holdout mask
        mask_h = pd.Series(True, index=holdout_df.index)
        for col_name, val in zip(cand.factor_cols, cand.factor_vals):
            if col_name in holdout_df.columns:
                mask_h = mask_h & (holdout_df[col_name].astype(str) == str(val))
            else:
                mask_h = pd.Series(False, index=holdout_df.index)
                break

        sub_h = holdout_df.loc[mask_h]
        n_h = len(sub_h)
        if n_h < sample_config.min_holdout_samples or win_col not in holdout_df.columns:
            continue

        w_h = int(sub_h[win_col].sum())
        wr_h = w_h / n_h
        edge_h = wr_h - be
        z_h = calculate_z_score(wr_h, be, n_h)

        # Stage 4 requirement: Untouched holdout z > 3.00 and edge > 0
        if edge_h > 0.0 and z_h > 3.00:
            stage4_holdout_count += 1

            # Stage 5 requirement: Calibration BSS > 0 and Conservative EV > 0
            ci_lo, _ = wilson_score_ci(w_h, n_h, confidence=0.95)
            cons_ev = calculate_conservative_ev(ci_lo, stake, payout)

            y_true = holdout_df[win_col].to_numpy(dtype=float)
            y_pred = np.where(mask_h, cand.prob, base_rate)
            cal_res = compute_calibration_curve(y_true, y_pred, n_bins=5, baseline_prob=base_rate)
            cal_ok = is_model_calibrated(cal_res, max_ece=0.05, min_bss=0.0)

            is_sig = (cand.adjusted_p_value <= alpha) or (getattr(cand, "holm_p_value", 1.0) <= alpha)
            if is_sig and cal_ok and cons_ev > 0.0:
                stage5_full_gate_count += 1

    return {
        "total_hypotheses_tested": total_hypotheses,
        "stage1_exploratory": stage1_exploratory_count,
        "stage2_significant": stage2_significant_count,
        "stage3_validation": stage3_val_count,
        "stage4_holdout": stage4_holdout_count,
        "stage5_full_gate": stage5_full_gate_count
    }


def run_negative_control_audit(
    features_df: pd.DataFrame,
    quote_engine: QuoteEngine,
    num_permutations: int = 3,
    null_methods: Optional[List[str]] = None,
    sample_config: Optional[SampleSizeConfig] = None,
    alpha: float = 0.05
) -> Dict[str, Any]:
    """Executes time-series-aware negative control experiments across all validation stages.
    
    Verifies that the multi-gate discovery pipeline does NOT produce false validated edges
    when running on noise datasets where predictive relationships are broken.
    
    Reports false positive rates separately for:
    - Stage 1: Exploratory Candidate Discovery
    - Stage 2: Confirmatory Significance
    - Stage 3: Out-of-sample Validation Survival
    - Stage 4: Untouched Holdout Confirmation
    - Stage 5: Full Tradability Gating
    """
    cfg = sample_config or SampleSizeConfig()
    methods = null_methods or ["permuted_states", "circular_shift"]

    stage1_tot = 0
    stage2_tot = 0
    stage3_tot = 0
    stage4_tot = 0
    stage5_tot = 0
    hypotheses_tot = 0
    sim_details = []

    sim_id = 0
    for method in methods:
        for seed_offset in range(num_permutations):
            sim_id += 1
            seed = 100 + seed_offset * 17 + (hash(method) % 1000)

            # Generate time-series-aware null series
            if method == "circular_shift":
                df_null = generate_circular_shift_series(features_df, random_seed=seed)
            else:
                df_null = generate_permuted_state_series(features_df, random_seed=seed)

            splits = create_purged_three_way_split(df_null, train_pct=0.60, val_pct=0.20, purge_gap=6)

            stage_res = evaluate_null_candidates_across_stages(
                train_df=splits.train_df,
                val_df=splits.val_df,
                holdout_df=splits.holdout_df,
                quote_engine=quote_engine,
                sample_config=cfg,
                alpha=alpha
            )

            hypotheses_tot += stage_res["total_hypotheses_tested"]
            stage1_tot += stage_res["stage1_exploratory"]
            stage2_tot += stage_res["stage2_significant"]
            stage3_tot += stage_res["stage3_validation"]
            stage4_tot += stage_res["stage4_holdout"]
            stage5_tot += stage_res["stage5_full_gate"]

            sim_details.append({
                "simulation": sim_id,
                "seed": seed,
                "method": method,
                "hypotheses_tested": stage_res["total_hypotheses_tested"],
                "stage1_exploratory": stage_res["stage1_exploratory"],
                "stage2_significant": stage_res["stage2_significant"],
                "stage3_validation": stage_res["stage3_validation"],
                "stage4_holdout": stage_res["stage4_holdout"],
                "stage5_full_gate": stage_res["stage5_full_gate"]
            })

    # Compute False Positive Rates and Wilson 95% CIs
    denom_hypotheses = max(1, hypotheses_tot)
    denom_exploratory = max(1, stage1_tot)

    # Stage 1 FPR vs all tested hypotheses
    fpr1 = stage1_tot / denom_hypotheses
    fpr1_ci = wilson_score_ci(stage1_tot, denom_hypotheses)

    # Stage 2 FPR vs all tested hypotheses (FWER)
    fpr2 = stage2_tot / denom_hypotheses
    fpr2_ci = wilson_score_ci(stage2_tot, denom_hypotheses)

    # Stage 3 FPR: proportion of exploratory candidates surviving validation fluctuation
    fpr3 = stage3_tot / denom_exploratory if stage1_tot > 0 else 0.0
    fpr3_ci = wilson_score_ci(stage3_tot, denom_exploratory) if stage1_tot > 0 else (0.0, 0.0)

    # Stage 4 FPR: proportion surviving untouched holdout
    fpr4 = stage4_tot / denom_exploratory if stage1_tot > 0 else 0.0
    fpr4_ci = wilson_score_ci(stage4_tot, denom_exploratory) if stage1_tot > 0 else (0.0, 0.0)

    # Stage 5 FPR: proportion surviving full tradability gate
    fpr5 = stage5_tot / denom_exploratory if stage1_tot > 0 else 0.0
    fpr5_ci = wilson_score_ci(stage5_tot, denom_exploratory) if stage1_tot > 0 else (0.0, 0.0)

    return {
        "num_simulations": len(sim_details),
        "total_hypotheses_tested": hypotheses_tot,
        "stage1_exploratory_discoveries": stage1_tot,
        "stage2_significant_discoveries": stage2_tot,
        "stage3_validation_survived": stage3_tot,
        "stage4_holdout_survived": stage4_tot,
        "stage5_full_gate_survived": stage5_tot,
        "stage_metrics": {
            "stage1_exploratory": {
                "count": stage1_tot,
                "fpr": round(fpr1, 4),
                "ci_95": (round(fpr1_ci[0], 4), round(fpr1_ci[1], 4)),
                "description": "In-sample exploratory candidate discovery (z >= 2.0)"
            },
            "stage2_significant": {
                "count": stage2_tot,
                "fpr": round(fpr2, 4),
                "ci_95": (round(fpr2_ci[0], 4), round(fpr2_ci[1], 4)),
                "description": "Family-wise confirmatory significance (Holm p <= 0.05)"
            },
            "stage3_validation": {
                "count": stage3_tot,
                "fpr": round(fpr3, 4),
                "ci_95": (round(fpr3_ci[0], 4), round(fpr3_ci[1], 4)),
                "description": "Validation slice edge survival (lift > 1.0, edge > 0)"
            },
            "stage4_holdout": {
                "count": stage4_tot,
                "fpr": round(fpr4, 4),
                "ci_95": (round(fpr4_ci[0], 4), round(fpr4_ci[1], 4)),
                "description": "Untouched holdout confirmation (z > 3.00)"
            },
            "stage5_full_gate": {
                "count": stage5_tot,
                "fpr": round(fpr5, 4),
                "ci_95": (round(fpr5_ci[0], 4), round(fpr5_ci[1], 4)),
                "description": "Full tradability gate (Holdout + Calibration + Conservative EV > 0)"
            }
        },
        # Backwards compatible keys for existing callers:
        "total_null_candidates_discovered": stage1_tot,
        "total_null_validated_edges": stage5_tot,
        "empirical_false_positive_rate": round(fpr5, 4),
        "passed_negative_control": (stage5_tot == 0),
        "simulations": sim_details
    }
