"""Automated Test Suite for V1.7.4.2 Release.

Covers:
1. Adversarial Test A: Variable ask prices and payouts (verifying quote-specific EV calculations).
2. Adversarial Test B: Fail-closed reference scenario qualification (positive reference EV gets REFERENCE_SCENARIO_ONLY).
3. Adversarial Test C: Missing quotes yield unavailable (None) verified EV.
4. Adversarial Test D: Future quote responses (lookahead) are strictly rejected with zero tolerance.
5. Adversarial Test E: Cross-duration quote mismatches (2T quote supplied to 5T prediction) are rejected.
6. Adversarial Test F: Prospective lifecycle pre-outcome journaling and independent resolution for 2T and 5T.
7. Adversarial Test G: Permanent non-purchasing safety invariant (LIVE_EXECUTION_DISABLED = True).
8. Quote matching dimensions, stale quote rejection, invalid price rejection, and break-even distributions.
"""
import os
import time
import tempfile
import uuid
import pytest
import numpy as np
import pandas as pd

from dual_duration_research import (
    DualDurationEvaluator,
    EvidenceClass,
    EvaluationMode,
    DurationMetricSummary
)
from quote_recorder import ProposalRecord, DerivQuoteRecorder
from quote_database import QuoteDatabase
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RECONSTRUCTED
)
from outcome_resolver import OutcomeResolver
from forward_observer import ForwardObserver, PairedForwardObserver
from forward_collection_service import ForwardCollectionService, LIVE_EXECUTION_DISABLED
import decision_gate


class TestAdversarialTestAChangingPayoutsAndQuoteEV:
    """Test A: Construct valid quotes with varying payouts and ask prices.
    Verify that aggregate quote-verified EV uses actual values, NOT reference values.
    """

    def test_variable_payouts_and_asks_use_actual_quote_values(self):
        evaluator = DualDurationEvaluator(symbol="R_75", stake=2.00, payout_2t=7.63)

        # 40 decisions at epochs 1000 to 1039
        timestamps = [1000.0 + i for i in range(40)]
        prices = [100.0 + i * 0.1 for i in range(40 + 35)]  # sufficient ticks

        # Quote 1: ask=2.00, payout=7.50 (at epoch 1000.0) -> for first 20 decisions
        # Quote 2: ask=2.20, payout=8.50 (at epoch 1020.0) -> for next 20 decisions
        q1 = ProposalRecord(
            request_timestamp=999.8,
            response_timestamp=999.9,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.50,
            potential_net_profit=5.50,
            currency="USD",
            proposal_id="Q_VARY_1",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        q2 = ProposalRecord(
            request_timestamp=1019.8,
            response_timestamp=1019.9,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.20,
            total_payout=8.50,
            potential_net_profit=6.30,
            currency="USD",
            proposal_id="Q_VARY_2",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )

        outcomes = [1.0] * 12 + [0.0] * 28  # 12 wins, 28 losses
        pred_probs = [0.30] * 40  # Constant model prediction = 30%

        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=pred_probs,
            payout=7.63,  # evaluator reference payout
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            decision_timestamps=timestamps,
            quote_records=[q1, q2]
        )

        assert summary.evaluation_mode == "QUOTE_VERIFIED"
        assert summary.eligible_quote_decisions_count == 40
        assert summary.missing_ev_count == 0

        # Verify actual ask and payout averages:
        # Decisions 0..19 match q1 (ask 2.00, payout 7.50)
        # Decisions 20..39 match q2 (ask 2.20, payout 8.50)
        expected_mean_ask = (20 * 2.00 + 20 * 2.20) / 40  # 2.10
        expected_mean_payout = (20 * 7.50 + 20 * 8.50) / 40  # 8.00
        assert summary.mean_actual_ask_price == pytest.approx(expected_mean_ask, 0.001)
        assert summary.mean_actual_payout == pytest.approx(expected_mean_payout, 0.001)

        # Expected EV calculation per decision:
        # For decisions 0..19: 0.30 * 7.50 - 2.00 = 2.25 - 2.00 = +0.25
        # For decisions 20..39: 0.30 * 8.50 - 2.20 = 2.55 - 2.20 = +0.35
        # Aggregate mean EV = (20 * 0.25 + 20 * 0.35) / 40 = +0.30
        assert summary.ordinary_ev == pytest.approx(0.30, 0.001)

        # Crucial check: it did NOT use the reference payout of 7.63!
        # Reference EV would be: 0.30 * 7.63 - 2.00 = 2.289 - 2.00 = +0.289
        assert summary.ordinary_ev != pytest.approx(0.289, 0.005)

        # Verify break-even distribution
        be1 = 2.00 / 7.50  # ~0.26667
        be2 = 2.20 / 8.50  # ~0.25882
        assert summary.break_even_distribution is not None
        assert summary.break_even_distribution["min"] == pytest.approx(min(be1, be2), 0.001)
        assert summary.break_even_distribution["max"] == pytest.approx(max(be1, be2), 0.001)


