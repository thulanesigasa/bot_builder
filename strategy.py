"""Probability-driven Market State Strategy Engine for RUNHIGH / RUNLOW.

Replaces hardcoded indicator rules with statistical conditioning:
1. Observes market state s (composite of streak, momentum, volatility, range).
2. Measures historical conditional probability:
   P(RUNHIGH | s) and P(RUNLOW | s).
3. Compares against exact quote implied probability:
   P_implied = Stake / Total Return (e.g. $2 / $61.03 = 3.28%).
4. Calculates Expected Value (EV) and statistical significance (z vs implied).
5. Emits signal ONLY when positive EV + proven statistical edge exists. Otherwise: NO_TRADE.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
from quote_engine import QuoteEngine
from probability import calculate_confidence_interval, calculate_z_score, calculate_ev_ci


@dataclass
class RegimeEdgeProfile:
    regime_name: str
    sample_size: int
    runhigh_wins: int
    runhigh_prob: float
    runhigh_edge: float
    runhigh_z: float
    runhigh_ev: float
    runlow_wins: int
    runlow_prob: float
    runlow_edge: float
    runlow_z: float
    runlow_ev: float
    recommended_action: str  # 'RUNHIGH', 'RUNLOW', or 'NO_TRADE'
    has_positive_edge: bool


class MarketStateProbabilityModel:
    """Discovers and evaluates state-conditional probabilities of uninterrupted 5-tick runs."""

    def __init__(
        self,
        min_sample_size: int = 30,
        z_threshold: float = 2.0,  # Minimum z-score to declare an edge candidate
        regime_col: str = "market_regime"
    ):
        self.min_sample_size = min_sample_size
        self.z_threshold = z_threshold
        self.regime_col = regime_col
        self.profiles: Dict[str, RegimeEdgeProfile] = {}
        self.baseline_runhigh_prob: float = 0.03125
        self.baseline_runlow_prob: float = 0.03125

    def fit(self, train_df: pd.DataFrame, quote_engine: QuoteEngine) -> Dict[str, RegimeEdgeProfile]:
        """Learns conditional run probabilities across all observed market states in training data."""
        up_quote = quote_engine.get_quote("UP")
        down_quote = quote_engine.get_quote("DOWN")

        if up_quote is None or down_quote is None:
            raise ValueError("QuoteEngine must have valid UP and DOWN quotes to fit probability model.")

        up_implied = up_quote.implied_probability
        down_implied = down_quote.implied_probability

        # Calculate unconditional baselines
        self.baseline_runhigh_prob = float(train_df["runhigh_win"].mean())
        self.baseline_runlow_prob = float(train_df["runlow_win"].mean())

        self.profiles.clear()
        for regime, grp in train_df.groupby(self.regime_col):
            n = len(grp)
            if n < self.min_sample_size:
                continue

            rh_wins = int(grp["runhigh_win"].sum())
            rh_prob = rh_wins / n
            rh_edge = rh_prob - up_implied
            rh_z = calculate_z_score(rh_prob, up_implied, n)
            rh_ev, _, _ = quote_engine.calculate_expected_value(rh_prob, up_quote.stake, up_quote.payout)

            rl_wins = int(grp["runlow_win"].sum())
            rl_prob = rl_wins / n
            rl_edge = rl_prob - down_implied
            rl_z = calculate_z_score(rl_prob, down_implied, n)
            rl_ev, _, _ = quote_engine.calculate_expected_value(rl_prob, down_quote.stake, down_quote.payout)

            # Determine signal action based on positive edge and significance
            action = "NO_TRADE"
            has_edge = False
            if rh_edge > 0 and rh_z >= self.z_threshold and rh_ev > 0 and rh_ev >= rl_ev:
                action = "RUNHIGH"
                has_edge = True
            elif rl_edge > 0 and rl_z >= self.z_threshold and rl_ev > 0 and rl_ev > rh_ev:
                action = "RUNLOW"
                has_edge = True

            self.profiles[regime] = RegimeEdgeProfile(
                regime_name=regime,
                sample_size=n,
                runhigh_wins=rh_wins,
                runhigh_prob=rh_prob,
                runhigh_edge=rh_edge,
                runhigh_z=rh_z,
                runhigh_ev=rh_ev,
                runlow_wins=rl_wins,
                runlow_prob=rl_prob,
                runlow_edge=rl_edge,
                runlow_z=rl_z,
                runlow_ev=rl_ev,
                recommended_action=action,
                has_positive_edge=has_edge
            )

        return self.profiles

    def predict_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Applies learned regime edge profiles to emit signals for evaluation."""
        if self.regime_col not in df.columns:
            out = pd.DataFrame(index=df.index)
            out["signal"] = "NO_TRADE"
            out["estimated_prob"] = 0.0
            out["expected_value"] = 0.0
            return out

        reg_series = df[self.regime_col]
        action_map = {k: v.recommended_action for k, v in self.profiles.items() if v.has_positive_edge}
        prob_map = {
            k: (v.runhigh_prob if v.recommended_action == "RUNHIGH" else v.runlow_prob)
            for k, v in self.profiles.items() if v.has_positive_edge
        }
        ev_map = {
            k: (v.runhigh_ev if v.recommended_action == "RUNHIGH" else v.runlow_ev)
            for k, v in self.profiles.items() if v.has_positive_edge
        }

        signals = reg_series.map(action_map).fillna("NO_TRADE")
        est_probs = reg_series.map(prob_map).fillna(0.0)
        expected_values = reg_series.map(ev_map).fillna(0.0)

        out = pd.DataFrame(index=df.index)
        out["signal"] = signals
        out["estimated_prob"] = est_probs
        out["expected_value"] = expected_values
        return out



