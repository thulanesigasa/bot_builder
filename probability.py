"""Statistical inference, probability estimation, Bonferroni correction, and EV engine.
Computes empirical win rates, break-even thresholds, confidence intervals, and z-scores.
"""
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
import math
import numpy as np
import pandas as pd



@dataclass
class SetupStats:
    name: str
    sample_size: int
    win_rate: float
    ci_lower: float
    ci_upper: float
    z_score: float
    expected_value: float
    ev_ci_lower: float
    ev_ci_upper: float
    beats_break_even: bool


def calculate_break_even(payout_ratio: float) -> float:
    """Calculates break-even win rate: 1 / (1 + payout_ratio)."""
    return 1.0 / (1.0 + payout_ratio)


def calculate_expected_value(win_rate: float, payout_ratio: float) -> float:
    """Calculates expected profit per $1 staked: WR * (1 + payout) - 1.0."""
    if np.isnan(win_rate):
        return np.nan
    return win_rate * (1.0 + payout_ratio) - 1.0


def calculate_confidence_interval(wins: int, n: int) -> tuple[float, float]:
    """Calculates 95% Wald confidence interval for binomial proportion."""
    if n <= 0:
        return 0.0, 0.0
    wr = wins / n
    se = float(np.sqrt(wr * (1.0 - wr) / n)) if 0 < wr < 1 else 0.0
    return max(0.0, wr - 1.96 * se), min(1.0, wr + 1.96 * se)


def calculate_z_score(win_rate: float, null_prob: float, n: int) -> float:
    """Calculates one-sample z-score of empirical win rate vs null break-even probability."""
    if n <= 0 or null_prob <= 0 or null_prob >= 1:
        return 0.0
    se = float(np.sqrt(null_prob * (1.0 - null_prob) / n))
    return float((win_rate - null_prob) / se)


def calculate_ev_ci(win_rate: float, n: int, payout_ratio: float, stake: float = 1.0) -> tuple[float, float, float]:
    """Calculates EV and its 95% confidence bounds."""
    if n <= 0:
        return 0.0, 0.0, 0.0
    ci_lo, ci_hi = calculate_confidence_interval(int(round(win_rate * n)), n)
    ev = calculate_expected_value(win_rate, payout_ratio) * stake
    ev_lo = calculate_expected_value(ci_lo, payout_ratio) * stake
    ev_hi = calculate_expected_value(ci_hi, payout_ratio) * stake
    return ev, ev_lo, ev_hi


def compute_probability_lift(conditional_prob: float, baseline_prob: float) -> float:
    """Calculates probability lift over unconditional baseline: P(event | state) / P(event)."""
    if baseline_prob <= 0 or np.isnan(conditional_prob) or np.isnan(baseline_prob):
        return 1.0
    return float(conditional_prob / baseline_prob)


def compute_absolute_lift(conditional_prob: float, baseline_prob: float) -> float:
    """Calculates absolute probability difference over baseline: P(event | state) - P(event)."""
    if np.isnan(conditional_prob) or np.isnan(baseline_prob):
        return 0.0
    return float(conditional_prob - baseline_prob)


@dataclass(frozen=True)
class BaselineStats:
    symbol: str
    direction: str  # 'RUNHIGH' or 'RUNLOW'
    observations: int
    wins: int
    losses: int
    empirical_prob: float
    standard_error: float
    ci_lower: float
    ci_upper: float
    theoretical_ref: float = 0.03125


def calculate_unconditional_baseline(
    df: pd.DataFrame,
    symbol: str = "R_75"
) -> Dict[str, BaselineStats]:
    """Calculates empirical baseline statistics for exact 5-transition RUNHIGH and RUNLOW.
    
    Does NOT assume theoretical 3.125%. Uses actual historical data to compute
    empirical probability, observations, wins, losses, SE, and 95% Wald CI.
    """
    res = {}
    for direction, col in [("RUNHIGH", "runhigh_win"), ("RUNLOW", "runlow_win")]:
        if col in df.columns:
            s = df[col].dropna()
        elif "only_ups_win" in df.columns and direction == "RUNHIGH":
            s = df["only_ups_win"].dropna()
        elif "only_downs_win" in df.columns and direction == "RUNLOW":
            s = df["only_downs_win"].dropna()
        else:
            # If outcome columns not present, compute using ContractOutcomeModel
            from contract_model import ContractOutcomeModel
            model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
            out = model.compute_contract_outcomes(df)
            s = out[col].dropna()

        n = len(s)
        wins = int(s.sum()) if n > 0 else 0
        losses = n - wins
        p = (wins / n) if n > 0 else 0.0
        se = float(np.sqrt(p * (1.0 - p) / n)) if (n > 0 and 0 < p < 1) else 0.0
        ci_lo = max(0.0, p - 1.96 * se)
        ci_hi = min(1.0, p + 1.96 * se)

        res[direction] = BaselineStats(
            symbol=symbol,
            direction=direction,
            observations=n,
            wins=wins,
            losses=losses,
            empirical_prob=p,
            standard_error=se,
            ci_lower=ci_lo,
            ci_upper=ci_hi,
            theoretical_ref=0.03125
        )
    return res



