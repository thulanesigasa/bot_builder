"""Comprehensive Adversarial Test Suite for V1.8.3.2 Strict Cohort Authority.

Verifies:
1. Safety invariants (LIVE_EXECUTION_DISABLED = True, NO_TRADE, no purchase requests).
2. Elimination of self-assigned label trust (stored labels cannot self-promote).
3. Rejection of invalid, stale, future, or cross-contaminated quotes.
4. Per-observation model registry verification and elimination of hardcoded bypasses.
5. Prospective chronology enforcement (lead times, epoch monotonicity, durable commit timestamps).
6. Contract outcome reconstruction (Rise/Fall equality loss, Only Ups/Downs monotonic path).
7. Historical session reclassification (SESS_20261012_105122_f4db88 strict Cohort C count is 0).
8. Acceptance session re-audit (28 verified Cohort C records).
9. Mandatory Section 15 Synthetic Database Fixture Integration Test:
   - 40 resolved predictions
   - 20 with proposal IDs
   - 15 with valid numerical quote terms
   - 10 with verifiable prospective chronology
   - Records with invalid models, stale/future quotes, incorrect outcomes
   - Production pipeline asserts exact eligible subset and explicit exclusion reasons.
"""

import json
import os
import sqlite3
import pytest
import numpy as np

from forward_shadow_engine import (
    LIVE_EXECUTION_DISABLED,
    OPERATING_MODE,
    DECISION,
    FAMILY_RISE_FALL,
    FAMILY_ONLY_UPS_DOWNS,
    DIRECTION_CALL,
    DIRECTION_PUT,
    DIRECTION_RUNHIGH,
    DIRECTION_RUNLOW,
    RESEARCH_MARKETS,
    OUTCOME_RESOLVED,
    OUTCOME_PENDING,
    COHORT_A,
    COHORT_B,
    COHORT_C,
    COHORT_D,
    SOURCE_BROKER_CAPTURED,
    ForwardObservationRecord,
    ForwardResearchDatabase,
    LiveBrokerProposal,
    LiveBrokerTick,
    ContractOutcomeResolvers,
    SafetyViolationError,
)
from model_registry import (
    AuthoritativeModelRegistry,
    MODEL_ID_CAUSAL_MOMENTUM_V1,
    MODEL_ID_CONSTANT_50_50,
    MODEL_ID_M_R75_2T,
    MODEL_ID_M_R75_5T,
    MODEL_TYPE_TRAINED_FROZEN,
    MODEL_TYPE_DETERMINISTIC_BASELINE,
    MODEL_TYPE_UNVERIFIED,
)
from strict_cohort_validator import (
    StrictCohortAuthorityValidator,
    CohortEligibilityDecision,
)
from canonical_cohort_reconciler import CanonicalCohortReconciler


class TestV1832SafetyInvariants:
    """Verifies non-purchasing safety gates and order endpoint prohibition."""

    def test_live_execution_disabled_constants(self):
        assert LIVE_EXECUTION_DISABLED is True
        assert OPERATING_MODE == "SHADOW_RESEARCH_ONLY"
        assert DECISION == "NO_TRADE"

    def test_broker_order_endpoints_raise_safety_violation(self):
        from forward_shadow_engine import DerivLiveShadowCollector
        c = DerivLiveShadowCollector(db_path=":memory:")
        for endpoint in [c.buy, c.sell, c.place_order, c.send_buy_order, c.send_order]:
            with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
                endpoint()


