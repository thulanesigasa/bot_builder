"""Comprehensive Automated Test Suite for V1.8.2 Evidence Integration & Data Provenance Enforcement.

Validates:
  1. Permanent Safety Invariants: LIVE_EXECUTION_DISABLED = True, NO_TRADE across all engines.
  2. Critical Defect 1: Elimination of reference quote masquerade.
     - evaluate_all_hypotheses under MODE_QUOTE_VERIFIED raises ValueError if loose reference tuple is passed.
     - Absent proposal quotes fail closed to INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE.
     - Synthesizes VERDICT_INSUFFICIENT_QUOTES when quote evidence is absent.
     - Reference mode permanently assigns REFERENCE_ECONOMICS_ONLY or negative EV, prohibiting candidate qualification.
     - VerifiedEconomicObservation dataclass enforces all 23 audit fields.
  3. Critical Defect 2: Data Provenance Fail-Closed Enforcement.
     - Default classification is UNVERIFIED_SOURCE.
     - Missing companion provenance JSON file fails closed to UNVERIFIED_SOURCE.
     - Corrupted companion provenance JSON fails closed to CORRUPTED_SOURCE.
     - Decouples file_integrity_status, source_authenticity_status, and transformation_lineage_status.
     - Cryptographic SHA-256 integrity alone does not grant broker authenticity without verified endpoint.
  4. Serial Dependence Auditor:
     - Calculates empirical autocorrelation rho(k), integrated autocorrelation time tau_int, and N_eff.
     - Compares Naive i.i.d., Duration heuristic N/D, Empirical tau_int, MBB, and Decimation.
     - Verifies test statistic inflation deflation.
  5. Canonical Pipeline & Release Artifacts:
     - Validates data/v182_data_provenance_manifest.json.
     - Validates data/v182_multi_market_evidence.json.
     - Validates all 8 markdown reports under reports/.
     - Confirms full disqualification of all 3 historical candidates.
"""

from datetime import datetime, timezone
import json
import math
import os
import sqlite3
import numpy as np
import pytest

from data_provenance import (
    DataProvenanceAuditor,
    DatasetProvenanceRecord,
    SOURCE_GENUINE_BROKER_API,
    SOURCE_UNVERIFIED_SOURCE,
    SOURCE_CORRUPTED_SOURCE,
    SOURCE_SYNTHETIC_FIXTURE,
    STATUS_FILE_INTEGRITY_VERIFIED,
    STATUS_FILE_INTEGRITY_FAILED,
    STATUS_FILE_INTEGRITY_UNVERIFIED,
    STATUS_SOURCE_AUTHENTICITY_VERIFIED,
    STATUS_SOURCE_AUTHENTICITY_UNVERIFIED,
    STATUS_LINEAGE_VERIFIED,
    STATUS_LINEAGE_UNVERIFIED,
    LIVE_EXECUTION_DISABLED as PROVENANCE_SAFETY,
)
from quote_economics_engine import (
    ProposalQuoteRecord,
    VerifiedEconomicObservation,
    PerObservationEconomicRecord,
    QuoteLevelEconomicEngine,
    MODE_QUOTE_VERIFIED,
    MODE_REFERENCE_ECONOMICS_ONLY,
    MODE_UNPRICED_PREDICTION_EVALUATION,
    STATUS_ELIGIBLE,
    STATUS_QUOTE_UNAVAILABLE,
    LIVE_EXECUTION_DISABLED as QUOTE_SAFETY,
)
from rise_fall_research import (
    MultiMarketEdgeDiscovery,
    HypothesisEvaluation,
    CandidateQualificationGate,
    SerialDependenceAuditor,
    HypothesisType,
    STATUS_CANDIDATE_IDENTIFIED,
    STATUS_INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE,
    STATUS_REFERENCE_ECONOMICS_ONLY,
    STATUS_REJECTED_NEGATIVE_EV,
    STATUS_REJECTED_NEGATIVE_PREDICTED_EV,
    VERDICT_EXPLORATORY,
    VERDICT_INSUFFICIENT_QUOTES,
    VERDICT_NO_EDGE,
    LIVE_EXECUTION_DISABLED as RESEARCH_SAFETY,
)
from canonical_pipeline import (
    run_provenance_audit,
    audit_proposal_quotes,
    run_canonical_pipeline,
    LIVE_EXECUTION_DISABLED as PIPELINE_SAFETY,
    OPERATING_MODE,
    DECISION,
    BASE_COMMIT,
    TARGET_RELEASE,
)