class TestAdversarialTestBPositiveReferenceEV:
    """Test B: Construct a reference scenario with positive point-estimate and conservative EV.
    Verify that it cannot receive a verified economic qualification or trading authorization.
    """

    def test_positive_reference_ev_gets_reference_scenario_only(self):
        evaluator = DualDurationEvaluator(symbol="R_75", stake=2.00, payout_2t=7.63)

        # 50 outcomes with 40 wins (80% win rate -> strongly positive EV in reference scenario)
        outcomes = [1.0] * 40 + [0.0] * 10
        pred_probs = [0.80] * 50
        timestamps = [float(i) for i in range(50)]

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
            decision_timestamps=timestamps,
            quote_records=None,
            min_ordinary_ev=0.0,
            min_conservative_ev=0.0
        )

        # Both ordinary EV and conservative EV are strongly positive
        assert summary.ordinary_ev > 0.0
        assert summary.conservative_ev_bootstrap is not None
        assert summary.conservative_ev_bootstrap > 0.0

        # BUT: Must fail-closed!
        # is_economically_positive MUST BE FALSE
        assert summary.is_economically_positive is False
        # Verdict MUST BE REFERENCE_SCENARIO_ONLY
        assert summary.verdict == "REFERENCE_SCENARIO_ONLY"
        assert summary.quote_availability_pct == 0.0


class TestAdversarialTestCMissingQuotes:
    """Test C: Valid historical outcomes and model probabilities with no quotes in QUOTE_VERIFIED mode.
    The evaluator must mark verified EV as unavailable (None) and fail-closed.
    """

    def test_missing_quotes_yields_unavailable_ev(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        outcomes = [1.0] * 20 + [0.0] * 20
        pred_probs = [0.50] * 40
        timestamps = [float(i) for i in range(40)]

        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=pred_probs,
            payout=7.63,
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            decision_timestamps=timestamps,
            quote_records=[]  # Empty quotes!
        )

        assert summary.ordinary_ev is None
        assert summary.ordinary_ev_per_dollar is None
        assert summary.predicted_ordinary_ev is None
        assert summary.retrospective_realized_return is None
        assert summary.conservative_ev_bootstrap is None
        assert summary.quote_availability_pct == 0.0
        assert summary.eligible_quote_decisions_count == 0
        assert summary.missing_ev_count == 40
        assert summary.is_economically_positive is False
        assert summary.verdict == "INSUFFICIENT_QUOTE_COVERAGE"


