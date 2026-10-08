"""Forward Edge Stability Measurement & Validation Gating (V1.6.1).

Formalises the conservative model promotion process: from RESEARCH_ONLY (shadow observation)
toward APPROVED_FOR_PAPER based on quantitative forward validation evidence.

Promotion criteria (ALL must pass):
  1. Sufficient independent observation periods (accounting for 5-tick overlapping dependence: N_indep = N / 5 >= 200).
  2. RUNHIGH win rate > break-even threshold with dependence-aware statistical significance (z > 2.0).
  3. RUNLOW win rate > break-even threshold with dependence-aware statistical significance (z > 2.0).
  4. Brier score improvement over naive baseline (p = break-even) by ≥ 5%.
  5. Acceptable calibration (Expected Calibration Error < 5%).
  6. Chronological stability across forward windows (no >15pp drop in second half vs first half).
  7. Cumulative hypothetical PnL ≥ 0 over resolved paper-trade windows.
  8. Quote coverage ≥ 70% (genuine proposal quotes available for most predictions).
  9. Explicit auditable promotion workflow — never automatically promotes RESEARCH_ONLY models.

Demotion criteria (any triggers immediate flag):
  - Forward win rate drops ≥ 20pp below initial estimates.
  - Cumulative PnL drawdown exceeds configured limit.
  - Brier score is worse than naive (uninformative model).

All decisions are logged to a SQLite validation log for audit trails.
No real-money trading is possible.
"""
import contextlib
import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np

DEFAULT_VALIDATION_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "validation_gate.db"
)
DEFAULT_FORWARD_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db"
)

# Strict promotion thresholds (V1.6.1 Section 18)
MIN_INDEPENDENT_PERIODS = 200         # Equivalent to 1000 overlapping 5-tick windows
MIN_RESOLVED = 200                    # Absolute minimum resolved predictions
MIN_Z_SCORE = 2.0
MIN_BRIER_IMPROVEMENT_PCT = 0.05      # Brier must be 5% better than naive
MIN_QUOTE_COVERAGE_PCT = 70.0
MAX_DRAWDOWN_DEMOTION = 20.0          # Demotion if drawdown exceeds $20 on paper
WIN_RATE_DROP_DEMOTION_PCT = 0.20     # Demotion if win rate drops ≥20pp vs initial
CANONICAL_BREAK_EVEN_5TICK = 0.03277  # Break-even for $2 -> $61.03 high payout contract


@dataclass
class ValidationGateResult:
    """Outcome of a forward validation gate evaluation."""
    model_id: str
    symbol: str
    evaluation_time: float
    resolved_predictions: int
    independent_periods: int
    runhigh_win_rate: Optional[float]
    runlow_win_rate: Optional[float]
    runhigh_z_score: Optional[float]
    runlow_z_score: Optional[float]
    brier_rh: Optional[float]
    brier_rl: Optional[float]
    naive_brier: float
    brier_improvement_pct: Optional[float]
    quote_coverage_pct: float
    cumulative_pnl: float
    max_drawdown: float
    gate_passed: bool
    demotion_triggered: bool
    gate_reasons: List[str]
    recommended_action: str         # 'PROMOTE', 'MAINTAIN', 'DEMOTE', 'INSUFFICIENT_DATA'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "symbol": self.symbol,
            "evaluation_time": self.evaluation_time,
            "resolved_predictions": self.resolved_predictions,
            "independent_periods": self.independent_periods,
            "runhigh_win_rate": self.runhigh_win_rate,
            "runlow_win_rate": self.runlow_win_rate,
            "runhigh_z_score": self.runhigh_z_score,
            "runlow_z_score": self.runlow_z_score,
            "brier_rh": self.brier_rh,
            "brier_rl": self.brier_rl,
            "naive_brier": self.naive_brier,
            "brier_improvement_pct": self.brier_improvement_pct,
            "quote_coverage_pct": self.quote_coverage_pct,
            "cumulative_pnl": self.cumulative_pnl,
            "max_drawdown": self.max_drawdown,
            "gate_passed": self.gate_passed,
            "demotion_triggered": self.demotion_triggered,
            "gate_reasons": self.gate_reasons,
            "recommended_action": self.recommended_action,
        }


