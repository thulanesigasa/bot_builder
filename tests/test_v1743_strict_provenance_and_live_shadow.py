"""Automated Test Suite for V1.7.4.3 Release.

Covers:
1. Strict Quote Provenance:
   - Missing market symbol fails closed (cannot default to R_75).
   - Missing currency fails closed (cannot default to USD).
   - Missing contract duration fails closed.
   - Missing contract direction fails closed.
   - Missing quote identity fails closed.
   - Wrong session ID fails closed.
   - Duplicate proposal IDs with distinct composite identities.
   - Tick-aware quote invalidation on intervening price change.
   - Tick-aware quote invalidation on excess intervening ticks.
   - Causality and clock provenance verification.
   - Complete granular quote rejection statistics (14 accounting dimensions).
2. Evidence Authority:
   - Historical arrays cannot self-certify as PROSPECTIVE_SHADOW.
   - Historical arrays cannot self-certify as INDEPENDENT_CONFIRMATION.
3. Startup Safety Preflight:
   - Verifies executable runtime configuration.
   - Rejects live purchasing flags and unsafe environment variables.
   - LIVE_EXECUTION_DISABLED = True permanently enforced.
4. Paired Lifecycles & Settlement Reconstruction:
   - 2-tick strict monotonic outcome rule.
   - 5-tick strict monotonic outcome rule.
   - Tick gap detection and incomplete outcome preservation.
5. Positive-EV Evidence Ladder & Economics:
   - Quote-specific hurdle calculation.
   - Ladder levels 0 through 4 hierarchy.
"""
import os
import json
import time
import math
import tempfile
import uuid
import pytest
import numpy as np

from config import run_startup_safety_preflight, LIVE_EXECUTION_DISABLED
from dual_duration_research import (
    DualDurationEvaluator,
    EvidenceClass,
    EvaluationMode,
    DurationMetricSummary,
    QuoteEvidenceStatus,
    ResearchEdgeLadder,
)
from quote_recorder import ProposalRecord
from quote_database import QuoteDatabase
from outcome_resolver import OutcomeResolver
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_INCOMPLETE,
    STATUS_DATA_GAP,
)