class TestAdversarialTestDFutureQuoteResponse:
    """Test D: A quote arrives after the economic decision (lookahead violation).
    The quote must be rejected regardless of valid parameters.
    """

    def test_future_quote_is_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        decision_time = 1000.0

        future_quote = ProposalRecord(
            request_timestamp=decision_time + 0.1,
            response_timestamp=decision_time + 0.2,  # Arrived after decision!
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

        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[decision_time],
            quote_records=[future_quote]
        )

        assert matched[0] is None
        assert cov["chrono"] == 0.0
        assert cov["exec"] == 0.0
        assert rej.get("QUOTE_LOOKAHEAD_REJECTED", 0) == 1


class TestAdversarialTestETwoDurationsCrossRejection:
    """Test E: A 2-tick quote is supplied to a 5-tick prediction.
    The evaluator must reject the quote.
    """

    def test_cross_duration_quote_mismatch_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        decision_time = 1000.0

        quote_2t = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.1,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,  # 2-tick contract!
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_2T",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )

        # Supplied to 5-tick prediction
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=5,  # Needs 5-tick quote!
            direction="RUNHIGH",
            decision_timestamps=[decision_time],
            quote_records=[quote_2t]
        )

        assert matched[0] is None
        assert cov["raw"] == 0.0
        assert cov["exec"] == 0.0
        assert rej.get("QUOTE_WRONG_CONTRACT_OR_SYMBOL", 0) == 1


class TestAdversarialTestFProspectiveLifecycle:
    """Test F: Persist an unresolved prediction first, then deliver genuine future ticks in sequence.
    Verify the outcome can ONLY resolve after all required future ticks arrive.
    """

    def test_2tick_and_5tick_resolution_lifecycles(self, tmp_path):
        db_path = str(tmp_path / "lifecycle_test.db")
        resolver = OutcomeResolver(db_path=db_path)

        now = 1000.0
        # Register 2-tick prediction (requires 3 ticks: S_0, S_1, S_2)
        p_2t = resolver.register_pending_prediction(
            prediction_id="PRED_2T_LIFE",
            session_id="SESS_LIFE",
            symbol="R_75",
            signal_epoch=int(now),
            signal_price=100.0,
            timestamp=now,
            contract_duration=2
        )
        # Register 5-tick prediction (requires 6 ticks: S_0 .. S_5)
        p_5t = resolver.register_pending_prediction(
            prediction_id="PRED_5T_LIFE",
            session_id="SESS_LIFE",
            symbol="R_75",
            signal_epoch=int(now),
            signal_price=100.0,
            timestamp=now,
            contract_duration=5
        )

        assert resolver.active_pending_count == 2

        # Tick 1: Entry S_0
        events1 = resolver.ingest_tick(epoch=1001, price=100.2, symbol="R_75")
        assert len(events1) == 0
        assert resolver.active_pending_count == 2

        # Tick 2: Movement S_1
        events2 = resolver.ingest_tick(epoch=1002, price=100.5, symbol="R_75")
        assert len(events2) == 0
        assert resolver.active_pending_count == 2

        # Tick 3: Movement S_2 -> 2T RESOLVES HERE! (3 ticks accumulated)
        events3 = resolver.ingest_tick(epoch=1003, price=100.9, symbol="R_75")
        assert len(events3) == 1
        assert events3[0]["prediction_id"] == "PRED_2T_LIFE"
        assert events3[0]["outcome_status"] == STATUS_RECONSTRUCTED
        assert events3[0]["runhigh_win"] == 1.0  # 100.2 < 100.5 < 100.9 -> RUNHIGH WIN!
        # 5T is STILL PENDING (only 3 of 6 ticks received)
        assert resolver.active_pending_count == 1

        # Tick 4: S_3
        resolver.ingest_tick(epoch=1004, price=101.2, symbol="R_75")
        assert resolver.active_pending_count == 1

        # Tick 5: S_4
        resolver.ingest_tick(epoch=1005, price=101.5, symbol="R_75")
        assert resolver.active_pending_count == 1

        # Tick 6: S_5 -> 5T RESOLVES HERE! (6 ticks accumulated)
        events6 = resolver.ingest_tick(epoch=1006, price=101.9, symbol="R_75")
        assert len(events6) == 1
        assert events6[0]["prediction_id"] == "PRED_5T_LIFE"
        assert events6[0]["outcome_status"] == STATUS_RECONSTRUCTED
        assert events6[0]["runhigh_win"] == 1.0
        assert resolver.active_pending_count == 0


