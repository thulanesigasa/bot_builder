"""Research plan cannot silently become a profitability confirmation."""
from freeze_shadow_pilot import PILOT, freeze_manifest
from model_registry import AuthoritativeModelRegistry, MODEL_ID_CAUSAL_MOMENTUM_V1
from forward_shadow_engine import LIVE_EXECUTION_DISABLED, DECISION


def test_pilot_is_non_purchasing_and_not_confirmation():
    assert LIVE_EXECUTION_DISABLED is True
    assert DECISION == "NO_TRADE"
    assert PILOT["mode"] == "SHADOW_RESEARCH_ONLY"
    assert PILOT["primary_hypothesis"] is None
    assert PILOT["confirmation_activated"] is False
    assert PILOT["profitability_promotion_prohibited"] is True


def test_pilot_identity_is_deterministic_and_model_is_registered():
    first = freeze_manifest()
    second = freeze_manifest()
    assert first == second
    assert len(first["protocol_sha256"]) == 64
    registry = AuthoritativeModelRegistry()
    model = registry.get_model_record(MODEL_ID_CAUSAL_MOMENTUM_V1)
    assert first["model_checksum"] == model.artifact_checksum


def test_pilot_preserves_both_contract_families_and_all_directions():
    assert PILOT["contracts"] == ["CALL", "PUT", "RUNHIGH", "RUNLOW"]
    assert PILOT["durations_ticks"] == [2, 5]
    assert PILOT["pilot_fixed_sessions"] == 4
