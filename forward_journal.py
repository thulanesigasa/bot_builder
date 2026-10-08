"""Forward Prediction Journal and Calibration Tracking Engine (V1.6.1).

Logs every forward market observation, frozen model conditional probability estimate,
synchronized proposal quote, hypothetical decision, and subsequent tick outcomes without lookahead.

Guarantees:
- Unique prediction IDs and session ID linkage across restarts.
- Prevention of duplicate prediction writes and duplicate outcome resolutions.
- Canonical outcome taxonomy:
    OUTCOME_PENDING
    OUTCOME_RECONSTRUCTED
    OUTCOME_VERIFIED
    OUTCOME_INCOMPLETE
    OUTCOME_DATA_GAP
    OUTCOME_UNVERIFIED
- Prediction immutability: original prediction probabilities and features are NEVER modified post-resolution.
- Incomplete outcomes are strictly excluded from win-rate metrics and never counted as losses.
- Evaluates out-of-sample forward accuracy: Brier scores, calibration error (ECE), realized win rates, PnL.
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
from outcome_resolver import (
    OutcomeResolver,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RECONSTRUCTED,
    STATUS_VERIFIED,
    STATUS_INCOMPLETE,
    STATUS_DATA_GAP,
    STATUS_UNVERIFIED,
    REASON_WAITING_FOR_ENTRY_TICK,
    REASON_WAITING_FOR_FUTURE_TICKS,
    REASON_TICK_SEQUENCE_GAP,
    REASON_SESSION_ENDED_BEFORE_RESOLUTION,
)


DEFAULT_FORWARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db")


RESOLVED_STATUSES = (STATUS_RECONSTRUCTED, STATUS_VERIFIED, "RESOLVED")
PENDING_STATUSES = (STATUS_PENDING, "PENDING")


@dataclass
class ForwardPredictionRecord:
    prediction_id: str
    timestamp: float
    symbol: str
    model_version: str
    market_state: str
    features_json: str
    session_id: str = ""
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
    decision: str = "NO_TRADE"
    rejection_reason: str = ""
    target_direction: str = "NONE"
    signal_epoch: int = 0
    signal_price: float = 0.0
    entry_epoch: Optional[int] = None
    expiry_epoch: Optional[int] = None
    forward_prices_json: str = "[]"
    forward_ticks_count: int = 0
    outcome_status: str = STATUS_PENDING
    runhigh_win: Optional[float] = None
    runlow_win: Optional[float] = None
    hypothetical_pnl: float = 0.0
    execution_mode: str = "SHADOW"
    model_id: str = ""
    quote_id: str = ""
    feature_schema_version: str = "1.0"
    source_provenance: str = "LIVE_DERIV"
    unresolved_reason: str = ""
    forward_epochs_json: str = "[]"


class ForwardPredictionJournal:
    """Persistent SQLite database and real-time evaluator for forward market predictions."""

    def __init__(self, db_path: Optional[str] = None, enforce_session_id: bool = False):
        self.db_path = db_path or DEFAULT_FORWARD_DB
        self.enforce_session_id = enforce_session_id
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()
        self.resolver = OutcomeResolver(db_path=self.db_path, gap_threshold_seconds=5.0)

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON;")
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
                    session_id TEXT DEFAULT '',
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
                    quote_id TEXT DEFAULT '',
                    feature_schema_version TEXT DEFAULT '1.5.3',
                    source_provenance TEXT DEFAULT 'LIVE_DERIV',
                    created_at TEXT NOT NULL
                )
            """)

            # Dedicated forward_outcomes table with foreign key (V1.6.2 Section 6 & 7)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forward_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    prediction_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    entry_epoch INTEGER,
                    expiry_epoch INTEGER,
                    forward_prices_json TEXT NOT NULL,
                    forward_ticks_count INTEGER NOT NULL DEFAULT 0,
                    outcome_status TEXT NOT NULL,
                    runhigh_win REAL,
                    runlow_win REAL,
                    hypothetical_pnl REAL NOT NULL DEFAULT 0.0,
                    contract_model_version TEXT DEFAULT '5_movement_canonical',
                    resolution_timestamp REAL NOT NULL,
                    verification_level TEXT DEFAULT 'RECONSTRUCTED',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (prediction_id) REFERENCES forward_predictions(prediction_id)
                )
            """)

            # Schema migration checks for existing databases
            cur = conn.execute("PRAGMA table_info(forward_predictions)")
            cols = [r["name"] for r in cur.fetchall()]
            if "session_id" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN session_id TEXT DEFAULT ''")
            if "execution_mode" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN execution_mode TEXT DEFAULT 'SHADOW'")
            if "model_id" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN model_id TEXT DEFAULT ''")
            if "quote_id" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN quote_id TEXT DEFAULT ''")
            if "feature_schema_version" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN feature_schema_version TEXT DEFAULT '1.5.3'")
            if "source_provenance" not in cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN source_provenance TEXT DEFAULT 'LIVE_DERIV'")

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fwd_status
                ON forward_predictions (outcome_status, timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fwd_session
                ON forward_predictions (session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcomes_session
                ON forward_outcomes (session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcomes_pred
                ON forward_outcomes (prediction_id)
            """)
            conn.commit()

    def log_prediction(self, record: ForwardPredictionRecord) -> str:
        """Stores a new forward observation / prediction record with duplicate write prevention."""
        if self.enforce_session_id and (not record.session_id or not str(record.session_id).strip()):
            raise ValueError("session_id must be a non-empty string. Blank or null session IDs are strictly rejected.")

        sess_id = record.session_id.strip() if (record.session_id and str(record.session_id).strip()) else "LEGACY_UNATTRIBUTED"
        provenance = getattr(record, "source_provenance", "LIVE_DERIV") or "LIVE_DERIV"
        created_at = datetime.now(timezone.utc).isoformat()

        with self._get_conn() as conn:
            # Check duplicate prediction ID
            existing = conn.execute(
                "SELECT prediction_id FROM forward_predictions WHERE prediction_id = ?",
                (record.prediction_id,)
            ).fetchone()
            if existing:
                return record.prediction_id

            # Normalise outcome status to canonical taxonomy
            norm_status = record.outcome_status
            if norm_status == "PENDING":
                norm_status = STATUS_PENDING

            conn.execute("""
                INSERT INTO forward_predictions (
                    prediction_id, session_id, timestamp, symbol, model_version, market_state,
                    features_json, runhigh_pred_prob, runlow_pred_prob,
                    runhigh_ask, runhigh_payout, runlow_ask, runlow_payout,
                    break_even_runhigh, break_even_runlow, ev_runhigh, ev_runlow,
                    cons_ev_runhigh, cons_ev_runlow, decision, rejection_reason,
                    target_direction, signal_epoch, signal_price, entry_epoch,
                    expiry_epoch, forward_prices_json, forward_ticks_count,
                    outcome_status, runhigh_win, runlow_win, hypothetical_pnl,
                    execution_mode, model_id, quote_id, feature_schema_version, source_provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.prediction_id, sess_id, record.timestamp, record.symbol, record.model_version,
                record.market_state, record.features_json, record.runhigh_pred_prob,
                record.runlow_pred_prob, record.runhigh_ask, record.runhigh_payout,
                record.runlow_ask, record.runlow_payout, record.break_even_runhigh,
                record.break_even_runlow, record.ev_runhigh, record.ev_runlow,
                record.cons_ev_runhigh, record.cons_ev_runlow, record.decision,
                record.rejection_reason, record.target_direction, record.signal_epoch,
                record.signal_price, record.entry_epoch, record.expiry_epoch,
                record.forward_prices_json, record.forward_ticks_count,
                norm_status, record.runhigh_win, record.runlow_win,
                record.hypothetical_pnl, record.execution_mode, record.model_id,
                getattr(record, "quote_id", "") or "",
                getattr(record, "feature_schema_version", "1.0") or "1.0", provenance, created_at
            ))
            conn.commit()

        # Register pending outcome with persistent resolver
        self.resolver.register_pending_prediction(
            prediction_id=record.prediction_id,
            session_id=sess_id,
            symbol=record.symbol,
            signal_epoch=record.signal_epoch or int(record.timestamp),
            signal_price=record.signal_price,
            timestamp=record.timestamp,
            model_version=record.model_version,
            decision=record.decision,
            target_direction=record.target_direction,
            runhigh_ask=record.runhigh_ask,
            runhigh_payout=record.runhigh_payout,
            runlow_ask=record.runlow_ask,
            runlow_payout=record.runlow_payout,
        )
        return record.prediction_id

    def ingest_forward_tick(
        self,
        epoch: int,
        price: float,
        symbol: str = "R_75",
        gap_threshold_seconds: float = 5.0
    ):
        """Feeds a newly arrived tick to update pending predictions' forward windows.
        
        Canonical 5-Movement Sequence:
        - 0 forward ticks accumulated: First subsequent tick is Entry Spot S_0 (i+1).
        - Next 5 ticks are S_1, S_2, S_3, S_4, S_5 (Expiry).
        - Once 6 forward ticks are collected, contract outcome is resolved.
        - RUNHIGH wins iff S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4.
        - RUNLOW wins iff S_1 < S_0 AND S_2 < S_1 AND S_3 < S_2 AND S_4 < S_3 AND S_5 < S_4.
        - Any tie or reversal is a loss under canonical model.
        - If tick interval > gap_threshold_seconds between successive ticks: marks OUTCOME_DATA_GAP.
        """
        self.resolver.gap_threshold_seconds = gap_threshold_seconds
        return self.resolver.ingest_tick(epoch=epoch, price=price, symbol=symbol)

    def mark_incomplete_as_unverified(
        self,
        symbol: Optional[str] = None,
        target_status: str = STATUS_UNVERIFIED
    ):
        """Marks dangling pending predictions as OUTCOME_INCOMPLETE (or OUTCOME_UNVERIFIED).
        Guarantees that partial tick histories are NEVER classified as trading losses.
        """
        return self.resolver.mark_remaining_as_incomplete(symbol=symbol, target_status=target_status)

    def get_accuracy_metrics(
        self,
        symbol: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculates prediction accuracy, Brier Score, calibration metrics on resolved records.
        Strictly filters by session_id when specified (V1.6.2 Section 10 & 16).
        """
        with self._get_conn() as conn:
            filters = []
            params = []
            if symbol:
                filters.append("symbol = ?")
                params.append(symbol)
            if session_id:
                filters.append("session_id = ?")
                params.append(session_id)

            where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""
            cur = conn.execute(f"""
                SELECT runhigh_pred_prob, runlow_pred_prob, runhigh_win, runlow_win,
                       decision, hypothetical_pnl, outcome_status, runhigh_ask, runlow_ask,
                       session_id
                FROM forward_predictions
                {where_clause}
            """, params)
            rows = cur.fetchall()

        if not rows:
            return {
                "total_predictions": 0,
                "resolved_predictions": 0,
                "pending_predictions": 0,
                "incomplete_predictions": 0,
                "data_gap_predictions": 0,
                "unverified_predictions": 0,
                "brier_score_runhigh": None,
                "brier_score_runlow": None,
                "runhigh_brier_score": None,
                "runlow_brier_score": None,
                "runhigh_observed_win_rate": None,
                "runlow_observed_win_rate": None,
                "realized_runhigh_win_rate": None,
                "realized_runlow_win_rate": None,
                "runhigh_estimated_mean_prob": None,
                "runlow_estimated_mean_prob": None,
                "calibration_error_runhigh": None,
                "calibration_error_runlow": None,
                "quote_coverage_pct": 0.0,
                "cumulative_pnl": 0.0
            }

        total = len(rows)
        resolved = [r for r in rows if r["outcome_status"] in RESOLVED_STATUSES and r["runhigh_win"] is not None]
        pending = len([r for r in rows if r["outcome_status"] in PENDING_STATUSES])
        incomplete = len([r for r in rows if r["outcome_status"] == STATUS_INCOMPLETE])
        data_gap = len([r for r in rows if r["outcome_status"] == STATUS_DATA_GAP])
        unverified = len([r for r in rows if r["outcome_status"] == STATUS_UNVERIFIED])

        # Quote coverage across all predictions
        with_quotes = [r for r in rows if (r["runhigh_ask"] or 0) > 0 or (r["runlow_ask"] or 0) > 0]
        quote_cov = round((len(with_quotes) / total * 100.0), 2) if total > 0 else 0.0

        if not resolved:
            return {
                "total_predictions": total,
                "resolved_predictions": 0,
                "pending_predictions": pending,
                "incomplete_predictions": incomplete,
                "data_gap_predictions": data_gap,
                "unverified_predictions": unverified,
                "brier_score_runhigh": None,
                "brier_score_runlow": None,
                "runhigh_brier_score": None,
                "runlow_brier_score": None,
                "runhigh_observed_win_rate": None,
                "runlow_observed_win_rate": None,
                "realized_runhigh_win_rate": None,
                "realized_runlow_win_rate": None,
                "runhigh_estimated_mean_prob": None,
                "runlow_estimated_mean_prob": None,
                "calibration_error_runhigh": None,
                "calibration_error_runlow": None,
                "quote_coverage_pct": quote_cov,
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

        mean_pred_rh = float(np.mean(rh_preds_valid)) if rh_preds_valid else None
        mean_pred_rl = float(np.mean(rl_preds_valid)) if rl_preds_valid else None

        # Calibration error (simple expected calibration discrepancy)
        cal_err_rh = abs(mean_pred_rh - win_rate_rh) if (mean_pred_rh is not None and win_rate_rh is not None) else None
        cal_err_rl = abs(mean_pred_rl - win_rate_rl) if (mean_pred_rl is not None and win_rate_rl is not None) else None

        return {
            "total_predictions": total,
            "resolved_predictions": len(resolved),
            "pending_predictions": pending,
            "incomplete_predictions": incomplete,
            "data_gap_predictions": data_gap,
            "unverified_predictions": unverified,
            "brier_score_runhigh": round(brier_rh, 5) if brier_rh is not None else None,
            "brier_score_runlow": round(brier_rl, 5) if brier_rl is not None else None,
            "runhigh_brier_score": round(brier_rh, 5) if brier_rh is not None else None,
            "runlow_brier_score": round(brier_rl, 5) if brier_rl is not None else None,
            "runhigh_observed_win_rate": round(win_rate_rh, 5) if win_rate_rh is not None else None,
            "runlow_observed_win_rate": round(win_rate_rl, 5) if win_rate_rl is not None else None,
            "realized_runhigh_win_rate": round(win_rate_rh, 5) if win_rate_rh is not None else None,
            "realized_runlow_win_rate": round(win_rate_rl, 5) if win_rate_rl is not None else None,
            "runhigh_estimated_mean_prob": round(mean_pred_rh, 5) if mean_pred_rh is not None else None,
            "runlow_estimated_mean_prob": round(mean_pred_rl, 5) if mean_pred_rl is not None else None,
            "calibration_error_runhigh": round(cal_err_rh, 5) if cal_err_rh is not None else None,
            "calibration_error_runlow": round(cal_err_rl, 5) if cal_err_rl is not None else None,
            "quote_coverage_pct": quote_cov,
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

    def get_prediction(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single prediction by its unique ID."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM forward_predictions WHERE prediction_id = ?", (prediction_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_session_predictions(self, session_id: str) -> List[Dict[str, Any]]:
        """Returns all predictions strictly belonging to a specific session (V1.6.2 Section 10)."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT * FROM forward_predictions WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def get_session_outcomes(self, session_id: str) -> List[Dict[str, Any]]:
        """Returns all resolved outcomes strictly belonging to a specific session (V1.6.2 Section 10)."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT * FROM forward_outcomes WHERE session_id = ? ORDER BY resolution_timestamp ASC",
                (session_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def migrate_legacy_unattributed(self) -> int:
        """Migrates historical records with blank/null or unregistered session_id to LEGACY_UNATTRIBUTED (V1.6.2 Section 5 & V1.6.4)."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                UPDATE forward_predictions
                SET session_id = 'LEGACY_UNATTRIBUTED', source_provenance = 'LEGACY_UNATTRIBUTED'
                WHERE session_id = '' OR session_id IS NULL
            """)
            count = cur.rowcount

            # Migrate orphan session references not found in sessions.db
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sess_db = os.path.join(script_dir, "data", "sessions.db")
            if os.path.exists(sess_db):
                try:
                    with sqlite3.connect(sess_db, timeout=2.0) as sconn:
                        srows = sconn.execute("SELECT session_id FROM sessions").fetchall()
                        registered_sessions = {r[0] for r in srows}
                    if registered_sessions:
                        curr_rows = conn.execute(
                            "SELECT DISTINCT session_id FROM forward_predictions WHERE session_id != 'LEGACY_UNATTRIBUTED'"
                        ).fetchall()
                        for crow in curr_rows:
                            sid = crow[0]
                            if sid and sid not in registered_sessions:
                                c2 = conn.execute("""
                                    UPDATE forward_predictions
                                    SET session_id = 'LEGACY_UNATTRIBUTED', source_provenance = 'LEGACY_UNATTRIBUTED'
                                    WHERE session_id = ?
                                """, (sid,))
                                conn.execute("""
                                    UPDATE forward_outcomes
                                    SET session_id = 'LEGACY_UNATTRIBUTED'
                                    WHERE session_id = ?
                                """, (sid,))
                                count += c2.rowcount
                except Exception:
                    pass

            # Backfill outcomes table for resolved legacy predictions if not already present
            resolved = conn.execute("""
                SELECT prediction_id, session_id, entry_epoch, expiry_epoch, forward_prices_json,
                       forward_ticks_count, outcome_status, runhigh_win, runlow_win, hypothetical_pnl, timestamp
                FROM forward_predictions
                WHERE outcome_status IN ('RESOLVED', 'OUTCOME_RECONSTRUCTED', 'OUTCOME_VERIFIED')
                  AND prediction_id NOT IN (SELECT prediction_id FROM forward_outcomes)
            """).fetchall()

            now_iso = datetime.now(timezone.utc).isoformat()
            for r in resolved:
                oid = str(uuid.uuid4())[:8]
                conn.execute("""
                    INSERT OR REPLACE INTO forward_outcomes (
                        outcome_id, prediction_id, session_id, entry_epoch, expiry_epoch,
                        forward_prices_json, forward_ticks_count, outcome_status,
                        runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                        resolution_timestamp, verification_level, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    oid, r["prediction_id"], r["session_id"] or "LEGACY_UNATTRIBUTED",
                    r["entry_epoch"] or int(r["timestamp"]), r["expiry_epoch"] or int(r["timestamp"] + 6),
                    r["forward_prices_json"] or "[]", r["forward_ticks_count"] or 0, r["outcome_status"],
                    r["runhigh_win"], r["runlow_win"], r["hypothetical_pnl"] or 0.0, "5_movement_canonical",
                    float(r["expiry_epoch"] or (r["timestamp"] + 6)), "LEGACY_BACKFILLED", now_iso
                ))
            conn.commit()
            return count


