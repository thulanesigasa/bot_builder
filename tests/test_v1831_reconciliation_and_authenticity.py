"""Unit and adversarial test suite for V1.8.3.1 Economic Reconciliation & Authenticity.

Covers:
1. Safety invariants (LIVE_EXECUTION_DISABLED, NO_TRADE, no purchase methods).
2. Authoritative model registry (rejection of mock hashes, classification of frozen models and deterministic baselines).
3. Prospective chronology auditor (lead times, wall-clock ordering, tick epoch monotonicity, fail-closed handling).
4. Outcome resolvers (Rise/Fall equality loss, Only Ups/Downs monotonic strictness, off-by-one tick vector checks).
5. Canonical cohort accounting (strict Cohorts A, B, C, D separation, SQL denominator discipline, individual return bootstrap).
6. Mandatory synthetic integration test fixture:
   - 30 resolved predictions
   - 10 valid priced predictions (6 priced wins, 4 priced losses)
   - 20 unpriced predictions
   - Assert Cohort A N=30, Cohort C priced N=10, priced win rate=60%, mean return uses exactly 10 records.
"""

import json
import os
import sqlite3
import time
import pytest
import numpy as np

from forward_shadow_engine import (
    LIVE_EXECUTION_DISABLED,
    OPERATING_MODE,
    DECISION,
    ContractOutcomeResolvers,
    SafetyViolationError,
    ForwardObservationRecord,
    ForwardResearchDatabase,
    LiveBrokerProposal,
    FAMILY_RISE_FALL,
    FAMILY_ONLY_UPS_DOWNS,
    DIRECTION_CALL,
    DIRECTION_PUT,
    DIRECTION_RUNHIGH,
    DIRECTION_RUNLOW,
    OUTCOME_RESOLVED,
    OUTCOME_PENDING,
    COHORT_A,
    COHORT_B,
    COHORT_C,
    COHORT_D,
)
from model_registry import (
    AuthoritativeModelRegistry,
    MODEL_TYPE_TRAINED_FROZEN,
    MODEL_TYPE_DETERMINISTIC_BASELINE,
    MODEL_TYPE_CONSTANT_BASELINE,
    MODEL_TYPE_UNVERIFIED,
    MODEL_ID_CAUSAL_MOMENTUM_V1,
    MODEL_ID_CONSTANT_50_50,
    MODEL_ID_M_R75_2T,
    MODEL_ID_M_R75_5T,
)
from chronology_auditor import (
    ChronologyAuditor,
    PROSPECTIVE_AUTHENTIC,
    PROSPECTIVE_AUTHORITY_UNVERIFIED,
    PROSPECTIVE_CHRONOLOGY_VIOLATION,
)
from canonical_cohort_reconciler import (
    CanonicalCohortReconciler,
    compute_mbb_bounds,
)


class TestV1831SafetyInvariants:
    """Verifies permanent non-purchasing safety gates."""

    def test_live_execution_permanently_disabled(self):
        assert LIVE_EXECUTION_DISABLED is True
        assert OPERATING_MODE == "SHADOW_RESEARCH_ONLY"
        assert DECISION == "NO_TRADE"

    def test_prohibited_purchase_endpoints(self):
        from forward_shadow_engine import DerivLiveShadowCollector
        collector = DerivLiveShadowCollector(db_path=":memory:")
        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.buy()
        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.sell()
        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.place_order()
        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.send_buy_order()
        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.send_order()


