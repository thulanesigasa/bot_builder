"""Forward Research Session Manager (V1.6).

Provides reproducible, uniquely-identified forward research sessions.
Each session captures:
- Session UUID and wall-clock start time
- Symbol, mode, model ID, and config snapshot
- Paths to session-specific data artifacts
- Session lifecycle state (ACTIVE, COMPLETED, ABORTED)

Sessions are persisted to a SQLite sessions registry so historical sessions
can be inspected, compared, and cross-referenced with prediction journals.

No live-money trading is possible via this module.
"""
import contextlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config import DEFAULT_CONFIG

DEFAULT_SESSIONS_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "sessions.db"
)


# Authoritative Session Lifecycle Statuses (V1.6.2 Section 11)
STATUS_CREATED = "CREATED"
STATUS_INITIALIZING = "INITIALIZING"
STATUS_ACTIVE = "ACTIVE"
STATUS_INTERRUPTED = "INTERRUPTED"
STATUS_STOPPING = "STOPPING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

VALID_SESSION_STATUSES = {
    STATUS_CREATED,
    STATUS_INITIALIZING,
    STATUS_ACTIVE,
    STATUS_INTERRUPTED,
    STATUS_STOPPING,
    STATUS_COMPLETED,
    STATUS_FAILED,
}

# Authoritative Session Reconciliation Statuses (V1.6.2 Section 12)
RECON_STATUS_RECONCILED = "RECONCILED"
RECON_STATUS_COUNT_MISMATCH = "COUNT_MISMATCH"
RECON_STATUS_MISSING_SESSION_ID = "MISSING_SESSION_ID"
RECON_STATUS_ORPHAN_PREDICTION = "ORPHAN_PREDICTION"
RECON_STATUS_ORPHAN_OUTCOME = "ORPHAN_OUTCOME"
RECON_STATUS_CROSS_SESSION_REFERENCE = "CROSS_SESSION_REFERENCE"
RECON_STATUS_TIMESTAMP_INCONSISTENCY = "TIMESTAMP_INCONSISTENCY"
RECON_STATUS_SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"

VALID_RECONCILIATION_STATUSES = {
    RECON_STATUS_RECONCILED,
    RECON_STATUS_COUNT_MISMATCH,
    RECON_STATUS_MISSING_SESSION_ID,
    RECON_STATUS_ORPHAN_PREDICTION,
    RECON_STATUS_ORPHAN_OUTCOME,
    RECON_STATUS_CROSS_SESSION_REFERENCE,
    RECON_STATUS_TIMESTAMP_INCONSISTENCY,
    RECON_STATUS_SOURCE_UNVERIFIED,
}


@dataclass
class ForwardSession:
    """Complete description of a single forward research session."""
    session_id: str
    symbol: str
    mode: str                       # DATA_COLLECTION_ONLY, SHADOW, PAPER
    model_id: str                   # Frozen model identifier or 'NONE'
    model_version: str
    start_time: float               # Unix epoch
    end_time: Optional[float]       # None while active
    planned_duration_seconds: float
    actual_duration_seconds: Optional[float]
    status: str                     # Authoritative lifecycle status
    journal_db_path: str
    quote_db_path: str
    live_ticks_csv: str
    config_snapshot_json: str       # JSON dump of TradingConfig at session start
    total_ticks: int = 0
    live_ticks: int = 0
    warmup_ticks: int = 0
    duplicate_ticks: int = 0
    rejected_ticks: int = 0
    total_predictions: int = 0
    resolved_predictions: int = 0
    unverified_predictions: int = 0
    cumulative_pnl: float = 0.0
    reconciliation_status: str = "PENDING"
    notes: str = ""

    @property
    def start_datetime_utc(self) -> str:
        return datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat()

    @property
    def is_active(self) -> bool:
        return self.status in (STATUS_ACTIVE, STATUS_INITIALIZING)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _config_snapshot() -> str:
    """Captures a JSON snapshot of the current DEFAULT_CONFIG (non-sensitive fields only)."""
    cfg = DEFAULT_CONFIG
    safe_fields = {
        "symbol": cfg.symbol,
        "duration_ticks": cfg.duration_ticks,
        "contract_family": cfg.contract_family,
        "up_payout_ratio": cfg.up_payout_ratio,
        "down_payout_ratio": cfg.down_payout_ratio,
        "default_stake": cfg.default_stake,
        "app_id": cfg.app_id,
        "max_quote_age_seconds": cfg.max_quote_age_seconds,
        "tick_gap_threshold_seconds": cfg.tick_gap_threshold_seconds,
        "min_expected_ev": cfg.min_expected_ev,
        "min_conservative_ev": cfg.min_conservative_ev,
        "min_probability_margin": cfg.min_probability_margin,
        "min_validation_sample": cfg.min_validation_sample,
        "live_execution_disabled": cfg.live_execution_disabled,
        "enable_demo_execution": cfg.enable_demo_execution,
    }
    return json.dumps(safe_fields)


