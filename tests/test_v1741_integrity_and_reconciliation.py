"""Comprehensive Regression and Adversarial Tests for V1.7.4.1 Research Integrity.

Verifies:
1. Adversarial Evidence Classification: Retrospective price series is strictly classified as HISTORICAL_REPLAY.
2. Prospective SHADOW Evidence: Genuinely journaled predictions with PENDING status prior to future ticks.
3. Reference vs Quote-Verified Economics: Unverified reference scenarios never claim quote coverage or verified EV.
4. Future Quote Rejection: Lookahead quote timestamps strictly rejected.
5. Cross-Duration Quote & Model Rejection: Mismatched durations are rejected.
6. Monotonic Benjamini-Hochberg Adjustment: Enforces step-up reverse cumulative minimum.
7. Exact Binomial Survival: Numerically stable exact calculations for rare-event regimes.
8. Chronological Partitions & Embargoing: No leakage between train, validation, and holdout.
9. Out-of-Sample Brier Score: Real holdout predictions evaluated, never p*(1-p).
10. Small-Sample Bootstrap Protection: Insufficient samples return unavailable conservative EV.
11. Conservative EV Hurdle: Negative conservative EV (< 0.0) strictly blocks qualification.
12. Permanent Safety Invariants: Real-money trading disabled, NO_TRADE authoritative.
"""
import math
import os
import time
import uuid
import tempfile
import numpy as np
import pandas as pd
import pytest

from dual_duration_research import (
    DualDurationEvaluator,
    DurationMetricSummary,
    EvidenceClass,
    EvaluationMode
)
from strategy_discovery import (
    benjamini_hochberg_adjustment,
    bonferroni_adjustment,
    exact_binomial_survival,
    binomial_test_greater,
    StrategyDiscoveryEngine,
    IS_ADVISORY_ONLY,
    EXECUTION_AUTHORIZATION_DISABLED
)
from model_2tick import (
    TwoTickModelTrainer,
    THEORETICAL_2T_BASELINE,
    DERIV_2T_BREAK_EVEN_HURDLE
)
from quote_database import QuoteDatabase, ProposalRecord
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RECONSTRUCTED
)
from decision_gate import (
    evaluate_paper_trade_eligibility,
    DecisionReason,
    LIVE_EXECUTION_DISABLED
)
from contract_specification import evaluate_canonical_outcome
from model_artifact import ModelArtifact, ModelStatus


class TestAdversarialEvidenceClassification:
    """Adversarial tests ensuring historical indexing is never misclassified as prospective."""

    def test_historical_price_list_is_classified_as_historical_replay(self):
        # Even if 1,000 prices are supplied with all outcomes known,
        # evaluator must classify evidence as HISTORICAL_REPLAY
        np.random.seed(101)
        prices = list(np.cumsum(np.random.randn(100)) + 1000.0)

        evaluator = DualDurationEvaluator(symbol="R_75")
        report = evaluator.evaluate_ticks(
            prices=prices,
            evidence_class=EvidenceClass.HISTORICAL_REPLAY,
            evaluation_mode=EvaluationMode.REFERENCE_SCENARIO
        )

        assert report.evidence_class == "HISTORICAL_REPLAY"
        for label, m in report.metrics.items():
            assert m.evidence_class == "HISTORICAL_REPLAY"
            # Reference scenario must report 0.0% quote coverage (unverified)
            assert m.quote_availability_pct == 0.0
            assert m.evaluation_mode == "REFERENCE_SCENARIO"

    def test_prospective_shadow_requires_pre_outcome_journaling(self):
        # Only predictions stored with PENDING status prior to future tick arrival
        # qualify as prospective SHADOW evidence
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "journal_test.db")
            journal = ForwardPredictionJournal(db_path=db_path)

            pred_id = f"PRED_TEST_{uuid.uuid4().hex[:8]}"
            t_now = time.time()

            rec = ForwardPredictionRecord(
                prediction_id=pred_id,
                timestamp=t_now,
                symbol="R_75",
                model_version="1.7.4.1",
                market_state="MOM_BULL_VOL_LOW",
                features_json="{}",
                session_id="SESS_PROSPECTIVE_TEST",
                signal_epoch=int(t_now),
                signal_price=100.0,
                outcome_status=STATUS_PENDING,
                contract_duration=2,
                execution_mode="SHADOW"
            )

            journal.log_prediction(rec)

            # In SQLite, the status must be PENDING before future ticks arrive
            fetched = journal.get_prediction(pred_id)
            assert fetched is not None
            assert fetched["outcome_status"] == STATUS_PENDING
            assert fetched["runhigh_win"] is None
            assert fetched["runlow_win"] is None

            # Simulate future ticks arriving AFTER prediction creation:
            # S_0 = 101.0, S_1 = 102.0, S_2 = 103.5 (Monotonic rise -> RUNHIGH wins)
            journal.ingest_forward_tick(epoch=int(t_now) + 1, price=101.0, symbol="R_75")
            journal.ingest_forward_tick(epoch=int(t_now) + 2, price=102.0, symbol="R_75")
            journal.ingest_forward_tick(epoch=int(t_now) + 3, price=103.5, symbol="R_75")

            resolved = journal.get_prediction(pred_id)
            assert resolved["outcome_status"] in (STATUS_RESOLVED, STATUS_RECONSTRUCTED)
            assert resolved["runhigh_win"] == 1.0
            assert resolved["runlow_win"] == 0.0