def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Calculates the Brier score (mean squared error of probability predictions): (1/N) * sum((p - y)^2)."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_prob, dtype=float)
    valid = ~(np.isnan(yt) | np.isnan(yp))
    if valid.sum() == 0:
        return 0.0
    return float(np.mean((yp[valid] - yt[valid]) ** 2))


def compute_brier_skill_score(y_true: np.ndarray, y_prob: np.ndarray, baseline_prob: float) -> float:
    """Calculates Brier Skill Score (BSS) relative to the unconditional baseline:
    BSS = 1 - (Brier_model / Brier_baseline).
    Positive BSS indicates true predictive skill beyond predicting the constant base rate.
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_prob, dtype=float)
    valid = ~(np.isnan(yt) | np.isnan(yp))
    if valid.sum() == 0:
        return 0.0
    yt = yt[valid]
    yp = yp[valid]
    brier_model = float(np.mean((yp - yt) ** 2))
    brier_baseline = float(np.mean((baseline_prob - yt) ** 2))
    if brier_baseline <= 0:
        return 0.0
    return float(1.0 - (brier_model / brier_baseline))


def compute_calibration_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 5,
    baseline_prob: Optional[float] = None
) -> dict:
    """Calculates bin-level probability calibration, Expected Calibration Error (ECE),
    Brier Score, and Brier Skill Score.
    
    Returns:
        dict with 'bin_pred_probs', 'bin_true_probs', 'bin_counts', 'ece',
                  'brier_score', 'baseline_brier_score', 'brier_skill_score'
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_prob, dtype=float)
    valid = ~(np.isnan(yt) | np.isnan(yp))
    yt = yt[valid]
    yp = yp[valid]
    total_n = len(yt)

    if total_n == 0:
        return {
            "bin_pred_probs": [],
            "bin_true_probs": [],
            "bin_counts": [],
            "ece": 0.0,
            "brier_score": 0.0,
            "baseline_brier_score": 0.0,
            "brier_skill_score": 0.0
        }

    # Bins between 0 and max probability observed (or 1.0)
    bins = np.linspace(0.0, max(0.10, float(np.max(yp))), n_bins + 1)
    bin_pred = []
    bin_true = []
    bin_counts = []
    ece = 0.0

    for i in range(n_bins):
        low, high = bins[i], bins[i + 1]
        mask = (yp >= low) & (yp <= high) if i == n_bins - 1 else (yp >= low) & (yp < high)
        n_b = int(mask.sum())
        if n_b > 0:
            p_mean = float(yp[mask].mean())
            y_mean = float(yt[mask].mean())
            bin_pred.append(p_mean)
            bin_true.append(y_mean)
            bin_counts.append(n_b)
            ece += (n_b / total_n) * abs(p_mean - y_mean)

    bs = compute_brier_score(yt, yp)
    base_p = baseline_prob if baseline_prob is not None else float(np.mean(yt))
    base_bs = float(np.mean((base_p - yt) ** 2))
    bss = float(1.0 - (bs / base_bs)) if base_bs > 0 else 0.0

    return {
        "bin_pred_probs": bin_pred,
        "bin_true_probs": bin_true,
        "bin_counts": bin_counts,
        "ece": float(ece),
        "brier_score": bs,
        "baseline_brier_score": base_bs,
        "brier_skill_score": bss
    }



def norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function using math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def bonferroni_critical_z(num_tests: int, alpha: float = 0.05) -> float:
    """Computes critical z-score threshold adjusted for family-wise error rate via Bonferroni."""
    if num_tests <= 0:
        return 1.96
    adj_alpha = alpha / float(num_tests)
    # Rational approximation for inverse normal CDF at high quantiles (Acklam)
    p = 1.0 - adj_alpha / 2.0
    # Binary search or rational approximation
    low, high = 1.96, 6.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if norm_cdf(mid) < p:
            low = mid
        else:
            high = mid
    return round((low + high) / 2.0, 3)


