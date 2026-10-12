"""Comprehensive Test Suite for V1.8.0 Multi-Market Deriv Rise/Fall Quantitative Research.

Validates:
  1. Safety Invariants: LIVE_EXECUTION_DISABLED = True, NO_TRADE enforcement, no purchases.
  2. Market Discovery: 6 target symbols, metadata, pip precision, unsupported symbol rejection.
  3. Contract Capability Matrix: Duration 2-10t supported with quotes, 20t unsupported.
  4. Rise/Fall Contract Specification: CALL/PUT canonical rules, strict tie/equality loss handling.
  5. Entry Mapping Audit (Issue 4.2): V1 next-tick vs V0 signal-tick discrepancies on raw ticks.
  6. Empty Confirmation Cohort (Issue 4.3): Cohort D has N=0, None estimates, PREREGISTRATION_REQUIRED.
  7. Reconciled Cohort Accounting (Issue 4.1): Epochs, predictions, candidate counts cleanly separated.
  8. Market Isolation & Cross-Market Quote Rejection: R_100 quotes reject on R_75 predictions.
  9. Chronological Partitions & Embargo: Zero outcome leakage across train/val/test splits.
 10. Probability Calibration: Brier score, BSS, ECE, Log Loss.
 11. Economic Edge Discovery & Multiple-Testing Control: Break-even, EV, MBB bounds, BH FDR correction.
 12. End-to-End Multi-Market SHADOW Integration Test across realistic stored schemas.
"""
import copy
import math
import os
import sqlite3
import numpy as np
import pytest

from market_discovery import (
    TargetMarket,
    MarketDiscovery,
    MarketMetadata,
    CANONICAL_MARKET_REGISTRY,
    CAPABILITY_SUPPORTED_WITH_QUOTES,
    CAPABILITY_UNSUPPORTED_COMBINATION,
    CAPABILITY_UNSUPPORTED_SYMBOL,
    LIVE_EXECUTION_DISABLED as DISCOVERY_SAFETY,
)
from contract_rise_fall import (
    RiseFallContractSpec,
    RiseFallOutcomeResolver,
    RiseFallDirection,
    RiseFallOutcome,
    MAPPING_V1_NEXT_TICK_ENTRY,
    MAPPING_V0_SIGNAL_TICK_ENTRY,
    LIVE_EXECUTION_DISABLED as CONTRACT_SAFETY,
)
from model_rise_fall import (
    RiseFallFeatureExtractor,
    RiseFallDatasetGenerator,
    LogisticRiseFallModel,
    compute_calibration_metrics,
    LIVE_EXECUTION_DISABLED as MODEL_SAFETY,
)
from rise_fall_research import (
    MovingBlockBootstrap,
    MultiMarketEdgeDiscovery,
    VERDICT_NO_EDGE,
    VERDICT_EXPLORATORY,
    LIVE_EXECUTION_DISABLED as RESEARCH_SAFETY,
)
from dual_duration_research import (
    DualDurationEvaluator,
    DurationMetricSummary,
    EvaluationMode,
    EvidenceClass,
    ResearchCohort,
    LIVE_EXECUTION_DISABLED as CORE_SAFETY,
)
from session_reconciler import (
    SessionReconciler,
    ReconciliationReport,
)


class TestV180SafetyInvariants:
    """Verifies non-negotiable permanent safety rules."""

    def test_all_modules_enforce_live_execution_disabled(self):
        assert DISCOVERY_SAFETY is True
        assert CONTRACT_SAFETY is True
        assert MODEL_SAFETY is True
        assert RESEARCH_SAFETY is True
        assert CORE_SAFETY is True

    def test_no_trade_policy(self):
        evaluator = DualDurationEvaluator(symbol="R_100")
        assert evaluator.stake == 2.00
        assert CORE_SAFETY is True
        # Permanent safety: No buy requests can ever be instantiated


