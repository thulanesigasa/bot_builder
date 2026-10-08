"""Explicit Feature Schema and Parity Verification for Deriv 5-Tick Models (V1.5.3).

Ensures deterministic mathematical parity between:
1. Offline historical training feature generation.
2. Online live streaming sliding window feature extraction.

Guarantees exact feature names, ordering, lookback requirements, and binning boundaries.
"""
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd

FEATURE_SCHEMA_VERSION: str = "1.5.3"

# Canonical feature list and order
CANONICAL_FEATURE_NAMES: List[str] = [
    "mom_bin",
    "streak_bin",
    "vol_bin",
    "accel_bin"
]

CANONICAL_FEATURE_LOOKBACK: int = 25  # Minimum ticks required to reliably compute lookback windows


@dataclass(frozen=True)
class FeatureSchema:
    schema_version: str
    feature_names: List[str]
    lookback_window: int
    contract_duration_ticks: int = 5
    allow_missing: bool = False

    def validate_features(self, features: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verifies that a feature dictionary satisfies canonical schema requirements."""
        missing = [f for f in self.feature_names if f not in features or features[f] is None]
        if missing and not self.allow_missing:
            return False, missing
        return True, []


CANONICAL_SCHEMA = FeatureSchema(
    schema_version=FEATURE_SCHEMA_VERSION,
    feature_names=CANONICAL_FEATURE_NAMES,
    lookback_window=CANONICAL_FEATURE_LOOKBACK
)


def extract_discrete_market_state(
    df_or_ticks: Any,
    min_ticks: int = CANONICAL_FEATURE_LOOKBACK
) -> Tuple[Dict[str, str], str]:
    """Computes features and discretized state from tick history (DataFrame or list of dicts).
    
    Returns:
        (feature_dict, market_state_string)
    """
    if isinstance(df_or_ticks, list):
        if len(df_or_ticks) < min_ticks:
            return {}, "INSUFFICIENT_TICKS"
        df = pd.DataFrame(df_or_ticks)
    elif isinstance(df_or_ticks, pd.DataFrame):
        if len(df_or_ticks) < min_ticks:
            return {}, "INSUFFICIENT_TICKS"
        df = df_or_ticks.copy()
    else:
        return {}, "INVALID_INPUT"

    # Ensure required columns exist
    if "price" not in df.columns:
        if "quote" in df.columns:
            df["price"] = df["quote"]
        else:
            return {}, "MISSING_PRICE_COLUMN"

    prices = df["price"].astype(float).values
    n = len(prices)

    # 1. Price Momentum (5-tick return)
    ret_5 = (prices[-1] - prices[-6]) if n >= 6 else 0.0
    if ret_5 > 0.005:
        mom_bin = "STRONG_BULL"
    elif ret_5 > 0.0005:
        mom_bin = "MILD_BULL"
    elif ret_5 < -0.005:
        mom_bin = "STRONG_BEAR"
    elif ret_5 < -0.0005:
        mom_bin = "MILD_BEAR"
    else:
        mom_bin = "NEUTRAL"

    # 2. Consecutive Directional Streak
    streak = 0
    for i in range(n - 1, 0, -1):
        diff = prices[i] - prices[i - 1]
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

    if streak >= 5:
        streak_bin = "EXTREME_UP_STREAK"
    elif streak >= 3:
        streak_bin = "HIGH_UP_STREAK"
    elif streak <= -5:
        streak_bin = "EXTREME_DOWN_STREAK"
    elif streak <= -3:
        streak_bin = "HIGH_DOWN_STREAK"
    else:
        streak_bin = "NEUTRAL_STREAK"

    # 3. Realized Volatility (10-tick rolling standard deviation of differences)
    if n >= 11:
        diffs = np.diff(prices[-11:])
        vol = float(np.std(diffs))
        if vol > 0.005:
            vol_bin = "HIGH_VOL"
        elif vol < 0.001:
            vol_bin = "LOW_VOL"
        else:
            vol_bin = "MED_VOL"
    else:
        vol_bin = "MED_VOL"

    # 4. Acceleration (diff of 3-tick return vs prior 3-tick return)
    if n >= 7:
        r_now = prices[-1] - prices[-4]
        r_prior = prices[-4] - prices[-7]
        accel = r_now - r_prior
        if accel > 0.002:
            accel_bin = "ACCEL_UP"
        elif accel < -0.002:
            accel_bin = "ACCEL_DOWN"
        else:
            accel_bin = "NEUTRAL_ACCEL"
    else:
        accel_bin = "NEUTRAL_ACCEL"

    feat_dict = {
        "mom_bin": mom_bin,
        "streak_bin": streak_bin,
        "vol_bin": vol_bin,
        "accel_bin": accel_bin
    }

    state_parts = [f"{k}={feat_dict[k]}" for k in CANONICAL_FEATURE_NAMES if k in feat_dict]
    market_state = " & ".join(state_parts)

    return feat_dict, market_state


def verify_feature_parity(ticks_full: pd.DataFrame, slice_window: int = 50) -> bool:
    """Validates that slicing the end of a DataFrame produces identical features to batch calculation."""
    if len(ticks_full) < slice_window:
        return True
    
    # Batch extraction on entire DF
    feat_batch, state_batch = extract_discrete_market_state(ticks_full)
    
    # Sliced extraction simulating sliding live buffer
    sliced_df = ticks_full.iloc[-slice_window:].copy()
    feat_slice, state_slice = extract_discrete_market_state(sliced_df)
    
    return (feat_batch == feat_slice) and (state_batch == state_slice)
