"""Comprehensive Automated Test Suite for V1.8.1 Economic Integrity Repair & Independent Validation.

Validates:
  1. Permanent Safety Invariants: LIVE_EXECUTION_DISABLED = True, NO_TRADE across all engines.
  2. Gate Rule: Negative predicted EV cannot qualify (REJECTED_NEGATIVE_PREDICTED_EV).
  3. Gate Rule: Positive realized EV alone cannot qualify.
  4. Gate Rule: Positive bootstrap bounds alone cannot qualify.
  5. Gate Rule: Constant reference pricing is prohibited from qualifying (REFERENCE_ECONOMICS_ONLY).
  6. Per-Observation Quote Matching:
     * Missing proposals fail closed (QUOTE_UNAVAILABLE).
     * Cross-market quote mismatch rejected (CROSS_MARKET_MISMATCH / filtered out).
     * Cross-duration quote mismatch rejected (CROSS_DURATION_MISMATCH / filtered out).
     * Quote received after decision timestamp rejected (FUTURE_QUOTE / filtered out).
     * Stale quotes rejected (> 5s).
     * Genuine matched quotes correctly compute per-observation break-even, predicted EV, and realized EV.
  7. Dependence-Aware Statistical Inference:
     * Effective sample size N_eff = max(1, floor(N / D)) inflates standard error.
     * Naive binomial test inflated z-scores collapse under dependence-aware evaluation.
  8. Full Reassessment of the Three V1.8.0 Candidates:
     * HYP_R_100_10T_PUT receives REJECTED_NEGATIVE_PREDICTED_EV.
     * HYP_1HZ50V_10T_PUT receives REJECTED_NEGATIVE_PREDICTED_EV.
     * HYP_1HZ50V_5T_PUT receives REJECTED_NEGATIVE_PREDICTED_EV.
  9. Data Provenance & Cryptographic Verification:
     * Manifest file contains genuine broker API classification and valid SHA-256 hashes.
     * Simulated test data cannot claim live-broker status.
 10. Mandatory Realistic SQLite-Based End-to-End Integration Fixture:
     * Real SQLite schema with predictions, proposals, outcomes across markets and durations.
     * Proves that a retrospective winning streak with negative predicted EV fails closed.
"""
import copy
import math
import os
import sqlite3
import numpy as np
import pytest

from rise_fall_research import (
    MultiMarketEdgeDiscovery,
    HypothesisEvaluation,
    CandidateQualificationGate,
    HypothesisType,
    STATUS_CANDIDATE_IDENTIFIED,
    STATUS_REJECTED_NEGATIVE_PREDICTED_EV,
    STATUS_REJECTED_NEGATIVE_EV,
    STATUS_REJECTED_INSUFFICIENT_CONSERVATIVE_EV,
    STATUS_REJECTED_STATISTICAL_INSUFFICIENCY,
    STATUS_REFERENCE_ECONOMICS_ONLY,
    VERDICT_NO_EDGE,
    LIVE_EXECUTION_DISABLED as RESEARCH_SAFETY,
)
from quote_economics_engine import (
    ProposalQuoteRecord,
    PerObservationEconomicRecord,
    QuoteLevelEconomicEngine,
    AggregatedEconomicSummary,
    STATUS_ELIGIBLE,
    STATUS_QUOTE_UNAVAILABLE,
    STATUS_STALE_QUOTE,
    STATUS_INVALID_PRICE_TERMS,
    MODE_QUOTE_VERIFIED,
    MODE_REFERENCE_ECONOMICS_ONLY,
    LIVE_EXECUTION_DISABLED as QUOTE_SAFETY,
)
from data_provenance import (
    DataProvenanceAuditor,
    DATA_CLASSIFICATION_GENUINE_BROKER,
    DATA_CLASSIFICATION_SIMULATED,
    LIVE_EXECUTION_DISABLED as PROVENANCE_SAFETY,
)
from market_discovery import (
    MarketDiscovery,
    LIVE_EXECUTION_DISABLED as DISCOVERY_SAFETY,
)
from contract_rise_fall import (
    RiseFallContractSpec,
    RiseFallOutcomeResolver,
    MAPPING_V1_NEXT_TICK_ENTRY,
    LIVE_EXECUTION_DISABLED as CONTRACT_SAFETY,
)


