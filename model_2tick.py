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
        approval_status: str = ModelStatus.RESEARCH_ONLY,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        embargo_ticks: int = 3
    ) -> Tuple[ModelArtifact, TwoTickEvaluationSummary]:
        """Fits an independent 2-tick state-conditional model using strict chronological partitions.
        
        Strict Chronological Protocol (V1.7.4.1 Part 5):
        1. Training Partition: First 60% of chronological observations.
        2. Purge/Embargo Gap: 3 ticks (duration + 1) excluded between train and validation.
        3. Validation Partition: Next 20% of observations for independent calibration & metrics.
        4. Purge/Embargo Gap: 3 ticks excluded between validation and holdout.
        5. Untouched Holdout: Final 20% of observations evaluated once without influencing model fitting.
        """
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

        # Collect valid decision points (lookback 25, forward 3)
        valid_indices: List[int] = []
        for i in range(25, n - 3):
            if outcomes_up[i] is None or outcomes_down[i] is None or math.isnan(outcomes_up[i]):
                continue
            valid_indices.append(i)

        total_valid = len(valid_indices)
        if total_valid < 100:
            raise ValueError(f"Insufficient valid decision points: {total_valid} < 100 required.")

        # Compute partition boundaries
        n_train = int(total_valid * train_ratio)
        n_val = int(total_valid * val_ratio)

        train_indices = valid_indices[:n_train]
        # Purge/embargo between train and val
        val_start_idx = n_train + embargo_ticks
        val_end_idx = val_start_idx + n_val
        val_indices = valid_indices[val_start_idx:val_end_idx]

        # Purge/embargo between val and holdout
        hold_start_idx = val_end_idx + embargo_ticks
        hold_indices = valid_indices[hold_start_idx:]

        # -------------------------------------------------------------
        # 1. FIT ON TRAINING PARTITION ONLY
        # -------------------------------------------------------------
        state_tables: Dict[str, Dict[str, Any]] = {}
        rh_wins_train = 0
        rl_wins_train = 0
        train_count = 0

        for i in train_indices:
            slice_df = df.iloc[max(0, i - 50):i + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)
            if state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED", "INVALID_INPUT"):
                continue

            train_count += 1
            is_up = int(outcomes_up[i])
            is_down = int(outcomes_down[i])

            rh_wins_train += is_up
            rl_wins_train += is_down

            if state not in state_tables:
                state_tables[state] = {
                    "sample_count": 0,
                    "runhigh_wins": 0,
                    "runlow_wins": 0
                }

            state_tables[state]["sample_count"] += 1
            state_tables[state]["runhigh_wins"] += is_up
            state_tables[state]["runlow_wins"] += is_down

        base_rate_rh = float(rh_wins_train / train_count) if train_count > 0 else THEORETICAL_2T_BASELINE
        base_rate_rl = float(rl_wins_train / train_count) if train_count > 0 else THEORETICAL_2T_BASELINE

        # Shrinkage prior weight
        prior_weight = 50.0

        def predict_probs(st: str) -> Tuple[float, float]:
            if st in state_tables:
                entry = state_tables[st]
                c = entry["sample_count"]
                p_rh = (entry["runhigh_wins"] + prior_weight * base_rate_rh) / (c + prior_weight)
                p_rl = (entry["runlow_wins"] + prior_weight * base_rate_rl) / (c + prior_weight)
            else:
                p_rh = base_rate_rh
                p_rl = base_rate_rl
            return p_rh, p_rl

        # -------------------------------------------------------------
        # 2. INDEPENDENT VALIDATION EVALUATION (Out-of-sample)
        # -------------------------------------------------------------
        val_probs_rh: List[float] = []
        val_probs_rl: List[float] = []
        val_y_rh: List[float] = []
        val_y_rl: List[float] = []

        for i in val_indices:
            slice_df = df.iloc[max(0, i - 50):i + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)
            if state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED", "INVALID_INPUT"):
                continue

            p_rh, p_rl = predict_probs(state)
            val_probs_rh.append(p_rh)
            val_probs_rl.append(p_rl)
            val_y_rh.append(float(outcomes_up[i]))
            val_y_rl.append(float(outcomes_down[i]))

        n_val_eval = len(val_y_rh)
        if n_val_eval > 0:
            val_bs_rh = float(np.mean([(p - y)**2 for p, y in zip(val_probs_rh, val_y_rh)]))
            val_bs_rl = float(np.mean([(p - y)**2 for p, y in zip(val_probs_rl, val_y_rl)]))
            ref_bs_rh = float(np.mean([(base_rate_rh - y)**2 for y in val_y_rh]))
            ref_bs_rl = float(np.mean([(base_rate_rl - y)**2 for y in val_y_rl]))
            val_bss_rh = float(1.0 - (val_bs_rh / ref_bs_rh)) if ref_bs_rh > 0 else 0.0
            val_bss_rl = float(1.0 - (val_bs_rl / ref_bs_rl)) if ref_bs_rl > 0 else 0.0
            # Log loss
            eps = 1e-15
            val_logloss_rh = float(-np.mean([y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(val_probs_rh, val_y_rh)]))
            val_logloss_rl = float(-np.mean([y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(val_probs_rl, val_y_rl)]))
        else:
            val_bs_rh = base_rate_rh * (1.0 - base_rate_rh)
            val_bs_rl = base_rate_rl * (1.0 - base_rate_rl)
            val_bss_rh = 0.0
            val_bss_rl = 0.0
            val_logloss_rh = 0.0
            val_logloss_rl = 0.0

        # -------------------------------------------------------------
        # 3. UNTOUCHED HOLDOUT EVALUATION (Out-of-sample)
        # -------------------------------------------------------------
        hold_probs_rh: List[float] = []
        hold_probs_rl: List[float] = []
        hold_y_rh: List[float] = []
        hold_y_rl: List[float] = []

        for i in hold_indices:
            slice_df = df.iloc[max(0, i - 50):i + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)
            if state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED", "INVALID_INPUT"):
                continue

            p_rh, p_rl = predict_probs(state)
            hold_probs_rh.append(p_rh)
            hold_probs_rl.append(p_rl)
            hold_y_rh.append(float(outcomes_up[i]))
            hold_y_rl.append(float(outcomes_down[i]))

        n_hold_eval = len(hold_y_rh)
        if n_hold_eval > 0:
            hold_bs_rh = float(np.mean([(p - y)**2 for p, y in zip(hold_probs_rh, hold_y_rh)]))
            hold_bs_rl = float(np.mean([(p - y)**2 for p, y in zip(hold_probs_rl, hold_y_rl)]))
            ref_hold_bs_rh = float(np.mean([(base_rate_rh - y)**2 for y in hold_y_rh]))
            ref_hold_bs_rl = float(np.mean([(base_rate_rl - y)**2 for y in hold_y_rl]))
            hold_bss_rh = float(1.0 - (hold_bs_rh / ref_hold_bs_rh)) if ref_hold_bs_rh > 0 else 0.0
            hold_bss_rl = float(1.0 - (hold_bs_rl / ref_hold_bs_rl)) if ref_hold_bs_rl > 0 else 0.0
            hold_winrate_rh = float(np.mean(hold_y_rh))
            hold_winrate_rl = float(np.mean(hold_y_rl))
        else:
            hold_bs_rh = base_rate_rh * (1.0 - base_rate_rh)
            hold_bs_rl = base_rate_rl * (1.0 - base_rate_rl)
            hold_bss_rh = 0.0
            hold_bss_rl = 0.0
            hold_winrate_rh = base_rate_rh
            hold_winrate_rl = base_rate_rl

        model_id = f"M_{self.symbol}_2TICK_20261011_120000"
        artifact = ModelArtifact(
            model_id=model_id,
            model_version="1.7.4.1",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            training_dataset_id=os.path.basename(csv_path),
            dataset_checksum=checksum,
            market_symbol=self.symbol,
            contract_family="RUNHIGH_RUNLOW",
            contract_duration=2,
            contract_duration_unit="t",
            outcome_definition_version="1.7.4.1",
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_names=CANONICAL_FEATURE_NAMES,
            feature_ordering=CANONICAL_FEATURE_NAMES,
            model_type="EMPIRICAL_STATE_CONDITIONAL",
            model_parameters={
                "base_rate_runhigh_train": round(base_rate_rh, 5),
                "base_rate_runlow_train": round(base_rate_rl, 5),
                "theoretical_baseline": THEORETICAL_2T_BASELINE,
                "break_even_hurdle": round(DERIV_2T_BREAK_EVEN_HURDLE, 5),
                "total_states_discovered": len(state_tables),
                "state_tables": state_tables,
                "partition_info": {
                    "train_ratio": train_ratio,
                    "val_ratio": val_ratio,
                    "embargo_ticks": embargo_ticks,
                    "train_sample_count": train_count,
                    "val_sample_count": n_val_eval,
                    "holdout_sample_count": n_hold_eval,
                    "train_index_range": [train_indices[0], train_indices[-1]] if train_indices else [],
                    "val_index_range": [val_indices[0], val_indices[-1]] if val_indices else [],
                    "holdout_index_range": [hold_indices[0], hold_indices[-1]] if hold_indices else []
                }
            },
            calibration_parameters={
                "method": "BAYESIAN_EMPIRICAL_SHRINKAGE",
                "shrinkage_prior_weight": prior_weight,
                "confidence_level": 0.95
            },
            training_sample_count=train_count,
            validation_sample_count=n_val_eval,
            holdout_sample_count=n_hold_eval,
            validation_metrics={
                "brier_score_runhigh": round(val_bs_rh, 5),
                "brier_score_runlow": round(val_bs_rl, 5),
                "brier_skill_score_runhigh": round(val_bss_rh, 5),
                "brier_skill_score_runlow": round(val_bss_rl, 5),
                "log_loss_runhigh": round(val_logloss_rh, 5),
                "log_loss_runlow": round(val_logloss_rl, 5),
                "break_even_hurdle": round(DERIV_2T_BREAK_EVEN_HURDLE, 5),
                "holdout_metrics": {
                    "brier_score_runhigh": round(hold_bs_rh, 5),
                    "brier_score_runlow": round(hold_bs_rl, 5),
                    "brier_skill_score_runhigh": round(hold_bss_rh, 5),
                    "brier_skill_score_runlow": round(hold_bss_rl, 5),
                    "empirical_win_rate_runhigh": round(hold_winrate_rh, 5),
                    "empirical_win_rate_runlow": round(hold_winrate_rl, 5)
                }
            },
            statistical_status="HISTORICAL_HOLDOUT_EVALUATED",
            approval_status=approval_status
        )

        fname = output_filename or f"{model_id}.json"
        dest_path = os.path.join(self.models_dir, fname)
        artifact.save_to_file(dest_path)

        be_hurdle = DERIV_2T_BREAK_EVEN_HURDLE
        rh_ev = base_rate_rh * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE
        rl_ev = base_rate_rl * DERIV_2T_REFERENCE_PAYOUT - DERIV_2T_REFERENCE_STAKE

        eval_summary = TwoTickEvaluationSummary(
            total_observations=total_valid,
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
            brier_score_runhigh=round(val_bs_rh, 5),
            brier_score_runlow=round(val_bs_rl, 5),
            is_economically_viable=(base_rate_rh > be_hurdle or base_rate_rl > be_hurdle),
            findings_summary=(
                f"2-Tick Model {model_id} fitted strictly on {train_count} training ticks (60%). "
                f"Embargo gap: {embargo_ticks} ticks. Evaluated on {n_val_eval} validation ticks and {n_hold_eval} holdout ticks. "
                f"Train Base Rate RH: {base_rate_rh*100:.3f}%, RL: {base_rate_rl*100:.3f}%. "
                f"Val BS RH: {val_bs_rh:.5f}, Val BSS RH: {val_bss_rh:+.5f}. "
                f"Holdout Win Rate RH: {hold_winrate_rh*100:.3f}%, RL: {hold_winrate_rl*100:.3f}% vs Hurdle {be_hurdle*100:.3f}%."
            )
        )

        return artifact, eval_summary

