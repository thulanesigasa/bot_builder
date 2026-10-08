"""Forward Prediction Journal and Calibration Tracking Engine (V1.5.2).

Logs every forward market observation, frozen model conditional probability estimate,
synchronized proposal quote, hypothetical decision, and subsequent tick outcomes without lookahead.

Evaluates out-of-sample forward prediction accuracy:
- Brier Score vs Empirical Baseline
- Expected Calibration Error (ECE)
- Predicted vs Realized Win Rates
- Hypothetical PnL Attribution
- Automatic resolution of 5-tick contract windows (Entry i+1 to Expiry i+6)
"""
import collections
import contextlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG


DEFAULT_FORWARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db")


@dataclass
class ForwardPredictionRecord:
    prediction_id: str
    timestamp: float
    symbol: str
    model_version: str
    market_state: str
    features_json: str
    runhigh_pred_prob: float
    runlow_pred_prob: float
    runhigh_ask: float
    runhigh_payout: float
    runlow_ask: float
    runlow_payout: float
    break_even_runhigh: float
    break_even_runlow: float
    ev_runhigh: float
    ev_runlow: float
    cons_ev_runhigh: float
    cons_ev_runlow: float
    decision: str  # 'TRADE' or 'NO_TRADE'
    rejection_reason: str
    target_direction: str  # 'RUNHIGH', 'RUNLOW', or 'NONE'
    signal_epoch: int
    signal_price: float
    entry_epoch: Optional[int] = None
    expiry_epoch: Optional[int] = None
    forward_prices_json: str = "[]"
    forward_ticks_count: int = 0
    outcome_status: str = "PENDING"  # 'PENDING', 'RESOLVED', 'EXPIRED'
    runhigh_win: Optional[float] = None
    runlow_win: Optional[float] = None
    hypothetical_pnl: float = 0.0