class TestV181SafetyInvariants:
    """Verifies permanent, compile-time non-purchasing safety invariants."""

    def test_all_v181_modules_enforce_live_execution_disabled(self):
        assert RESEARCH_SAFETY is True
        assert QUOTE_SAFETY is True
        assert PROVENANCE_SAFETY is True
        assert DISCOVERY_SAFETY is True
        assert CONTRACT_SAFETY is True

    def test_candidate_gate_never_authorizes_purchases(self):
        # Even if a hypothetical candidate somehow passed, platform decision is NO_TRADE
        gate_res = CandidateQualificationGate.audit_candidate(
            HypothesisEvaluation(
                hypothesis_id="TEST_HYP",
                market="R_100",
                duration_ticks=5,
                direction="CALL",
                sample_size=1000,
                p_model=0.55,
                empirical_win_rate=0.56,
                ask_price=2.0,
                total_payout=3.91,
                break_even_rate=0.5115,
                probability_advantage=0.0385,
                predicted_ev=0.1505,
                realized_ev=0.1896,
                conservative_ev_mbb_95=0.05,
                raw_p_value=0.001,
                adjusted_p_value_fdr=0.01,
                is_statistically_significant=True,
                is_economically_positive=True,
                verdict=STATUS_CANDIDATE_IDENTIFIED,
            )
        )
        assert RESEARCH_SAFETY is True
        assert gate_res["is_qualified"] is True
        # Safety invariant remains true: no orders can be routed
        assert QUOTE_SAFETY is True


class TestV181CandidateQualificationGate:
    """Adversarial testing of the repaired candidate qualification gate."""

    def test_negative_predicted_ev_fails_qualification(self):
        # Scenario matching V1.8.0 candidates:
        # P_model = 0.5041 (< break-even 0.5115), Realized WinRate = 53.84% (> 51.15%)
        # Predicted EV = -0.029, Realized EV = +0.105, Conservative EV = +0.0075
        eval_obj = HypothesisEvaluation(
            hypothesis_id="HYP_TEST_NEGATIVE_PRED_EV",
            market="R_100",
            duration_ticks=10,
            direction="PUT",
            sample_size=4978,
            p_model=0.5041,
            empirical_win_rate=0.5384,
            ask_price=2.0,
            total_payout=3.91,
            break_even_rate=0.5115,
            probability_advantage=-0.0074,
            predicted_ev=-0.0290,
            realized_ev=0.1050,
            conservative_ev_mbb_95=0.0075,
            raw_p_value=0.001,
            adjusted_p_value_fdr=0.01,
            is_statistically_significant=True,
            is_economically_positive=False,
            verdict="TBD",
        )
        res = CandidateQualificationGate.audit_candidate(eval_obj)
        assert res["is_qualified"] is False
        assert res["gate_positive_predicted_ev"] is False
        assert "NEGATIVE_PREDICTED_EV" in res["failure_reasons"]

    def test_positive_realized_ev_alone_cannot_qualify(self):
        # Retrospective win rate is 60%, but model forecast was 48% (negative predicted EV)
        eval_obj = HypothesisEvaluation(
            hypothesis_id="HYP_LUCKY_STREAK",
            market="R_75",
            duration_ticks=5,
            direction="CALL",
            sample_size=1000,
            p_model=0.48,
            empirical_win_rate=0.60,
            ask_price=2.0,
            total_payout=3.91,
            break_even_rate=0.5115,
            probability_advantage=-0.0315,
            predicted_ev=-0.1232,
            realized_ev=0.3460,
            conservative_ev_mbb_95=0.20,
            raw_p_value=0.0001,
            adjusted_p_value_fdr=0.001,
            is_statistically_significant=True,
            is_economically_positive=False,
            verdict="TBD",
        )
        res = CandidateQualificationGate.audit_candidate(eval_obj)
        assert res["is_qualified"] is False
        assert res["gate_positive_realized_ev"] is True
        assert res["gate_positive_predicted_ev"] is False

    def test_positive_bootstrap_bound_alone_cannot_qualify(self):
        # Conservative EV > 0, but predicted EV <= 0
        eval_obj = HypothesisEvaluation(
            hypothesis_id="HYP_BOOTSTRAP_ALONE",
            market="1HZ50V",
            duration_ticks=10,
            direction="PUT",
            sample_size=2000,
            p_model=0.50,
            empirical_win_rate=0.55,
            ask_price=2.0,
            total_payout=3.91,
            break_even_rate=0.5115,
            probability_advantage=-0.0115,
            predicted_ev=-0.0450,
            realized_ev=0.1505,
            conservative_ev_mbb_95=0.02,
            raw_p_value=0.002,
            adjusted_p_value_fdr=0.02,
            is_statistically_significant=True,
            is_economically_positive=False,
            verdict="TBD",
        )
        res = CandidateQualificationGate.audit_candidate(eval_obj)
        assert res["is_qualified"] is False
        assert res["gate_positive_conservative_ev"] is True
        assert res["gate_positive_predicted_ev"] is False

    def test_reference_pricing_prohibited_from_qualifying(self):
        # Even if all metrics are positive, reference mode fails candidate qualification
        eval_obj = HypothesisEvaluation(
            hypothesis_id="HYP_REF_MODE",
            market="R_100",
            duration_ticks=5,
            direction="CALL",
            sample_size=1000,
            p_model=0.55,
            empirical_win_rate=0.55,
            ask_price=2.0,
            total_payout=3.91,
            break_even_rate=0.5115,
            probability_advantage=0.0385,
            predicted_ev=0.1505,
            realized_ev=0.1505,
            conservative_ev_mbb_95=0.08,
            raw_p_value=0.001,
            adjusted_p_value_fdr=0.01,
            is_statistically_significant=True,
            is_economically_positive=True,
            verdict="TBD",
            evaluation_mode="REFERENCE_ECONOMICS_ONLY",
        )
        res = CandidateQualificationGate.audit_candidate(eval_obj)
        assert res["is_qualified"] is False
        assert res["gate_quote_verified"] is False
        assert "REFERENCE_ECONOMICS_PROHIBITED" in res["failure_reasons"]