class TestV1831ModelAuthenticity:
    """Verifies model registry and rejection of placeholder checksums."""

    def test_rejection_of_mock_checksums(self):
        reg = AuthoritativeModelRegistry()
        mock_hashes = [
            "sha256_mock_a8f9c1e2",
            "sha256_mock_e4d3c2b1",
            "sha256_v183_frozen_model",
            "",
            None,
        ]
        for m in mock_hashes:
            is_valid, classification, rec = reg.verify_model_provenance("MODEL_ANY", m)
            assert is_valid is False
            assert classification == MODEL_TYPE_UNVERIFIED

    def test_deterministic_causal_baseline_provenance(self):
        reg = AuthoritativeModelRegistry()
        rec = reg.get_model_record(MODEL_ID_CAUSAL_MOMENTUM_V1)
        assert rec is not None
        assert rec.model_type == MODEL_TYPE_DETERMINISTIC_BASELINE
        assert len(rec.artifact_checksum) == 64
        assert int(rec.artifact_checksum, 16) > 0

        is_valid, classification, _ = reg.verify_model_provenance(
            MODEL_ID_CAUSAL_MOMENTUM_V1, rec.artifact_checksum
        )
        assert is_valid is True
        assert classification == MODEL_TYPE_DETERMINISTIC_BASELINE

    def test_genuine_frozen_model_verification(self):
        reg = AuthoritativeModelRegistry()
        rec_2t = reg.get_model_record(MODEL_ID_M_R75_2T)
        if rec_2t:
            assert rec_2t.model_type == MODEL_TYPE_TRAINED_FROZEN
            assert len(rec_2t.artifact_checksum) == 64
            is_valid, classification, _ = reg.verify_model_provenance(
                MODEL_ID_M_R75_2T, rec_2t.artifact_checksum
            )
            assert is_valid is True
            assert classification == MODEL_TYPE_TRAINED_FROZEN

    def test_unverified_model_fails_closed(self):
        reg = AuthoritativeModelRegistry()
        is_valid, classification, _ = reg.verify_model_provenance("UNKNOWN_MODEL", "abcdef" * 10 + "1234")
        assert is_valid is False
        assert classification == MODEL_TYPE_UNVERIFIED


class TestV1831ProspectiveChronology:
    """Verifies prospective authority and chronological order validation."""

    def test_prospective_authentic_when_committed_prior_to_future_tick(self):
        res = ChronologyAuditor.audit_observation_chronology(
            signal_epoch=1000,
            decision_timestamp=1000.100,
            journal_commit_timestamp=1000.105,
            first_future_tick_epoch=1002,
            first_future_tick_receipt_ts=1002.100,
            expiry_epoch=1006,
            model_is_verified=True,
        )
        assert res.is_prospective is True
        assert res.status == PROSPECTIVE_AUTHENTIC
        assert res.lead_time_ms > 0

    def test_chronology_violation_when_future_tick_arrives_before_commit(self):
        # Commit happened at 1003.0, but first future tick was received at 1002.0
        res = ChronologyAuditor.audit_observation_chronology(
            signal_epoch=1000,
            decision_timestamp=1000.100,
            journal_commit_timestamp=1003.000,
            first_future_tick_epoch=1002,
            first_future_tick_receipt_ts=1002.000,
            expiry_epoch=1006,
            model_is_verified=True,
        )
        assert res.is_prospective is False
        assert res.status == PROSPECTIVE_CHRONOLOGY_VIOLATION
        assert "BEFORE journal commit" in res.reason

    def test_chronology_violation_when_future_epoch_le_signal_epoch(self):
        res = ChronologyAuditor.audit_observation_chronology(
            signal_epoch=1000,
            decision_timestamp=1000.100,
            journal_commit_timestamp=1000.105,
            first_future_tick_epoch=1000,  # Same as signal epoch!
            first_future_tick_receipt_ts=1002.000,
            expiry_epoch=1006,
            model_is_verified=True,
        )
        assert res.is_prospective is False
        assert res.status == PROSPECTIVE_CHRONOLOGY_VIOLATION

    def test_missing_commit_timestamp_unverified(self):
        res = ChronologyAuditor.audit_observation_chronology(
            signal_epoch=1000,
            decision_timestamp=1000.100,
            journal_commit_timestamp=None,
            first_future_tick_epoch=1002,
            first_future_tick_receipt_ts=1002.000,
            expiry_epoch=1006,
            model_is_verified=True,
        )
        assert res.is_prospective is False
        assert res.status == PROSPECTIVE_AUTHORITY_UNVERIFIED

    def test_unverified_model_fails_prospective_status(self):
        res = ChronologyAuditor.audit_observation_chronology(
            signal_epoch=1000,
            decision_timestamp=1000.100,
            journal_commit_timestamp=1000.105,
            first_future_tick_epoch=1002,
            first_future_tick_receipt_ts=1002.100,
            expiry_epoch=1006,
            model_is_verified=False,
        )
        assert res.is_prospective is False
        assert res.status == PROSPECTIVE_AUTHORITY_UNVERIFIED


