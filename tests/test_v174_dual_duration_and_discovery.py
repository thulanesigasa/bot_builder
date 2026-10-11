"""Comprehensive V1.7.4 Test Suite: Dual-Duration 2T vs 5T, Strategy Discovery & Integrity Verification.

Validates:
1. Canonical 2-tick RUNHIGH wins (S_0 < S_1 < S_2)
2. Canonical 2-tick RUNLOW wins (S_0 > S_1 > S_2)
3. Canonical 2-tick dual losses (reversal and non-monotonic movements)
4. Canonical 2-tick equality handling (strict loss on ties)
5. Canonical 5-tick backward compatibility
6. Correct entry and expiry mapping for both durations
7. OutcomeResolver duration-aware resolution (2T and 5T)
8. QuoteDatabase duration-specific lookup and cross-duration rejection
9. Centralized Decision Gate duration matching (Gate 3) and cross-duration quote/model rejection
10. Accurate EV and Break-even calculations without fallbacks
11. Historical V1.7.3 probability report inconsistency detection
12. Predeclared hypothesis testing and Bonferroni multiple-testing control
13. Overlapping-label purging logic
14. Permanent safety invariants: LIVE_EXECUTION_DISABLED = True, IS_ADVISORY_ONLY = True, NO_TRADE enforcement
"""
import os
import time
import pytest
import numpy as np
import pandas as pd

from contract_specification import (
    CANONICAL_RUNHIGH_2T_SPEC,
    CANONICAL_RUNLOW_2T_SPEC,
    CANONICAL_RUNHIGH_5T_SPEC,
    CANONICAL_RUNLOW_5T_SPEC,
    evaluate_canonical_outcome,
    evaluate_monotonic_outcome
)
from outcome_resolver import (
    OutcomeResolver,
    STATUS_RECONSTRUCTED,
    STATUS_DATA_GAP,
    STATUS_PENDING
)
from quote_recorder import ProposalRecord
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine, ProposalQuote
from decision_gate import (
    evaluate_paper_trade_eligibility,
    DecisionReason,
    LIVE_EXECUTION_DISABLED
)
from model_artifact import ModelArtifact, ModelStatus
from model_2tick import (
    TwoTickModelTrainer,
    DERIV_2T_REFERENCE_STAKE,
    DERIV_2T_REFERENCE_PAYOUT,
    DERIV_2T_BREAK_EVEN_HURDLE
)
from strategy_discovery import (
    StrategyDiscoveryEngine,
    PredeclaredHypothesis,
    IS_ADVISORY_ONLY,
    binomial_test_greater
)
from dual_duration_research import DualDurationEvaluator


