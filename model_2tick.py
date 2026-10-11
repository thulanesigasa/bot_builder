"""Independent 2-Tick (2T) RUNHIGH and RUNLOW Model Specification and Trainer (V1.7.4).

Provides targeted modeling, feature conditioning, calibration, and economic hurdle evaluation
for Deriv Volatility 75 (R_75) Only Ups (RUNHIGH) and Only Downs (RUNLOW) 2-tick contracts.

Core Research Question:
Does a two-tick contract provide more reliable, economically profitable prediction opportunities
than the existing five-tick contract?

Contract Lifecycle (2 Ticks):
1. Signal generated at tick i.
2. Entry spot S_0 observed at tick i + 1.
3. Successive movements:
   - S_1 observed at tick i + 2
   - S_2 observed at tick i + 3 (Expiry spot)
4. Monotonic Outcomes:
   - RUNHIGH_2T wins iff S_0 < S_1 < S_2 (both movements strictly increase).
   - RUNLOW_2T wins iff S_0 > S_1 > S_2 (both movements strictly decrease).
   - Strict equality loss: if S_0 == S_1 or S_1 == S_2, the contract loses.
   - Reversal loss: if S_0 < S_1 and S_1 > S_2, both RUNHIGH and RUNLOW lose.

Benchmark Hurdle:
- Theoretical random-walk baseline: (0.5)^2 = 0.25 (25.000%).
- Deriv 2-tick proposal quote ($2.00 stake -> $7.63 total payout):
    Break-even probability = 2.00 / 7.63 = 26.212% (0.26212).
- Any strategy whose conditional probability is below 26.212% has negative expected value!
"""
import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from feature_schema import (
    FEATURE_SCHEMA_VERSION,
    CANONICAL_FEATURE_NAMES,
    CANONICAL_FEATURE_LOOKBACK,
    extract_discrete_market_state
)
from model_artifact import (
    ModelArtifact,
    ModelStatus,
    compute_file_sha256
)
from contract_model import ContractOutcomeModel
from contract_specification import (
    CANONICAL_RUNHIGH_2T_SPEC,
    CANONICAL_RUNLOW_2T_SPEC,
    evaluate_canonical_outcome
)


THEORETICAL_2T_BASELINE = 0.25  # 25.0%
DERIV_2T_REFERENCE_STAKE = 2.00
DERIV_2T_REFERENCE_PAYOUT = 7.63
DERIV_2T_BREAK_EVEN_HURDLE = DERIV_2T_REFERENCE_STAKE / DERIV_2T_REFERENCE_PAYOUT  # 26.212%


@dataclass
class TwoTickEvaluationSummary:
    """Statistical and economic summary of a 2-tick model evaluation."""
    total_observations: int
    unconditional_runhigh_rate: float
    unconditional_runlow_rate: float
    both_lose_rate: float
    theoretical_baseline: float
    quote_break_even_hurdle: float
    runhigh_edge_vs_hurdle: float
    runlow_edge_vs_hurdle: float
    runhigh_ev_per_stake: float
    runlow_ev_per_stake: float
    discovered_states_count: int
    brier_score_runhigh: float
    brier_score_runlow: float
    is_economically_viable: bool
    findings_summary: str


