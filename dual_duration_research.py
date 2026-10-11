"""Paired Dual-Duration Research and Comparison Engine: 2-Tick vs 5-Tick (V1.7.4.1).

Conducts rigorous, fair, and scientifically grounded comparisons between Deriv
2-tick and 5-tick RUNHIGH (Only Ups) and RUNLOW (Only Downs) contracts on R_75.

Core Research Protocol:
1. Paired Forward Stream: Evaluates 2T and 5T simultaneously on the exact same tick stream.
2. Direction-Specific: RUNHIGH and RUNLOW are evaluated completely independently.
3. Explicit Evidence Classes (V1.7.4.1 Part 3):
   - HISTORICAL_REPLAY: Retrospective replay over existing ticks.
   - HISTORICAL_HOLDOUT: Strictly untouched chronological holdout.
   - PROSPECTIVE_SHADOW: Live predictions journaled prior to observing forward ticks.
   - INDEPENDENT_CONFIRMATION: Registered with ForwardConfirmationGate on untouched stream.
4. Separated Evaluation Modes (V1.7.4.1 Part 2):
   - REFERENCE_SCENARIO: Hypothetical illustrative payouts ($7.63, $61.07); quote coverage is 0%.
   - QUOTE_VERIFIED: Real proposal quotes matched to decisions; verified coverage and lookahead-free.
5. Economic Qualification:
   - Ordinary EV must exceed threshold.
   - Conservative EV (Moving-Block Bootstrap 95% lower bound) must be >= 0.0.
   - Small samples return unavailable conservative EV (None), preventing false qualification.
"""
import collections
from enum import Enum
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from contract_specification import (
    evaluate_canonical_outcome,
    CANONICAL_RUNHIGH_2T_SPEC,
    CANONICAL_RUNLOW_2T_SPEC,
    CANONICAL_RUNHIGH_5T_SPEC,
    CANONICAL_RUNLOW_5T_SPEC
)
from probability import wilson_score_interval


class EvidenceClass(str, Enum):
    """Classification of empirical research evidence."""
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    HISTORICAL_HOLDOUT = "HISTORICAL_HOLDOUT"
    PROSPECTIVE_SHADOW = "PROSPECTIVE_SHADOW"
    INDEPENDENT_CONFIRMATION = "INDEPENDENT_CONFIRMATION"


class EvaluationMode(str, Enum):
    """Mode of economic valuation."""
    REFERENCE_SCENARIO = "REFERENCE_SCENARIO"  # Illustrative hypothetical payouts
    QUOTE_VERIFIED = "QUOTE_VERIFIED"          # Genuine matched proposal quotes


class QuoteEvidenceStatus(str, Enum):
    """Hierarchy of quote evidence classifications (V1.7.4.3 Section 3.5)."""
    CONTRACT_AVAILABLE = "CONTRACT_AVAILABLE"
    PROPOSAL_RECEIVED = "PROPOSAL_RECEIVED"
    QUOTE_CHRONOLOGICALLY_VALID = "QUOTE_CHRONOLOGICALLY_VALID"
    QUOTE_ECONOMICALLY_EVALUABLE = "QUOTE_ECONOMICALLY_EVALUABLE"
    QUOTE_EXECUTION_QUALITY_VERIFIED = "QUOTE_EXECUTION_QUALITY_VERIFIED"
    QUOTE_VALIDITY_UNVERIFIED = "QUOTE_VALIDITY_UNVERIFIED"
    QUOTE_REJECTED = "QUOTE_REJECTED"


class ResearchEdgeLadder(str, Enum):
    """Authoritative Positive-EV Evidence Ladder (V1.7.4.3 Section 9)."""
    NO_VALIDATED_POSITIVE_EV_EDGE = "NO_VALIDATED_POSITIVE_EV_EDGE"                 # Level 0
    EXPLORATORY_POSITIVE_EV_SIGNAL = "EXPLORATORY_POSITIVE_EV_SIGNAL"               # Level 1
    QUOTE_VERIFIED_RESEARCH_CANDIDATE = "QUOTE_VERIFIED_RESEARCH_CANDIDATE"         # Level 2
    CONFIRMATION_REGISTERED = "CONFIRMATION_REGISTERED"                             # Level 3
    POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED = "POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED" # Level 4


@dataclass
class DurationMetricSummary:
    """Comprehensive performance and economic metrics for a specific duration & direction."""
    duration: int                         # 2 or 5
    direction: str                        # 'RUNHIGH' or 'RUNLOW'
    contract_label: str                   # '2T_RUNHIGH', '5T_RUNLOW', etc.
    total_predictions: int
    resolved_outcomes: int
    wins: int
    losses: int
    empirical_win_rate: float
    mean_predicted_prob: float
    calibration_error_ece: float
    brier_score: float
    brier_skill_score: float
    break_even_hurdle: float
    stake: float
    total_payout: float
    ordinary_ev: Optional[float]                    # Ordinary EV based on model prediction (or realized if model unavailable)
    ordinary_ev_per_dollar: Optional[float]
    predicted_ordinary_ev: Optional[float]
    retrospective_realized_return: Optional[float]  # Realized hypothetical return per contract: (Wins * Payout - N * Stake) / N
    conservative_ev_bootstrap: Optional[float]      # 95% MBB lower bound (None if insufficient data)
    bootstrap_uncertainty_status: str               # 'SUFFICIENT_SAMPLE' or 'INSUFFICIENT_SAMPLE'
    bootstrap_sensitivity_summary: Dict[str, Optional[float]]
    win_rate_ci_95: Tuple[float, float]
    raw_quote_coverage_pct: float
    chronological_quote_coverage_pct: float
    economic_quote_coverage_pct: float
    execution_quality_coverage_pct: float
    quote_availability_pct: float                   # Verified quote coverage (0.0 in REFERENCE_SCENARIO)
    evaluation_mode: str                            # REFERENCE_SCENARIO or QUOTE_VERIFIED
    evidence_class: str                             # HISTORICAL_REPLAY, etc.
    is_economically_positive: bool                  # True iff ord_ev > 0 AND cons_ev >= 0
    verdict: str
    mean_actual_ask_price: Optional[float] = None
    mean_actual_payout: Optional[float] = None
    mean_actual_break_even: Optional[float] = None
    break_even_distribution: Optional[Dict[str, float]] = None
    eligible_quote_decisions_count: int = 0
    missing_ev_count: int = 0
    quote_rejection_reasons: Dict[str, int] = field(default_factory=dict)
    total_decision_points: int = 0
    total_quotes_collected: int = 0
    missing_quote_count: int = 0
    future_quote_count: int = 0
    missing_timestamp_count: int = 0
    stale_quote_count: int = 0
    wrong_symbol_count: int = 0
    wrong_direction_count: int = 0
    wrong_duration_count: int = 0
    wrong_currency_count: int = 0
    wrong_session_count: int = 0
    ambiguous_proposal_count: int = 0
    invalidated_quote_count: int = 0
    quote_validity_unverified_count: int = 0


