"""Economic Performance Tracker for Forward Paper Trading (V1.6).

Tracks and reports genuine-quote-based economic performance across forward
research sessions. All PnL attribution uses actual recorded Deriv proposal
prices — no benchmark or theoretical contract pricing.

Metrics computed:
  - Cumulative hypothetical PnL (real quote prices)
  - Win rate (RUNHIGH / RUNLOW separately and combined)
  - EV accuracy: predicted EV vs realized EV per trade
  - Per market-state breakdown (win rate, PnL, count)
  - Per session breakdown (all metrics above, per session)
  - Drawdown: peak-to-trough on cumulative PnL series
  - Sharpe-like ratio: mean PnL per trade / std dev
  - Quote coverage: fraction of signals with genuine quotes available

Safety directive: This module is purely analytical. It performs zero
market interactions and cannot initiate any trade orders.
"""
import os
import sqlite3
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG

DEFAULT_FORWARD_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db"
)


@dataclass
class PerformanceSummary:
    """Aggregated economic performance over a set of resolved forward predictions."""
    session_id: Optional[str]
    symbol: str
    mode: str
    total_predictions: int
    paper_trade_signals: int        # Decisions == PAPER_TRADE
    resolved_trades: int            # PAPER_TRADE + RESOLVED outcome
    wins: int
    losses: int
    win_rate: Optional[float]
    cumulative_pnl: float
    mean_pnl_per_trade: Optional[float]
    std_pnl_per_trade: Optional[float]
    sharpe_ratio: Optional[float]   # mean / std (unitless, not annualised)
    max_drawdown: float
    quote_coverage_pct: float       # % of predictions that had a genuine quote
    predicted_ev_mean: Optional[float]
    realized_ev_mean: Optional[float]
    ev_accuracy_error: Optional[float]  # realized - predicted (positive = better)
    brier_score_runhigh: Optional[float]
    brier_score_runlow: Optional[float]
    per_state_breakdown: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "mode": self.mode,
            "total_predictions": self.total_predictions,
            "paper_trade_signals": self.paper_trade_signals,
            "resolved_trades": self.resolved_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4) if self.win_rate is not None else None,
            "cumulative_pnl": round(self.cumulative_pnl, 4),
            "mean_pnl_per_trade": round(self.mean_pnl_per_trade, 4) if self.mean_pnl_per_trade is not None else None,
            "std_pnl_per_trade": round(self.std_pnl_per_trade, 4) if self.std_pnl_per_trade is not None else None,
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None,
            "max_drawdown": round(self.max_drawdown, 4),
            "quote_coverage_pct": round(self.quote_coverage_pct, 2),
            "predicted_ev_mean": round(self.predicted_ev_mean, 4) if self.predicted_ev_mean is not None else None,
            "realized_ev_mean": round(self.realized_ev_mean, 4) if self.realized_ev_mean is not None else None,
            "ev_accuracy_error": round(self.ev_accuracy_error, 4) if self.ev_accuracy_error is not None else None,
            "brier_score_runhigh": round(self.brier_score_runhigh, 5) if self.brier_score_runhigh is not None else None,
            "brier_score_runlow": round(self.brier_score_runlow, 5) if self.brier_score_runlow is not None else None,
            "per_state_breakdown": self.per_state_breakdown,
            "generated_at": self.generated_at,
        }


