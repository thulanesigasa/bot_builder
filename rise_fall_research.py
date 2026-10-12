"""Multi-Market Rise/Fall Quantitative Edge Discovery & Hypothesis Testing Engine (V1.8.1).

Features:
  - Multi-Market Hypothesis Family: 48 predefined hypotheses
    (6 markets x 4 durations [2, 3, 5, 10 ticks] x 2 directions [CALL, PUT])
  - Strict Gating Architecture (V1.8.1 Critical Repair):
      * Ex-ante predicted EV MUST be strictly positive: PredictedEV > 0
      * Prospective hypothetical realized EV MUST be strictly positive: RealizedEV > 0
      * Conservative uncertainty bound MUST be strictly positive: ConservativeEV (MBB 95%) > 0
      * Multiple-testing control: Benjamini-Hochberg FDR-adjusted p-value < alpha
      * Serial dependence: Effective sample size N_eff = max(1, floor(N / D))
      * Reference pricing fallback prohibited from candidate qualification
  - Predeclared Hypothesis Classifications:
      * MODEL_CONDITIONED_SIGNAL_HYPOTHESIS
      * UNCONDITIONAL_DIRECTIONAL_BIAS_HYPOTHESIS
      * QUOTE_CONDITIONED_ECONOMIC_HYPOTHESIS
  - Candidate Qualification Gate: Centralized fail-closed evaluation
  - Authoritative Research Verdict: NO_VALIDATED_POSITIVE_EV_EDGE

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

STATUS_CANDIDATE_IDENTIFIED = "CANDIDATE_IDENTIFIED"
STATUS_REJECTED_NEGATIVE_PREDICTED_EV = "REJECTED_NEGATIVE_PREDICTED_EV"
STATUS_REJECTED_NEGATIVE_REALIZED_EV = "REJECTED_NEGATIVE_REALIZED_EV"
STATUS_REJECTED_NEGATIVE_EV = "REJECTED_NEGATIVE_EV"
STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV = "INCONCLUSIVE_INSUFFICIENT_CONSERVATIVE_EV"
STATUS_REJECTED_STATISTICAL_INSUFFICIENCY = "REJECTED_STATISTICAL_INSUFFICIENCY"
STATUS_REJECTED_INVALID_ECONOMIC_EVIDENCE = "REJECTED_INVALID_ECONOMIC_EVIDENCE"
STATUS_REFERENCE_ECONOMICS_ONLY = "REFERENCE_ECONOMICS_ONLY"


class HypothesisType(str, Enum):
    """Predeclared research hypothesis classification."""
    MODEL_CONDITIONED_SIGNAL = "MODEL_CONDITIONED_SIGNAL_HYPOTHESIS"
    UNCONDITIONAL_DIRECTIONAL_BIAS = "UNCONDITIONAL_DIRECTIONAL_BIAS_HYPOTHESIS"
    QUOTE_CONDITIONED_ECONOMIC = "QUOTE_CONDITIONED_ECONOMIC_HYPOTHESIS"


@dataclass
class HypothesisEvaluation:
    """Authoritative hypothesis evaluation under dependence-aware and multiple-testing control."""
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
    effective_sample_size: int = 0
    hypothesis_type: str = HypothesisType.MODEL_CONDITIONED_SIGNAL.value
    evaluation_mode: str = "QUOTE_VERIFIED"
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_type": self.hypothesis_type,
            "market": self.market,
            "duration_ticks": self.duration_ticks,
            "direction": self.direction,
            "sample_size": self.sample_size,
            "effective_sample_size": self.effective_sample_size if self.effective_sample_size > 0 else self.sample_size,
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
            "evaluation_mode": self.evaluation_mode,
            "verdict": self.verdict,
            "rejection_reason": self.rejection_reason,
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


class CandidateQualificationGate:
    """Authoritative, centralized gate verifying all necessary economic and statistical conditions.
    
    Prevents retrospective win rate leaks from qualifying strategies with negative predicted EV.
    """

    @staticmethod
    def audit_candidate(evaluation: HypothesisEvaluation, min_sample: int = 50) -> Dict[str, Any]:
        """Audits an evaluation against all candidate qualification criteria."""
        g_ref = (evaluation.evaluation_mode != "REFERENCE_ECONOMICS_ONLY")
        g_pred = (evaluation.predicted_ev > 0.0)
        g_real = (evaluation.realized_ev > 0.0)
        g_cons = (evaluation.conservative_ev_mbb_95 is not None and evaluation.conservative_ev_mbb_95 > 0.0)
        g_sig = bool(evaluation.is_statistically_significant)
        g_samp = (evaluation.sample_size >= min_sample)

        # For model-conditioned hypotheses, predicted EV must be strictly positive
        if evaluation.hypothesis_type == HypothesisType.MODEL_CONDITIONED_SIGNAL.value:
            is_qualified = g_ref and g_pred and g_real and g_cons and g_sig and g_samp
        else:
            # Unconditional bias hypothesis requires base-rate hurdle clearance
            is_qualified = g_ref and g_real and g_cons and g_sig and g_samp

        failure_reasons = []
        if not g_ref:
            failure_reasons.append("REFERENCE_ECONOMICS_PROHIBITED")
        if not g_pred and evaluation.hypothesis_type == HypothesisType.MODEL_CONDITIONED_SIGNAL.value:
            failure_reasons.append("NEGATIVE_PREDICTED_EV")
        if not g_real:
            failure_reasons.append("NEGATIVE_REALIZED_EV")
        if not g_cons:
            failure_reasons.append("NON_POSITIVE_CONSERVATIVE_EV")
        if not g_sig:
            failure_reasons.append("STATISTICALLY_INSIGNIFICANT")
        if not g_samp:
            failure_reasons.append("INSUFFICIENT_SAMPLE_SIZE")

        return {
            "is_qualified": is_qualified,
            "gate_quote_verified": g_ref,
            "gate_positive_predicted_ev": g_pred,
            "gate_positive_realized_ev": g_real,
            "gate_positive_conservative_ev": g_cons,
            "gate_statistically_significant": g_sig,
            "gate_adequate_sample": g_samp,
            "failure_reasons": failure_reasons,
        }


class MultiMarketEdgeDiscovery:
    """Orchestrates multi-market hypothesis testing, economic evaluation, and multiple-testing adjustment."""

    def __init__(self, fdr_alpha: float = 0.05, use_effective_sample_size: bool = True):
        self.fdr_alpha = fdr_alpha
        self.use_effective_sample_size = use_effective_sample_size
        self.markets = ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        self.durations = [2, 3, 5, 10]
        self.directions = ["CALL", "PUT"]

    def evaluate_all_hypotheses(
        self,
        market_outcomes: Dict[str, Dict[int, Dict[str, np.ndarray]]],
        market_p_models: Dict[str, Dict[int, Dict[str, np.ndarray]]],
        typical_quote: Tuple[float, float] = (2.0, 3.91),
        evaluation_mode: str = "QUOTE_VERIFIED",
        hypothesis_type: str = HypothesisType.MODEL_CONDITIONED_SIGNAL.value,
    ) -> List[HypothesisEvaluation]:
        """Evaluates all 48 hypotheses with dependence-aware testing and Benjamini-Hochberg FDR correction.
        
        Args:
            market_outcomes: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            market_p_models: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            typical_quote: (ask_price, total_payout)
            evaluation_mode: "QUOTE_VERIFIED" or "REFERENCE_ECONOMICS_ONLY"
            hypothesis_type: One of HypothesisType values
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

                    # Effective sample size accounting for serial dependence in overlapping tick contracts
                    n_eff = max(1, int(n // dur)) if self.use_effective_sample_size else n

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

                    # Compute asymptotic one-sided p-value for H0: EV <= 0 using n_eff
                    se = math.sqrt(break_even * (1.0 - break_even) / n_eff)
                    z_stat = (emp_wr - break_even) / se if se > 0 else 0.0
                    # Standard normal survival function: P(Z >= z_stat)
                    p_val = float(0.5 * math.erfc(z_stat / math.sqrt(2.0)))

                    raw_evaluations.append({
                        "hypothesis_id": hyp_id,
                        "hypothesis_type": hypothesis_type,
                        "market": m,
                        "duration_ticks": dur,
                        "direction": direct,
                        "sample_size": n,
                        "effective_sample_size": n_eff,
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
                        "evaluation_mode": evaluation_mode,
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

            is_pred_pos = (raw["predicted_ev"] > 0.0)
            is_real_pos = (raw["realized_ev"] > 0.0)
            is_cons_pos = (cons_ev is not None and cons_ev > 0.0)

            # Combined economic positivity requires all three to be positive
            is_pos = (is_real_pos and is_cons_pos and is_pred_pos)

            # Strict Gating Verdict Classification:
            if raw["evaluation_mode"] == "REFERENCE_ECONOMICS_ONLY":
                verdict = STATUS_REFERENCE_ECONOMICS_ONLY
                rejection_reason = "REFERENCE_PRICING_INELIGIBLE_FOR_CANDIDATE_QUALIFICATION"
            elif is_sig and is_real_pos and is_cons_pos and is_pred_pos:
                verdict = STATUS_CANDIDATE_IDENTIFIED
                rejection_reason = None
            elif not is_pred_pos and is_real_pos:
                # The critical defect repair: retrospective win rate exceeded hurdle, but model forecast EV was negative!
                verdict = STATUS_REJECTED_NEGATIVE_PREDICTED_EV
                rejection_reason = "MODEL_FORECAST_EV_NON_POSITIVE"
            elif raw["realized_ev"] <= 0.0:
                verdict = STATUS_REJECTED_NEGATIVE_EV
                rejection_reason = "REALIZED_RETURN_NON_POSITIVE"
            elif not is_cons_pos:
                verdict = STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV
                rejection_reason = "CONSERVATIVE_BOOTSTRAP_BOUND_NON_POSITIVE"
            elif not is_sig:
                verdict = STATUS_REJECTED_STATISTICAL_INSUFFICIENCY
                rejection_reason = "FDR_MULTIPLE_TESTING_INSIGNIFICANT"
            else:
                verdict = STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV
                rejection_reason = "GENERAL_QUALIFICATION_FAILURE"

            eval_obj = HypothesisEvaluation(
                hypothesis_id=raw["hypothesis_id"],
                hypothesis_type=raw["hypothesis_type"],
                market=raw["market"],
                duration_ticks=raw["duration_ticks"],
                direction=raw["direction"],
                sample_size=raw["sample_size"],
                effective_sample_size=raw["effective_sample_size"],
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
                evaluation_mode=raw["evaluation_mode"],
                verdict=verdict,
                rejection_reason=rejection_reason,
            )
            final_evals.append(eval_obj)

        return final_evals

    def synthesize_verdict(self, evaluations: List[HypothesisEvaluation]) -> str:
        """Determines the authoritative research verdict across all tested candidates."""
        if not evaluations:
            return VERDICT_INSUFFICIENT_DATA

        promising = [e for e in evaluations if e.verdict == STATUS_CANDIDATE_IDENTIFIED]
        if promising:
            return VERDICT_EXPLORATORY

        # If zero hypotheses demonstrate statistically significant positive conservative EV and positive predicted EV:
        return VERDICT_NO_EDGE
