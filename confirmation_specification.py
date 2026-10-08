"""Confirmation Criteria Specification & Frozen Manifest Engine (V1.7.1 Part D Section 8).

Defines an immutable, cryptographically hashed specification governing forward edge confirmation:
- Records model ID, artifact checksum, market symbol, and candidate market states.
- Locks statistical significance thresholds, calibration tolerances, sample minimums,
  and genuine quote-based economic hurdles before confirmation sessions begin.
- Provides SHA-256 integrity verification to detect any retrospective parameter tampering or p-hacking.
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


CONFIRMATION_SPEC_VERSION = "V1.7.1"


@dataclass
class ConfirmationManifest:
    """Pre-registered, immutable specification for a forward confirmation study."""
    specification_id: str
    model_id: str
    model_artifact_checksum: str
    market_symbol: str
    contract_type: str = "RUNHIGH"       # 'RUNHIGH', 'RUNLOW', or 'BOTH'
    contract_duration: int = 5           # Always 5 ticks
    candidate_market_states: List[str] = field(default_factory=lambda: ["ALL"])
    evaluation_start_boundary: float = 0.0
    min_confirmation_observations: int = 500
    min_confirmation_sessions: int = 2
    min_effective_sample_size: float = 100.0
    min_quote_coverage_pct: float = 95.0
    max_quote_freshness_seconds: float = 60.0
    statistical_significance_alpha: float = 0.05
    min_z_score: float = 1.96
    min_brier_skill_score: float = 0.0   # Must strictly beat unconditional reference rate
    max_expected_calibration_error: float = 0.05  # ECE <= 5.0%
    min_ordinary_ev: float = 0.0         # EV > 0.0 based on real quotes
    min_conservative_ev: float = 0.0     # Conservative EV > 0.0 using lower probability bound
    max_hypothetical_drawdown: float = 20.0
    max_consecutive_losses: int = 5
    software_version: str = "V1.7.1"
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    specification_checksum: str = ""

    def __post_init__(self):
        if not self.specification_checksum:
            self.specification_checksum = self.compute_checksum()

    @property
    def manifest_id(self) -> str:
        return self.specification_id

    @property
    def manifest_checksum(self) -> str:
        return self.specification_checksum

    @manifest_checksum.setter
    def manifest_checksum(self, val: str) -> None:
        self.specification_checksum = val

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConfirmationManifest":
        return cls(**d)

    def canonical_dict(self) -> Dict[str, Any]:
        """Returns ordered dict excluding the checksum itself for hashing."""
        d = asdict(self)
        d.pop("specification_checksum", None)
        return d

    def compute_checksum(self) -> str:
        """Calculates SHA-256 checksum of canonical JSON representation."""
        payload = json.dumps(self.canonical_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_checksum(self) -> bool:
        """Verifies that the specification has not been tampered with."""
        return self.compute_checksum() == self.specification_checksum

    def save_to_file(self, filepath: str) -> None:
        """Saves manifest to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, sort_keys=True)

    @classmethod
    def load_from_file(cls, filepath: str) -> "ConfirmationManifest":
        """Loads manifest from a JSON file and verifies its checksum."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        obj = cls(**data)
        if not obj.verify_checksum():
            raise ValueError(
                f"Confirmation manifest checksum mismatch in {filepath}: "
                f"stored={obj.specification_checksum}, recomputed={obj.compute_checksum()}"
            )
        return obj

    @classmethod
    def create_default_for_model(
        cls,
        model_id: str,
        model_artifact_path: str = "",
        artifact_checksum: str = "",
        symbol: str = "R_75",
        market_symbol: str = "R_75",
        contract_type: str = "RUNHIGH",
        min_observations: int = 500
    ) -> "ConfirmationManifest":
        """Creates and checksums a confirmation specification for a given model artifact."""
        model_checksum = artifact_checksum or "UNAVAILABLE"
        target_symbol = market_symbol if market_symbol != "R_75" else symbol

        if model_artifact_path and os.path.exists(model_artifact_path):
            with open(model_artifact_path, "rb") as f:
                model_checksum = hashlib.sha256(f.read()).hexdigest()

        spec_id = f"CONF_MANIFEST_{target_symbol}_{contract_type}_{int(time.time())}"
        manifest = cls(
            specification_id=spec_id,
            model_id=model_id,
            model_artifact_checksum=model_checksum,
            market_symbol=target_symbol,
            contract_type=contract_type,
            min_confirmation_observations=min_observations,
            min_effective_sample_size=max(50.0, min_observations / 4.5),
        )
        return manifest