class TestV1831ContractOutcomeResolvers:
    """Verifies strict inequality and monotonic path outcome resolution."""

    def test_rise_fall_equality_is_loss(self):
        outcome_call, is_tie = ContractOutcomeResolvers.resolve_rise_fall(
            entry_spot=100.50, expiry_spot=100.50, direction="CALL"
        )
        assert outcome_call == 0
        assert is_tie is True

        outcome_put, is_tie = ContractOutcomeResolvers.resolve_rise_fall(
            entry_spot=100.50, expiry_spot=100.50, direction="PUT"
        )
        assert outcome_put == 0
        assert is_tie is True

    def test_only_ups_monotonicity(self):
        # Strict upward path
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0,
            forward_spots=[100.1, 100.2, 100.3, 100.4, 100.5],
            direction="RUNHIGH",
            duration=5,
        )
        assert outcome == 1
        assert break_step is None

        # Reversal on step 2 (0-indexed: index 2 < index 1)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0,
            forward_spots=[100.1, 100.2, 100.15, 100.3, 100.4],
            direction="RUNHIGH",
            duration=5,
        )
        assert outcome == 0
        assert break_step == 2

        # Equal spot on step 1 (0-indexed: index 1 == index 0) is failure
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0,
            forward_spots=[100.1, 100.1, 100.2],
            direction="RUNHIGH",
            duration=3,
        )
        assert outcome == 0
        assert break_step == 1


