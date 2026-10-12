"""Market-Specific Predictive Modeling & Baseline Benchmark Pipeline for Rise/Fall (V1.8.0).

Features:
  - Causal rolling features strictly computed before prediction commitment:
    * Recent tick returns (1, 2, 3, 5 ticks)
    * Directional momentum and acceleration
    * Short-term rolling realized volatility
    * Directional streak length
    * EMA distance (mean-reversion)
  - Chronological dataset partitioning (Train 60%, Validation 20%, Untouched Test 20%)
    with purge/embargo to prevent overlapping outcome leakage.
  - Baselines:
    1. Naive 50/50 Constant Reference
    2. Unconditional Base-Rate Reference
    3. Regularized Logistic Regression Model
    4. Streak/Momentum Conditioned Empirical Table Model
  - Rigorous Probability Calibration:
    * Brier Score
    * Brier Skill Score (BSS) relative to base rate
    * Expected Calibration Error (ECE)
    * Calibration Intercept & Slope
    * Log Loss

Safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

LIVE_EXECUTION_DISABLED: bool = True


@dataclass
class CalibrationMetrics:
    """Rigorous probabilistic calibration evaluation."""
    sample_size: int
    empirical_win_rate: float
    mean_predicted_prob: float
    brier_score: float
    brier_ref_score: float
    brier_skill_score: float
    expected_calibration_error_ece: float
    calibration_slope: Optional[float]
    calibration_intercept: Optional[float]
    log_loss: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "empirical_win_rate": round(self.empirical_win_rate, 4),
            "mean_predicted_prob": round(self.mean_predicted_prob, 4),
            "brier_score": round(self.brier_score, 6),
            "brier_ref_score": round(self.brier_ref_score, 6),
            "brier_skill_score": round(self.brier_skill_score, 6),
            "expected_calibration_error_ece": round(self.expected_calibration_error_ece, 6),
            "calibration_slope": round(self.calibration_slope, 4) if self.calibration_slope is not None else None,
            "calibration_intercept": round(self.calibration_intercept, 4) if self.calibration_intercept is not None else None,
            "log_loss": round(self.log_loss, 6),
        }


class RiseFallFeatureExtractor:
    """Extracts causal features strictly using historical price observations prior to decision epoch."""

    @staticmethod
    def extract_features(prices: np.ndarray, window_size: int = 25) -> Tuple[np.ndarray, List[str]]:
        """Computes feature matrix X from price series.
        
        Args:
            prices: Array of prices up to current index t.
            window_size: Required warmup window length.
            
        Returns:
            X: Matrix of shape (N - window_size, n_features)
            feature_names: List of feature names.
        """
        n = len(prices)
        if n < window_size:
            return np.empty((0, 8)), []

        feature_names = [
            "ret_1",
            "ret_2",
            "ret_3",
            "ret_5",
            "momentum_3",
            "acceleration",
            "volatility_10",
            "streak",
        ]

        X_rows = []
        for i in range(window_size, n):
            p_cur = prices[i]
            p_1 = prices[i - 1]
            p_2 = prices[i - 2]
            p_3 = prices[i - 3]
            p_5 = prices[i - 5]

            # Causal returns
            ret_1 = (p_cur - p_1) / p_1 if p_1 > 0 else 0.0
            ret_2 = (p_cur - p_2) / p_2 if p_2 > 0 else 0.0
            ret_3 = (p_cur - p_3) / p_3 if p_3 > 0 else 0.0
            ret_5 = (p_cur - p_5) / p_5 if p_5 > 0 else 0.0

            # Momentum and acceleration
            mom_3 = p_cur - p_3
            accel = (p_cur - p_1) - (p_1 - p_2)

            # Rolling volatility over last 10 ticks
            recent = prices[i - 10 : i + 1]
            diffs = np.diff(recent)
            vol_10 = float(np.std(diffs)) if len(diffs) > 1 else 0.0

            # Directional streak
            streak = 0
            for k in range(i, max(0, i - 10), -1):
                diff = prices[k] - prices[k - 1]
                if diff > 0:
                    if streak >= 0:
                        streak += 1
                    else:
                        break
                elif diff < 0:
                    if streak <= 0:
                        streak -= 1
                    else:
                        break
                else:
                    break

            X_rows.append([ret_1, ret_2, ret_3, ret_5, mom_3, accel, vol_10, float(streak)])

        return np.array(X_rows, dtype=np.float64), feature_names


class RiseFallDatasetGenerator:
    """Generates chronologically partitioned training, validation, and holdout datasets."""

    @staticmethod
    def create_dataset(
        prices: np.ndarray,
        duration_ticks: int = 5,
        window_size: int = 25,
        train_pct: float = 0.60,
        val_pct: float = 0.20,
    ) -> Dict[str, Any]:
        """Builds causal features and V1 next-tick binary Rise outcomes with embargo between splits.
        
        Label y = 1 if forward_ticks[duration_ticks] > forward_ticks[0] (CALL win) else 0.
        """
        n = len(prices)
        needed_forward = duration_ticks + 1
        max_idx = n - needed_forward

        if max_idx <= window_size + 100:
            raise ValueError(f"Insufficient prices ({n}) for window {window_size} and duration {duration_ticks}.")

        X_list = []
        y_call_list = []
        valid_indices = []

        for i in range(window_size, max_idx):
            # Causal features at index i
            p_cur = prices[i]
            p_1 = prices[i - 1]
            p_2 = prices[i - 2]
            p_3 = prices[i - 3]
            p_5 = prices[i - 5]

            ret_1 = (p_cur - p_1) / p_1 if p_1 > 0 else 0.0
            ret_2 = (p_cur - p_2) / p_2 if p_2 > 0 else 0.0
            ret_3 = (p_cur - p_3) / p_3 if p_3 > 0 else 0.0
            ret_5 = (p_cur - p_5) / p_5 if p_5 > 0 else 0.0
            mom_3 = p_cur - p_3
            accel = (p_cur - p_1) - (p_1 - p_2)

            recent = prices[i - 10 : i + 1]
            diffs = np.diff(recent)
            vol_10 = float(np.std(diffs)) if len(diffs) > 1 else 0.0

            streak = 0
            for k in range(i, max(0, i - 10), -1):
                diff = prices[k] - prices[k - 1]
                if diff > 0:
                    if streak >= 0:
                        streak += 1
                    else:
                        break
                elif diff < 0:
                    if streak <= 0:
                        streak -= 1
                    else:
                        break
                else:
                    break

            feat = [ret_1, ret_2, ret_3, ret_5, mom_3, accel, vol_10, float(streak)]

            # V1 next-tick entry: entry spot is prices[i + 1]
            # Expiry spot is prices[i + 1 + duration_ticks]
            s_entry = prices[i + 1]
            s_expiry = prices[i + 1 + duration_ticks]
            y_call = 1 if s_expiry > s_entry else 0

            X_list.append(feat)
            y_call_list.append(y_call)
            valid_indices.append(i)

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_call_list, dtype=np.int32)
        total_obs = len(X)

        # Chronological partition points
        train_end = int(total_obs * train_pct)
        # Purge/embargo between train and val
        embargo = duration_ticks + 5
        val_start = train_end + embargo
        val_end = int(total_obs * (train_pct + val_pct))
        test_start = val_end + embargo

        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[val_start:val_end], y[val_start:val_end]
        X_test, y_test = X[test_start:], y[test_start:]

        return {
            "total_observations": total_obs,
            "train": {"X": X_train, "y": y_train, "count": len(X_train)},
            "val": {"X": X_val, "y": y_val, "count": len(X_val)},
            "test": {"X": X_test, "y": y_test, "count": len(X_test)},
            "embargo_ticks": embargo,
        }


def compute_calibration_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> CalibrationMetrics:
    """Computes comprehensive probabilistic calibration and scoring metrics."""
    n = len(y_true)
    if n == 0:
        return CalibrationMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, None, 0.0)

    emp_win_rate = float(np.mean(y_true))
    mean_prob = float(np.mean(y_prob))

    # Brier Score
    brier = float(np.mean((y_prob - y_true) ** 2))
    # Reference Brier Score using empirical base rate
    brier_ref = float(np.mean((emp_win_rate - y_true) ** 2))
    bss = 1.0 - (brier / brier_ref) if brier_ref > 0 else 0.0

    # Log Loss (with epsilon clipping)
    eps = 1e-15
    y_prob_clipped = np.clip(y_prob, eps, 1.0 - eps)
    logloss = float(-np.mean(y_true * np.log(y_prob_clipped) + (1.0 - y_true) * np.log(1.0 - y_prob_clipped)))

    # Expected Calibration Error (ECE) over 10 equal-width probability bins
    bin_edges = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for b in range(10):
        low, high = bin_edges[b], bin_edges[b + 1]
        mask = (y_prob >= low) & (y_prob < high) if b < 9 else (y_prob >= low) & (y_prob <= high)
        n_bin = np.sum(mask)
        if n_bin > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (n_bin / n) * abs(bin_acc - bin_conf)

    # Calibration slope & intercept via simple linear fit of logit(prob) vs observed
    # For robust computation without external dependencies:
    slope = None
    intercept = None
    try:
        # Logistic calibration: logit(p) as feature
        logits = np.log(y_prob_clipped / (1.0 - y_prob_clipped))
        # Simple covariance slope:
        cov_xy = np.cov(logits, y_true)[0, 1]
        var_x = np.var(logits)
        if var_x > 1e-9:
            slope = float(cov_xy / var_x)
            intercept = float(emp_win_rate - slope * np.mean(logits))
    except Exception:
        pass

    return CalibrationMetrics(
        sample_size=n,
        empirical_win_rate=emp_win_rate,
        mean_predicted_prob=mean_prob,
        brier_score=brier,
        brier_ref_score=brier_ref,
        brier_skill_score=bss,
        expected_calibration_error_ece=ece,
        calibration_slope=slope,
        calibration_intercept=intercept,
        log_loss=logloss,
    )


class LogisticRiseFallModel:
    """Analytical regularized logistic regression model for Rise/Fall probability estimation."""

    def __init__(self, l2_reg: float = 1.0, max_iter: int = 100):
        self.l2_reg = l2_reg
        self.max_iter = max_iter
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticRiseFallModel":
        """Fits model via gradient descent with standard feature scaling."""
        n, d = X.shape
        self.feature_mean = np.mean(X, axis=0)
        self.feature_std = np.std(X, axis=0)
        self.feature_std[self.feature_std == 0.0] = 1.0

        X_scaled = (X - self.feature_mean) / self.feature_std

        # Initialize weights
        w = np.zeros(d, dtype=np.float64)
        b = 0.0
        lr = 0.05

        for _ in range(self.max_iter):
            z = np.clip(np.dot(X_scaled, w) + b, -20.0, 20.0)
            p = 1.0 / (1.0 + np.exp(-z))
            err = p - y

            # Gradients with L2 regularization on weights (not bias)
            grad_w = (np.dot(X_scaled.T, err) / n) + (self.l2_reg * w / n)
            grad_b = float(np.mean(err))

            w -= lr * grad_w
            b -= lr * grad_b

        self.weights = w
        self.bias = b
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Outputs calibrated probability of Rise (CALL)."""
        if self.weights is None:
            return np.full(len(X), 0.5)

        X_scaled = (X - self.feature_mean) / self.feature_std
        z = np.clip(np.dot(X_scaled, self.weights) + self.bias, -20.0, 20.0)
        return 1.0 / (1.0 + np.exp(-z))