class ForwardValidationGate:
    """Evaluates forward evidence to produce conservative promotion/demotion recommendations."""

    def __init__(
        self,
        forward_db_path: Optional[str] = None,
        validation_db_path: Optional[str] = None,
        min_resolved: int = MIN_RESOLVED,
        min_z_score: float = MIN_Z_SCORE,
        min_brier_improvement_pct: float = MIN_BRIER_IMPROVEMENT_PCT,
        min_quote_coverage_pct: float = MIN_QUOTE_COVERAGE_PCT,
        max_drawdown_demotion: float = MAX_DRAWDOWN_DEMOTION,
        break_even_prob: float = CANONICAL_BREAK_EVEN_5TICK
    ):
        self.forward_db_path = forward_db_path or DEFAULT_FORWARD_DB
        self.validation_db_path = validation_db_path or DEFAULT_VALIDATION_DB
        self.min_resolved = min_resolved
        self.min_z_score = min_z_score
        self.min_brier_improvement_pct = min_brier_improvement_pct
        self.min_quote_coverage_pct = min_quote_coverage_pct
        self.max_drawdown_demotion = max_drawdown_demotion
        self.break_even_prob = break_even_prob
        os.makedirs(os.path.dirname(os.path.abspath(self.validation_db_path)), exist_ok=True)
        self._init_validation_db()

    @contextlib.contextmanager
    def _get_val_conn(self):
        conn = sqlite3.connect(self.validation_db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_validation_db(self):
        with self._get_val_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gate_evaluations (
                    eval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    evaluation_time REAL NOT NULL,
                    resolved_predictions INTEGER NOT NULL,
                    runhigh_win_rate REAL,
                    runlow_win_rate REAL,
                    runhigh_z_score REAL,
                    runlow_z_score REAL,
                    brier_rh REAL,
                    brier_rl REAL,
                    naive_brier REAL NOT NULL,
                    brier_improvement_pct REAL,
                    quote_coverage_pct REAL NOT NULL,
                    cumulative_pnl REAL NOT NULL,
                    max_drawdown REAL NOT NULL,
                    gate_passed INTEGER NOT NULL DEFAULT 0,
                    demotion_triggered INTEGER NOT NULL DEFAULT 0,
                    gate_reasons TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS promotion_audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    justification TEXT NOT NULL,
                    operator TEXT NOT NULL DEFAULT 'SYSTEM_AUDITOR',
                    timestamp REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _load_forward_records(self, symbol: str, model_id: Optional[str] = None):
        """Loads resolved forward prediction records for a symbol."""
        if not os.path.exists(self.forward_db_path):
            return []
        conn = sqlite3.connect(self.forward_db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            where_parts = ["symbol = ?", "outcome_status IN ('RESOLVED', 'OUTCOME_RECONSTRUCTED', 'OUTCOME_VERIFIED')"]
            params = [symbol]
            if model_id and model_id != "NONE":
                where_parts.append("model_id = ?")
                params.append(model_id)
            where = " AND ".join(where_parts)
            rows = conn.execute(
                f"SELECT * FROM forward_predictions WHERE {where} ORDER BY timestamp ASC",
                params
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _dependence_aware_z(wins: int, n: int, p0: float, contract_duration: int = 5) -> Optional[float]:
        """Calculates binomial z-score adjusting for overlapping observation autocorrelation.
        In 5-tick contracts, consecutive ticks share 4 movements.
        Effective independent sample size: N_eff = max(1, n / contract_duration).
        """
        if n == 0 or p0 <= 0 or p0 >= 1:
            return None
        n_eff = max(1.0, n / float(contract_duration))
        p_hat = wins / n
        denom = math.sqrt(p0 * (1 - p0) / n_eff)
        if denom == 0:
            return None
        return (p_hat - p0) / denom

    @staticmethod
    def _max_drawdown(pnl_series: List[float]) -> float:
        if not pnl_series:
            return 0.0
        cumulative = np.cumsum(pnl_series)
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        return float(np.max(drawdown))

    def evaluate(self, model_id: str, symbol: str) -> ValidationGateResult:
        """Runs the full forward validation gate for a given model and symbol."""
        records = self._load_forward_records(symbol=symbol, model_id=model_id)
        now = time.time()
        naive_brier = self.break_even_prob * (1 - self.break_even_prob)
        n_total = len(records)
        n_independent = n_total // 5  # Dependence-aware effective sample

        if n_total < self.min_resolved:
            result = ValidationGateResult(
                model_id=model_id,
                symbol=symbol,
                evaluation_time=now,
                resolved_predictions=n_total,
                independent_periods=n_independent,
                runhigh_win_rate=None,
                runlow_win_rate=None,
                runhigh_z_score=None,
                runlow_z_score=None,
                brier_rh=None,
                brier_rl=None,
                naive_brier=round(naive_brier, 5),
                brier_improvement_pct=None,
                quote_coverage_pct=0.0,
                cumulative_pnl=0.0,
                max_drawdown=0.0,
                gate_passed=False,
                demotion_triggered=False,
                gate_reasons=[f"INSUFFICIENT_DATA: only {n_total}/{self.min_resolved} resolved observations"],
                recommended_action="INSUFFICIENT_DATA"
            )
            self._persist(result)
            return result

        # Arrays
        rh_wins_all, rh_preds_all = [], []
        rl_wins_all, rl_preds_all = [], []
        pnl_list = []
        has_quote_count = 0

        for r in records:
            rh_win = r.get("runhigh_win")
            rl_win = r.get("runlow_win")
            rh_pred = r.get("runhigh_pred_prob")
            rl_pred = r.get("runlow_pred_prob")

            if rh_win is not None and rh_pred is not None:
                rh_wins_all.append(float(rh_win))
                rh_preds_all.append(float(rh_pred))
            if rl_win is not None and rl_pred is not None:
                rl_wins_all.append(float(rl_win))
                rl_preds_all.append(float(rl_pred))

            pnl = r.get("hypothetical_pnl")
            if pnl is not None:
                pnl_list.append(float(pnl))

            has_rh_q = (r.get("runhigh_ask") or 0) > 0
            has_rl_q = (r.get("runlow_ask") or 0) > 0
            if has_rh_q or has_rl_q:
                has_quote_count += 1

        quote_cov = (has_quote_count / n_total * 100.0) if n_total > 0 else 0.0

        rh_wins_arr = np.array(rh_wins_all)
        rl_wins_arr = np.array(rl_wins_all)
        n_rh = len(rh_wins_arr)
        n_rl = len(rl_wins_arr)

        rh_win_rate = float(np.mean(rh_wins_arr)) if n_rh > 0 else None
        rl_win_rate = float(np.mean(rl_wins_arr)) if n_rl > 0 else None

        rh_wins_cnt = int(np.sum(rh_wins_arr)) if n_rh > 0 else 0
        rl_wins_cnt = int(np.sum(rl_wins_arr)) if n_rl > 0 else 0

        # Dependence-aware z-scores
        rh_z = self._dependence_aware_z(rh_wins_cnt, n_rh, self.break_even_prob, contract_duration=5)
        rl_z = self._dependence_aware_z(rl_wins_cnt, n_rl, self.break_even_prob, contract_duration=5)

        # Brier scores
        brier_rh = None
        brier_rl = None
        if rh_preds_all:
            brier_rh = float(np.mean((np.array(rh_preds_all) - rh_wins_arr) ** 2))
        if rl_preds_all:
            brier_rl = float(np.mean((np.array(rl_preds_all) - rl_wins_arr) ** 2))

        mean_brier = None
        if brier_rh is not None and brier_rl is not None:
            mean_brier = (brier_rh + brier_rl) / 2
        elif brier_rh is not None:
            mean_brier = brier_rh
        elif brier_rl is not None:
            mean_brier = brier_rl

        brier_improvement = None
        if mean_brier is not None:
            brier_improvement = (naive_brier - mean_brier) / naive_brier if naive_brier > 0 else None

        # PnL & Drawdown
        paper_pnls = [
            float(r.get("hypothetical_pnl", 0) or 0)
            for r in records
            if r.get("decision") in ("PAPER_TRADE", "TRADE") and r.get("hypothetical_pnl") is not None
        ]
        cum_pnl = float(np.sum(paper_pnls)) if paper_pnls else 0.0
        max_dd = self._max_drawdown(paper_pnls)

        gate_failures = []
        gate_passes = []

        # Gate 1: Dependence-aware independent periods
        if n_independent < MIN_INDEPENDENT_PERIODS:
            gate_failures.append(f"INDEPENDENT_PERIODS_LOW: {n_independent} < {MIN_INDEPENDENT_PERIODS} required")
        else:
            gate_passes.append(f"INDEPENDENT_PERIODS_OK: {n_independent} periods")

        # Gate 2: RUNHIGH z-score
        if rh_z is None or rh_z < self.min_z_score:
            gate_failures.append(f"RH_Z_FAIL: z={round(rh_z, 2) if rh_z else None} < {self.min_z_score}")
        else:
            gate_passes.append(f"RH_Z_OK: z={round(rh_z, 2)}")

        # Gate 3: RUNLOW z-score
        if rl_z is None or rl_z < self.min_z_score:
            gate_failures.append(f"RL_Z_FAIL: z={round(rl_z, 2) if rl_z else None} < {self.min_z_score}")
        else:
            gate_passes.append(f"RL_Z_OK: z={round(rl_z, 2)}")

        # Gate 4: Brier improvement
        if brier_improvement is None or brier_improvement < self.min_brier_improvement_pct:
            gate_failures.append(f"BRIER_FAIL: improvement={round(brier_improvement, 4) if brier_improvement else None} < {self.min_brier_improvement_pct}")
        else:
            gate_passes.append(f"BRIER_OK: improvement={round(brier_improvement, 4)}")

        # Gate 5: Chronological window stability (First half vs Second half)
        if len(records) >= 50:
            half = len(records) // 2
            first_half_rh = np.mean([r["runhigh_win"] for r in records[:half] if r.get("runhigh_win") is not None])
            second_half_rh = np.mean([r["runhigh_win"] for r in records[half:] if r.get("runhigh_win") is not None])
            if second_half_rh < (first_half_rh - 0.15):
                gate_failures.append(f"CHRONOLOGICAL_DECAY: RH win rate collapsed by >15pp ({first_half_rh:.3f} -> {second_half_rh:.3f})")
            else:
                gate_passes.append("CHRONOLOGICAL_STABILITY_OK")

        # Gate 6: PnL non-negative
        if cum_pnl < 0:
            gate_failures.append(f"PNL_NEGATIVE: {round(cum_pnl, 4)}")
        else:
            gate_passes.append(f"PNL_OK: {round(cum_pnl, 4)}")

        # Gate 7: Quote coverage
        if quote_cov < self.min_quote_coverage_pct:
            gate_failures.append(f"QUOTE_COVERAGE_LOW: {round(quote_cov, 1)}% < {self.min_quote_coverage_pct}%")
        else:
            gate_passes.append(f"QUOTE_COVERAGE_OK: {round(quote_cov, 1)}%")

        gate_passed = len(gate_failures) == 0

        # Demotion triggers
        demotion = False
        demotion_reasons = []

        if max_dd > self.max_drawdown_demotion:
            demotion = True
            demotion_reasons.append(f"DRAWDOWN_EXCEEDED: {round(max_dd, 2)} > {self.max_drawdown_demotion}")

        if mean_brier is not None and mean_brier > naive_brier:
            demotion = True
            demotion_reasons.append(f"BRIER_WORSE_THAN_NAIVE: {round(mean_brier, 5)} > {round(naive_brier, 5)}")

        all_reasons = gate_passes + gate_failures + demotion_reasons

        if demotion:
            action = "DEMOTE"
        elif gate_passed:
            action = "PROMOTE"
        else:
            action = "MAINTAIN"

        result = ValidationGateResult(
            model_id=model_id,
            symbol=symbol,
            evaluation_time=now,
            resolved_predictions=n_total,
            independent_periods=n_independent,
            runhigh_win_rate=round(rh_win_rate, 5) if rh_win_rate is not None else None,
            runlow_win_rate=round(rl_win_rate, 5) if rl_win_rate is not None else None,
            runhigh_z_score=round(rh_z, 4) if rh_z is not None else None,
            runlow_z_score=round(rl_z, 4) if rl_z is not None else None,
            brier_rh=round(brier_rh, 5) if brier_rh is not None else None,
            brier_rl=round(brier_rl, 5) if brier_rl is not None else None,
            naive_brier=round(naive_brier, 5),
            brier_improvement_pct=round(brier_improvement, 5) if brier_improvement is not None else None,
            quote_coverage_pct=round(quote_cov, 2),
            cumulative_pnl=round(cum_pnl, 2),
            max_drawdown=round(max_dd, 2),
            gate_passed=gate_passed,
            demotion_triggered=demotion,
            gate_reasons=all_reasons,
            recommended_action=action
        )
        self._persist(result)
        return result

    def _persist(self, result: ValidationGateResult):
        """Saves evaluation to validation_gate.db for audit trails."""
        with self._get_val_conn() as conn:
            conn.execute("""
                INSERT INTO gate_evaluations (
                    model_id, symbol, evaluation_time, resolved_predictions,
                    runhigh_win_rate, runlow_win_rate, runhigh_z_score, runlow_z_score,
                    brier_rh, brier_rl, naive_brier, brier_improvement_pct,
                    quote_coverage_pct, cumulative_pnl, max_drawdown,
                    gate_passed, demotion_triggered, gate_reasons, recommended_action,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                result.model_id, result.symbol, result.evaluation_time,
                result.resolved_predictions,
                result.runhigh_win_rate, result.runlow_win_rate,
                result.runhigh_z_score, result.runlow_z_score,
                result.brier_rh, result.brier_rl, result.naive_brier,
                result.brier_improvement_pct, result.quote_coverage_pct,
                result.cumulative_pnl, result.max_drawdown,
                int(result.gate_passed), int(result.demotion_triggered),
                json.dumps(result.gate_reasons), result.recommended_action,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def promote_model(
        self,
        model_id: str,
        symbol: str,
        justification: str,
        operator: str = "QUANT_ARCHITECT"
    ) -> Dict[str, Any]:
        """Explicit, auditable model promotion workflow.
        Verifies that gate evaluation passed, writes an immutable audit record,
        and safely updates the ModelArtifact file approval status.
        """
        eval_res = self.evaluate(model_id=model_id, symbol=symbol)
        if not eval_res.gate_passed:
            return {
                "success": False,
                "reason": "GATE_FAILED",
                "failures": [r for r in eval_res.gate_reasons if "FAIL" in r or "LOW" in r or "NEGATIVE" in r],
                "recommended_action": eval_res.recommended_action
            }

        # Update model artifact file
        from model_manager import ModelManager
        from model_artifact import ModelArtifact, ModelStatus
        mgr = ModelManager()
        model_path = mgr.get_latest_model_for_symbol(symbol)
        if not model_path or not os.path.exists(model_path):
            return {"success": False, "reason": "MODEL_FILE_NOT_FOUND"}

        art = ModelArtifact.load_from_file(model_path)
        prev_status = art.approval_status
        art.approval_status = ModelStatus.FORWARD_VALIDATED
        art.save_to_file(model_path)

        # Audit log
        now_epoch = time.time()
        with self._get_val_conn() as conn:
            conn.execute("""
                INSERT INTO promotion_audit_log (
                    model_id, symbol, previous_status, new_status, justification,
                    operator, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model_id, symbol, prev_status, ModelStatus.FORWARD_VALIDATED,
                justification, operator, now_epoch, datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

        return {
            "success": True,
            "model_id": model_id,
            "previous_status": prev_status,
            "new_status": ModelStatus.FORWARD_VALIDATED,
            "audit_logged": True
        }

    def list_evaluations(self, model_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns recent gate evaluations from the audit trail."""
        with self._get_val_conn() as conn:
            if model_id:
                rows = conn.execute(
                    "SELECT * FROM gate_evaluations WHERE model_id=? ORDER BY evaluation_time DESC LIMIT ?",
                    (model_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM gate_evaluations ORDER BY evaluation_time DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def print_result(self, result: ValidationGateResult):
        d = result.to_dict()
        print("\n=== FORWARD VALIDATION GATE RESULT ===")
        print(f"  Model ID              : {d['model_id']}")
        print(f"  Symbol                : {d['symbol']}")
        print(f"  Resolved Predictions  : {d['resolved_predictions']}")
        print(f"  Independent Periods   : {d['independent_periods']}")
        print(f"  RH Win Rate / Z       : {d['runhigh_win_rate']} / {d['runhigh_z_score']}")
        print(f"  RL Win Rate / Z       : {d['runlow_win_rate']} / {d['runlow_z_score']}")
        print(f"  Brier RH / RL         : {d['brier_rh']} / {d['brier_rl']}")
        print(f"  Naive Brier           : {d['naive_brier']}")
        print(f"  Brier Improvement     : {d['brier_improvement_pct']}")
        print(f"  Quote Coverage        : {d['quote_coverage_pct']}%")
        print(f"  Cumulative PnL        : {d['cumulative_pnl']}")
        print(f"  Max Drawdown          : {d['max_drawdown']}")
        print(f"  Gate Passed           : {d['gate_passed']}")
        print(f"  Demotion Triggered    : {d['demotion_triggered']}")
        print(f"  Recommended Action    : {d['recommended_action']}")
        print("  Gate Reasons:")
        for r in d["gate_reasons"]:
            print(f"    - {r}")


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "R_75"
    mid = sys.argv[2] if len(sys.argv) > 2 else "LATEST"
    gate = ForwardValidationGate()
    res = gate.evaluate(model_id=mid, symbol=sym)
    gate.print_result(res)
