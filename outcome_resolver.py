"""Persistent Outcome Resolver Engine (V1.6.4).

Resolves forward contract outcomes for Deriv RUNHIGH and RUNLOW predictions
using verified sequences of future ticks observed after prediction generation.

Canonical 5-Movement Lifecycle:
  Prediction Signal (t_sig, P_sig)
  -> First subsequent tick: Entry Spot S_0 (t_0 > t_sig, P_0)
  -> Successive movements: S_1, S_2, S_3, S_4, S_5 (Expiry Spot)
  -> RUNHIGH wins iff S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4
  -> RUNLOW wins iff S_1 < S_0 AND S_2 < S_1 AND S_3 < S_2 AND S_4 < S_3 AND S_5 < S_4
  -> Ties or reversals are classified as losses under the canonical research model.

Key Architectural Guarantees:
  1. Multiple overlapping predictions are tracked and resolved independently.
  2. Consecutive tick gaps are measured BETWEEN SUCCESSIVE TICKS in the forward window
     (not from the initial entry spot), eliminating false OUTCOME_DATA_GAP triggers.
  3. Strict chronological boundary enforcement: price movements prior to or at the
     prediction signal are NEVER used for outcome evaluation.
  4. Rich unresolved diagnostics: WAITING_FOR_ENTRY_TICK, WAITING_FOR_FUTURE_TICKS (n/6),
     TICK_SEQUENCE_GAP, SESSION_ENDED_BEFORE_RESOLUTION, OUTCOME_WINDOW_INCOMPLETE.
  5. Immutable outcome persistence to forward_outcomes and forward_predictions.
"""

import contextlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

# Canonical Outcome Statuses
STATUS_PENDING = "OUTCOME_PENDING"
STATUS_RESOLVED = "RESOLVED"
STATUS_RECONSTRUCTED = "OUTCOME_RECONSTRUCTED"
STATUS_VERIFIED = "OUTCOME_VERIFIED"
STATUS_INCOMPLETE = "OUTCOME_INCOMPLETE"
STATUS_DATA_GAP = "OUTCOME_DATA_GAP"
STATUS_UNVERIFIED = "OUTCOME_UNVERIFIED"

# Diagnostic Reasons (V1.6.4 Part J Section 23)
REASON_WAITING_FOR_ENTRY_TICK = "WAITING_FOR_ENTRY_TICK"
REASON_WAITING_FOR_FUTURE_TICKS = "WAITING_FOR_FUTURE_TICKS"
REASON_OUTCOME_WINDOW_INCOMPLETE = "OUTCOME_WINDOW_INCOMPLETE"
REASON_STREAM_DISCONNECTED = "STREAM_DISCONNECTED"
REASON_TICK_SEQUENCE_GAP = "TICK_SEQUENCE_GAP"
REASON_CONTRACT_MODEL_AMBIGUOUS = "CONTRACT_MODEL_AMBIGUOUS"
REASON_SESSION_ENDED_BEFORE_RESOLUTION = "SESSION_ENDED_BEFORE_RESOLUTION"
REASON_DATABASE_WRITE_FAILED = "DATABASE_WRITE_FAILED"
REASON_INVALID_TICK_REFERENCE = "INVALID_TICK_REFERENCE"
REASON_CROSS_SESSION_REFERENCE = "CROSS_SESSION_REFERENCE"


