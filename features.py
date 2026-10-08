"""Feature engineering pipeline and data integrity validation for tick series.
Computes technical indicators without lookahead bias and enforces contract outcome rules.
"""
from datetime import datetime, timezone
from typing import Tuple, List
import time
import numpy as np
import pandas as pd


def validate_data(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validates tick data integrity, flagging artificial or corrupt series.
    
    Checks:
    1. Exact-constant epoch intervals (e.g. synthetic data with 0 delta variance).
    2. Round-number start times (e.g. epoch % 100000 == 0).
    3. Date ranges far from today (> 2 years old or in the future).
    4. Impossible price patterns (non-positive prices, zero variance, constant price steps).
    
    Returns:
        (is_valid: bool, issues: List[str])
    """
    issues: List[str] = []
    
    if "price" not in df.columns:
        issues.append("Missing required 'price' column.")
        return False, issues

    # 1. Price sanity checks
    prices = df["price"].astype(float)
    if (prices <= 0).any():
        issues.append("Detected non-positive price values (price <= 0).")
    if prices.std() == 0:
        issues.append("Detected zero price variance (flat constant series).")
        
    diffs = prices.diff().dropna()
    if len(diffs) > 100 and (diffs.abs() == diffs.abs().iloc[0]).mean() > 0.95:
        issues.append("Detected unnatural constant absolute price increments.")

    # 2. Epoch timestamp checks
    if "epoch" in df.columns:
        epochs = df["epoch"].astype(float)
        gaps = epochs.diff().dropna()
        
        # Exact-constant epoch gap detection (synthetic random-walk generator artifact)
        if len(gaps) > 10 and gaps.std() == 0.0:
            val = gaps.iloc[0]
            issues.append(f"Exact-constant epoch gap ({val}s across all rows). Synthetic data detected.")
            
        # Round-number start time detection (e.g. 1728000000, 1700000000)
        start_epoch = int(epochs.iloc[0])
        if start_epoch % 100000 == 0:
            issues.append(f"Suspiciously round start epoch ({start_epoch}). Synthetic generator origin detected.")
            
        # Date range relative to current timestamp
        current_time = time.time()
        start_dt = datetime.fromtimestamp(epochs.iloc[0], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(epochs.iloc[-1], tz=timezone.utc)
        
        # Future ticks check (allow max 60s clock skew)
        if epochs.iloc[-1] > current_time + 60:
            issues.append(f"Data extends into the future (last tick: {end_dt.isoformat()}, system time: {datetime.fromtimestamp(current_time, tz=timezone.utc).isoformat()}).")
        elif epochs.iloc[-1] < current_time - 86400 * 365 * 2:
            issues.append(f"Date range is far from today ({start_dt.date()} to {end_dt.date()}).")

    is_valid = len(issues) == 0
    return is_valid, issues


def check_data_coverage(df: pd.DataFrame, duration_ticks: int = 5) -> dict:

    """Analyzes historical dataset coverage and flags insufficient duration or sample size.
    
    Reports:
        total_ticks, date_start, date_end, duration_days, observations,
        usable_contract_windows, is_sufficient, warnings
    """
    total_ticks = len(df)
    usable_windows = max(0, total_ticks - (duration_ticks + 1))
    warnings: List[str] = []

    date_start_str = "UNKNOWN"
    date_end_str = "UNKNOWN"
    duration_days = 0.0

    if "epoch" in df.columns and total_ticks > 0:
        epochs = df["epoch"].astype(float)
        start_epoch = epochs.iloc[0]
        end_epoch = epochs.iloc[-1]
        dt_start = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
        dt_end = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
        date_start_str = dt_start.isoformat()
        date_end_str = dt_end.isoformat()
        duration_days = max(0.0, (end_epoch - start_epoch) / 86400.0)

        if duration_days < 0.5:
            warnings.append(f"Insufficient historical duration ({duration_days:.2f} days < 0.5 days). Short window risks single-regime overfitting.")
        if usable_windows < 2000:
            warnings.append(f"Small usable sample size ({usable_windows:,} contract windows < 2,000 required).")
    else:
        warnings.append("Missing epoch column; unable to calculate calendar duration.")

    return {
        "total_ticks": total_ticks,
        "date_start": date_start_str,
        "date_end": date_end_str,
        "duration_days": round(duration_days, 3),
        "observations": total_ticks,
        "usable_contract_windows": usable_windows,
        "is_sufficient": len(warnings) == 0,
        "warnings": warnings
    }


def compute_features(df: pd.DataFrame, duration_ticks: int = 5) -> pd.DataFrame:

    """Calculates quantitative features and forward outcome targets for 5-tick contracts.
    
    Outcome Rule:
    - Entry price = tick i+1
    - Exit price = tick i+duration_ticks (tick i+5)
    - Rise win: exit > entry
    - Fall win: exit < entry
    - Ties (exit == entry): Count as loss for both directions.
    
    All indicator features at index i use ONLY information available at or before tick i.
    """
    p = df["price"].astype(float)
    d = p.diff()
    sign = np.sign(d).fillna(0)

    f = pd.DataFrame(index=df.index)
    f["price"] = p
    if "epoch" in df.columns:
        f["epoch"] = df["epoch"].astype(int)

    # 1. Directional Streak (+ for consecutive up ticks, - for consecutive down ticks)
    # Resets on direction reversal or zero-delta tick
    direction_change = (sign != sign.shift()).cumsum()
    f["streak"] = sign.groupby(direction_change).cumcount().add(1) * sign

    # 2. Rolling Net Direction (Velocity over 5, 10, and 20 ticks)
    f["net5"] = sign.rolling(5).sum()
    f["net10"] = sign.rolling(10).sum()
    f["net20"] = sign.rolling(20).sum()

    # 3. Volatility (50-tick rolling standard deviation of price changes)
    sd = d.rolling(50).std()
    f["volatility"] = sd

    # 4. Z-scored 5-tick Momentum
    f["mom"] = (p - p.shift(5)) / (sd * np.sqrt(5))

    # 5. Acceleration (second derivative: change in 3-tick move)
    f["accel"] = (p - p.shift(3)) - (p.shift(3) - p.shift(6))

    # 6. Distance from recent 20-tick extremes
    f["from_high"] = (p.rolling(20).max() - p) / sd
    f["from_low"] = (p - p.rolling(20).min()) / sd

    # 7. Last tick direction and aliases
    f["last_tick"] = sign
    f["sign"] = sign
    f["mom5"] = f["mom"]
    f["accel3"] = f["accel"]

    # Reversal and range aliases
    f["first_down_after_uptrend"] = (f["net5"].shift(1) >= 3) & (sign < 0)
    f["first_up_after_downtrend"] = (f["net5"].shift(1) <= -3) & (sign > 0)
    high20 = p.rolling(20).max()
    low20 = p.rolling(20).min()
    rng20 = (high20 - low20).replace(0, np.nan).fillna(1e-6)
    f["range_position"] = (p - low20) / rng20

    # 8. 5-Tick Contract Outcome Targets
    # Deriv contract rule: entry = tick i+1, exit = tick i+1+duration_ticks (tick i+6 for 5-tick contracts)
    entry = p.shift(-1)
    exit_ = p.shift(-(1 + duration_ticks))

    f["entry_price"] = entry
    f["exit_price"] = exit_
    
    # Ties count as loss for both CALL and PUT
    f["rise_win"] = (exit_ > entry).astype(float)
    f["fall_win"] = (exit_ < entry).astype(float)

    # 5-step RUNHIGH and RUNLOW (consecutive transitions after entry: S_0 -> S_1 -> S_2 -> S_3 -> S_4 -> S_5)
    up_steps = []
    down_steps = []
    for step in range(1, duration_ticks + 1):
        t_curr = p.shift(-step)
        t_next = p.shift(-(step + 1))
        up_steps.append(t_next > t_curr)
        down_steps.append(t_next < t_curr)
    
    all_up = up_steps[0]
    all_down = down_steps[0]
    for u, d in zip(up_steps[1:], down_steps[1:]):
        all_up = all_up & u
        all_down = all_down & d
    f["runhigh_win"] = all_up.astype(float)
    f["runlow_win"] = all_down.astype(float)
    f["only_ups_win"] = f["runhigh_win"]
    f["only_downs_win"] = f["runlow_win"]

    # Exclude lookahead edges where forward exit is unknown
    f.loc[p.shift(-(1 + duration_ticks)).isna(), ["rise_win", "fall_win", "runhigh_win", "runlow_win", "only_ups_win", "only_downs_win"]] = np.nan
    return f.dropna().copy()