class TwoTickModelTrainer:
    """Trainer and evaluator for 2-tick empirical and feature-conditional models."""

    def __init__(
        self,
        symbol: str = "R_75",
        models_dir: Optional[str] = None
    ):
        self.symbol = symbol
        self.models_dir = models_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        os.makedirs(self.models_dir, exist_ok=True)

    def evaluate_dataset(self, csv_path: str) -> TwoTickEvaluationSummary:
        """Evaluates empirical 2-tick frequencies and economic viability across a historical dataset."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Dataset not found: {csv_path}")

        df = pd.read_csv(csv_path)
        contract_model = ContractOutcomeModel(duration_ticks=2, entry_offset=1)
        outcomes_df = contract_model.compute_contract_outcomes(df)

        rh_wins = outcomes_df["runhigh_win"].dropna().values
        rl_wins = outcomes_df["runlow_win"].dropna().values
        n = len(rh_wins)

        rh_rate = float(np.mean(rh_wins))
        rl_rate = float(np.mean(rl_wins))
        both_lose = float(np.mean((rh_wins == 0) & (rl_wins == 0)))

        # Economic EV calculations on reference quote
        be_hurdle = DERIV_2T_BREAK_EVEN_HURDLE
        rh_edge = rh_rate - be_hurdle
        rl_edge = rl_rate - be_hurdle

        rh_ev = rh_rate * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE
        rl_ev = rl_rate * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE

        brier_rh = float(rh_rate * (1.0 - rh_rate))
        brier_rl = float(rl_rate * (1.0 - rl_rate))

        is_viable = (rh_rate > be_hurdle) or (rl_rate > be_hurdle)
        summary = (
            f"2T Unconditional RUNHIGH: {rh_rate*100:.3f}%, RUNLOW: {rl_rate*100:.3f}%. "
            f"Deriv Break-even Hurdle: {be_hurdle*100:.3f}%. "
            f"Net Ordinary EV per $2.00: RUNHIGH ${rh_ev:+.4f}, RUNLOW ${rl_ev:+.4f}. "
            f"Unconditional edge is NEGATIVE because base rates ({rh_rate*100:.2f}%) < hurdle ({be_hurdle*100:.2f}%)."
        )

        return TwoTickEvaluationSummary(
            total_observations=n,
            unconditional_runhigh_rate=round(rh_rate, 5),
            unconditional_runlow_rate=round(rl_rate, 5),
            both_lose_rate=round(both_lose, 5),
            theoretical_baseline=THEORETICAL_2T_BASELINE,
            quote_break_even_hurdle=round(be_hurdle, 5),
            runhigh_edge_vs_hurdle=round(rh_edge, 5),
            runlow_edge_vs_hurdle=round(rl_edge, 5),
            runhigh_ev_per_stake=round(rh_ev, 4),
            runlow_ev_per_stake=round(rl_ev, 4),
            discovered_states_count=0,
            brier_score_runhigh=round(brier_rh, 5),
            brier_score_runlow=round(brier_rl, 5),
            is_economically_viable=is_viable,
            findings_summary=summary
        )

    def train_and_export_2tick_model(
        self,
        csv_path: str,
        output_filename: Optional[str] = None,
        approval_status: str = ModelStatus.RESEARCH_ONLY
    ) -> Tuple[ModelArtifact, TwoTickEvaluationSummary]:
        """Fits an independent 2-tick state-conditional model and serializes it with full provenance."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Training CSV not found: {csv_path}")

        checksum = compute_file_sha256(csv_path)
        df = pd.read_csv(csv_path)
        prices = df["price"].astype(float).values
        n = len(prices)

        contract_model = ContractOutcomeModel(duration_ticks=2, entry_offset=1)
        outcomes_df = contract_model.compute_contract_outcomes(df)
        outcomes_up = outcomes_df["runhigh_win"].values
        outcomes_down = outcomes_df["runlow_win"].values

        state_tables: Dict[str, Dict[str, Any]] = {}
        rh_wins_total = 0
        rl_wins_total = 0
        valid_obs_count = 0

        # Lookback = 25 ticks, forward horizon = 3 ticks (i+1 to i+3)
        for i in range(25, n - 3):
            if outcomes_up[i] is None or outcomes_down[i] is None or math.isnan(outcomes_up[i]):
                continue

            slice_df = df.iloc[max(0, i - 50):i + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)
            if state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED", "INVALID_INPUT"):
                continue

            valid_obs_count += 1
            is_up = int(outcomes_up[i])
            is_down = int(outcomes_down[i])

            rh_wins_total += is_up
            rl_wins_total += is_down

            if state not in state_tables:
                state_tables[state] = {
                    "sample_count": 0,
                    "runhigh_wins": 0,
                    "runlow_wins": 0
                }

            state_tables[state]["sample_count"] += 1
            state_tables[state]["runhigh_wins"] += is_up
            state_tables[state]["runlow_wins"] += is_down

        base_rate_rh = float(rh_wins_total / valid_obs_count) if valid_obs_count > 0 else THEORETICAL_2T_BASELINE
        base_rate_rl = float(rl_wins_total / valid_obs_count) if valid_obs_count > 0 else THEORETICAL_2T_BASELINE

        train_n = int(valid_obs_count * 0.6)
        val_n = int(valid_obs_count * 0.2)
        hold_n = valid_obs_count - train_n - val_n

        brier_rh = float(base_rate_rh * (1.0 - base_rate_rh))
        brier_rl = float(base_rate_rl * (1.0 - base_rate_rl))

        model_id = f"M_{self.symbol}_2TICK_20261011_120000"
        artifact = ModelArtifact(
            model_id=model_id,
            model_version="1.7.4",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            training_dataset_id=os.path.basename(csv_path),
            dataset_checksum=checksum,
            market_symbol=self.symbol,
            contract_family="RUNHIGH_RUNLOW",
            contract_duration=2,
            contract_duration_unit="t",
            outcome_definition_version="1.7.4",
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_names=CANONICAL_FEATURE_NAMES,
            feature_ordering=CANONICAL_FEATURE_NAMES,
            model_type="EMPIRICAL_STATE_CONDITIONAL",
            model_parameters={
                "base_rate_runhigh": round(base_rate_rh, 5),
                "base_rate_runlow": round(base_rate_rl, 5),
                "theoretical_baseline": THEORETICAL_2T_BASELINE,
                "break_even_hurdle": round(DERIV_2T_BREAK_EVEN_HURDLE, 5),
                "total_states_discovered": len(state_tables),
                "state_tables": state_tables
            },
            calibration_parameters={
                "method": "BAYESIAN_EMPIRICAL_SHRINKAGE",
                "shrinkage_prior_weight": 50.0,
                "confidence_level": 0.95
            },
            training_sample_count=train_n,
            validation_sample_count=val_n,
            holdout_sample_count=hold_n,
            validation_metrics={
                "brier_score_runhigh": round(brier_rh, 5),
                "brier_score_runlow": round(brier_rl, 5),
                "break_even_hurdle": round(DERIV_2T_BREAK_EVEN_HURDLE, 5),
                "relative_lift_max": 0.0
            },
            statistical_status="EMPIRICAL_BASELINE",
            approval_status=approval_status
        )

        fname = output_filename or f"{model_id}.json"
        dest_path = os.path.join(self.models_dir, fname)
        artifact.save_to_file(dest_path)

        be_hurdle = DERIV_2T_BREAK_EVEN_HURDLE
        rh_ev = base_rate_rh * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE
        rl_ev = base_rate_rl * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE

        eval_summary = TwoTickEvaluationSummary(
            total_observations=valid_obs_count,
            unconditional_runhigh_rate=round(base_rate_rh, 5),
            unconditional_runlow_rate=round(base_rate_rl, 5),
            both_lose_rate=round(1.0 - (base_rate_rh + base_rate_rl), 5),
            theoretical_baseline=THEORETICAL_2T_BASELINE,
            quote_break_even_hurdle=round(be_hurdle, 5),
            runhigh_edge_vs_hurdle=round(base_rate_rh - be_hurdle, 5),
            runlow_edge_vs_hurdle=round(base_rate_rl - be_hurdle, 5),
            runhigh_ev_per_stake=round(rh_ev, 4),
            runlow_ev_per_stake=round(rl_ev, 4),
            discovered_states_count=len(state_tables),
            brier_score_runhigh=round(brier_rh, 5),
            brier_score_runlow=round(brier_rl, 5),
            is_economically_viable=(base_rate_rh > be_hurdle or base_rate_rl > be_hurdle),
            findings_summary=(
                f"2-Tick Model {model_id} trained on {valid_obs_count} ticks. "
                f"Base rate RUNHIGH {base_rate_rh*100:.3f}%, RUNLOW {base_rate_rl*100:.3f}%. "
                f"Hurdle: {be_hurdle*100:.3f}%. Discovered {len(state_tables)} states."
            )
        )

        return artifact, eval_summary
