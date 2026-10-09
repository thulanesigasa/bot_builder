"""Multi-Session Research Aggregator & Forward Confirmation Engine (V1.7 Part G & I).

Aggregates forward market evidence across multiple independent observation sessions
while strictly preserving their individual boundaries and research stage designations:
  - EXPLORATORY_FORWARD: Used for software verification, initial observation, and feature diagnostics.
  - VALIDATION_FORWARD: Used for out-of-sample tuning and parameter sanity validation.
  - CONFIRMATION_FORWARD: Pre-registered, untouched forward evaluation of frozen models.

Prevents data snooping by keeping confirmation sessions segregated from exploratory data.
Calculates session-to-session stability, cross-session win rates, and determines the
authoritative research verdict.
"""
import os
import json
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from forward_session import (
    ForwardSessionRegistry,
    ForwardSession,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION,
    VALID_RESEARCH_STAGES
)
from forward_journal import ForwardPredictionJournal
from statistical_evaluator import StatisticalEvaluator
from economic_evaluator import EconomicEvaluator
from research_metrics_engine import ResearchMetricsEngine
from config import DEFAULT_CONFIG


# Research Verdict Constants (V1.7.1 Part D & Part L Section 29)
VERDICT_NO_CONFIRMATION_SESSIONS = "NO_CONFIRMATION_SESSIONS"
VERDICT_QUOTE_DATA_INSUFFICIENT = "QUOTE_DATA_INSUFFICIENT"
VERDICT_CALIBRATION_FAILED = "CALIBRATION_FAILED"
VERDICT_CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_FORWARD_DATA"
VERDICT_NO_VALIDATED_EDGE = "NO_VALIDATED_EDGE"
VERDICT_EXPLORATORY_CANDIDATE = "EXPLORATORY_CANDIDATE"
VERDICT_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
VERDICT_FORWARD_EDGE_CONFIRMED = "FORWARD_EDGE_CONFIRMED"


