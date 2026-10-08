"""Statistical Calibration & Dependence-Aware Evaluation Engine (V1.7 Part E).

Scientifically assesses whether forward market predictions exhibit statistical skill,
accurate probability calibration, and genuine directional lift:
1. Observed win rates with Wilson score confidence intervals for rare events.
2. Probability calibration: Brier score, Brier Skill Score (BSS), and Expected Calibration Error (ECE)
   using rare-event adaptive reliability bins.
3. Dependence-aware uncertainty analysis:
   - Moving block bootstrap accounting for 5-movement outcome window overlap.
   - Autocorrelation-adjusted effective sample size (N_eff).
   - Non-overlapping subsampling sensitivity analysis.
4. Conditional probability lift analysis by discrete market state.
"""
import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


# Canonical empirical reference probabilities (V1.6.3 Section 1 baseline)
REFERENCE_BASE_RATE_RUNHIGH = 0.03275  # Empirical 3.275% on R_75
REFERENCE_BASE_RATE_RUNLOW = 0.02971   # Empirical 2.971% on R_75
THEORETICAL_RANDOM_WALK = 0.03125      # (0.5)^5 = 3.125%


def wilson_score_interval(wins: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculates Wilson score confidence interval for a binomial proportion.
    
    Particularly well-suited for rare-event rates where normal approximations fail.
    """
    if n <= 0:
        return (0.0, 0.0)
    
    # z for 95% = 1.95996
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 2.57583  # 99%
    p_hat = wins / n
    denom = 1.0 + (z**2 / n)
    center = (p_hat + (z**2 / (2.0 * n))) / denom
    spread = (z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z**2 / (4.0 * n**2)))) / denom
    
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (round(lower, 5), round(upper, 5))


class StatisticalEvaluator:
    """Rigorous time-series and probabilistic validation engine."""

    def __init__(self, block_size: int = 5, n_bootstraps: int = 1000):
        self.block_size = block_size
        self.n_bootstraps = n_bootstraps

    @staticmethod
    def moving_block_bootstrap_ci(series: List[float], block_size: int = 5, n_resamples: int = 1000, random_seed: int = 42) -> Tuple[float, float]:
        arr = np.array(series, dtype=np.float64)
        n = len(arr)
        if n == 0:
            return (0.0, 0.0)
        block_len = min(max(2, block_size), n)
        if n < block_len:
            return wilson_score_interval(int(np.sum(arr)), n)
        rng = np.random.default_rng(random_seed)
        max_start = n - block_len + 1
        n_blocks = int(math.ceil(n / block_len))
        boot_means = []
        for _ in range(n_resamples):
            starts = rng.integers(0, max_start, size=n_blocks)
            sample = np.concatenate([arr[st:st + block_len] for st in starts])[:n]
            boot_means.append(float(np.mean(sample)))
        return (round(float(np.percentile(boot_means, 2.5)), 5), round(float(np.percentile(boot_means, 97.5)), 5))

    @staticmethod
    def effective_sample_size(series: List[float], max_lag: int = 4) -> float:
        arr = np.array(series, dtype=np.float64)
        n = len(arr)
        if n <= 1:
            return float(n)
        tau = 1.0
        if np.std(arr) > 1e-9:
            s_mean = np.mean(arr)
            s_var = np.var(arr)
            for lag in range(1, min(max_lag + 1, n)):
                cov = np.mean((arr[:-lag] - s_mean) * (arr[lag:] - s_mean))
                rho = cov / s_var if s_var > 1e-9 else 0.0
                if rho > 0:
                    tau += 2.0 * float(rho)
        return round(max(1.0, float(n / tau)), 2)

    @staticmethod
    def non_overlapping_subsampling(series: List[float], stride: int = 5) -> Dict[str, Any]:
        sub = series[::stride]
        n_sub = len(sub)
        w_sub = sum(1 for x in sub if float(x) == 1.0)
        rate = round(w_sub / n_sub, 5) if n_sub > 0 else 0.0
        return {
            "stride": stride,
            "subsampled_count": n_sub,
            "subsampled_wins": w_sub,
            "subsampled_win_rate": rate,
            "ci_95": wilson_score_interval(w_sub, n_sub) if n_sub > 0 else (0.0, 0.0)
        }

    @classmethod
    def evaluate_win_rates(
        cls,
        arg1: Any,
        arg2: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Calculates observed win rates, calibration metrics, and lifts for resolved predictions."""
        if arg2 is not None:
            outcomes, predictions = arg1, arg2
            outcomes_by_id = {o.get("prediction_id"): o for o in outcomes}
            merged = []
            for p in predictions:
                p_copy = dict(p)
                p_id = p.get("prediction_id")
                if p_id in outcomes_by_id:
                    o = outcomes_by_id[p_id]
                    p_copy["outcome_status"] = o.get("outcome_status", "RESOLVED")
                    p_copy["runhigh_win"] = o.get("runhigh_win")
                    p_copy["runlow_win"] = o.get("runlow_win")
                    p_copy["forward_ticks_count"] = o.get("forward_ticks_count")
                elif "outcome_status" not in p_copy:
                    p_copy["outcome_status"] = "PENDING"
                merged.append(p_copy)
            predictions = merged
        else:
            predictions = arg1

        eligible = [
            p for p in predictions
            if p.get("outcome_status") in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        n_eligible = len(eligible)

        evaluator = cls() if isinstance(cls, type) else cls
        cal_rh = evaluator.evaluate_calibration(eligible, direction="RUNHIGH") if n_eligible > 0 else {}
        cal_rl = evaluator.evaluate_calibration(eligible, direction="RUNLOW") if n_eligible > 0 else {}
        dep_rh = evaluator.evaluate_dependence_aware_uncertainty(eligible, direction="RUNHIGH") if n_eligible > 0 else {}
        dep_rl = evaluator.evaluate_dependence_aware_uncertainty(eligible, direction="RUNLOW") if n_eligible > 0 else {}
        lift_rh = evaluator.evaluate_conditional_probability_lift(eligible, direction="RUNHIGH") if n_eligible > 0 else {"states": {}}
        lift_rl = evaluator.evaluate_conditional_probability_lift(eligible, direction="RUNLOW") if n_eligible > 0 else {"states": {}}

        if n_eligible == 0:
            return {
                "eligible_resolved_count": 0,
                "runhigh": {
                    "wins": 0, "observed_rate": 0.0, "ci_95": (0.0, 0.0),
                    "resolved_count": 0, "observed_wins": 0, "observed_win_rate": 0.0,
                    "mean_predicted_prob": 0.0, "brier_score": None, "reference_brier_score": None,
                    "brier_skill_score": None, "expected_calibration_error": None,
                    "effective_sample_size": 0.0, "block_bootstrap_ci": (0.0, 0.0)
                },
                "runlow": {
                    "wins": 0, "observed_rate": 0.0, "ci_95": (0.0, 0.0),
                    "resolved_count": 0, "observed_wins": 0, "observed_win_rate": 0.0,
                    "mean_predicted_prob": 0.0, "brier_score": None, "reference_brier_score": None,
                    "brier_skill_score": None, "expected_calibration_error": None,
                    "effective_sample_size": 0.0, "block_bootstrap_ci": (0.0, 0.0)
                },
                "conditional_lift": {"runhigh": {}, "runlow": {}}
            }

        rh_wins = sum(1 for p in eligible if float(p.get("runhigh_win") or 0) == 1.0)
        rl_wins = sum(1 for p in eligible if float(p.get("runlow_win") or 0) == 1.0)

        rh_rate = round(rh_wins / n_eligible, 5)
        rl_rate = round(rl_wins / n_eligible, 5)

        rh_ci = wilson_score_interval(rh_wins, n_eligible)
        rl_ci = wilson_score_interval(rl_wins, n_eligible)

        return {
            "eligible_resolved_count": n_eligible,
            "runhigh": {
                "wins": rh_wins,
                "observed_rate": rh_rate,
                "ci_95": rh_ci,
                "resolved_count": n_eligible,
                "observed_wins": rh_wins,
                "observed_win_rate": rh_rate,
                "mean_predicted_prob": cal_rh.get("mean_predicted_prob", rh_rate),
                "brier_score": cal_rh.get("brier_score"),
                "reference_brier_score": cal_rh.get("reference_brier"),
                "brier_skill_score": cal_rh.get("brier_skill_score"),
                "expected_calibration_error": cal_rh.get("expected_calibration_error"),
                "effective_sample_size": dep_rh.get("effective_sample_size", n_eligible),
                "block_bootstrap_ci": dep_rh.get("bootstrap_ci_95", rh_ci)
            },
            "runlow": {
                "wins": rl_wins,
                "observed_rate": rl_rate,
                "ci_95": rl_ci,
                "resolved_count": n_eligible,
                "observed_wins": rl_wins,
                "observed_win_rate": rl_rate,
                "mean_predicted_prob": cal_rl.get("mean_predicted_prob", rl_rate),
                "brier_score": cal_rl.get("brier_score"),
                "reference_brier_score": cal_rl.get("reference_brier"),
                "brier_skill_score": cal_rl.get("brier_skill_score"),
                "expected_calibration_error": cal_rl.get("expected_calibration_error"),
                "effective_sample_size": dep_rl.get("effective_sample_size", n_eligible),
                "block_bootstrap_ci": dep_rl.get("bootstrap_ci_95", rl_ci)
            },
            "conditional_lift": {
                "runhigh": lift_rh.get("states", {}),
                "runlow": lift_rl.get("states", {})
            }
        }

    def evaluate_calibration(
        self,
        predictions: List[Dict[str, Any]],
        direction: str = "RUNHIGH",
        reference_base_rate: Optional[float] = None,
        n_bins: int = 5
    ) -> Dict[str, Any]:
        """Calculates Brier Score, Brier Skill Score (BSS), and Expected Calibration Error (ECE)."""
        eligible = [
            p for p in predictions
            if p.get("outcome_status") in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        if not eligible:
            return {
                "direction": direction,
                "sample_count": 0,
                "brier_score": None,
                "reference_brier": None,
                "brier_skill_score": None,
                "expected_calibration_error": None,
                "reliability_bins": []
            }

        dir_key = direction.upper()
        prob_key = "runhigh_pred_prob" if dir_key == "RUNHIGH" else "runlow_pred_prob"
        win_key = "runhigh_win" if dir_key == "RUNHIGH" else "runlow_win"
        default_ref = REFERENCE_BASE_RATE_RUNHIGH if dir_key == "RUNHIGH" else REFERENCE_BASE_RATE_RUNLOW
        ref_rate = reference_base_rate if reference_base_rate is not None else default_ref

        probs: List[float] = []
        actuals: List[float] = []

        for p in eligible:
            p_val = p.get(prob_key)
            w_val = p.get(win_key)
            if p_val is not None and w_val is not None:
                probs.append(float(p_val))
                actuals.append(1.0 if float(w_val) == 1.0 else 0.0)

        n = len(probs)
        if n == 0:
            return {
                "direction": dir_key,
                "sample_count": 0,
                "brier_score": None,
                "reference_brier": None,
                "brier_skill_score": None,
                "expected_calibration_error": None,
                "reliability_bins": []
            }

        p_arr = np.array(probs, dtype=np.float64)
        y_arr = np.array(actuals, dtype=np.float64)

        # 1. Brier score
        bs = float(np.mean((p_arr - y_arr) ** 2))

        # 2. Reference Brier score (using unconditional reference rate)
        ref_bs = float(np.mean((ref_rate - y_arr) ** 2))

        # 3. Brier Skill Score: BSS = 1 - (BS / BS_ref)
        # BSS > 0 indicates predictive advantage over naive climatology
        bss = round(1.0 - (bs / ref_bs), 5) if ref_bs > 1e-9 else 0.0

        # 4. Expected Calibration Error (ECE) with bins tailored for rare events
        # Bins: [0, 0.02), [0.02, 0.035), [0.035, 0.05), [0.05, 0.08), [0.08, 1.0]
        bin_edges = [0.0, 0.02, 0.035, 0.05, 0.08, 1.0]
        bins_data: List[Dict[str, Any]] = []
        weighted_ece = 0.0

        for b_idx in range(len(bin_edges) - 1):
            low = bin_edges[b_idx]
            high = bin_edges[b_idx + 1]
            if b_idx == len(bin_edges) - 2:
                mask = (p_arr >= low) & (p_arr <= high)
            else:
                mask = (p_arr >= low) & (p_arr < high)

            count_b = int(np.sum(mask))
            if count_b > 0:
                mean_p_b = float(np.mean(p_arr[mask]))
                obs_freq_b = float(np.mean(y_arr[mask]))
                abs_diff = abs(mean_p_b - obs_freq_b)
                weighted_ece += (count_b / n) * abs_diff
                bins_data.append({
                    "bin_range": f"[{low:.3f}, {high:.3f})",
                    "count": count_b,
                    "mean_predicted": round(mean_p_b, 5),
                    "observed_frequency": round(obs_freq_b, 5),
                    "calibration_gap": round(abs_diff, 5)
                })
            else:
                bins_data.append({
                    "bin_range": f"[{low:.3f}, {high:.3f})",
                    "count": 0,
                    "mean_predicted": None,
                    "observed_frequency": None,
                    "calibration_gap": None
                })

        return {
            "direction": dir_key,
            "sample_count": n,
            "mean_predicted_prob": round(float(np.mean(p_arr)), 5),
            "observed_win_rate": round(float(np.mean(y_arr)), 5),
            "brier_score": round(bs, 6),
            "reference_brier": round(ref_bs, 6),
            "brier_skill_score": bss,
            "expected_calibration_error": round(weighted_ece, 5),
            "reliability_bins": bins_data
        }

    def evaluate_dependence_aware_uncertainty(
        self,
        predictions: List[Dict[str, Any]],
        direction: str = "RUNHIGH"
    ) -> Dict[str, Any]:
        """Assesses autocorrelation, effective sample size, block bootstrap CIs,
        and non-overlapping subsampling sensitivity (V1.7 Part E Section 12).
        """
        eligible = [
            p for p in predictions
            if p.get("outcome_status") in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        if not eligible:
            return {
                "nominal_sample_size": 0,
                "effective_sample_size": 0.0,
                "autocorrelation_lag1_to_4": [],
                "bootstrap_ci_95": (0.0, 0.0),
                "non_overlapping": {
                    "count": 0,
                    "observed_rate": 0.0,
                    "ci_95": (0.0, 0.0)
                }
            }

        dir_key = direction.upper()
        win_key = "runhigh_win" if dir_key == "RUNHIGH" else "runlow_win"
        series = np.array([1.0 if float(p.get(win_key) or 0) == 1.0 else 0.0 for p in eligible], dtype=np.float64)
        n = len(series)

        # 1. Autocorrelation for lags 1 to 4
        autocorrs: List[float] = []
        tau = 1.0
        if n > 5 and np.std(series) > 1e-9:
            s_mean = np.mean(series)
            s_var = np.var(series)
            for lag in range(1, min(5, n)):
                cov = np.mean((series[:-lag] - s_mean) * (series[lag:] - s_mean))
                rho = cov / s_var if s_var > 1e-9 else 0.0
                autocorrs.append(round(float(rho), 4))
                if rho > 0:
                    tau += 2.0 * float(rho)
        else:
            autocorrs = [0.0, 0.0, 0.0, 0.0]

        n_eff = round(max(1.0, float(n / tau)), 2)

        # 2. Moving block bootstrap (block size = 5 ticks)
        block_len = min(max(2, self.block_size), n)
        boot_means = []
        if n >= block_len:
            rng = np.random.default_rng(42)
            max_start = n - block_len + 1
            n_blocks = int(math.ceil(n / block_len))
            for _ in range(self.n_bootstraps):
                starts = rng.integers(0, max_start, size=n_blocks)
                sample = np.concatenate([series[st:st + block_len] for st in starts])[:n]
                boot_means.append(float(np.mean(sample)))
            boot_ci_low = float(np.percentile(boot_means, 2.5))
            boot_ci_high = float(np.percentile(boot_means, 97.5))
            boot_ci = (round(boot_ci_low, 5), round(boot_ci_high, 5))
        else:
            boot_ci = wilson_score_interval(int(np.sum(series)), n)

        # 3. Non-overlapping subsampling (filter predictions by stride >= 5 movements)
        # Using entry_epoch or sequence index to ensure zero shared forward ticks
        non_overlap_subset = []
        last_expiry_epoch = -1

        # Sort eligible chronologically
        sorted_preds = sorted(eligible, key=lambda x: float(x.get("entry_epoch") or x.get("timestamp") or 0.0))
        for p in sorted_preds:
            entry_ep = int(p.get("entry_epoch") or p.get("signal_epoch") or p.get("timestamp") or 0)
            if entry_ep > last_expiry_epoch:
                non_overlap_subset.append(p)
                # Next prediction must start strictly after this prediction's expiry
                expiry_ep = int(p.get("expiry_epoch") or (entry_ep + 12))  # ~10s-12s
                last_expiry_epoch = expiry_ep

        n_no = len(non_overlap_subset)
        no_wins = sum(1 for p in non_overlap_subset if float(p.get(win_key) or 0) == 1.0)
        no_rate = round(no_wins / n_no, 5) if n_no > 0 else 0.0
        no_ci = wilson_score_interval(no_wins, n_no) if n_no > 0 else (0.0, 0.0)

        return {
            "nominal_sample_size": n,
            "effective_sample_size": n_eff,
            "autocorrelation_lag1_to_4": autocorrs,
            "bootstrap_ci_95": boot_ci,
            "non_overlapping": {
                "count": n_no,
                "wins": no_wins,
                "observed_rate": no_rate,
                "ci_95": no_ci
            }
        }

    def evaluate_conditional_probability_lift(
        self,
        predictions: List[Dict[str, Any]],
        direction: str = "RUNHIGH"
    ) -> Dict[str, Any]:
        """Calculates conditional win rate lift across discrete market states."""
        eligible = [
            p for p in predictions
            if p.get("outcome_status") in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        if not eligible:
            return {"unconditional_rate": 0.0, "states": {}}

        dir_key = direction.upper()
        win_key = "runhigh_win" if dir_key == "RUNHIGH" else "runlow_win"
        n_total = len(eligible)
        total_wins = sum(1 for p in eligible if float(p.get(win_key) or 0) == 1.0)
        p_uncond = total_wins / n_total

        # Group by market state
        state_groups: Dict[str, List[Dict[str, Any]]] = {}
        for p in eligible:
            st = p.get("market_state") or "DEFAULT"
            state_groups.setdefault(st, []).append(p)

        states_result: Dict[str, Any] = {}
        for st, st_preds in state_groups.items():
            n_st = len(st_preds)
            w_st = sum(1 for p in st_preds if float(p.get(win_key) or 0) == 1.0)
            p_st = w_st / n_st
            abs_lift = p_st - p_uncond
            rel_lift = (abs_lift / p_uncond) if p_uncond > 1e-6 else 0.0

            # Two-proportion z-score
            denom = math.sqrt(p_uncond * (1.0 - p_uncond) * (1.0 / n_st + 1.0 / n_total)) if p_uncond > 0 and p_uncond < 1 else 1.0
            z_score = abs_lift / denom if denom > 1e-9 else 0.0

            states_result[st] = {
                "sample_count": n_st,
                "sample_size": n_st,
                "wins": w_st,
                "observed_wins": w_st,
                "observed_rate": round(p_st, 5),
                "conditional_win_rate": round(p_st, 5),
                "absolute_lift": round(abs_lift, 5),
                "relative_lift": round(rel_lift, 4),
                "z_score": round(z_score, 3),
                "ci_95": wilson_score_interval(w_st, n_st)
            }

        return {
            "unconditional_rate": round(p_uncond, 5),
            "total_samples": n_total,
            "states": states_result
        }