class ForwardSessionRegistry:
    """Persistent SQLite registry for all forward research sessions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_SESSIONS_DB
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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    planned_duration_seconds REAL NOT NULL,
                    actual_duration_seconds REAL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    journal_db_path TEXT NOT NULL,
                    quote_db_path TEXT NOT NULL,
                    live_ticks_csv TEXT NOT NULL,
                    config_snapshot_json TEXT NOT NULL,
                    total_ticks INTEGER DEFAULT 0,
                    live_ticks INTEGER DEFAULT 0,
                    warmup_ticks INTEGER DEFAULT 0,
                    duplicate_ticks INTEGER DEFAULT 0,
                    rejected_ticks INTEGER DEFAULT 0,
                    total_predictions INTEGER DEFAULT 0,
                    resolved_predictions INTEGER DEFAULT 0,
                    unverified_predictions INTEGER DEFAULT 0,
                    cumulative_pnl REAL DEFAULT 0.0,
                    reconciliation_status TEXT DEFAULT 'PENDING',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            # Schema migration checks for existing sessions tables
            cur = conn.execute("PRAGMA table_info(sessions)")
            cols = [r["name"] for r in cur.fetchall()]
            if "live_ticks" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN live_ticks INTEGER DEFAULT 0")
            if "warmup_ticks" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN warmup_ticks INTEGER DEFAULT 0")
            if "duplicate_ticks" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN duplicate_ticks INTEGER DEFAULT 0")
            if "rejected_ticks" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN rejected_ticks INTEGER DEFAULT 0")
            if "reconciliation_status" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN reconciliation_status TEXT DEFAULT 'PENDING'")
            conn.commit()

    def create_session(
        self,
        symbol: str,
        mode: str,
        model_id: str,
        model_version: str,
        planned_duration_seconds: float = 3600.0,
        journal_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
        live_ticks_csv: Optional[str] = None,
        notes: str = "",
        status: str = STATUS_ACTIVE
    ) -> ForwardSession:
        """Creates and persists a new session record with specified initial status."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "data")
        sid = str(uuid.uuid4())
        now = time.time()

        j_path = journal_db_path or DEFAULT_CONFIG.forward_predictions_db_path
        q_path = quote_db_path or DEFAULT_CONFIG.quotes_db_path
        t_csv = live_ticks_csv or os.path.join(data_dir, f"{symbol}_live_ticks.csv")

        session = ForwardSession(
            session_id=sid,
            symbol=symbol,
            mode=mode.upper(),
            model_id=model_id,
            model_version=model_version,
            start_time=now,
            end_time=None,
            planned_duration_seconds=planned_duration_seconds,
            actual_duration_seconds=None,
            status=status,
            journal_db_path=j_path,
            quote_db_path=q_path,
            live_ticks_csv=t_csv,
            config_snapshot_json=_config_snapshot(),
            notes=notes
        )

        created_at = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (
                    session_id, symbol, mode, model_id, model_version,
                    start_time, end_time, planned_duration_seconds, actual_duration_seconds,
                    status, journal_db_path, quote_db_path, live_ticks_csv,
                    config_snapshot_json, total_ticks, live_ticks, warmup_ticks,
                    duplicate_ticks, rejected_ticks, total_predictions,
                    resolved_predictions, unverified_predictions, cumulative_pnl,
                    reconciliation_status, notes, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                session.session_id, session.symbol, session.mode,
                session.model_id, session.model_version, session.start_time,
                None, session.planned_duration_seconds, None,
                session.status, session.journal_db_path, session.quote_db_path,
                session.live_ticks_csv, session.config_snapshot_json,
                0, 0, 0, 0, 0, 0, 0, 0, 0.0, "PENDING", notes, created_at
            ))
            conn.commit()

        return session

    def set_session_status(self, session_id: str, new_status: str, notes: Optional[str] = None):
        """Atomically transitions session lifecycle state with validation."""
        if new_status not in VALID_SESSION_STATUSES:
            raise ValueError(f"Invalid session status: {new_status}. Must be one of {VALID_SESSION_STATUSES}")
        with self._get_conn() as conn:
            if notes is not None:
                conn.execute(
                    "UPDATE sessions SET status=?, notes=? WHERE session_id=?",
                    (new_status, notes, session_id)
                )
            else:
                conn.execute(
                    "UPDATE sessions SET status=? WHERE session_id=?",
                    (new_status, session_id)
                )
            conn.commit()

    def update_reconciliation_status(self, session_id: str, status: str):
        """Persists the session reconciliation integrity status."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET reconciliation_status=? WHERE session_id=?",
                (status, session_id)
            )
            conn.commit()

    def update_session_stats(
        self,
        session_id: str,
        total_ticks: int = 0,
        live_ticks: Optional[int] = None,
        warmup_ticks: Optional[int] = None,
        duplicate_ticks: Optional[int] = None,
        rejected_ticks: Optional[int] = None,
        total_predictions: int = 0,
        resolved_predictions: int = 0,
        unverified_predictions: int = 0,
        cumulative_pnl: float = 0.0,
        reconciliation_status: Optional[str] = None
    ):
        """Updates live session statistics with granular tick accounting."""
        lt = live_ticks if live_ticks is not None else total_ticks
        wt = warmup_ticks if warmup_ticks is not None else 0
        dt = duplicate_ticks if duplicate_ticks is not None else 0
        rt = rejected_ticks if rejected_ticks is not None else 0

        with self._get_conn() as conn:
            if reconciliation_status:
                conn.execute("""
                    UPDATE sessions
                    SET total_ticks=?, live_ticks=?, warmup_ticks=?, duplicate_ticks=?, rejected_ticks=?,
                        total_predictions=?, resolved_predictions=?,
                        unverified_predictions=?, cumulative_pnl=?, reconciliation_status=?
                    WHERE session_id=?
                """, (total_ticks, lt, wt, dt, rt, total_predictions, resolved_predictions,
                      unverified_predictions, round(cumulative_pnl, 4), reconciliation_status, session_id))
            else:
                conn.execute("""
                    UPDATE sessions
                    SET total_ticks=?, live_ticks=?, warmup_ticks=?, duplicate_ticks=?, rejected_ticks=?,
                        total_predictions=?, resolved_predictions=?,
                        unverified_predictions=?, cumulative_pnl=?
                    WHERE session_id=?
                """, (total_ticks, lt, wt, dt, rt, total_predictions, resolved_predictions,
                      unverified_predictions, round(cumulative_pnl, 4), session_id))
            conn.commit()

    def complete_session(
        self,
        session_id: str,
        status: str = STATUS_COMPLETED,
        total_ticks: int = 0,
        live_ticks: Optional[int] = None,
        warmup_ticks: Optional[int] = None,
        duplicate_ticks: Optional[int] = None,
        rejected_ticks: Optional[int] = None,
        total_predictions: int = 0,
        resolved_predictions: int = 0,
        unverified_predictions: int = 0,
        cumulative_pnl: float = 0.0,
        reconciliation_status: Optional[str] = None,
        notes: str = ""
    ):
        """Marks a session as COMPLETED, INTERRUPTED, or FAILED and records final metrics."""
        end_time = time.time()
        lt = live_ticks if live_ticks is not None else total_ticks
        wt = warmup_ticks if warmup_ticks is not None else 0
        dt = duplicate_ticks if duplicate_ticks is not None else 0
        rt = rejected_ticks if rejected_ticks is not None else 0

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT start_time FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            actual_dur = round(end_time - float(row["start_time"]), 2) if row else None
            conn.execute("""
                UPDATE sessions
                SET status=?, end_time=?, actual_duration_seconds=?,
                    total_ticks=?, live_ticks=?, warmup_ticks=?, duplicate_ticks=?, rejected_ticks=?,
                    total_predictions=?, resolved_predictions=?,
                    unverified_predictions=?, cumulative_pnl=?, notes=?
                WHERE session_id=?
            """, (
                status, end_time, actual_dur,
                total_ticks, lt, wt, dt, rt,
                total_predictions, resolved_predictions,
                unverified_predictions, round(cumulative_pnl, 4),
                notes, session_id
            ))
            if reconciliation_status:
                conn.execute(
                    "UPDATE sessions SET reconciliation_status=? WHERE session_id=?",
                    (reconciliation_status, session_id)
                )
            conn.commit()

    def update_reconciliation_status(self, session_id: str, reconciliation_status: str):
        """Updates the authoritative reconciliation status of a session (V1.6.2 Section 12)."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET reconciliation_status=? WHERE session_id=?",
                (reconciliation_status, session_id)
            )
            conn.commit()

    def recover_interrupted_sessions(self, max_grace_seconds: float = 30.0) -> List[str]:
        """Scans for active/initializing sessions that crashed or were abandoned on restart."""
        recovered = []
        now = time.time()
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT session_id, start_time, planned_duration_seconds
                FROM sessions
                WHERE status IN ('ACTIVE', 'INITIALIZING', 'CREATED')
            """).fetchall()

            for r in rows:
                sid = r["session_id"]
                st = float(r["start_time"])
                planned = float(r["planned_duration_seconds"] or 0.0)
                # If planned duration elapsed + grace period, or if process restarted
                dur = round(now - st, 2)
                conn.execute("""
                    UPDATE sessions
                    SET status=?, end_time=?, actual_duration_seconds=?, notes=notes || ' [Auto-recovered on startup]'
                    WHERE session_id=?
                """, (STATUS_INTERRUPTED, now, dur, sid))
                recovered.append(sid)

            if recovered:
                conn.commit()
        return recovered

    def get_session(self, session_id: str) -> Optional[ForwardSession]:
        """Retrieves a session by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def list_sessions(
        self,
        symbol: Optional[str] = None,
        limit: int = 20
    ) -> List[ForwardSession]:
        """Lists recent sessions in reverse chronological order."""
        with self._get_conn() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE symbol=? ORDER BY start_time DESC LIMIT ?",
                    (symbol, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def get_active_session(self, symbol: Optional[str] = None) -> Optional[ForwardSession]:
        """Returns the most recent ACTIVE session, optionally filtered by symbol."""
        with self._get_conn() as conn:
            if symbol:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE status='ACTIVE' AND symbol=? ORDER BY start_time DESC LIMIT 1",
                    (symbol,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE status='ACTIVE' ORDER BY start_time DESC LIMIT 1"
                ).fetchone()
        return self._row_to_session(row) if row else None

    @staticmethod
    def _row_to_session(row) -> ForwardSession:
        d = dict(row)
        return ForwardSession(
            session_id=d["session_id"],
            symbol=d["symbol"],
            mode=d["mode"],
            model_id=d["model_id"],
            model_version=d["model_version"],
            start_time=d["start_time"],
            end_time=d.get("end_time"),
            planned_duration_seconds=d["planned_duration_seconds"],
            actual_duration_seconds=d.get("actual_duration_seconds"),
            status=d["status"],
            journal_db_path=d["journal_db_path"],
            quote_db_path=d["quote_db_path"],
            live_ticks_csv=d["live_ticks_csv"],
            config_snapshot_json=d.get("config_snapshot_json", "{}"),
            total_ticks=d.get("total_ticks", 0),
            live_ticks=d.get("live_ticks", d.get("total_ticks", 0)),
            warmup_ticks=d.get("warmup_ticks", 0),
            duplicate_ticks=d.get("duplicate_ticks", 0),
            rejected_ticks=d.get("rejected_ticks", 0),
            total_predictions=d.get("total_predictions", 0),
            resolved_predictions=d.get("resolved_predictions", 0),
            unverified_predictions=d.get("unverified_predictions", 0),
            cumulative_pnl=d.get("cumulative_pnl", 0.0),
            reconciliation_status=d.get("reconciliation_status", "PENDING"),
            notes=d.get("notes", "")
        )