@dataclass
class DualDurationComparisonReport:
    """Comparative synthesis of 2-tick vs 5-tick performance on the same market stream."""
    symbol: str
    stream_tick_count: int
    decision_points_count: int
    metrics: Dict[str, DurationMetricSummary]
    economic_ranking: List[str]
    winning_candidate: Optional[str]
    selection_bias_warning: str
    recommendation: str
    evidence_class: str = EvidenceClass.HISTORICAL_REPLAY.value
    evaluation_mode: str = EvaluationMode.REFERENCE_SCENARIO.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stream_tick_count": self.stream_tick_count,
            "decision_points_count": self.decision_points_count,
            "evidence_class": self.evidence_class,
            "evaluation_mode": self.evaluation_mode,
            "metrics": {k: v.__dict__ for k, v in self.metrics.items()},
            "economic_ranking": self.economic_ranking,
            "winning_candidate": self.winning_candidate,
            "selection_bias_warning": self.selection_bias_warning,
            "recommendation": self.recommendation
        }


class DualDurationEvaluator:
    """Evaluates paired 2T and 5T contracts across identical market ticks."""

    def __init__(
        self,
        symbol: str = "R_75",
        stake: float = 2.00,
        payout_2t: float = 7.63,
        payout_5t: float = 61.07,
        bootstrap_iterations: int = 500,
        bootstrap_block_size: int = 5,
        min_ordinary_ev: float = 0.0,
        min_conservative_ev: float = 0.0
    ):
        self.symbol = symbol
        self.stake = stake
        self.payout_2t = payout_2t
        self.payout_5t = payout_5t
        self.bootstrap_iterations = bootstrap_iterations
        self.bootstrap_block_size = bootstrap_block_size
        self.min_ordinary_ev = min_ordinary_ev
        self.min_conservative_ev = min_conservative_ev

    def evaluate_ticks(
        self,
        prices: List[float],
        timestamps: Optional[List[float]] = None,
        model_2t: Optional[Any] = None,
        model_5t: Optional[Any] = None,
        evidence_class: EvidenceClass = EvidenceClass.HISTORICAL_REPLAY,
        evaluation_mode: EvaluationMode = EvaluationMode.REFERENCE_SCENARIO,
        quote_records: Optional[List[Any]] = None,
        min_ordinary_ev: Optional[float] = None,
        min_conservative_ev: Optional[float] = None,
        session_manifest: Optional[Dict[str, Any]] = None,
        prospective_journal_records: Optional[List[Any]] = None,
        expected_session_id: Optional[str] = None,
        tick_records: Optional[List[Any]] = None
    ) -> DualDurationComparisonReport:
        """Evaluates all 4 configurations (2T RH, 2T RL, 5T RH, 5T RL) on the price series."""
        n = len(prices)
        if n < 35:
            raise ValueError(f"Insufficient ticks for dual duration evaluation: {n} < 35 required.")

        # Section 4.1: Structural separation of replay and forward modes (Evidence Authority)
        effective_evidence_class = evidence_class
        evidence_authority_warning = None
        if evidence_class in (EvidenceClass.PROSPECTIVE_SHADOW, EvidenceClass.INDEPENDENT_CONFIRMATION):
            if not prospective_journal_records or not session_manifest:
                effective_evidence_class = EvidenceClass.HISTORICAL_REPLAY
                evidence_authority_warning = (
                    f"EVIDENCE AUTHORITY FAIL-CLOSED: External claim '{evidence_class.value}' rejected. "
                    "Historical price arrays cannot self-certify as prospective evidence without authentic pre-outcome "
                    "journal records and verified session manifest."
                )

        min_ord = self.min_ordinary_ev if min_ordinary_ev is None else min_ordinary_ev
        min_cons = self.min_conservative_ev if min_conservative_ev is None else min_conservative_ev

        # Canonical hurdles
        hurdle_2t = self.stake / self.payout_2t  # ~0.26212
        hurdle_5t = self.stake / self.payout_5t  # ~0.03275

        # Track outcomes
        outcomes_2t_rh: List[float] = []
        outcomes_2t_rl: List[float] = []
        outcomes_5t_rh: List[float] = []
        outcomes_5t_rl: List[float] = []

        probs_2t_rh: List[float] = []
        probs_2t_rl: List[float] = []
        probs_5t_rh: List[float] = []
        probs_5t_rl: List[float] = []

        decision_timestamps: List[float] = []

        # Decision point i requires lookback of 25 ticks and 6 forward ticks (for 5T)
        decision_points = 0
        for i in range(25, n - 6):
            decision_points += 1
            t_curr = timestamps[i] if (timestamps is not None and i < len(timestamps)) else float(i)
            decision_timestamps.append(t_curr)

            # 2T evaluation: prices at [i+1, i+2, i+3] (S_0, S_1, S_2)
            p_2t = prices[i+1 : i+4]
            rh_2t_win = 1.0 if (p_2t[1] > p_2t[0] and p_2t[2] > p_2t[1]) else 0.0
            rl_2t_win = 1.0 if (p_2t[1] < p_2t[0] and p_2t[2] < p_2t[1]) else 0.0
            outcomes_2t_rh.append(rh_2t_win)
            outcomes_2t_rl.append(rl_2t_win)

            # 5T evaluation: prices at [i+1, ... i+7] (S_0 ... S_5)
            p_5t = prices[i+1 : i+7]
            rh_5t_win = 1.0 if all(p_5t[k] > p_5t[k-1] for k in range(1, 6)) else 0.0
            rl_5t_win = 1.0 if all(p_5t[k] < p_5t[k-1] for k in range(1, 6)) else 0.0
            outcomes_5t_rh.append(rh_5t_win)
            outcomes_5t_rl.append(rl_5t_win)

            # Model probabilities if available, else theoretical baseline
            if model_2t is not None and hasattr(model_2t, "predict_probabilities"):
                from feature_schema import extract_discrete_market_state
                window_df = pd.DataFrame({"price": prices[max(0, i-50) : i+1]})
                _, st = extract_discrete_market_state(window_df)
                p_rh, p_rl, _ = model_2t.predict_probabilities(st)
                probs_2t_rh.append(p_rh)
                probs_2t_rl.append(p_rl)
            else:
                probs_2t_rh.append(0.25)
                probs_2t_rl.append(0.25)

            if model_5t is not None and hasattr(model_5t, "predict_probabilities"):
                from feature_schema import extract_discrete_market_state
                window_df = pd.DataFrame({"price": prices[max(0, i-50) : i+1]})
                _, st = extract_discrete_market_state(window_df)
                p_rh, p_rl, _ = model_5t.predict_probabilities(st)
                probs_5t_rh.append(p_rh)
                probs_5t_rl.append(p_rl)
            else:
                probs_5t_rh.append(0.03125)
                probs_5t_rl.append(0.03125)

        configs = [
            ("2T_RUNHIGH", 2, "RUNHIGH", outcomes_2t_rh, probs_2t_rh, self.payout_2t, hurdle_2t),
            ("2T_RUNLOW",  2, "RUNLOW",  outcomes_2t_rl, probs_2t_rl, self.payout_2t, hurdle_2t),
            ("5T_RUNHIGH", 5, "RUNHIGH", outcomes_5t_rh, probs_5t_rh, self.payout_5t, hurdle_5t),
            ("5T_RUNLOW",  5, "RUNLOW",  outcomes_5t_rl, probs_5t_rl, self.payout_5t, hurdle_5t),
        ]

        metrics_dict: Dict[str, DurationMetricSummary] = {}
        for label, dur, direct, y_true, y_prob, payout, hurdle in configs:
            summary = self._compute_metrics(
                label=label,
                duration=dur,
                direction=direct,
                outcomes=y_true,
                pred_probs=y_prob,
                payout=payout,
                hurdle=hurdle,
                evidence_class=effective_evidence_class,
                evaluation_mode=evaluation_mode,
                decision_timestamps=decision_timestamps,
                quote_records=quote_records,
                min_ordinary_ev=min_ord,
                min_conservative_ev=min_cons,
                expected_session_id=expected_session_id,
                tick_records=tick_records
            )
            metrics_dict[label] = summary

        # Rank strictly by ordinary expected value per dollar
        sorted_labels = sorted(
            metrics_dict.keys(),
            key=lambda k: (
                metrics_dict[k].ordinary_ev_per_dollar
                if metrics_dict[k].ordinary_ev_per_dollar is not None
                else -float("inf")
            ),
            reverse=True
        )

        top = sorted_labels[0]
        top_summary = metrics_dict[top]
        winning = top if top_summary.is_economically_positive else None

        bias_text = (
            "PREVENTING SELECTION BIAS: Do NOT select the winning duration based on win rate. "
            "2-tick contracts win ~25% vs 5-tick contracts ~3%, but 2-tick payouts are ~8x smaller ($7.63 vs $61.07). "
            f"Evidence Class: {effective_evidence_class.value}. Evaluation Mode: {evaluation_mode.value}. "
            "Any candidate selected on exploratory data must be frozen and confirmed on untouched future sessions."
        )
        warning = f"{evidence_authority_warning} {bias_text}" if evidence_authority_warning else bias_text

        ord_ev_str = f"${top_summary.ordinary_ev:+.4f}" if top_summary.ordinary_ev is not None else "UNAVAILABLE"
        cons_ev_str = f"{top_summary.conservative_ev_bootstrap}" if top_summary.conservative_ev_bootstrap is not None else "UNAVAILABLE"
        rec = (
            f"Top Ranked: {top} with Ordinary EV/stake {ord_ev_str}. "
            f"Economically viable: {top_summary.is_economically_positive} (conservative EV: {cons_ev_str}). "
            f"Verdict: {top_summary.verdict}. All tested configurations remain non-trading (NO_TRADE invariant enforced)."
        )

        return DualDurationComparisonReport(
            symbol=self.symbol,
            stream_tick_count=n,
            decision_points_count=decision_points,
            metrics=metrics_dict,
            economic_ranking=sorted_labels,
            winning_candidate=winning,
            selection_bias_warning=warning,
            recommendation=rec,
            evidence_class=effective_evidence_class.value,
            evaluation_mode=evaluation_mode.value
        )

    def _compute_metrics(
        self,
        label: str,
        duration: int,
        direction: str,
        outcomes: List[float],
        pred_probs: List[float],
        payout: float,
        hurdle: float,
        evidence_class: EvidenceClass,
        evaluation_mode: EvaluationMode,
        decision_timestamps: List[float],
        quote_records: Optional[List[Any]],
        min_ordinary_ev: float = 0.0,
        min_conservative_ev: float = 0.0,
        expected_session_id: Optional[str] = None,
        tick_records: Optional[List[Any]] = None
    ) -> DurationMetricSummary:
        n = len(outcomes)
        wins = int(sum(outcomes))
        losses = n - wins
        emp_win_rate = (wins / n) if n > 0 else 0.0

        mean_prob = float(np.mean(pred_probs)) if pred_probs else 0.0

        # Calibration Error (ECE - 5 equal bins)
        ece = self._compute_ece(outcomes, pred_probs, n_bins=5)

        # Brier Score & BSS
        bs = float(np.mean([(p - y)**2 for p, y in zip(pred_probs, outcomes)])) if n > 0 else 0.0
        bs_ref = float(np.mean([(emp_win_rate - y)**2 for y in outcomes])) if n > 0 else 0.0
        bss = float(1.0 - (bs / bs_ref)) if bs_ref > 0 else 0.0

        # Wilson 95% Confidence Interval for win rate
        ci_lo, ci_hi = wilson_score_interval(wins, n, confidence=0.95)

        tot_quotes = len(quote_records) if quote_records else 0

        # Separate REFERENCE_SCENARIO and QUOTE_VERIFIED paths strictly (V1.7.4.2 Part B & C)
        if evaluation_mode == EvaluationMode.REFERENCE_SCENARIO:
            # REFERENCE_SCENARIO: All results are illustrative. Quote coverage is strictly 0%.
            # Verified quote-specific EV is unavailable. Reference scenarios CAN NEVER qualify for trading.
            predicted_ord_ev = (mean_prob * payout) - self.stake
            retrospective_return = ((wins * payout) - (n * self.stake)) / n if n > 0 else 0.0
            ordinary_ev = predicted_ord_ev
            ord_ev_per_dollar = ordinary_ev / self.stake if self.stake > 0 else 0.0

            block_size = max(2, duration + 1)
            cons_ev, unc_status, sens_dict = self._moving_block_bootstrap_ev(
                outcomes=outcomes,
                payout=payout,
                stake=self.stake,
                block_size=block_size,
                iterations=self.bootstrap_iterations,
                percentile=5.0,
                seed=42
            )

            has_positive_ord = ordinary_ev > min_ordinary_ev
            has_positive_cons = (cons_ev is not None) and (cons_ev >= min_conservative_ev)
            has_sufficient_samples = (unc_status == "SUFFICIENT_SAMPLE")

            # Reference scenarios can NEVER receive verified economic qualification!
            is_pos = False

            if unc_status == "INSUFFICIENT_SAMPLE":
                verdict = "INSUFFICIENT_UNCERTAINTY_EVIDENCE"
            elif not has_positive_ord:
                verdict = "NEGATIVE_ORDINARY_EV"
            elif not has_positive_cons:
                verdict = "FAILED_CONSERVATIVE_HURDLE"
            else:
                verdict = "REFERENCE_SCENARIO_ONLY"

            return DurationMetricSummary(
                duration=duration,
                direction=direction,
                contract_label=label,
                total_predictions=n,
                resolved_outcomes=n,
                wins=wins,
                losses=losses,
                empirical_win_rate=round(emp_win_rate, 5),
                mean_predicted_prob=round(mean_prob, 5),
                calibration_error_ece=round(ece, 5),
                brier_score=round(bs, 5),
                brier_skill_score=round(bss, 5),
                break_even_hurdle=round(hurdle, 5),
                stake=self.stake,
                total_payout=payout,
                ordinary_ev=round(ordinary_ev, 4),
                ordinary_ev_per_dollar=round(ord_ev_per_dollar, 4),
                predicted_ordinary_ev=round(predicted_ord_ev, 4),
                retrospective_realized_return=round(retrospective_return, 4),
                conservative_ev_bootstrap=round(cons_ev, 4) if cons_ev is not None else None,
                bootstrap_uncertainty_status=unc_status,
                bootstrap_sensitivity_summary=sens_dict,
                win_rate_ci_95=(round(ci_lo, 5), round(ci_hi, 5)),
                raw_quote_coverage_pct=0.0,
                chronological_quote_coverage_pct=0.0,
                economic_quote_coverage_pct=0.0,
                execution_quality_coverage_pct=0.0,
                quote_availability_pct=0.0,
                evaluation_mode=evaluation_mode.value,
                evidence_class=evidence_class.value,
                is_economically_positive=False,
                verdict=verdict,
                mean_actual_ask_price=None,
                mean_actual_payout=None,
                mean_actual_break_even=None,
                break_even_distribution=None,
                eligible_quote_decisions_count=0,
                missing_ev_count=n,
                quote_rejection_reasons={"REFERENCE_SCENARIO": n},
                total_decision_points=n,
                total_quotes_collected=tot_quotes,
                missing_quote_count=n,
                future_quote_count=0,
                missing_timestamp_count=0,
                stale_quote_count=0,
                wrong_symbol_count=0,
                wrong_direction_count=0,
                wrong_duration_count=0,
                wrong_currency_count=0,
                wrong_session_count=0,
                ambiguous_proposal_count=0,
                invalidated_quote_count=0,
                quote_validity_unverified_count=0
            )

        # QUOTE_VERIFIED mode: Per-decision matching using actual ask prices and payouts
        matched_quotes, cov_pcts, rej_reasons = self._match_quotes_per_decision(
            duration=duration,
            direction=direction,
            decision_timestamps=decision_timestamps,
            quote_records=quote_records,
            expected_session_id=expected_session_id,
            tick_records=tick_records
        )

        raw_cov = cov_pcts["raw"]
        chrono_cov = cov_pcts["chrono"]
        econ_cov = cov_pcts["econ"]
        exec_cov = cov_pcts["exec"]
        quote_avail_pct = exec_cov

        wrong_sym = rej_reasons.get("QUOTE_MISSING_SYMBOL", 0) + rej_reasons.get("QUOTE_WRONG_SYMBOL", 0)
        wrong_dir = rej_reasons.get("QUOTE_WRONG_DIRECTION", 0)
        wrong_dur = rej_reasons.get("QUOTE_WRONG_DURATION", 0)
        wrong_curr = rej_reasons.get("QUOTE_CURRENCY_MISMATCH", 0) + rej_reasons.get("QUOTE_MISSING_CURRENCY", 0)
        wrong_sess = rej_reasons.get("QUOTE_WRONG_SESSION", 0)
        fut_q = rej_reasons.get("QUOTE_LOOKAHEAD_REJECTED", 0)
        miss_ts = rej_reasons.get("QUOTE_RESPONSE_TIME_MISSING", 0)
        stale_q = rej_reasons.get("QUOTE_STALE", 0)
        inval_q = rej_reasons.get("QUOTE_INVALIDATED_BY_INTERVENING_TICK", 0)
        ambig_q = rej_reasons.get("QUOTE_AMBIGUOUS_PROPOSAL", 0)
        miss_q = rej_reasons.get("NO_QUOTES_PROVIDED", 0) + rej_reasons.get("QUOTE_NO_CANDIDATES", 0)
        unverif_q = rej_reasons.get("QUOTE_VALIDITY_UNVERIFIED", 0)

        eligible_indices = [idx for idx, q in enumerate(matched_quotes) if q is not None]
        m = len(eligible_indices)

        if m == 0:
            # If no genuine eligible quotes exist, mark quote-verified EV as unavailable (None)
            # Do NOT assign zero EV to missing evidence!
            return DurationMetricSummary(
                duration=duration,
                direction=direction,
                contract_label=label,
                total_predictions=n,
                resolved_outcomes=n,
                wins=wins,
                losses=losses,
                empirical_win_rate=round(emp_win_rate, 5),
                mean_predicted_prob=round(mean_prob, 5),
                calibration_error_ece=round(ece, 5),
                brier_score=round(bs, 5),
                brier_skill_score=round(bss, 5),
                break_even_hurdle=round(hurdle, 5),
                stake=self.stake,
                total_payout=payout,
                ordinary_ev=None,
                ordinary_ev_per_dollar=None,
                predicted_ordinary_ev=None,
                retrospective_realized_return=None,
                conservative_ev_bootstrap=None,
                bootstrap_uncertainty_status="INSUFFICIENT_SAMPLE",
                bootstrap_sensitivity_summary={},
                win_rate_ci_95=(round(ci_lo, 5), round(ci_hi, 5)),
                raw_quote_coverage_pct=round(raw_cov, 2),
                chronological_quote_coverage_pct=round(chrono_cov, 2),
                economic_quote_coverage_pct=round(econ_cov, 2),
                execution_quality_coverage_pct=round(exec_cov, 2),
                quote_availability_pct=round(quote_avail_pct, 2),
                evaluation_mode=evaluation_mode.value,
                evidence_class=evidence_class.value,
                is_economically_positive=False,
                verdict="INSUFFICIENT_QUOTE_COVERAGE",
                mean_actual_ask_price=None,
                mean_actual_payout=None,
                mean_actual_break_even=None,
                break_even_distribution=None,
                eligible_quote_decisions_count=0,
                missing_ev_count=n,
                quote_rejection_reasons=rej_reasons,
                total_decision_points=n,
                total_quotes_collected=tot_quotes,
                missing_quote_count=miss_q,
                future_quote_count=fut_q,
                missing_timestamp_count=miss_ts,
                stale_quote_count=stale_q,
                wrong_symbol_count=wrong_sym,
                wrong_direction_count=wrong_dir,
                wrong_duration_count=wrong_dur,
                wrong_currency_count=wrong_curr,
                wrong_session_count=wrong_sess,
                ambiguous_proposal_count=ambig_q,
                invalidated_quote_count=inval_q,
                quote_validity_unverified_count=unverif_q
            )

        # Genuine per-decision calculation over eligible matched decisions
        asks = [matched_quotes[idx]["ask_price"] for idx in eligible_indices]
        payouts = [matched_quotes[idx]["total_payout"] for idx in eligible_indices]
        bes = [matched_quotes[idx]["break_even"] for idx in eligible_indices]
        probs = [pred_probs[idx] for idx in eligible_indices]
        y_eligible = [outcomes[idx] for idx in eligible_indices]

        # EV_i = P_model_i * TotalPayout_i - AskPrice_i
        per_decision_ev = [(probs[k] * payouts[k]) - asks[k] for k in range(m)]
        # Return_i = (y_i * TotalPayout_i) - AskPrice_i
        per_decision_realized = [(y_eligible[k] * payouts[k]) - asks[k] for k in range(m)]

        mean_ask = float(np.mean(asks))
        mean_payout = float(np.mean(payouts))
        mean_be = float(np.mean(bes))
        be_dist = {
            "min": round(float(np.min(bes)), 5),
            "median": round(float(np.median(bes)), 5),
            "max": round(float(np.max(bes)), 5),
            "std": round(float(np.std(bes)), 5)
        }

        ordinary_ev = float(np.mean(per_decision_ev))
        ord_ev_per_dollar = ordinary_ev / mean_ask if mean_ask > 0 else 0.0
        predicted_ord_ev = ordinary_ev
        retrospective_return = float(np.mean(per_decision_realized))

        # Dependence-aware Moving-Block Bootstrap over actual per-decision realized returns
        block_size = max(2, duration + 1)
        cons_ev, unc_status, sens_dict = self._moving_block_bootstrap_quote_ev(
            returns=per_decision_realized,
            block_size=block_size,
            iterations=self.bootstrap_iterations,
            percentile=5.0,
            seed=42
        )

        has_positive_ord = (ordinary_ev is not None) and (ordinary_ev > min_ordinary_ev)
        has_positive_cons = (cons_ev is not None) and (cons_ev >= min_conservative_ev)
        has_sufficient_samples = (unc_status == "SUFFICIENT_SAMPLE")
        has_valid_quotes = (quote_avail_pct >= 90.0)

        is_pos = has_positive_ord and has_positive_cons and has_sufficient_samples and has_valid_quotes

        if unc_status == "INSUFFICIENT_SAMPLE":
            verdict = "INSUFFICIENT_EVIDENCE"
        elif not has_valid_quotes:
            verdict = "INSUFFICIENT_QUOTE_COVERAGE"
        elif not has_positive_ord:
            verdict = "FAILED_ECONOMIC_HURDLE"
        elif not has_positive_cons:
            verdict = "FAILED_CONSERVATIVE_HURDLE"
        else:
            verdict = "QUOTE_VERIFIED_RESEARCH_CANDIDATE"

        return DurationMetricSummary(
            duration=duration,
            direction=direction,
            contract_label=label,
            total_predictions=n,
            resolved_outcomes=n,
            wins=wins,
            losses=losses,
            empirical_win_rate=round(emp_win_rate, 5),
            mean_predicted_prob=round(mean_prob, 5),
            calibration_error_ece=round(ece, 5),
            brier_score=round(bs, 5),
            brier_skill_score=round(bss, 5),
            break_even_hurdle=round(hurdle, 5),
            stake=round(mean_ask, 2),
            total_payout=round(mean_payout, 2),
            ordinary_ev=round(ordinary_ev, 4),
            ordinary_ev_per_dollar=round(ord_ev_per_dollar, 4),
            predicted_ordinary_ev=round(predicted_ord_ev, 4),
            retrospective_realized_return=round(retrospective_return, 4),
            conservative_ev_bootstrap=round(cons_ev, 4) if cons_ev is not None else None,
            bootstrap_uncertainty_status=unc_status,
            bootstrap_sensitivity_summary=sens_dict,
            win_rate_ci_95=(round(ci_lo, 5), round(ci_hi, 5)),
            raw_quote_coverage_pct=round(raw_cov, 2),
            chronological_quote_coverage_pct=round(chrono_cov, 2),
            economic_quote_coverage_pct=round(econ_cov, 2),
            execution_quality_coverage_pct=round(exec_cov, 2),
            quote_availability_pct=round(quote_avail_pct, 2),
            evaluation_mode=evaluation_mode.value,
            evidence_class=evidence_class.value,
            is_economically_positive=is_pos,
            verdict=verdict,
            mean_actual_ask_price=round(mean_ask, 4),
            mean_actual_payout=round(mean_payout, 4),
            mean_actual_break_even=round(mean_be, 5),
            break_even_distribution=be_dist,
            eligible_quote_decisions_count=m,
            missing_ev_count=n - m,
            quote_rejection_reasons=rej_reasons,
            total_decision_points=n,
            total_quotes_collected=tot_quotes,
            missing_quote_count=miss_q,
            future_quote_count=fut_q,
            missing_timestamp_count=miss_ts,
            stale_quote_count=stale_q,
            wrong_symbol_count=wrong_sym,
            wrong_direction_count=wrong_dir,
            wrong_duration_count=wrong_dur,
            wrong_currency_count=wrong_curr,
            wrong_session_count=wrong_sess,
            ambiguous_proposal_count=ambig_q,
            invalidated_quote_count=inval_q,
            quote_validity_unverified_count=unverif_q
        )

    def _match_quotes_per_decision(
        self,
        duration: int,
        direction: str,
        decision_timestamps: List[float],
        quote_records: Optional[List[Any]],
        max_freshness_seconds: float = 60.0,
        expected_session_id: Optional[str] = None,
        tick_records: Optional[List[Any]] = None,
        max_intervening_ticks: int = 2
    ) -> Tuple[List[Optional[Dict[str, Any]]], Dict[str, float], Dict[str, int]]:
        """Matches an individually identifiable, chronological quote record to each decision point.
        
        Strict Quote Matching Rules (V1.7.4.3 Section 3):
        - Verified database identity: quote_record_id, proposal_id, or persistent id
        - Same market symbol (self.symbol) - missing symbol fails closed
        - Same contract duration (duration)
        - Same contract direction (direction) - missing type fails closed
        - Explicit currency ('USD') - missing currency fails closed
        - Valid ask price and payout: ask > 0, payout > 0, ask < payout
        - Strict causality: response_timestamp <= decision_timestamp (zero lookahead tolerance)
        - Freshness: (decision_timestamp - response_timestamp) <= max_freshness_seconds
        - Session attribution: matches expected_session_id if provided
        - Tick-aware invalidation: quotes invalidated by intervening market movements
        """
        n = len(decision_timestamps)
        if n == 0:
            return [], {"raw": 0.0, "chrono": 0.0, "econ": 0.0, "exec": 0.0}, {}

        if not quote_records:
            return [None] * n, {"raw": 0.0, "chrono": 0.0, "econ": 0.0, "exec": 0.0}, {"NO_QUOTES_PROVIDED": n}

        matched_list: List[Optional[Dict[str, Any]]] = []
        raw_valid = 0
        chrono_valid = 0
        econ_valid = 0
        exec_valid = 0
        rejection_reasons: Dict[str, int] = collections.defaultdict(int)

        norm_dir = direction.upper()
        dir_aliases = (norm_dir, "UP" if norm_dir == "RUNHIGH" else "DOWN", "RISE" if norm_dir == "RUNHIGH" else "FALL")

        for t_dec in decision_timestamps:
            # 1. Match symbol, duration, direction, currency, identity, session
            candidates = []
            cand_rejections = []
            for q in quote_records:
                # Identity check
                q_id = getattr(q, "quote_record_id", None) or getattr(q, "id", None) or getattr(q, "proposal_id", None)
                if not q_id or str(q_id).strip() == "" or str(q_id).strip().upper() == "NONE":
                    cand_rejections.append("QUOTE_ID_MISSING")
                    continue

                # Symbol check (fail-closed: missing symbol must NEVER default to R_75)
                raw_sym = getattr(q, "market_symbol", None) or getattr(q, "symbol", None)
                if not raw_sym or str(raw_sym).strip() == "":
                    cand_rejections.append("QUOTE_MISSING_SYMBOL")
                    continue
                q_sym = str(raw_sym).strip().upper()
                if q_sym != self.symbol.upper():
                    cand_rejections.append("QUOTE_WRONG_SYMBOL")
                    continue

                # Currency check (fail-closed: missing currency must NEVER default to USD)
                raw_curr = getattr(q, "currency", None)
                if not raw_curr or str(raw_curr).strip() == "":
                    cand_rejections.append("QUOTE_MISSING_CURRENCY")
                    continue
                q_curr = str(raw_curr).strip().upper()
                if q_curr != "USD":
                    cand_rejections.append("QUOTE_CURRENCY_MISMATCH")
                    continue

                # Duration check
                q_dur = getattr(q, "contract_duration", None)
                if q_dur is None or q_dur != duration:
                    cand_rejections.append("QUOTE_WRONG_DURATION")
                    continue

                # Direction check
                raw_type = getattr(q, "contract_type", None)
                if not raw_type or str(raw_type).strip() == "":
                    cand_rejections.append("QUOTE_WRONG_DIRECTION")
                    continue
                q_type = str(raw_type).strip().upper()
                if q_type not in dir_aliases:
                    cand_rejections.append("QUOTE_WRONG_DIRECTION")
                    continue

                # Session check (if expected_session_id is specified)
                if expected_session_id is not None:
                    q_sess = getattr(q, "session_id", None)
                    s_exp = str(expected_session_id).strip()
                    s_act = str(q_sess).strip() if q_sess else ""
                    if not s_act or not (s_act == s_exp or s_act.startswith(s_exp) or s_exp.startswith(s_act)):
                        cand_rejections.append("QUOTE_WRONG_SESSION")
                        continue

                candidates.append(q)

            if candidates:
                raw_valid += 1
            else:
                rejection_reasons["QUOTE_WRONG_CONTRACT_OR_SYMBOL"] += 1
                for r in cand_rejections:
                    rejection_reasons[r] += 1
                matched_list.append(None)
                continue

            # 2. Chronological filter: response_timestamp <= t_dec (zero lookahead tolerance)
            chrono_candidates = [
                q for q in candidates
                if getattr(q, "response_timestamp", None) is not None
                and not math.isnan(getattr(q, "response_timestamp", float("nan")))
                and getattr(q, "response_timestamp", float("inf")) <= t_dec
            ]
            if chrono_candidates:
                chrono_valid += 1
            else:
                has_future = any(
                    getattr(q, "response_timestamp", None) is not None and getattr(q, "response_timestamp", 0.0) > t_dec
                    for q in candidates
                )
                if has_future:
                    rejection_reasons["QUOTE_LOOKAHEAD_REJECTED"] += 1
                else:
                    rejection_reasons["QUOTE_RESPONSE_TIME_MISSING"] += 1
                matched_list.append(None)
                continue

            # 3. Economic filter: ask > 0, payout > 0, ask < payout
            econ_candidates = []
            for q in chrono_candidates:
                ask = getattr(q, "ask_price", getattr(q, "stake", 0.0))
                payout = getattr(q, "total_payout", 0.0)
                status = getattr(q, "collection_status", "QUOTE_AVAILABLE")
                if ask > 0 and payout > 0 and ask < payout and status == "QUOTE_AVAILABLE":
                    econ_candidates.append(q)

            if econ_candidates:
                econ_valid += 1
            else:
                rejection_reasons["QUOTE_PRICE_OR_PAYOUT_INVALID"] += 1
                matched_list.append(None)
                continue

            # 4. Execution quality filter: freshness <= max_freshness_seconds
            exec_candidates = [
                q for q in econ_candidates
                if (t_dec - getattr(q, "response_timestamp", 0.0)) <= max_freshness_seconds
            ]
            if not exec_candidates:
                rejection_reasons["QUOTE_STALE"] += 1
                matched_list.append(None)
                continue

            # 5. Check proposal ambiguity (duplicate proposal records at the exact same timestamp with conflicting asks/payouts)
            resp_dict = {}
            has_ambiguity = False
            for q in exec_candidates:
                pid = getattr(q, "proposal_id", None)
                r_ts = getattr(q, "response_timestamp", None)
                if pid and r_ts is not None:
                    q_ask = float(getattr(q, "ask_price", getattr(q, "stake", 0.0)))
                    q_pay = float(getattr(q, "total_payout", 0.0))
                    key = (pid, round(float(r_ts), 4))
                    if key in resp_dict:
                        prev_ask, prev_pay = resp_dict[key]
                        if abs(prev_ask - q_ask) > 1e-4 or abs(prev_pay - q_pay) > 1e-4:
                            has_ambiguity = True
                            break
                    else:
                        resp_dict[key] = (q_ask, q_pay)
            if has_ambiguity:
                rejection_reasons["QUOTE_AMBIGUOUS_PROPOSAL"] += 1
                matched_list.append(None)
                continue

            # Select the most recent quote received prior to decision
            best_q = max(exec_candidates, key=lambda q: getattr(q, "response_timestamp", 0.0))
            b_resp = float(getattr(best_q, "response_timestamp", 0.0))

            # 6. Tick-aware Invalidation / Market Continuity Check (Section 3.4)
            if tick_records:
                intervening = [
                    t for t in tick_records
                    if getattr(t, "epoch", getattr(t, "timestamp", 0.0)) > b_resp
                    and getattr(t, "epoch", getattr(t, "timestamp", 0.0)) <= t_dec
                ]
                quote_spot = None
                meta_str = getattr(best_q, "api_response_metadata", "")
                if meta_str:
                    try:
                        m_obj = json.loads(meta_str)
                        quote_spot = m_obj.get("spot")
                    except Exception:
                        quote_spot = None

                invalidated = False
                if quote_spot is not None and intervening:
                    for t in intervening:
                        p_t = getattr(t, "price", None)
                        if p_t is not None and abs(p_t - float(quote_spot)) > 1e-5:
                            invalidated = True
                            break

                if not invalidated and len(intervening) > max_intervening_ticks:
                    invalidated = True

                if invalidated:
                    rejection_reasons["QUOTE_INVALIDATED_BY_INTERVENING_TICK"] += 1
                    rejection_reasons["QUOTE_VALIDITY_UNVERIFIED"] += 1
                    matched_list.append(None)
                    continue

            exec_valid += 1
            b_ask = float(getattr(best_q, "ask_price", getattr(best_q, "stake", 0.0)))
            b_pay = float(getattr(best_q, "total_payout", 0.0))
            matched_list.append({
                "decision_timestamp": t_dec,
                "quote_id": str(getattr(best_q, "quote_record_id", None) or getattr(best_q, "proposal_id", "") or getattr(best_q, "id", "")),
                "response_timestamp": b_resp,
                "ask_price": b_ask,
                "total_payout": b_pay,
                "break_even": b_ask / b_pay,
                "age_seconds": t_dec - b_resp,
                "quote_source": getattr(best_q, "quote_source", "live_proposal")
            })

        cov_pcts = {
            "raw": (raw_valid / n) * 100.0,
            "chrono": (chrono_valid / n) * 100.0,
            "econ": (econ_valid / n) * 100.0,
            "exec": (exec_valid / n) * 100.0
        }
        return matched_list, cov_pcts, dict(rejection_reasons)

    def _compute_quote_coverage(
        self,
        duration: int,
        direction: str,
        decision_timestamps: List[float],
        quote_records: Optional[List[Any]],
        evaluation_mode: EvaluationMode
    ) -> Tuple[float, float, float, float]:
        """Calculates granular quote coverage against decision timestamps."""
        if evaluation_mode == EvaluationMode.REFERENCE_SCENARIO or not quote_records:
            return 0.0, 0.0, 0.0, 0.0
        _, cov_pcts, _ = self._match_quotes_per_decision(
            duration=duration,
            direction=direction,
            decision_timestamps=decision_timestamps,
            quote_records=quote_records
        )
        return cov_pcts["raw"], cov_pcts["chrono"], cov_pcts["econ"], cov_pcts["exec"]

    def _compute_ece(self, outcomes: List[float], pred_probs: List[float], n_bins: int = 5) -> float:
        """Expected Calibration Error across equal probability bins."""
        if not outcomes or not pred_probs:
            return 0.0
        y = np.array(outcomes)
        p = np.array(pred_probs)
        bins = np.linspace(0.0, max(0.5, float(np.max(p))), n_bins + 1)

        ece = 0.0
        total_n = len(y)
        for b_lo, b_hi in zip(bins[:-1], bins[1:]):
            mask = (p >= b_lo) & (p <= b_hi)
            bin_n = np.sum(mask)
            if bin_n > 0:
                acc = np.mean(y[mask])
                conf = np.mean(p[mask])
                ece += (bin_n / total_n) * abs(acc - conf)
        return float(ece)

    def _moving_block_bootstrap_quote_ev(
        self,
        returns: List[float],
        block_size: int,
        iterations: int = 500,
        percentile: float = 5.0,
        seed: int = 42
    ) -> Tuple[Optional[float], str, Dict[str, Optional[float]]]:
        """Computes dependence-aware lower percentile of quote-verified EV using moving-block bootstrap.
        
        Strict Uncertainty Guard (V1.7.4.2 Part B Section 6 & Part E Section 18):
        Operates on actual per-decision realized returns (y_i * Payout_i - Ask_i).
        If n < max(30, block_size * 2), returns unavailable (None).
        """
        n = len(returns)
        if n < max(30, block_size * 2):
            return None, "INSUFFICIENT_SAMPLE", {}

        arr = np.array(returns)
        num_blocks = n - block_size + 1
        blocks = [arr[j : j + block_size] for j in range(num_blocks)]
        blocks_needed = int(math.ceil(n / block_size))

        rng = np.random.default_rng(seed=seed)

        ev_samples = []
        for _ in range(iterations):
            sampled_block_indices = rng.integers(0, num_blocks, size=blocks_needed)
            sample_arr = np.concatenate([blocks[idx] for idx in sampled_block_indices])[:n]
            sample_mean = float(np.mean(sample_arr))
            ev_samples.append(sample_mean)

        cons_ev = float(np.percentile(ev_samples, percentile))

        # Sensitivity analysis across alternative block sizes
        sens_dict: Dict[str, Optional[float]] = {}
        alt_sizes = [max(2, block_size - 1), block_size, block_size + 3]
        for alt_bs in set(alt_sizes):
            if alt_bs == block_size:
                sens_dict[f"block_{alt_bs}"] = round(cons_ev, 4)
            else:
                if n >= alt_bs * 2:
                    alt_blocks = [arr[j : j + alt_bs] for j in range(n - alt_bs + 1)]
                    alt_needed = int(math.ceil(n / alt_bs))
                    alt_samples = []
                    for _ in range(iterations):
                        s_idx = rng.integers(0, len(alt_blocks), size=alt_needed)
                        s_arr = np.concatenate([alt_blocks[idx] for idx in s_idx])[:n]
                        alt_samples.append(float(np.mean(s_arr)))
                    sens_dict[f"block_{alt_bs}"] = round(float(np.percentile(alt_samples, percentile)), 4)
                else:
                    sens_dict[f"block_{alt_bs}"] = None

        return cons_ev, "SUFFICIENT_SAMPLE", sens_dict

    def _moving_block_bootstrap_ev(
        self,
        outcomes: List[float],
        payout: float,
        stake: float,
        block_size: int,
        iterations: int = 500,
        percentile: float = 5.0,
        seed: int = 42
    ) -> Tuple[Optional[float], str, Dict[str, Optional[float]]]:
        """Computes dependence-aware lower percentile of reference EV using moving-block bootstrap.
        
        Strict Uncertainty Guard (V1.7.4.1 Part 2 Section 2.5):
        If n < block_size * 2 or n < 30, conservative bound is UNAVAILABLE (None).
        Never substitutes empirical point estimate as conservative bound!
        """
        n = len(outcomes)
        if n < max(30, block_size * 2):
            return None, "INSUFFICIENT_SAMPLE", {}

        arr = np.array(outcomes)
        num_blocks = n - block_size + 1
        blocks = [arr[j : j + block_size] for j in range(num_blocks)]
        blocks_needed = int(math.ceil(n / block_size))

        rng = np.random.default_rng(seed=seed)

        ev_samples = []
        for _ in range(iterations):
            sampled_block_indices = rng.integers(0, num_blocks, size=blocks_needed)
            sample_arr = np.concatenate([blocks[idx] for idx in sampled_block_indices])[:n]
            sample_win_rate = np.mean(sample_arr)
            sample_ev = (sample_win_rate * payout) - stake
            ev_samples.append(sample_ev)

        cons_ev = float(np.percentile(ev_samples, percentile))

        # Sensitivity analysis across alternative block sizes (Section 2.6)
        sens_dict: Dict[str, Optional[float]] = {}
        alt_sizes = [max(2, block_size - 1), block_size, block_size + 3]
        for alt_bs in set(alt_sizes):
            if alt_bs == block_size:
                sens_dict[f"block_{alt_bs}"] = round(cons_ev, 4)
            else:
                if n >= alt_bs * 2:
                    alt_blocks = [arr[j : j + alt_bs] for j in range(n - alt_bs + 1)]
                    alt_needed = int(math.ceil(n / alt_bs))
                    alt_samples = []
                    for _ in range(iterations):
                        s_idx = rng.integers(0, len(alt_blocks), size=alt_needed)
                        s_arr = np.concatenate([alt_blocks[idx] for idx in s_idx])[:n]
                        alt_samples.append((np.mean(s_arr) * payout) - stake)
                    sens_dict[f"block_{alt_bs}"] = round(float(np.percentile(alt_samples, percentile)), 4)
                else:
                    sens_dict[f"block_{alt_bs}"] = None

        return cons_ev, "SUFFICIENT_SAMPLE", sens_dict

    def evaluate_prospective_session(
        self,
        session_id: str,
        manifest_path: Optional[str] = None,
        journal_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
        tick_records: Optional[List[Any]] = None
    ) -> DualDurationComparisonReport:
        """Evaluates a completed or active prospective session with authentic records.
        
        Loads:
        1. Predictions from SQLite forward_predictions.db
        2. Quotes from SQLite quotes.db
        3. Session manifest from sessions.db or JSON manifest file
        4. Validates pre-outcome journaling and strict quote provenance.
        """
        import sqlite3
        from forward_session import DEFAULT_SESSIONS_DB, ForwardSessionRegistry
        from session_reconciler import DEFAULT_FORWARD_DB, DEFAULT_QUOTES_DB

        j_path = journal_db_path or DEFAULT_FORWARD_DB
        q_path = quote_db_path or DEFAULT_QUOTES_DB

        # Resolve full session_id if short prefix passed
        target_sid = session_id
        if len(session_id) < 32 and os.path.exists(j_path):
            conn_temp = sqlite3.connect(j_path)
            try:
                row_sid = conn_temp.execute(
                    "SELECT session_id FROM forward_predictions WHERE session_id LIKE ? LIMIT 1",
                    (f"{session_id}%",)
                ).fetchone()
                if row_sid:
                    target_sid = row_sid[0]
            finally:
                conn_temp.close()

        # 1. Load predictions
        preds = []
        if os.path.exists(j_path):
            conn = sqlite3.connect(j_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT * FROM forward_predictions WHERE session_id = ? ORDER BY timestamp ASC",
                    (target_sid,)
                ).fetchall()
                preds = [dict(r) for r in rows]
            finally:
                conn.close()

        # 2. Load quotes
        quotes = []
        if os.path.exists(q_path):
            from quote_database import QuoteDatabase
            q_db = QuoteDatabase(db_path=q_path)
            quotes = q_db.get_session_quotes(target_sid)

        # 3. Load session manifest
        manifest = None
        if manifest_path and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = None
        if not manifest:
            try:
                registry = ForwardSessionRegistry()
                sess = registry.get_session(target_sid)
                if sess:
                    manifest = sess.to_dict()
            except Exception:
                manifest = None

        # Fail-closed evidence classification
        if not preds or not manifest:
            evidence_class = EvidenceClass.HISTORICAL_REPLAY
        else:
            evidence_class = EvidenceClass.PROSPECTIVE_SHADOW

        # If predictions exist, extract outcomes and timestamps
        preds_2t = [p for p in preds if p.get("contract_duration") == 2]
        preds_5t = [p for p in preds if p.get("contract_duration") == 5]

        # Extract timestamps
        dec_ts_2t = [p["timestamp"] for p in preds_2t if "timestamp" in p]
        dec_ts_5t = [p["timestamp"] for p in preds_5t if "timestamp" in p]

        # Construct outcomes and probabilities
        def extract_series(pred_subset, direction):
            y_true = []
            y_prob = []
            for p in pred_subset:
                out_high = p.get("outcome_runhigh")
                out_low = p.get("outcome_runlow")
                if direction == "RUNHIGH":
                    y_true.append(1.0 if out_high == 1 else 0.0)
                    y_prob.append(float(p.get("prob_runhigh") or (0.25 if p.get("contract_duration") == 2 else 0.03125)))
                else:
                    y_true.append(1.0 if out_low == 1 else 0.0)
                    y_prob.append(float(p.get("prob_runlow") or (0.25 if p.get("contract_duration") == 2 else 0.03125)))
            return y_true, y_prob

        outcomes_2t_rh, probs_2t_rh = extract_series(preds_2t, "RUNHIGH")
        outcomes_2t_rl, probs_2t_rl = extract_series(preds_2t, "RUNLOW")
        outcomes_5t_rh, probs_5t_rh = extract_series(preds_5t, "RUNHIGH")
        outcomes_5t_rl, probs_5t_rl = extract_series(preds_5t, "RUNLOW")

        hurdle_2t = self.stake / self.payout_2t if self.payout_2t > 0 else 0.0
        hurdle_5t = self.stake / self.payout_5t if self.payout_5t > 0 else 0.0

        configs = [
            ("2T_RUNHIGH", 2, "RUNHIGH", outcomes_2t_rh, probs_2t_rh, self.payout_2t, hurdle_2t, dec_ts_2t),
            ("2T_RUNLOW",  2, "RUNLOW",  outcomes_2t_rl, probs_2t_rl, self.payout_2t, hurdle_2t, dec_ts_2t),
            ("5T_RUNHIGH", 5, "RUNHIGH", outcomes_5t_rh, probs_5t_rh, self.payout_5t, hurdle_5t, dec_ts_5t),
            ("5T_RUNLOW",  5, "RUNLOW",  outcomes_5t_rl, probs_5t_rl, self.payout_5t, hurdle_5t, dec_ts_5t),
        ]

        metrics_dict: Dict[str, DurationMetricSummary] = {}
        for label, dur, direct, y_true, y_prob, payout, hurdle, ts_list in configs:
            summary = self._compute_metrics(
                label=label,
                duration=dur,
                direction=direct,
                outcomes=y_true,
                pred_probs=y_prob,
                payout=payout,
                hurdle=hurdle,
                evidence_class=evidence_class,
                evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
                decision_timestamps=ts_list,
                quote_records=quotes,
                min_ordinary_ev=self.min_ordinary_ev,
                min_conservative_ev=self.min_conservative_ev,
                expected_session_id=target_sid,
                tick_records=tick_records
            )
            metrics_dict[label] = summary

        sorted_labels = sorted(
            metrics_dict.keys(),
            key=lambda k: (
                metrics_dict[k].ordinary_ev_per_dollar
                if metrics_dict[k].ordinary_ev_per_dollar is not None
                else -float("inf")
            ),
            reverse=True
        )

        top = sorted_labels[0]
        top_summary = metrics_dict[top]
        winning = top if top_summary.is_economically_positive else None

        rec = (
            f"Prospective Session: {session_id}. Top Ranked: {top}. "
            f"Economically viable: {top_summary.is_economically_positive}. "
            f"Verdict: {top_summary.verdict}. Real-money trading remains permanently disabled."
        )

        return DualDurationComparisonReport(
            symbol=self.symbol,
            stream_tick_count=len(preds),
            decision_points_count=len(preds),
            metrics=metrics_dict,
            economic_ranking=sorted_labels,
            winning_candidate=winning,
            selection_bias_warning=(
                f"Prospective evaluation for session {session_id}. "
                f"Evidence Class: {evidence_class.value}. Evaluation Mode: QUOTE_VERIFIED."
            ),
            recommendation=rec,
            evidence_class=evidence_class.value,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED.value
        )

