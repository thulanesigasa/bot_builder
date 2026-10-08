"""Trade journaling, audit trails, and performance attribution database.
Records comprehensive tick execution telemetry, market state, risk parameters,
and directional outcomes for post-trade quantitative diagnostics.
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import os
import json
import pandas as pd
import numpy as np


@dataclass
class TradeRecord:
    timestamp_utc: str
    epoch: int
    symbol: str
    setup_name: str
    engine_type: str  # 'continuation' or 'reversal'
    direction: str    # 'UP' or 'DOWN'
    entry_price: float
    exit_price: float
    is_win: bool
    is_tie: bool
    market_state: str
    momentum: float
    acceleration: float
    streak: int
    volatility_regime: str
    range_position: float
    stake: float
    actual_payout: float
    required_probability: float  # Implied break-even probability
    estimated_probability: float
    expected_value: float
    net_pnl: float


class TradeJournal:
    """In-memory and file-persisted trade database for quantitative backtests."""

    def __init__(self):
        self.trades: List[TradeRecord] = []

    def record_trade(self, record: TradeRecord):
        self.trades.append(record)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([asdict(t) for t in self.trades])

    def export_csv(self, file_path: str):
        df = self.to_dataframe()
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        df.to_csv(file_path, index=False)

    def export_json(self, file_path: str):
        data = [asdict(t) for t in self.trades]
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

    def summarize_performance(self) -> Dict[str, Any]:
        """Calculates performance breakdown across continuation, reversal, and market states."""
        df = self.to_dataframe()
        if df.empty:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "profit_factor": 0.0,
                "continuation": {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "net_pnl": 0.0},
                "reversal": {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "net_pnl": 0.0},
                "market_states": {}
            }

        total_trades = len(df)
        wins = int(df["is_win"].sum())
        losses = total_trades - wins
        win_rate = (wins / total_trades) if total_trades > 0 else 0.0
        net_pnl = float(df["net_pnl"].sum())

        gross_profit = float(df.loc[df["net_pnl"] > 0, "net_pnl"].sum())
        gross_loss = abs(float(df.loc[df["net_pnl"] < 0, "net_pnl"].sum()))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 1.0)

        # Continuation vs Reversal attribution
        cont_df = df[df["engine_type"] == "continuation"]
        rev_df = df[df["engine_type"] == "reversal"]

        def _sub_stats(sub: pd.DataFrame):
            n = len(sub)
            if n == 0:
                return {"trades": 0, "win_rate": 0.0, "net_pnl": 0.0}
            w = int(sub["is_win"].sum())
            return {
                "trades": n,
                "wins": w,
                "losses": n - w,
                "win_rate": w / n,
                "net_pnl": float(sub["net_pnl"].sum())
            }

        # Market state attribution
        state_breakdown = {}
        for state, grp in df.groupby("market_state"):
            state_breakdown[state] = _sub_stats(grp)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "net_pnl": net_pnl,
            "profit_factor": profit_factor,
            "continuation": _sub_stats(cont_df),
            "reversal": _sub_stats(rev_df),
            "market_states": state_breakdown
        }