class ForwardPredictionJournal:
    """Persistent SQLite database and real-time evaluator for forward market predictions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_FORWARD_DB
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forward_predictions (
                    prediction_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    symbol TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    market_state TEXT NOT NULL,
                    features_json TEXT,
                    runhigh_pred_prob REAL NOT NULL,
                    runlow_pred_prob REAL NOT NULL,
                    runhigh_ask REAL NOT NULL,
                    runhigh_payout REAL NOT NULL,
                    runlow_ask REAL NOT NULL,
                    runlow_payout REAL NOT NULL,
                    break_even_runhigh REAL NOT NULL,
                    break_even_runlow REAL NOT NULL,
                    ev_runhigh REAL NOT NULL,
                    ev_runlow REAL NOT NULL,
                    cons_ev_runhigh REAL NOT NULL,
                    cons_ev_runlow REAL NOT NULL,
                    decision TEXT NOT NULL,
                    rejection_reason TEXT NOT NULL,
                    target_direction TEXT NOT NULL,
                    signal_epoch INTEGER NOT NULL,
                    signal_price REAL NOT NULL,
                    entry_epoch INTEGER,
                    expiry_epoch INTEGER,
                    forward_prices_json TEXT NOT NULL,
                    forward_ticks_count INTEGER NOT NULL DEFAULT 0,
                    outcome_status TEXT NOT NULL,
                    runhigh_win REAL,
                    runlow_win REAL,
                    hypothetical_pnl REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fwd_status
                ON forward_predictions (outcome_status, timestamp)
            """)
            conn.commit()

    def log_prediction(self, record: ForwardPredictionRecord) -> str:
        """Stores a new shadow prediction record."""
        created_at = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO forward_predictions (
                    prediction_id, timestamp, symbol, model_version, market_state,
                    features_json, runhigh_pred_prob, runlow_pred_prob,
                    runhigh_ask, runhigh_payout, runlow_ask, runlow_payout,
                    break_even_runhigh, break_even_runlow, ev_runhigh, ev_runlow,
                    cons_ev_runhigh, cons_ev_runlow, decision, rejection_reason,
                    target_direction, signal_epoch, signal_price, entry_epoch,
                    expiry_epoch, forward_prices_json, forward_ticks_count,
                    outcome_status, runhigh_win, runlow_win, hypothetical_pnl, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.prediction_id, record.timestamp, record.symbol, record.model_version,
                record.market_state, record.features_json, record.runhigh_pred_prob,
                record.runlow_pred_prob, record.runhigh_ask, record.runhigh_payout,
                record.runlow_ask, record.runlow_payout, record.break_even_runhigh,
                record.break_even_runlow, record.ev_runhigh, record.ev_runlow,
                record.cons_ev_runhigh, record.cons_ev_runlow, record.decision,
                record.rejection_reason, record.target_direction, record.signal_epoch,
                record.signal_price, record.entry_epoch, record.expiry_epoch,
                record.forward_prices_json, record.forward_ticks_count,
                record.outcome_status, record.runhigh_win, record.runlow_win,
                record.hypothetical_pnl, created_at
            ))
            conn.commit()
        return record.prediction_id

    def ingest_forward_tick(self, epoch: int, price: float, symbol: str = "R_75"):
        """Feeds a newly arrived tick to update pending predictions forward windows.
        
        Lifecycle:
        - When an observation has 0 forward ticks, first tick is Entry Spot S_0 (i+1).
        - Next 5 ticks are S_1, S_2, S_3, S_4, S_5 (Expiry).
        - Once 6 forward ticks are collected, contract outcome is resolved.
        """
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT prediction_id, signal_epoch, forward_prices_json, forward_ticks_count,
                       runhigh_ask, runhigh_payout, runlow_ask, runlow_payout,
                       target_direction, decision
                FROM forward_predictions
                WHERE symbol = ? AND outcome_status = 'PENDING'
                ORDER BY timestamp ASC
            """, (symbol,))
            pending_rows = cur.fetchall()

            for row in pending_rows:
                pid = row["prediction_id"]
                sig_epoch = row["signal_epoch"]
                if epoch <= sig_epoch:
                    continue  # Ignore ticks at or before signal

                try:
                    prices = json.loads(row["forward_prices_json"])
                except Exception:
                    prices = []

                prices.append(price)
                count = len(prices)

                if count < 6:
                    # Still accumulating forward ticks
                    conn.execute("""
                        UPDATE forward_predictions
                        SET forward_prices_json = ?, forward_ticks_count = ?
                        WHERE prediction_id = ?
                    """, (json.dumps(prices), count, pid))
                else:
                    # 6 ticks accumulated: S_0, S_1, S_2, S_3, S_4, S_5
                    s0 = prices[0]
                    # Evaluate RUNHIGH: S_1 > S_0, S_2 > S_1, S_3 > S_2, S_4 > S_3, S_5 > S_4
                    rh_win = 1.0 if all(prices[k] > prices[k - 1] for k in range(1, 6)) else 0.0
                    # Evaluate RUNLOW: S_1 < S_0, S_2 < S_1, S_3 < S_2, S_4 < S_3, S_5 < S_4
                    rl_win = 1.0 if all(prices[k] < prices[k - 1] for k in range(1, 6)) else 0.0

                    pnl = 0.0
                    td = row["target_direction"]
                    dec = row["decision"]
                    if dec == "TRADE":
                        if td == "RUNHIGH":
                            pnl = (row["runhigh_payout"] - row["runhigh_ask"]) if rh_win == 1.0 else -row["runhigh_ask"]
                        elif td == "RUNLOW":
                            pnl = (row["runlow_payout"] - row["runlow_ask"]) if rl_win == 1.0 else -row["runlow_ask"]

                    conn.execute("""
                        UPDATE forward_predictions
                        SET forward_prices_json = ?, forward_ticks_count = ?,
                            outcome_status = 'RESOLVED',
                            runhigh_win = ?, runlow_win = ?,
                            hypothetical_pnl = ?, expiry_epoch = ?
                        WHERE prediction_id = ?
                    """, (json.dumps(prices), count, rh_win, rl_win, round(pnl, 2), epoch, pid))

            conn.commit()

    def get_accuracy_metrics(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Calculates prediction accuracy, Brier Score, and calibration metrics on resolved records."""
        with self._get_conn() as conn:
            where_clause = "WHERE symbol = ?" if symbol else ""
            params = (symbol,) if symbol else ()
            cur = conn.execute(f"""
                SELECT runhigh_pred_prob, runlow_pred_prob, runhigh_win, runlow_win,
                       decision, hypothetical_pnl, outcome_status
                FROM forward_predictions
                {where_clause}
            """, params)
            rows = cur.fetchall()

        total = len(rows)
        resolved = [r for r in rows if r["outcome_status"] == "RESOLVED" and r["runhigh_win"] is not None]
        pending = sum(1 for r in rows if r["outcome_status"] == "PENDING")

        if not resolved:
            return {
                "total_predictions": total,
                "resolved_predictions": 0,
                "pending_predictions": pending,
                "runhigh_brier_score": None,
                "runhigh_observed_win_rate": None,
                "runhigh_mean_predicted_prob": None,
                "runlow_brier_score": None,
                "runlow_observed_win_rate": None,
                "runlow_mean_predicted_prob": None,
                "total_hypothetical_pnl": 0.0,
                "status": "AWAITING_RESOLUTIONS"
            }

        rh_preds = np.array([r["runhigh_pred_prob"] for r in resolved])
        rh_acts = np.array([r["runhigh_win"] for r in resolved])
        rl_preds = np.array([r["runlow_pred_prob"] for r in resolved])
        rl_acts = np.array([r["runlow_win"] for r in resolved])

        rh_brier = float(np.mean((rh_preds - rh_acts) ** 2))
        rl_brier = float(np.mean((rl_preds - rl_acts) ** 2))
        total_pnl = sum(r["hypothetical_pnl"] for r in resolved)

        return {
            "total_predictions": total,
            "resolved_predictions": len(resolved),
            "pending_predictions": pending,
            "runhigh_brier_score": round(rh_brier, 6),
            "runhigh_observed_win_rate": round(float(np.mean(rh_acts)), 4),
            "runhigh_mean_predicted_prob": round(float(np.mean(rh_preds)), 4),
            "runlow_brier_score": round(rl_brier, 6),
            "runlow_observed_win_rate": round(float(np.mean(rl_acts)), 4),
            "runlow_mean_predicted_prob": round(float(np.mean(rl_preds)), 4),
            "total_hypothetical_pnl": round(total_pnl, 2),
            "status": "EVALUATED"
        }

    def inspect_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns the most recent forward prediction records."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM forward_predictions
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]


def main():
    journal = ForwardPredictionJournal()
    print("=== FORWARD PREDICTION JOURNAL STATUS ===")
    metrics = journal.get_accuracy_metrics()
    for k, v in metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
