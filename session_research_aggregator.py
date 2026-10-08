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


# Research Verdict Constants (V1.7 Part I Section 22 & Part L Section 28)
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
        min_confirmation_samples: int = 100
    ):
        self.registry = registry or ForwardSessionRegistry()
        self.journal = journal or ForwardPredictionJournal()
        self.min_confirmation_samples = min_confirmation_samples
        self.stat_evaluator = StatisticalEvaluator(block_size=5, n_bootstraps=500)
        self.econ_evaluator = EconomicEvaluator()

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

        conf_wr = stage_metrics[STAGE_CONFIRMATION]["win_rates"]
        conf_dep = stage_metrics[STAGE_CONFIRMATION]["dependence_runhigh"]
        conf_econ = stage_metrics[STAGE_CONFIRMATION]["economics_runhigh"]

        n_conf_resolved = conf_wr["eligible_resolved_count"]
        n_conf_eff = conf_dep["effective_sample_size"]
        conf_rh_rate = conf_wr["runhigh"]["observed_rate"]
        conf_be_pct = (conf_econ["mean_break_even_pct"] or 3.277) / 100.0

        verdict = VERDICT_INSUFFICIENT_DATA
        verdict_rationale = ""

        if n_conf_resolved >= self.min_confirmation_samples and n_conf_eff >= (self.min_confirmation_samples * 0.5):
            # We have sufficient confirmation data
            if conf_rh_rate > conf_be_pct and (conf_econ["mean_conservative_ev"] or -1.0) > 0:
                verdict = VERDICT_FORWARD_EDGE_CONFIRMED
                verdict_rationale = f"Confirmatory win rate ({conf_rh_rate:.4f}) exceeds break-even ({conf_be_pct:.4f}) with positive conservative EV."
            else:
                verdict = VERDICT_NO_VALIDATED_EDGE
                verdict_rationale = f"Confirmatory win rate ({conf_rh_rate:.4f}) fails to reliably beat proposal hurdle ({conf_be_pct:.4f})."
        elif len(val_preds) >= 50:
            val_rh_rate = stage_metrics[STAGE_VALIDATION]["win_rates"]["runhigh"]["observed_rate"]
            val_be_pct = (stage_metrics[STAGE_VALIDATION]["economics_runhigh"]["mean_break_even_pct"] or 3.277) / 100.0
            if val_rh_rate > val_be_pct:
                verdict = VERDICT_CONFIRMATION_REQUIRED
                verdict_rationale = "Validation dataset shows positive lift. Independent pre-registered confirmation required."
            else:
                verdict = VERDICT_NO_VALIDATED_EDGE
                verdict_rationale = "Validation dataset demonstrates no statistical or economic edge over break-even."
        elif len(expl_preds) > 0:
            expl_rh_rate = stage_metrics[STAGE_EXPLORATORY]["win_rates"]["runhigh"]["observed_rate"]
            verdict = VERDICT_INSUFFICIENT_DATA
            verdict_rationale = f"Current data ({len(expl_preds)} exploratory predictions) is exploratory and insufficient to establish statistical edge."
        else:
            verdict = VERDICT_INSUFFICIENT_DATA
            verdict_rationale = "Zero forward prediction records available for research evaluation."

        return {
            "symbol": symbol,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "verdict_rationale": verdict_rationale,
            "verdict_reasons": [verdict_rationale],
            "stage_metrics": stage_metrics,
            "session_level_stability": session_level_rates,
            "total_independent_sessions": len(session_level_rates)
        }

    def generate_markdown_report(self, report_data: Dict[str, Any]) -> str:
        """Renders comprehensive multi-session research report in GitHub-flavored markdown."""
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
        md.append("\n---\n")

        md.append("## 1. Research Stage Breakdown\n")
        md.append("| Research Stage | Sessions | Predictions | Resolved | RUNHIGH Wins | RUNHIGH Rate | RUNLOW Wins | RUNLOW Rate |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
            wr = m.get("win_rates", {})
            rh = wr.get("runhigh", {})
            rl = wr.get("runlow", {})
            md.append(
                f"| `{stg}` | {m.get('session_count', 0)} | {m.get('prediction_count', 0)} | "
                f"{wr.get('eligible_resolved_count', 0)} | {rh.get('wins', 0)} | "
                f"{rh.get('observed_rate', 0.0):.4f} | {rl.get('wins', 0)} | "
                f"{rl.get('observed_rate', 0.0):.4f} |"
            )

        md.append("\n---\n")
        md.append("## 2. Calibration & Dependence Analysis (RUNHIGH)\n")
        md.append("| Stage | Brier Score | Ref Brier | Brier Skill Score | ECE | N_nominal | N_effective | Bootstrap 95% CI |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
            cal = m.get("calibration_runhigh", {})
            dep = m.get("dependence_runhigh", {})
            bs = cal.get("brier_score")
            ref_bs = cal.get("reference_brier")
            bss = cal.get("brier_skill_score")
            ece = cal.get("expected_calibration_error")
            n_nom = dep.get("nominal_sample_size", 0)
            n_eff = dep.get("effective_sample_size", 0.0)
            b_ci = dep.get("bootstrap_ci_95", (0.0, 0.0))

            md.append(
                f"| `{stg}` | {f'{bs:.5f}' if bs is not None else 'N/A'} | "
                f"{f'{ref_bs:.5f}' if ref_bs is not None else 'N/A'} | "
                f"{f'{bss:.4f}' if bss is not None else 'N/A'} | "
                f"{f'{ece:.4f}' if ece is not None else 'N/A'} | {n_nom} | {n_eff} | "
                f"[{b_ci[0]:.4f}, {b_ci[1]:.4f}] |"
            )

        md.append("\n---\n")
        md.append("## 3. Proposal Economic Viability (RUNHIGH)\n")
        md.append("| Stage | Quote Coverage | Mean Ask | Mean Payout | Break-Even Hurdle | Ordinary EV | Cons. EV | Cumulative PnL |")
        md.append("|---|---|---|---|---|---|---|---|")

        for stg in [STAGE_EXPLORATORY, STAGE_VALIDATION, STAGE_CONFIRMATION]:
            m = metrics.get(stg, {})
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
        md.append(f"> - Additional sustained forward observations are required before evaluating confirmation claims.\n")

        return "\n".join(md)