@dataclass
class PendingOutcome:
    """State of an in-flight forward prediction awaiting future tick resolution."""
    prediction_id: str
    session_id: str
    symbol: str
    contract_type: str                  # RUNHIGH, RUNLOW, or RUNHIGH_RUNLOW
    contract_duration: int              # Number of movements (standard = 5)
    prediction_timestamp: float         # Signal creation timestamp (epoch)
    signal_price: float
    model_version: str
    decision: str
    target_direction: str
    runhigh_ask: Optional[float]
    runhigh_payout: Optional[float]
    runlow_ask: Optional[float]
    runlow_payout: Optional[float]
    required_entry_boundary: float      # Ticks must have epoch > required_entry_boundary
    required_future_tick_count: int = 6 # S_0 (entry spot) + 5 successive movements = 6 ticks
    entry_epoch: Optional[int] = None
    entry_price: Optional[float] = None
    forward_prices: List[float] = field(default_factory=list)
    forward_epochs: List[int] = field(default_factory=list)
    last_processed_tick_epoch: Optional[int] = None
    outcome_status: str = STATUS_PENDING
    unresolved_reason: str = REASON_WAITING_FOR_ENTRY_TICK
    resolver_version: str = "1.6.4"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "session_id": self.session_id,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "contract_duration": self.contract_duration,
            "prediction_timestamp": self.prediction_timestamp,
            "signal_price": self.signal_price,
            "model_version": self.model_version,
            "decision": self.decision,
            "target_direction": self.target_direction,
            "required_future_tick_count": self.required_future_tick_count,
            "collected_future_ticks": len(self.forward_prices),
            "entry_epoch": self.entry_epoch,
            "entry_price": self.entry_price,
            "forward_prices": list(self.forward_prices),
            "forward_epochs": list(self.forward_epochs),
            "last_processed_tick_epoch": self.last_processed_tick_epoch,
            "outcome_status": self.outcome_status,
            "unresolved_reason": self.unresolved_reason,
            "resolver_version": self.resolver_version,
        }


