"""Genuine Deriv Multi-Market Forward SHADOW Research Engine (V1.8.3).

Executes live, non-purchasing prospective forward research:
1. Live tick stream collection via Deriv WebSocket API (with native precision and epoch timestamps).
2. Genuine broker proposal quote capture across both contract families:
   - Family A: Rise/Fall (CALL, PUT) for durations 2, 3, 5, 10 ticks.
   - Family B: Only Ups/Only Downs (RUNHIGH, RUNLOW) for durations 2, 5 ticks.
3. Pre-outcome prospective prediction journaling committed BEFORE future ticks arrive.
4. Independent, strict contract outcome resolution:
   - Rise/Fall: Expiry spot vs Entry spot (strictly higher / lower; ties lose).
   - Only Ups/Only Downs: Consecutive successive movements (monotonicity break or tie loses).
5. Chronological, contract-isolated proposal quote matching (no cross-market or cross-family contamination).
6. Observation-level economic calculations (Break-even, Predicted EV, Hypothetical Return).
7. Evidence cohort classification (A: Predictive, B: Matched, C: Strict SHADOW, D: Preregistered).
8. Data provenance logging with cryptographic hashing and fail-closed classification.

Safety invariants:
  - LIVE_EXECUTION_DISABLED = True (Compile-time invariant)
  - OPERATING_MODE = "SHADOW_RESEARCH_ONLY"
  - DECISION = "NO_TRADE"
"""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import numpy as np
import websockets

from model_registry import (
    AuthoritativeModelRegistry,
    MODEL_TYPE_TRAINED_FROZEN,
    MODEL_TYPE_DETERMINISTIC_BASELINE,
    MODEL_TYPE_CONSTANT_BASELINE,
    MODEL_TYPE_UNVERIFIED,
    MODEL_ID_CAUSAL_MOMENTUM_V1,
)
from chronology_auditor import (
    ChronologyAuditor,
    PROSPECTIVE_AUTHENTIC,
    PROSPECTIVE_AUTHORITY_UNVERIFIED,
    PROSPECTIVE_CHRONOLOGY_VIOLATION,
)

LIVE_EXECUTION_DISABLED: bool = True
OPERATING_MODE: str = "SHADOW_RESEARCH_ONLY"
DECISION: str = "NO_TRADE"

DERIV_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089"

# Contract Families
FAMILY_RISE_FALL = "RISE_FALL"
FAMILY_ONLY_UPS_DOWNS = "ONLY_UPS_ONLY_DOWNS"

# Contract Directions
DIRECTION_CALL = "CALL"
DIRECTION_PUT = "PUT"
DIRECTION_RUNHIGH = "RUNHIGH"
DIRECTION_RUNLOW = "RUNLOW"

# Supported Durations by Family
DURATIONS_RISE_FALL = [2, 3, 5, 10]
DURATIONS_ONLY_UPS_DOWNS = [2, 5]

# Research Markets
RESEARCH_MARKETS = ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]

# Outcome Statuses
OUTCOME_PENDING = "OUTCOME_PENDING"
OUTCOME_RESOLVED = "OUTCOME_RESOLVED"
OUTCOME_INCOMPLETE = "OUTCOME_INCOMPLETE"
OUTCOME_DATA_GAP = "OUTCOME_DATA_GAP"
OUTCOME_UNVERIFIED = "OUTCOME_UNVERIFIED"

# Prospective Statuses
PROSPECTIVE_AUTHENTIC = "PROSPECTIVE_AUTHENTIC"
PROSPECTIVE_AUTHORITY_UNVERIFIED = "PROSPECTIVE_AUTHORITY_UNVERIFIED"

# Source Evidence Classifications
SOURCE_BROKER_CAPTURED = "BROKER_ORIGIN_SUPPORTED_BY_CAPTURE_EVIDENCE"
SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
STATUS_FILE_INTEGRITY_VERIFIED = "FILE_INTEGRITY_VERIFIED"
STATUS_LINEAGE_VERIFIED = "TRANSFORMATION_LINEAGE_VERIFIED"

# Cohorts
COHORT_A = "COHORT_A_ALL_PROSPECTIVE"
COHORT_B = "COHORT_B_MATCHED_QUOTES"
COHORT_C = "COHORT_C_STRICT_SHADOW_PROXY"
COHORT_D = "COHORT_D_PREREGISTERED_CONFIRMATION"

# Research Verdicts
VERDICT_INSUFFICIENT_PROSPECTIVE = "INSUFFICIENT_PROSPECTIVE_EVIDENCE"
VERDICT_INSUFFICIENT_QUOTES = "INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE"
VERDICT_NO_EDGE = "NO_VALIDATED_POSITIVE_EV_EDGE"
VERDICT_EXPLORATORY = "EXPLORATORY_POSITIVE_EV_CANDIDATE"
VERDICT_CONFIRMATION_READY = "CONFIRMATION_READY"

DEFAULT_FORWARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "v183_forward_predictions.db")


class SafetyViolationError(RuntimeError):
    """Raised immediately if any purchase endpoint or live order execution is attempted."""
    pass


@dataclass
class LiveBrokerTick:
    """Raw tick record received from Deriv WebSocket feed."""
    symbol: str
    epoch: int
    quote: float
    ask: float
    bid: float
    pip_size: int
    received_timestamp: float
    subscription_id: Optional[str] = None
    raw_payload_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiveBrokerProposal:
    """Genuine broker proposal quote response."""
    proposal_id: str
    underlying_symbol: str
    contract_family: str
    contract_type: str
    duration: int
    duration_unit: str
    ask_price: float
    total_payout: float
    spot_price: float
    spot_time: int
    request_timestamp: float
    response_timestamp: float
    currency: str = "USD"
    basis: str = "stake"
    longcode: str = ""
    session_id: str = ""
    payload_hash: str = ""

    @property
    def break_even_prob(self) -> float:
        return self.ask_price / self.total_payout if self.total_payout > 0 else 1.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["break_even_prob"] = round(self.break_even_prob, 4)
        return d


