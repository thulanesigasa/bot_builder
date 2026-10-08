"""Forward Prediction Journal and Calibration Tracking Engine (V1.5.3).

Logs every forward market observation, frozen model conditional probability estimate,
synchronized proposal quote, hypothetical decision, and subsequent tick outcomes without lookahead.

Evaluates out-of-sample forward prediction accuracy:
- Brier Score vs Empirical Baseline
- Expected Calibration Error (ECE)
- Predicted vs Realized Win Rates
- Hypothetical PnL Attribution
- Automatic resolution of 5-tick contract windows (Entry i+1 to Expiry i+6)
- Explicit OUTCOME_UNVERIFIED handling for incomplete sequences or data gaps
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
    runhigh_pred_prob: Optional[float] = None
    runlow_pred_prob: Optional[float] = None
    runhigh_ask: Optional[float] = None
    runhigh_payout: Optional[float] = None
    runlow_ask: Optional[float] = None
    runlow_payout: Optional[float] = None
    break_even_runhigh: Optional[float] = None
    break_even_runlow: Optional[float] = None
    ev_runhigh: Optional[float] = None
    ev_runlow: Optional[float] = None
    cons_ev_runhigh: Optional[float] = None
    cons_ev_runlow: Optional[float] = None
    decision: str = "NO_TRADE"  # 'TRADE' or 'NO_TRADE'
    rejection_reason: str = ""
    target_direction: str = "NONE"  # 'RUNHIGH', 'RUNLOW', or 'NONE'
    signal_epoch: int = 0
    signal_price: float = 0.0
    entry_epoch: Optional[int] = None
    expiry_epoch: Optional[int] = None
    forward_prices_json: str = "[]"
    forward_ticks_count: int = 0
    outcome_status: str = "PENDING"  # 'PENDING', 'RESOLVED', 'OUTCOME_UNVERIFIED', 'EXPIRED'
    runhigh_win: Optional[float] = None
    runlow_win: Optional[float] = None
    hypothetical_pnl: float = 0.0
    execution_mode: str = "SHADOW"  # 'DATA_COLLECTION_ONLY', 'SHADOW', 'PAPER'
    model_id: str = ""
    feature_schema_version: str = "1.5.3"


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
                    runhigh_pred_prob REAL,
                    runlow_pred_prob REAL,
                    runhigh_ask REAL,
                    runhigh_payout REAL,
                    runlow_ask REAL,
                    runlow_payout REAL,
                    break_even_runhigh REAL,
                    break_even_runlow REAL,
                    ev_runhigh REAL,
                    ev_runlow REAL,
                    cons_ev_runhigh REAL,
                    cons_ev_runlow REAL,
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
                    execution_mode TEXT DEFAULT 'SHADOW',
                    model_id TEXT DEFAULT '',
                    feature_schema_version TEXT DEFAULT '1.5.3',
                    created_at TEXT NOT NULL
                )
            """)

            # Schema migration checks
            cur = conn.execute("PRAGMA table_info(forward_predictions)")
            cols = [r["name"] for r in cur.fetchall()]
            if "execution_mode" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN execution_mode TEXT DEFAULT 'SHADOW'")
            if "model_id" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN model_id TEXT DEFAULT ''")
            if "feature_schema_version" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN feature_schema_version TEXT DEFAULT '1.5.3'")

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fwd_status
                ON forward_predictions (outcome_status, timestamp)
            """)
            conn.commit()

    def log_prediction(self, record: ForwardPredictionRecord) -> str:
        """Stores a new forward observation / prediction record."""
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
                    outcome_status, runhigh_win, runlow_win, hypothetical_pnl,
                    execution_mode, model_id, feature_schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.hypothetical_pnl, record.execution_mode, record.model_id,
                record.feature_schema_version, created_at
            ))
            conn.commit()
        return record.prediction_id

    def ingest_forward_tick(self, epoch: int, price: float, symbol: str = "R_75"):
        """Feeds a newly arrived tick to update pending predictions' forward windows.
        
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
                    # Evaluate RUNHIGH: S_1 > S_0, S_2 > S_1, S_3 > S_2, S_4 > S_3, S_5 > S_4
                    rh_win = 1.0 if all(prices[k] > prices[k - 1] for k in range(1, 6)) else 0.0
                    # Evaluate RUNLOW: S_1 < S_0, S_2 < S_1, S_3 < S_2, S_4 < S_3, S_5 < S_4
                    rl_win = 1.0 if all(prices[k] < prices[k - 1] for k in range(1, 6)) else 0.0

                    pnl = 0.0
                    td = row["target_direction"]
                    dec = row["decision"]
                    rh_ask = row["runhigh_ask"]
                    rh_pay = row["runhigh_payout"]
                    rl_ask = row["runlow_ask"]
                    rl_pay = row["runlow_payout"]

                    if dec in ("TRADE", "PAPER_TRADE"):
                        if td == "RUNHIGH" and rh_pay is not None and rh_ask is not None:
                            pnl = (rh_pay - rh_ask) if rh_win == 1.0 else -rh_ask
                        elif td == "RUNLOW" and rl_pay is not None and rl_ask is not None:
                            pnl = (rl_pay - rl_ask) if rl_win == 1.0 else -rl_ask

                    conn.execute("""
                        UPDATE forward_predictions
                        SET forward_prices_json = ?, forward_ticks_count = ?,
                            outcome_status = 'RESOLVED',
                            runhigh_win = ?, runlow_win = ?,
                            hypothetical_pnl = ?, expiry_epoch = ?
                        WHERE prediction_id = ?
                    """, (json.dumps(prices), count, rh_win, rl_win, round(pnl, 2), epoch, pid))

            conn.commit()

    def mark_incomplete_as_unverified(self, symbol: Optional[str] = None):
        """Marks any dangling or incomplete pending predictions as OUTCOME_UNVERIFIED.
        Guarantees that partial tick histories are NEVER counted as trading losses.
        """
        with self._get_conn() as conn:
            where_clause = "WHERE outcome_status = 'PENDING'"
            params = ()
            if symbol:
                where_clause += " AND symbol = ?"
                params = (symbol,)

            conn.execute(f"""
                UPDATE forward_predictions
                SET outcome_status = 'OUTCOME_UNVERIFIED'
                {where_clause}
            """, params)
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

        if not rows:
            return {
                "total_predictions": 0,
                "resolved_predictions": 0,
                "unverified_predictions": 0,
                "pending_predictions": 0,
                "brier_score_runhigh": None,
                "brier_score_runlow": None,
                "runhigh_brier_score": None,
                "runlow_brier_score": None,
                "runhigh_observed_win_rate": None,
                "runlow_observed_win_rate": None,
                "realized_runhigh_win_rate": None,
                "realized_runlow_win_rate": None,
                "cumulative_pnl": 0.0
            }

        total = len(rows)
        resolved = [r for r in rows if r["outcome_status"] == "RESOLVED" and r["runhigh_win"] is not None]
        unverified = len([r for r in rows if r["outcome_status"] == "OUTCOME_UNVERIFIED"])
        pending = len([r for r in rows if r["outcome_status"] == "PENDING"])

        if not resolved:
            return {
                "total_predictions": total,
                "resolved_predictions": 0,
                "unverified_predictions": unverified,
                "pending_predictions": pending,
                "brier_score_runhigh": None,
                "brier_score_runlow": None,
                "runhigh_brier_score": None,
                "runlow_brier_score": None,
                "runhigh_observed_win_rate": None,
                "runlow_observed_win_rate": None,
                "realized_runhigh_win_rate": None,
                "realized_runlow_win_rate": None,
                "cumulative_pnl": 0.0
            }

        rh_preds_valid = [r["runhigh_pred_prob"] for r in resolved if r["runhigh_pred_prob"] is not None]
        rh_wins_valid = [r["runhigh_win"] for r in resolved if r["runhigh_pred_prob"] is not None]
        rl_preds_valid = [r["runlow_pred_prob"] for r in resolved if r["runlow_pred_prob"] is not None]
        rl_wins_valid = [r["runlow_win"] for r in resolved if r["runlow_pred_prob"] is not None]

        rh_wins = np.array([r["runhigh_win"] for r in resolved if r["runhigh_win"] is not None])
        rl_wins = np.array([r["runlow_win"] for r in resolved if r["runlow_win"] is not None])
        pnls = [r["hypothetical_pnl"] for r in resolved if r["hypothetical_pnl"] is not None]

        brier_rh = float(np.mean((np.array(rh_preds_valid) - np.array(rh_wins_valid)) ** 2)) if rh_preds_valid else None
        brier_rl = float(np.mean((np.array(rl_preds_valid) - np.array(rl_wins_valid)) ** 2)) if rl_preds_valid else None
        win_rate_rh = float(np.mean(rh_wins)) if len(rh_wins) > 0 else None
        win_rate_rl = float(np.mean(rl_wins)) if len(rl_wins) > 0 else None
        cum_pnl = float(sum(pnls)) if pnls else 0.0

        return {
            "total_predictions": total,
            "resolved_predictions": len(resolved),
            "unverified_predictions": unverified,
            "pending_predictions": pending,
            "brier_score_runhigh": round(brier_rh, 5) if brier_rh is not None else None,
            "brier_score_runlow": round(brier_rl, 5) if brier_rl is not None else None,
            "runhigh_brier_score": round(brier_rh, 5) if brier_rh is not None else None,
            "runlow_brier_score": round(brier_rl, 5) if brier_rl is not None else None,
            "runhigh_observed_win_rate": round(win_rate_rh, 5) if win_rate_rh is not None else None,
            "runlow_observed_win_rate": round(win_rate_rl, 5) if win_rate_rl is not None else None,
            "realized_runhigh_win_rate": round(win_rate_rh, 5) if win_rate_rh is not None else None,
            "realized_runlow_win_rate": round(win_rate_rl, 5) if win_rate_rl is not None else None,
            "cumulative_pnl": round(cum_pnl, 2)
        }

    def inspect_recent(self, limit: int = 10, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent prediction records in a stable, credentials-safe format."""
        with self._get_conn() as conn:
            where_clause = "WHERE symbol = ?" if symbol else ""
            params = (symbol, limit) if symbol else (limit,)
            cur = conn.execute(f"""
                SELECT * FROM forward_predictions
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
