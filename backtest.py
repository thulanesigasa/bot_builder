"""Upgraded probability-driven event-driven backtesting engine for 5-tick contracts.
Integrates QuoteEngine for direction-specific payouts, ContractOutcomeModel for
execution fidelity, and TradeJournal for granular performance attribution.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np

from risk import RiskManager
from quote_engine import QuoteEngine, ProposalQuote
from contract_model import ContractOutcomeModel
from trade_journal import TradeJournal, TradeRecord
from datetime import datetime, timezone


@dataclass
class BacktestResult:
    mode: str  # 'research' or 'risk_managed'
    total_trades: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    net_profit: float
    profit_factor: float
    max_drawdown_amount: float
    max_drawdown_pct: float
    initial_balance: float
    final_balance: float
    equity_curve: List[float]
    journal: TradeJournal
    cooldown_count: int = 0
    daily_reset_count: int = 0


def run_probability_backtest(
    df: pd.DataFrame,
    quote_engine: Optional[QuoteEngine] = None,
    initial_balance: float = 1000.0,
    risk_per_trade_pct: float = 0.0025,  # 0.25% per trade
    max_stake: float = 5.0,
    max_consecutive_losses: int = 3,
    cooldown_ticks: int = 50,
    daily_loss_limit_pct: float = 0.05,
    mode: str = "research",
    allow_overlapping: bool = False,
    symbol: str = "R_75"
) -> BacktestResult:
    """Executes a backtest using direction-specific quotes and contract lifecycle modeling."""
    is_research = (mode == "research")
    if quote_engine is None:
        quote_engine = QuoteEngine()

    risk = RiskManager(
        initial_balance=initial_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        max_stake=max_stake,
        max_consecutive_losses=max_consecutive_losses,
        cooldown_ticks=cooldown_ticks,
        daily_loss_limit_pct=daily_loss_limit_pct,
        research_mode=is_research
    )

    journal = TradeJournal()
    equity_curve: List[float] = [initial_balance]
    last_exit_idx = -1
    total_gains = 0.0
    total_losses_amount = 0.0
    ties_count = 0

    n = len(df)
    has_epoch = "epoch" in df.columns

    for i in range(n):
        row = df.iloc[i]
        sig = row.get("signal", "NO_TRADE")

        if sig not in ("UP", "DOWN", "RISE", "FALL", "RUNHIGH", "RUNLOW"):
            continue

        sig_norm = "UP" if sig in ("UP", "RISE", "RUNHIGH") else "DOWN"

        # Prevent overlapping entries if configured
        if not allow_overlapping and i < last_exit_idx:
            continue

        cur_epoch = int(row["epoch"]) if has_epoch else i
        can_run, _ = risk.can_trade(tick_idx=i, epoch=cur_epoch)
        if not can_run:
            continue

        quote = quote_engine.get_quote(sig_norm, epoch=cur_epoch)
        if quote is None:
            # STRICT RULE: No quote available -> NO TRADE
            continue

        base_stake = quote.stake if is_research else min(risk.calculate_stake(), quote.stake)
        if base_stake <= 0:
            continue

        entry_p = row.get("entry_price")
        exit_p = row.get("exit_price")
        if pd.isna(entry_p) or pd.isna(exit_p):
            continue

        # Outcome determination (RUNHIGH / RUNLOW: 5 consecutive uninterrupted transitions)
        is_high_payout = quote.contract_type in ("RUNHIGH", "RUNLOW", "ONLY_UPS", "ONLY_DOWNS")
        if is_high_payout:
            if sig_norm == "UP":
                won = bool(row.get("runhigh_win", row.get("only_ups_win", 0.0)) == 1.0)
            else:
                won = bool(row.get("runlow_win", row.get("only_downs_win", 0.0)) == 1.0)
            tied = False
        else:
            if sig_norm == "UP":
                won = bool(exit_p > entry_p)
                tied = bool(exit_p == entry_p)
            else:
                won = bool(exit_p < entry_p)
                tied = bool(exit_p == entry_p)

            if tied:
                won = False
                ties_count += 1

        profit_on_win = base_stake * quote.payout_ratio
        pnl = round(profit_on_win, 2) if won else -round(base_stake, 2)

        if won:
            total_gains += pnl
        else:
            total_losses_amount += abs(pnl)

        risk.record_trade(won, base_stake, quote.payout_ratio, tick_idx=i, epoch=cur_epoch)
        current_bal = risk.current_balance
        equity_curve.append(current_bal)

        # Telemetry & Trade Logging
        dt_str = datetime.fromtimestamp(cur_epoch, tz=timezone.utc).isoformat() if has_epoch else str(i)
        market_st = str(row.get("market_state", "UNKNOWN"))
        mom_val = float(row.get("mom5", 0.0))
        accel_val = float(row.get("accel3", 0.0))
        streak_val = int(row.get("streak", 0))
        vol_reg = str(row.get("vol_regime", "NORMAL_VOL"))
        range_pos = float(row.get("range_position", 0.5))

        # Expected value modeling
        est_prob = float(row.get("estimated_prob", quote.implied_probability))
        ev_dollar, _, _ = quote_engine.calculate_expected_value(est_prob, base_stake, base_stake + profit_on_win)

        record = TradeRecord(
            timestamp_utc=dt_str,
            epoch=cur_epoch,
            symbol=symbol,
            setup_name=str(row.get("setup_name", "SIGNAL")),
            engine_type=str(row.get("engine_type", "directional")),
            direction=sig_norm,
            entry_price=float(entry_p),
            exit_price=float(exit_p),
            is_win=won,
            is_tie=tied,
            market_state=market_st,
            momentum=mom_val,
            acceleration=accel_val,
            streak=streak_val,
            volatility_regime=vol_reg,
            range_position=range_pos,
            stake=base_stake,
            actual_payout=base_stake + profit_on_win,
            required_probability=quote.implied_probability,
            estimated_probability=est_prob,
            expected_value=ev_dollar,
            net_pnl=pnl
        )
        journal.record_trade(record)
        # Entry S_0 is i+1, Expiry S_5 is i+6 -> next available trade after completion is i+6
        last_exit_idx = i + 6


    t_count = len(journal.trades)
    w_count = sum(1 for t in journal.trades if t.is_win)
    l_count = t_count - w_count
    wr = (w_count / t_count) if t_count > 0 else 0.0
    net_profit = risk.current_balance - initial_balance
    pf = (total_gains / total_losses_amount) if total_losses_amount > 0 else (np.inf if total_gains > 0 else 0.0)

    return BacktestResult(
        mode=mode,
        total_trades=t_count,
        wins=w_count,
        losses=l_count,
        ties=ties_count,
        win_rate=wr,
        net_profit=round(net_profit, 2),
        profit_factor=round(pf, 2),
        max_drawdown_amount=round(risk.max_drawdown_amount, 2),
        max_drawdown_pct=round(risk.max_drawdown_pct, 4),
        initial_balance=initial_balance,
        final_balance=round(risk.current_balance, 2),
        equity_curve=equity_curve,
        journal=journal,
        cooldown_count=risk.cooldown_count,
        daily_reset_count=risk.daily_reset_count
    )


# Backward-compatible wrapper
def run_backtest(
    df: pd.DataFrame,
    payout_ratio: float = 0.95,
    initial_balance: float = 1000.0,
    risk_per_trade_pct: float = 0.0025,
    max_stake: float = 5.0,
    max_consecutive_losses: int = 3,
    cooldown_ticks: int = 50,
    daily_loss_limit_pct: float = 0.05,
    duration_ticks: int = 5,
    mode: str = "risk_managed",
    allow_overlapping: bool = False
) -> BacktestResult:
    qe = QuoteEngine(default_up_payout_ratio=payout_ratio, default_down_payout_ratio=payout_ratio)
    return run_probability_backtest(
        df=df,
        quote_engine=qe,
        initial_balance=initial_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        max_stake=max_stake,
        max_consecutive_losses=max_consecutive_losses,
        cooldown_ticks=cooldown_ticks,
        daily_loss_limit_pct=daily_loss_limit_pct,
        mode=mode,
        allow_overlapping=allow_overlapping
    )
