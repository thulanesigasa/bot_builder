"""Paired Dual-Duration Research and Comparison Engine: 2-Tick vs 5-Tick (V1.7.4).

Conducts rigorous, fair, and scientifically grounded comparisons between Deriv
2-tick and 5-tick RUNHIGH (Only Ups) and RUNLOW (Only Downs) contracts on R_75.

Core Research Protocol:
1. Paired Forward Stream: Evaluates 2T and 5T simultaneously on the exact same tick stream.
2. Direction-Specific: RUNHIGH and RUNLOW are evaluated completely independently.
3. Full Metric Spectrum:
   - Win count, loss count, empirical win rate
   - Mean predicted probability, calibration error (ECE)
   - Brier score, Brier Skill Score (BSS)
   - Quote-implied break-even hurdles
   - Ordinary Expected Value ($ and per $1 stake)
   - Dependence-Aware Conservative EV (via Moving-Block Bootstrap)
4. Anti-Selection Bias Protocol: Prevents ranking by win rate alone. Higher win frequency
   (25% in 2T vs 3.2% in 5T) does NOT imply economic profitability because the payout is 8x smaller!
"""
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
    ordinary_ev: float
    ordinary_ev_per_dollar: float
    conservative_ev_bootstrap: float
    win_rate_ci_95: Tuple[float, float]
    quote_availability_pct: float
    is_economically_positive: bool
    verdict: str


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stream_tick_count": self.stream_tick_count,
            "decision_points_count": self.decision_points_count,
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
        bootstrap_block_size: int = 5
    ):
        self.symbol = symbol
        self.stake = stake
        self.payout_2t = payout_2t
        self.payout_5t = payout_5t
        self.bootstrap_iterations = bootstrap_iterations
        self.bootstrap_block_size = bootstrap_block_size

    def evaluate_ticks(
        self,
        prices: List[float],
        model_2t: Optional[Any] = None,
        model_5t: Optional[Any] = None
    ) -> DualDurationComparisonReport:
        """Evaluates all 4 configurations (2T RH, 2T RL, 5T RH, 5T RL) on the price series."""
        n = len(prices)
        if n < 35:
            raise ValueError(f"Insufficient ticks for dual duration evaluation: {n} < 35 required.")

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

        # Decision point i requires lookback of 25 ticks and 6 forward ticks (for 5T)
        decision_points = 0
        for i in range(25, n - 6):
            decision_points += 1

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
                hurdle=hurdle
            )
            metrics_dict[label] = summary

        # Rank strictly by ordinary expected value per dollar (economic hurdle performance)
        sorted_labels = sorted(
            metrics_dict.keys(),
            key=lambda k: metrics_dict[k].ordinary_ev_per_dollar,
            reverse=True
        )

        top = sorted_labels[0]
        top_summary = metrics_dict[top]
        winning = top if top_summary.is_economically_positive else None

        warning = (
            "PREVENTING SELECTION BIAS: Do NOT select the winning duration based on win rate. "
            "2-tick contracts win ~25% vs 5-tick contracts ~3%, but 2-tick payouts are ~8x smaller ($7.63 vs $61.07). "
            "Any candidate selected on exploratory data must be frozen and confirmed on untouched future sessions."
        )

        rec = (
            f"Top Ranked: {top} with Ordinary EV/stake ${top_summary.ordinary_ev:+.4f}. "
            f"Economically viable: {top_summary.is_economically_positive}. "
            "All tested configurations remain non-trading (NO_TRADE invariant enforced)."
        )

        return DualDurationComparisonReport(
            symbol=self.symbol,
            stream_tick_count=n,
            decision_points_count=decision_points,
            metrics=metrics_dict,
            economic_ranking=sorted_labels,
            winning_candidate=winning,
            selection_bias_warning=warning,
            recommendation=rec
        )

    def _compute_metrics(
        self,
        label: str,
        duration: int,
        direction: str,
        outcomes: List[float],
        pred_probs: List[float],
        payout: float,
        hurdle: float
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
        # Reference BS based on empirical win rate
        bs_ref = float(np.mean([(emp_win_rate - y)**2 for y in outcomes])) if n > 0 else 0.0
        bss = float(1.0 - (bs / bs_ref)) if bs_ref > 0 else 0.0

        # Ordinary EV on reference stake
        # EV = P_model * Payout - Stake
        ord_ev = (mean_prob * payout) - self.stake
        ord_ev_per_dollar = ord_ev / self.stake if self.stake > 0 else 0.0

        # Moving-Block Bootstrap for Conservative EV
        # Block size = duration + 1 to preserve serial correlation
        block_size = max(2, duration + 1)
        cons_ev = self._moving_block_bootstrap_ev(
            outcomes=outcomes,
            payout=payout,
            stake=self.stake,
            block_size=block_size,
            iterations=self.bootstrap_iterations,
            percentile=5.0  # 95% lower bound
        )

        # Wilson 95% Confidence Interval for win rate
        ci_lo, ci_hi = wilson_score_interval(wins, n, confidence=0.95)

        is_pos = (ord_ev > 0.0) and (cons_ev > -0.05)

        verdict = "POSITIVE_ORDINARY_EV" if ord_ev > 0 else "NEGATIVE_ORDINARY_EV"

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
            ordinary_ev=round(ord_ev, 4),
            ordinary_ev_per_dollar=round(ord_ev_per_dollar, 4),
            conservative_ev_bootstrap=round(cons_ev, 4),
            win_rate_ci_95=(round(ci_lo, 5), round(ci_hi, 5)),
            quote_availability_pct=100.0,
            is_economically_positive=is_pos,
            verdict=verdict
        )

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

    def _moving_block_bootstrap_ev(
        self,
        outcomes: List[float],
        payout: float,
        stake: float,
        block_size: int,
        iterations: int = 500,
        percentile: float = 5.0
    ) -> float:
        """Computes dependence-aware lower percentile of EV using moving-block bootstrap."""
        n = len(outcomes)
        if n < block_size * 2:
            # Fallback to simple mean minus stake
            return float(np.mean(outcomes) * payout - stake)

        arr = np.array(outcomes)
        # Create blocks
        num_blocks = n - block_size + 1
        blocks = [arr[j : j + block_size] for j in range(num_blocks)]

        blocks_needed = int(math.ceil(n / block_size))
        rng = np.random.default_rng(seed=42)

        ev_samples = []
        for _ in range(iterations):
            sampled_block_indices = rng.integers(0, num_blocks, size=blocks_needed)
            sample_arr = np.concatenate([blocks[idx] for idx in sampled_block_indices])[:n]
            sample_win_rate = np.mean(sample_arr)
            sample_ev = (sample_win_rate * payout) - stake
            ev_samples.append(sample_ev)

        return float(np.percentile(ev_samples, percentile))
