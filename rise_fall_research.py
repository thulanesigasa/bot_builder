"""Multi-Market Rise/Fall Quantitative Edge Discovery & Hypothesis Testing Engine (V1.8.0).

Features:
  - Multi-Market Hypothesis Family: 48 predefined hypotheses
    (6 markets x 4 durations [2, 3, 5, 10 ticks] x 2 directions [CALL, PUT])
  - Genuine Deriv proposal quotes and break-even hurdle calculation:
      BreakEven = AskPrice / TotalPayout
      PredictedEV = P_model * TotalPayout - AskPrice
      RealizedEV = Outcome * TotalPayout - AskPrice
      ProbabilityAdvantage = P_model - BreakEven
  - Moving-Block Bootstrap (MBB) 95% Lower Confidence Bound for EV
  - Benjamini-Hochberg False Discovery Rate (FDR) Multiple-Testing Correction
  - 4-Tier Research Cohort System (A, B, C, D) with strictly empty Cohort D:
      Cohort D contains zero observations, None for win rate / EV, and PREREGISTRATION_REQUIRED
  - Authoritative Verdict Generator: NO_VALIDATED_POSITIVE_EV_EDGE

Safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

LIVE_EXECUTION_DISABLED: bool = True

VERDICT_NO_EDGE = "NO_VALIDATED_POSITIVE_EV_EDGE"
VERDICT_EXPLORATORY = "EXPLORATORY_CANDIDATE_IDENTIFIED"
VERDICT_CONFIRMATION_READY = "CONFIRMATION_READY"
VERDICT_CONFIRMED = "POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_MARKET_DATA"


@dataclass
class HypothesisEvaluation:
    """Predeclared hypothesis evaluation under multiple-testing control."""
    hypothesis_id: str
    market: str
    duration_ticks: int
    direction: str
    sample_size: int
    p_model: float
    empirical_win_rate: float
    ask_price: float
    total_payout: float
    break_even_rate: float
    probability_advantage: float
    predicted_ev: float
    realized_ev: float
    conservative_ev_mbb_95: Optional[float]
    raw_p_value: float
    adjusted_p_value_fdr: float
    is_statistically_significant: bool
    is_economically_positive: bool
    verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "market": self.market,
            "duration_ticks": self.duration_ticks,
            "direction": self.direction,
            "sample_size": self.sample_size,
            "p_model": round(self.p_model, 4),
            "empirical_win_rate": round(self.empirical_win_rate, 4),
            "ask_price": round(self.ask_price, 2),
            "total_payout": round(self.total_payout, 2),
            "break_even_rate": round(self.break_even_rate, 4),
            "probability_advantage": round(self.probability_advantage, 4),
            "predicted_ev": round(self.predicted_ev, 4),
            "realized_ev": round(self.realized_ev, 4),
            "conservative_ev_mbb_95": round(self.conservative_ev_mbb_95, 4) if self.conservative_ev_mbb_95 is not None else None,
            "raw_p_value": round(self.raw_p_value, 6),
            "adjusted_p_value_fdr": round(self.adjusted_p_value_fdr, 6),
            "is_statistically_significant": self.is_statistically_significant,
            "is_economically_positive": self.is_economically_positive,
            "verdict": self.verdict,
        }


class MovingBlockBootstrap:
    """Computes dependence-aware conservative uncertainty bounds for time-series contract returns."""

    @staticmethod
    def compute_ev_lower_bound(
        outcomes: np.ndarray,
        payout: float,
        stake: float,
        block_size: int,
        iterations: int = 500,
        percentile: float = 5.0,
        seed: int = 42,
    ) -> Optional[float]:
        """Calculates 95% lower confidence bound (5th percentile) of EV via moving-block bootstrap."""
        n = len(outcomes)
        if n < max(30, block_size * 2):
            return None

        num_blocks = n - block_size + 1
        blocks = [outcomes[j : j + block_size] for j in range(num_blocks)]
        blocks_needed = int(math.ceil(n / block_size))

        rng = np.random.default_rng(seed=seed)
        ev_samples = []

        for _ in range(iterations):
            sampled_block_indices = rng.integers(0, num_blocks, size=blocks_needed)
            sample_arr = np.concatenate([blocks[idx] for idx in sampled_block_indices])[:n]
            sample_ev = (np.mean(sample_arr) * payout) - stake
            ev_samples.append(sample_ev)

        return float(np.percentile(ev_samples, percentile))


class MultiMarketEdgeDiscovery:
    """Orchestrates multi-market hypothesis testing, economic evaluation, and multiple-testing adjustment."""

    def __init__(self, fdr_alpha: float = 0.05):
        self.fdr_alpha = fdr_alpha
        self.markets = ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        self.durations = [2, 3, 5, 10]
        self.directions = ["CALL", "PUT"]

    def evaluate_all_hypotheses(
        self,
        market_outcomes: Dict[str, Dict[int, Dict[str, np.ndarray]]],
        market_p_models: Dict[str, Dict[int, Dict[str, np.ndarray]]],
        typical_quote: Tuple[float, float] = (2.0, 3.91),
    ) -> List[HypothesisEvaluation]:
        """Evaluates all 48 hypotheses with Benjamini-Hochberg FDR correction.
        
        Args:
            market_outcomes: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            market_p_models: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            typical_quote: (ask_price, total_payout)
        """
        ask, payout = typical_quote
        break_even = ask / payout

        raw_evaluations: List[Dict[str, Any]] = []

        for m in self.markets:
            for dur in self.durations:
                for direct in self.directions:
                    hyp_id = f"HYP_{m}_{dur}T_{direct}"
                    outcomes = market_outcomes.get(m, {}).get(dur, {}).get(direct, np.array([]))
                    probs = market_p_models.get(m, {}).get(dur, {}).get(direct, np.array([]))

                    n = len(outcomes)
                    if n == 0:
                        continue

                    emp_wr = float(np.mean(outcomes))
                    p_model = float(np.mean(probs)) if len(probs) > 0 else 0.50

                    prob_adv = p_model - break_even
                    pred_ev = (p_model * payout) - ask
                    real_ev = (emp_wr * payout) - ask

                    # Moving-block bootstrap conservative bound (block_size = max(2, dur))
                    bs = max(2, dur)
                    cons_ev = MovingBlockBootstrap.compute_ev_lower_bound(
                        outcomes=outcomes,
                        payout=payout,
                        stake=ask,
                        block_size=bs,
                        iterations=500,
                        percentile=5.0,
                    )

                    # Compute asymptotic one-sided p-value for H0: EV <= 0 (or WinRate <= break_even)
                    se = math.sqrt(break_even * (1.0 - break_even) / n)
                    z_stat = (emp_wr - break_even) / se if se > 0 else 0.0
                    # Standard normal survival function: P(Z >= z_stat)
                    p_val = float(0.5 * math.erfc(z_stat / math.sqrt(2.0)))

                    raw_evaluations.append({
                        "hypothesis_id": hyp_id,
                        "market": m,
                        "duration_ticks": dur,
                        "direction": direct,
                        "sample_size": n,
                        "p_model": p_model,
                        "empirical_win_rate": emp_wr,
                        "ask_price": ask,
                        "total_payout": payout,
                        "break_even_rate": break_even,
                        "probability_advantage": prob_adv,
                        "predicted_ev": pred_ev,
                        "realized_ev": real_ev,
                        "conservative_ev_mbb_95": cons_ev,
                        "raw_p_value": p_val,
                    })

        # Apply Benjamini-Hochberg FDR adjustment across all tested hypotheses
        m_total = len(raw_evaluations)
        if m_total == 0:
            return []

        # Sort by raw p-value ascending
        sorted_indices = sorted(range(m_total), key=lambda i: raw_evaluations[i]["raw_p_value"])
        adj_p_values = [1.0] * m_total

        # BH Step-up: p_adj = min(1.0, p_val * m / rank)
        cum_min = 1.0
        for rank_idx in range(m_total - 1, -1, -1):
            orig_idx = sorted_indices[rank_idx]
            rank = rank_idx + 1  # 1-based rank
            raw_p = raw_evaluations[orig_idx]["raw_p_value"]
            adjusted = (raw_p * m_total) / rank
            cum_min = min(cum_min, adjusted)
            adj_p_values[orig_idx] = min(1.0, cum_min)

        final_evals: List[HypothesisEvaluation] = []
        for i, raw in enumerate(raw_evaluations):
            p_adj = adj_p_values[i]
            is_sig = (p_adj < self.fdr_alpha)
            cons_ev = raw["conservative_ev_mbb_95"]
            is_pos = (raw["realized_ev"] > 0 and (cons_ev is not None and cons_ev > 0))

            if is_sig and is_pos:
                verdict = "CANDIDATE_IDENTIFIED"
            elif raw["realized_ev"] <= 0:
                verdict = "REJECTED_NEGATIVE_EV"
            else:
                verdict = "INCONCLUSIVE_INSUFFICIENT_CONSERVATIVE_EV"

            eval_obj = HypothesisEvaluation(
                hypothesis_id=raw["hypothesis_id"],
                market=raw["market"],
                duration_ticks=raw["duration_ticks"],
                direction=raw["direction"],
                sample_size=raw["sample_size"],
                p_model=raw["p_model"],
                empirical_win_rate=raw["empirical_win_rate"],
                ask_price=raw["ask_price"],
                total_payout=raw["total_payout"],
                break_even_rate=raw["break_even_rate"],
                probability_advantage=raw["probability_advantage"],
                predicted_ev=raw["predicted_ev"],
                realized_ev=raw["realized_ev"],
                conservative_ev_mbb_95=cons_ev,
                raw_p_value=raw["raw_p_value"],
                adjusted_p_value_fdr=p_adj,
                is_statistically_significant=is_sig,
                is_economically_positive=is_pos,
                verdict=verdict,
            )
            final_evals.append(eval_obj)

        return final_evals

    def synthesize_verdict(self, evaluations: List[HypothesisEvaluation]) -> str:
        """Determines the authoritative research verdict across all tested candidates."""
        if not evaluations:
            return VERDICT_INSUFFICIENT_DATA

        promising = [e for e in evaluations if e.verdict == "CANDIDATE_IDENTIFIED"]
        if promising:
            return VERDICT_EXPLORATORY

        # If zero hypotheses demonstrate statistically significant positive conservative EV:
        return VERDICT_NO_EDGE