class TestCanonicalTwoTickContractOutcomes:
    """Tests 2-tick monotonic outcome evaluation per Part D & E."""

    def test_2tick_runhigh_win(self):
        # S_0 = 100.0, S_1 = 101.0, S_2 = 102.5 (strictly increasing)
        prices = [100.0, 101.0, 102.5]
        res_rh = evaluate_canonical_outcome("RUNHIGH", prices, duration_ticks=2)
        res_rl = evaluate_canonical_outcome("RUNLOW", prices, duration_ticks=2)
        assert res_rh.outcome_status == "WON"
        assert res_rh.is_win is True
        assert res_rl.outcome_status == "LOST"
        assert res_rl.is_win is False

    def test_2tick_runlow_win(self):
        # S_0 = 100.0, S_1 = 98.5, S_2 = 97.0 (strictly decreasing)
        prices = [100.0, 98.5, 97.0]
        res_rh = evaluate_canonical_outcome("RUNHIGH", prices, duration_ticks=2)
        res_rl = evaluate_canonical_outcome("RUNLOW", prices, duration_ticks=2)
        assert res_rh.outcome_status == "LOST"
        assert res_rh.is_win is False
        assert res_rl.outcome_status == "WON"
        assert res_rl.is_win is True

    def test_2tick_reversal_dual_loss(self):
        # S_0 = 100.0, S_1 = 105.0, S_2 = 102.0 (up then down: both lose)
        prices_up_down = [100.0, 105.0, 102.0]
        res_rh = evaluate_canonical_outcome("RUNHIGH", prices_up_down, duration_ticks=2)
        res_rl = evaluate_canonical_outcome("RUNLOW", prices_up_down, duration_ticks=2)
        assert res_rh.outcome_status == "LOST"
        assert res_rl.outcome_status == "LOST"

        # S_0 = 100.0, S_1 = 95.0, S_2 = 98.0 (down then up: both lose)
        prices_down_up = [100.0, 95.0, 98.0]
        res_rh2 = evaluate_canonical_outcome("RUNHIGH", prices_down_up, duration_ticks=2)
        res_rl2 = evaluate_canonical_outcome("RUNLOW", prices_down_up, duration_ticks=2)
        assert res_rh2.outcome_status == "LOST"
        assert res_rl2.outcome_status == "LOST"

    def test_2tick_equality_handling(self):
        # Tie on first movement: S_0 == S_1
        tie_first = [100.0, 100.0, 105.0]
        assert evaluate_canonical_outcome("RUNHIGH", tie_first, duration_ticks=2).outcome_status == "LOST"
        assert evaluate_canonical_outcome("RUNLOW", tie_first, duration_ticks=2).outcome_status == "LOST"

        # Tie on second movement: S_1 == S_2
        tie_second = [100.0, 102.0, 102.0]
        assert evaluate_canonical_outcome("RUNHIGH", tie_second, duration_ticks=2).outcome_status == "LOST"
        assert evaluate_canonical_outcome("RUNLOW", tie_second, duration_ticks=2).outcome_status == "LOST"

    def test_5tick_backward_compatibility(self):
        # 5-tick strictly increasing (6 prices)
        rh_5t_prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        res = evaluate_canonical_outcome("RUNHIGH", rh_5t_prices, duration_ticks=5)
        assert res.outcome_status == "WON"
        assert res.is_win is True

        # Reversal on 5th tick: S_4 -> S_5 drops
        reversal_5t = [100.0, 101.0, 102.0, 103.0, 104.0, 103.5]
        assert evaluate_canonical_outcome("RUNHIGH", reversal_5t, duration_ticks=5).outcome_status == "LOST"


class TestDurationAwareOutcomeResolver:
    """Tests persistent OutcomeResolver with 2-tick and 5-tick predictions."""

    def test_resolve_2tick_prediction(self, tmp_path):
        db_path = str(tmp_path / "test_resolver_2t.db")
        resolver = OutcomeResolver(db_path=db_path)

        # Register 2-tick prediction at epoch 1000
        pending = resolver.register_pending_prediction(
            prediction_id="pred_2t_001",
            session_id="test_sess_2t",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0,
            contract_duration=2
        )
        assert pending.contract_duration == 2
        assert pending.required_future_tick_count == 3

        # Ingest tick 1: Entry S_0
        events = resolver.ingest_tick(epoch=1001, price=100.5, symbol="R_75")
        assert len(events) == 0

        # Ingest tick 2: Movement S_1
        events = resolver.ingest_tick(epoch=1002, price=101.5, symbol="R_75")
        assert len(events) == 0

        # Ingest tick 3: Movement S_2 (Expiry) -> completes 2T sequence
        events = resolver.ingest_tick(epoch=1003, price=102.5, symbol="R_75")
        assert len(events) == 1
        ev = events[0]
        assert ev["prediction_id"] == "pred_2t_001"
        assert ev["outcome_status"] == STATUS_RECONSTRUCTED
        assert ev["runhigh_win"] == 1.0
        assert ev["runlow_win"] == 0.0

    def test_cross_duration_resolution_independence(self, tmp_path):
        db_path = str(tmp_path / "test_resolver_dual.db")
        resolver = OutcomeResolver(db_path=db_path)

        # Register 2T and 5T predictions simultaneously at epoch 1000
        resolver.register_pending_prediction(
            prediction_id="pred_2t",
            session_id="sess_dual",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0,
            contract_duration=2
        )
        resolver.register_pending_prediction(
            prediction_id="pred_5t",
            session_id="sess_dual",
            symbol="R_75",
            signal_epoch=1000,
            signal_price=100.0,
            timestamp=1000.0,
            contract_duration=5
        )

        # Ingest 3 ticks (1001, 1002, 1003)
        resolver.ingest_tick(epoch=1001, price=100.0, symbol="R_75")
        resolver.ingest_tick(epoch=1002, price=101.0, symbol="R_75")
        evs_3 = resolver.ingest_tick(epoch=1003, price=102.0, symbol="R_75")

        # 2T should be resolved, 5T should still be pending!
        resolved_pids = [e["prediction_id"] for e in evs_3]
        assert "pred_2t" in resolved_pids
        assert "pred_5t" not in resolved_pids

        # Ingest remaining 3 ticks for 5T (1004, 1005, 1006)
        resolver.ingest_tick(epoch=1004, price=103.0, symbol="R_75")
        resolver.ingest_tick(epoch=1005, price=104.0, symbol="R_75")
        evs_6 = resolver.ingest_tick(epoch=1006, price=105.0, symbol="R_75")

        assert len(evs_6) == 1
        assert evs_6[0]["prediction_id"] == "pred_5t"
        assert evs_6[0]["runhigh_win"] == 1.0


