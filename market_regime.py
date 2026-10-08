"""Market regime classification and discrete state space engine for 5-tick series.
Transforms backward-looking technical features into discrete observable market regimes
to measure state-conditional probabilities of uninterrupted RUNHIGH and RUNLOW events.
"""
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


def compute_expanded_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical indicator space without lookahead bias and partitions into discrete regimes."""
    p = df["price"].astype(float)
    epochs = df["epoch"].astype(int) if "epoch" in df.columns else pd.Series(df.index, index=df.index)
    d = p.diff()
    sign = np.sign(d).fillna(0)

    f = pd.DataFrame(index=df.index)
    f["epoch"] = epochs
    f["price"] = p
    f["delta"] = d
    f["sign"] = sign
    f["last_tick"] = sign

    # 1. Multi-scale Net Direction (Velocity)
    f["net3"] = sign.rolling(3).sum()
    f["net5"] = sign.rolling(5).sum()
    f["net8"] = sign.rolling(8).sum()
    f["net10"] = sign.rolling(10).sum()
    f["net20"] = sign.rolling(20).sum()

    # 2. Rolling Volatility (50-tick std dev)
    sd = d.rolling(50).std().replace(0, np.nan).bfill()
    sd = sd.fillna(1e-6)
    f["vol_sd"] = sd
    f["volatility"] = sd

    q25 = sd.quantile(0.25)
    q75 = sd.quantile(0.75)
    q95 = sd.quantile(0.95)

    vol_bin = pd.Series("NORMAL_VOL", index=df.index)
    vol_bin[sd < q25] = "LOW_VOL"
    vol_bin[sd > q75] = "HIGH_VOL"
    vol_bin[sd > q95] = "EXTREME_VOL"
    f["vol_regime"] = vol_bin
    f["vol_bin"] = vol_bin

    # 3. Multi-scale Normalized Momentum
    f["mom3"] = (p - p.shift(3)) / (sd * np.sqrt(3))
    f["mom5"] = (p - p.shift(5)) / (sd * np.sqrt(5))
    f["mom8"] = (p - p.shift(8)) / (sd * np.sqrt(8))
    f["mom10"] = (p - p.shift(10)) / (sd * np.sqrt(10))
    f["mom"] = f["mom5"]

    mom_bin = pd.Series("NEUTRAL_MOM", index=df.index)
    mom_bin[f["mom5"] > 1.5] = "STRONG_BULL"
    mom_bin[(f["mom5"] > 0.5) & (f["mom5"] <= 1.5)] = "MOD_BULL"
    mom_bin[(f["mom5"] < -0.5) & (f["mom5"] >= -1.5)] = "MOD_BEAR"
    mom_bin[f["mom5"] < -1.5] = "STRONG_BEAR"
    f["mom_bin"] = mom_bin

    # 4. Acceleration & Deceleration
    accel3 = (p - p.shift(3)) - (p.shift(3) - p.shift(6))
    f["accel3"] = accel3
    f["accel"] = accel3

    accel_bin = pd.Series("NEUTRAL_ACCEL", index=df.index)
    accel_bin[((f["mom5"] > 0) & (accel3 > 0)) | ((f["mom5"] < 0) & (accel3 < 0))] = "ACCELERATING"
    accel_bin[((f["mom5"] > 0) & (accel3 < 0)) | ((f["mom5"] < 0) & (accel3 > 0))] = "DECELERATING"
    f["accel_bin"] = accel_bin

    # 5. Discrete Streak Binning
    grp = (sign != sign.shift()).cumsum()
    streak = sign.groupby(grp).cumcount().add(1) * sign
    f["streak"] = streak

    streak_bin = pd.Series("NEUTRAL_STREAK", index=df.index)
    streak_bin[streak >= 4] = "EXTREME_UP_STREAK"
    streak_bin[(streak >= 2) & (streak <= 3)] = "MOD_UP_STREAK"
    streak_bin[(streak <= -2) & (streak >= -3)] = "MOD_DOWN_STREAK"
    streak_bin[streak <= -4] = "EXTREME_DOWN_STREAK"
    f["streak_bin"] = streak_bin

    # 6. Range Position (20-tick high/low)
    high20 = p.rolling(20).max()
    low20 = p.rolling(20).min()
    range20 = (high20 - low20).replace(0, np.nan).fillna(1e-6)
    pos = (p - low20) / range20
    f["range_position"] = pos
    f["from_high"] = (high20 - p) / sd
    f["from_low"] = (p - low20) / sd

    range_bin = pd.Series("RANGE_MID", index=df.index)
    range_bin[pos >= 0.80] = "RANGE_HIGH"
    range_bin[pos <= 0.20] = "RANGE_LOW"
    f["range_bin"] = range_bin

    # 7. Velocity Net5 Binning
    net5_bin = pd.Series("NEUTRAL_NET", index=df.index)
    net5_bin[f["net5"] >= 4] = "STRONG_BULL_NET"
    net5_bin[(f["net5"] >= 2) & (f["net5"] <= 3)] = "MOD_BULL_NET"
    net5_bin[(f["net5"] <= -2) & (f["net5"] >= -3)] = "MOD_BEAR_NET"
    net5_bin[f["net5"] <= -4] = "STRONG_BEAR_NET"
    f["net5_bin"] = net5_bin

    # 8. Fast Momentum (3-tick) Binning
    mom3_bin = pd.Series("NEUTRAL_MOM3", index=df.index)
    mom3_bin[f["mom3"] > 1.0] = "BULL_MOM3"
    mom3_bin[f["mom3"] < -1.0] = "BEAR_MOM3"
    f["mom3_bin"] = mom3_bin

    # 9. Medium-term 20-tick Momentum & Persistence
    f["mom20"] = (p - p.shift(20)) / (sd * np.sqrt(20))
    mom_pers = pd.Series("MIXED_MOM", index=df.index)
    mom_pers[(f["mom3"] > 0.5) & (f["mom5"] > 0.5) & (f["mom10"] > 0.5)] = "PERSISTENT_BULL"
    mom_pers[(f["mom3"] < -0.5) & (f["mom5"] < -0.5) & (f["mom10"] < -0.5)] = "PERSISTENT_BEAR"
    f["mom_persistence"] = mom_pers

    # 10. Momentum Exhaustion (Extreme momentum with conflicting acceleration)
    mom_exh = pd.Series("NO_EXHAUSTION", index=df.index)
    mom_exh[(f["mom5"] > 1.5) & (accel3 < 0)] = "BULL_EXHAUSTION"
    mom_exh[(f["mom5"] < -1.5) & (accel3 > 0)] = "BEAR_EXHAUSTION"
    f["mom_exhaustion"] = mom_exh

    # 11. Multi-scale Volatility Structure & Transitions
    v5 = d.rolling(5).std().bfill().fillna(1e-6)
    v20 = d.rolling(20).std().bfill().fillna(1e-6)
    f["vol5"] = v5
    f["vol20"] = v20
    f["vol_ratio"] = v5 / sd
    f["vol_transition"] = np.where(v5 > v20, "EXPANDING_VOL", "CONTRACTING_VOL")

    # 12. Directional Structure & Streak Characteristics
    f["up_streak"] = np.maximum(0, streak)
    f["down_streak"] = np.maximum(0, -streak)
    f["streak_mean_10"] = streak.abs().rolling(10).mean()
    f["interruption_freq_20"] = (sign != sign.shift()).rolling(20).mean().fillna(0.0)

    # Direction history encodings (last 3, 5 directions)
    s1 = np.where(sign > 0, "U", np.where(sign < 0, "D", "F"))
    s2 = np.where(sign.shift(1) > 0, "U", np.where(sign.shift(1) < 0, "D", "F"))
    s3 = np.where(sign.shift(2) > 0, "U", np.where(sign.shift(2) < 0, "D", "F"))
    f["dir_3"] = [f"{a}{b}{c}" for a, b, c in zip(s3, s2, s1)]

    # 13. Market Structure: Imbalance, Reversals, Alternation, Persistence
    f["imbalance_10"] = f["net10"] / 10.0
    f["imbalance_20"] = f["net20"] / 20.0
    reversal_10 = (sign != sign.shift()).rolling(10).mean().fillna(0.0)
    f["reversal_freq_10"] = reversal_10
    f["alternation_freq_10"] = ((sign * sign.shift()) < 0).rolling(10).mean().fillna(0.0)
    f["persistence_10"] = (sign == sign.shift()).rolling(10).mean().fillna(0.0)

    struct_bin = pd.Series("NEUTRAL_STRUCT", index=df.index)
    struct_bin[(f["imbalance_10"].abs() >= 0.6) & (f["persistence_10"] >= 0.6)] = "TRENDING"
    struct_bin[reversal_10 >= 0.7] = "CHOPPY_REVERSAL"
    struct_bin[f["range_bin"] == "RANGE_MID"] = "RANGE_BOUND"
    f["structure_bin"] = struct_bin

    # Reversal transition indicators
    f["first_down_after_uptrend"] = (f["net5"].shift(1) >= 3) & (sign < 0)
    f["first_up_after_downtrend"] = (f["net5"].shift(1) <= -3) & (sign > 0)

    # 14. Composite Market Regime Key
    # Format: [MOM]__[STREAK]__[VOL]
    regimes = []
    for row in f.itertuples():
        regimes.append(f"{row.mom_bin}__{row.streak_bin}__{row.vol_bin}")
    f["market_regime"] = regimes
    f["market_state"] = regimes

    return f.dropna()