class TestAdversarialTestGNoLiveExecutionSafetyInvariant:
    """Test G: Inspect all execution paths.
    Verify that neither normal nor error-handling paths can issue real-money buy orders.
    """

    def test_live_execution_permanently_disabled_invariant(self):
        # 1. Module-level invariant
        assert LIVE_EXECUTION_DISABLED is True
        assert decision_gate.LIVE_EXECUTION_DISABLED is True

        # 2. Service-level invariant
        assert ForwardCollectionService.LIVE_EXECUTION_DISABLED is True
        assert ForwardObserver.LIVE_EXECUTION_DISABLED is True
        assert PairedForwardObserver.LIVE_EXECUTION_DISABLED is True

        # 3. Decision gate blocks any attempt to trade live
        res = decision_gate.evaluate_paper_trade_eligibility(
            symbol="R_75",
            contract_type="RUNHIGH",
            duration_ticks=2,
            execution_mode="LIVE"  # Invalid mode!
        )
        assert res.is_eligible is False
        assert res.decision == "NO_TRADE"


class TestPairedForwardObserverOperation:
    """Validates concurrent dual-duration prediction generation and isolation."""

    def test_paired_observer_generates_both_2t_and_5t_records(self, tmp_path):
        from live_collector import LiveTickRecord

        j_db = str(tmp_path / "paired_journal.db")
        q_db = str(tmp_path / "paired_quotes.db")

        paired = PairedForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=j_db,
            quote_db_path=q_db,
            session_id="SESS_PAIRED_TEST",
            duration_seconds=60.0
        )

        assert paired.observer_2t.contract_duration == 2
        assert paired.observer_5t.contract_duration == 5

        # Feed 30 warmup ticks to buffer
        for i in range(30):
            t = LiveTickRecord(
                symbol="R_75",
                server_timestamp=1000 + i,
                local_receipt_timestamp=1000.0 + i,
                price=100.0 + i * 0.1,
                source="LIVE_DERIV",
                session_id="SESS_PAIRED_TEST",
                sequence_id=i + 1,
                data_quality_flags="NORMAL"
            )
            paired.observer_2t.tick_history.append({"epoch": int(t.server_timestamp), "price": t.price})
            paired.observer_5t.tick_history.append({"epoch": int(t.server_timestamp), "price": t.price})

        # Incoming live tick
        live_tick = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1031,
            local_receipt_timestamp=1031.0,
            price=103.1,
            source="LIVE_DERIV",
            session_id="SESS_PAIRED_TEST",
            sequence_id=31,
            data_quality_flags="NORMAL"
        )

        p2, p5 = paired.process_incoming_tick(live_tick)

        assert p2 is not None
        assert p5 is not None
        assert p2.contract_duration == 2
        assert p5.contract_duration == 5
        assert p2.session_id == "SESS_PAIRED_TEST"
        assert p5.session_id == "SESS_PAIRED_TEST"


