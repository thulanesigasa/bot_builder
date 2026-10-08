"""Centralized Forward Edge Confirmation Gate (V1.7.1 Part D).

Provides the single authoritative gate evaluating whether a trading candidate has demonstrated
an independently confirmed, statistically robust, calibrated, and economically positive edge:
- Enforces strict AND logic across 13 mandatory categories.
- Precludes any code path from declaring FORWARD_EDGE_CONFIRMED with weaker requirements.
- Distinguishes absent confirmation studies (NO_CONFIRMATION_SESSIONS) from failed studies.
- Completely eliminates historical benchmark quote fallbacks (returns QUOTE_DATA_INSUFFICIENT).
"""
import hashlib
import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from confirmation_specification import ConfirmationManifest
from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION,
)
from session_reconciler import SessionReconciler
from statistical_evaluator import (
    StatisticalEvaluator,
    wilson_score_interval,
    REFERENCE_BASE_RATE_RUNHIGH,
    REFERENCE_BASE_RATE_RUNLOW,
)
from economic_evaluator import EconomicEvaluator
from quote_database import QuoteDatabase


# Authoritative Verdict Constants
VERDICT_NO_CONFIRMATION_SESSIONS = "NO_CONFIRMATION_SESSIONS"
VERDICT_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
VERDICT_QUOTE_DATA_INSUFFICIENT = "QUOTE_DATA_INSUFFICIENT"
VERDICT_CALIBRATION_FAILED = "CALIBRATION_FAILED"
VERDICT_CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
VERDICT_FORWARD_EDGE_CONFIRMED = "FORWARD_EDGE_CONFIRMED"
VERDICT_INSUFFICIENT_FORWARD_DATA = "INSUFFICIENT_FORWARD_DATA"
VERDICT_NO_VALIDATED_EDGE = "NO_VALIDATED_EDGE"

# Short aliases
VERDICT_NO_CONFIRMATION = VERDICT_NO_CONFIRMATION_SESSIONS
VERDICT_QUOTE_INSUFFICIENT = VERDICT_QUOTE_DATA_INSUFFICIENT
VERDICT_REJECTED = VERDICT_CONFIRMATION_REJECTED
VERDICT_CONFIRMED = VERDICT_FORWARD_EDGE_CONFIRMED
VERDICT_INSUFFICIENT_DATA = VERDICT_INSUFFICIENT_FORWARD_DATA


@dataclass
class ConfirmationGateReport:
    """Full auditable result from authoritative confirmation gate evaluation."""
    verdict: str
    is_confirmed: bool
    model_id: str
    symbol: str
    contract_type: str
    evaluation_time_utc: str
    manifest_id: Optional[str]
    manifest_checksum: Optional[str]
    manifest_verified: bool
    confirmation_sessions_count: int
    confirmation_sessions_reconciled: bool
    nominal_sample_size: int
    effective_sample_size: float
    observed_win_rate: Optional[float]
    mean_predicted_prob: Optional[float]
    break_even_hurdle: Optional[float]
    quote_coverage_pct: float
    brier_score: Optional[float]
    brier_skill_score: Optional[float]
    expected_calibration_error: Optional[float]
    bootstrap_ci_95: Tuple[Optional[float], Optional[float]]
    ordinary_ev: Optional[float]
    conservative_ev: Optional[float]
    max_drawdown: float
    gate_checks: Dict[str, bool]
    rejection_reasons: List[str]
    manifest: Optional[ConfirmationManifest] = None

    @property
    def confirmed(self) -> bool:
        return self.is_confirmed

    @property
    def gate_failures(self) -> List[str]:
        return [k for k, v in self.gate_checks.items() if not v]

    @property
    def criteria_frozen(self) -> bool:
        return self.manifest_verified

    @property
    def confirmation_resolved_count(self) -> int:
        return self.nominal_sample_size

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("manifest", None)
        return d


ConfirmationGateResult = ConfirmationGateReport


