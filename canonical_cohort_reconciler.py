"""Canonical Cohort Accounting & Economic Reconciliation Engine (V1.8.3.1).

Eliminates mixed economic denominators by enforcing independent cohort accounting:
- Cohort A: All resolved prospective predictions (unpriced predictive quality, directional accuracy).
- Cohort B: Chronologically matched genuine broker quotes (descriptive pricing economics).
- Cohort C: Strict execution-quality SHADOW proxy (realized hypothetical return strictly divided by priced N).
- Cohort D: Preregistered independent confirmation (quarantined, N = 0).

Permanent safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""

from dataclasses import dataclass, field, asdict
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LIVE_EXECUTION_DISABLED: bool = True

COHORT_A = "COHORT_A_ALL_PROSPECTIVE"
COHORT_B = "COHORT_B_MATCHED_QUOTES"
COHORT_C = "COHORT_C_STRICT_SHADOW_PROXY"
COHORT_D = "COHORT_D_PREREGISTERED_CONFIRMATION"

OUTCOME_RESOLVED = "OUTCOME_RESOLVED"


@dataclass
class HypothesisCohortMetrics:
    """Rigorous cohort metrics for an individual market/contract/duration hypothesis."""
    contract_family: str
    contract_type: str
    duration_ticks: int
    
    # Cohort A: All Resolved Prospective Predictions
    cohort_a_total_committed: int
    cohort_a_resolved_n: int
    cohort_a_wins: int
    cohort_a_losses: int
    cohort_a_win_rate: float
    cohort_a_mean_prob: float
    cohort_a_brier_score: float
    cohort_a_obs_ids: List[str] = field(default_factory=list)

    # Cohort B: Chronologically Matched Genuine Proposals
    cohort_b_matched_n: int = 0
    cohort_b_mean_ask: float = 0.0
    cohort_b_mean_payout: float = 0.0
    cohort_b_implied_break_even: float = 0.0
    cohort_b_obs_ids: List[str] = field(default_factory=list)

    # Cohort C: Strict Execution-Quality SHADOW Proxy (Priced Economics)
    cohort_c_priced_n: int = 0
    cohort_c_wins: int = 0
    cohort_c_losses: int = 0
    cohort_c_win_rate: float = 0.0
    cohort_c_mean_ask: float = 0.0
    cohort_c_mean_payout: float = 0.0
    cohort_c_mean_predicted_ev: float = 0.0
    cohort_c_sum_hypothetical_return: float = 0.0
    cohort_c_mean_hypothetical_return: float = 0.0
    cohort_c_mbb_lower_95: float = 0.0
    cohort_c_mbb_upper_95: float = 0.0
    cohort_c_obs_ids: List[str] = field(default_factory=list)

    # Cohort D: Preregistered Confirmation
    cohort_d_count: int = 0
    cohort_d_quarantined: bool = True

    # Denominator Divergence Metrics
    unpriced_resolved_n: int = 0
    unpriced_wins: int = 0
    denominator_divergence: int = 0  # cohort_a_resolved_n - cohort_c_priced_n

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Exclude massive id lists from high-level summary view if needed
        d["cohort_a_obs_count"] = len(self.cohort_a_obs_ids)
        d["cohort_b_obs_count"] = len(self.cohort_b_obs_ids)
        d["cohort_c_obs_count"] = len(self.cohort_c_obs_ids)
        return d


def compute_mbb_bounds(returns: np.ndarray, iterations: int = 500, alpha: float = 0.05) -> Tuple[float, float]:
    """Computes dependence-aware Moving Block Bootstrap 95% confidence interval."""
    n = len(returns)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        val = float(returns[0])
        return val, val

    block_size = max(2, min(5, n // 4)) if n >= 8 else 1
    n_blocks = max(1, n // block_size)
    means = []

    for _ in range(iterations):
        sample = []
        for _ in range(n_blocks):
            start = np.random.randint(0, max(1, n - block_size + 1))
            sample.extend(returns[start : start + block_size])
        if sample:
            means.append(np.mean(sample))

    if not means:
        m = float(np.mean(returns))
        return m, m

    means_arr = np.array(means)
    low = float(np.percentile(means_arr, alpha * 100))
    high = float(np.percentile(means_arr, (1.0 - alpha) * 100))
    return round(low, 4), round(high, 4)


class CanonicalCohortReconciler:
    """Authoritative reconciler calculating independent cohort populations and economics."""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self.conn.row_factory = sqlite3.Row

    @classmethod
    def from_db_path(cls, db_path: str) -> "CanonicalCohortReconciler":
        conn = sqlite3.connect(db_path)
        return cls(conn)

    def close(self) -> None:
        self.conn.close()

    def reconcile_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Performs exhaustive, population-isolated reconciliation across all cohorts."""
        cursor = self.conn.cursor()

        # Target session filter
        sess_clause = "WHERE session_id = ?" if session_id else ""
        sess_params = (session_id,) if session_id else ()

        # 1. Total Session Telemetry
        cursor.execute(f"SELECT count(*) FROM forward_observations {sess_clause}", sess_params)
        total_committed = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT count(*) FROM forward_observations {sess_clause} "
            f"{'AND' if session_id else 'WHERE'} outcome_status = '{OUTCOME_RESOLVED}'",
            sess_params,
        )
        total_resolved = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT count(*) FROM forward_observations {sess_clause} "
            f"{'AND' if session_id else 'WHERE'} proposal_id IS NOT NULL",
            sess_params,
        )
        total_quote_matched = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT count(*) FROM forward_observations {sess_clause} "
            f"{'AND' if session_id else 'WHERE'} hypothetical_return IS NOT NULL",
            sess_params,
        )
        total_strictly_priced = cursor.fetchone()[0]

        # 2. Extract Distinct Hypothesis Tuples
        cursor.execute(
            f"SELECT DISTINCT contract_family, contract_type, duration_ticks "
            f"FROM forward_observations {sess_clause} "
            f"ORDER BY contract_family, contract_type, duration_ticks",
            sess_params,
        )
        hypotheses = cursor.fetchall()

        hypothesis_metrics: List[HypothesisCohortMetrics] = []

        for h in hypotheses:
            fam = h["contract_family"]
            ctype = h["contract_type"]
            dur = h["duration_ticks"]

            # Filter for this hypothesis
            where_base = (
                f"WHERE contract_family = ? AND contract_type = ? AND duration_ticks = ? "
                + (f"AND session_id = ? " if session_id else "")
            )
            base_params = [fam, ctype, dur]
            if session_id:
                base_params.append(session_id)

            # Query all records for this hypothesis
            cursor.execute(
                f"SELECT observation_id, predicted_prob, observed_outcome, outcome_status, "
                f"       proposal_id, ask_price, total_payout, hypothetical_return, evidence_cohort "
                f"FROM forward_observations {where_base}",
                base_params,
            )
            rows = cursor.fetchall()

            # --- COHORT A: All Resolved Prospective ---
            committed_n = len(rows)
            resolved_rows = [r for r in rows if r["outcome_status"] == OUTCOME_RESOLVED]
            resolved_n = len(resolved_rows)
            resolved_wins = sum(1 for r in resolved_rows if r["observed_outcome"] == 1)
            resolved_losses = resolved_n - resolved_wins
            unpriced_wr = (resolved_wins / resolved_n) if resolved_n > 0 else 0.0

            probs = [r["predicted_prob"] for r in resolved_rows if r["predicted_prob"] is not None]
            mean_prob = float(np.mean(probs)) if probs else 0.5
            outcomes = [r["observed_outcome"] for r in resolved_rows if r["observed_outcome"] is not None]
            brier = float(np.mean([(p - o) ** 2 for p, o in zip(probs, outcomes)])) if (probs and outcomes) else 0.0

            cohort_a_ids = [r["observation_id"] for r in resolved_rows]

            # --- COHORT B: Quoted Observations ---
            quoted_rows = [r for r in rows if r["proposal_id"] is not None and r["ask_price"] is not None and r["total_payout"] is not None]
            quoted_n = len(quoted_rows)
            asks = [r["ask_price"] for r in quoted_rows]
            payouts = [r["total_payout"] for r in quoted_rows]
            mean_ask_b = float(np.mean(asks)) if asks else 0.0
            mean_payout_b = float(np.mean(payouts)) if payouts else 0.0
            be_b = (mean_ask_b / mean_payout_b) if mean_payout_b > 0 else 0.0
            cohort_b_ids = [r["observation_id"] for r in quoted_rows]

            # --- COHORT C: Strict Execution-Quality SHADOW Proxy ---
            # Strict conditions: Resolved outcome, matched proposal, non-null ask, payout, return
            priced_rows = [
                r for r in resolved_rows
                if r["proposal_id"] is not None
                and r["ask_price"] is not None
                and r["total_payout"] is not None
                and r["hypothetical_return"] is not None
            ]
            priced_n = len(priced_rows)
            priced_wins = sum(1 for r in priced_rows if r["observed_outcome"] == 1)
            priced_losses = priced_n - priced_wins
            priced_wr = (priced_wins / priced_n) if priced_n > 0 else 0.0

            priced_asks = [r["ask_price"] for r in priced_rows]
            priced_payouts = [r["total_payout"] for r in priced_rows]
            returns = [r["hypothetical_return"] for r in priced_rows]

            mean_ask_c = float(np.mean(priced_asks)) if priced_asks else 0.0
            mean_payout_c = float(np.mean(priced_payouts)) if priced_payouts else 0.0
            sum_ret_c = float(np.sum(returns)) if returns else 0.0
            mean_ret_c = (sum_ret_c / priced_n) if priced_n > 0 else 0.0

            # Predicted EV on priced observations
            pred_evs = [
                (r["predicted_prob"] * r["total_payout"] - r["ask_price"])
                for r in priced_rows
                if r["predicted_prob"] is not None and r["total_payout"] is not None and r["ask_price"] is not None
            ]
            mean_pred_ev_c = float(np.mean(pred_evs)) if pred_evs else 0.0

            # MBB confidence bounds strictly on priced returns
            ret_arr = np.array(returns, dtype=np.float64)
            mbb_low, mbb_high = compute_mbb_bounds(ret_arr)

            cohort_c_ids = [r["observation_id"] for r in priced_rows]

            # Unpriced divergence accounting
            unpriced_rows = [r for r in resolved_rows if r["hypothetical_return"] is None]
            unpriced_n = len(unpriced_rows)
            unpriced_wins = sum(1 for r in unpriced_rows if r["observed_outcome"] == 1)
            div = resolved_n - priced_n

            metrics = HypothesisCohortMetrics(
                contract_family=fam,
                contract_type=ctype,
                duration_ticks=dur,
                cohort_a_total_committed=committed_n,
                cohort_a_resolved_n=resolved_n,
                cohort_a_wins=resolved_wins,
                cohort_a_losses=resolved_losses,
                cohort_a_win_rate=round(unpriced_wr, 4),
                cohort_a_mean_prob=round(mean_prob, 4),
                cohort_a_brier_score=round(brier, 6),
                cohort_a_obs_ids=cohort_a_ids,
                cohort_b_matched_n=quoted_n,
                cohort_b_mean_ask=round(mean_ask_b, 2),
                cohort_b_mean_payout=round(mean_payout_b, 2),
                cohort_b_implied_break_even=round(be_b, 4),
                cohort_b_obs_ids=cohort_b_ids,
                cohort_c_priced_n=priced_n,
                cohort_c_wins=priced_wins,
                cohort_c_losses=priced_losses,
                cohort_c_win_rate=round(priced_wr, 4),
                cohort_c_mean_ask=round(mean_ask_c, 2),
                cohort_c_mean_payout=round(mean_payout_c, 2),
                cohort_c_mean_predicted_ev=round(mean_pred_ev_c, 4),
                cohort_c_sum_hypothetical_return=round(sum_ret_c, 4),
                cohort_c_mean_hypothetical_return=round(mean_ret_c, 4),
                cohort_c_mbb_lower_95=mbb_low,
                cohort_c_mbb_upper_95=mbb_high,
                cohort_c_obs_ids=cohort_c_ids,
                cohort_d_count=0,
                cohort_d_quarantined=True,
                unpriced_resolved_n=unpriced_n,
                unpriced_wins=unpriced_wins,
                denominator_divergence=div,
            )
            hypothesis_metrics.append(metrics)

        return {
            "session_id": session_id or "ALL_SESSIONS",
            "telemetry": {
                "total_committed": total_committed,
                "total_resolved": total_resolved,
                "total_quote_matched": total_quote_matched,
                "total_strictly_priced": total_strictly_priced,
            },
            "hypotheses": [h.to_dict() for h in hypothesis_metrics],
        }