class TestV182SafetyInvariants:
    """Verifies permanent, compile-time non-purchasing safety invariants across all modules."""

    def test_all_v182_modules_enforce_live_execution_disabled(self):
        assert RESEARCH_SAFETY is True
        assert QUOTE_SAFETY is True
        assert PROVENANCE_SAFETY is True
        assert PIPELINE_SAFETY is True

    def test_platform_operating_mode_and_decision_invariants(self):
        assert OPERATING_MODE == "SHADOW_RESEARCH_ONLY"
        assert DECISION == "NO_TRADE"


class TestV182QuoteEconomicsEngineIntegration:
    """Verifies Critical Defect 1: quote integration into evaluator and elimination of reference masquerade."""

    def test_quote_verified_mode_rejects_loose_reference_tuple(self):
        discovery = MultiMarketEdgeDiscovery()
        dummy_outcomes = {
            m: {dur: {"CALL": np.array([1, 0] * 50), "PUT": np.array([1, 0] * 50)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }
        dummy_p_models = {
            m: {dur: {"CALL": np.full(100, 0.50), "PUT": np.full(100, 0.50)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }

        # Passing reference price tuple under QUOTE_VERIFIED MUST raise ValueError
        with pytest.raises(ValueError, match="strictly requires verified observation quote records"):
            discovery.evaluate_all_hypotheses(
                market_outcomes=dummy_outcomes,
                market_p_models=dummy_p_models,
                typical_quote=(2.0, 3.91),
                evaluation_mode=MODE_QUOTE_VERIFIED,
                verified_quotes=None,
                verified_observations=None,
            )

    def test_missing_quotes_fail_closed_to_insufficient_quote_verified_evidence(self):
        discovery = MultiMarketEdgeDiscovery()
        dummy_outcomes = {
            m: {dur: {"CALL": np.array([1, 0] * 50), "PUT": np.array([1, 0] * 50)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }
        dummy_p_models = {
            m: {dur: {"CALL": np.full(100, 0.50), "PUT": np.full(100, 0.50)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }

        evals = discovery.evaluate_all_hypotheses(
            market_outcomes=dummy_outcomes,
            market_p_models=dummy_p_models,
            typical_quote=None,
            evaluation_mode=MODE_QUOTE_VERIFIED,
            verified_quotes=None,
            verified_observations=None,
        )

        assert len(evals) == 48
        for e in evals:
            assert e.verdict == STATUS_INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE
            assert e.rejection_reason == "INSUFFICIENT_AUTHENTICATED_QUOTE_RECORDS"
            assert e.quote_match_count == 0

        # Synthesize verdict must fail closed to INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE
        overall_verdict = discovery.synthesize_verdict(evals)
        assert overall_verdict == VERDICT_INSUFFICIENT_QUOTES

    def test_reference_economics_mode_permanently_prohibits_candidate_qualification(self):
        discovery = MultiMarketEdgeDiscovery()
        # Create a synthetic dataset with high win rate that would have passed under naive reference pricing
        dummy_outcomes = {
            m: {dur: {"CALL": np.array([1, 1, 1, 0] * 50), "PUT": np.array([0, 1] * 100)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }
        dummy_p_models = {
            m: {dur: {"CALL": np.full(200, 0.70), "PUT": np.full(200, 0.40)} for dur in [2, 3, 5, 10]}
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }

        evals = discovery.evaluate_all_hypotheses(
            market_outcomes=dummy_outcomes,
            market_p_models=dummy_p_models,
            typical_quote=(2.0, 3.91),
            evaluation_mode=MODE_REFERENCE_ECONOMICS_ONLY,
        )

        for e in evals:
            # Under REFERENCE_ECONOMICS_ONLY mode, verdict can NEVER be CANDIDATE_IDENTIFIED
            assert e.verdict != STATUS_CANDIDATE_IDENTIFIED
            if e.realized_ev > 0.0 and e.predicted_ev > 0.0:
                assert e.verdict == STATUS_REFERENCE_ECONOMICS_ONLY
                assert e.rejection_reason == "REFERENCE_PRICING_INELIGIBLE_FOR_CANDIDATE_QUALIFICATION"

    def test_verified_economic_observation_structure(self):
        obs = VerifiedEconomicObservation(
            observation_id="OBS_001",
            session_id="SESS_TEST",
            market_symbol="R_100",
            contract_type="CALL",
            contract_duration=5,
            decision_epoch=1791234567.0,
            prediction_journal_id="PJ_001",
            model_checksum="sha256_dummy_model",
            predicted_prob=0.55,
            quote_response_id="QR_001",
            proposal_id="PROP_12345",
            quote_request_epoch=1791234566.0,
            quote_response_epoch=1791234566.2,
            ask_price=2.00,
            total_payout=3.91,
            break_even_rate=2.00 / 3.91,
            predicted_ev=(0.55 * 3.91) - 2.00,
            observed_outcome=1,
            hypothetical_return=1.91,
            entry_mapping_version="MAPPING_V1_NEXT_TICK_ENTRY",
            source_evidence_status="GENUINE_BROKER_API",
            quote_eligibility_status=STATUS_ELIGIBLE,
            economic_evidence_status=MODE_QUOTE_VERIFIED,
            exclusion_reason=None,
        )
        d = obs.to_dict()
        assert d["observation_id"] == "OBS_001"
        assert d["market_symbol"] == "R_100"
        assert d["quote_eligibility_status"] == STATUS_ELIGIBLE
        assert d["ask_price"] == 2.00
        assert d["total_payout"] == 3.91
        assert len(d) == 24


class TestV182DataProvenanceFailClosed:
    """Verifies Critical Defect 2: fail-closed data provenance and decoupled statuses."""

    def test_provenance_audit_file_fails_closed_when_companion_missing(self, tmp_path):
        csv_file = tmp_path / "untracked_ticks.csv"
        csv_file.write_text("epoch,price\n100,10.5\n101,10.6\n")

        res = DataProvenanceAuditor.audit_file(str(csv_file))
        assert res["source_classification"] == SOURCE_UNVERIFIED_SOURCE
        assert res["is_broker_derived"] is False
        assert res["source_authenticity_status"] == STATUS_SOURCE_AUTHENTICITY_UNVERIFIED
        assert "Missing companion provenance" in res["details"]

    def test_provenance_audit_file_fails_closed_when_companion_corrupted(self, tmp_path):
        csv_file = tmp_path / "corrupted_ticks.csv"
        csv_file.write_text("epoch,price\n100,10.5\n101,10.6\n")
        json_file = tmp_path / "corrupted_ticks_provenance.json"
        json_file.write_text("{invalid json syntax, missing quotes")

        res = DataProvenanceAuditor.audit_file(str(csv_file), str(json_file))
        assert res["source_classification"] == SOURCE_CORRUPTED_SOURCE
        assert res["is_broker_derived"] is False
        assert res["file_integrity_status"] == STATUS_FILE_INTEGRITY_FAILED
        assert res["source_authenticity_status"] == STATUS_SOURCE_AUTHENTICITY_UNVERIFIED

    def test_decoupled_statuses_on_verified_broker_data(self):
        """Check actual source integrity instead of assuming legacy CSVs match.

        Six legacy CSV/companion pairs were committed with inconsistent hashes
        in the initial repository import. They remain usable only as
        exploratory/unverified data unless independently re-acquired.
        """
        auditor = DataProvenanceAuditor()
        manifest = auditor.generate_manifest()
        assert len(manifest) == 6
        from data_provenance import (
            compute_file_sha256,
            STATUS_FILE_INTEGRITY_FAILED,
            STATUS_SOURCE_AUTHENTICITY_UNVERIFIED,
        )
        import json
        for sym, path, _, provenance_path in auditor.MARKET_SPECS:
            rec = manifest[sym]
            with open(provenance_path, encoding="utf-8") as f:
                claimed = json.load(f).get("sha256_checksum")
            actual = compute_file_sha256(path)
            assert rec["sha256_checksum"] == actual
            assert len(actual) == 64
            assert rec["duplicates_count"] == 0
            assert rec["inversions_count"] == 0
            if claimed != actual:
                assert rec["file_integrity_status"] == STATUS_FILE_INTEGRITY_FAILED
                assert rec["source_authenticity_status"] == STATUS_SOURCE_AUTHENTICITY_UNVERIFIED
                assert rec["is_eligible_for_authoritative_research"] is False
            else:
                assert rec["file_integrity_status"] == STATUS_FILE_INTEGRITY_VERIFIED
                assert rec["transformation_lineage_status"] == STATUS_LINEAGE_VERIFIED

    def test_synthetic_fixture_cannot_acquire_broker_status(self):
        sim_rec = DataProvenanceAuditor.audit_file("data/quarantine/simulated.csv")
        assert sim_rec["source_classification"] == SOURCE_SYNTHETIC_FIXTURE
        assert sim_rec["is_broker_derived"] is False


class TestV182SerialDependenceAuditor:
    """Verifies empirical autocorrelation, tau_int, and test statistic deflation."""

    def test_autocorrelation_computation(self):
        # Strongly correlated series
        x = np.array([1, 1, 1, 1, 0, 0, 0, 0] * 50)
        rhos = SerialDependenceAuditor.compute_autocorrelation(x, max_lag=5)
        assert len(rhos) == 6  # Lags 0, 1, 2, 3, 4, 5
        assert rhos[0] == 1.0  # Lag 0 is always 1.0
        assert rhos[1] > 0.4   # Lag 1 positive autocorrelation

    def test_integrated_autocorrelation_time_and_n_eff(self):
        # Correlated series
        x = np.repeat([1, 0], 100)  # Long runs
        tau_int = SerialDependenceAuditor.compute_integrated_autocorrelation_time(x)
        assert tau_int > 1.0

        n_eff = SerialDependenceAuditor.compute_effective_sample_size(x, tau_int)
        assert n_eff < len(x)
        assert n_eff >= 1

    def test_compare_dependence_methods_deflates_z_statistic(self):
        # Generate autocorrelated outcomes
        np.random.seed(42)
        n = 1000
        # Block of 5 identical outcomes
        blocks = np.random.choice([0, 1], size=200, p=[0.45, 0.55])
        correlated_outcomes = np.repeat(blocks, 5)

        summary = SerialDependenceAuditor.compare_dependence_methods(correlated_outcomes, duration_ticks=5)
        naive_z = abs(summary["naive_independent"]["z"])
        emp_z = abs(summary["empirical_autocorrelation"]["z"])

        # Empirical z-statistic must be smaller than naive z-statistic due to SE inflation
        assert emp_z < naive_z
        assert summary["empirical_autocorrelation"]["tau_int"] > 1.5
        assert summary["empirical_autocorrelation"]["n_eff"] < n


class TestV182CanonicalPipelineAndEvidencePackage:
    """Verifies canonical pipeline execution and serialization of evidence package."""

    def test_canonical_manifest_and_evidence_files_exist(self):
        manifest_path = "data/v182_data_provenance_manifest.json"
        evidence_path = "data/v182_multi_market_evidence.json"
        assert os.path.exists(manifest_path), f"Missing {manifest_path}"
        assert os.path.exists(evidence_path), f"Missing {evidence_path}"

    def test_evidence_package_verdicts_and_candidate_disqualification(self):
        with open("data/v182_multi_market_evidence.json", "r", encoding="utf-8") as f:
            evidence = json.load(f)

        meta = evidence["metadata"]
        assert meta["pipeline_version"] == "V1.8.2"
        assert meta["base_commit"] == "8bcda0238ad8e88060d20e319040f2bce4665df6"
        assert meta["safety_invariants"]["LIVE_EXECUTION_DISABLED"] is True
        assert meta["safety_invariants"]["DECISION"] == "NO_TRADE"

        verdicts = evidence["verdicts"]
        assert verdicts["authoritative_quote_verified_verdict"] == "INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE"
        assert verdicts["baseline_reference_verdict"] == "NO_VALIDATED_POSITIVE_EV_EDGE"
        assert verdicts["quote_verified_candidate_count"] == 0
        assert verdicts["reference_candidate_count"] == 0
        assert verdicts["final_economic_verdict"] == "NO_VALIDATED_POSITIVE_EV_EDGE"

        # Check candidate reassessment
        reassess = evidence["historical_candidate_reassessment"]
        assert len(reassess) == 3
        for c in reassess:
            assert c["is_authoritative_candidate"] is False
            assert c["quote_verified_verdict"] == "INSUFFICIENT_QUOTE_VERIFIED_EVIDENCE"
            assert "Zero proposal quotes" in c["disqualification_reasons"][0]

    def test_all_eight_v182_reports_exist_and_conform_to_rules(self):
        expected_reports = [
            "reports/V1_8_2_END_TO_END_PIPELINE_AUDIT.md",
            "reports/V1_8_2_DATA_AUTHENTICITY_REASSESSMENT.md",
            "reports/V1_8_2_QUOTE_EVIDENCE_INTEGRATION.md",
            "reports/V1_8_2_CORRECTED_48_HYPOTHESES.md",
            "reports/V1_8_2_STATISTICAL_INFERENCE_AUDIT.md",
            "reports/V1_8_2_CANDIDATE_REASSESSMENT.md",
            "reports/V1_8_2_FORWARD_RESEARCH_READINESS.md",
            "reports/V1_8_2_RELEASE_VALIDATION_REPORT.md",
        ]
        for rpath in expected_reports:
            assert os.path.exists(rpath), f"Report {rpath} does not exist"
            with open(rpath, "r", encoding="utf-8") as rf:
                content = rf.read()
            # Rule 18: No emojis allowed
            for ch in content:
                assert ord(ch) <= 10000, f"Emoji character {ch} detected in {rpath}"
            # Must include shields.io badge
            assert "img.shields.io" in content, f"Missing shields.io badges in {rpath}"