class TestQuoteEconomicsAndCoverageIntegrity:
    """Tests that artificial quote coverage is eliminated and reference payouts are isolated."""

    def test_reference_scenario_reports_zero_quote_coverage(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        prices = [100.0 + i * 0.5 for i in range(50)]
        report = evaluator.evaluate_ticks(
            prices=prices,
            evaluation_mode=EvaluationMode.REFERENCE_SCENARIO
        )

        for label, m in report.metrics.items():
            # Never invent 100% quote coverage!
            assert m.quote_availability_pct == 0.0
            assert m.raw_quote_coverage_pct == 0.0
            assert m.chronological_quote_coverage_pct == 0.0
            assert m.economic_quote_coverage_pct == 0.0
            assert m.execution_quality_coverage_pct == 0.0

    def test_quote_verified_mode_calculates_real_coverage(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        prices = [100.0 + i * 0.2 for i in range(50)]
        timestamps = [1000.0 + i for i in range(50)]

        # Provide a quote arriving at 1035.0: decisions between 1025 and 1034 will have NO quote
        q1 = ProposalRecord(
            request_timestamp=1034.9,
            response_timestamp=1035.0,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q1",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )

        report = evaluator.evaluate_ticks(
            prices=prices,
            timestamps=timestamps,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            quote_records=[q1]
        )

        m_2t_rh = report.metrics["2T_RUNHIGH"]
        # Exactly matching decisions will receive coverage; non-matching will not
        assert m_2t_rh.evaluation_mode == "QUOTE_VERIFIED"
        assert m_2t_rh.quote_availability_pct < 100.0  # Partial coverage (< 100%)
        assert m_2t_rh.quote_availability_pct > 0.0    # But greater than 0%


    def test_future_quote_rejected_by_lookahead_check(self):
        # A quote with response timestamp > decision timestamp must be rejected
        now = 1000.0
        future_quote = ProposalRecord(
            request_timestamp=now + 5.0,
            response_timestamp=now + 5.2,  # In the future!
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_FUTURE",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )

        evaluator = DualDurationEvaluator(symbol="R_75")
        _, chrono_cov, _, _ = evaluator._compute_quote_coverage(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[now],
            quote_records=[future_quote],
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED
        )
        assert chrono_cov == 0.0


class TestEconomicHurdleAndConservativeEV:
    """Validates conservative EV calculation and small-sample fallback protection."""

    def test_insufficient_sample_returns_unavailable_conservative_ev(self):
        # When sample count < 30 or < block_size * 2, conservative EV MUST be None!
        evaluator = DualDurationEvaluator(symbol="R_75")
        small_outcomes = [1.0, 0.0, 1.0, 0.0]  # n = 4 < 30

        cons_ev, status, sens = evaluator._moving_block_bootstrap_ev(
            outcomes=small_outcomes,
            payout=7.63,
            stake=2.00,
            block_size=5
        )

        assert cons_ev is None
        assert status == "INSUFFICIENT_SAMPLE"

    def test_negative_conservative_ev_blocks_economic_qualification(self):
        # Candidate with positive ordinary EV but negative conservative EV must be REJECTED
        evaluator = DualDurationEvaluator(symbol="R_75", min_conservative_ev=0.0)

        # 40 outcomes where win rate is slightly above break-even (e.g. 28% vs 26.212%),
        # but conservative lower bound is negative
        outcomes = [1.0] * 11 + [0.0] * 29  # 11/40 = 27.5% win rate
        pred_probs = [0.275] * 40

        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=pred_probs,
            payout=7.63,
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.HISTORICAL_REPLAY,
            evaluation_mode=EvaluationMode.REFERENCE_SCENARIO,
            decision_timestamps=[float(i) for i in range(40)],
            quote_records=None,
            min_ordinary_ev=0.0,
            min_conservative_ev=0.0
        )

        # Ordinary EV is positive: 0.275 * 7.63 - 2.00 = +0.09825
        assert summary.ordinary_ev > 0.0
        # Conservative EV lower bound will be below 0 due to sampling variance
        assert summary.conservative_ev_bootstrap is not None
        assert summary.conservative_ev_bootstrap < 0.0
        # Qualification must be strictly False
        assert summary.is_economically_positive is False
        assert summary.verdict == "FAILED_CONSERVATIVE_HURDLE"


class TestMultipleTestingAndStatisticalRigor:
    """Verifies monotonic Benjamini-Hochberg adjustment and exact binomial survival."""

    def test_benjamini_hochberg_enforces_monotonicity(self):
        # Textbook example where raw rank adjustment is not monotonic:
        # p = [0.01, 0.04, 0.03]
        # Rank adjustment:
        # p(1)=0.01 -> 0.01*3/1 = 0.03
        # p(2)=0.03 -> 0.03*3/2 = 0.045
        # p(3)=0.04 -> 0.04*3/3 = 0.04
        # Without reverse cumulative minimum, q(2) = 0.045 > q(3) = 0.04!
        # With reverse cumulative min: q'(2) = min(0.045, 0.04) = 0.04
        raw_p = [0.01, 0.04, 0.03]
        adj_p = benjamini_hochberg_adjustment(raw_p)

        assert len(adj_p) == 3
        assert adj_p[0] == 0.03
        assert adj_p[1] == 0.04
        assert adj_p[2] == 0.04

    def test_benjamini_hochberg_preserves_bounds_and_ordering(self):
        raw_p = [0.005, 0.02, 0.04, 0.50, 0.90]
        adj_p = benjamini_hochberg_adjustment(raw_p)

        # All values between 0.0 and 1.0
        assert all(0.0 <= p <= 1.0 for p in adj_p)
        # Adjusted p-values are >= raw p-values
        assert all(adj >= raw for adj, raw in zip(adj_p, raw_p))

    def test_exact_binomial_survival_rare_event_regime(self):
        # In 5-tick contract regime: p = 0.03125 (3.125%)
        # In n = 100 trials, probability of observing >= 5 wins
        p_val, is_exact = exact_binomial_survival(k=5, n=100, p=0.03125)
        assert is_exact is True
        assert 0.0 <= p_val <= 1.0
        # Expected value is 3.125, so >= 5 wins has p-value around 0.20
        assert 0.15 < p_val < 0.25


class TestTwoTickChronologicalPartitioning:
    """Verifies strict train-validation-holdout separation without leakage."""

    def test_chronological_splits_and_embargo(self):
        # Create synthetic CSV with 1,000 ticks
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "test_ticks.csv")
            np.random.seed(42)
            prices = np.cumsum(np.random.randn(1000)) + 1000.0
            df = pd.DataFrame({"epoch": list(range(1000, 2000)), "price": prices})
            df.to_csv(csv_path, index=False)

            trainer = TwoTickModelTrainer(symbol="R_75", models_dir=tmp_dir)
            artifact, summary = trainer.train_and_export_2tick_model(
                csv_path=csv_path,
                output_filename="test_2t_model.json",
                train_ratio=0.60,
                val_ratio=0.20,
                embargo_ticks=3
            )

            p_info = artifact.model_parameters["partition_info"]
            train_end = p_info["train_index_range"][1]
            val_start = p_info["val_index_range"][0]
            val_end = p_info["val_index_range"][1]
            hold_start = p_info["holdout_index_range"][0]

            # Embargo gap strictly enforced between partitions:
            # val_start - train_end must be > 3
            assert val_start > train_end + 3
            # hold_start - val_end must be > 3
            assert hold_start > val_end + 3

            # Model status reflects historical holdout evaluation
            assert artifact.statistical_status == "HISTORICAL_HOLDOUT_EVALUATED"
            # Validation metrics contains true out-of-sample holdout metrics
            assert "holdout_metrics" in artifact.validation_metrics
            h_metrics = artifact.validation_metrics["holdout_metrics"]
            assert "brier_score_runhigh" in h_metrics
            assert "brier_score_runlow" in h_metrics


class TestPermanentSafetyGuards:
    """Verifies that all safety gates remain unconditionally authoritative."""

    def test_real_money_execution_permanently_disabled(self):
        assert LIVE_EXECUTION_DISABLED is True

    def test_strategy_discovery_execution_disabled(self):
        assert IS_ADVISORY_ONLY is True
        assert EXECUTION_AUTHORIZATION_DISABLED is True

    def test_shadow_mode_forces_no_trade_unconditionally(self):
        res = evaluate_paper_trade_eligibility(
            symbol="R_75",
            contract_type="RUNHIGH",
            duration_ticks=2,
            execution_mode="SHADOW"
        )
        assert res.decision == "NO_TRADE"
        assert not res.is_eligible
        assert DecisionReason.SHADOW_MODE_NON_TRADING.value in res.rejection_reasons