# Backward-compatible setup dictionary mappings for comparative research
CONTINUATION_SETUPS = {
    "cont: streak>=3 UP -> RUNHIGH": (lambda f: f.streak >= 3, "runhigh"),
    "cont: streak>=3 DOWN -> RUNLOW": (lambda f: f.streak <= -3, "runlow"),
    "cont: streak>=5 UP -> RUNHIGH": (lambda f: f.streak >= 5, "runhigh"),
    "cont: streak>=5 DOWN -> RUNLOW": (lambda f: f.streak <= -5, "runlow"),
    "cont: velocity net5>=3 -> RUNHIGH": (lambda f: (f.net5 >= 3) & (f.sign > 0), "runhigh"),
    "cont: velocity net5<=-3 -> RUNLOW": (lambda f: (f.net5 <= -3) & (f.sign < 0), "runlow"),
    "cont: trend net10>=4 -> RUNHIGH": (lambda f: (f.net10 >= 4) & (f.mom5 > 0), "runhigh"),
    "cont: trend net10<=-4 -> RUNLOW": (lambda f: (f.net10 <= -4) & (f.mom5 < 0), "runlow"),
    "cont: accelerating mom UP -> RUNHIGH": (lambda f: (f.mom5 > 1.0) & (f.accel3 > 0), "runhigh"),
    "cont: accelerating mom DOWN -> RUNLOW": (lambda f: (f.mom5 < -1.0) & (f.accel3 < 0), "runlow"),
}

REVERSAL_SETUPS = {
    "rev: streak>=4 UP -> RUNLOW": (lambda f: f.streak >= 4, "runlow"),
    "rev: streak>=4 DOWN -> RUNHIGH": (lambda f: f.streak <= -4, "runhigh"),
    "rev: streak>=6 UP -> RUNLOW": (lambda f: f.streak >= 6, "runlow"),
    "rev: streak>=6 DOWN -> RUNHIGH": (lambda f: f.streak <= -6, "runhigh"),
    "rev: first DOWN after uptrend -> RUNLOW": (lambda f: f.first_down_after_uptrend, "runlow"),
    "rev: first UP after downtrend -> RUNHIGH": (lambda f: f.first_up_after_downtrend, "runhigh"),
    "rev: exhaust mom>1.5 accel<0 -> RUNLOW": (lambda f: (f.mom5 > 1.5) & (f.accel3 < 0), "runlow"),
    "rev: exhaust mom<-1.5 accel>0 -> RUNHIGH": (lambda f: (f.mom5 < -1.5) & (f.accel3 > 0), "runhigh"),
    "rev: range high bounce -> RUNLOW": (lambda f: (f.range_position >= 0.80) & (f.sign < 0), "runlow"),
    "rev: range low bounce -> RUNHIGH": (lambda f: (f.range_position <= 0.20) & (f.sign > 0), "runhigh"),
}

ALL_SETUPS = {**CONTINUATION_SETUPS, **REVERSAL_SETUPS}
SETUPS = ALL_SETUPS


class ContinuationEngine:
    """Helper wrapper for evaluating continuation setups."""
    def __init__(self, setups: Optional[Dict] = None):
        self.setups = setups or CONTINUATION_SETUPS

    def scan_signals(self, features: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=features.index)
        for name, (fn, side) in self.setups.items():
            out[name] = fn(features)
        return out


class ReversalEngine:
    """Helper wrapper for evaluating reversal setups."""
    def __init__(self, setups: Optional[Dict] = None):
        self.setups = setups or REVERSAL_SETUPS

    def scan_signals(self, features: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=features.index)
        for name, (fn, side) in self.setups.items():
            out[name] = fn(features)
        return out