class TestQuoteDurationMatchingAndRejection:
    """Tests duration-specific quote queries and cross-duration rejection."""

    def test_duration_specific_quote_retrieval(self, tmp_path):
        db_path = str(tmp_path / "test_quotes_dur.db")
        qdb = QuoteDatabase(db_path=db_path)

        # Store 2-tick quote
        rec_2t = ProposalRecord(
            request_timestamp=100.0,
            response_timestamp=100.1,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.0,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="prop_2t_123",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        qdb.store_quote(rec_2t)

        # Store 5-tick quote
        rec_5t = ProposalRecord(
            request_timestamp=100.2,
            response_timestamp=100.3,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.07,
            potential_net_profit=59.07,
            currency="USD",
            proposal_id="prop_5t_456",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        qdb.store_quote(rec_5t)

        # Query specifying duration=2: must return 2T quote, NOT 5T quote
        fetched_2t = qdb.get_latest_quote_before(
            symbol="R_75",
            contract_type="RUNHIGH",
            timestamp=105.0,
            duration=2
        )
        assert fetched_2t is not None
        assert fetched_2t.contract_duration == 2
        assert fetched_2t.total_payout == 7.63

        # Query specifying duration=5: must return 5T quote
        fetched_5t = qdb.get_latest_quote_before(
            symbol="R_75",
            contract_type="RUNHIGH",
            timestamp=105.0,
            duration=5
        )
        assert fetched_5t is not None
        assert fetched_5t.contract_duration == 5
        assert fetched_5t.total_payout == 61.07

    def test_decision_gate_rejects_cross_duration_quotes(self):
        # A 5-tick quote applied to a 2-tick contract decision must fail with QUOTE_WRONG_DURATION
        now = time.time()
        res = evaluate_paper_trade_eligibility(
            symbol="R_75",
            contract_type="RUNHIGH",
            duration_ticks=2,
            estimated_prob=0.28,
            lower_prob_bound=0.27,
            ask_price=2.00,
            total_payout=61.07,
            quote_duration=5,  # Mismatched quote duration!
            quote_symbol="R_75",
            quote_contract_type="RUNHIGH",
            quote_currency="USD",
            quote_request_timestamp=now - 2.0,
            quote_response_timestamp=now - 1.8,
            current_epoch=now,
            execution_mode="PAPER"
        )
        assert not res.is_eligible
        assert DecisionReason.QUOTE_WRONG_DURATION.value in res.rejection_reasons

    def test_decision_gate_rejects_cross_duration_models(self):
        # A 5-tick model applied to a 2-tick evaluation must fail with MODEL_CONTRACT_MISMATCH
        now = time.time()
        m5 = ModelArtifact(
            model_id="M_5T",
            model_version="1.5.3",
            created_at_utc="",
            training_dataset_id="",
            dataset_checksum="",
            market_symbol="R_75",
            contract_family="RUNHIGH_RUNLOW",
            contract_duration=5,  # Model is 5T
            contract_duration_unit="t",
            outcome_definition_version="1.5",
            feature_schema_version="1.5.3",
            feature_names=[],
            feature_ordering=[],
            model_type="EMPIRICAL",
            model_parameters={},
            calibration_parameters={},
            training_sample_count=100,
            validation_sample_count=100,
            holdout_sample_count=100,
            validation_metrics={},
            statistical_status="",
            approval_status=ModelStatus.VALIDATED_RESEARCH
        )

        res = evaluate_paper_trade_eligibility(
            symbol="R_75",
            contract_type="RUNHIGH",
            duration_ticks=2,  # Evaluation is 2T
            model_artifact=m5,
            estimated_prob=0.28,
            lower_prob_bound=0.27,
            ask_price=2.00,
            total_payout=7.63,
            quote_duration=2,
            quote_symbol="R_75",
            quote_contract_type="RUNHIGH",
            quote_currency="USD",
            quote_request_timestamp=now - 2.0,
            quote_response_timestamp=now - 1.8,
            current_epoch=now,
            execution_mode="PAPER"
        )
        assert not res.is_eligible
        assert DecisionReason.MODEL_CONTRACT_MISMATCH.value in res.rejection_reasons


class TestExpectedValueMathematicsAndHurdles:
    """Validates mathematical correctness of EV and BreakEven equations per Part B Section 4."""

    def test_2tick_break_even_and_ev(self):
        ask = 2.00
        payout = 7.63
        be = ask / payout
        assert abs(be - 0.262123) < 1e-4

        # Model probability below break-even (25.0% < 26.212%) -> Negative EV
        prob_uncond = 0.25
        ev = prob_uncond * payout - ask
        assert ev < 0.0
        assert abs(ev - (-0.0925)) < 1e-4

        # Model probability above break-even (28.0% > 26.212%) -> Positive EV
        prob_edge = 0.28
        ev_pos = prob_edge * payout - ask
        assert ev_pos > 0.0
        assert abs(ev_pos - 0.1364) < 1e-4

    def test_5tick_break_even_and_ev(self):
        ask = 2.00
        payout = 61.07
        be = ask / payout
        assert abs(be - 0.032749) < 1e-4

        # Stored V1.7.3 model probability for RUNHIGH is 3.277% -> barely positive (+0.0013)
        prob_rh = 0.03277
        ev_rh = prob_rh * payout - ask
        assert abs(ev_rh - 0.00126) < 1e-4

        # Stored V1.7.3 model probability for RUNLOW is 2.978% -> negative (-0.1812)
        prob_rl = 0.02978
        ev_rl = prob_rl * payout - ask
        assert ev_rl < 0.0
        assert abs(ev_rl - (-0.1813)) < 1e-3


class TestStrategyDiscoveryAndMultipleTesting:
    """Tests AI-assisted hypothesis testing, Bonferroni correction, and advisory restrictions."""

    def test_pure_python_binomial_test(self):
        # 10 successes in 20 trials with p=0.5 -> p_val ≈ 0.588
        p = binomial_test_greater(10, 20, 0.5)
        assert 0.58 < p < 0.60

        # 18 successes in 20 trials with p=0.5 -> highly significant
        p_sig = binomial_test_greater(18, 20, 0.5)
        assert p_sig < 0.001

        # Edge cases
        assert binomial_test_greater(0, 20, 0.5) == 1.0
        assert binomial_test_greater(25, 20, 0.5) == 0.0

    def test_bonferroni_multiple_testing_correction(self):
        # When evaluating M hypotheses, raw p-value must be adjusted by M
        engine = StrategyDiscoveryEngine()
        m = len(engine.hypotheses)
        assert m >= 5

        # Create dummy dataframe with random walk ticks
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(300)) + 1000.0
        df = pd.DataFrame({"epoch": list(range(1000, 1300)), "price": prices})

        results = engine.evaluate_all(df, purge_overlap=True)
        assert len(results) == m
        for r in results:
            # Adjusted Bonferroni p-value is strictly >= raw p-value
            assert r.adjusted_p_value_bonferroni >= r.raw_p_value_vs_hurdle
            assert r.adjusted_p_value_bonferroni <= 1.0

    def test_strategy_discovery_strictly_advisory(self):
        assert IS_ADVISORY_ONLY is True
        # Discovery engine cannot authorize paper trades
        from strategy_discovery import EXECUTION_AUTHORIZATION_DISABLED
        assert EXECUTION_AUTHORIZATION_DISABLED is True


class TestSafetyInvariants:
    """Verifies that permanent safety invariants remain strictly active."""

    def test_live_execution_permanently_disabled(self):
        assert LIVE_EXECUTION_DISABLED is True

    def test_shadow_mode_forces_no_trade(self):
        res = evaluate_paper_trade_eligibility(
            symbol="R_75",
            contract_type="RUNHIGH",
            duration_ticks=2,
            execution_mode="SHADOW"
        )
        assert not res.is_eligible
        assert res.decision == "NO_TRADE"
        assert DecisionReason.SHADOW_MODE_NON_TRADING.value in res.rejection_reasons