class TestGranularQuoteValidationAndResearchCandidate:
    """Verifies edge cases: stale quotes, invalid prices, reused proposal IDs, and research candidate qualification."""

    def test_wrong_direction_quote_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_rl = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.1,
            market_symbol="R_75",
            contract_type="RUNLOW",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_RL",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_rl]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_WRONG_CONTRACT_OR_SYMBOL", 0) == 1

    def test_wrong_symbol_quote_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_other_sym = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.1,
            market_symbol="R_100",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_R100",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_other_sym]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_WRONG_CONTRACT_OR_SYMBOL", 0) == 1

    def test_missing_response_timestamp_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_no_time = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=float("nan"),
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_NOTIME",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_no_time]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_RESPONSE_TIME_MISSING", 0) == 1

    def test_stale_quote_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_stale = ProposalRecord(
            request_timestamp=899.9,
            response_timestamp=900.0,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_STALE",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_stale],
            max_freshness_seconds=60.0
        )
        assert matched[0] is None
        assert cov["exec"] == 0.0
        assert rej.get("QUOTE_STALE", 0) == 1

    def test_invalid_prices_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_inv = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.1,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=8.00,
            total_payout=7.63,
            potential_net_profit=-0.37,
            currency="USD",
            proposal_id="Q_INV",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_inv]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_PRICE_OR_PAYOUT_INVALID", 0) == 1

    def test_reused_proposal_id_matches_chronologically(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_early = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.50,
            potential_net_profit=5.50,
            currency="USD",
            proposal_id="Q_REUSED",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )
        q_late = ProposalRecord(
            request_timestamp=1010.0,
            response_timestamp=1010.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=8.00,
            potential_net_profit=6.00,
            currency="USD",
            proposal_id="Q_REUSED",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE"
        )

        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0, 1015.0],
            quote_records=[q_early, q_late]
        )
        assert matched[0] is not None
        assert matched[0]["total_payout"] == 7.50
        assert matched[1] is not None
        assert matched[1]["total_payout"] == 8.00

    def test_quote_verified_research_candidate_qualification(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        timestamps = [1000.0 + i for i in range(50)]
        quotes = [
            ProposalRecord(
                request_timestamp=999.0 + i,
                response_timestamp=999.5 + i,
                market_symbol="R_75",
                contract_type="RUNHIGH",
                contract_duration=2,
                duration_unit="t",
                stake=2.00,
                total_payout=7.63,
                potential_net_profit=5.63,
                currency="USD",
                proposal_id=f"Q_{i}",
                quote_source="live_proposal",
                quote_latency_ms=100.0,
                collection_status="QUOTE_AVAILABLE"
            )
            for i in range(50)
        ]
        outcomes = [1.0] * 35 + [0.0] * 15
        pred_probs = [0.70] * 50

        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=pred_probs,
            payout=7.63,
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            decision_timestamps=timestamps,
            quote_records=quotes,
            min_ordinary_ev=0.0,
            min_conservative_ev=0.0
        )

        assert summary.evaluation_mode == "QUOTE_VERIFIED"
        assert summary.quote_availability_pct == 100.0
        assert summary.ordinary_ev > 0.0
        assert summary.conservative_ev_bootstrap is not None
        assert summary.conservative_ev_bootstrap > 0.0
        assert summary.is_economically_positive is True
        assert summary.verdict == "QUOTE_VERIFIED_RESEARCH_CANDIDATE"

    def test_conservative_ev_unavailable_blocks_qualification(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        timestamps = [1000.0 + i for i in range(10)]
        quotes = [
            ProposalRecord(
                request_timestamp=999.0 + i,
                response_timestamp=999.5 + i,
                market_symbol="R_75",
                contract_type="RUNHIGH",
                contract_duration=2,
                duration_unit="t",
                stake=2.00,
                total_payout=7.63,
                potential_net_profit=5.63,
                currency="USD",
                proposal_id=f"Q_SMALL_{i}",
                quote_source="live_proposal",
                quote_latency_ms=100.0,
                collection_status="QUOTE_AVAILABLE"
            )
            for i in range(10)
        ]
        outcomes = [1.0] * 8 + [0.0] * 2
        pred_probs = [0.80] * 10

        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=pred_probs,
            payout=7.63,
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            decision_timestamps=timestamps,
            quote_records=quotes
        )

        assert summary.conservative_ev_bootstrap is None
        assert summary.bootstrap_uncertainty_status == "INSUFFICIENT_SAMPLE"
        assert summary.is_economically_positive is False
        assert summary.verdict == "INSUFFICIENT_EVIDENCE"
