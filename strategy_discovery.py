"""AI-Assisted Strategy Discovery and Predeclared Hypothesis Testing Engine (V1.7.4).

Inspired by Vibe-Trading methodology, this module provides controlled, evidence-grounded
hypothesis generation and statistical verification for Deriv R_75 tick behavior.

Core Principles:
1. Advisory-Only: Proposes hypotheses about market behavior. CANNOT authorize execution.
2. Controlled Hypothesis Families: Eliminates unrestricted data-mining or p-hacking.
3. Overlapping-Label Purging: Purges neighboring dependent ticks so test samples are non-overlapping.
4. Multiple-Testing Correction: Applies Bonferroni and Benjamini-Hochberg (FDR) corrections.
5. Strict Economic Hurdle: A hypothesis is only candidate-viable if its conditional probability
   exceeds the broker break-even hurdle with statistical significance.
"""
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable
import numpy as np
import pandas as pd


def binomial_test_greater(k: int, n: int, p: float) -> float:
    """Computes one-tailed p-value P(X >= k) for Binomial(n, p) using pure standard library.
    
    Uses exact binomial sum for n <= 50, and continuity-corrected normal approximation
    via math.erfc for larger n.
    """
    if n <= 0:
        return 1.0
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0 if k > 0 else 1.0
    if p >= 1.0:
        return 1.0 if k <= n else 0.0

    if n <= 50:
        # Exact binomial sum
        prob_sum = 0.0
        for j in range(k, n + 1):
            prob_sum += math.comb(n, j) * (p ** j) * ((1.0 - p) ** (n - j))
        return min(1.0, max(0.0, prob_sum))
    else:
        # Continuity-corrected normal approximation
        mean = n * p
        var = n * p * (1.0 - p)
        if var <= 0.0:
            return 1.0 if k <= mean else 0.0
        std = math.sqrt(var)
        z = (k - 0.5 - mean) / std
        # P(Z >= z) = 0.5 * erfc(z / sqrt(2))
        p_val = 0.5 * math.erfc(z / math.sqrt(2.0))
        return min(1.0, max(0.0, p_val))

from feature_schema import extract_discrete_market_state
from contract_model import ContractOutcomeModel


# Permanent Invariant: Strategy discovery is strictly advisory and cannot execute orders
IS_ADVISORY_ONLY: bool = True
EXECUTION_AUTHORIZATION_DISABLED: bool = True

DERIV_2T_REFERENCE_STAKE: float = 2.00
DERIV_2T_REFERENCE_PAYOUT: float = 7.63
DERIV_5T_REFERENCE_STAKE: float = 2.00
DERIV_5T_REFERENCE_PAYOUT: float = 61.07


@dataclass(frozen=True)
class PredeclaredHypothesis:
    """Predeclared research hypothesis specifying explicit features and evaluation rules."""
    hypothesis_id: str
    name: str
    rationale: str
    target_direction: str          # 'RUNHIGH' or 'RUNLOW'
    contract_duration: int         # 2 or 5
    feature_requirements: Dict[str, Any]
    economic_hurdle: float         # 0.26212 for 2T, 0.03275 for 5T
    predeclared_rule: str


@dataclass
class HypothesisTestResult:
    """Evidence-grounded audit result for a tested research hypothesis."""
    hypothesis_id: str
    name: str
    target_direction: str
    contract_duration: int
    total_purged_samples: int
    conditioned_samples: int
    win_count: int
    empirical_win_rate: float
    unconditional_baseline: float
    economic_hurdle: float
    raw_p_value_vs_baseline: float
    raw_p_value_vs_hurdle: float
    adjusted_p_value_bonferroni: float
    adjusted_p_value_fdr: float
    ordinary_ev_per_dollar: float
    is_statistically_significant: bool
    is_economically_viable: bool
    verdict: str                  # 'REJECTED', 'INCONCLUSIVE', or 'PROVISIONALLY_SUPPORTED'
    audit_notes: str


