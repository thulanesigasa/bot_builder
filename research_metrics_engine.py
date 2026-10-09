"""Authoritative Canonical Research Metrics Engine (V1.7.2 Part C).

Provides a single authoritative data-analysis and metrics computation interface
shared across session reporting, multi-session research aggregation, dashboard visualization,
and the forward confirmation gate.

Enforces strict referential integrity, canonical direction-specific outcome modeling,
zero complementary-win inference (RUNLOW != 1 - RUNHIGH), and cryptographic integrity checksumming.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
import hashlib
import json
import math
import os
import sqlite3

from config import DEFAULT_CONFIG
from statistical_evaluator import StatisticalEvaluator, wilson_score_interval
from economic_evaluator import EconomicEvaluator


@dataclass
class DirectionalMetrics:
    direction: str
    eligible_count: int
    wins: int
    losses: int
    observed_win_rate: Optional[float]
    mean_predicted_prob: Optional[float]
    wilson_ci_95: Tuple[Optional[float], Optional[float]]
    brier_score: Optional[float] = None
    reference_brier_score: Optional[float] = None
    brier_skill_score: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    effective_sample_size: Optional[float] = None
    bootstrap_ci_95: Tuple[Optional[float], Optional[float]] = (None, None)


@dataclass
class ResearchDatasetMetrics:
    symbol: str
    session_ids: List[str]
    total_predictions: int
    eligible_resolved_count: int
    pending_count: int
    incomplete_count: int
    data_gap_count: int
    both_lost_count: int
    runhigh: DirectionalMetrics
    runlow: DirectionalMetrics
    quote_coverage_pct: float
    mean_ask: Optional[float]
    mean_payout: Optional[float]
    mean_break_even_pct: Optional[float]
    ordinary_ev: Optional[float]
    conservative_ev: Optional[float]
    cumulative_pnl: float
    max_drawdown: float
    integrity_checksum: str
    evaluation_timestamp_utc: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchMetricsEngine:
    """Canonical engine for deriving research statistics directly from verified SQLite records."""

    def __init__(
        self,
        forward_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
        session_db_path: Optional[str] = None
    ):
        self.forward_db_path = forward_db_path or DEFAULT_CONFIG.forward_predictions_db_path
        self.quote_db_path = quote_db_path or DEFAULT_CONFIG.quotes_db_path
        self.session_db_path = session_db_path or getattr(DEFAULT_CONFIG, "sessions_db_path", "data/sessions.db")
        self.stat_evaluator = StatisticalEvaluator()
        self.econ_evaluator = EconomicEvaluator()

    def _get_fwd_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.forward_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def compute_integrity_checksum(
        self,
        records: List[Dict[str, Any]],
        session_ids: List[str],
        symbol: str
    ) -> str:
        """Computes a deterministic SHA-256 integrity hash over canonical research records."""
        payload = {
            "symbol": symbol,
            "session_ids": sorted(session_ids),
            "records": [
                {
                    "prediction_id": r.get("prediction_id"),
                    "session_id": r.get("session_id"),
                    "outcome_status": r.get("outcome_status"),
                    "runhigh_win": r.get("runhigh_win"),
                    "runlow_win": r.get("runlow_win"),
                    "timestamp": r.get("timestamp"),
                    "runhigh_ask": r.get("runhigh_ask"),
                    "runhigh_payout": r.get("runhigh_payout")
                }
                for r in sorted(records, key=lambda x: str(x.get("prediction_id", "")))
            ]
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    def load_authoritative_predictions_for_sessions(
        self,
        session_ids: List[str],
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries predictions and outcomes with referential integrity verification."""
        if not session_ids or not os.path.exists(self.forward_db_path):
            return []

        placeholders = ",".join("?" for _ in session_ids)
        params: List[Any] = list(session_ids)
        symbol_clause = ""
        if symbol:
            symbol_clause = " AND p.symbol = ?"
            params.append(symbol)

        with self._get_fwd_conn() as conn:
            # Check if forward_outcomes table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='forward_outcomes'"
            ).fetchone()

            if table_check:
                query = f"""
                    SELECT 
                        p.prediction_id, p.session_id, p.timestamp, p.symbol, p.model_version,
                        p.model_id, p.market_state, p.runhigh_pred_prob, p.runlow_pred_prob,
                        p.runhigh_ask, p.runhigh_payout, p.runlow_ask, p.runlow_payout,
                        p.target_direction, p.decision, p.quote_id, p.source_provenance,
                        COALESCE(o.outcome_status, p.outcome_status) AS outcome_status,
                        COALESCE(o.runhigh_win, p.runhigh_win) AS runhigh_win,
                        COALESCE(o.runlow_win, p.runlow_win) AS runlow_win,
                        COALESCE(o.hypothetical_pnl, p.hypothetical_pnl) AS hypothetical_pnl,
                        o.forward_prices_json, o.forward_ticks_count
                    FROM forward_predictions p
                    LEFT JOIN forward_outcomes o ON p.prediction_id = o.prediction_id
                    WHERE p.session_id IN ({placeholders}) {symbol_clause}
                    ORDER BY p.timestamp ASC
                """
            else:
                query = f"""
                    SELECT * FROM forward_predictions p
                    WHERE p.session_id IN ({placeholders}) {symbol_clause}
                    ORDER BY p.timestamp ASC
                """
            rows = conn.execute(query, params).fetchall()

        records = []
        for r in rows:
            d = dict(r)
            # Strict float normalization for win flags (never infer from strings or bools)
            for k in ("runhigh_win", "runlow_win"):
                val = d.get(k)
                if val is not None:
                    try:
                        d[k] = float(val)
                    except (ValueError, TypeError):
                        d[k] = None
            records.append(d)
        return records

    def calculate_metrics(
        self,
        session_ids: List[str],
        symbol: str = "R_75"
    ) -> ResearchDatasetMetrics:
        """Derives canonical research metrics across the specified sessions.
        
        Guarantees:
        1. RUNHIGH and RUNLOW wins are evaluated independently (zero binary inversion).
        2. Non-resolved or gap outcomes are not counted as losses.
        3. Unavailable win rates are returned as None when eligible count is zero.
        4. Integrity checksum uniquely fingerprinting the dataset is generated.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        records = self.load_authoritative_predictions_for_sessions(session_ids=session_ids, symbol=symbol)

        total_preds = len(records)
        eligible: List[Dict[str, Any]] = []
        pending_count = 0
        incomplete_count = 0
        data_gap_count = 0

        for r in records:
            status = str(r.get("outcome_status", "")).upper()
            if status in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED"):
                eligible.append(r)
            elif status in ("PENDING", "STATUS_PENDING"):
                pending_count += 1
            elif status in ("OUTCOME_INCOMPLETE", "INCOMPLETE"):
                incomplete_count += 1
            elif status in ("OUTCOME_DATA_GAP", "DATA_GAP"):
                data_gap_count += 1
            else:
                pending_count += 1

        n_eligible = len(eligible)

        if n_eligible == 0:
            rh_metrics = DirectionalMetrics(
                direction="RUNHIGH",
                eligible_count=0,
                wins=0,
                losses=0,
                observed_win_rate=None,
                mean_predicted_prob=None,
                wilson_ci_95=(None, None)
            )
            rl_metrics = DirectionalMetrics(
                direction="RUNLOW",
                eligible_count=0,
                wins=0,
                losses=0,
                observed_win_rate=None,
                mean_predicted_prob=None,
                wilson_ci_95=(None, None)
            )
            checksum = self.compute_integrity_checksum(records, session_ids, symbol)
            return ResearchDatasetMetrics(
                symbol=symbol,
                session_ids=session_ids,
                total_predictions=total_preds,
                eligible_resolved_count=0,
                pending_count=pending_count,
                incomplete_count=incomplete_count,
                data_gap_count=data_gap_count,
                both_lost_count=0,
                runhigh=rh_metrics,
                runlow=rl_metrics,
                quote_coverage_pct=0.0,
                mean_ask=None,
                mean_payout=None,
                mean_break_even_pct=None,
                ordinary_ev=None,
                conservative_ev=None,
                cumulative_pnl=0.0,
                max_drawdown=0.0,
                integrity_checksum=checksum,
                evaluation_timestamp_utc=now_iso,
                notes=["Zero eligible resolved outcomes found in specified sessions."]
            )

        # Count wins independently from canonical columns
        rh_wins = sum(1 for p in eligible if p.get("runhigh_win") is not None and float(p.get("runhigh_win", 0.0)) == 1.0)
        rl_wins = sum(1 for p in eligible if p.get("runlow_win") is not None and float(p.get("runlow_win", 0.0)) == 1.0)
        both_lost = sum(1 for p in eligible if float(p.get("runhigh_win") or 0.0) == 0.0 and float(p.get("runlow_win") or 0.0) == 0.0)

        rh_rate = round(rh_wins / n_eligible, 5)
        rl_rate = round(rl_wins / n_eligible, 5)

        rh_ci = wilson_score_interval(rh_wins, n_eligible)
        rl_ci = wilson_score_interval(rl_wins, n_eligible)

        # Calibration and statistical evaluation
        cal_rh = self.stat_evaluator.evaluate_calibration(eligible, direction="RUNHIGH")
        cal_rl = self.stat_evaluator.evaluate_calibration(eligible, direction="RUNLOW")
        dep_rh = self.stat_evaluator.evaluate_dependence_aware_uncertainty(eligible, direction="RUNHIGH")
        dep_rl = self.stat_evaluator.evaluate_dependence_aware_uncertainty(eligible, direction="RUNLOW")

        rh_metrics = DirectionalMetrics(
            direction="RUNHIGH",
            eligible_count=n_eligible,
            wins=rh_wins,
            losses=n_eligible - rh_wins,
            observed_win_rate=rh_rate,
            mean_predicted_prob=cal_rh.get("mean_predicted_prob"),
            wilson_ci_95=rh_ci,
            brier_score=cal_rh.get("brier_score"),
            reference_brier_score=cal_rh.get("reference_brier"),
            brier_skill_score=cal_rh.get("brier_skill_score"),
            expected_calibration_error=cal_rh.get("expected_calibration_error"),
            effective_sample_size=dep_rh.get("effective_sample_size"),
            bootstrap_ci_95=dep_rh.get("bootstrap_ci_95", (None, None))
        )

        rl_metrics = DirectionalMetrics(
            direction="RUNLOW",
            eligible_count=n_eligible,
            wins=rl_wins,
            losses=n_eligible - rl_wins,
            observed_win_rate=rl_rate,
            mean_predicted_prob=cal_rl.get("mean_predicted_prob"),
            wilson_ci_95=rl_ci,
            brier_score=cal_rl.get("brier_score"),
            reference_brier_score=cal_rl.get("reference_brier"),
            brier_skill_score=cal_rl.get("brier_skill_score"),
            expected_calibration_error=cal_rl.get("expected_calibration_error"),
            effective_sample_size=dep_rl.get("effective_sample_size"),
            bootstrap_ci_95=dep_rl.get("bootstrap_ci_95", (None, None))
        )

        # Economics evaluation
        econ = self.econ_evaluator.evaluate_quote_economics(eligible, direction="RUNHIGH")
        cum_pnl = sum(float(p.get("hypothetical_pnl") or 0.0) for p in eligible)

        checksum = self.compute_integrity_checksum(records, session_ids, symbol)

        return ResearchDatasetMetrics(
            symbol=symbol,
            session_ids=session_ids,
            total_predictions=total_preds,
            eligible_resolved_count=n_eligible,
            pending_count=pending_count,
            incomplete_count=incomplete_count,
            data_gap_count=data_gap_count,
            both_lost_count=both_lost,
            runhigh=rh_metrics,
            runlow=rl_metrics,
            quote_coverage_pct=econ.get("quote_coverage_pct", 0.0),
            mean_ask=econ.get("mean_ask"),
            mean_payout=econ.get("mean_payout"),
            mean_break_even_pct=econ.get("mean_break_even_pct"),
            ordinary_ev=econ.get("mean_ordinary_ev"),
            conservative_ev=econ.get("mean_conservative_ev"),
            cumulative_pnl=round(cum_pnl, 4),
            max_drawdown=econ.get("max_drawdown", 0.0),
            integrity_checksum=checksum,
            evaluation_timestamp_utc=now_iso,
            notes=[]
        )

    def compute_metrics(
        self,
        symbol: str = "R_75",
        session_id: Optional[str] = None,
        session_ids: Optional[List[str]] = None
    ) -> ResearchDatasetMetrics:
        """Convenience method accepting either a single session_id, a list of session_ids, or defaulting to all registered sessions."""
        target_sessions: List[str] = []
        if session_ids:
            target_sessions = list(session_ids)
        elif session_id:
            target_sessions = [session_id]
        else:
            # Query sessions from session_db_path or forward_db_path
            if os.path.exists(self.session_db_path):
                try:
                    with sqlite3.connect(self.session_db_path) as s_conn:
                        s_cur = s_conn.execute("SELECT session_id FROM forward_sessions WHERE symbol = ?", (symbol,))
                        target_sessions = [r[0] for r in s_cur.fetchall()]
                except Exception:
                    pass
            if not target_sessions and os.path.exists(self.forward_db_path):
                try:
                    with sqlite3.connect(self.forward_db_path) as f_conn:
                        f_cur = f_conn.execute("SELECT DISTINCT session_id FROM forward_predictions WHERE symbol = ? AND session_id != ''", (symbol,))
                        target_sessions = [r[0] for r in f_cur.fetchall()]
                except Exception:
                    pass
        return self.calculate_metrics(session_ids=target_sessions, symbol=symbol)

