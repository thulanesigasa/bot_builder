"""Tests for risk manager cooldowns, UTC day resets, and data integrity validator.
"""
import numpy as np
import pandas as pd
import pytest

from risk import RiskManager
from features import validate_data


def test_consecutive_loss_triggers_cooldown_not_halt():
    risk = RiskManager(
        initial_balance=1000.0,
        max_consecutive_losses=3,
        cooldown_ticks=50,
        research_mode=False
    )
    
    # 3 consecutive losses
    risk.record_trade(won=False, stake=10.0, tick_idx=10)
    risk.record_trade(won=False, stake=10.0, tick_idx=15)
    risk.record_trade(won=False, stake=10.0, tick_idx=20)
    
    # At tick 21 (during cooldown 20 + 50 = 70), trading must be paused
    can_trade, reason = risk.can_trade(tick_idx=21)
    assert not can_trade
    assert "Cooldown" in reason
    
    # At tick 71 (cooldown expired), trading must automatically resume!
    can_trade_after, _ = risk.can_trade(tick_idx=71)
    assert can_trade_after


def test_utc_daily_loss_reset():
    risk = RiskManager(
        initial_balance=1000.0,
        daily_loss_limit_pct=0.05,  # 5% = $50 loss limit
        research_mode=False
    )
    
    day1_epoch = 1700000000  # UTC Day 19675
    # Lose $60 on Day 1
    risk.record_trade(won=False, stake=30.0, epoch=day1_epoch)
    risk.record_trade(won=False, stake=30.0, epoch=day1_epoch)
    
    # Day 1 is now over limit
    can_run_day1, reason = risk.can_trade(epoch=day1_epoch)
    assert not can_run_day1
    assert "daily loss" in reason.lower()
    
    # On next day (epoch + 86400), daily loss limit must reset!
    day2_epoch = day1_epoch + 86400
    can_run_day2, _ = risk.can_trade(epoch=day2_epoch)
    assert can_run_day2


def test_validate_data_flags_synthetic_constant_gaps():
    # Synthetic data with constant gap of exactly 2.0s
    epochs = np.arange(1728000000, 1728000000 + 100 * 2, 2)
    prices = 100.0 + np.cumsum(np.random.normal(0, 1, 100))
    df = pd.DataFrame({"epoch": epochs, "price": prices})
    
    is_valid, issues = validate_data(df)
    assert not is_valid
    assert any("Exact-constant epoch gap" in i for i in issues)
    assert any("Suspiciously round start epoch" in i for i in issues)
