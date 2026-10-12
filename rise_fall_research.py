"""Multi-Market Rise/Fall Quantitative Edge Discovery & Hypothesis Testing Engine (V1.8.2).

Features:
  - Multi-Market Hypothesis Family: 48 predefined hypotheses
    (6 markets x 4 durations [2, 3, 5, 10 ticks] x 2 directions [CALL, PUT])
  - Strict Gating Architecture & Fail-Closed Quote Integration (V1.8.2):
      * Supported Research Modes:
          1. QUOTE_VERIFIED: Requires authenticated observation-level broker proposal records.
             Fails closed to INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE if quotes are absent.
             Passing a reference price tuple under QUOTE_VERIFIED raises ValueError.
          2. REFERENCE_ECONOMICS_ONLY: Illustrative fallback, permanently prohibited from qualifying.
          3. UNPRICED_PREDICTION_EVALUATION: Signal accuracy without economic pricing.
      * Ex-ante predicted EV MUST be strictly positive: PredictedEV > 0
      * Prospective hypothetical realized EV MUST be strictly positive: RealizedEV > 0
      * Conservative uncertainty bound MUST be strictly positive: ConservativeEV (MBB 95%) > 0
      * Multiple-testing control: Benjamini-Hochberg FDR-adjusted p-value < alpha
      * Serial dependence: Evaluates empirical autocorrelation time (tau_int) and N_eff.
  - Predeclared Hypothesis Classifications:
      * MODEL_CONDITIONED_SIGNAL_HYPOTHESIS
      * UNCONDITIONAL_DIRECTIONAL_BIAS_HYPOTHESIS
      * QUOTE_CONDITIONED_ECONOMIC_HYPOTHESIS
  - Candidate Qualification Gate: Centralized fail-closed evaluation
  - Authoritative Research Verdicts:
      * NO_VALIDATED_POSITIVE_EV_EDGE
      * INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE

Safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

from quote_economics_engine import (
    ProposalQuoteRecord,
    VerifiedEconomicObservation,
    PerObservationEconomicRecord,
    QuoteLevelEconomicEngine,
    MODE_QUOTE_VERIFIED,
    MODE_REFERENCE_ECONOMICS_ONLY,
    MODE_UNPRICED_PREDICTION_EVALUATION,
    STATUS_ELIGIBLE,
)

LIVE_EXECUTION_DISABLED: bool = True

VERDICT_NO_EDGE = "NO_VALIDATED_POSITIVE_EV_EDGE"
VERDICT_EXPLORATORY = "EXPLORATORY_CANDIDATE_IDENTIFIED"
VERDICT_CONFIRMATION_READY = "CONFIRMATION_READY"
VERDICT_CONFIRMED = "POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_MARKET_DATA"
VERDICT_INSUFFICIENT_QUOTES = "INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE"

STATUS_CANDIDATE_IDENTIFIED = "CANDIDATE_IDENTIFIED"
STATUS_REJECTED_NEGATIVE_PREDICTED_EV = "REJECTED_NEGATIVE_PREDICTED_EV"
STATUS_REJECTED_NEGATIVE_REALIZED_EV = "REJECTED_NEGATIVE_REALIZED_EV"
STATUS_REJECTED_NEGATIVE_EV = "REJECTED_NEGATIVE_EV"
STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV = "INCONCLUSIVE_INSUFFICIENT_CONSERVATIVE_EV"
STATUS_REJECTED_STATISTICAL_INSUFFICIENCY = "REJECTED_STATISTICAL_INSUFFICIENCY"
STATUS_REJECTED_INVALID_ECONOMIC_EVIDENCE = "REJECTED_INVALID_ECONOMIC_EVIDENCE"
STATUS_REFERENCE_ECONOMICS_ONLY = "REFERENCE_ECONOMICS_ONLY"
STATUS_INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE = "INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE"
STATUS_UNPRICED_PREDICTION_EVALUATION = "UNPRICED_PREDICTION_EVALUATION"


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
    evaluation_mode: str = MODE_QUOTE_VERIFIED
    rejection_reason: Optional[str] = None
    empirical_tau_int: Optional[float] = None
    quote_match_count: int = 0
    quote_eligibility_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_type": self.hypothesis_type,
            "market": self.market,
            "duration_ticks": self.duration_ticks,
            "direction": self.direction,
            "sample_size": self.sample_size,
            "effective_sample_size": self.effective_sample_size if self.effective_sample_size > 0 else self.sample_size,
            "empirical_tau_int": round(self.empirical_tau_int, 2) if self.empirical_tau_int is not None else None,
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
            "quote_match_count": self.quote_match_count,
            "quote_eligibility_pct": round(self.quote_eligibility_pct, 2),
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


class SerialDependenceAuditor:
    """Rigorous evaluation of serial dependence, autocorrelation, and effective sample size (Section 9)."""

    @staticmethod
    def compute_autocorrelation(series: np.ndarray, max_lag: int) -> np.ndarray:
        """Computes sample autocorrelation function rho(k) for k in [0, max_lag]."""
        n = len(series)
        if n <= 1:
            return np.ones(max_lag + 1)
        mean = float(np.mean(series))
        var = float(np.var(series))
        if var == 0:
            return np.ones(max_lag + 1)

        centered = series - mean
        autocorr = np.zeros(max_lag + 1)
        autocorr[0] = 1.0

        for k in range(1, min(max_lag + 1, n)):
            cov_k = np.mean(centered[: n - k] * centered[k:])
            autocorr[k] = cov_k / var

        return autocorr

    @classmethod
    def compute_integrated_autocorrelation_time(cls, series: np.ndarray, max_lag: int = 20) -> float:
        """Estimates integrated autocorrelation time tau_int = 1 + 2 * sum(rho(k))."""
        autocorr = cls.compute_autocorrelation(series, max_lag)
        tau = 1.0
        for k in range(1, len(autocorr)):
            if autocorr[k] <= 0:
                break
            tau += 2.0 * autocorr[k]
        return max(1.0, float(tau))

    @staticmethod
    def compute_effective_sample_size(series_or_n: Any, tau_int: float) -> int:
        """Computes empirical effective sample size N_eff = max(1, floor(N / tau_int))."""
        n = len(series_or_n) if hasattr(series_or_n, "__len__") else int(series_or_n)
        return max(1, int(n // tau_int))

    @classmethod
    def compare_dependence_methods(
        cls,
        outcomes: np.ndarray,
        duration_ticks: int,
        break_even: float = 0.51150895,
        payout: float = 3.91,
        ask: float = 2.0,
    ) -> Dict[str, Any]:
        """Compares the five dependence evaluation methods required by Section 9.2."""
        n = len(outcomes)
        if n == 0:
            return {}

        emp_wr = float(np.mean(outcomes))
        tau_int = cls.compute_integrated_autocorrelation_time(outcomes, max_lag=duration_ticks * 2)
        n_eff_emp = max(1, int(n // tau_int))
        n_eff_heur = max(1, int(n // duration_ticks))

        # 1. Naive independent-sample inference
        se_naive = math.sqrt(break_even * (1.0 - break_even) / n)
        z_naive = (emp_wr - break_even) / se_naive if se_naive > 0 else 0.0
        p_naive = float(0.5 * math.erfc(z_naive / math.sqrt(2.0)))

        # 2. Duration-divided sample-size heuristic (N / D)
        se_heur = math.sqrt(break_even * (1.0 - break_even) / n_eff_heur)
        z_heur = (emp_wr - break_even) / se_heur if se_heur > 0 else 0.0
        p_heur = float(0.5 * math.erfc(z_heur / math.sqrt(2.0)))

        # 3. Empirical autocorrelation-adjusted inference (N / tau_int)
        se_emp = math.sqrt(break_even * (1.0 - break_even) / n_eff_emp)
        z_emp = (emp_wr - break_even) / se_emp if se_emp > 0 else 0.0
        p_emp = float(0.5 * math.erfc(z_emp / math.sqrt(2.0)))

        # 4. Moving-block bootstrap bounds across multiple block sizes (b=2, b=D, b=2D)
        mbb_bounds = {}
        for b in [2, duration_ticks, duration_ticks * 2]:
            b_val = max(2, min(b, n // 2))
            bound = MovingBlockBootstrap.compute_ev_lower_bound(
                outcomes=outcomes, payout=payout, stake=ask, block_size=b_val, iterations=300
            )
            mbb_bounds[f"block_size_{b}"] = bound

        # 5. Non-overlapping decimated sampling (decimate by D)
        step = max(1, duration_ticks)
        decimated_outcomes = outcomes[::step]
        n_dec = len(decimated_outcomes)
        wr_dec = float(np.mean(decimated_outcomes))
        se_dec = math.sqrt(break_even * (1.0 - break_even) / n_dec)
        z_dec = (wr_dec - break_even) / se_dec if se_dec > 0 else 0.0
        p_dec = float(0.5 * math.erfc(z_dec / math.sqrt(2.0)))

        return {
            "sample_size_total": n,
            "empirical_win_rate": emp_wr,
            "naive_independent": {"n": n, "se": se_naive, "z": z_naive, "p_value": p_naive},
            "duration_divided_heuristic": {"n_eff": n_eff_heur, "se": se_heur, "z": z_heur, "p_value": p_heur},
            "empirical_autocorrelation": {
                "tau_int": tau_int, "n_eff": n_eff_emp, "se": se_emp, "z": z_emp, "p_value": p_emp
            },
            "moving_block_bootstrap_bounds": mbb_bounds,
            "non_overlapping_decimation": {"n_dec": n_dec, "win_rate": wr_dec, "se": se_dec, "z": z_dec, "p_value": p_dec},
            "assumptions_and_limitations": {
                "naive_independent": "Assumes zero serial correlation between consecutive ticks (grossly invalid for overlapping contracts).",
                "duration_divided_heuristic": "Approximates correlation length as duration D. Simple and robust for order-of-magnitude correction.",
                "empirical_autocorrelation": "Integrates observed outcome autocorrelation rho(k). More sequence-adaptive but sensitive to sample noise.",
                "moving_block_bootstrap": "Distribution-free resampling preserving local dependency blocks. Does not assume normality.",
                "non_overlapping_decimation": "Subsamples every D ticks to enforce true independence, at the cost of discarding (D-1)/D observations.",
            },
        }


class CandidateQualificationGate:
    """Authoritative, centralized gate verifying all necessary economic and statistical conditions."""

    @staticmethod
    def audit_candidate(evaluation: HypothesisEvaluation, min_sample: int = 50) -> Dict[str, Any]:
        """Audits an evaluation against all candidate qualification criteria."""
        g_ref = (evaluation.evaluation_mode == MODE_QUOTE_VERIFIED)
        g_pred = (evaluation.predicted_ev > 0.0)
        g_real = (evaluation.realized_ev > 0.0)
        g_cons = (evaluation.conservative_ev_mbb_95 is not None and evaluation.conservative_ev_mbb_95 > 0.0)
        g_sig = bool(evaluation.is_statistically_significant)
        g_samp = (evaluation.sample_size >= min_sample)

        # For model-conditioned hypotheses, predicted EV must be strictly positive
        if evaluation.hypothesis_type == HypothesisType.MODEL_CONDITIONED_SIGNAL.value:
            is_qualified = g_ref and g_pred and g_real and g_cons and g_sig and g_samp
        else:
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
        typical_quote: Optional[Tuple[float, float]] = None,
        evaluation_mode: str = MODE_REFERENCE_ECONOMICS_ONLY,
        verified_quotes: Optional[List[ProposalQuoteRecord]] = None,
        verified_observations: Optional[Dict[str, List[VerifiedEconomicObservation]]] = None,
        hypothesis_type: str = HypothesisType.MODEL_CONDITIONED_SIGNAL.value,
    ) -> List[HypothesisEvaluation]:
        """Evaluates all 48 hypotheses with strict mode enforcement and multiple-testing control.
        
        Args:
            market_outcomes: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            market_p_models: Dict[market, Dict[duration, Dict[direction, np.ndarray]]]
            typical_quote: Optional reference price tuple (ask, payout) for REFERENCE_ECONOMICS_ONLY.
            evaluation_mode: One of MODE_QUOTE_VERIFIED, MODE_REFERENCE_ECONOMICS_ONLY, MODE_UNPRICED_PREDICTION_EVALUATION.
            verified_quotes: Optional list of authentic ProposalQuoteRecord instances.
            verified_observations: Optional dict mapping hypothesis_id to VerifiedEconomicObservation instances.
            hypothesis_type: HypothesisType classification.
        """
        # Critical Defect 1 Guard: Prohibit reference tuples masquerading as QUOTE_VERIFIED (Section 4.1 / 13)
        if evaluation_mode == MODE_QUOTE_VERIFIED:
            if typical_quote is not None and verified_quotes is None and verified_observations is None:
                raise ValueError(
                    "QUOTE_VERIFIED mode strictly requires verified observation quote records. "
                    "Passing a reference price tuple under QUOTE_VERIFIED is prohibited."
                )

        ref_ask, ref_payout = typical_quote if typical_quote is not None else (2.0, 3.91)
        ref_be = ref_ask / ref_payout

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

                    # Effective sample size using empirical autocorrelation or duration heuristic
                    tau_int = SerialDependenceAuditor.compute_integrated_autocorrelation_time(outcomes, max_lag=dur * 2)
                    n_eff = max(1, int(n // tau_int)) if self.use_effective_sample_size else n

                    # Check quote availability under QUOTE_VERIFIED mode
                    if evaluation_mode == MODE_QUOTE_VERIFIED:
                        has_verified_data = False
                        matched_count = 0
                        matched_cov = 0.0
                        actual_ask = 0.0
                        actual_payout = 0.0
                        actual_be = 0.0
                        pred_ev = 0.0
                        real_ev = 0.0

                        if verified_observations and hyp_id in verified_observations:
                            obs_list = verified_observations[hyp_id]
                            elig = [o for o in obs_list if o.quote_eligibility_status == STATUS_ELIGIBLE]
                            if len(elig) >= 50:
                                has_verified_data = True
                                matched_count = len(elig)
                                matched_cov = (matched_count / len(obs_list)) * 100.0
                                actual_ask = float(np.mean([o.ask_price for o in elig if o.ask_price is not None]))
                                actual_payout = float(np.mean([o.total_payout for o in elig if o.total_payout is not None]))
                                actual_be = float(np.mean([o.break_even_rate for o in elig if o.break_even_rate is not None]))
                                pred_ev = float(np.mean([o.predicted_ev for o in elig if o.predicted_ev is not None]))
                                real_ev = float(np.mean([o.hypothetical_return for o in elig if o.hypothetical_return is not None]))
                        elif verified_quotes:
                            # Match using QuoteLevelEconomicEngine
                            obs_dicts = [
                                {"decision_epoch": float(idx), "predicted_prob": float(p), "observed_outcome": int(y)}
                                for idx, (p, y) in enumerate(zip(probs, outcomes))
                            ]
                            _, summary = QuoteLevelEconomicEngine.evaluate_observations(
                                observations=obs_dicts,
                                quotes=verified_quotes,
                                symbol=m,
                                contract_type=direct,
                                duration_ticks=dur,
                            )
                            if summary.eligible_decisions_count >= 50 and summary.is_quote_verified:
                                has_verified_data = True
                                matched_count = summary.eligible_decisions_count
                                matched_cov = summary.eligibility_coverage_pct
                                actual_ask = summary.mean_ask_price or 2.0
                                actual_payout = summary.mean_total_payout or 3.91
                                actual_be = summary.mean_break_even_rate or (actual_ask / actual_payout)
                                pred_ev = summary.mean_predicted_ev or 0.0
                                real_ev = summary.mean_realized_ev or 0.0

                        if not has_verified_data:
                            # Section 8: Missing quote data fails closed to INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE
                            raw_evaluations.append({
                                "hypothesis_id": hyp_id,
                                "hypothesis_type": hypothesis_type,
                                "market": m,
                                "duration_ticks": dur,
                                "direction": direct,
                                "sample_size": n,
                                "effective_sample_size": n_eff,
                                "empirical_tau_int": tau_int,
                                "p_model": p_model,
                                "empirical_win_rate": emp_wr,
                                "ask_price": 0.0,
                                "total_payout": 0.0,
                                "break_even_rate": 0.0,
                                "probability_advantage": 0.0,
                                "predicted_ev": 0.0,
                                "realized_ev": 0.0,
                                "conservative_ev_mbb_95": None,
                                "raw_p_value": 1.0,
                                "evaluation_mode": MODE_QUOTE_VERIFIED,
                                "quote_match_count": 0,
                                "quote_eligibility_pct": 0.0,
                                "force_verdict": STATUS_INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE,
                                "rejection_reason": "INSUFFICIENT_AUTHENTICATED_QUOTE_RECORDS",
                            })
                            continue
                        else:
                            # Genuine quote economics matched
                            bs = max(2, dur)
                            cons_ev = MovingBlockBootstrap.compute_ev_lower_bound(
                                outcomes=outcomes, payout=actual_payout, stake=actual_ask, block_size=bs, iterations=500
                            )
                            se = math.sqrt(actual_be * (1.0 - actual_be) / n_eff)
                            z_stat = (emp_wr - actual_be) / se if se > 0 else 0.0
                            p_val = float(0.5 * math.erfc(z_stat / math.sqrt(2.0)))

                            raw_evaluations.append({
                                "hypothesis_id": hyp_id,
                                "hypothesis_type": hypothesis_type,
                                "market": m,
                                "duration_ticks": dur,
                                "direction": direct,
                                "sample_size": n,
                                "effective_sample_size": n_eff,
                                "empirical_tau_int": tau_int,
                                "p_model": p_model,
                                "empirical_win_rate": emp_wr,
                                "ask_price": actual_ask,
                                "total_payout": actual_payout,
                                "break_even_rate": actual_be,
                                "probability_advantage": p_model - actual_be,
                                "predicted_ev": pred_ev,
                                "realized_ev": real_ev,
                                "conservative_ev_mbb_95": cons_ev,
                                "raw_p_value": p_val,
                                "evaluation_mode": MODE_QUOTE_VERIFIED,
                                "quote_match_count": matched_count,
                                "quote_eligibility_pct": matched_cov,
                                "force_verdict": None,
                                "rejection_reason": None,
                            })
                            continue

                    # Reference economics or unpriced prediction evaluation mode
                    prob_adv = p_model - ref_be
                    pred_ev = (p_model * ref_payout) - ref_ask
                    real_ev = (emp_wr * ref_payout) - ref_ask

                    bs = max(2, dur)
                    cons_ev = MovingBlockBootstrap.compute_ev_lower_bound(
                        outcomes=outcomes, payout=ref_payout, stake=ref_ask, block_size=bs, iterations=500
                    )

                    se = math.sqrt(ref_be * (1.0 - ref_be) / n_eff)
                    z_stat = (emp_wr - ref_be) / se if se > 0 else 0.0
                    p_val = float(0.5 * math.erfc(z_stat / math.sqrt(2.0)))

                    raw_evaluations.append({
                        "hypothesis_id": hyp_id,
                        "hypothesis_type": hypothesis_type,
                        "market": m,
                        "duration_ticks": dur,
                        "direction": direct,
                        "sample_size": n,
                        "effective_sample_size": n_eff,
                        "empirical_tau_int": tau_int,
                        "p_model": p_model,
                        "empirical_win_rate": emp_wr,
                        "ask_price": ref_ask,
                        "total_payout": ref_payout,
                        "break_even_rate": ref_be,
                        "probability_advantage": prob_adv,
                        "predicted_ev": pred_ev,
                        "realized_ev": real_ev,
                        "conservative_ev_mbb_95": cons_ev,
                        "raw_p_value": p_val,
                        "evaluation_mode": evaluation_mode,
                        "quote_match_count": 0,
                        "quote_eligibility_pct": 0.0,
                        "force_verdict": None,
                        "rejection_reason": None,
                    })

        # Apply Benjamini-Hochberg FDR adjustment across all tested hypotheses
        m_total = len(raw_evaluations)
        if m_total == 0:
            return []

        sorted_indices = sorted(range(m_total), key=lambda i: raw_evaluations[i]["raw_p_value"])
        adj_p_values = [1.0] * m_total
        cum_min = 1.0
        for rank_idx in range(m_total - 1, -1, -1):
            orig_idx = sorted_indices[rank_idx]
            rank = rank_idx + 1
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
            is_pos = (is_real_pos and is_cons_pos and is_pred_pos)

            if raw.get("force_verdict"):
                verdict = raw["force_verdict"]
                rejection_reason = raw["rejection_reason"]
            elif raw["evaluation_mode"] == MODE_UNPRICED_PREDICTION_EVALUATION:
                verdict = STATUS_UNPRICED_PREDICTION_EVALUATION
                rejection_reason = "UNPRICED_SIGNAL_EVALUATION_MODE"
            elif raw["evaluation_mode"] == MODE_REFERENCE_ECONOMICS_ONLY:
                # Reference mode can NEVER qualify as candidate
                if not is_pred_pos and is_real_pos:
                    verdict = STATUS_REJECTED_NEGATIVE_PREDICTED_EV
                    rejection_reason = "MODEL_FORECAST_EV_NON_POSITIVE"
                elif raw["realized_ev"] <= 0.0:
                    verdict = STATUS_REJECTED_NEGATIVE_EV
                    rejection_reason = "REALIZED_RETURN_NON_POSITIVE"
                else:
                    verdict = STATUS_REFERENCE_ECONOMICS_ONLY
                    rejection_reason = "REFERENCE_PRICING_INELIGIBLE_FOR_CANDIDATE_QUALIFICATION"
            elif is_sig and is_real_pos and is_cons_pos and is_pred_pos:
                verdict = STATUS_CANDIDATE_IDENTIFIED
                rejection_reason = None
            elif not is_pred_pos and is_real_pos:
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
                empirical_tau_int=raw["empirical_tau_int"],
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
                quote_match_count=raw.get("quote_match_count", 0),
                quote_eligibility_pct=raw.get("quote_eligibility_pct", 0.0),
                verdict=verdict,
                rejection_reason=rejection_reason,
            )
            final_evals.append(eval_obj)

        return final_evals

    def synthesize_verdict(self, evaluations: List[HypothesisEvaluation]) -> str:
        """Determines the authoritative research verdict across all tested candidates."""
        if not evaluations:
            return VERDICT_INSUFFICIENT_DATA

        # If evaluated under QUOTE_VERIFIED and all failed due to insufficient quotes:
        if all(e.verdict == STATUS_INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE for e in evaluations):
            return VERDICT_INSUFFICIENT_QUOTES

        promising = [e for e in evaluations if e.verdict == STATUS_CANDIDATE_IDENTIFIED]
        if promising:
            return VERDICT_EXPLORATORY

        return VERDICT_NO_EDGE
