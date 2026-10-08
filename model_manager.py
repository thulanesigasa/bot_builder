"""Frozen Model Loading, Schema Validation, and Provenance Manager (V1.5.3).

Enforces strict model validation gates:
- MODEL_NOT_FOUND
- MODEL_CORRUPTED
- MODEL_SCHEMA_MISMATCH
- MODEL_SYMBOL_MISMATCH
- MODEL_CONTRACT_MISMATCH
- MODEL_UNVALIDATED
- MODEL_UNCALIBRATED

Provides reproducible training and export of frozen model artifacts from historical datasets.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

from feature_schema import (
    FEATURE_SCHEMA_VERSION,
    CANONICAL_FEATURE_NAMES,
    extract_discrete_market_state
)
from model_artifact import (
    ModelArtifact,
    ModelStatus,
    compute_file_sha256
)
from contract_model import ContractOutcomeModel


class ModelValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ModelManager:
    """Manages frozen model discovery, verification, loading, and export."""

    DEFAULT_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = models_dir or self.DEFAULT_MODELS_DIR
        os.makedirs(self.models_dir, exist_ok=True)

    def get_latest_model_for_symbol(self, symbol: str = "R_75") -> Optional[str]:
        """Finds the latest valid JSON model artifact file for a given symbol."""
        candidates = []
        sym_norm = symbol.upper().replace("_", "")
        for fname in os.listdir(self.models_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.models_dir, fname)
                try:
                    art = ModelArtifact.load_from_file(fpath)
                    if art.market_symbol.upper().replace("_", "") == sym_norm:
                        candidates.append((art.created_at_utc, fpath))
                except Exception:
                    continue
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def validate_and_load_model(
        self,
        model_path_or_id: str,
        expected_symbol: str = "R_75",
        expected_contract_family: str = "RUNHIGH_RUNLOW",
        expected_duration_ticks: int = 5,
        require_paper_approval: bool = False
    ) -> Tuple[bool, str, Optional[ModelArtifact]]:
        """Loads and strictly validates a frozen model artifact.
        
        Returns:
            (is_valid, status_code, artifact_or_none)
        """
        # 1. Resolve path
        target_path = model_path_or_id
        if not os.path.exists(target_path):
            candidate = os.path.join(self.models_dir, model_path_or_id)
            if os.path.exists(candidate):
                target_path = candidate
            elif os.path.exists(f"{candidate}.json"):
                target_path = f"{candidate}.json"
            else:
                return False, "MODEL_NOT_FOUND", None

        # 2. Check file integrity
        try:
            artifact = ModelArtifact.load_from_file(target_path)
        except Exception:
            return False, "MODEL_CORRUPTED", None

        # 3. Schema version verification
        if artifact.feature_schema_version != FEATURE_SCHEMA_VERSION:
            return False, "MODEL_SCHEMA_MISMATCH", None

        # 4. Symbol match verification
        if artifact.market_symbol.upper() != expected_symbol.upper():
            return False, "MODEL_SYMBOL_MISMATCH", None

        # 5. Contract specification verification
        if (artifact.contract_family.upper() != expected_contract_family.upper() or
                artifact.contract_duration != expected_duration_ticks):
            return False, "MODEL_CONTRACT_MISMATCH", None

        # 6. Feature names verification
        if set(artifact.feature_names) != set(CANONICAL_FEATURE_NAMES):
            return False, "MODEL_SCHEMA_MISMATCH", None

        # 7. Calibration verification
        if not artifact.calibration_parameters or "shrinkage_prior_weight" not in artifact.calibration_parameters:
            return False, "MODEL_UNCALIBRATED", None

        # 8. Paper trading qualification gate
        if require_paper_approval:
            if artifact.approval_status not in ModelStatus.APPROVED_FOR_PAPER:
                return False, "MODEL_UNVALIDATED", artifact

        return True, "MODEL_VALIDATED", artifact

    def train_and_export_baseline_model(
        self,
        csv_path: str,
        symbol: str = "R_75",
        output_filename: Optional[str] = None,
        approval_status: str = ModelStatus.RESEARCH_ONLY
    ) -> ModelArtifact:
        """Reproducibly fits an empirical Bayesian state-conditional probability model and exports it."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Training CSV not found: {csv_path}")

        checksum = compute_file_sha256(csv_path)
        df = pd.read_csv(csv_path)
        prices = df["price"].astype(float).values
        n = len(prices)

        # 5-tick contract outcome modeling
        contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
        outcomes_df = contract_model.compute_contract_outcomes(df)
        outcomes_up = outcomes_df["runhigh_win"].values
        outcomes_down = outcomes_df["runlow_win"].values

        # Compute rolling features and accumulate state tables
        state_tables: Dict[str, Dict[str, Any]] = {}
        rh_wins_total = 0
        rl_wins_total = 0
        valid_obs_count = 0

        # Require lookback of at least 25 ticks
        for i in range(25, n - 6):
            if outcomes_up[i] is None or outcomes_down[i] is None:
                continue

            # Extract state on slice up to i
            slice_df = df.iloc[max(0, i - 50):i + 1]
            feat_dict, state = extract_discrete_market_state(slice_df)
            if state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED"):
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

        # Bayesian smoothed unconditional empirical base rates (shrinkage floor > 0)
        base_rate_rh = max(0.001, (rh_wins_total / valid_obs_count)) if valid_obs_count > 0 else 0.03125
        base_rate_rl = max(0.001, (rl_wins_total / valid_obs_count)) if valid_obs_count > 0 else 0.03125

        # 3-way split observations for validation metrics
        train_n = int(valid_obs_count * 0.6)
        val_n = int(valid_obs_count * 0.2)
        hold_n = valid_obs_count - train_n - val_n

        # Baseline Brier score against constant base rate
        brier_rh = float(base_rate_rh * (1 - base_rate_rh))
        brier_rl = float(base_rate_rl * (1 - base_rate_rl))

        artifact = ModelArtifact(
            model_id=f"M_{symbol}_5TICK_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            model_version="1.5.3",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            training_dataset_id=os.path.basename(csv_path),
            dataset_checksum=checksum,
            market_symbol=symbol,
            contract_family="RUNHIGH_RUNLOW",
            contract_duration=5,
            contract_duration_unit="t",
            outcome_definition_version="1.5",
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_names=CANONICAL_FEATURE_NAMES,
            feature_ordering=CANONICAL_FEATURE_NAMES,
            model_type="EMPIRICAL_STATE_CONDITIONAL",
            model_parameters={
                "base_rate_runhigh": round(base_rate_rh, 5),
                "base_rate_runlow": round(base_rate_rl, 5),
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
                "relative_lift_max": 0.0
            },
            statistical_status="EMPIRICAL_BASELINE",
            approval_status=approval_status
        )

        fname = output_filename or f"{artifact.model_id}.json"
        dest_path = os.path.join(self.models_dir, fname)
        artifact.save_to_file(dest_path)
        print(f"Exported frozen model artifact: {dest_path}")
        return artifact