class ForwardConfirmationGate:
    """Authoritative gatekeeper for quantitative edge confirmation."""

    def __init__(
        self,
        session_registry: Optional[ForwardSessionRegistry] = None,
        quote_db: Optional[QuoteDatabase] = None,
        forward_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
        session_db_path: Optional[str] = None,
        manifest: Optional[ConfirmationManifest] = None
    ):
        if session_registry:
            self.session_registry = session_registry
        elif session_db_path:
            self.session_registry = ForwardSessionRegistry(db_path=session_db_path)
        else:
            self.session_registry = ForwardSessionRegistry()

        if quote_db:
            self.quote_db = quote_db
        elif quote_db_path:
            self.quote_db = QuoteDatabase(db_path=quote_db_path)
        else:
            self.quote_db = QuoteDatabase()

        self.forward_db_path = forward_db_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "forward_predictions.db"
        )
        self.reconciler = SessionReconciler(
            registry_db_path=self.session_registry.db_path,
            journal_db_path=self.forward_db_path,
            quote_db_path=self.quote_db.db_path
        )
        self.stat_evaluator = StatisticalEvaluator()
        self.econ_evaluator = EconomicEvaluator()
        self.manifest = manifest

    def evaluate(
        self,
        symbol: str = "R_75",
        model_id: str = "LATEST",
        contract_type: str = "RUNHIGH",
        manifest: Optional[ConfirmationManifest] = None
    ) -> ConfirmationGateReport:
        """Alias for evaluate_forward_edge_confirmation."""
        return self.evaluate_forward_edge_confirmation(
            model_id=model_id,
            symbol=symbol,
            contract_type=contract_type,
            manifest=manifest or self.manifest
        )

    def _load_predictions_for_sessions(self, session_ids: List[str]) -> List[Dict[str, Any]]:
        """Loads predictions strictly belonging to the given session IDs."""
        if not session_ids or not os.path.exists(self.forward_db_path):
            return []
        conn = sqlite3.connect(self.forward_db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            placeholders = ",".join("?" for _ in session_ids)
            query = f"""
                SELECT p.*, o.runhigh_win, o.runlow_win, o.outcome_status as outcome_res_status
                FROM forward_predictions p
                LEFT JOIN forward_outcomes o ON p.prediction_id = o.prediction_id
                WHERE p.session_id IN ({placeholders})
                ORDER BY p.timestamp ASC
            """
            rows = conn.execute(query, session_ids).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                # Ensure outcome status from outcomes table is recognized
                if d.get("outcome_res_status"):
                    d["outcome_status"] = d["outcome_res_status"]
                results.append(d)
            return results
        finally:
            conn.close()

    def evaluate_forward_edge_confirmation(
        self,
        model_id: str,
        symbol: str = "R_75",
        contract_type: str = "RUNHIGH",
        manifest: Optional[ConfirmationManifest] = None,
        model_artifact_path: Optional[str] = None
    ) -> ConfirmationGateReport:
        """Runs the complete 13-gate confirmation assessment.
        
        Strictly enforces:
        1. Manifest verification (pre-registered frozen criteria)
        2. Presence of independent CONFIRMATION_FORWARD sessions (never exploratory)
        3. Database reconciliation on all confirmation sessions
        4. Chronological separation from model selection/training
        5. Adequate sample size and effective sample size (N_eff)
        6. Genuine quote coverage >= 95% with lookahead protection (no benchmark fallbacks)
        7. Probability calibration (BSS > 0, ECE <= 5%)
        8. Statistical significance (dependence-aware)
        9. Ordinary EV > 0
        10. Conservative EV > 0 with validated lower probability bound
        11. Forward stability across independent sessions
        12. Acceptable hypothetical risk and drawdown
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        gate_checks: Dict[str, bool] = {
            "manifest_valid": False,
            "confirmation_sessions_present": False,
            "sessions_reconciled": False,
            "chronological_integrity": False,
            "sample_size_adequate": False,
            "effective_sample_adequate": False,
            "quote_coverage_adequate": False,
            "calibration_valid": False,
            "statistical_significance": False,
            "ordinary_ev_positive": False,
            "conservative_ev_positive": False,
            "stability_adequate": False,
            "risk_limits_respected": False,
        }
        reasons: List[str] = []

        # 1. Manifest verification
        manifest_verified = False
        if manifest:
            manifest_verified = manifest.verify_checksum()
            if not manifest_verified:
                reasons.append("Confirmation manifest checksum verification failed (specification tampered).")
            elif manifest.model_id != model_id or manifest.market_symbol != symbol:
                manifest_verified = False
                reasons.append(f"Manifest model/symbol mismatch: expected {model_id}/{symbol}, got {manifest.model_id}/{manifest.market_symbol}.")
        gate_checks["manifest_valid"] = manifest_verified

        # 2. Check for Confirmation Sessions
        all_sessions = self.session_registry.list_sessions(symbol=symbol)
        conf_sessions = [s for s in all_sessions if s.research_stage == STAGE_CONFIRMATION]
        val_sessions = [s for s in all_sessions if s.research_stage == STAGE_VALIDATION]
        expl_sessions = [s for s in all_sessions if s.research_stage == STAGE_EXPLORATORY]

        if not conf_sessions:
            # Distinguish absent confirmation sessions from completed failed studies
            gate_checks["confirmation_sessions_present"] = False
            reasons.append("NO_CONFIRMATION_SESSIONS: Zero independent sessions registered under CONFIRMATION_FORWARD stage.")
            
            # Check if validation data shows promise (CONFIRMATION_REQUIRED) or not
            verdict = VERDICT_NO_CONFIRMATION_SESSIONS
            if val_sessions:
                val_ids = [s.session_id for s in val_sessions]
                val_preds = self._load_predictions_for_sessions(val_ids)
                if len(val_preds) >= 50:
                    val_wr = self.stat_evaluator.evaluate_win_rates(val_preds)
                    c_key = "runhigh" if contract_type.upper() == "RUNHIGH" else "runlow"
                    obs_rate = val_wr.get(c_key, {}).get("observed_rate", 0.0)
                    ref_rate = REFERENCE_BASE_RATE_RUNHIGH if c_key == "runhigh" else REFERENCE_BASE_RATE_RUNLOW
                    if obs_rate > ref_rate:
                        verdict = VERDICT_CONFIRMATION_REQUIRED
                        reasons.append("Validation stage demonstrated positive lift; pre-registered confirmation study is required.")

            return ConfirmationGateReport(
                verdict=verdict,
                is_confirmed=False,
                model_id=model_id,
                symbol=symbol,
                contract_type=contract_type,
                evaluation_time_utc=now_iso,
                manifest_id=manifest.specification_id if manifest else None,
                manifest_checksum=manifest.specification_checksum if manifest else None,
                manifest_verified=manifest_verified,
                confirmation_sessions_count=0,
                confirmation_sessions_reconciled=False,
                nominal_sample_size=0,
                effective_sample_size=0.0,
                observed_win_rate=None,
                mean_predicted_prob=None,
                break_even_hurdle=None,
                quote_coverage_pct=0.0,
                brier_score=None,
                brier_skill_score=None,
                expected_calibration_error=None,
                bootstrap_ci_95=(None, None),
                ordinary_ev=None,
                conservative_ev=None,
                max_drawdown=0.0,
                gate_checks=gate_checks,
                rejection_reasons=reasons
            )

        gate_checks["confirmation_sessions_present"] = True

        # 3. Session Reconciliation & Provenance Audit
        all_reconciled = True
        for s in conf_sessions:
            recon = self.reconciler.reconcile_session(s.session_id)
            if not recon.is_verified:
                all_reconciled = False
                reasons.append(f"Confirmation session {s.session_id} failed reconciliation: {recon.issues}")
        gate_checks["sessions_reconciled"] = all_reconciled

        # 4. Chronological Separation
        if manifest and getattr(manifest, "evaluation_start_boundary", 0.0) > 0:
            chrono_ok = all(
                getattr(s, "start_time", getattr(s, "start_timestamp", 0.0)) >= manifest.evaluation_start_boundary
                for s in conf_sessions
            )
            if not chrono_ok:
                reasons.append("Confirmation sessions contain records preceding the manifest evaluation start boundary.")
            gate_checks["chronological_integrity"] = chrono_ok
        else:
            gate_checks["chronological_integrity"] = True

        # Load confirmation predictions
        conf_session_ids = [s.session_id for s in conf_sessions]
        conf_preds = self._load_predictions_for_sessions(conf_session_ids)
        eligible_preds = [
            p for p in conf_preds
            if p.get("outcome_status") in ("RESOLVED", "RESOLVED_WIN", "RESOLVED_LOSS", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        n_eligible = len(eligible_preds)

        # 5. Sample Size Requirements
        min_obs = manifest.min_confirmation_observations if manifest else 500
        min_eff = manifest.min_effective_sample_size if manifest else 100.0
        min_sess = manifest.min_confirmation_sessions if manifest else 2

        gate_checks["sample_size_adequate"] = (n_eligible >= min_obs)
        gate_checks["stability_adequate"] = (len(conf_sessions) >= min_sess)
        if n_eligible < min_obs:
            reasons.append(f"Insufficient confirmation observations: {n_eligible} resolved vs {min_obs} required.")
        if len(conf_sessions) < min_sess:
            reasons.append(f"Insufficient independent confirmation sessions: {len(conf_sessions)} vs {min_sess} required.")

        # Statistical analysis
        c_dir = contract_type.upper()
        stat_eval = self.stat_evaluator.evaluate_win_rates(eligible_preds)
        c_stat = stat_eval.get("runhigh" if c_dir == "RUNHIGH" else "runlow", {})
        obs_rate = c_stat.get("observed_rate", 0.0)
        mean_pred = c_stat.get("mean_predicted_prob", 0.0)
        brier_s = c_stat.get("brier_score")
        bss = c_stat.get("brier_skill_score")
        ece = c_stat.get("expected_calibration_error")
        n_eff = c_stat.get("effective_sample_size", float(n_eligible))
        boot_ci = c_stat.get("block_bootstrap_ci", (0.0, 0.0))

        gate_checks["effective_sample_adequate"] = (n_eff >= min_eff)
        if n_eff < min_eff:
            reasons.append(f"Effective sample size under serial dependence too low: Neff={n_eff:.1f} vs {min_eff:.1f} required.")

        # 6. Quote Coverage & Economic Viability (STRICTLY NO BENCHMARK FALLBACKS)
        ask_key = "runhigh_ask" if c_dir == "RUNHIGH" else "runlow_ask"
        payout_key = "runhigh_payout" if c_dir == "RUNHIGH" else "runlow_payout"
        enriched_preds = []
        for p in eligible_preds:
            p_dict = dict(p)
            if not p_dict.get(ask_key) or float(p_dict.get(ask_key) or 0) <= 0:
                matched_q = self.quote_db.get_latest_quote_before(
                    symbol=symbol,
                    contract_type=c_dir,
                    timestamp=p_dict.get("timestamp", 0.0),
                    session_id=p_dict.get("session_id"),
                    max_freshness_seconds=manifest.max_quote_freshness_seconds if manifest else 60.0
                )
                if matched_q:
                    p_dict[ask_key] = matched_q.ask_price
                    p_dict[payout_key] = matched_q.total_payout
            enriched_preds.append(p_dict)

        econ_eval = self.econ_evaluator.evaluate_quote_economics(enriched_preds, direction=c_dir)
        quote_cov = econ_eval.get("quote_coverage_pct", 0.0)
        min_cov = manifest.min_quote_coverage_pct if manifest else 95.0

        # CRITICAL V1.7.1 RULE: If quote coverage < 95% or no genuine quotes, FAIL WITH QUOTE_DATA_INSUFFICIENT
        be_hurdle = econ_eval.get("mean_break_even_pct")
        if be_hurdle is not None:
            be_hurdle = be_hurdle / 100.0

        if quote_cov < min_cov or be_hurdle is None:
            gate_checks["quote_coverage_adequate"] = False
            reasons.append(f"QUOTE_DATA_INSUFFICIENT: Quote coverage insufficient: {quote_cov:.1f}% vs {min_cov:.1f}% required (no benchmark fallbacks allowed).")
            # If quote coverage fails on genuine confirmation data, verdict is QUOTE_DATA_INSUFFICIENT
            return ConfirmationGateReport(
                verdict=VERDICT_QUOTE_DATA_INSUFFICIENT,
                is_confirmed=False,
                model_id=model_id,
                symbol=symbol,
                contract_type=contract_type,
                evaluation_time_utc=now_iso,
                manifest_id=manifest.specification_id if manifest else None,
                manifest_checksum=manifest.specification_checksum if manifest else None,
                manifest_verified=manifest_verified,
                confirmation_sessions_count=len(conf_sessions),
                confirmation_sessions_reconciled=all_reconciled,
                nominal_sample_size=n_eligible,
                effective_sample_size=n_eff,
                observed_win_rate=obs_rate if n_eligible > 0 else None,
                mean_predicted_prob=mean_pred if n_eligible > 0 else None,
                break_even_hurdle=None,
                quote_coverage_pct=quote_cov,
                brier_score=brier_s,
                brier_skill_score=bss,
                expected_calibration_error=ece,
                bootstrap_ci_95=boot_ci,
                ordinary_ev=None,
                conservative_ev=None,
                max_drawdown=econ_eval.get("max_drawdown", 0.0),
                gate_checks=gate_checks,
                rejection_reasons=reasons,
                manifest=manifest
            )

        gate_checks["quote_coverage_adequate"] = True

        # 7. Probability Calibration checks
        max_ece = manifest.max_expected_calibration_error if manifest else 0.05
        min_bss = manifest.min_brier_skill_score if manifest else 0.0
        cal_ok = (bss is not None and bss > min_bss) and (ece is not None and ece <= max_ece)
        gate_checks["calibration_valid"] = cal_ok
        if not cal_ok:
            reasons.append(f"CALIBRATION_FAILED: Calibration failed: BSS={bss} (must be > {min_bss}), ECE={ece} (must be <= {max_ece}).")

        # 8. Statistical Significance (z-score against break-even hurdle)
        z_score = 0.0
        if be_hurdle and be_hurdle > 0 and n_eff > 1:
            denom = math.sqrt(be_hurdle * (1.0 - be_hurdle) / n_eff)
            z_score = (obs_rate - be_hurdle) / denom if denom > 1e-9 else 0.0

        min_z = manifest.min_z_score if manifest else 1.96
        stat_sig = (z_score >= min_z) and (boot_ci[0] is not None and boot_ci[0] > be_hurdle)
        gate_checks["statistical_significance"] = stat_sig
        if not stat_sig:
            reasons.append(f"STATISTICAL_SIGNIFICANCE_FAILED: Statistical significance failed: z={z_score:.2f} (required >={min_z}), bootstrap lower bound={boot_ci[0]} vs hurdle={be_hurdle:.5f}.")

        # 9. Ordinary Expected Value
        ord_ev = econ_eval.get("mean_ordinary_ev")
        ord_ok = (ord_ev is not None and ord_ev > 0.0)
        gate_checks["ordinary_ev_positive"] = ord_ok
        if not ord_ok:
            reasons.append(f"Ordinary EV non-positive: {ord_ev}.")

        # 10. Conservative Expected Value (STRICT LOWER BOUND REQUIREMENT)
        # Conservative EV uses the lower bound of the moving block bootstrap CI
        lower_bound = boot_ci[0]
        mean_ask = econ_eval.get("mean_ask")
        mean_payout = econ_eval.get("mean_payout")
        cons_ev = None
        if lower_bound is not None and mean_ask is not None and mean_payout is not None:
            cons_ev = (lower_bound * mean_payout) - mean_ask

        min_c_ev = manifest.min_conservative_ev if manifest else 0.0
        cons_ok = (cons_ev is not None and cons_ev > min_c_ev)
        gate_checks["conservative_ev_positive"] = cons_ok
        if not cons_ok:
            reasons.append(f"CONSERVATIVE_EV_NON_POSITIVE: Conservative EV non-positive or unavailable: {cons_ev} (required > {min_c_ev}).")

        # 11. Risk & Drawdown Limits
        max_dd_limit = manifest.max_hypothetical_drawdown if manifest else 20.0
        actual_dd = econ_eval.get("max_drawdown", 0.0)
        risk_ok = (actual_dd <= max_dd_limit)
        gate_checks["risk_limits_respected"] = risk_ok
        if not risk_ok:
            reasons.append(f"Drawdown limit exceeded: {actual_dd} > {max_dd_limit}.")

        # Authoritative Verdict Resolution
        all_passed = all(gate_checks.values())
        if all_passed:
            verdict = VERDICT_FORWARD_EDGE_CONFIRMED
        elif not cal_ok:
            verdict = VERDICT_CALIBRATION_FAILED
        elif ord_ok and not cons_ok:
            verdict = VERDICT_CONFIRMATION_REJECTED
        elif not stat_sig:
            verdict = "STATISTICAL_SIGNIFICANCE_FAILED"
        elif n_eligible < min_obs or n_eff < min_eff:
            verdict = VERDICT_INSUFFICIENT_FORWARD_DATA
        else:
            verdict = VERDICT_CONFIRMATION_REJECTED

        return ConfirmationGateReport(
            verdict=verdict,
            is_confirmed=all_passed,
            model_id=model_id,
            symbol=symbol,
            contract_type=contract_type,
            evaluation_time_utc=now_iso,
            manifest_id=manifest.specification_id if manifest else None,
            manifest_checksum=manifest.specification_checksum if manifest else None,
            manifest_verified=manifest_verified,
            confirmation_sessions_count=len(conf_sessions),
            confirmation_sessions_reconciled=all_reconciled,
            nominal_sample_size=n_eligible,
            effective_sample_size=n_eff,
            observed_win_rate=obs_rate,
            mean_predicted_prob=mean_pred,
            break_even_hurdle=be_hurdle,
            quote_coverage_pct=quote_cov,
            brier_score=brier_s,
            brier_skill_score=bss,
            expected_calibration_error=ece,
            bootstrap_ci_95=boot_ci,
            ordinary_ev=ord_ev,
            conservative_ev=cons_ev,
            max_drawdown=actual_dd,
            gate_checks=gate_checks,
            rejection_reasons=reasons,
            manifest=manifest
        )


def evaluate_forward_edge_confirmation(
    model_id: str = "LATEST",
    symbol: str = "R_75",
    contract_type: str = "RUNHIGH",
    manifest: Optional[ConfirmationManifest] = None,
    session_registry: Optional[ForwardSessionRegistry] = None,
    quote_db: Optional[QuoteDatabase] = None,
    forward_db_path: Optional[str] = None,
    quote_db_path: Optional[str] = None,
    session_db_path: Optional[str] = None,
    **kwargs
) -> ConfirmationGateReport:
    """Convenience functional interface for authoritative edge confirmation evaluation."""
    if "symbol" in kwargs:
        symbol = kwargs["symbol"]
    if "model_id" in kwargs:
        model_id = kwargs["model_id"]
    if model_id in ("R_75", "R_50", "R_100", "R_10", "R_25") and symbol not in ("R_75", "R_50", "R_100", "R_10", "R_25"):
        model_id, symbol = symbol, model_id

    gate = ForwardConfirmationGate(
        session_registry=session_registry,
        quote_db=quote_db,
        forward_db_path=forward_db_path,
        quote_db_path=quote_db_path,
        session_db_path=session_db_path,
        manifest=manifest
    )
    return gate.evaluate_forward_edge_confirmation(
        model_id=model_id,
        symbol=symbol,
        contract_type=contract_type,
        manifest=manifest
    )