def calculate_true_break_even(stake: float, payout: float, basis: str = "stake") -> float:
    """Calculates true break-even probability respecting Deriv payout basis semantics.
    
    If payout is total return including stake: BE = stake / payout.
    If payout represents net profit (basis == 'profit'): BE = stake / (stake + payout).
    """
    if stake <= 0 or payout <= 0:
        return 0.0
    if basis.lower() == "profit":
        return float(stake / (stake + payout))
    return float(stake / payout)


def calculate_true_ev(
    prob: float,
    stake: float,
    payout: float,
    basis: str = "stake"
) -> float:
    """Calculates true Expected Value ($) respecting Deriv payout basis semantics.
    
    If payout is total return: EV = prob * payout - stake.
    If payout is net profit: EV = prob * payout - (1 - prob) * stake.
    """
    if np.isnan(prob) or stake <= 0 or payout <= 0:
        return 0.0
    if basis.lower() == "profit":
        return float(prob * payout - (1.0 - prob) * stake)
    return float(prob * payout - stake)


def calculate_p_value(win_rate: float, null_prob: float, n: int) -> float:
    """Calculates one-sided upper-tail p-value for binomial test vs null probability: P(Z >= z)."""
    if n <= 0 or null_prob <= 0 or null_prob >= 1 or np.isnan(win_rate):
        return 1.0
    z = calculate_z_score(win_rate, null_prob, n)
    return float(max(0.0, min(1.0, norm_cdf(-z))))


def calculate_adjusted_p_value(raw_p: float, num_tests: int) -> float:
    """Applies Bonferroni multiple-testing correction to raw p-value."""
    if np.isnan(raw_p) or num_tests <= 0:
        return 1.0
    return float(min(1.0, raw_p * num_tests))


def evaluate_significance_status(
    raw_p: float,
    adj_p: float,
    n: int,
    min_samples: int = 50,
    alpha: float = 0.05
) -> str:
    """Determines statistical significance status under sample-size and family-wise error guards.
    
    Returns:
        'INSUFFICIENT_SAMPLE' if n < min_samples
        'STATISTICALLY_SIGNIFICANT' if adj_p <= alpha
        'NOT_SIGNIFICANT' otherwise
    """
    if n < min_samples:
        return "INSUFFICIENT_SAMPLE"
    if adj_p <= alpha:
        return "STATISTICALLY_SIGNIFICANT"
    return "NOT_SIGNIFICANT"


def is_model_calibrated(
    calibration_result: dict,
    max_ece: float = 0.05,
    min_bss: float = 0.0
) -> bool:
    """Checks whether the probability model satisfies calibration standards.
    Requires positive skill (bss > 0) and low Expected Calibration Error (ece <= max_ece).
    """
    ece = calibration_result.get("ece", 1.0)
    bss = calibration_result.get("brier_skill_score", -1.0)
    return bool(bss > min_bss and ece <= max_ece)


def evaluate_setup(

    df: pd.DataFrame,
    mask: pd.Series,
    side: str,
    payout_ratio: float = 0.953,
    name: str = "Setup"
) -> SetupStats:
    """Evaluates a trading setup mask with confidence intervals and z-score test vs break-even.
    
    Args:
        df: DataFrame with forward win targets ('rise_win', 'fall_win').
        mask: Boolean Series selecting candidate ticks.
        side: Trade direction ('rise' or 'fall').
        payout_ratio: Payout ratio per $1 staked.
        name: Name identifier for the setup.
    """
    be = calculate_break_even(payout_ratio)
    win_col = f"{side}_win"
    if win_col not in df.columns:
        if side in ("runhigh", "up", "rise") and "runhigh_win" in df.columns:
            win_col = "runhigh_win"
        elif side in ("runlow", "down", "fall") and "runlow_win" in df.columns:
            win_col = "runlow_win"
        elif side in ("runhigh", "up", "rise") and "only_ups_win" in df.columns:
            win_col = "only_ups_win"
        elif side in ("runlow", "down", "fall") and "only_downs_win" in df.columns:
            win_col = "only_downs_win"
        elif side in ("runhigh", "up", "rise") and "rise_win" in df.columns:
            win_col = "rise_win"
        elif side in ("runlow", "down", "fall") and "fall_win" in df.columns:
            win_col = "fall_win"
    
    wins = df.loc[mask, win_col].dropna() if win_col in df.columns else pd.Series(dtype=float)
    n = len(wins)
    
    if n == 0:
        return SetupStats(
            name=name,
            sample_size=0,
            win_rate=np.nan,
            ci_lower=np.nan,
            ci_upper=np.nan,
            z_score=np.nan,
            expected_value=np.nan,
            ev_ci_lower=np.nan,
            ev_ci_upper=np.nan,
            beats_break_even=False
        )
        
    wr = float(wins.mean())
    se = float(np.sqrt(wr * (1.0 - wr) / n)) if 0 < wr < 1 else 0.0
    ci_lo = max(0.0, wr - 1.96 * se)
    ci_hi = min(1.0, wr + 1.96 * se)
    
    z = float((wr - be) / np.sqrt(be * (1.0 - be) / n))
    
    ev = calculate_expected_value(wr, payout_ratio)
    ev_lo = calculate_expected_value(ci_lo, payout_ratio)
    ev_hi = calculate_expected_value(ci_hi, payout_ratio)
    
    return SetupStats(
        name=name,
        sample_size=n,
        win_rate=wr,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        z_score=z,
        expected_value=ev,
        ev_ci_lower=ev_lo,
        ev_ci_upper=ev_hi,
        beats_break_even=(wr > be and ci_lo > be)
    )


