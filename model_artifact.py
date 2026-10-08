"""Frozen Model Artifact Specification and Serialization (V1.5.3).

Provides transparent, human-readable, JSON-based storage for statistical prediction models.
Strictly prohibits arbitrary code execution or unpickling.
Records complete data provenance, parameter specifications, calibration curves, and qualification status.
"""
import hashlib
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from feature_schema import FEATURE_SCHEMA_VERSION, CANONICAL_FEATURE_NAMES


class ModelStatus:
    RESEARCH_ONLY = "RESEARCH_ONLY"
    TRAINED = "TRAINED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    HOLDOUT_FAILED = "HOLDOUT_FAILED"
    CALIBRATION_FAILED = "CALIBRATION_FAILED"
    CANDIDATE = "CANDIDATE"
    VALIDATED_RESEARCH = "VALIDATED_RESEARCH"
    FORWARD_VALIDATION_PENDING = "FORWARD_VALIDATION_PENDING"
    FORWARD_VALIDATED = "FORWARD_VALIDATED"

    ALL_STATUSES = {
        RESEARCH_ONLY,
        TRAINED,
        VALIDATION_FAILED,
        HOLDOUT_FAILED,
        CALIBRATION_FAILED,
        CANDIDATE,
        VALIDATED_RESEARCH,
        FORWARD_VALIDATION_PENDING,
        FORWARD_VALIDATED
    }

    # Statuses permitted to authorize simulated/paper trades in PAPER mode
    APPROVED_FOR_PAPER = {
        VALIDATED_RESEARCH,
        FORWARD_VALIDATED
    }


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA256 checksum of a file for cryptographic dataset provenance."""
    if not os.path.exists(filepath):
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class ModelArtifact:
    model_id: str
    model_version: str
    created_at_utc: str
    training_dataset_id: str
    dataset_checksum: str
    market_symbol: str
    contract_family: str  # 'RUNHIGH_RUNLOW'
    contract_duration: int  # 5
    contract_duration_unit: str  # 't'
    outcome_definition_version: str  # '1.5'
    feature_schema_version: str  # '1.5.3'
    feature_names: List[str]
    feature_ordering: List[str]
    model_type: str  # 'EMPIRICAL_STATE_CONDITIONAL'
    model_parameters: Dict[str, Any]  # State conditional probability tables & priors
    calibration_parameters: Dict[str, Any]  # Calibration metrics & shrinkage hyperparams
    training_sample_count: int
    validation_sample_count: int
    holdout_sample_count: int
    validation_metrics: Dict[str, Any]
    statistical_status: str
    approval_status: str
    model_hash: str = ""
    required_lookback: int = 25

    def calculate_hash(self) -> str:
        """Computes deterministic SHA256 of the core specification and parameters."""
        spec_dict = {
            "model_id": self.model_id,
            "market_symbol": self.market_symbol,
            "contract_family": self.contract_family,
            "contract_duration": self.contract_duration,
            "feature_schema_version": self.feature_schema_version,
            "model_parameters": self.model_parameters,
            "calibration_parameters": self.calibration_parameters,
            "approval_status": self.approval_status
        }
        serialized = json.dumps(spec_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Converts artifact to dictionary representation."""
        if not self.model_hash:
            self.model_hash = self.calculate_hash()
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serializes artifact to JSON string, injecting hash."""
        if not self.model_hash:
            self.model_hash = self.calculate_hash()
        return json.dumps(asdict(self), indent=indent)

    def save_to_file(self, filepath: str):
        """Saves artifact safely to JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        self.model_hash = self.calculate_hash()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelArtifact":
        """Instantiates from dictionary representation."""
        return cls(
            model_id=str(data["model_id"]),
            model_version=str(data["model_version"]),
            created_at_utc=str(data["created_at_utc"]),
            training_dataset_id=str(data["training_dataset_id"]),
            dataset_checksum=str(data["dataset_checksum"]),
            market_symbol=str(data["market_symbol"]),
            contract_family=str(data["contract_family"]),
            contract_duration=int(data["contract_duration"]),
            contract_duration_unit=str(data.get("contract_duration_unit", "t")),
            outcome_definition_version=str(data.get("outcome_definition_version", "1.5")),
            feature_schema_version=str(data.get("feature_schema_version", FEATURE_SCHEMA_VERSION)),
            feature_names=list(data["feature_names"]),
            feature_ordering=list(data["feature_ordering"]),
            model_type=str(data["model_type"]),
            model_parameters=dict(data["model_parameters"]),
            calibration_parameters=dict(data.get("calibration_parameters", {})),
            training_sample_count=int(data["training_sample_count"]),
            validation_sample_count=int(data.get("validation_sample_count", 0)),
            holdout_sample_count=int(data.get("holdout_sample_count", 0)),
            validation_metrics=dict(data.get("validation_metrics", {})),
            statistical_status=str(data.get("statistical_status", "UNKNOWN")),
            approval_status=str(data.get("approval_status", ModelStatus.RESEARCH_ONLY)),
            model_hash=str(data.get("model_hash", "")),
            required_lookback=int(data.get("required_lookback", data.get("model_parameters", {}).get("required_lookback", 25)))
        )

    @classmethod
    def load_from_file(cls, filepath: str) -> "ModelArtifact":
        """Loads and parses a JSON model artifact from disk."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Model artifact file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw)

    def predict_probabilities(self, market_state: str) -> Tuple[float, float, Dict[str, Any]]:
        """Computes calibrated RUNHIGH and RUNLOW probabilities for a market state.
        
        Returns:
            (runhigh_prob, runlow_prob, metadata)
        """
        base_rh = float(self.model_parameters.get("base_rate_runhigh", 0.03125))
        base_rl = float(self.model_parameters.get("base_rate_runlow", 0.03125))
        state_tables = self.model_parameters.get("state_tables", {})
        shrinkage_weight = float(self.calibration_parameters.get("shrinkage_prior_weight", 50.0))

        if market_state in state_tables:
            entry = state_tables[market_state]
            n = float(entry.get("sample_count", 0))
            k_rh = float(entry.get("runhigh_wins", 0))
            k_rl = float(entry.get("runlow_wins", 0))

            # Empirical Bayes posterior mean with pseudo-prior count M:
            # P_smoothed = (k + M * P_0) / (n + M)
            p_rh = (k_rh + shrinkage_weight * base_rh) / (n + shrinkage_weight) if (n + shrinkage_weight) > 0 else base_rh
            p_rl = (k_rl + shrinkage_weight * base_rl) / (n + shrinkage_weight) if (n + shrinkage_weight) > 0 else base_rl

            from probability import wilson_score_interval
            rh_lo, rh_hi = wilson_score_interval(int(k_rh), int(n))
            rl_lo, rl_hi = wilson_score_interval(int(k_rl), int(n))

            meta = {
                "source": "STATE_CONDITIONAL_FROZEN",
                "uncertainty_method": "WILSON_SCORE",
                "sample_count": n,
                "raw_runhigh_rate": (k_rh / n) if n > 0 else base_rh,
                "raw_runlow_rate": (k_rl / n) if n > 0 else base_rl,
                "smoothed_runhigh": p_rh,
                "smoothed_runlow": p_rl,
                "lower_bound_runhigh": rh_lo,
                "lower_bound_runlow": rl_lo
            }
            return float(p_rh), float(p_rl), meta

        # Unobserved state: evaluate empirical baseline with explicit metadata
        meta = {
            "source": "UNCONDITIONAL_BASELINE",
            "uncertainty_method": "NONE",
            "sample_count": 0,
            "raw_runhigh_rate": base_rh,
            "raw_runlow_rate": base_rl,
            "smoothed_runhigh": base_rh,
            "smoothed_runlow": base_rl,
            "lower_bound_runhigh": None,
            "lower_bound_runlow": None
        }
        return base_rh, base_rl, meta