# Canonical Predeclared Hypothesis Families (V1.7.4 Part F Section 17 & 18)
CANONICAL_HYPOTHESES: List[PredeclaredHypothesis] = [
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_STREAK_CONT_UP",
        name="2-Tick Streak Continuation (RUNHIGH)",
        rationale="Does an existing upward streak (HIGH_UP_STREAK or EXTREME_UP_STREAK) increase 2-tick run probability?",
        target_direction="RUNHIGH",
        contract_duration=2,
        feature_requirements={"streak_bin": ["HIGH_UP_STREAK", "EXTREME_UP_STREAK"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="streak_bin in ('HIGH_UP_STREAK', 'EXTREME_UP_STREAK')"
    ),
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_STREAK_CONT_DOWN",
        name="2-Tick Streak Continuation (RUNLOW)",
        rationale="Does an existing downward streak (HIGH_DOWN_STREAK or EXTREME_DOWN_STREAK) increase 2-tick run probability?",
        target_direction="RUNLOW",
        contract_duration=2,
        feature_requirements={"streak_bin": ["HIGH_DOWN_STREAK", "EXTREME_DOWN_STREAK"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="streak_bin in ('HIGH_DOWN_STREAK', 'EXTREME_DOWN_STREAK')"
    ),
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_VOL_REGIME_LOW_UP",
        name="2-Tick Low Volatility Trend (RUNHIGH)",
        rationale="Does low volatility combined with bullish momentum favor 2-tick monotonic rise?",
        target_direction="RUNHIGH",
        contract_duration=2,
        feature_requirements={"vol_bin": ["LOW_VOL"], "mom_bin": ["STRONG_BULL", "MILD_BULL"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BULL', 'MILD_BULL')"
    ),
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_VOL_REGIME_LOW_DOWN",
        name="2-Tick Low Volatility Trend (RUNLOW)",
        rationale="Does low volatility combined with bearish momentum favor 2-tick monotonic fall?",
        target_direction="RUNLOW",
        contract_duration=2,
        feature_requirements={"vol_bin": ["LOW_VOL"], "mom_bin": ["STRONG_BEAR", "MILD_BEAR"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="vol_bin == 'LOW_VOL' and mom_bin in ('STRONG_BEAR', 'MILD_BEAR')"
    ),
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_REVERSAL_EXTREME_DROP",
        name="2-Tick Mean Reversion After Extreme Drop",
        rationale="Does an extreme negative drop (STRONG_BEAR + ACCEL_DOWN) trigger short-term mean-reverting 2-tick bounce?",
        target_direction="RUNHIGH",
        contract_duration=2,
        feature_requirements={"mom_bin": ["STRONG_BEAR"], "accel_bin": ["ACCEL_DOWN"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="mom_bin == 'STRONG_BEAR' and accel_bin == 'ACCEL_DOWN'"
    ),
    PredeclaredHypothesis(
        hypothesis_id="HYP_2T_REVERSAL_EXTREME_RISE",
        name="2-Tick Mean Reversion After Extreme Rise",
        rationale="Does an extreme positive rally (STRONG_BULL + ACCEL_UP) trigger short-term mean-reverting 2-tick pullback?",
        target_direction="RUNLOW",
        contract_duration=2,
        feature_requirements={"mom_bin": ["STRONG_BULL"], "accel_bin": ["ACCEL_UP"]},
        economic_hurdle=2.00 / 7.63,
        predeclared_rule="mom_bin == 'STRONG_BULL' and accel_bin == 'ACCEL_UP'"
    ),
]


class StrategyDiscoveryEngine:
    """Evaluates controlled strategy hypotheses with purged validation and multiple-testing controls."""

    def __init__(
        self,
        hypotheses: Optional[List[PredeclaredHypothesis]] = None,
        significance_alpha: float = 0.05
    ):
        self.hypotheses = hypotheses or list(CANONICAL_HYPOTHESES)
        self.significance_alpha = significance_alpha

    def evaluate_all(
        self,
        df: pd.DataFrame,
        purge_overlap: bool = True
    ) -> List[HypothesisTestResult]:
        """Evaluates all predeclared hypotheses on the provided tick dataframe."""
        raw_results: List[Dict[str, Any]] = []

        m_total = len(self.hypotheses)
        p_values_baseline = []
        p_values_hurdle = []

        for hyp in self.hypotheses:
            res_dict = self._evaluate_single_hypothesis(df, hyp, purge_overlap=purge_overlap)
            raw_results.append(res_dict)
            p_values_baseline.append(res_dict["raw_p_val_baseline"])
            p_values_hurdle.append(res_dict["raw_p_val_hurdle"])

        # Multiple testing adjustments
        # 1. Bonferroni: p_adj = min(1.0, p * M)
        # 2. Benjamini-Hochberg (FDR)
        bonferroni_p = [min(1.0, p * m_total) for p in p_values_hurdle]

        # FDR calculation
        sorted_indices = np.argsort(p_values_hurdle)
        fdr_p = [1.0] * m_total
        for rank, idx in enumerate(sorted_indices):
            fdr_val = min(1.0, p_values_hurdle[idx] * m_total / (rank + 1))
            fdr_p[idx] = fdr_val

        final_results: List[HypothesisTestResult] = []
        for i, r in enumerate(raw_results):
            hyp = self.hypotheses[i]
            p_bonf = bonferroni_p[i]
            p_fdr = fdr_p[i]
            win_rate = r["win_rate"]
            hurdle = hyp.economic_hurdle

            is_stat_sig = (p_bonf < self.significance_alpha) and (win_rate > r["uncond_baseline"])
            is_econ_viable = (win_rate > hurdle) and (p_bonf < self.significance_alpha)

            if win_rate <= hurdle:
                verdict = "REJECTED (BELOW_ECONOMIC_HURDLE)"
            elif not is_stat_sig:
                verdict = "INCONCLUSIVE (INSIGNIFICANT_AFTER_BONFERRONI)"
            else:
                verdict = "PROVISIONALLY_SUPPORTED (REQUIRES_UNTOUCHED_CONFIRMATION)"

            notes = (
                f"Samples: {r['n_cond']}/{r['n_purged']} ({r['wins']} wins). "
                f"Win Rate: {win_rate*100:.2f}% vs Hurdle {hurdle*100:.2f}%. "
                f"Raw p vs Hurdle: {r['raw_p_val_hurdle']:.4f}, Bonferroni p: {p_bonf:.4f}."
            )

            # EV per $1.00 stake: (win_rate * payout - 1.0) / stake
            payout = DERIV_2T_REFERENCE_PAYOUT if hyp.contract_duration == 2 else 61.07
            stake = 2.00
            ev_per_dollar = (win_rate * payout - stake) / stake

            final_results.append(HypothesisTestResult(
                hypothesis_id=hyp.hypothesis_id,
                name=hyp.name,
                target_direction=hyp.target_direction,
                contract_duration=hyp.contract_duration,
                total_purged_samples=r["n_purged"],
                conditioned_samples=r["n_cond"],
                win_count=r["wins"],
                empirical_win_rate=round(win_rate, 5),
                unconditional_baseline=round(r["uncond_baseline"], 5),
                economic_hurdle=round(hurdle, 5),
                raw_p_value_vs_baseline=round(r["raw_p_val_baseline"], 5),
                raw_p_value_vs_hurdle=round(r["raw_p_val_hurdle"], 5),
                adjusted_p_value_bonferroni=round(p_bonf, 5),
                adjusted_p_value_fdr=round(p_fdr, 5),
                ordinary_ev_per_dollar=round(ev_per_dollar, 4),
                is_statistically_significant=is_stat_sig,
                is_economically_viable=is_econ_viable,
                verdict=verdict,
                audit_notes=notes
            ))

        return final_results

    def _evaluate_single_hypothesis(
        self,
        df: pd.DataFrame,
        hyp: PredeclaredHypothesis,
        purge_overlap: bool = True
    ) -> Dict[str, Any]:
        """Evaluates one hypothesis across the dataframe with purged sampling."""
        dur = hyp.contract_duration
        contract_model = ContractOutcomeModel(duration_ticks=dur, entry_offset=1)
        outcomes_df = contract_model.compute_contract_outcomes(df)

        col = "runhigh_win" if hyp.target_direction == "RUNHIGH" else "runlow_win"
        outcomes = outcomes_df[col].values
        n = len(df)

        step = (dur + 1) if purge_overlap else 1
        eval_indices = list(range(25, n - (dur + 1), step))

        n_purged = len(eval_indices)
        n_cond = 0
        wins = 0
        all_uncond_wins = 0

        for idx in eval_indices:
            out_val = outcomes[idx]
            if out_val is None or math.isnan(out_val):
                continue

            all_uncond_wins += int(out_val)

            # Check if features match hypothesis requirements
            slice_df = df.iloc[max(0, idx - 50):idx + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)

            match = True
            for f_name, required_vals in hyp.feature_requirements.items():
                if feat_dict.get(f_name) not in required_vals:
                    match = False
                    break

            if match:
                n_cond += 1
                wins += int(out_val)

        uncond_rate = (all_uncond_wins / n_purged) if n_purged > 0 else (0.5 ** dur)
        win_rate = (wins / n_cond) if n_cond > 0 else 0.0

        # One-tailed binomial tests:
        # 1. H0: p <= uncond_rate
        # 2. H0: p <= economic_hurdle
        if n_cond > 0:
            raw_p_base = float(binomial_test_greater(wins, n_cond, p=uncond_rate))
            raw_p_hurdle = float(binomial_test_greater(wins, n_cond, p=hyp.economic_hurdle))
        else:
            raw_p_base = 1.0
            raw_p_hurdle = 1.0

        return {
            "n_purged": n_purged,
            "n_cond": n_cond,
            "wins": wins,
            "win_rate": win_rate,
            "uncond_baseline": uncond_rate,
            "raw_p_val_baseline": raw_p_base,
            "raw_p_val_hurdle": raw_p_hurdle
        }