# ==============================================================================
# V1.5 ADVANCED STATISTICAL ESTIMATION & SAFEGUARDS
# ==============================================================================

def bayesian_smoothed_probability(
    wins: int,
    n: int,
    baseline_prob: float = 0.03125,
    prior_weight: float = 50.0
) -> float:
    """Applies Bayesian conjugate Beta smoothing (shrinkage) centered on unconditional baseline P_0.
    
    Prevents extreme low-sample distortion by pulling sparse states toward the base rate:
    P_bayes = (wins + prior_weight * baseline_prob) / (n + prior_weight).
    """
    if n <= 0:
        return baseline_prob
    return float((wins + prior_weight * baseline_prob) / (n + prior_weight))


def wilson_score_interval(wins: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculates Wilson score confidence interval with improved coverage at low probabilities.
    
    Handles edge cases where p is near 0 or 1 better than standard Wald interval.
    """
    if n <= 0:
        return 0.0, 0.0
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 2.57583
    p_hat = wins / n
    denominator = 1.0 + (z ** 2) / n
    center = (p_hat + (z ** 2) / (2.0 * n)) / denominator
    std_err = math.sqrt((p_hat * (1.0 - p_hat) / n) + ((z ** 2) / (4.0 * (n ** 2))))
    margin = (z * std_err) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def calculate_conservative_ev(
    lower_bound_prob: float,
    stake: float,
    payout: float,
    basis: str = "stake"
) -> float:
    """Calculates conservative Expected Value using the lower bound of the winning probability confidence interval.
    
    Provides a statistical safety margin against sampling variance.
    """
    return calculate_true_ev(lower_bound_prob, stake, payout, basis=basis)


def calculate_expected_roi(ev: float, stake: float) -> float:
    """Calculates expected return on investment (ROI): EV / stake."""
    if stake <= 0 or np.isnan(ev):
        return 0.0
    return float(ev / stake)


def calculate_effective_sample_size(
    n: int,
    duration_ticks: int = 5,
    autocorrelation: Optional[float] = None
) -> float:
    """Calculates effective sample size adjusting for serial dependence of overlapping 5-tick contract windows.
    
    For overlapping sliding windows of length L, adjacent windows share L-1 transitions.
    Conservative effective N adjusts for overlap by a factor of 1 / duration_ticks.
    """
    if n <= 0:
        return 0.0
    if autocorrelation is not None and autocorrelation > 0:
        rho = min(0.95, autocorrelation)
        factor = (1.0 - rho) / (1.0 + rho)
        return max(1.0, float(n * factor))
    return max(1.0, float(n / duration_ticks))


def calculate_fdr_q_values(p_values: List[float]) -> List[float]:
    """Calculates Benjamini-Hochberg False Discovery Rate (FDR) adjusted q-values across m tests.
    
    Sorts p-values, computes q_i = p_(i) * m / i, and enforces step-up monotonicity.
    """
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    q_vals = [0.0] * m
    running_min = 1.0
    
    for rank in range(m, 0, -1):
        orig_idx, p_val = indexed[rank - 1]
        adjusted = min(1.0, p_val * m / rank)
        running_min = min(running_min, adjusted)
        q_vals[orig_idx] = float(running_min)
        
    return q_vals

