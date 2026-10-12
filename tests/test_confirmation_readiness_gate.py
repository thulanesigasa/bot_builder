"""Confirmation is impossible without an independently frozen study plan."""
import json
from pathlib import Path
from tools.confirmation_readiness_gate import evaluate

def test_unfrozen_plan_fails_closed():
    plan=json.loads(Path("research/confirmation_plan_DRAFT.json").read_text())
    result=evaluate(plan)
    assert not result["ready"]
    assert result["required_eligible_n"] is None
    assert "MISSING_PRIMARY_CONTRACT" in result["reasons"]

def test_pilot_cannot_be_mislabeled_confirmation():
    plan=json.loads(Path("research/confirmation_plan_DRAFT.json").read_text())
    plan["pilot_observations_excluded"]=False
    assert not evaluate(plan)["ready"]

def test_planning_power_rejects_optimistic_underpowered_sample():
    plan={
        "primary_market":"R_75", "primary_contract":"PUT", "primary_duration_ticks":2,
        "frozen_model_sha256":"a"*64, "analysis_code_sha256":"b"*64,
        "primary_alternative":"mean_net_return_greater_than_zero",
        "alpha":0.05, "power":0.8, "minimum_economically_relevant_ev":0.1,
        "expected_return_stddev":2.0, "dependence_inflation_factor":2.0,
        "expected_quote_coverage":0.5, "fixed_eligible_sample_size":32,
        "maximum_collection_sessions":4,
        "preregistration_utc":"2026-10-12T13:00:00Z",
        "confirmation_start_utc":"2026-10-13T13:00:00Z",
        "pilot_observations_excluded":True,
    }
    result=evaluate(plan)
    assert not result["ready"]
    assert result["required_eligible_n"] > 32
    assert "FIXED_ELIGIBLE_N_BELOW_PLANNING_LOWER_BOUND" in result["reasons"]