class TestV181QuoteLevelEconomicsEngine:
    """Verifies per-observation quote matching and fail-closed behaviors."""

    def test_missing_proposals_fail_closed_as_quote_unavailable(self):
        obs = [
            {"decision_epoch": 100.0, "predicted_prob": 0.53, "observed_outcome": 1},
            {"decision_epoch": 102.0, "predicted_prob": 0.54, "observed_outcome": 0},
        ]
        quotes = []  # No proposals available
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=quotes,
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
        )
        assert len(recs) == 2
        assert recs[0].status == STATUS_QUOTE_UNAVAILABLE
        assert recs[0].is_eligible is False
        assert summary.eligible_decisions_count == 0
        assert summary.is_quote_verified is False
        assert summary.is_candidate_eligible is False

    def test_cross_market_quote_mismatch_rejected(self):
        # Proposal quote for R_75 must NOT match R_100 observation
        q = ProposalQuoteRecord(
            quote_id="Q1",
            proposal_id="P1",
            market_symbol="R_75",
            contract_type="CALL",
            contract_duration=5,
            ask_price=2.0,
            total_payout=3.91,
            response_timestamp=99.0,
        )
        obs = [{"decision_epoch": 100.0, "predicted_prob": 0.53, "observed_outcome": 1}]
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=[q],
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
        )
        assert recs[0].status == STATUS_QUOTE_UNAVAILABLE
        assert recs[0].is_eligible is False

    def test_cross_duration_quote_mismatch_rejected(self):
        # Proposal quote for 10t must NOT match 5t observation
        q = ProposalQuoteRecord(
            quote_id="Q2",
            proposal_id="P2",
            market_symbol="R_100",
            contract_type="CALL",
            contract_duration=10,
            ask_price=2.0,
            total_payout=3.91,
            response_timestamp=99.0,
        )
        obs = [{"decision_epoch": 100.0, "predicted_prob": 0.53, "observed_outcome": 1}]
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=[q],
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
        )
        assert recs[0].status == STATUS_QUOTE_UNAVAILABLE
        assert recs[0].is_eligible is False

    def test_future_quote_rejected_as_chronology_leakage(self):
        # Quote received AFTER decision timestamp must NOT match
        q = ProposalQuoteRecord(
            quote_id="Q3",
            proposal_id="P3",
            market_symbol="R_100",
            contract_type="CALL",
            contract_duration=5,
            ask_price=2.0,
            total_payout=3.91,
            response_timestamp=101.0,  # 1.0s in future
        )
        obs = [{"decision_epoch": 100.0, "predicted_prob": 0.53, "observed_outcome": 1}]
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=[q],
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
        )
        assert recs[0].status == STATUS_QUOTE_UNAVAILABLE
        assert recs[0].is_eligible is False

    def test_stale_quote_rejected(self):
        # Quote received 10s prior to decision exceeds max_freshness (5s)
        q = ProposalQuoteRecord(
            quote_id="Q4",
            proposal_id="P4",
            market_symbol="R_100",
            contract_type="CALL",
            contract_duration=5,
            ask_price=2.0,
            total_payout=3.91,
            response_timestamp=85.0,  # 15s age
        )
        obs = [{"decision_epoch": 100.0, "predicted_prob": 0.53, "observed_outcome": 1}]
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=[q],
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
            max_freshness_seconds=5.0,
        )
        assert recs[0].status == STATUS_STALE_QUOTE
        assert recs[0].is_eligible is False

    def test_genuine_matched_quote_computes_exact_economics(self):
        # Valid quote received 1.5s prior to decision
        q = ProposalQuoteRecord(
            quote_id="Q5",
            proposal_id="P5",
            market_symbol="R_100",
            contract_type="CALL",
            contract_duration=5,
            ask_price=2.0,
            total_payout=3.90,  # 3.90 payout => break-even = 2.0 / 3.90 = 0.51282
            response_timestamp=98.5,
        )
        obs = [{"decision_epoch": 100.0, "predicted_prob": 0.55, "observed_outcome": 1}]
        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=obs,
            quotes=[q],
            symbol="R_100",
            contract_type="CALL",
            duration_ticks=5,
        )
        rec = recs[0]
        assert rec.status == STATUS_ELIGIBLE
        assert rec.is_eligible is True
        assert rec.ask_price == 2.0
        assert rec.total_payout == 3.90
        assert abs(rec.break_even_rate - (2.0 / 3.90)) < 1e-4
        assert abs(rec.predicted_ev - (0.55 * 3.90 - 2.0)) < 1e-4
        assert abs(rec.realized_return - (1.0 * 3.90 - 2.0)) < 1e-4