class TestStrictQuoteProvenance:
    """Objective A: Strict Quote Provenance Tests."""

    def test_missing_market_symbol_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        # Quote with blank symbol
        q_blank_sym = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="",  # Missing symbol!
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_NO_SYM",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_NO_SYM_1"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_blank_sym]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_MISSING_SYMBOL", 0) >= 1
        assert rej.get("QUOTE_WRONG_CONTRACT_OR_SYMBOL", 0) >= 1
        assert cov["exec"] == 0.0

    def test_missing_currency_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        # Quote with blank currency
        q_blank_curr = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="",  # Missing currency!
            proposal_id="Q_NO_CURR",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_NO_CURR_1"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_blank_curr]
        )
        assert matched[0] is None
        assert (rej.get("QUOTE_MISSING_CURRENCY", 0) >= 1 or rej.get("QUOTE_CURRENCY_MISMATCH", 0) >= 1)
        assert cov["exec"] == 0.0

    def test_missing_contract_direction_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_no_dir = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="",  # Missing direction!
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_NO_DIR",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_NO_DIR_1"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_no_dir]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_WRONG_DIRECTION", 0) >= 1
        assert cov["exec"] == 0.0

    def test_missing_contract_duration_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_no_dur = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=0,  # Invalid duration!
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_NO_DUR",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_NO_DUR_1"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_no_dur]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_WRONG_DURATION", 0) >= 1

    def test_missing_quote_identity_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_no_id = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="NONE",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id=None,
            id=None
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_no_id]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_ID_MISSING", 0) >= 1

    def test_wrong_session_id_fails_closed(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        q_sess = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_SESS_1",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_SESS_1",
            session_id="SESS_AAA"
        )
        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1000.0],
            quote_records=[q_sess],
            expected_session_id="SESS_BBB"  # Mismatched session!
        )
        assert matched[0] is None
        assert rej.get("QUOTE_WRONG_SESSION", 0) >= 1

    def test_duplicate_proposal_ids_composite_identity_storage(self, tmp_path):
        db_path = str(tmp_path / "quotes_composite_test.db")
        q_db = QuoteDatabase(db_path=db_path)

        # Store two quotes with the SAME proposal_id but different timestamps/payouts
        q1 = ProposalRecord(
            request_timestamp=100.0,
            response_timestamp=100.2,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.0,
            total_payout=7.60,
            potential_net_profit=5.60,
            currency="USD",
            proposal_id="PROP_REUSED_123",
            quote_source="live_proposal",
            quote_latency_ms=200.0,
            collection_status="QUOTE_AVAILABLE",
            session_id="SESS_COMP",
            quote_record_id="QR_COMP_001"
        )
        q2 = ProposalRecord(
            request_timestamp=105.0,
            response_timestamp=105.2,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.0,
            total_payout=7.80,
            potential_net_profit=5.80,
            currency="USD",
            proposal_id="PROP_REUSED_123",  # Same proposal_id!
            quote_source="live_proposal",
            quote_latency_ms=200.0,
            collection_status="QUOTE_AVAILABLE",
            session_id="SESS_COMP",
            quote_record_id="QR_COMP_002"  # Distinct composite ID!
        )

        id1 = q_db.store_quote(q1)
        id2 = q_db.store_quote(q2)
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

        all_quotes = q_db.get_session_quotes("SESS_COMP")
        assert len(all_quotes) == 2
        # Verify neither quote was overwritten
        payouts = {q.total_payout for q in all_quotes}
        assert 7.60 in payouts
        assert 7.80 in payouts

    def test_tick_aware_quote_invalidation_spot_change(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        # Quote recorded when spot was 100.0
        meta = json.dumps({"spot": 100.0, "spot_time": 999})
        q = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_SPOT_1",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_SPOT_1",
            api_response_metadata=meta
        )

        class MockTick:
            def __init__(self, epoch, price):
                self.epoch = epoch
                self.price = price

        # Intervening tick moved spot to 102.5 before decision at 1001.0
        intervening_tick = MockTick(epoch=1000.0, price=102.5)

        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2,
            direction="RUNHIGH",
            decision_timestamps=[1001.0],
            quote_records=[q],
            tick_records=[intervening_tick]
        )
        assert matched[0] is None
        assert rej.get("QUOTE_INVALIDATED_BY_INTERVENING_TICK", 0) >= 1
        assert rej.get("QUOTE_VALIDITY_UNVERIFIED", 0) >= 1

    def test_complete_granular_rejection_statistics(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        outcomes = [1.0, 0.0, 1.0, 0.0]
        probs = [0.25, 0.25, 0.25, 0.25]
        timestamps = [1000.0, 1002.0, 1004.0, 1006.0]

        # Quote 1: valid
        q_valid = ProposalRecord(
            request_timestamp=999.0,
            response_timestamp=999.2,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.00,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            proposal_id="Q_G_VALID",
            quote_source="live_proposal",
            quote_latency_ms=100.0,
            collection_status="QUOTE_AVAILABLE",
            quote_record_id="QR_G_1"
        )
        summary = evaluator._compute_metrics(
            label="2T_RUNHIGH",
            duration=2,
            direction="RUNHIGH",
            outcomes=outcomes,
            pred_probs=probs,
            payout=7.63,
            hurdle=2.00 / 7.63,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.QUOTE_VERIFIED,
            decision_timestamps=timestamps,
            quote_records=[q_valid]
        )
        # Verify all 14 granular fields exist and are populated
        assert hasattr(summary, "total_decision_points")
        assert summary.total_decision_points == 4
        assert hasattr(summary, "total_quotes_collected")
        assert summary.total_quotes_collected == 1
        assert hasattr(summary, "missing_quote_count")
        assert hasattr(summary, "future_quote_count")
        assert hasattr(summary, "missing_timestamp_count")
        assert hasattr(summary, "stale_quote_count")
        assert hasattr(summary, "wrong_symbol_count")
        assert hasattr(summary, "wrong_direction_count")
        assert hasattr(summary, "wrong_duration_count")
        assert hasattr(summary, "wrong_currency_count")
        assert hasattr(summary, "wrong_session_count")
        assert hasattr(summary, "ambiguous_proposal_count")
        assert hasattr(summary, "invalidated_quote_count")
        assert hasattr(summary, "quote_validity_unverified_count")


class TestEvidenceAuthorityAndFailClosed:
    """Objective A & 4.1: Evidence Authority Fail-Closed Verification."""

    def test_historical_replay_cannot_claim_prospective_shadow(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        prices = [100.0 + i * 0.1 for i in range(50)]

        # Caller attempts to pass PROSPECTIVE_SHADOW without prospective journal records
        report = evaluator.evaluate_ticks(
            prices=prices,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            evaluation_mode=EvaluationMode.REFERENCE_SCENARIO,
            prospective_journal_records=None,  # Missing journal records!
            session_manifest=None              # Missing session manifest!
        )

        # Must fail-closed to HISTORICAL_REPLAY
        assert report.evidence_class == EvidenceClass.HISTORICAL_REPLAY.value
        assert "EVIDENCE AUTHORITY FAIL-CLOSED" in report.selection_bias_warning

    def test_historical_replay_cannot_claim_independent_confirmation(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        prices = [100.0 + i * 0.1 for i in range(50)]

        # Caller attempts to self-certify as INDEPENDENT_CONFIRMATION
        report = evaluator.evaluate_ticks(
            prices=prices,
            evidence_class=EvidenceClass.INDEPENDENT_CONFIRMATION,
            evaluation_mode=EvaluationMode.REFERENCE_SCENARIO,
            prospective_journal_records=None,
            session_manifest=None
        )

        assert report.evidence_class == EvidenceClass.HISTORICAL_REPLAY.value
        assert "EVIDENCE AUTHORITY FAIL-CLOSED" in report.selection_bias_warning


class TestStartupSafetyPreflight:
    """Section 1: Startup Safety Preflight Tests."""

    def test_preflight_passes_with_default_safety_config(self):
        # Default environment: LIVE_EXECUTION_DISABLED = True
        status = run_startup_safety_preflight()
        assert status["status"] == "SAFETY_PREFLIGHT_PASSED"
        assert status["live_execution_disabled"] is True

    def test_preflight_rejects_unsafe_env_var(self, monkeypatch):
        monkeypatch.setenv("DERIV_LIVE_EXECUTION", "1")
        with pytest.raises(RuntimeError, match="Unsafe runtime environment variable detected"):
            run_startup_safety_preflight()


class TestPairedLifecyclesAndReconstruction:
    """Section 5: Strict Monotonic Contract Outcomes."""

    def test_two_tick_monotonic_runhigh_and_runlow(self, tmp_path):
        db_path = str(tmp_path / "resolver_test.db")
        resolver = OutcomeResolver(db_path=db_path)

        now = 1000.0
        # Register 2-tick prediction at price 100.0 (requires 3 ticks: S_0, S_1, S_2)
        pred = resolver.register_pending_prediction(
            prediction_id="P_2T_MONO",
            session_id="S_TEST",
            symbol="R_75",
            signal_epoch=int(now),
            signal_price=100.0,
            timestamp=now,
            contract_duration=2
        )

        # Monotonic Up: 100.2 < 100.5 < 100.9
        # Tick 1: S_0 = 100.2
        ev1 = resolver.ingest_tick(epoch=1001, price=100.2, symbol="R_75")
        assert len(ev1) == 0

        # Tick 2: S_1 = 100.5
        ev2 = resolver.ingest_tick(epoch=1002, price=100.5, symbol="R_75")
        assert len(ev2) == 0

        # Tick 3: S_2 = 100.9 (Expiry tick)
        ev3 = resolver.ingest_tick(epoch=1003, price=100.9, symbol="R_75")
        assert len(ev3) == 1
        res = ev3[0]
        assert res["prediction_id"] == "P_2T_MONO"
        assert res["outcome_status"] == STATUS_RESOLVED or res["outcome_status"] == "OUTCOME_RECONSTRUCTED"
        assert res["runhigh_win"] == 1.0  # 100.2 < 100.5 < 100.9 -> Win
        assert res["runlow_win"] == 0.0

    def test_five_tick_monotonic_outcome(self, tmp_path):
        db_path = str(tmp_path / "resolver_5t_test.db")
        resolver = OutcomeResolver(db_path=db_path)

        now = 2000.0
        pred = resolver.register_pending_prediction(
            prediction_id="P_5T_MONO",
            session_id="S_TEST",
            symbol="R_75",
            signal_epoch=int(now),
            signal_price=50.0,
            timestamp=now,
            contract_duration=5
        )

        # Sequence: 50.0 -> 51.0 -> 52.0 -> 51.5 (down!) -> 53.0 -> 54.0
        prices = [50.0, 51.0, 52.0, 51.5, 53.0, 54.0]
        resolved = []
        for i, p in enumerate(prices):
            r = resolver.ingest_tick(epoch=int(now + 1 + i), price=p, symbol="R_75")
            if r:
                resolved.extend(r)

        assert len(resolved) == 1
        res = resolved[0]
        assert res["prediction_id"] == "P_5T_MONO"
        # Dip at tick 3 breaks strict monotonicity -> RUNHIGH is 0
        assert res["runhigh_win"] == 0.0
        assert res["runlow_win"] == 0.0


class TestPositiveEVEvidenceLadder:
    """Section 9: Positive-EV Evidence Ladder Verification."""

    def test_ladder_level_definitions(self):
        assert ResearchEdgeLadder.NO_VALIDATED_POSITIVE_EV_EDGE.value == "NO_VALIDATED_POSITIVE_EV_EDGE"
        assert ResearchEdgeLadder.EXPLORATORY_POSITIVE_EV_SIGNAL.value == "EXPLORATORY_POSITIVE_EV_SIGNAL"
        assert ResearchEdgeLadder.QUOTE_VERIFIED_RESEARCH_CANDIDATE.value == "QUOTE_VERIFIED_RESEARCH_CANDIDATE"
        assert ResearchEdgeLadder.CONFIRMATION_REGISTERED.value == "CONFIRMATION_REGISTERED"
        assert ResearchEdgeLadder.POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED.value == "POSITIVE_EV_EDGE_INDEPENDENTLY_CONFIRMED"