class SessionResearchAggregator:
    """Aggregates independent sessions and evaluates confirmatory statistical edge."""

    def __init__(
        self,
        registry: Optional[ForwardSessionRegistry] = None,
        journal: Optional[ForwardPredictionJournal] = None,
        min_confirmation_samples: int = 100,
        session_registry_db: Optional[str] = None,
        forward_journal_db: Optional[str] = None,
        quote_db: Optional[Any] = None
    ):
        if registry:
            self.registry = registry
        elif session_registry_db:
            self.registry = ForwardSessionRegistry(db_path=session_registry_db)
        else:
            self.registry = ForwardSessionRegistry()

        if journal:
            self.journal = journal
        elif forward_journal_db:
            self.journal = ForwardPredictionJournal(db_path=forward_journal_db)
        else:
            self.journal = ForwardPredictionJournal()

        self.session_registry_db = session_registry_db or getattr(self.registry, "db_path", "data/forward_sessions.db")
        self.forward_journal_db = forward_journal_db or getattr(self.journal, "db_path", "data/forward_predictions.db")
        self.quote_db_path = getattr(quote_db, "db_path", quote_db) if quote_db else DEFAULT_CONFIG.quotes_db_path
        self.manifest = None
        self.confirmation_gate = None
        self.stat_evaluator = StatisticalEvaluator()
        self.econ_evaluator = EconomicEvaluator()
        self.min_confirmation_samples = min_confirmation_samples
        self.metrics_engine = ResearchMetricsEngine(
            forward_db_path=self.forward_journal_db,
            quote_db_path=self.quote_db_path,
            session_db_path=self.session_registry_db
        )

    def load_session_dataset(
        self,
        symbol: Optional[str] = None,
        stages: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Loads and segregates all sessions and their predictions by research stage."""
        all_sessions = self.registry.list_sessions(symbol=symbol, limit=200)
        target_stages = set(stages) if stages else VALID_RESEARCH_STAGES

        sessions_by_stage: Dict[str, List[ForwardSession]] = {
            STAGE_EXPLORATORY: [],
            STAGE_VALIDATION: [],
            STAGE_CONFIRMATION: []
        }

        preds_by_stage: Dict[str, List[Dict[str, Any]]] = {
            STAGE_EXPLORATORY: [],
            STAGE_VALIDATION: [],
            STAGE_CONFIRMATION: []
        }

        for sess in all_sessions:
            stage = getattr(sess, "research_stage", STAGE_EXPLORATORY)
            if stage not in sessions_by_stage:
                stage = STAGE_EXPLORATORY
            if stage in target_stages:
                sessions_by_stage[stage].append(sess)
                sess_preds = self.journal.get_session_predictions(sess.session_id)
                preds_by_stage[stage].extend(sess_preds)

        return {
            "sessions_by_stage": sessions_by_stage,
            "predictions_by_stage": preds_by_stage,
            "total_sessions": len(all_sessions)
        }

    def evaluate_multi_session_research(
        self,
        symbol: str = "R_75"
    ) -> Dict[str, Any]:
        """Conducts comprehensive multi-session statistical edge assessment across all stages."""
        dataset = self.load_session_dataset(symbol=symbol)
        sess_stage = dataset["sessions_by_stage"]
        preds_stage = dataset["predictions_by_stage"]

        stage_metrics: Dict[str, Any] = {}
        all_eligible_preds: List[Dict[str, Any]] = []

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            p_list = preds_stage[stg]
            all_eligible_preds.extend(p_list)
            
            wr_res = self.stat_evaluator.evaluate_win_rates(p_list)
            cal_rh = self.stat_evaluator.evaluate_calibration(p_list, direction="RUNHIGH")
            cal_rl = self.stat_evaluator.evaluate_calibration(p_list, direction="RUNLOW")
            dep_rh = self.stat_evaluator.evaluate_dependence_aware_uncertainty(p_list, direction="RUNHIGH")
            econ_rh = self.econ_evaluator.evaluate_quote_economic_performance(p_list, direction="RUNHIGH")
            econ_rl = self.econ_evaluator.evaluate_quote_economic_performance(p_list, direction="RUNLOW")

            stage_metrics[stg] = {
                "session_count": len(sess_stage[stg]),
                "prediction_count": len(p_list),
                "win_rates": wr_res,
                "calibration_runhigh": cal_rh,
                "calibration_runlow": cal_rl,
                "dependence_runhigh": dep_rh,
                "economics_runhigh": econ_rh,
                "economics_runlow": econ_rl,
            }

        # Evaluate cross-session stability
        session_level_rates: List[Dict[str, Any]] = []
        for stg, s_list in sess_stage.items():
            for s in s_list:
                s_preds = self.journal.get_session_predictions(s.session_id)
                wr = self.stat_evaluator.evaluate_win_rates(s_preds)
                session_level_rates.append({
                    "session_id": s.session_id,
                    "stage": stg,
                    "date": s.start_datetime_utc[:10],
                    "eligible": wr["eligible_resolved_count"],
                    "runhigh_wins": wr["runhigh"]["wins"],
                    "runhigh_rate": wr["runhigh"]["observed_rate"],
                    "runlow_wins": wr["runlow"]["wins"],
                    "runlow_rate": wr["runlow"]["observed_rate"]
                })

        # Authoritative Research Verdict Determination
        conf_preds = preds_stage[STAGE_CONFIRMATION]
        val_preds = preds_stage[STAGE_VALIDATION]
        expl_preds = preds_stage[STAGE_EXPLORATORY]
        conf_sessions_count = len(sess_stage[STAGE_CONFIRMATION])

        conf_wr = stage_metrics[STAGE_CONFIRMATION]["win_rates"]
        conf_dep = stage_metrics[STAGE_CONFIRMATION]["dependence_runhigh"]
        conf_econ = stage_metrics[STAGE_CONFIRMATION]["economics_runhigh"]

        n_conf_resolved = conf_wr["eligible_resolved_count"]
        n_conf_eff = conf_dep["effective_sample_size"]
        conf_rh_rate = conf_wr["runhigh"]["observed_rate"]

        # V1.7.1 RULE: STRICTLY NO BENCHMARK FALLBACKS
        conf_be_pct = conf_econ.get("mean_break_even_pct")
        if conf_be_pct is not None:
            conf_be_pct = conf_be_pct / 100.0

        verdict = VERDICT_INSUFFICIENT_DATA
        verdict_rationale = ""
        verdict_reasons = []
        confirmation_gate_report = None

        if conf_sessions_count == 0:
            # Defect C Fix: Distinguish absent confirmation sessions from completed zero-win study
            if len(val_preds) >= 50:
                val_rh_rate = stage_metrics[STAGE_VALIDATION]["win_rates"]["runhigh"]["observed_rate"]
                val_be_pct = stage_metrics[STAGE_VALIDATION]["economics_runhigh"].get("mean_break_even_pct")
                if val_be_pct is not None:
                    val_be_pct = val_be_pct / 100.0
                    if val_rh_rate > val_be_pct:
                        verdict = VERDICT_CONFIRMATION_REQUIRED
                        verdict_rationale = "Validation dataset shows positive lift. Independent pre-registered confirmation study is required."
                        verdict_reasons.append(verdict_rationale)
                    else:
                        verdict = VERDICT_NO_VALIDATED_EDGE
                        verdict_rationale = "Validation dataset demonstrates no statistical or economic edge over break-even."
                        verdict_reasons.append(verdict_rationale)
                else:
                    verdict = VERDICT_CONFIRMATION_REQUIRED
                    verdict_rationale = "Validation dataset evaluated, but confirmation sessions have not yet been conducted."
                    verdict_reasons.append(verdict_rationale)
            elif len(expl_preds) > 0:
                verdict = VERDICT_NO_CONFIRMATION_SESSIONS
                verdict_rationale = f"Zero independent sessions registered under CONFIRMATION_FORWARD stage ({len(expl_preds)} exploratory predictions available)."
                verdict_reasons.append(verdict_rationale)
            else:
                verdict = VERDICT_INSUFFICIENT_DATA
                verdict_rationale = "Zero forward prediction records available for research evaluation."
                verdict_reasons.append(verdict_rationale)
        else:
            # UNIFIED CONFIRMATION AUTHORITY (V1.7.2 Defect B Fix):
            # SessionResearchAggregator delegates confirmed-edge decisions exclusively
            # to ForwardConfirmationGate. No weaker bypass exists.
            from forward_confirmation_gate import ForwardConfirmationGate
            gate = self.confirmation_gate or ForwardConfirmationGate(
                forward_db_path=self.forward_journal_db,
                quote_db_path=self.quote_db_path,
                session_db_path=self.session_registry_db,
                manifest=self.manifest
            )
            gate_rep = gate.evaluate(symbol=symbol)
            verdict = gate_rep.verdict
            verdict_rationale = "; ".join(gate_rep.rejection_reasons) if not gate_rep.is_confirmed else "Authoritative confirmation gate passed all 13 mandatory categories."
            verdict_reasons = gate_rep.rejection_reasons
            confirmation_gate_report = gate_rep.to_dict()

        # Compute dataset integrity checksum
        all_s_ids = [s.session_id for s_list in sess_stage.values() for s in s_list]
        dataset_checksum = self.metrics_engine.compute_integrity_checksum(all_eligible_preds, all_s_ids, symbol)

        return {
            "symbol": symbol,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "verdict_rationale": verdict_rationale,
            "verdict_reasons": verdict_reasons,
            "stage_metrics": stage_metrics,
            "session_level_stability": session_level_rates,
            "total_independent_sessions": len(session_level_rates),
            "integrity_checksum": dataset_checksum,
            "confirmation_gate_report": confirmation_gate_report
        }

    def generate_markdown_report(self, report_data: Any) -> str:
        """Renders comprehensive multi-session research report in GitHub-flavored markdown."""
        if isinstance(report_data, str):
            report_data = self.evaluate_multi_session_research(symbol=report_data)
        symbol = report_data["symbol"]
        ts = report_data["generated_at_utc"]
        verdict = report_data["verdict"]
        rationale = report_data["verdict_rationale"]
        metrics = report_data["stage_metrics"]

        md = []
        md.append(f"# Multi-Session Forward Research & Confirmation Report — {symbol}")
        md.append(f"**Generated:** {ts}  ")
        md.append(f"**Research Verdict:** `{verdict}`  ")
        md.append(f"**Rationale:** {rationale}  ")
        if report_data.get("integrity_checksum"):
            md.append(f"**Dataset Integrity Checksum:** `{report_data['integrity_checksum']}`  ")
        md.append("\n---\n")

        md.append("## 1. Research Stage Breakdown\n")
        md.append("| Research Stage | Sessions | Predictions | Resolved | RUNHIGH Wins | RUNHIGH Rate | RUNLOW Wins | RUNLOW Rate |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
            sess_cnt = m.get("session_count", 0)
            wr = m.get("win_rates", {})
            rh = wr.get("runhigh", {})
            rl = wr.get("runlow", {})

            # Defect C Fix: Distinguish absent confirmation study from completed zero-win study
            if sess_cnt == 0:
                md.append(
                    f"| `{stg}` | 0 | 0 | 0 | N/A | N/A (No Sessions) | N/A | N/A (No Sessions) |"
                )
            else:
                rh_rate_str = f"{rh.get('observed_rate', 0.0):.4f}" if rh.get('observed_rate') is not None else "N/A"
                rl_rate_str = f"{rl.get('observed_rate', 0.0):.4f}" if rl.get('observed_rate') is not None else "N/A"
                md.append(
                    f"| `{stg}` | {sess_cnt} | {m.get('prediction_count', 0)} | "
                    f"{wr.get('eligible_resolved_count', 0)} | {rh.get('wins', 0)} | "
                    f"{rh_rate_str} | {rl.get('wins', 0)} | "
                    f"{rl_rate_str} |"
                )

        md.append("\n---\n")
        md.append("## 2. Calibration & Dependence Analysis (RUNHIGH)\n")
        md.append("| Stage | Brier Score | Ref Brier | Brier Skill Score | ECE | N_nominal | N_effective | Bootstrap 95% CI |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
            sess_cnt = m.get("session_count", 0)
            if sess_cnt == 0:
                md.append(f"| `{stg}` | N/A | N/A | N/A | N/A | 0 | 0.0 | [N/A, N/A] |")
                continue

            cal = m.get("calibration_runhigh", {})
            dep = m.get("dependence_runhigh", {})
            bs = cal.get("brier_score")
            ref_bs = cal.get("reference_brier")
            bss = cal.get("brier_skill_score")
            ece = cal.get("expected_calibration_error")
            n_nom = dep.get("nominal_sample_size", 0)
            n_eff = dep.get("effective_sample_size", 0.0)
            b_ci = dep.get("bootstrap_ci_95", (None, None))

            ci_str = f"[{b_ci[0]:.4f}, {b_ci[1]:.4f}]" if b_ci[0] is not None and b_ci[1] is not None else "[N/A, N/A]"

            md.append(
                f"| `{stg}` | {f'{bs:.5f}' if bs is not None else 'N/A'} | "
                f"{f'{ref_bs:.5f}' if ref_bs is not None else 'N/A'} | "
                f"{f'{bss:.4f}' if bss is not None else 'N/A'} | "
                f"{f'{ece:.4f}' if ece is not None else 'N/A'} | {n_nom} | {n_eff} | "
                f"{ci_str} |"
            )

        md.append("\n---\n")
        md.append("## 3. Proposal Economic Viability (RUNHIGH)\n")
        md.append("| Stage | Quote Coverage | Mean Ask | Mean Payout | Break-Even Hurdle | Ordinary EV | Cons. EV | Cumulative PnL |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
            sess_cnt = m.get("session_count", 0)
            if sess_cnt == 0:
                md.append(f"| `{stg}` | N/A | N/A | N/A | N/A | N/A | N/A | N/A |")
                continue

            ec = m.get("economics_runhigh", {})
            cov = ec.get("quote_coverage_pct", 0.0)
            ask = ec.get("mean_ask")
            payout = ec.get("mean_payout")
            be = ec.get("mean_break_even_pct")
            ord_ev = ec.get("mean_ordinary_ev")
            c_ev = ec.get("mean_conservative_ev")
            pnl = ec.get("hypothetical_cumulative_pnl", 0.0)

            md.append(
                f"| `{stg}` | {cov:.1f}% | {f'${ask:.2f}' if ask else 'N/A'} | "
                f"{f'${payout:.2f}' if payout else 'N/A'} | "
                f"{f'{be:.3f}%' if be else 'N/A'} | "
                f"{f'${ord_ev:.3f}' if ord_ev is not None else 'N/A'} | "
                f"{f'${c_ev:.3f}' if c_ev is not None else 'N/A'} | ${pnl:.2f} |"
            )

        md.append("\n---\n")
        md.append("## 4. Final Research Verdict & Recommendation\n")
        md.append(f"> **Verdict**: `{verdict}`\n")
        md.append(f"> **Operational Directives**:\n")
        md.append(f"> - Real-money trading remains permanently disabled (`LIVE_EXECUTION_DISABLED = True`).\n")
        md.append(f"> - Model artifacts remain restricted to research mode (`RESEARCH_ONLY`).\n")
        md.append(f"> - Independent confirmation sessions are mandatory before evaluating any edge confirmation claim.\n")

        return "\n".join(md)

