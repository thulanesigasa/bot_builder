"""Authoritative Model Registry & Provenance Auditor (V1.8.3.1).

Eliminates placeholder model checksums and establishes strict verification of:
1. TRAINED_FROZEN_MODEL: Actual serialized model artifacts with verified 64-character SHA-256 digests.
2. DETERMINISTIC_CAUSAL_BASELINE: Causal heuristics and deterministic decision rules with canonical code/spec digests.
3. CONSTANT_PROBABILITY_BASELINE: Fixed unconditional reference probabilities.
4. UNVERIFIED_MODEL_SOURCE: Fail-closed classification for unknown, corrupted, or placeholder models.

Permanent safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

LIVE_EXECUTION_DISABLED: bool = True

# Model Classification Enums
MODEL_TYPE_TRAINED_FROZEN = "TRAINED_FROZEN_MODEL"
MODEL_TYPE_DETERMINISTIC_BASELINE = "DETERMINISTIC_CAUSAL_BASELINE"
MODEL_TYPE_CONSTANT_BASELINE = "CONSTANT_PROBABILITY_BASELINE"
MODEL_TYPE_UNVERIFIED = "UNVERIFIED_MODEL_SOURCE"

# Recognized Model IDs
MODEL_ID_M_R75_2T = "M_R_75_2TICK_20261011_120000"
MODEL_ID_M_R75_5T = "M_R_75_5TICK_20261008_132512"
MODEL_ID_CAUSAL_MOMENTUM_V1 = "BASELINE_CAUSAL_MOMENTUM_V1"
MODEL_ID_CONSTANT_50_50 = "BASELINE_CONSTANT_50_50"


@dataclass
class ModelProvenanceRecord:
    """Immutable audit record for a verified model or deterministic baseline."""
    model_id: str
    model_type: str
    model_family: str
    description: str
    code_checksum: str
    artifact_path: Optional[str] = None
    artifact_checksum: Optional[str] = None
    training_dataset_id: Optional[str] = None
    training_cutoff_utc: Optional[str] = None
    feature_schema_version: str = "1.5.3"
    calibration_version: str = "1.0.0"
    frozen_configuration_json: str = "{}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuthoritativeModelRegistry:
    """Registry maintaining verified provenance for all forward prediction sources."""

    def __init__(self, models_dir: str = "models"):
        self.models_dir = models_dir
        self._registry: Dict[str, ModelProvenanceRecord] = {}
        self._init_registry()

    @staticmethod
    def compute_sha256_file(filepath: str) -> Optional[str]:
        """Computes lowercase 64-character SHA-256 digest of a file."""
        if not os.path.exists(filepath):
            return None
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compute_sha256_canonical_json(data: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 over canonically formatted JSON string."""
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _init_registry(self) -> None:
        """Initializes recognized models and baselines with verified checksums."""
        # 1. Baseline Causal Momentum V1 (Deterministic causal heuristic)
        causal_spec = {
            "model_id": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "type": MODEL_TYPE_DETERMINISTIC_BASELINE,
            "formula_call": "p_call = 0.50 + np.clip(streak * 0.015, -0.05, 0.05)",
            "formula_put": "p_put = 1.0 - p_call",
            "formula_runhigh_2t": "p_runhigh_2t = 0.25 * (1.0 + streak * 0.02)",
            "formula_runhigh_5t": "p_runhigh_5t = 0.03125 * (1.0 + streak * 0.01)",
            "causal_window": 5,
        }
        causal_checksum = self.compute_sha256_canonical_json(causal_spec)
        self._registry[MODEL_ID_CAUSAL_MOMENTUM_V1] = ModelProvenanceRecord(
            model_id=MODEL_ID_CAUSAL_MOMENTUM_V1,
            model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
            model_family="CAUSAL_STREAK_MOMENTUM_BASELINE",
            description="Deterministic causal momentum heuristic tilting around theoretical base rates.",
            code_checksum=causal_checksum,
            artifact_path=None,
            artifact_checksum=causal_checksum,
            training_dataset_id=None,
            training_cutoff_utc=None,
            feature_schema_version="1.8.3_CAUSAL_STREAK",
            calibration_version="1.8.3_UNWEIGHTED",
            frozen_configuration_json=json.dumps(causal_spec),
        )

        # 2. Constant 50/50 Baseline
        const_spec = {
            "model_id": MODEL_ID_CONSTANT_50_50,
            "type": MODEL_TYPE_CONSTANT_BASELINE,
            "p_call": 0.50,
            "p_put": 0.50,
            "p_runhigh_2t": 0.25,
            "p_runhigh_5t": 0.03125,
        }
        const_checksum = self.compute_sha256_canonical_json(const_spec)
        self._registry[MODEL_ID_CONSTANT_50_50] = ModelProvenanceRecord(
            model_id=MODEL_ID_CONSTANT_50_50,
            model_type=MODEL_TYPE_CONSTANT_BASELINE,
            model_family="CONSTANT_UNCONDITIONAL_REFERENCE",
            description="Constant unconditional base rate reference.",
            code_checksum=const_checksum,
            artifact_path=None,
            artifact_checksum=const_checksum,
            frozen_configuration_json=json.dumps(const_spec),
        )

        # 3. Genuine Trained Frozen Model: M_R_75_2TICK_20261011_120000
        path_2t = os.path.join(self.models_dir, f"{MODEL_ID_M_R75_2T}.json")
        sha_2t = self.compute_sha256_file(path_2t)
        if sha_2t:
            self._registry[MODEL_ID_M_R75_2T] = ModelProvenanceRecord(
                model_id=MODEL_ID_M_R75_2T,
                model_type=MODEL_TYPE_TRAINED_FROZEN,
                model_family="EMPIRICAL_STATE_CONDITIONAL",
                description="Empirical state conditional table trained on R_75 master ticks for 2-tick contracts.",
                code_checksum=sha_2t,
                artifact_path=path_2t,
                artifact_checksum=sha_2t,
                training_dataset_id="R_75_master.csv",
                training_cutoff_utc="2026-10-11T17:54:01.279905+00:00",
                feature_schema_version="1.5.3",
                calibration_version="1.7.4.1",
            )

        # 4. Genuine Trained Frozen Model: M_R_75_5TICK_20261008_132512
        path_5t = os.path.join(self.models_dir, f"{MODEL_ID_M_R75_5T}.json")
        sha_5t = self.compute_sha256_file(path_5t)
        if sha_5t:
            self._registry[MODEL_ID_M_R75_5T] = ModelProvenanceRecord(
                model_id=MODEL_ID_M_R75_5T,
                model_type=MODEL_TYPE_TRAINED_FROZEN,
                model_family="EMPIRICAL_STATE_CONDITIONAL",
                description="Empirical state conditional table trained on R_75 master ticks for 5-tick contracts.",
                code_checksum=sha_5t,
                artifact_path=path_5t,
                artifact_checksum=sha_5t,
                training_dataset_id="R_75_master.csv",
                training_cutoff_utc="2026-10-08T13:25:12+00:00",
                feature_schema_version="1.5.3",
                calibration_version="1.7.4",
            )

    def get_model_record(self, model_id: str) -> Optional[ModelProvenanceRecord]:
        """Retrieves verified model record or None if unknown."""
        return self._registry.get(model_id)

    def verify_model_provenance(
        self, model_id: str, reported_checksum: str
    ) -> Tuple[bool, str, ModelProvenanceRecord]:
        """Audits model ID and checksum against registered authoritative provenance.
        
        Returns:
            (is_verified: bool, classification: str, record: ModelProvenanceRecord)
        """
        # Reject placeholder patterns
        if not reported_checksum or reported_checksum.startswith("sha256_mock_") or reported_checksum == "sha256_v183_frozen_model":
            rec = ModelProvenanceRecord(
                model_id=model_id,
                model_type=MODEL_TYPE_UNVERIFIED,
                model_family="UNVERIFIED",
                description=f"Placeholder or mock checksum detected: '{reported_checksum}'.",
                code_checksum="",
                artifact_checksum="",
            )
            return False, MODEL_TYPE_UNVERIFIED, rec

        # Check against registered models
        registered = self._registry.get(model_id)
        if not registered:
            rec = ModelProvenanceRecord(
                model_id=model_id,
                model_type=MODEL_TYPE_UNVERIFIED,
                model_family="UNVERIFIED",
                description=f"Unregistered model ID: '{model_id}'.",
                code_checksum=reported_checksum,
            )
            return False, MODEL_TYPE_UNVERIFIED, rec

        # Compare checksums
        expected_chk = registered.artifact_checksum or registered.code_checksum
        if reported_checksum.lower() != expected_chk.lower():
            rec = ModelProvenanceRecord(
                model_id=model_id,
                model_type=MODEL_TYPE_UNVERIFIED,
                model_family=registered.model_family,
                description=f"Checksum mismatch for '{model_id}': got {reported_checksum}, expected {expected_chk}.",
                code_checksum=reported_checksum,
            )
            return False, MODEL_TYPE_UNVERIFIED, rec

        return True, registered.model_type, registered