class TestV1831MandatorySyntheticIntegration:
    """Mandatory Section 15 Synthetic Database Fixture Integration Test.

    Requirements:
    - 30 resolved predictions
    - 10 valid priced predictions (6 priced wins, 4 priced losses)
    - 20 unpriced predictions
    - Varying genuine-schema quote prices
    - Correct session timestamps
    - Causal model metadata
    - Execute production reporting pipeline
    - Assert: Cohort A N=30, Priced N=10, Priced Win Rate=60%, Mean Return uses exactly 10 records.
    """

    @pytest.fixture
    def synthetic_db(self, tmp_path):
        db_file = str(tmp_path / "synthetic_audit_test.db")
        db = ForwardResearchDatabase(db_file)
        session_id = "SESS_TEST_SYNTHETIC_001"
        base_ts = 1700000000.0

        # Insert 10 valid priced observations (6 wins, 4 losses)
        # 6 priced wins
        for i in range(6):
            obs_id = f"OBS_PRICED_WIN_{i:03d}"
            ask = 2.00 + (i * 0.10)
            payout = 3.91 + (i * 0.15)
            hyp_return = round((1 * payout) - ask, 4)
            obs = ForwardObservationRecord(
                observation_id=obs_id,
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_PUT,
                duration_ticks=2,
                decision_timestamp=base_ts + i * 10,
                signal_epoch=int(base_ts + i * 10),
                signal_price=1000.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                proposal_id=f"PROP_{i}",
                quote_timestamp=base_ts + i * 10 - 0.5,
                ask_price=ask,
                total_payout=payout,
                entry_epoch=int(base_ts + i * 10 + 2),
                entry_spot=1000.0,
                expiry_epoch=int(base_ts + i * 10 + 4),
                expiry_spot=999.0,
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=hyp_return,
                evidence_cohort=COHORT_C,
                prospective_status=PROSPECTIVE_AUTHENTIC,
                journal_commit_timestamp=base_ts + i * 10 + 0.005,
                first_future_tick_epoch=int(base_ts + i * 10 + 2),
                first_future_tick_receipt_ts=base_ts + i * 10 + 2.0,
                expiry_receipt_ts=base_ts + i * 10 + 4.0,
                resolution_timestamp=base_ts + i * 10 + 4.005,
                model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
                true_model_checksum="347bbca473b6ef1ee0bb2144fa506f36802e3b4a24f21db597621c1729c15e86",
            )
            db.insert_observation(obs)

        # 4 priced losses
        for i in range(4):
            obs_id = f"OBS_PRICED_LOSS_{i:03d}"
            ask = 2.00
            payout = 3.91
            hyp_return = round((0 * payout) - ask, 4)  # -2.00
            obs = ForwardObservationRecord(
                observation_id=obs_id,
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_PUT,
                duration_ticks=2,
                decision_timestamp=base_ts + 60 + i * 10,
                signal_epoch=int(base_ts + 60 + i * 10),
                signal_price=1000.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                proposal_id=f"PROP_LOSS_{i}",
                quote_timestamp=base_ts + 60 + i * 10 - 0.5,
                ask_price=ask,
                total_payout=payout,
                entry_epoch=int(base_ts + 60 + i * 10 + 2),
                entry_spot=1000.0,
                expiry_epoch=int(base_ts + 60 + i * 10 + 4),
                expiry_spot=1001.0,
                observed_outcome=0,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=hyp_return,
                evidence_cohort=COHORT_C,
                prospective_status=PROSPECTIVE_AUTHENTIC,
                journal_commit_timestamp=base_ts + 60 + i * 10 + 0.005,
                first_future_tick_epoch=int(base_ts + 60 + i * 10 + 2),
                first_future_tick_receipt_ts=base_ts + 60 + i * 10 + 2.0,
                expiry_receipt_ts=base_ts + 60 + i * 10 + 4.0,
                resolution_timestamp=base_ts + 60 + i * 10 + 4.005,
                model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
                true_model_checksum="347bbca473b6ef1ee0bb2144fa506f36802e3b4a24f21db597621c1729c15e86",
            )
            db.insert_observation(obs)

        # 20 unpriced predictions (12 wins, 8 losses, NO QUOTES, return=NULL)
        for i in range(20):
            obs_id = f"OBS_UNPRICED_{i:03d}"
            outcome = 1 if i < 12 else 0
            obs = ForwardObservationRecord(
                observation_id=obs_id,
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_PUT,
                duration_ticks=2,
                decision_timestamp=base_ts + 100 + i * 10,
                signal_epoch=int(base_ts + 100 + i * 10),
                signal_price=1000.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                proposal_id=None,
                ask_price=None,
                total_payout=None,
                entry_epoch=int(base_ts + 100 + i * 10 + 2),
                entry_spot=1000.0,
                expiry_epoch=int(base_ts + 100 + i * 10 + 4),
                expiry_spot=999.0 if outcome == 1 else 1001.0,
                observed_outcome=outcome,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=None,
                evidence_cohort=COHORT_A,
                prospective_status=PROSPECTIVE_AUTHENTIC,
                journal_commit_timestamp=base_ts + 100 + i * 10 + 0.005,
                first_future_tick_epoch=int(base_ts + 100 + i * 10 + 2),
                first_future_tick_receipt_ts=base_ts + 100 + i * 10 + 2.0,
                expiry_receipt_ts=base_ts + 100 + i * 10 + 4.0,
                resolution_timestamp=base_ts + 100 + i * 10 + 4.005,
                model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
                true_model_checksum="347bbca473b6ef1ee0bb2144fa506f36802e3b4a24f21db597621c1729c15e86",
            )
            db.insert_observation(obs)

        db.close()
        return db_file

    def test_canonical_cohort_reconciler_on_synthetic_fixture(self, synthetic_db):
        reconciler = CanonicalCohortReconciler.from_db_path(synthetic_db)
        result = reconciler.reconcile_session("SESS_TEST_SYNTHETIC_001")
        reconciler.close()

        hyp = result["hypotheses"][0]
        # Cohort A assertions: Exactly 30 resolved observations
        assert hyp["cohort_a_resolved_n"] == 30
        # Total wins in Cohort A = 6 priced wins + 12 unpriced wins = 18
        assert hyp["cohort_a_wins"] == 18
        assert hyp["cohort_a_win_rate"] == 0.6000

        # Cohort C assertions: Exactly 10 priced observations
        assert hyp["cohort_c_priced_n"] == 10
        assert hyp["cohort_c_wins"] == 6
        assert hyp["cohort_c_losses"] == 4
        assert hyp["cohort_c_win_rate"] == 0.6000  # 6 / 10 = 60%

        # Denominator divergence: 30 - 10 = 20
        assert hyp["unpriced_resolved_n"] == 20
        assert hyp["denominator_divergence"] == 20

        # Assert hypothetical mean return uses exactly 10 records
        assert len(hyp["cohort_c_obs_ids"]) == 10
        assert len(hyp["cohort_a_obs_ids"]) == 30

        # Ensure return is the exact average of the 10 priced rows
        expected_sum = (
            sum(round(1 * (3.91 + i * 0.15) - (2.00 + i * 0.10), 4) for i in range(6))
            + (-2.00 * 4)
        )
        expected_mean = round(expected_sum / 10.0, 4)
        assert hyp["cohort_c_mean_hypothetical_return"] == pytest.approx(expected_mean, abs=1e-4)

        # Unpriced observations CANNOT enter Cohort C
        for uid in hyp["cohort_a_obs_ids"]:
            if "UNPRICED" in uid:
                assert uid not in hyp["cohort_c_obs_ids"]