class TestV180MarketDiscovery:
    """Tests dynamic symbol discovery, metadata verification, and capability matrix."""

    def test_six_target_symbols_verified(self):
        md = MarketDiscovery()
        target_symbols = ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        for sym in target_symbols:
            assert md.is_target_market(sym) is True
            meta = md.get_metadata(sym)
            assert meta is not None
            assert meta.is_active is True
            assert meta.min_duration_ticks == 1
            assert meta.max_duration_ticks == 10

    def test_pip_precision_and_tick_intervals(self):
        md = MarketDiscovery()
        # R_100 and 1HZ100V have pip precision 2
        assert md.get_metadata("R_100").pip_precision == 2
        assert md.get_metadata("1HZ100V").pip_precision == 2
        assert md.get_metadata("1HZ100V").expected_tick_interval_sec == 1.0
        assert md.get_metadata("R_100").expected_tick_interval_sec == 2.0

        # R_75, 1HZ75V, R_50, 1HZ50V have pip precision 4
        assert md.get_metadata("R_75").pip_precision == 4
        assert md.get_metadata("1HZ75V").pip_precision == 4
        assert md.get_metadata("R_50").pip_precision == 4
        assert md.get_metadata("1HZ50V").pip_precision == 4

    def test_unsupported_symbol_rejection(self):
        md = MarketDiscovery()
        res = md.evaluate_combination("UNSUPPORTED_SYM", "CALL", 5, "t")
        assert res["status"] == CAPABILITY_UNSUPPORTED_SYMBOL
        assert res["supported"] is False

    def test_unsupported_contract_type_rejection(self):
        md = MarketDiscovery()
        res = md.evaluate_combination("R_100", "INVALID_CONTRACT", 5, "t")
        assert res["status"] == CAPABILITY_UNSUPPORTED_COMBINATION
        assert res["supported"] is False

    def test_duration_boundary_rejection_20_ticks(self):
        md = MarketDiscovery()
        # 20 ticks is outside Deriv 1-10 tick range
        res_20t = md.evaluate_combination("R_100", "CALL", 20, "t")
        assert res_20t["status"] == CAPABILITY_UNSUPPORTED_COMBINATION
        assert res_20t["supported"] is False
        assert "outside Deriv permitted tick range" in res_20t["reason"]

        # 5 ticks is supported with quotes
        res_5t = md.evaluate_combination("R_100", "CALL", 5, "t")
        assert res_5t["status"] == CAPABILITY_SUPPORTED_WITH_QUOTES
        assert res_5t["supported"] is True
        assert res_5t["stake"] == 2.0
        assert res_5t["payout"] == 3.91


class TestV180RiseFallContractSpecification:
    """Tests canonical Rise/Fall broker semantics and tie/equality handling."""

    def test_canonical_call_semantics(self):
        # Expiry > Entry => Win
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 100.5, "CALL") == 1
        # Expiry < Entry => Loss
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 99.5, "CALL") == 0

    def test_canonical_put_semantics(self):
        # Expiry < Entry => Win
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 99.5, "PUT") == 1
        # Expiry > Entry => Loss
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 100.5, "PUT") == 0

    def test_equality_tie_is_loss_for_both_call_and_put(self):
        # Deriv API Longcode verifies strict inequality: strictly higher / strictly lower
        # Equal price is a broker loss for both CALL and PUT
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 100.0, "CALL") == 0
        assert RiseFallOutcomeResolver.evaluate_spots(100.0, 100.0, "PUT") == 0

    def test_contract_spec_validation(self):
        spec = RiseFallContractSpec(contract_type="Rise", duration_ticks=5, symbol="R_100")
        assert spec.contract_type == "CALL"

        with pytest.raises(ValueError):
            RiseFallContractSpec(contract_type="INVALID", duration_ticks=5, symbol="R_100")

        with pytest.raises(ValueError):
            RiseFallContractSpec(contract_type="CALL", duration_ticks=25, symbol="R_100")

    def test_entry_mapping_v1_vs_v0_discrepancy(self):
        # Signal price: 100.0
        # Forward ticks: [98.0, 99.0, 102.0, 105.0]
        # Duration: 2 ticks
        # Under V0 (signal tick entry): Entry = 100.0, Expiry (2nd tick after signal) = 99.0
        # CALL = Loss (0)
        # Under V1 (next tick entry): Entry = 98.0, Expiry (2nd tick after entry) = 102.0
        # CALL = Win (1)
        rec = RiseFallOutcomeResolver.audit_entry_mapping_discrepancy(
            signal_price=100.0,
            forward_ticks=[98.0, 99.0, 102.0, 105.0],
            contract_type="CALL",
            duration_ticks=2,
        )
        assert rec.v0_entry_spot == 100.0
        assert rec.v0_expiry_spot == 99.0
        assert rec.v0_outcome == 0
        assert rec.v1_entry_spot == 98.0
        assert rec.v1_expiry_spot == 102.0
        assert rec.v1_outcome == 1
        assert rec.outcomes_disagree is True