class PerformanceTracker:
    """Reads forward_predictions.db and computes genuine-quote economic performance metrics."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_FORWARD_DB

    @contextlib.contextmanager
    def _get_conn(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Forward predictions DB not found: {self.db_path}")
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _load_records(
        self,
        symbol: Optional[str] = None,
        session_id: Optional[str] = None,
        mode: Optional[str] = None,
        resolved_only: bool = False
    ) -> pd.DataFrame:
        """Loads prediction records into a DataFrame with optional filters."""
        if not os.path.exists(self.db_path):
            return pd.DataFrame()

        filters = []
        params: List[Any] = []

        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        if session_id:
            filters.append("session_id = ?")
            params.append(session_id)
        if mode:
            filters.append("execution_mode = ?")
            params.append(mode)
        if resolved_only:
            filters.append("outcome_status IN ('RESOLVED', 'OUTCOME_RECONSTRUCTED', 'OUTCOME_VERIFIED')")

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        with self._get_conn() as conn:
            df = pd.read_sql_query(
                f"SELECT * FROM forward_predictions {where} ORDER BY timestamp ASC",
                conn,
                params=params
            )
        return df

    @staticmethod
    def _compute_drawdown(pnl_series: np.ndarray) -> float:
        """Computes peak-to-trough max drawdown on a cumulative PnL series."""
        if len(pnl_series) == 0:
            return 0.0
        cumulative = np.cumsum(pnl_series)
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        return float(np.max(drawdown))

    def compute_performance(
        self,
        symbol: Optional[str] = None,
        session_id: Optional[str] = None,
        mode: Optional[str] = None
    ) -> PerformanceSummary:
        """Computes full economic performance summary strictly for the given session (V1.6.2 Section 10)."""
        df = self._load_records(symbol=symbol, session_id=session_id, mode=mode)

        symbol_str = symbol or "ALL"
        mode_str = mode or "ALL"

        total = len(df)
        if total == 0:
            return self._empty_summary(symbol_str, mode_str, session_id)

        # Quote coverage: records where at least one genuine quote was available
        has_rh_quote = df["runhigh_ask"].notna() & (df["runhigh_ask"] > 0)
        has_rl_quote = df["runlow_ask"].notna() & (df["runlow_ask"] > 0)
        quote_coverage = float((has_rh_quote | has_rl_quote).sum()) / total * 100.0

        # Resolved paper trades only for financial metrics
        paper_mask = df["decision"] == "PAPER_TRADE"
        resolved_mask = df["outcome_status"].isin(["RESOLVED", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED"])
        active_mask = paper_mask & resolved_mask & df["hypothetical_pnl"].notna()

        paper_count = int(paper_mask.sum())
        resolved_df = df[active_mask].copy()
        resolved_count = len(resolved_df)

        # Win/loss calculation
        wins = 0
        losses = 0
        win_rate = None
        cum_pnl = 0.0
        mean_pnl = None
        std_pnl = None
        sharpe = None
        max_dd = 0.0
        realized_ev_mean = None
        predicted_ev_mean = None
        ev_error = None

        if resolved_count > 0:
            pnl_arr = resolved_df["hypothetical_pnl"].values.astype(float)
            wins = int((pnl_arr > 0).sum())
            losses = int((pnl_arr < 0).sum())
            cum_pnl = float(np.sum(pnl_arr))
            win_rate = float(wins / resolved_count)
            mean_pnl = float(np.mean(pnl_arr))
            std_val = float(np.std(pnl_arr))
            std_pnl = std_val
            sharpe = float(mean_pnl / std_val) if std_val > 1e-9 else None
            max_dd = self._compute_drawdown(pnl_arr)

            # Realized EV per trade: actual PnL per trade
            realized_ev_mean = mean_pnl

            # Predicted EV: average of ev_runhigh or ev_runlow depending on target_direction
            ev_col = np.where(
                resolved_df["target_direction"] == "RUNHIGH",
                resolved_df["ev_runhigh"].fillna(np.nan),
                resolved_df["ev_runlow"].fillna(np.nan)
            )
            valid_ev = ev_col[~np.isnan(ev_col.astype(float))]
            if len(valid_ev) > 0:
                predicted_ev_mean = float(np.mean(valid_ev.astype(float)))
                ev_error = realized_ev_mean - predicted_ev_mean

        # Brier scores
        brier_rh = None
        brier_rl = None
        resolved_all = df[resolved_mask & df["runhigh_win"].notna()].copy()
        if len(resolved_all) > 0:
            rh_valid = resolved_all[resolved_all["runhigh_pred_prob"].notna()]
            if len(rh_valid) > 0:
                brier_rh = float(np.mean(
                    (rh_valid["runhigh_pred_prob"].values - rh_valid["runhigh_win"].values) ** 2
                ))
            rl_valid = resolved_all[resolved_all["runlow_pred_prob"].notna()]
            if len(rl_valid) > 0:
                brier_rl = float(np.mean(
                    (rl_valid["runlow_pred_prob"].values - rl_valid["runlow_win"].values) ** 2
                ))

        # Per-state breakdown
        per_state = {}
        if "market_state" in df.columns and resolved_count > 0:
            state_groups = resolved_df.groupby("market_state")
            for state_name, grp in state_groups:
                grp_pnl = grp["hypothetical_pnl"].values.astype(float)
                s_wins = int((grp_pnl > 0).sum())
                s_count = len(grp_pnl)
                per_state[str(state_name)] = {
                    "count": s_count,
                    "wins": s_wins,
                    "win_rate": round(s_wins / s_count, 4) if s_count > 0 else None,
                    "cumulative_pnl": round(float(np.sum(grp_pnl)), 4),
                    "mean_pnl": round(float(np.mean(grp_pnl)), 4) if s_count > 0 else None,
                }

        return PerformanceSummary(
            session_id=session_id,
            symbol=symbol_str,
            mode=mode_str,
            total_predictions=total,
            paper_trade_signals=paper_count,
            resolved_trades=resolved_count,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            cumulative_pnl=round(cum_pnl, 4),
            mean_pnl_per_trade=round(mean_pnl, 4) if mean_pnl is not None else None,
            std_pnl_per_trade=round(std_pnl, 4) if std_pnl is not None else None,
            sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
            max_drawdown=round(max_dd, 4),
            quote_coverage_pct=round(quote_coverage, 2),
            predicted_ev_mean=round(predicted_ev_mean, 4) if predicted_ev_mean is not None else None,
            realized_ev_mean=round(realized_ev_mean, 4) if realized_ev_mean is not None else None,
            ev_accuracy_error=round(ev_error, 4) if ev_error is not None else None,
            brier_score_runhigh=round(brier_rh, 5) if brier_rh is not None else None,
            brier_score_runlow=round(brier_rl, 5) if brier_rl is not None else None,
            per_state_breakdown=per_state,
            generated_at=datetime.now(timezone.utc).isoformat()
        )

    @staticmethod
    def _empty_summary(symbol: str, mode: str, session_id: Optional[str]) -> PerformanceSummary:
        return PerformanceSummary(
            session_id=session_id,
            symbol=symbol,
            mode=mode,
            total_predictions=0,
            paper_trade_signals=0,
            resolved_trades=0,
            wins=0,
            losses=0,
            win_rate=None,
            cumulative_pnl=0.0,
            mean_pnl_per_trade=None,
            std_pnl_per_trade=None,
            sharpe_ratio=None,
            max_drawdown=0.0,
            quote_coverage_pct=0.0,
            predicted_ev_mean=None,
            realized_ev_mean=None,
            ev_accuracy_error=None,
            brier_score_runhigh=None,
            brier_score_runlow=None,
            per_state_breakdown={},
            generated_at=datetime.now(timezone.utc).isoformat()
        )

    def print_summary(self, summary: PerformanceSummary):
        """Pretty-prints a PerformanceSummary to stdout."""
        d = summary.to_dict()
        print("\n=== ECONOMIC PERFORMANCE SUMMARY ===")
        print(f"  Symbol            : {d['symbol']}")
        print(f"  Mode              : {d['mode']}")
        print(f"  Total Predictions : {d['total_predictions']}")
        print(f"  Paper Trade Sigs  : {d['paper_trade_signals']}")
        print(f"  Resolved Trades   : {d['resolved_trades']}")
        print(f"  Wins / Losses     : {d['wins']} / {d['losses']}")
        print(f"  Win Rate          : {d['win_rate']}")
        print(f"  Cumulative PnL    : {d['cumulative_pnl']}")
        print(f"  Mean PnL/Trade    : {d['mean_pnl_per_trade']}")
        print(f"  Std PnL/Trade     : {d['std_pnl_per_trade']}")
        print(f"  Sharpe Ratio      : {d['sharpe_ratio']}")
        print(f"  Max Drawdown      : {d['max_drawdown']}")
        print(f"  Quote Coverage    : {d['quote_coverage_pct']}%")
        print(f"  Predicted EV Mean : {d['predicted_ev_mean']}")
        print(f"  Realized EV Mean  : {d['realized_ev_mean']}")
        print(f"  EV Accuracy Error : {d['ev_accuracy_error']}")
        print(f"  Brier RH          : {d['brier_score_runhigh']}")
        print(f"  Brier RL          : {d['brier_score_runlow']}")
        if d["per_state_breakdown"]:
            print("\n  Per-State Breakdown:")
            for state, m in d["per_state_breakdown"].items():
                print(f"    {state}: count={m['count']}, win_rate={m['win_rate']}, pnl={m['cumulative_pnl']}")
        print(f"\n  Generated at: {d['generated_at']}")


if __name__ == "__main__":
    tracker = PerformanceTracker()
    summary = tracker.compute_performance()
    tracker.print_summary(summary)
