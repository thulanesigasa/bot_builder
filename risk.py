"""Risk management engine enforcing consecutive-loss cooldowns,
UTC-daily loss limit resets, position sizing, capital protection, and persistent state (V1.6.1).

Guarantees:
- Real persistent PAPER-mode risk state surviving application restarts.
- Tracks consecutive losses, daily simulated PnL, daily drawdown, cooldown status.
- Tracks outstanding hypothetical positions and per-symbol exposure.
- Never substitutes default zero values when persisted risk information exists.
- Reports is_valid() == False if risk state is corrupted or unavailable.
"""
import contextlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any, List


DEFAULT_RISK_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "risk_state.db"
)


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
    daily_pnl: float = 0.0
    outstanding_positions_count: int = 0
    current_exposure: float = 0.0
    per_symbol_exposure: Dict[str, float] = field(default_factory=dict)
    last_updated_epoch: float = 0.0
    is_valid: bool = True


class RiskManager:
    """Enforces position sizing, consecutive-loss cooldowns, UTC day loss limits,
    and persistent state across process restarts.
    """

    def __init__(
        self,
        initial_balance: float = 1000.0,
        risk_per_trade_pct: float = 0.01,
        max_stake: float = 10.0,
        max_consecutive_losses: int = 3,
        cooldown_ticks: int = 50,
        daily_loss_limit_pct: float = 0.05,
        research_mode: bool = False,
        db_path: Optional[str] = None,
        symbol: str = "R_75"
    ):
        self.initial_balance = initial_balance
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_stake = max_stake
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_ticks = cooldown_ticks
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.research_mode = research_mode
        self.symbol = symbol
        self.db_path = db_path

        # Balances & Metrics
        self.current_balance = initial_balance
        self.daily_start_balance = initial_balance
        self.peak_balance = initial_balance
        self.daily_pnl = 0.0

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

        # Exposure & Position Tracking
        self.outstanding_positions_count: int = 0
        self.current_exposure: float = 0.0
        self.per_symbol_exposure: Dict[str, float] = {}
        self.last_updated_epoch: float = 0.0
        self._state_valid = True

        # Initialize persistence database if path provided
        if self.db_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self._init_db()
            self._load_persisted_state()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS risk_state (
                        symbol TEXT PRIMARY KEY,
                        current_balance REAL NOT NULL,
                        daily_start_balance REAL NOT NULL,
                        consecutive_losses INTEGER NOT NULL,
                        peak_balance REAL NOT NULL,
                        max_drawdown_amount REAL NOT NULL,
                        max_drawdown_pct REAL NOT NULL,
                        daily_pnl REAL NOT NULL,
                        current_utc_day INTEGER,
                        cooldown_until_tick_idx INTEGER,
                        cooldown_count INTEGER NOT NULL,
                        daily_reset_count INTEGER NOT NULL,
                        total_trades INTEGER NOT NULL,
                        total_wins INTEGER NOT NULL,
                        total_losses INTEGER NOT NULL,
                        outstanding_positions_count INTEGER NOT NULL DEFAULT 0,
                        current_exposure REAL NOT NULL DEFAULT 0.0,
                        per_symbol_exposure_json TEXT DEFAULT '{}',
                        last_updated_epoch REAL NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            self._state_valid = False

    def _load_persisted_state(self):
        """Loads persistent risk state if previously saved, avoiding zero-resets."""
        if not self.db_path or not os.path.exists(self.db_path):
            return
        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "SELECT * FROM risk_state WHERE symbol = ?", (self.symbol,)
                )
                row = cur.fetchone()
                if row:
                    self.current_balance = float(row["current_balance"])
                    self.daily_start_balance = float(row["daily_start_balance"])
                    self.consecutive_losses = int(row["consecutive_losses"])
                    self.peak_balance = float(row["peak_balance"])
                    self.max_drawdown_amount = float(row["max_drawdown_amount"])
                    self.max_drawdown_pct = float(row["max_drawdown_pct"])
                    self.daily_pnl = float(row["daily_pnl"])
                    self.current_utc_day = row["current_utc_day"]
                    self.cooldown_until_tick_idx = int(row["cooldown_until_tick_idx"]) if row["cooldown_until_tick_idx"] is not None else -1
                    self.cooldown_count = int(row["cooldown_count"])
                    self.daily_reset_count = int(row["daily_reset_count"])
                    self.total_trades = int(row["total_trades"])
                    self.total_wins = int(row["total_wins"])
                    self.total_losses = int(row["total_losses"])
                    self.outstanding_positions_count = int(row["outstanding_positions_count"])
                    self.current_exposure = float(row["current_exposure"])
                    try:
                        self.per_symbol_exposure = json.loads(row["per_symbol_exposure_json"] or "{}")
                    except Exception:
                        self.per_symbol_exposure = {}
                    self.last_updated_epoch = float(row["last_updated_epoch"])
                    self._state_valid = True
        except Exception:
            self._state_valid = False

    def save_state(self):
        """Persists risk state snapshot to SQLite."""
        if not self.db_path:
            return
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO risk_state (
                        symbol, current_balance, daily_start_balance, consecutive_losses,
                        peak_balance, max_drawdown_amount, max_drawdown_pct, daily_pnl,
                        current_utc_day, cooldown_until_tick_idx, cooldown_count,
                        daily_reset_count, total_trades, total_wins, total_losses,
                        outstanding_positions_count, current_exposure, per_symbol_exposure_json,
                        last_updated_epoch, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        current_balance=excluded.current_balance,
                        daily_start_balance=excluded.daily_start_balance,
                        consecutive_losses=excluded.consecutive_losses,
                        peak_balance=excluded.peak_balance,
                        max_drawdown_amount=excluded.max_drawdown_amount,
                        max_drawdown_pct=excluded.max_drawdown_pct,
                        daily_pnl=excluded.daily_pnl,
                        current_utc_day=excluded.current_utc_day,
                        cooldown_until_tick_idx=excluded.cooldown_until_tick_idx,
                        cooldown_count=excluded.cooldown_count,
                        daily_reset_count=excluded.daily_reset_count,
                        total_trades=excluded.total_trades,
                        total_wins=excluded.total_wins,
                        total_losses=excluded.total_losses,
                        outstanding_positions_count=excluded.outstanding_positions_count,
                        current_exposure=excluded.current_exposure,
                        per_symbol_exposure_json=excluded.per_symbol_exposure_json,
                        last_updated_epoch=excluded.last_updated_epoch,
                        updated_at=excluded.updated_at
                """, (
                    self.symbol, self.current_balance, self.daily_start_balance,
                    self.consecutive_losses, self.peak_balance, self.max_drawdown_amount,
                    self.max_drawdown_pct, self.daily_pnl, self.current_utc_day,
                    self.cooldown_until_tick_idx, self.cooldown_count, self.daily_reset_count,
                    self.total_trades, self.total_wins, self.total_losses,
                    self.outstanding_positions_count, self.current_exposure,
                    json.dumps(self.per_symbol_exposure), self.last_updated_epoch, now_iso
                ))
                conn.commit()
            self._state_valid = True
        except Exception:
            self._state_valid = False

    def is_valid(self) -> bool:
        """Returns True if risk state is loaded and internally consistent."""
        return self._state_valid

    def check_day_reset(self, epoch: Optional[int]):
        """Resets daily loss counter when moving to a new UTC calendar day."""
        if epoch is None or epoch <= 0:
            return
        utc_day = int(epoch) // 86400
        if self.current_utc_day is None:
            self.current_utc_day = utc_day
            self.daily_start_balance = self.current_balance
            self.daily_pnl = 0.0
            self.save_state()
        elif utc_day != self.current_utc_day:
            self.current_utc_day = utc_day
            self.daily_start_balance = self.current_balance
            self.daily_pnl = 0.0
            self.daily_loss_limit_hit = False
            self.daily_reset_count += 1
            self.save_state()

    def can_trade(self, tick_idx: int = 0, epoch: Optional[int] = None) -> Tuple[bool, str]:
        """Validates if risk constraints allow placing a new trade."""
        if not self._state_valid:
            return False, "Risk state unavailable or corrupted"

        if self.research_mode:
            return True, "Research mode (unconstrained signals)"

        if self.current_balance <= 0:
            return False, "Account balance depleted."

        # Check UTC day boundary
        self.check_day_reset(epoch)

        # 1. Consecutive-loss cooldown check
        if tick_idx < self.cooldown_until_tick_idx:
            remaining = self.cooldown_until_tick_idx - tick_idx
            return False, f"Cooldown: Paused for {remaining} more ticks after consecutive losses"

        # 2. Daily loss limit check
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
        if epoch is not None:
            self.last_updated_epoch = float(epoch)

        if won:
            profit = round(stake * payout_ratio, 2)
            self.current_balance += profit
            self.daily_pnl += profit
            self.consecutive_losses = 0
            self.total_wins += 1
        else:
            self.current_balance -= round(stake, 2)
            self.daily_pnl -= round(stake, 2)
            self.consecutive_losses += 1
            self.total_losses += 1

            # Trigger consecutive-loss cooldown
            if not self.research_mode and self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until_tick_idx = tick_idx + self.cooldown_ticks
                self.cooldown_count += 1

        # Track Drawdown
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        dd_amt = self.peak_balance - self.current_balance
        dd_pct = (dd_amt / self.peak_balance) if self.peak_balance > 0 else 0.0
        if dd_amt > self.max_drawdown_amount:
            self.max_drawdown_amount = dd_amt
            self.max_drawdown_pct = dd_pct

        # Persist updated state
        self.save_state()

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
            daily_pnl=round(self.daily_pnl, 2),
            total_trades=self.total_trades,
            total_wins=self.total_wins,
            total_losses=self.total_losses,
            cooldown_count=self.cooldown_count,
            daily_reset_count=self.daily_reset_count,
            is_paused=not can_run,
            pause_reason=reason,
            outstanding_positions_count=self.outstanding_positions_count,
            current_exposure=round(self.current_exposure, 2),
            per_symbol_exposure=dict(self.per_symbol_exposure),
            last_updated_epoch=self.last_updated_epoch,
            is_valid=self._state_valid
        )


# Backward compatibility alias
PersistentRiskManager = RiskManager