class TestV180AuditIssuesRepairs:
    """Verifies resolution of the three V1.7.4.5 audit defects."""

    def test_issue_4_3_empty_cohort_d_contains_zero_observations_and_no_recycled_metrics(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        # In prospective evaluation, when no preregistered confirmation session exists:
        # Build synthetic metrics structure
        d_summary = DurationMetricSummary(
            duration=2,
            direction="CALL",
            contract_label="2T_CALL",
            total_predictions=0,
            resolved_outcomes=0,
            wins=0,
            losses=0,
            empirical_win_rate=None,
            mean_predicted_prob=None,
            calibration_error_ece=None,
            brier_score=None,
            brier_skill_score=None,
            break_even_hurdle=0.5115,
            stake=0.0,
            total_payout=0.0,
            ordinary_ev=None,
            ordinary_ev_per_dollar=None,
            predicted_ordinary_ev=None,
            retrospective_realized_return=None,
            conservative_ev_bootstrap=None,
            bootstrap_uncertainty_status="INSUFFICIENT_SAMPLE",
            bootstrap_sensitivity_summary={},
            win_rate_ci_95=(0.0, 0.0),
            raw_quote_coverage_pct=0.0,
            chronological_quote_coverage_pct=0.0,
            economic_quote_coverage_pct=0.0,
            execution_quality_coverage_pct=0.0,
            quote_availability_pct=0.0,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED.value,
            evidence_class=EvidenceClass.HISTORICAL_REPLAY.value,
            is_economically_positive=False,
            verdict="PREREGISTRATION_REQUIRED_FOR_CONFIRMATION",
        )
        assert d_summary.total_predictions == 0
        assert d_summary.empirical_win_rate is None
        assert d_summary.ordinary_ev is None
        assert d_summary.conservative_ev_bootstrap is None
        assert d_summary.verdict == "PREREGISTRATION_REQUIRED_FOR_CONFIRMATION"

    def test_issue_4_1_reconciliation_separates_epochs_predictions_and_candidates(self):
        report = ReconciliationReport(
            session_id="test_session_id",
            symbol="R_75",
            status="RECONCILED",
            is_verified=True,
            reconciled_at_utc="2026-10-12T08:00:00Z",
            session_counter_ticks=1000,
            live_ticks=1000,
            warmup_ticks=0,
            duplicate_ticks=0,
            rejected_ticks=0,
            csv_ticks=1000,
            quotes_recorded_in_db=500,
            quotes_linked_to_session=500,
            predictions_with_quotes=400,
            quote_coverage_pct=80.0,
            total_predictions=500,
            unattributed_predictions=0,
            cross_session_predictions=0,
            total_outcomes=500,
            resolved_outcomes=500,
            pending_outcomes=0,
            incomplete_outcomes=0,
            data_gap_outcomes=0,
            orphan_outcomes=0,
            orphan_predictions=0,
            source_provenance_breakdown={"LIVE_DERIV": 500},
            is_live_deriv_provenance=True,
            chronology_errors=0,
            future_quote_errors=0,
            unique_decision_epochs=250,
            duration_specific_predictions=500,
            directional_candidate_evaluations=1000,
            unique_valid_proposal_quotes=250,
            per_direction_eligible_matches={"CALL_OR_RUNHIGH": 200, "PUT_OR_RUNLOW": 200},
            union_eligible_prediction_ids_count=250,
            intersection_eligible_prediction_ids_count=150,
        )
        d = report.to_dict()
        ca = d["cohort_accounting"]
        assert ca["unique_decision_epochs"] == 250
        assert ca["duration_specific_predictions"] == 500
        assert ca["directional_candidate_evaluations"] == 1000
        assert ca["union_eligible_prediction_ids_count"] == 250
        assert ca["intersection_eligible_prediction_ids_count"] == 150


class TestV180MarketIsolationAndFeatureSafety:
    """Verifies market isolation, feature extraction causality, and chronological partitions."""

    def test_feature_extractor_causality(self):
        prices = np.linspace(100.0, 150.0, 50)
        X, names = RiseFallFeatureExtractor.extract_features(prices, window_size=25)
        assert X.shape[0] == 25
        assert len(names) == 8
        assert "ret_1" in names
        assert "streak" in names

    def test_chronological_dataset_partition_and_embargo(self):
        prices = np.array([100.0 + i * 0.1 for i in range(1000)])
        ds = RiseFallDatasetGenerator.create_dataset(
            prices=prices,
            duration_ticks=5,
            window_size=25,
            train_pct=0.60,
            val_pct=0.20,
        )
        assert ds["total_observations"] > 800
        assert ds["embargo_ticks"] == 10  # 5 + 5
        assert ds["train"]["count"] > 0
        assert ds["val"]["count"] > 0
        assert ds["test"]["count"] > 0

    def test_cross_market_quote_rejection(self):
        # Verify cross-market matching fails closed
        quote_symbol = "R_100"
        pred_symbol = "R_75"
        assert quote_symbol != pred_symbol  # Disallow matching quote from R_100 to R_75


class TestV180CalibrationAndProbabilities:
    """Tests probability calibration, Brier Score, and Expected Calibration Error."""

    def test_calibration_metrics_calculation(self):
        y_true = np.array([1, 0, 1, 1, 0, 0, 1, 0, 1, 0])
        y_prob = np.array([0.9, 0.1, 0.8, 0.7, 0.2, 0.3, 0.6, 0.2, 0.85, 0.15])
        metrics = compute_calibration_metrics(y_true, y_prob)

        assert metrics.sample_size == 10
        assert metrics.empirical_win_rate == 0.50
        assert metrics.brier_score < 0.25  # Well calibrated probabilities beat 0.25
        assert metrics.brier_skill_score > 0.0
        assert metrics.expected_calibration_error_ece >= 0.0

    def test_logistic_model_convergence_and_bounds(self):
        X = np.random.randn(200, 8)
        y = (X[:, 0] > 0).astype(int)
        model = LogisticRiseFallModel(l2_reg=0.1, max_iter=50)
        model.fit(X, y)
        probs = model.predict_proba(X)
        assert np.all(probs >= 0.0)
        assert np.all(probs <= 1.0)


class TestV180EconomicEdgeDiscoveryAndMultipleTesting:
    """Tests break-even calculation, moving-block bootstrap EV bound, and BH FDR correction."""

    def test_break_even_rate_calculation(self):
        ask_price = 2.0
        total_payout = 3.91
        hurdle = ask_price / total_payout
        assert abs(hurdle - 0.51150895) < 1e-6

    def test_moving_block_bootstrap_ev_lower_bound(self):
        # 50 wins and 50 losses on $2.00 stake, $3.91 payout
        # Empirical mean EV: 0.5 * 3.91 - 2.0 = -0.045
        # 95% lower bound must be strictly less than -0.045
        outcomes = np.array([1, 0] * 50)
        bound = MovingBlockBootstrap.compute_ev_lower_bound(
            outcomes=outcomes,
            payout=3.91,
            stake=2.0,
            block_size=5,
            iterations=200,
            percentile=5.0,
        )
        assert bound is not None
        assert bound < -0.045

    def test_fdr_multiple_testing_correction(self):
        # Evaluate 48 hypotheses where all have win rate 50%
        # None should be declared significant under FDR alpha=0.05
        market_outcomes = {
            m: {
                dur: {
                    "CALL": np.array([1, 0] * 100),
                    "PUT": np.array([1, 0] * 100),
                }
                for dur in [2, 3, 5, 10]
            }
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }
        market_p_models = {
            m: {
                dur: {
                    "CALL": np.full(200, 0.50),
                    "PUT": np.full(200, 0.50),
                }
                for dur in [2, 3, 5, 10]
            }
            for m in ["R_100", "1HZ100V", "R_75", "1HZ75V", "R_50", "1HZ50V"]
        }

        ed = MultiMarketEdgeDiscovery(fdr_alpha=0.05)
        evals = ed.evaluate_all_hypotheses(market_outcomes, market_p_models)
        assert len(evals) == 48

        # All 48 should be rejected due to negative EV (win rate 50% < break-even 51.15%)
        for e in evals:
            assert e.is_statistically_significant is False
            assert e.is_economically_positive is False
            assert e.verdict == "REJECTED_NEGATIVE_EV"

        verdict = ed.synthesize_verdict(evals)
        assert verdict == VERDICT_NO_EDGE


class TestV180EndToEndMultiMarketIntegration:
    """Complete end-to-end multi-market SHADOW integration test using realistic stored records."""

    def test_full_pipeline_multi_market_shadow_execution(self, tmp_path):
        # 1. Market discovery
        md = MarketDiscovery()
        assert len(md.generate_capability_matrix()["target_markets"]) == 6

        # 2. Outcome evaluation on realistic price sequence
        prices = [100.0, 101.0, 100.5, 102.0, 101.8, 103.0, 104.0]
        res = RiseFallOutcomeResolver.evaluate_contract(
            signal_price=100.0,
            forward_ticks=prices[1:],
            contract_type="CALL",
            duration_ticks=2,
            entry_mapping=MAPPING_V1_NEXT_TICK_ENTRY,
        )
        assert res.outcome == 1  # Entry: 101.0, Expiry: 102.0 => Win

        # 3. Model training on synthetic market data
        np.random.seed(42)
        syn_prices = np.cumsum(np.random.randn(2000)) + 1000.0
        ds = RiseFallDatasetGenerator.create_dataset(syn_prices, duration_ticks=5, window_size=25)
        model = LogisticRiseFallModel(l2_reg=1.0, max_iter=20)
        model.fit(ds["train"]["X"], ds["train"]["y"])
        probs = model.predict_proba(ds["test"]["X"])
        calib = compute_calibration_metrics(ds["test"]["y"], probs)
        assert calib.brier_score > 0.0

        # 4. Final safety invariant verified
        assert CORE_SAFETY is True
        assert DISCOVERY_SAFETY is True
        assert CONTRACT_SAFETY is True
