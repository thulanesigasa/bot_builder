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
        min_conservative_ev: Optional[float] = None
    ) -> DualDurationComparisonReport:
        """Evaluates all 4 configurations (2T RH, 2T RL, 5T RH, 5T RL) on the price series."""
        n = len(prices)
        if n < 35:
            raise ValueError(f"Insufficient ticks for dual duration evaluation: {n} < 35 required.")

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
                evidence_class=evidence_class,
                evaluation_mode=evaluation_mode,
                decision_timestamps=decision_timestamps,
                quote_records=quote_records,
                min_ordinary_ev=min_ord,
                min_conservative_ev=min_cons
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

        warning = (
            "PREVENTING SELECTION BIAS: Do NOT select the winning duration based on win rate. "
            "2-tick contracts win ~25% vs 5-tick contracts ~3%, but 2-tick payouts are ~8x smaller ($7.63 vs $61.07). "
            f"Evidence Class: {evidence_class.value}. Evaluation Mode: {evaluation_mode.value}. "
            "Any candidate selected on exploratory data must be frozen and confirmed on untouched future sessions."
        )

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
            evidence_class=evidence_class.value,
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
        min_conservative_ev: float = 0.0
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
                quote_rejection_reasons={"REFERENCE_SCENARIO": n}
            )

        # QUOTE_VERIFIED mode: Per-decision matching using actual ask prices and payouts
        matched_quotes, cov_pcts, rej_reasons = self._match_quotes_per_decision(
            duration=duration,
            direction=direction,
            decision_timestamps=decision_timestamps,
            quote_records=quote_records
        )

        raw_cov = cov_pcts["raw"]
        chrono_cov = cov_pcts["chrono"]
        econ_cov = cov_pcts["econ"]
        exec_cov = cov_pcts["exec"]
        quote_avail_pct = exec_cov

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
                quote_rejection_reasons=rej_reasons
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
            quote_rejection_reasons=rej_reasons
        )

    def _match_quotes_per_decision(
        self,
        duration: int,
        direction: str,
        decision_timestamps: List[float],
        quote_records: Optional[List[Any]],
        max_freshness_seconds: float = 60.0
    ) -> Tuple[List[Optional[Dict[str, Any]]], Dict[str, float], Dict[str, int]]:
        """Matches an individually identifiable, chronological quote record to each decision point.
        
        Strict Quote Matching Rules (V1.7.4.2 Part B):
        - Same market symbol (self.symbol)
        - Same contract duration (duration)
        - Same contract direction (direction)
        - Valid currency ('USD')
        - Valid ask price and payout: ask > 0, payout > 0, ask < payout
        - Chronological response receipt: response_timestamp <= decision_timestamp (zero lookahead tolerance)
        - Freshness: (decision_timestamp - response_timestamp) <= max_freshness_seconds
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
            # 1. Match symbol, duration, direction, currency
            candidates = []
            for q in quote_records:
                q_dur = getattr(q, "contract_duration", None)
                q_type = str(getattr(q, "contract_type", "")).upper()
                q_sym = str(getattr(q, "market_symbol", "") or getattr(q, "symbol", "")).upper()
                q_curr = str(getattr(q, "currency", "USD")).upper()

                if q_sym and q_sym != self.symbol.upper():
                    continue
                if q_dur != duration:
                    continue
                if q_type not in dir_aliases:
                    continue
                if q_curr != "USD":
                    continue
                candidates.append(q)

            if candidates:
                raw_valid += 1
            else:
                rejection_reasons["QUOTE_WRONG_CONTRACT_OR_SYMBOL"] += 1
                matched_list.append(None)
                continue

            # 2. Chronological filter: response_timestamp <= t_dec
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
            if exec_candidates:
                exec_valid += 1
                # Select the most recent quote received prior to decision
                best_q = max(exec_candidates, key=lambda q: getattr(q, "response_timestamp", 0.0))
                b_ask = float(getattr(best_q, "ask_price", getattr(best_q, "stake", 0.0)))
                b_pay = float(getattr(best_q, "total_payout", 0.0))
                b_resp = float(getattr(best_q, "response_timestamp", 0.0))
                matched_list.append({
                    "decision_timestamp": t_dec,
                    "quote_id": str(getattr(best_q, "proposal_id", "") or getattr(best_q, "id", "")),
                    "response_timestamp": b_resp,
                    "ask_price": b_ask,
                    "total_payout": b_pay,
                    "break_even": b_ask / b_pay,
                    "age_seconds": t_dec - b_resp,
                    "quote_source": getattr(best_q, "quote_source", "live_proposal")
                })
            else:
                rejection_reasons["QUOTE_STALE"] += 1
                matched_list.append(None)

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
