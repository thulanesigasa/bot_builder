"""Risk management engine enforcing consecutive-loss cooldowns,
UTC-daily loss limit resets, position sizing, and capital protection.
"""
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class RiskState:
    current_balance: float
    daily_start_balance: float
    consecutive_losses: int
    peak_balance: float
    max_drawdown_amount: float
    max_drawdown_pct: float
    total_trades: int
    total_wins: int
    total_losses: int
    cooldown_count: int
    daily_reset_count: int
    is_paused: bool
    pause_reason: str


class RiskManager:
    """Enforces position sizing, consecutive-loss cooldowns, and UTC day loss limits."""

    def __init__(
        self,
        initial_balance: float = 1000.0,
        risk_per_trade_pct: float = 0.01,
        max_stake: float = 10.0,
        max_consecutive_losses: int = 3,
        cooldown_ticks: int = 50,
        daily_loss_limit_pct: float = 0.05,
        research_mode: bool = False
    ):
        self.initial_balance = initial_balance
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_stake = max_stake
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_ticks = cooldown_ticks
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.research_mode = research_mode

        # Balances
        self.current_balance = initial_balance
        self.daily_start_balance = initial_balance
        self.peak_balance = initial_balance
        
        # Tracking
        self.consecutive_losses = 0
        self.cooldown_until_tick_idx: int = -1
        self.current_utc_day: Optional[int] = None
        self.daily_loss_limit_hit = False
        
        self.max_drawdown_amount = 0.0
        self.max_drawdown_pct = 0.0
        self.total_trades = 0
        self.total_wins = 0
        self.total_losses = 0
        self.cooldown_count = 0
        self.daily_reset_count = 0

    def check_day_reset(self, epoch: Optional[int]):
        """Resets daily loss counter when moving to a new UTC calendar day."""
        if epoch is None or epoch <= 0:
            return
        utc_day = int(epoch) // 86400
        if self.current_utc_day is None:
            self.current_utc_day = utc_day
            self.daily_start_balance = self.current_balance
        elif utc_day != self.current_utc_day:
            self.current_utc_day = utc_day
            self.daily_start_balance = self.current_balance
            self.daily_loss_limit_hit = False
            self.daily_reset_count += 1

    def can_trade(self, tick_idx: int = 0, epoch: Optional[int] = None) -> Tuple[bool, str]:
        """Validates if risk constraints allow placing a new trade."""
        if self.research_mode:
            return True, "Research mode (unconstrained signals)"

        if self.current_balance <= 0:
            return False, "Account balance depleted."

        # Check UTC day boundary
        self.check_day_reset(epoch)

        # 1. Consecutive-loss cooldown check (temporary pause, not permanent halt)
        if tick_idx < self.cooldown_until_tick_idx:
            remaining = self.cooldown_until_tick_idx - tick_idx
            return False, f"Cooldown: Paused for {remaining} more ticks after consecutive losses"

        # 2. Daily loss limit check (resets at 00:00 UTC)
        if self.daily_loss_limit_hit:
            return False, "Paused: Hit daily loss limit for current UTC day"
            
        daily_loss = self.daily_start_balance - self.current_balance
        max_allowed_loss = self.daily_start_balance * self.daily_loss_limit_pct
        if daily_loss >= max_allowed_loss:
            self.daily_loss_limit_hit = True
            return False, f"Paused: Daily loss reached {self.daily_loss_limit_pct:.1%} limit"

        return True, "Trading allowed"

    def calculate_stake(self) -> float:
        """Determines position size based on current equity or research mode."""
        if self.research_mode:
            return 1.0  # Flat $1 stake in research mode
        stake = self.current_balance * self.risk_per_trade_pct
        return round(min(stake, self.max_stake, self.current_balance), 2)

    def record_trade(
        self,
        won: bool,
        stake: float,
        payout_ratio: float = 0.953,
        tick_idx: int = 0,
        epoch: Optional[int] = None
    ):
        """Updates account state and risk metrics after a trade outcome."""
        self.check_day_reset(epoch)
        self.total_trades += 1
        
        if won:
            profit = round(stake * payout_ratio, 2)
            self.current_balance += profit
            self.consecutive_losses = 0
            self.total_wins += 1
        else:
            self.current_balance -= round(stake, 2)
            self.consecutive_losses += 1
            self.total_losses += 1

            # Trigger consecutive-loss cooldown
            if not self.research_mode and self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until_tick_idx = tick_idx + self.cooldown_ticks
                self.consecutive_losses = 0  # reset for post-cooldown
                self.cooldown_count += 1

        # Track Drawdown
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        dd_amt = self.peak_balance - self.current_balance
        dd_pct = (dd_amt / self.peak_balance) if self.peak_balance > 0 else 0.0
        if dd_amt > self.max_drawdown_amount:
            self.max_drawdown_amount = dd_amt
            self.max_drawdown_pct = dd_pct

    def get_state(self, tick_idx: int = 0, epoch: Optional[int] = None) -> RiskState:
        """Returns snapshot of current risk status."""
        can_run, reason = self.can_trade(tick_idx, epoch)
        return RiskState(
            current_balance=round(self.current_balance, 2),
            daily_start_balance=round(self.daily_start_balance, 2),
            consecutive_losses=self.consecutive_losses,
            peak_balance=round(self.peak_balance, 2),
            max_drawdown_amount=round(self.max_drawdown_amount, 2),
            max_drawdown_pct=round(self.max_drawdown_pct, 4),
            total_trades=self.total_trades,
            total_wins=self.total_wins,
            total_losses=self.total_losses,
            cooldown_count=self.cooldown_count,
            daily_reset_count=self.daily_reset_count,
            is_paused=not can_run,
            pause_reason=reason
        )