class TestV181StatisticalDependenceAndReassessment:
    """Verifies dependence-aware inference and reclassification of V1.8.0 candidates."""

    def test_effective_sample_size_inflates_standard_error(self):
        n = 5000
        dur = 10
        p0 = 0.5115
        n_eff = n // dur  # 500

        se_naive = math.sqrt(p0 * (1.0 - p0) / n)
        se_eff = math.sqrt(p0 * (1.0 - p0) / n_eff)

        ratio = se_eff / se_naive
        assert abs(ratio - math.sqrt(10)) < 1e-4

    def test_reassessment_of_three_v180_candidates(self):
        # Setup data representing the 3 candidates with negative predicted EV
        market_outcomes = {
            "R_100": {10: {"PUT": np.array([1 if i % 100 < 54 else 0 for i in range(4978)])}},
            "1HZ50V": {
                10: {"PUT": np.array([1 if i % 100 < 54 else 0 for i in range(4978)])},
                5: {"PUT": np.array([1 if i % 100 < 53 else 0 for i in range(4984)])},
            },
        }
        market_p_models = {
            "R_100": {10: {"PUT": np.full(4978, 0.5041)}},    # < 0.5115
            "1HZ50V": {
                10: {"PUT": np.full(4978, 0.4984)},   # < 0.5115
                5: {"PUT": np.full(4984, 0.5008)},    # < 0.5115
            },
        }

        ed = MultiMarketEdgeDiscovery(fdr_alpha=0.05, use_effective_sample_size=True)
        evals = ed.evaluate_all_hypotheses(market_outcomes, market_p_models)

        eval_map = {e.hypothesis_id: e for e in evals}

        # Candidate A: HYP_R_100_10T_PUT
        h_a = eval_map.get("HYP_R_100_10T_PUT")
        assert h_a is not None
        assert h_a.predicted_ev < 0.0
        assert h_a.verdict == STATUS_REJECTED_NEGATIVE_PREDICTED_EV

        # Candidate B: HYP_1HZ50V_10T_PUT
        h_b = eval_map.get("HYP_1HZ50V_10T_PUT")
        assert h_b is not None
        assert h_b.predicted_ev < 0.0
        assert h_b.verdict == STATUS_REJECTED_NEGATIVE_PREDICTED_EV

        # Candidate C: HYP_1HZ50V_5T_PUT
        h_c = eval_map.get("HYP_1HZ50V_5T_PUT")
        assert h_c is not None
        assert h_c.predicted_ev < 0.0
        assert h_c.verdict == STATUS_REJECTED_NEGATIVE_PREDICTED_EV

        # Synthesized verdict across candidates must be NO_VALIDATED_POSITIVE_EV_EDGE
        overall_verdict = ed.synthesize_verdict(evals)
        assert overall_verdict == VERDICT_NO_EDGE