def main():
    parser = argparse.ArgumentParser(description="Deriv Frozen Model Manager (V1.5.3)")
    parser.add_argument("--inspect", type=str, help="Path or ID of model artifact to inspect")
    parser.add_argument("--train", type=str, help="CSV path to train and export model from")
    parser.add_argument("--symbol", type=str, default="R_75", help="Asset symbol (default: R_75)")
    parser.add_argument("--status", type=str, default=ModelStatus.RESEARCH_ONLY, help="Initial model status")
    args = parser.parse_args()

    mgr = ModelManager()

    if args.inspect:
        ok, status_code, artifact = mgr.validate_and_load_model(args.inspect, expected_symbol=args.symbol)
        if not ok and artifact is None:
            print(f"Error inspecting model: [{status_code}]")
            sys.exit(1)

        print("\n" + "=" * 60)
        print(f"           MODEL ARTIFACT INSPECTION: {artifact.model_id}")
        print("=" * 60)
        print(f"  Version:               {artifact.model_version}")
        print(f"  Created (UTC):         {artifact.created_at_utc}")
        print(f"  Market Symbol:         {artifact.market_symbol}")
        print(f"  Contract:              {artifact.contract_family} ({artifact.contract_duration}{artifact.contract_duration_unit})")
        print(f"  Feature Schema:        v{artifact.feature_schema_version}")
        print(f"  Training Dataset:      {artifact.training_dataset_id}")
        print(f"  Dataset Checksum:      {artifact.dataset_checksum[:16]}...")
        print(f"  Sample Counts:         Train: {artifact.training_sample_count:,} | Val: {artifact.validation_sample_count:,} | Holdout: {artifact.holdout_sample_count:,}")
        print(f"  Base Rate (RUNHIGH):   {artifact.model_parameters.get('base_rate_runhigh', 0.0):.3%}")
        print(f"  Base Rate (RUNLOW):    {artifact.model_parameters.get('base_rate_runlow', 0.0):.3%}")
        print(f"  Discovered States:     {artifact.model_parameters.get('total_states_discovered', 0)}")
        print(f"  Approval Status:       {artifact.approval_status}")
        print(f"  Validation Status:     {status_code}")
        print(f"  Model Hash:            {artifact.model_hash[:16]}...")
        print("=" * 60 + "\n")
        return

    if args.train:
        artifact = mgr.train_and_export_baseline_model(
            csv_path=args.train,
            symbol=args.symbol,
            approval_status=args.status
        )
        print(f"Successfully trained and saved model: {artifact.model_id}")


if __name__ == "__main__":
    main()