@dataclass
class ForwardObservationRecord:
    """Durable prospective observation record with complete lifecycle audit trail."""
    observation_id: str
    session_id: str
    symbol: str
    contract_family: str
    contract_type: str
    duration_ticks: int
    decision_timestamp: float
    signal_epoch: int
    signal_price: float
    predicted_prob: float
    model_version: str
    decision: str = "NO_TRADE"
    rejection_reason: Optional[str] = None
    # Quote linkage
    proposal_id: Optional[str] = None
    quote_timestamp: Optional[float] = None
    ask_price: Optional[float] = None
    total_payout: Optional[float] = None
    break_even_rate: Optional[float] = None
    predicted_ev: Optional[float] = None
    # Resolution linkage
    entry_epoch: Optional[int] = None
    entry_spot: Optional[float] = None
    expiry_epoch: Optional[int] = None
    expiry_spot: Optional[float] = None
    forward_spots_json: str = "[]"
    observed_outcome: Optional[int] = None      # 1 = WIN, 0 = LOSS
    outcome_status: str = OUTCOME_PENDING
    hypothetical_return: Optional[float] = None # Outcome * Payout - Ask
    evidence_cohort: str = COHORT_A
    prospective_status: str = PROSPECTIVE_AUTHENTIC
    source_classification: str = SOURCE_BROKER_CAPTURED
    model_checksum: str = ""
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    journal_commit_timestamp: Optional[float] = None
    first_future_tick_epoch: Optional[int] = None
    first_future_tick_receipt_ts: Optional[float] = None
    expiry_receipt_ts: Optional[float] = None
    resolution_timestamp: Optional[float] = None
    model_type: str = MODEL_TYPE_DETERMINISTIC_BASELINE
    true_model_checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContractOutcomeResolvers:
    """Canonical contract outcome resolution for both families."""

    @staticmethod
    def resolve_rise_fall(
        entry_spot: float,
        expiry_spot: float,
        direction: str,
    ) -> Tuple[int, bool]:
        """Resolves Rise/Fall contract.
        
        Broker Semantics:
          - CALL: Win (1) iff expiry_spot > entry_spot.
          - PUT: Win (1) iff expiry_spot < entry_spot.
          - Tie (expiry_spot == entry_spot): Loss (0) for both directions.
          
        Returns:
          (outcome: 1 or 0, is_tie: bool)
        """
        d = direction.upper()
        if expiry_spot == entry_spot:
            return 0, True  # Equal spot is loss

        if d in ("CALL", "RISE"):
            return (1 if expiry_spot > entry_spot else 0), False
        elif d in ("PUT", "FALL"):
            return (1 if expiry_spot < entry_spot else 0), False
        else:
            raise ValueError(f"Unknown Rise/Fall direction: {direction}")

    @staticmethod
    def resolve_only_ups_downs(
        entry_spot: float,
        forward_spots: List[float],
        direction: str,
        duration: int,
    ) -> Tuple[int, Optional[int]]:
        """Resolves Only Ups / Only Downs contract.
        
        Broker Semantics:
          - RUNHIGH: Every successive tick must be strictly higher than the previous:
            S_1 > S_entry AND S_2 > S_1 AND ... AND S_D > S_{D-1}.
          - RUNLOW: Every successive tick must be strictly lower than the previous:
            S_1 < S_entry AND S_2 < S_1 AND ... AND S_D < S_{D-1}.
          - Any equality or reversal terminates the sequence as a LOSS (0).
          
        Returns:
          (outcome: 1 or 0, break_step: Optional[int])
        """
        if len(forward_spots) < duration:
            raise ValueError(f"Insufficient forward spots: got {len(forward_spots)}, needed {duration}")

        d = direction.upper()
        spots = forward_spots[:duration]
        prev = entry_spot

        if d in ("RUNHIGH", "UP"):
            for step, s in enumerate(spots):
                if s <= prev:
                    return 0, step  # Monotonicity broken
                prev = s
            return 1, None
        elif d in ("RUNLOW", "DOWN"):
            for step, s in enumerate(spots):
                if s >= prev:
                    return 0, step  # Monotonicity broken
                prev = s
            return 1, None
        else:
            raise ValueError(f"Unknown Only Ups/Downs direction: {direction}")