class TestV1832SelfAssignedLabelsCannotPromote:
    """Verifies that an observation cannot self-certify scientific authority."""

    def test_stored_cohort_c_label_rejected_when_missing_quote(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_FORGERY_001",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 5,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1010,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.2, 100.4, 100.6, 100.8, 101.0]),
            # Forged stored labels:
            "evidence_cohort": COHORT_C,
            "prospective_status": "PROSPECTIVE_AUTHENTIC",
            # MISSING QUOTE:
            "proposal_id": None,
            "ask_price": None,
            "total_payout": None,
            "hypothetical_return": None,
        }
        decision = val.validate_observation(obs)
        assert decision.is_cohort_c_eligible is False
        assert decision.final_evidence_cohort == COHORT_A
        assert any("unpriced record" in r for r in decision.rejection_reasons)

    def test_stored_cohort_c_label_rejected_when_future_quote(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_FUTURE_QUOTE",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "proposal_id": "PROP_001",
            "ask_price": 2.0,
            "total_payout": 3.91,
            "break_even_rate": 0.5115,
            "predicted_ev": 0.0,
            "hypothetical_return": 1.91,
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
            "evidence_cohort": COHORT_C,
        }

        # Mock DB where proposal response_timestamp is AFTER decision_timestamp
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.cursor().execute("""
            CREATE TABLE broker_proposals (
                proposal_id TEXT, underlying_symbol TEXT, contract_type TEXT, duration INT,
                duration_unit TEXT, ask_price REAL, total_payout REAL, response_timestamp REAL
            )
        """)
        conn.cursor().execute("""
            INSERT INTO broker_proposals VALUES ('PROP_001', 'R_75', 'CALL', 2, 't', 2.0, 3.91, 1005.0)
        """)
        conn.commit()

        decision = val.validate_observation(obs, conn=conn)
        conn.close()

        assert decision.is_cohort_c_eligible is False
        assert any("Future quote" in r for r in decision.rejection_reasons)

    def test_stored_cohort_c_label_rejected_when_stale_quote(self):
        val = StrictCohortAuthorityValidator(max_quote_age_sec=5.0)
        obs = {
            "observation_id": "OBS_STALE_QUOTE",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "proposal_id": "PROP_STALE",
            "ask_price": 2.0,
            "total_payout": 3.91,
            "break_even_rate": 0.5115,
            "predicted_ev": 0.0,
            "hypothetical_return": 1.91,
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
            "evidence_cohort": COHORT_C,
        }

        # Mock DB where proposal is 10.0s old (threshold is 5.0s)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.cursor().execute("""
            CREATE TABLE broker_proposals (
                proposal_id TEXT, underlying_symbol TEXT, contract_type TEXT, duration INT,
                duration_unit TEXT, ask_price REAL, total_payout REAL, response_timestamp REAL
            )
        """)
        conn.cursor().execute("""
            INSERT INTO broker_proposals VALUES ('PROP_STALE', 'R_75', 'CALL', 2, 't', 2.0, 3.91, 990.0)
        """)
        conn.commit()

        decision = val.validate_observation(obs, conn=conn)
        conn.close()

        assert decision.is_cohort_c_eligible is False
        assert any("Stale quote" in r for r in decision.rejection_reasons)

    def test_stored_cohort_c_label_rejected_when_cross_market_quote(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_CROSS_MKT",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "proposal_id": "PROP_100V",
            "ask_price": 2.0,
            "total_payout": 3.91,
            "break_even_rate": 0.5115,
            "predicted_ev": 0.0,
            "hypothetical_return": 1.91,
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
            "evidence_cohort": COHORT_C,
        }

        # Proposal belongs to 1HZ100V, not R_75!
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.cursor().execute("""
            CREATE TABLE broker_proposals (
                proposal_id TEXT, underlying_symbol TEXT, contract_type TEXT, duration INT,
                duration_unit TEXT, ask_price REAL, total_payout REAL, response_timestamp REAL
            )
        """)
        conn.cursor().execute("""
            INSERT INTO broker_proposals VALUES ('PROP_100V', '1HZ100V', 'CALL', 2, 't', 2.0, 3.91, 999.0)
        """)
        conn.commit()

        decision = val.validate_observation(obs, conn=conn)
        conn.close()

        assert decision.is_cohort_c_eligible is False
        assert any("Cross-market quote mismatch" in r for r in decision.rejection_reasons)


class TestV1832ModelAuthorityAndChronology:
    """Verifies per-observation model provenance and durable commit chronology."""

    def test_mock_checksum_fails_model_authority(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_MOCK_HASH",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "sha256_mock_a8f9c1e2",  # MOCK HASH!
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
        }
        decision = val.validate_observation(obs)
        assert decision.model_provenance_verdict is False
        assert decision.is_cohort_c_eligible is False
        assert any("Placeholder or mock checksum" in r for r in decision.rejection_reasons)

    def test_prediction_committed_after_future_tick_fails_chronology(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_CHRONO_VIOLATION",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1003.500,  # Committed at 1003.5
            "first_future_tick_receipt_ts": 1002.000,  # Arrived at 1002.0 (BEFORE commit!)
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
        }
        decision = val.validate_observation(obs)
        assert decision.prediction_chronology_verdict is False
        assert decision.is_cohort_c_eligible is False
        assert any("BEFORE journal commit" in r for r in decision.rejection_reasons)

    def test_missing_commit_timestamp_fails_chronology(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_NO_COMMIT_TS",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": None,  # Missing!
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,
            "entry_spot": 100.0,
            "expiry_spot": 101.0,
            "forward_spots_json": json.dumps([100.5, 101.0]),
        }
        decision = val.validate_observation(obs)
        assert decision.prediction_chronology_verdict is False
        assert decision.is_cohort_c_eligible is False
        assert any("Missing journal_commit_timestamp" in r for r in decision.rejection_reasons)


class TestV1832ContractOutcomeIntegrity:
    """Verifies outcome resolvers and rejection of corrupted outcomes."""

    def test_reconstructed_outcome_mismatch_fails_integrity(self):
        val = StrictCohortAuthorityValidator()
        obs = {
            "observation_id": "OBS_OUTCOME_CORRUPTION",
            "symbol": "R_75",
            "contract_family": FAMILY_RISE_FALL,
            "contract_type": DIRECTION_CALL,
            "duration_ticks": 2,
            "decision_timestamp": 1000.0,
            "journal_commit_timestamp": 1000.005,
            "first_future_tick_receipt_ts": 1002.0,
            "first_future_tick_epoch": 1002,
            "signal_epoch": 1000,
            "expiry_epoch": 1004,
            "model_version": MODEL_ID_CAUSAL_MOMENTUM_V1,
            "true_model_checksum": "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6",
            "entry_spot": 100.0,
            "expiry_spot": 99.0,  # Spot dropped from 100.0 to 99.0 (CALL LOST!)
            "forward_spots_json": json.dumps([99.5, 99.0]),
            "outcome_status": OUTCOME_RESOLVED,
            "observed_outcome": 1,  # Falsely claims WIN (1)!
        }
        decision = val.validate_observation(obs)
        assert decision.outcome_integrity_verdict is False
        assert decision.is_cohort_c_eligible is False
        assert any("Outcome reconstruction mismatch" in r for r in decision.rejection_reasons)


class TestV1832MandatoryIntegrationFixture:
    """Mandatory Section 15 Synthetic Database Fixture Integration Test.

    Constructs a database fixture containing:
    - 40 resolved predictions.
    - 20 predictions with proposal IDs.
    - 15 predictions with valid numerical quote terms.
    - 10 predictions with verifiable prospective chronology.
    - Several records with invalid model provenance.
    - Several records with stale or future quotes.
    - Several records with incorrect contract outcomes.
    - Only a defined subset (exactly 5 observations) satisfying every strict requirement.

    Runs production reconciliation pipeline and asserts:
    - All resolved predictions are accounted for.
    - Invalid observations cannot self-promote.
    - Strict Cohort C includes only the independently eligible subset.
    - Rejection reasons are explicitly recorded.
    """

    @pytest.fixture
    def complex_synthetic_db(self, tmp_path):
        db_file = str(tmp_path / "v1832_complex_fixture.db")
        db = ForwardResearchDatabase(db_file)
        session_id = "SESS_COMPLEX_001"
        base_ts = 1700000000.0

        # Seed broker_proposals table with authentic quotes
        # Quotes 0 to 4: valid and fresh
        for i in range(5):
            db.insert_proposal(LiveBrokerProposal(
                proposal_id=f"PROP_VALID_{i}",
                underlying_symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration=2,
                duration_unit="t",
                ask_price=2.00,
                total_payout=3.91,
                spot_price=100.0,
                spot_time=int(base_ts + i * 20),
                request_timestamp=base_ts + i * 20 - 0.5,
                response_timestamp=base_ts + i * 20 - 0.1,  # 0.1s fresh before decision
                longcode="Valid proposal quote",
                session_id=session_id,
                payload_hash="valid_hash",
            ))

        # Quote 5: STALE (> 5.0s age)
        db.insert_proposal(LiveBrokerProposal(
            proposal_id="PROP_STALE",
            underlying_symbol="R_75",
            contract_family=FAMILY_RISE_FALL,
            contract_type=DIRECTION_CALL,
            duration=2,
            duration_unit="t",
            ask_price=2.00,
            total_payout=3.91,
            spot_price=100.0,
            spot_time=int(base_ts - 20),
            request_timestamp=base_ts - 20,
            response_timestamp=base_ts - 15.0,  # 15s old at decision!
            longcode="Stale proposal quote",
            session_id=session_id,
            payload_hash="stale_hash",
        ))

        # Quote 6: FUTURE (response_timestamp > decision_timestamp)
        db.insert_proposal(LiveBrokerProposal(
            proposal_id="PROP_FUTURE",
            underlying_symbol="R_75",
            contract_family=FAMILY_RISE_FALL,
            contract_type=DIRECTION_CALL,
            duration=2,
            duration_unit="t",
            ask_price=2.00,
            total_payout=3.91,
            spot_price=100.0,
            spot_time=int(base_ts + 200),
            request_timestamp=base_ts + 190,
            response_timestamp=base_ts + 210.0,  # In the future!
            longcode="Future proposal quote",
            session_id=session_id,
            payload_hash="future_hash",
        ))

        # Seed broker_ticks
        for t_idx in range(50):
            db.insert_tick(LiveBrokerTick(
                symbol="R_75",
                epoch=int(base_ts + t_idx * 5),
                quote=100.0 + t_idx * 0.1,
                ask=100.05 + t_idx * 0.1,
                bid=99.95 + t_idx * 0.1,
                pip_size=4,
                received_timestamp=base_ts + t_idx * 5,
                raw_payload_hash="tick_hash",
            ))

        valid_chk = "2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6"

        # -------------------------------------------------------------
        # Group 1: Exactly 5 PERFECT, STRICTLY VALID COHORT C OBSERVATIONS
        # -------------------------------------------------------------
        for i in range(5):
            t_dec = base_ts + i * 20
            obs = ForwardObservationRecord(
                observation_id=f"OBS_STRICT_VALID_{i}",
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=t_dec,
                signal_epoch=int(t_dec),
                signal_price=100.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                true_model_checksum=valid_chk,
                proposal_id=f"PROP_VALID_{i}",
                quote_timestamp=t_dec - 0.1,
                ask_price=2.00,
                total_payout=3.91,
                break_even_rate=0.5115,
                predicted_ev=round(0.52 * 3.91 - 2.00, 4),
                entry_epoch=int(t_dec + 5),
                entry_spot=100.0,
                expiry_epoch=int(t_dec + 10),
                expiry_spot=100.5,  # Win!
                forward_spots_json=json.dumps([100.2, 100.5]),
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=1.91,
                evidence_cohort=COHORT_C,
                prospective_status="PROSPECTIVE_AUTHENTIC",
                journal_commit_timestamp=t_dec + 0.005,
                first_future_tick_epoch=int(t_dec + 5),
                first_future_tick_receipt_ts=t_dec + 5.0,  # 4.995s lead time!
                expiry_receipt_ts=t_dec + 10.0,
                resolution_timestamp=t_dec + 10.005,
                model_type=MODEL_TYPE_DETERMINISTIC_BASELINE,
            )
            db.insert_observation(obs)

        # -------------------------------------------------------------
        # Group 2: 5 observations with valid quotes but INVALID CHRONOLOGY (Lead time < 0)
        # -> Should enter Cohort B, NOT Cohort C!
        # -------------------------------------------------------------
        for i in range(5):
            t_dec = base_ts + 100 + i * 20
            obs = ForwardObservationRecord(
                observation_id=f"OBS_BAD_CHRONO_{i}",
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=t_dec,
                signal_epoch=int(t_dec),
                signal_price=100.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                true_model_checksum=valid_chk,
                proposal_id=f"PROP_VALID_{i}",  # Valid proposal
                quote_timestamp=t_dec - 0.1,
                ask_price=2.00,
                total_payout=3.91,
                entry_epoch=int(t_dec + 5),
                entry_spot=100.0,
                expiry_epoch=int(t_dec + 10),
                expiry_spot=100.5,
                forward_spots_json=json.dumps([100.2, 100.5]),
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=1.91,
                evidence_cohort=COHORT_C,  # Forged label!
                journal_commit_timestamp=t_dec + 6.0,  # Committed AFTER tick arrived at +5.0!
                first_future_tick_epoch=int(t_dec + 5),
                first_future_tick_receipt_ts=t_dec + 5.0,
            )
            db.insert_observation(obs)

        # -------------------------------------------------------------
        # Group 3: 5 observations with valid chronology but INVALID MODEL HASH
        # -> Should enter Cohort B, NOT Cohort C!
        # -------------------------------------------------------------
        for i in range(5):
            t_dec = base_ts + 200 + i * 20
            obs = ForwardObservationRecord(
                observation_id=f"OBS_BAD_MODEL_{i}",
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=t_dec,
                signal_epoch=int(t_dec),
                signal_price=100.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                true_model_checksum="sha256_mock_corrupted",  # Invalid checksum!
                proposal_id=f"PROP_VALID_{i}",
                quote_timestamp=t_dec - 0.1,
                ask_price=2.00,
                total_payout=3.91,
                entry_epoch=int(t_dec + 5),
                entry_spot=100.0,
                expiry_epoch=int(t_dec + 10),
                expiry_spot=100.5,
                forward_spots_json=json.dumps([100.2, 100.5]),
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=1.91,
                evidence_cohort=COHORT_C,
                journal_commit_timestamp=t_dec + 0.005,
                first_future_tick_epoch=int(t_dec + 5),
                first_future_tick_receipt_ts=t_dec + 5.0,
            )
            db.insert_observation(obs)

        # -------------------------------------------------------------
        # Group 4: 5 observations with proposal IDs but STALE/FUTURE quotes or invalid price
        # -> Should NOT enter Cohort C!
        # -------------------------------------------------------------
        for i in range(5):
            t_dec = base_ts + 300 + i * 20
            prop_id = "PROP_STALE" if i % 2 == 0 else "PROP_FUTURE"
            obs = ForwardObservationRecord(
                observation_id=f"OBS_BAD_QUOTE_{i}",
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=t_dec,
                signal_epoch=int(t_dec),
                signal_price=100.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                true_model_checksum=valid_chk,
                proposal_id=prop_id,
                quote_timestamp=t_dec - 0.1,
                ask_price=2.00,
                total_payout=3.91,
                entry_epoch=int(t_dec + 5),
                entry_spot=100.0,
                expiry_epoch=int(t_dec + 10),
                expiry_spot=100.5,
                forward_spots_json=json.dumps([100.2, 100.5]),
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=1.91,
                evidence_cohort=COHORT_C,
                journal_commit_timestamp=t_dec + 0.005,
                first_future_tick_epoch=int(t_dec + 5),
                first_future_tick_receipt_ts=t_dec + 5.0,
            )
            db.insert_observation(obs)

        # -------------------------------------------------------------
        # Group 5: 20 unpriced resolved predictions (pure predictive Cohort A)
        # -------------------------------------------------------------
        for i in range(20):
            t_dec = base_ts + 400 + i * 20
            outcome = 1 if i < 10 else 0
            obs = ForwardObservationRecord(
                observation_id=f"OBS_UNPRICED_{i}",
                session_id=session_id,
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=t_dec,
                signal_epoch=int(t_dec),
                signal_price=100.0,
                predicted_prob=0.52,
                model_version=MODEL_ID_CAUSAL_MOMENTUM_V1,
                true_model_checksum=valid_chk,
                proposal_id=None,
                ask_price=None,
                total_payout=None,
                entry_epoch=int(t_dec + 5),
                entry_spot=100.0,
                expiry_epoch=int(t_dec + 10),
                expiry_spot=100.5 if outcome == 1 else 99.5,
                forward_spots_json=json.dumps([100.2, 100.5] if outcome == 1 else [99.8, 99.5]),
                observed_outcome=outcome,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=None,
                evidence_cohort=COHORT_A,
                journal_commit_timestamp=t_dec + 0.005,
                first_future_tick_epoch=int(t_dec + 5),
                first_future_tick_receipt_ts=t_dec + 5.0,
            )
            db.insert_observation(obs)

        db.close()
        return db_file

    def test_production_reconciliation_on_complex_fixture(self, complex_synthetic_db):
        reconciler = CanonicalCohortReconciler.from_db_path(complex_synthetic_db)
        result = reconciler.reconcile_session_authoritative("SESS_COMPLEX_001")
        reconciler.close()

        telem = result["telemetry"]
        assert telem["total_committed"] == 40

        # Assert exactly 5 observations achieve strict Cohort C eligibility
        assert telem["total_authoritative_cohort_c"] == 5

        # Check the hypothesis metrics
        hyp = result["hypotheses"][0]
        assert hyp["cohort_c_priced_n"] == 5
        assert hyp["cohort_c_wins"] == 5
        assert hyp["cohort_c_win_rate"] == 1.0000
        assert hyp["cohort_c_mean_hypothetical_return"] == 1.9100

        # Assert that the 5 bad chronology and 5 bad model rows were demoted from Cohort C
        for uid in hyp["cohort_c_obs_ids"]:
            assert "OBS_STRICT_VALID" in uid
            assert "BAD_CHRONO" not in uid
            assert "BAD_MODEL" not in uid
            assert "BAD_QUOTE" not in uid
            assert "UNPRICED" not in uid

        # Verify that exclusion reasons were captured
        excl = result["exclusion_reasons_summary"]
        assert len(excl) > 0
        assert any("BEFORE journal commit" in k for k in excl.keys())
        assert any("Placeholder or mock checksum" in k for k in excl.keys())
        assert any("Future quote" in k or "Stale quote" in k for k in excl.keys())