class OutcomeResolver:
    """Persistent outcome tracking and resolution engine."""

    def __init__(
        self,
        db_path: str,
        gap_threshold_seconds: float = 5.0,
        required_movements: int = 5,
        resolver_version: str = "1.6.4"
    ):
        self.db_path = db_path
        self.gap_threshold_seconds = gap_threshold_seconds
        self.required_movements = required_movements
        self.required_ticks_total = required_movements + 1  # S_0 entry spot + movements
        self.resolver_version = resolver_version
        self._active_pending: Dict[str, PendingOutcome] = {}
        self._ensure_schema()
        self.load_pending_from_db()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self):
        """Ensures database tables exist and contain all required columns for V1.6.4."""
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
                    created_at TEXT NOT NULL,
                    unresolved_reason TEXT DEFAULT '',
                    forward_epochs_json TEXT DEFAULT '[]',
                    last_forward_epoch INTEGER
                )
            """)
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
                    symbol TEXT DEFAULT 'R_75',
                    contract_type TEXT DEFAULT 'RUNHIGH_RUNLOW',
                    entry_price REAL,
                    forward_epochs_json TEXT DEFAULT '[]',
                    resolver_version TEXT DEFAULT '1.6.4',
                    unresolved_reason TEXT DEFAULT '',
                    FOREIGN KEY (prediction_id) REFERENCES forward_predictions(prediction_id)
                )
            """)

            # Check and add columns to forward_predictions in case it was created with an older schema
            cur = conn.execute("PRAGMA table_info(forward_predictions)")
            pred_cols = {r["name"] for r in cur.fetchall()}

            if "unresolved_reason" not in pred_cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN unresolved_reason TEXT DEFAULT ''")
            if "forward_epochs_json" not in pred_cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN forward_epochs_json TEXT DEFAULT '[]'")
            if "last_forward_epoch" not in pred_cols:
                conn.execute("ALTER TABLE forward_predictions ADD COLUMN last_forward_epoch INTEGER")

            # Check and add columns to forward_outcomes
            cur = conn.execute("PRAGMA table_info(forward_outcomes)")
            out_cols = {r["name"] for r in cur.fetchall()}

            if "symbol" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN symbol TEXT DEFAULT 'R_75'")
            if "contract_type" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN contract_type TEXT DEFAULT 'RUNHIGH_RUNLOW'")
            if "entry_price" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN entry_price REAL")
            if "forward_epochs_json" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN forward_epochs_json TEXT DEFAULT '[]'")
            if "resolver_version" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN resolver_version TEXT DEFAULT '1.6.4'")
            if "unresolved_reason" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN unresolved_reason TEXT DEFAULT ''")
            if "verification_level" not in out_cols:
                conn.execute("ALTER TABLE forward_outcomes ADD COLUMN verification_level TEXT DEFAULT 'RECONSTRUCTED'")

            conn.commit()

    def load_pending_from_db(self, symbol: Optional[str] = None):
        """Loads or synchronizes active pending predictions from the database."""
        with self._get_conn() as conn:
            where_sql = "WHERE outcome_status IN ('PENDING', 'OUTCOME_PENDING')"
            params: List[Any] = []
            if symbol:
                where_sql += " AND symbol = ?"
                params.append(symbol)

            cur = conn.execute(f"""
                SELECT prediction_id, session_id, symbol, model_version, decision,
                       target_direction, signal_epoch, signal_price, timestamp,
                       entry_epoch, forward_prices_json, forward_ticks_count,
                       runhigh_ask, runhigh_payout, runlow_ask, runlow_payout,
                       unresolved_reason, forward_epochs_json, last_forward_epoch
                FROM forward_predictions
                {where_sql}
                ORDER BY timestamp ASC
            """, params)

            rows = cur.fetchall()
            for r in rows:
                pid = r["prediction_id"]
                if pid in self._active_pending:
                    continue  # Already in memory

                try:
                    fwd_prices = json.loads(r["forward_prices_json"] or "[]")
                except Exception:
                    fwd_prices = []

                try:
                    fwd_epochs = json.loads(r["forward_epochs_json"] or "[]")
                except Exception:
                    fwd_epochs = []

                entry_ep = r["entry_epoch"]
                sig_ep = r["signal_epoch"] or int(r["timestamp"])
                entry_pr = fwd_prices[0] if fwd_prices else None
                last_ep = r["last_forward_epoch"] or (fwd_epochs[-1] if fwd_epochs else (entry_ep or sig_ep))

                reason = r["unresolved_reason"]
                if not reason:
                    if not fwd_prices:
                        reason = REASON_WAITING_FOR_ENTRY_TICK
                    else:
                        reason = f"{REASON_WAITING_FOR_FUTURE_TICKS} ({len(fwd_prices)}/{self.required_ticks_total})"

                self._active_pending[pid] = PendingOutcome(
                    prediction_id=pid,
                    session_id=r["session_id"] or "LEGACY_UNATTRIBUTED",
                    symbol=r["symbol"],
                    contract_type="RUNHIGH_RUNLOW",
                    contract_duration=self.required_movements,
                    prediction_timestamp=float(r["timestamp"]),
                    signal_price=float(r["signal_price"] or 0.0),
                    model_version=r["model_version"] or "V1.6.4",
                    decision=r["decision"] or "NO_TRADE",
                    target_direction=r["target_direction"] or "NONE",
                    runhigh_ask=r["runhigh_ask"],
                    runhigh_payout=r["runhigh_payout"],
                    runlow_ask=r["runlow_ask"],
                    runlow_payout=r["runlow_payout"],
                    required_entry_boundary=float(sig_ep),
                    required_future_tick_count=self.required_ticks_total,
                    entry_epoch=entry_ep,
                    entry_price=entry_pr,
                    forward_prices=fwd_prices,
                    forward_epochs=fwd_epochs,
                    last_processed_tick_epoch=last_ep,
                    outcome_status=STATUS_PENDING,
                    unresolved_reason=reason,
                    resolver_version=self.resolver_version
                )

    def register_pending_prediction(
        self,
        prediction_id: str,
        session_id: str,
        symbol: str,
        signal_epoch: int,
        signal_price: float,
        timestamp: float,
        model_version: str = "V1.6.4",
        decision: str = "NO_TRADE",
        target_direction: str = "NONE",
        runhigh_ask: Optional[float] = None,
        runhigh_payout: Optional[float] = None,
        runlow_ask: Optional[float] = None,
        runlow_payout: Optional[float] = None,
    ) -> PendingOutcome:
        """Registers a newly generated prediction as an active pending outcome."""
        pending = PendingOutcome(
            prediction_id=prediction_id,
            session_id=session_id or "LEGACY_UNATTRIBUTED",
            symbol=symbol,
            contract_type="RUNHIGH_RUNLOW",
            contract_duration=self.required_movements,
            prediction_timestamp=timestamp,
            signal_price=signal_price,
            model_version=model_version,
            decision=decision,
            target_direction=target_direction,
            runhigh_ask=runhigh_ask,
            runhigh_payout=runhigh_payout,
            runlow_ask=runlow_ask,
            runlow_payout=runlow_payout,
            required_entry_boundary=float(signal_epoch),
            required_future_tick_count=self.required_ticks_total,
            outcome_status=STATUS_PENDING,
            unresolved_reason=REASON_WAITING_FOR_ENTRY_TICK,
            resolver_version=self.resolver_version
        )
        self._active_pending[prediction_id] = pending

        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO forward_predictions (
                    prediction_id, session_id, timestamp, symbol, model_version,
                    market_state, decision, rejection_reason, target_direction,
                    signal_epoch, signal_price, forward_prices_json, forward_ticks_count,
                    outcome_status, created_at, forward_epochs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', 0, ?, ?, '[]')
            """, (
                prediction_id, session_id or "LEGACY_UNATTRIBUTED", timestamp, symbol,
                model_version, "DEFAULT", decision, "", target_direction,
                signal_epoch, signal_price, STATUS_PENDING,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

        return pending

    def ingest_tick(
        self,
        epoch: int,
        price: float,
        symbol: str = "R_75"
    ) -> List[Dict[str, Any]]:
        """Ingests a live or recovered tick, updating all active pending predictions.
        
        Returns a list of outcome resolution events occurred during this tick.
        """
        resolved_events: List[Dict[str, Any]] = []
        if not self._active_pending:
            # Sync with database in case new predictions were logged externally
            self.load_pending_from_db(symbol=symbol)
            if not self._active_pending:
                return resolved_events

        # Iterate over copy of pending IDs
        active_ids = list(self._active_pending.keys())
        pids_to_remove: List[str] = []

        with self._get_conn() as conn:
            for pid in active_ids:
                pending = self._active_pending.get(pid)
                if not pending or pending.symbol != symbol:
                    continue

                # 1. Enforce chronological boundary: tick must be strictly future to prediction signal
                if epoch <= pending.required_entry_boundary:
                    continue

                # 2. Check for duplicate or out-of-order ticks in this pending window
                if pending.last_processed_tick_epoch is not None:
                    if epoch <= pending.last_processed_tick_epoch:
                        # Out-of-order or duplicate tick received; ignore without corrupting state
                        continue

                    # 3. Check consecutive tick gap BETWEEN SUCCESSIVE TICKS
                    tick_delta = epoch - pending.last_processed_tick_epoch
                    if tick_delta > self.gap_threshold_seconds:
                        # Genuine tick gap detected!
                        pending.outcome_status = STATUS_DATA_GAP
                        pending.unresolved_reason = f"{REASON_TICK_SEQUENCE_GAP}: delta {tick_delta:.1f}s > {self.gap_threshold_seconds:.1f}s"
                        
                        # Update database
                        conn.execute("""
                            UPDATE forward_predictions
                            SET outcome_status = ?, expiry_epoch = ?, unresolved_reason = ?,
                                last_forward_epoch = ?
                            WHERE prediction_id = ?
                        """, (STATUS_DATA_GAP, epoch, pending.unresolved_reason, epoch, pid))

                        # Record gap in forward_outcomes
                        oid = str(uuid.uuid4())[:8]
                        now_iso = datetime.now(timezone.utc).isoformat()
                        conn.execute("""
                            INSERT OR REPLACE INTO forward_outcomes (
                                outcome_id, prediction_id, session_id, symbol, contract_type,
                                entry_epoch, entry_price, expiry_epoch, forward_prices_json,
                                forward_epochs_json, forward_ticks_count, outcome_status,
                                runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                                resolution_timestamp, verification_level, resolver_version,
                                unresolved_reason, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            oid, pid, pending.session_id, pending.symbol, pending.contract_type,
                            pending.entry_epoch, pending.entry_price, epoch,
                            json.dumps(pending.forward_prices), json.dumps(pending.forward_epochs),
                            len(pending.forward_prices), STATUS_DATA_GAP, None, None, 0.0,
                            "5_movement_canonical", float(epoch), "DATA_GAP",
                            self.resolver_version, pending.unresolved_reason, now_iso
                        ))

                        pids_to_remove.append(pid)
                        resolved_events.append({
                            "prediction_id": pid,
                            "outcome_status": STATUS_DATA_GAP,
                            "reason": pending.unresolved_reason
                        })
                        continue

                # 4. Ingest tick into outcome window
                if pending.entry_epoch is None:
                    # First tick is Entry Spot S_0
                    pending.entry_epoch = epoch
                    pending.entry_price = price

                pending.forward_prices.append(price)
                pending.forward_epochs.append(epoch)
                pending.last_processed_tick_epoch = epoch
                count = len(pending.forward_prices)

                if count < self.required_ticks_total:
                    # Window accumulating
                    pending.outcome_status = STATUS_PENDING
                    pending.unresolved_reason = f"{REASON_WAITING_FOR_FUTURE_TICKS} ({count}/{self.required_ticks_total})"

                    conn.execute("""
                        UPDATE forward_predictions
                        SET forward_prices_json = ?, forward_epochs_json = ?,
                            forward_ticks_count = ?, entry_epoch = ?,
                            last_forward_epoch = ?, unresolved_reason = ?
                        WHERE prediction_id = ?
                    """, (
                        json.dumps(pending.forward_prices),
                        json.dumps(pending.forward_epochs),
                        count,
                        pending.entry_epoch,
                        epoch,
                        pending.unresolved_reason,
                        pid
                    ))
                else:
                    # Complete canonical 6-tick sequence: S_0, S_1, S_2, S_3, S_4, S_5
                    prices = pending.forward_prices[:self.required_ticks_total]
                    epochs = pending.forward_epochs[:self.required_ticks_total]

                    # Canonical 5-movement evaluation
                    # S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4
                    rh_win = 1.0 if all(prices[k] > prices[k - 1] for k in range(1, 6)) else 0.0
                    rl_win = 1.0 if all(prices[k] < prices[k - 1] for k in range(1, 6)) else 0.0

                    # Hypothetical PnL calculation
                    pnl = 0.0
                    td = pending.target_direction
                    dec = pending.decision
                    rh_ask = pending.runhigh_ask
                    rh_pay = pending.runhigh_payout
                    rl_ask = pending.runlow_ask
                    rl_pay = pending.runlow_payout

                    if dec in ("TRADE", "PAPER_TRADE"):
                        if td == "RUNHIGH" and rh_pay is not None and rh_ask is not None:
                            pnl = (rh_pay - rh_ask) if rh_win == 1.0 else -rh_ask
                        elif td == "RUNLOW" and rl_pay is not None and rl_ask is not None:
                            pnl = (rl_pay - rl_ask) if rl_win == 1.0 else -rl_ask

                    pending.outcome_status = STATUS_RECONSTRUCTED
                    pending.unresolved_reason = ""

                    # Update forward_predictions
                    conn.execute("""
                        UPDATE forward_predictions
                        SET forward_prices_json = ?, forward_epochs_json = ?,
                            forward_ticks_count = ?, outcome_status = ?,
                            runhigh_win = ?, runlow_win = ?, hypothetical_pnl = ?,
                            expiry_epoch = ?, last_forward_epoch = ?, unresolved_reason = ?
                        WHERE prediction_id = ?
                    """, (
                        json.dumps(prices), json.dumps(epochs), count,
                        STATUS_RECONSTRUCTED, rh_win, rl_win, round(pnl, 2),
                        epoch, epoch, "", pid
                    ))

                    # Persist dedicated forward_outcomes record
                    oid = str(uuid.uuid4())[:8]
                    now_iso = datetime.now(timezone.utc).isoformat()
                    conn.execute("""
                        INSERT OR REPLACE INTO forward_outcomes (
                            outcome_id, prediction_id, session_id, symbol, contract_type,
                            entry_epoch, entry_price, expiry_epoch, forward_prices_json,
                            forward_epochs_json, forward_ticks_count, outcome_status,
                            runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                            resolution_timestamp, verification_level, resolver_version,
                            unresolved_reason, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        oid, pid, pending.session_id, pending.symbol, pending.contract_type,
                        pending.entry_epoch, pending.entry_price, epoch,
                        json.dumps(prices), json.dumps(epochs), count, STATUS_RECONSTRUCTED,
                        rh_win, rl_win, round(pnl, 2), "5_movement_canonical",
                        float(epoch), "RECONSTRUCTED", self.resolver_version, "", now_iso
                    ))

                    pids_to_remove.append(pid)
                    resolved_events.append({
                        "prediction_id": pid,
                        "outcome_id": oid,
                        "outcome_status": STATUS_RECONSTRUCTED,
                        "runhigh_win": rh_win,
                        "runlow_win": rl_win,
                        "hypothetical_pnl": round(pnl, 2),
                        "prices": prices,
                        "epochs": epochs
                    })

            conn.commit()

        # Remove finished outcomes from in-memory tracking
        for pid in pids_to_remove:
            self._active_pending.pop(pid, None)

        return resolved_events

    def mark_remaining_as_incomplete(
        self,
        symbol: Optional[str] = None,
        reason: str = REASON_SESSION_ENDED_BEFORE_RESOLUTION,
        target_status: str = STATUS_INCOMPLETE
    ) -> int:
        """Marks any outstanding pending predictions as OUTCOME_INCOMPLETE (or target_status).
        
        Strict rule: partial forward windows are NEVER classified as trading losses.
        """
        with self._get_conn() as conn:
            where_sql = "WHERE outcome_status IN ('PENDING', 'OUTCOME_PENDING')"
            params: List[Any] = [target_status, reason]
            if symbol:
                where_sql += " AND symbol = ?"
                params.append(symbol)

            cur = conn.execute(f"""
                UPDATE forward_predictions
                SET outcome_status = ?, unresolved_reason = ?
                {where_sql}
            """, params)
            count = cur.rowcount

            # Also create incomplete outcome records in forward_outcomes if missing
            pending_preds = conn.execute(f"""
                SELECT prediction_id, session_id, symbol, entry_epoch, signal_epoch,
                       forward_prices_json, forward_epochs_json, forward_ticks_count, timestamp
                FROM forward_predictions
                WHERE outcome_status = ?
                  AND prediction_id NOT IN (SELECT prediction_id FROM forward_outcomes)
            """, (target_status,)).fetchall()

            now_iso = datetime.now(timezone.utc).isoformat()
            now_ts = time.time()
            for r in pending_preds:
                oid = str(uuid.uuid4())[:8]
                try:
                    fp = json.loads(r["forward_prices_json"] or "[]")
                except Exception:
                    fp = []
                try:
                    fe = json.loads(r["forward_epochs_json"] or "[]")
                except Exception:
                    fe = []
                ep_val = r["entry_epoch"] or r["signal_epoch"] or int(r["timestamp"])

                conn.execute("""
                    INSERT OR REPLACE INTO forward_outcomes (
                        outcome_id, prediction_id, session_id, symbol, contract_type,
                        entry_epoch, entry_price, expiry_epoch, forward_prices_json,
                        forward_epochs_json, forward_ticks_count, outcome_status,
                        runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                        resolution_timestamp, verification_level, resolver_version,
                        unresolved_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    oid, r["prediction_id"], r["session_id"] or "LEGACY_UNATTRIBUTED",
                    r["symbol"] or "R_75", "RUNHIGH_RUNLOW", ep_val, fp[0] if fp else None,
                    fe[-1] if fe else ep_val, json.dumps(fp), json.dumps(fe),
                    len(fp), target_status, None, None, 0.0, "5_movement_canonical",
                    now_ts, "UNVERIFIED", self.resolver_version, reason, now_iso
                ))

            conn.commit()

        if symbol:
            self._active_pending = {
                pid: p for pid, p in self._active_pending.items() if p.symbol != symbol
            }
        else:
            self._active_pending.clear()

        return count

    @property
    def active_pending_count(self) -> int:
        return len(self._active_pending)

    def get_pending_summary(self) -> Dict[str, Any]:
        """Provides an auditable diagnostic summary of in-flight outcomes."""
        items = [p.to_dict() for p in self._active_pending.values()]
        return {
            "active_pending_count": len(items),
            "pending_outcomes": items,
            "resolver_version": self.resolver_version,
            "gap_threshold_seconds": self.gap_threshold_seconds,
            "required_movements": self.required_movements
        }