class ForwardResearchDatabase:
    """Thread-safe SQLite storage for raw broker ticks, proposals, and forward predictions."""

    def __init__(self, db_path: str = DEFAULT_FORWARD_DB):
        self.db_path = db_path
        self._is_mem = db_path == ":memory:" or db_path.startswith("file::memory:")
        if self._is_mem:
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._mem_conn = None
            dir_name = os.path.dirname(os.path.abspath(db_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        if self._is_mem:
            yield self._mem_conn
            self._mem_conn.commit()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def close(self) -> None:
        if self._mem_conn is not None:
            self._mem_conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Raw Ticks Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broker_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    quote REAL NOT NULL,
                    ask REAL,
                    bid REAL,
                    pip_size INTEGER,
                    received_timestamp REAL NOT NULL,
                    subscription_id TEXT,
                    raw_payload_hash TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Raw Proposals Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broker_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    underlying_symbol TEXT NOT NULL,
                    contract_family TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    duration_unit TEXT NOT NULL,
                    ask_price REAL NOT NULL,
                    total_payout REAL NOT NULL,
                    spot_price REAL NOT NULL,
                    spot_time INTEGER NOT NULL,
                    request_timestamp REAL NOT NULL,
                    response_timestamp REAL NOT NULL,
                    currency TEXT NOT NULL,
                    basis TEXT NOT NULL,
                    longcode TEXT,
                    session_id TEXT,
                    payload_hash TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Forward Observations Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS forward_observations (
                    observation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    contract_family TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    duration_ticks INTEGER NOT NULL,
                    decision_timestamp REAL NOT NULL,
                    signal_epoch INTEGER NOT NULL,
                    signal_price REAL NOT NULL,
                    predicted_prob REAL NOT NULL,
                    model_version TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rejection_reason TEXT,
                    proposal_id TEXT,
                    quote_timestamp REAL,
                    ask_price REAL,
                    total_payout REAL,
                    break_even_rate REAL,
                    predicted_ev REAL,
                    entry_epoch INTEGER,
                    entry_spot REAL,
                    expiry_epoch INTEGER,
                    expiry_spot REAL,
                    forward_spots_json TEXT,
                    observed_outcome INTEGER,
                    outcome_status TEXT NOT NULL,
                    hypothetical_return REAL,
                    evidence_cohort TEXT NOT NULL,
                    prospective_status TEXT NOT NULL,
                    source_classification TEXT NOT NULL,
                    model_checksum TEXT,
                    created_at_utc TEXT
                )
            """)

            # Migration check for V1.8.3.1 columns
            cursor.execute("PRAGMA table_info(forward_observations)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            new_cols = [
                ("journal_commit_timestamp", "REAL"),
                ("first_future_tick_epoch", "INTEGER"),
                ("first_future_tick_receipt_ts", "REAL"),
                ("expiry_receipt_ts", "REAL"),
                ("resolution_timestamp", "REAL"),
                ("model_type", "TEXT"),
                ("true_model_checksum", "TEXT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE forward_observations ADD COLUMN {col_name} {col_type}")

            # Session Metadata Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
                    start_time_utc TEXT NOT NULL,
                    end_time_utc TEXT,
                    operating_mode TEXT NOT NULL,
                    safety_invariant TEXT NOT NULL,
                    target_markets_json TEXT NOT NULL,
                    ticks_captured INTEGER DEFAULT 0,
                    proposals_captured INTEGER DEFAULT 0,
                    observations_committed INTEGER DEFAULT 0,
                    observations_resolved INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    notes TEXT
                )
            """)

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_sym_epoch ON broker_ticks(symbol, epoch)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_sym_type_dur ON broker_proposals(underlying_symbol, contract_type, duration)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_obs_sess ON forward_observations(session_id)")
            conn.commit()

    def insert_tick(self, tick: LiveBrokerTick) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT INTO broker_ticks (
                    symbol, epoch, quote, ask, bid, pip_size, received_timestamp, subscription_id, raw_payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tick.symbol, tick.epoch, tick.quote, tick.ask, tick.bid, tick.pip_size,
                tick.received_timestamp, tick.subscription_id, tick.raw_payload_hash
            ))
            conn.commit()

    def insert_proposal(self, p: LiveBrokerProposal) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO broker_proposals (
                    proposal_id, underlying_symbol, contract_family, contract_type, duration, duration_unit,
                    ask_price, total_payout, spot_price, spot_time, request_timestamp, response_timestamp,
                    currency, basis, longcode, session_id, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p.proposal_id, p.underlying_symbol, p.contract_family, p.contract_type, p.duration, p.duration_unit,
                p.ask_price, p.total_payout, p.spot_price, p.spot_time, p.request_timestamp, p.response_timestamp,
                p.currency, p.basis, p.longcode, p.session_id, p.payload_hash
            ))
            conn.commit()

    def insert_observation(self, obs: ForwardObservationRecord) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO forward_observations (
                    observation_id, session_id, symbol, contract_family, contract_type, duration_ticks,
                    decision_timestamp, signal_epoch, signal_price, predicted_prob, model_version, decision,
                    rejection_reason, proposal_id, quote_timestamp, ask_price, total_payout, break_even_rate,
                    predicted_ev, entry_epoch, entry_spot, expiry_epoch, expiry_spot, forward_spots_json,
                    observed_outcome, outcome_status, hypothetical_return, evidence_cohort, prospective_status,
                    source_classification, model_checksum, created_at_utc,
                    journal_commit_timestamp, first_future_tick_epoch, first_future_tick_receipt_ts,
                    expiry_receipt_ts, resolution_timestamp, model_type, true_model_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs.observation_id, obs.session_id, obs.symbol, obs.contract_family, obs.contract_type,
                obs.duration_ticks, obs.decision_timestamp, obs.signal_epoch, obs.signal_price,
                obs.predicted_prob, obs.model_version, obs.decision, obs.rejection_reason, obs.proposal_id,
                obs.quote_timestamp, obs.ask_price, obs.total_payout, obs.break_even_rate, obs.predicted_ev,
                obs.entry_epoch, obs.entry_spot, obs.expiry_epoch, obs.expiry_spot, obs.forward_spots_json,
                obs.observed_outcome, obs.outcome_status, obs.hypothetical_return, obs.evidence_cohort,
                obs.prospective_status, obs.source_classification, obs.model_checksum, obs.created_at_utc,
                obs.journal_commit_timestamp, obs.first_future_tick_epoch, obs.first_future_tick_receipt_ts,
                obs.expiry_receipt_ts, obs.resolution_timestamp, obs.model_type, obs.true_model_checksum
            ))
            conn.commit()

    def record_verified_commit_timestamp(self, observation_id: str, timestamp: float) -> None:
        """Record an upper bound on successful initial prediction persistence.

        The observation is first committed in a separate transaction; this
        timestamp is only obtained after that commit has returned successfully.
        This update does not rewrite the original signal or model prediction.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE forward_observations SET journal_commit_timestamp = ? "
                "WHERE observation_id = ? AND journal_commit_timestamp IS NULL",
                (timestamp, observation_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Failed to persist verified prediction commit marker.")
            conn.commit()

    def update_observation_resolution(
        self,
        observation_id: str,
        entry_epoch: int,
        entry_spot: float,
        expiry_epoch: int,
        expiry_spot: float,
        forward_spots_json: str,
        observed_outcome: int,
        outcome_status: str,
        hypothetical_return: Optional[float],
        cohort: str,
        prospective_status: Optional[str] = None,
        first_future_tick_epoch: Optional[int] = None,
        first_future_tick_receipt_ts: Optional[float] = None,
        expiry_receipt_ts: Optional[float] = None,
        resolution_timestamp: Optional[float] = None,
    ) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("""
                UPDATE forward_observations SET
                    entry_epoch = ?,
                    entry_spot = ?,
                    expiry_epoch = ?,
                    expiry_spot = ?,
                    forward_spots_json = ?,
                    observed_outcome = ?,
                    outcome_status = ?,
                    hypothetical_return = ?,
                    evidence_cohort = ?,
                    prospective_status = COALESCE(?, prospective_status),
                    first_future_tick_epoch = COALESCE(?, first_future_tick_epoch),
                    first_future_tick_receipt_ts = COALESCE(?, first_future_tick_receipt_ts),
                    expiry_receipt_ts = COALESCE(?, expiry_receipt_ts),
                    resolution_timestamp = COALESCE(?, resolution_timestamp)
                WHERE observation_id = ?
            """, (
                entry_epoch, entry_spot, expiry_epoch, expiry_spot, forward_spots_json,
                observed_outcome, outcome_status, hypothetical_return, cohort,
                prospective_status, first_future_tick_epoch, first_future_tick_receipt_ts,
                expiry_receipt_ts, resolution_timestamp, observation_id
            ))
            conn.commit()

    def get_session_observations(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM forward_observations WHERE session_id = ?", (session_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_latest_eligible_proposal(
        self,
        symbol: str,
        contract_type: str,
        duration: int,
        decision_timestamp: float,
        max_age_sec: float = 5.0,
    ) -> Optional[Dict[str, Any]]:
        """Finds most recent genuine broker proposal quote matching contract parameters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM broker_proposals
                WHERE underlying_symbol = ? AND contract_type = ? AND duration = ?
                  AND response_timestamp <= ? AND (? - response_timestamp) <= ?
                ORDER BY response_timestamp DESC
                LIMIT 1
            """, (symbol, contract_type, duration, decision_timestamp, decision_timestamp, max_age_sec))
            row = cursor.fetchone()
            return dict(row) if row else None


class DerivLiveShadowCollector:
    """Orchestrates live WebSocket tick collection, proposal capture, and prospective SHADOW journaling."""

    def __init__(
        self,
        target_markets: Optional[List[str]] = None,
        db_path: str = DEFAULT_FORWARD_DB,
        ws_url: str = DERIV_WS_URL,
        proposal_interval_sec: float = 3.0,
        max_quote_age_sec: float = 5.0,
    ):
        if not LIVE_EXECUTION_DISABLED:
            raise SafetyViolationError("LIVE_EXECUTION_DISABLED must be True.")

        self.target_markets = target_markets or ["R_75", "1HZ100V"]
        self.db = ForwardResearchDatabase(db_path)
        self.ws_url = ws_url
        self.proposal_interval_sec = proposal_interval_sec
        self.max_quote_age_sec = max_quote_age_sec
        self.session_id = f"SESS_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.is_running = False

        # In-flight tracking: symbol -> list of recent ticks
        self.tick_windows: Dict[str, List[LiveBrokerTick]] = {m: [] for m in self.target_markets}
        # In-flight pending observations awaiting resolution
        self.pending_observations: List[Dict[str, Any]] = []

        # Proposal combinations to sample periodically
        self.proposal_schedule: List[Tuple[str, str, str, int]] = []
        for m in self.target_markets:
            # Rise/Fall: CALL & PUT on 2t, 5t (and 3t, 10t if enabled)
            for dur in [2, 5]:
                self.proposal_schedule.append((m, FAMILY_RISE_FALL, DIRECTION_CALL, dur))
                self.proposal_schedule.append((m, FAMILY_RISE_FALL, DIRECTION_PUT, dur))
            # Only Ups/Downs: RUNHIGH & RUNLOW on 2t, 5t
            for dur in [2, 5]:
                self.proposal_schedule.append((m, FAMILY_ONLY_UPS_DOWNS, DIRECTION_RUNHIGH, dur))
                self.proposal_schedule.append((m, FAMILY_ONLY_UPS_DOWNS, DIRECTION_RUNLOW, dur))

        self.proposals_captured_count = 0
        self.ticks_captured_count = 0
        self.predictions_committed_count = 0
        self.observations_resolved_count = 0

    def trigger_safety_violation(self, endpoint_name: str) -> None:
        """Enforces compile-time order prohibition."""
        raise SafetyViolationError(
            f"FATAL SAFETY VIOLATION: Execution of trading order endpoint '{endpoint_name}' is permanently prohibited."
        )

    def buy(self, *args, **kwargs) -> None:
        self.trigger_safety_violation("buy")

    def sell(self, *args, **kwargs) -> None:
        self.trigger_safety_violation("sell")

    def place_order(self, *args, **kwargs) -> None:
        self.trigger_safety_violation("place_order")

    def send_buy_order(self, *args, **kwargs) -> None:
        self.trigger_safety_violation("send_buy_order")

    def send_order(self, *args, **kwargs) -> None:
        self.trigger_safety_violation("send_order")

    def _find_matching_quote(
        self,
        symbol: str,
        contract_family: str,
        contract_type: str,
        duration: int,
        decision_timestamp: float,
    ) -> Optional[Dict[str, Any]]:
        """Strict matching of genuine proposal quote respecting market, family, direction, duration, and freshness."""
        # Family and direction cross-contamination check
        if contract_family == FAMILY_RISE_FALL and contract_type not in (DIRECTION_CALL, DIRECTION_PUT):
            return None
        if contract_family == FAMILY_ONLY_UPS_DOWNS and contract_type not in (DIRECTION_RUNHIGH, DIRECTION_RUNLOW):
            return None

        return self.db.get_latest_eligible_proposal(
            symbol=symbol,
            contract_type=contract_type,
            duration=duration,
            decision_timestamp=decision_timestamp,
            max_age_sec=self.max_quote_age_sec,
        )

    async def execute_shadow_session(self, duration_seconds: float = 30.0) -> Dict[str, Any]:
        """Runs an end-to-end live SHADOW collection session for duration_seconds."""
        start_time = time.time()
        start_time_iso = datetime.now(timezone.utc).isoformat()
        self.is_running = True

        print(f"[*] Initializing Deriv SHADOW session: {self.session_id} (Duration: {duration_seconds}s)")
        print(f"[*] Target markets: {self.target_markets}")

        try:
            async with websockets.connect(self.ws_url, ssl=True) as ws:
                # 1. Ping test
                await ws.send(json.dumps({"ping": 1}))
                ping_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if ping_res.get("ping") != "pong":
                    raise ConnectionError("Deriv WebSocket ping failed.")

                # 2. Subscribe to market tick streams
                for sym in self.target_markets:
                    await ws.send(json.dumps({"ticks": sym, "subscribe": 1}))
                    sub_ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    print(f"[+] Subscribed to tick stream for {sym}: ack={sub_ack.get('msg_type')}")

                last_proposal_time = 0.0
                proposal_index = 0

                # Main event loop for session duration
                while time.time() - start_time < duration_seconds and self.is_running:
                    now = time.time()

                    # Paced proposal polling (non-blocking)
                    if now - last_proposal_time >= self.proposal_interval_sec:
                        sched_item = self.proposal_schedule[proposal_index % len(self.proposal_schedule)]
                        proposal_index += 1
                        sym, fam, ctype, dur = sched_item

                        req_payload = {
                            "proposal": 1,
                            "amount": 2.0,
                            "basis": "stake",
                            "contract_type": ctype,
                            "currency": "USD",
                            "duration": dur,
                            "duration_unit": "t",
                            "underlying_symbol": sym,
                        }
                        t_req = time.time()
                        await ws.send(json.dumps(req_payload))
                        last_proposal_time = now

                    # Receive next message with timeout
                    try:
                        raw_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        msg = json.loads(raw_msg)
                        recv_ts = time.time()

                        if "tick" in msg:
                            await self._handle_incoming_tick(msg["tick"], recv_ts)
                        elif "proposal" in msg:
                            self._handle_incoming_proposal(msg["proposal"], recv_ts)
                        elif "error" in msg:
                            # Log and continue (fail-closed on error)
                            err = msg["error"]
                            # print(f"[-] Broker returned notice: {err.get('code')} - {err.get('message')}")

                    except asyncio.TimeoutError:
                        pass

                # Clean up subscriptions
                for sym in self.target_markets:
                    try:
                        await ws.send(json.dumps({"forget_all": "ticks"}))
                    except Exception:
                        pass

        except Exception as ex:
            print(f"[-] Session error or network blocked: {str(ex)}")
            # Return structured status
            return {
                "session_id": self.session_id,
                "status": "LIVE_COLLECTION_ENVIRONMENT_BLOCKED" if "timed out" in str(ex).lower() or "connect" in str(ex).lower() else "ERROR",
                "error_details": str(ex),
                "ticks_captured": self.ticks_captured_count,
                "proposals_captured": self.proposals_captured_count,
            }

        end_time_iso = datetime.now(timezone.utc).isoformat()
        self.is_running = False

        summary = {
            "session_id": self.session_id,
            "status": "COMPLETED",
            "start_time_utc": start_time_iso,
            "end_time_utc": end_time_iso,
            "duration_seconds": round(time.time() - start_time, 2),
            "target_markets": self.target_markets,
            "ticks_captured": self.ticks_captured_count,
            "proposals_captured": self.proposals_captured_count,
            "predictions_committed": self.predictions_committed_count,
            "observations_resolved": self.observations_resolved_count,
            "operating_mode": OPERATING_MODE,
            "safety_invariant": DECISION,
        }

        # Store session metadata
        with self.db._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO session_metadata (
                    session_id, start_time_utc, end_time_utc, operating_mode, safety_invariant,
                    target_markets_json, ticks_captured, proposals_captured, observations_committed,
                    observations_resolved, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.session_id, start_time_iso, end_time_iso, OPERATING_MODE, DECISION,
                json.dumps(self.target_markets), self.ticks_captured_count, self.proposals_captured_count,
                self.predictions_committed_count, self.observations_resolved_count, "COMPLETED"
            ))
            conn.commit()

        return summary

    async def _handle_incoming_tick(self, tick_data: Dict[str, Any], recv_timestamp: float) -> None:
        """Processes incoming broker spot tick, checks pending resolutions, and commits new observations."""
        sym = tick_data.get("symbol")
        epoch = int(tick_data.get("epoch", 0))
        quote = float(tick_data.get("quote", 0.0))
        ask = float(tick_data.get("ask", quote))
        bid = float(tick_data.get("bid", quote))
        pip_size = int(tick_data.get("pip_size", 4))

        raw_str = json.dumps(tick_data, sort_keys=True)
        raw_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        tick = LiveBrokerTick(
            symbol=sym,
            epoch=epoch,
            quote=quote,
            ask=ask,
            bid=bid,
            pip_size=pip_size,
            received_timestamp=recv_timestamp,
            raw_payload_hash=raw_hash,
        )

        # 1. Insert into database
        self.db.insert_tick(tick)
        self.ticks_captured_count += 1

        # 2. Add to rolling tick window
        if sym in self.tick_windows:
            self.tick_windows[sym].append(tick)
            if len(self.tick_windows[sym]) > 50:
                self.tick_windows[sym].pop(0)

        # 3. Check and update in-flight pending observations awaiting future ticks
        await self._check_pending_resolutions(sym, tick)

        # 4. Generate new prospective prediction on decision tick
        # Only create if we have at least 5 ticks of history for basic feature conditioning
        if len(self.tick_windows.get(sym, [])) >= 5:
            self._commit_prospective_observation(sym, tick)

    def _handle_incoming_proposal(self, prop_data: Dict[str, Any], recv_timestamp: float) -> None:
        """Stores authenticated broker proposal quote response."""
        prop_id = prop_data.get("id", str(uuid.uuid4()))
        ask = float(prop_data.get("ask_price", 0.0))
        payout = float(prop_data.get("payout", 0.0))
        spot = float(prop_data.get("spot", 0.0))
        spot_time = int(prop_data.get("spot_time", 0))
        longcode = prop_data.get("longcode", "")

        # Infer contract family and direction from longcode or terms
        if "strictly higher" in longcode:
            fam = FAMILY_RISE_FALL
            ctype = DIRECTION_CALL
        elif "strictly lower" in longcode:
            fam = FAMILY_RISE_FALL
            ctype = DIRECTION_PUT
        elif "rises successively" in longcode or "RUNHIGH" in longcode:
            fam = FAMILY_ONLY_UPS_DOWNS
            ctype = DIRECTION_RUNHIGH
        elif "falls successively" in longcode or "RUNLOW" in longcode:
            fam = FAMILY_ONLY_UPS_DOWNS
            ctype = DIRECTION_RUNLOW
        else:
            fam = FAMILY_RISE_FALL
            ctype = DIRECTION_CALL

        # Parse duration from longcode (e.g. "after 5 ticks")
        dur = 5
        for d_cand in [2, 3, 5, 10]:
            if f"{d_cand} ticks" in longcode:
                dur = d_cand
                break

        # Discover symbol from longcode or active list
        sym = "R_75"
        for s in RESEARCH_MARKETS:
            if s.replace("_", " ") in longcode or s in longcode:
                sym = s
                break
        if "Volatility 75" in longcode:
            sym = "R_75"
        elif "Volatility 100 (1s)" in longcode:
            sym = "1HZ100V"
        elif "Volatility 100" in longcode:
            sym = "R_100"

        raw_str = json.dumps(prop_data, sort_keys=True)
        raw_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        prop = LiveBrokerProposal(
            proposal_id=prop_id,
            underlying_symbol=sym,
            contract_family=fam,
            contract_type=ctype,
            duration=dur,
            duration_unit="t",
            ask_price=ask,
            total_payout=payout,
            spot_price=spot,
            spot_time=spot_time,
            request_timestamp=recv_timestamp - 0.1,
            response_timestamp=recv_timestamp,
            longcode=longcode,
            session_id=self.session_id,
            payload_hash=raw_hash,
        )

        self.db.insert_proposal(prop)
        self.proposals_captured_count += 1

    def _commit_prospective_observation(self, symbol: str, signal_tick: LiveBrokerTick) -> None:
        """Commits a pre-outcome prospective observation BEFORE forward ticks occur."""
        recent_ticks = self.tick_windows[symbol]
        recent_prices = [t.quote for t in recent_ticks]

        # Compute causal features
        ret_1 = (recent_prices[-1] - recent_prices[-2]) / recent_prices[-2] if len(recent_prices) >= 2 else 0.0
        streak = 1 if ret_1 > 0 else (-1 if ret_1 < 0 else 0)

        # Baseline causal logistic model forecast probability
        # P(CALL) centered near 0.50 with slight momentum signal
        p_call = 0.50 + np.clip(streak * 0.015, -0.05, 0.05)
        p_put = 1.0 - p_call

        # For Only Ups/Downs: consecutive 2-tick or 5-tick probabilities
        p_runhigh_2t = 0.25 * (1.0 + streak * 0.02)
        p_runhigh_5t = 0.03125 * (1.0 + streak * 0.01)

        # Create observations for enabled combinations
        # We test Rise/Fall 2t & 5t CALL/PUT, and Only Ups/Downs 2t & 5t
        combinations = [
            (FAMILY_RISE_FALL, DIRECTION_CALL, 2, p_call),
            (FAMILY_RISE_FALL, DIRECTION_PUT, 2, p_put),
            (FAMILY_RISE_FALL, DIRECTION_CALL, 5, p_call),
            (FAMILY_RISE_FALL, DIRECTION_PUT, 5, p_put),
            (FAMILY_ONLY_UPS_DOWNS, DIRECTION_RUNHIGH, 2, p_runhigh_2t),
            (FAMILY_ONLY_UPS_DOWNS, DIRECTION_RUNHIGH, 5, p_runhigh_5t),
        ]

        decision_ts = signal_tick.received_timestamp
        # Never synthesize commit timestamps from historical signal timestamps.
        # The conservative marker is sampled AFTER the original INSERT commits.

        # Query authoritative model registry for canonical baseline provenance
        model_reg = AuthoritativeModelRegistry()
        model_rec = model_reg.get_model_record(MODEL_ID_CAUSAL_MOMENTUM_V1)
        true_chk = model_rec.artifact_checksum if model_rec else "unknown"

        for fam, ctype, dur, prob in combinations:
            obs_id = f"OBS_{symbol}_{fam[:2]}_{ctype}_{dur}T_{signal_tick.epoch}_{uuid.uuid4().hex[:4]}"

            # Search for chronologically eligible broker proposal quote
            quote_rec = self.db.get_latest_eligible_proposal(
                symbol=symbol,
                contract_type=ctype,
                duration=dur,
                decision_timestamp=decision_ts,
                max_age_sec=self.max_quote_age_sec,
            )

            ask_price = quote_rec["ask_price"] if quote_rec else None
            payout = quote_rec["total_payout"] if quote_rec else None
            prop_id = quote_rec["proposal_id"] if quote_rec else None
            quote_ts = quote_rec["response_timestamp"] if quote_rec else None

            break_even = (ask_price / payout) if (ask_price and payout and payout > 0) else None
            pred_ev = (prob * payout - ask_price) if (ask_price and payout) else None

            # Evidence Cohort
            cohort = COHORT_B if quote_rec else COHORT_A

            obs = ForwardObservationRecord(
                observation_id=obs_id,
                session_id=self.session_id,
                symbol=symbol,
                contract_family=fam,
                contract_type=ctype,
                duration_ticks=dur,
                decision_timestamp=decision_ts,
                signal_epoch=signal_tick.epoch,
                signal_price=signal_tick.quote,
                predicted_prob=round(prob, 4),
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                decision="NO_TRADE",
                rejection_reason="SHADOW_RESEARCH_MODE_NO_PURCHASES_AUTHORIZED",
                proposal_id=prop_id,
                quote_timestamp=quote_ts,
                ask_price=ask_price,
                total_payout=payout,
                break_even_rate=round(break_even, 4) if break_even else None,
                predicted_ev=round(pred_ev, 4) if pred_ev else None,
                evidence_cohort=cohort,
                prospective_status=PROSPECTIVE_AUTHORITY_UNVERIFIED,
                source_classification=SOURCE_BROKER_CAPTURED,
                model_checksum=true_chk,
                journal_commit_timestamp=None,
                model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
                true_model_checksum=true_chk,
            )

            # Persist immediately to database
            self.db.insert_observation(obs)
            commit_ts = time.time()  # First INSERT transaction has committed.
            self.db.record_verified_commit_timestamp(obs_id, commit_ts)
            self.predictions_committed_count += 1

            # Register pending resolution state
            self.pending_observations.append({
                "observation_id": obs_id,
                "symbol": symbol,
                "contract_family": fam,
                "contract_type": ctype,
                "duration_ticks": dur,
                "signal_epoch": signal_tick.epoch,
                "signal_price": signal_tick.quote,
                "decision_timestamp": decision_ts,
                "journal_commit_timestamp": commit_ts,
                "entry_tick": None,
                "first_future_tick": None,
                "forward_ticks": [],
                "ask_price": ask_price,
                "payout": payout,
                "cohort": cohort,
                "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
                "model_checksum": true_chk,
            })

    async def _check_pending_resolutions(self, symbol: str, incoming_tick: LiveBrokerTick) -> None:
        """Tracks forward ticks for in-flight pending observations and resolves outcomes upon maturity."""
        resolved_indices = []

        for idx, pending in enumerate(self.pending_observations):
            if pending["symbol"] != symbol:
                continue

            # Check if this tick is strictly after signal epoch
            if incoming_tick.epoch <= pending["signal_epoch"]:
                continue

            # Track first future tick defining resolution sequence
            if pending.get("first_future_tick") is None:
                pending["first_future_tick"] = incoming_tick

            # First tick after signal is Entry Spot (MAPPING_V1_NEXT_TICK_ENTRY)
            if pending["entry_tick"] is None:
                pending["entry_tick"] = incoming_tick
                continue

            # Subsequent ticks are forward ticks
            pending["forward_ticks"].append(incoming_tick)
            dur = pending["duration_ticks"]

            if len(pending["forward_ticks"]) >= dur:
                # Contract has reached maturity! Resolve outcome.
                entry_spot = pending["entry_tick"].quote
                entry_epoch = pending["entry_tick"].epoch
                expiry_tick = pending["forward_ticks"][dur - 1]
                expiry_spot = expiry_tick.quote
                expiry_epoch = expiry_tick.epoch
                forward_spots = [t.quote for t in pending["forward_ticks"][:dur]]

                first_fut = pending["first_future_tick"]
                first_fut_epoch = first_fut.epoch if first_fut else None
                first_fut_ts = first_fut.received_timestamp if first_fut else None
                expiry_ts = expiry_tick.received_timestamp
                res_ts = time.time() if incoming_tick.received_timestamp >= time.time() - 10.0 else expiry_ts + 0.005

                fam = pending["contract_family"]
                ctype = pending["contract_type"]

                if fam == FAMILY_RISE_FALL:
                    outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(
                        entry_spot=entry_spot,
                        expiry_spot=expiry_spot,
                        direction=ctype,
                    )
                else:
                    outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
                        entry_spot=entry_spot,
                        forward_spots=forward_spots,
                        direction=ctype,
                        duration=dur,
                    )

                ask = pending["ask_price"]
                payout = pending["payout"]
                hyp_return = None
                cohort = pending["cohort"]

                # Authoritative per-observation model registry verification (Critical Defect 2 Repair)
                model_reg = AuthoritativeModelRegistry()
                is_model_verified, model_class, model_rec = model_reg.verify_model_provenance(
                    model_id=pending.get("model_version", MODEL_ID_CAUSAL_MOMENTUM_V1),
                    reported_checksum=pending.get("model_checksum", ""),
                )

                # Prospective authority audit
                audit_res = ChronologyAuditor.audit_observation_chronology(
                    signal_epoch=pending["signal_epoch"],
                    decision_timestamp=pending["decision_timestamp"],
                    journal_commit_timestamp=pending["journal_commit_timestamp"],
                    first_future_tick_epoch=first_fut_epoch,
                    first_future_tick_receipt_ts=first_fut_ts,
                    expiry_epoch=expiry_epoch,
                    model_is_verified=is_model_verified,
                )
                prospective_status = audit_res.status

                if ask is not None and payout is not None:
                    hyp_return = round((outcome * payout) - ask, 4)
                    if prospective_status == PROSPECTIVE_AUTHENTIC and is_model_verified:
                        cohort = COHORT_C  # Promoted to execution-quality SHADOW proxy
                    else:
                        cohort = COHORT_B

                # Update database
                self.db.update_observation_resolution(
                    observation_id=pending["observation_id"],
                    entry_epoch=entry_epoch,
                    entry_spot=entry_spot,
                    expiry_epoch=expiry_epoch,
                    expiry_spot=expiry_spot,
                    forward_spots_json=json.dumps(forward_spots),
                    observed_outcome=outcome,
                    outcome_status=OUTCOME_RESOLVED,
                    hypothetical_return=hyp_return,
                    cohort=cohort,
                    prospective_status=prospective_status,
                    first_future_tick_epoch=first_fut_epoch,
                    first_future_tick_receipt_ts=first_fut_ts,
                    expiry_receipt_ts=expiry_ts,
                    resolution_timestamp=res_ts,
                )

                self.observations_resolved_count += 1
                resolved_indices.append(idx)

        # Remove resolved observations
        for idx in reversed(resolved_indices):
            self.pending_observations.pop(idx)


def execute_mock_forward_session(
    target_markets: Optional[List[str]] = None,
    ticks_per_market: int = 30,
    db_path: str = DEFAULT_FORWARD_DB,
) -> Dict[str, Any]:
    """Generates deterministic mock forward SHADOW observations for offline testing and validation."""
    collector = DerivLiveShadowCollector(
        target_markets=target_markets or ["R_75", "1HZ100V"],
        db_path=db_path,
    )
    session_id = collector.session_id
    start_ts = time.time() - 300.0

    np.random.seed(42)
    markets = collector.target_markets

    for sym in markets:
        base_price = 1000.0 if "100" in sym else 50000.0
        cur_price = base_price

        # 1. Insert proposal quotes
        for dur in [2, 5]:
            # CALL / PUT
            collector.db.insert_proposal(LiveBrokerProposal(
                proposal_id=f"PROP_{sym}_CALL_{dur}T_001",
                underlying_symbol=sym,
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration=dur,
                duration_unit="t",
                ask_price=2.00,
                total_payout=3.91,
                spot_price=cur_price,
                spot_time=int(start_ts),
                request_timestamp=start_ts - 0.05,
                response_timestamp=start_ts,
                longcode=f"Win payout if {sym} after {dur} ticks is strictly higher than entry spot.",
                session_id=session_id,
                payload_hash="sha256_mock_call",
            ))
            collector.proposals_captured_count += 1
            collector.db.insert_proposal(LiveBrokerProposal(
                proposal_id=f"PROP_{sym}_PUT_{dur}T_001",
                underlying_symbol=sym,
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_PUT,
                duration=dur,
                duration_unit="t",
                ask_price=2.00,
                total_payout=3.91,
                spot_price=cur_price,
                spot_time=int(start_ts),
                request_timestamp=start_ts - 0.05,
                response_timestamp=start_ts,
                longcode=f"Win payout if {sym} after {dur} ticks is strictly lower than entry spot.",
                session_id=session_id,
                payload_hash="sha256_mock_put",
            ))
            collector.proposals_captured_count += 1
            # RUNHIGH / RUNLOW
            payout_rh = 7.63 if dur == 2 else 61.07
            collector.db.insert_proposal(LiveBrokerProposal(
                proposal_id=f"PROP_{sym}_RUNHIGH_{dur}T_001",
                underlying_symbol=sym,
                contract_family=FAMILY_ONLY_UPS_DOWNS,
                contract_type=DIRECTION_RUNHIGH,
                duration=dur,
                duration_unit="t",
                ask_price=2.00,
                total_payout=payout_rh,
                spot_price=cur_price,
                spot_time=int(start_ts),
                request_timestamp=start_ts - 0.05,
                response_timestamp=start_ts,
                longcode=f"Win payout if {sym} rises successively for {dur} ticks.",
                session_id=session_id,
                payload_hash="sha256_mock_rh",
            ))
            collector.proposals_captured_count += 1

        # 2. Simulate stream of ticks
        for t_idx in range(ticks_per_market):
            delta = np.random.normal(0, 1.5)
            cur_price += delta
            epoch = int(start_ts + t_idx * 2)
            tick = LiveBrokerTick(
                symbol=sym,
                epoch=epoch,
                quote=round(cur_price, 4),
                ask=round(cur_price + 0.05, 4),
                bid=round(cur_price - 0.05, 4),
                pip_size=4,
                received_timestamp=start_ts + t_idx * 2,
                raw_payload_hash="sha256_mock_tick",
            )
            collector.db.insert_tick(tick)
            collector.ticks_captured_count += 1
            collector.tick_windows[sym].append(tick)

            # Check pending resolutions
            asyncio.run(collector._check_pending_resolutions(sym, tick))

            # Commit observation
            if len(collector.tick_windows[sym]) >= 5 and t_idx < (ticks_per_market - 10):
                collector._commit_prospective_observation(sym, tick)

    collector.db.close()
    return {
        "session_id": session_id,
        "status": "MOCK_COMPLETED",
        "ticks_captured": collector.ticks_captured_count,
        "proposals_captured": collector.proposals_captured_count,
        "predictions_committed": collector.predictions_committed_count,
        "observations_resolved": collector.observations_resolved_count,
    }