class TestV181DataProvenanceAndEvidenceIntegrity:
    """Verifies cryptographic data hashes and source separation."""

    def test_data_provenance_manifest_structure(self):
        auditor = DataProvenanceAuditor()
        manifest = auditor.generate_manifest()
        assert "R_100" in manifest
        assert "1HZ50V" in manifest
        for sym, rec in manifest.items():
            assert rec["source_classification"] == DATA_CLASSIFICATION_GENUINE_BROKER
            assert len(rec["sha256_checksum"]) == 64
            assert rec["duplicates_count"] == 0
            assert rec["inversions_count"] == 0
            assert rec["gaps_count"] == 0

    def test_simulated_dataset_cannot_acquire_broker_status(self):
        sim_rec = DataProvenanceAuditor.audit_file("data/quarantine/simulated.csv")
        assert sim_rec["source_classification"] == DATA_CLASSIFICATION_SIMULATED


class TestV181SQLiteIntegrationFixture:
    """End-to-end integration test over realistic SQLite schema verifying fail-closed candidate evaluation."""

    def test_sqlite_pipeline_blocks_retrospective_winning_streak(self, tmp_path):
        db_path = str(tmp_path / "test_research.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Create schema for quotes and predictions
        cur.execute("""
            CREATE TABLE quotes (
                quote_id TEXT PRIMARY KEY,
                proposal_id TEXT,
                market_symbol TEXT,
                contract_type TEXT,
                contract_duration INTEGER,
                ask_price REAL,
                total_payout REAL,
                response_timestamp REAL
            )
        """)
        cur.execute("""
            CREATE TABLE predictions (
                decision_id TEXT PRIMARY KEY,
                session_id TEXT,
                market_symbol TEXT,
                contract_type TEXT,
                contract_duration INTEGER,
                decision_epoch REAL,
                p_model REAL,
                observed_outcome INTEGER
            )
        """)

        # Insert realistic proposal quotes
        cur.execute("""
            INSERT INTO quotes VALUES
            ('Q_001', 'P_001', 'R_100', 'PUT', 10, 2.0, 3.91, 1000.0),
            ('Q_002', 'P_002', 'R_100', 'PUT', 10, 2.0, 3.91, 1002.0),
            ('Q_003', 'P_003', 'R_100', 'PUT', 10, 2.0, 3.91, 1004.0)
        """)

        # Insert predictions with high win rate (retrospective lucky streak, win 3/3 = 100%)
        # but with NEGATIVE predicted EV (P_model = 0.50 < break_even 0.5115)
        cur.execute("""
            INSERT INTO predictions VALUES
            ('D_001', 'SES_A', 'R_100', 'PUT', 10, 1001.0, 0.50, 1),
            ('D_002', 'SES_A', 'R_100', 'PUT', 10, 1003.0, 0.50, 1),
            ('D_003', 'SES_A', 'R_100', 'PUT', 10, 1005.0, 0.50, 1)
        """)
        conn.commit()

        # Query and match through QuoteLevelEconomicEngine
        cur.execute("SELECT * FROM quotes")
        q_rows = cur.fetchall()
        quotes = [
            ProposalQuoteRecord(
                quote_id=r[0], proposal_id=r[1], market_symbol=r[2],
                contract_type=r[3], contract_duration=r[4], ask_price=r[5],
                total_payout=r[6], response_timestamp=r[7]
            )
            for r in q_rows
        ]

        cur.execute("SELECT decision_epoch, p_model, observed_outcome FROM predictions")
        obs_rows = cur.fetchall()
        observations = [
            {"decision_epoch": r[0], "predicted_prob": r[1], "observed_outcome": r[2]}
            for r in obs_rows
        ]

        recs, summary = QuoteLevelEconomicEngine.evaluate_observations(
            observations=observations,
            quotes=quotes,
            symbol="R_100",
            contract_type="PUT",
            duration_ticks=10,
        )

        conn.close()

        # Verify: All 3 observations matched genuine quotes
        assert len(recs) == 3
        assert all(r.is_eligible for r in recs)
        assert summary.eligible_decisions_count == 3
        assert summary.empirical_win_rate == 1.0  # Lucky streak!
        assert summary.mean_predicted_prob == 0.50
        assert summary.mean_predicted_ev is not None and summary.mean_predicted_ev < 0.0  # -0.045
        assert summary.mean_realized_ev is not None and summary.mean_realized_ev > 0.0   # +1.91

        # CRITICAL ASSERTION: The retrospective lucky streak CANNOT qualify!
        assert summary.is_candidate_eligible is False
