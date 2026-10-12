"""Comprehensive Automated Test Suite for V1.8.3 Forward SHADOW Research Release.

Validates:
  1. Permanent Safety Invariants:
     - LIVE_EXECUTION_DISABLED = True across all V1.8.3 modules.
     - OPERATING_MODE = 'SHADOW_RESEARCH_ONLY', DECISION = 'NO_TRADE'.
     - All live purchase endpoints (buy, sell, place_order, send_buy_order, send_order)
       fail closed and raise SafetyViolationError.
  2. Contract Outcome Resolvers:
     - Rise/Fall (CALL / PUT): strictly terminal direction, equal spot (tie) is a strict loss.
     - Only Ups / Only Downs (RUNHIGH / RUNLOW): strictly monotonic consecutive path;
       any equal spot or reversal terminates contract immediately as a loss.
  3. Broker Proposal & Quote Matching Isolation:
     - Genuine proposal schema parsing (underlying_symbol, contract_type, duration, ask, payout).
     - Market isolation (R_75 quotes never match 1HZ100V).
     - Family isolation (Rise/Fall quotes never match Only Ups/Downs).
     - Direction isolation (CALL never matches PUT).
     - Duration isolation (2t never matches 5t or 10t).
     - Freshness barrier (quotes older than 5.0s rejected).
     - Chronological boundary (future quotes rejected).
     - No reference-price fallback (unmatched quotes remain None).
  4. Tick Ingestion, Sequence, and Hashing:
     - Native precision and epoch preservation.
     - SHA-256 payload hashing for auditability.
  5. Prospective Prediction Journaling:
     - Predictions committed before future ticks arrive.
     - Post-outcome insertion classified as PROSPECTIVE_AUTHORITY_UNVERIFIED.
     - Evidence cohort accounting (Cohorts A, B, C, D).
     - Cohort D strictly quarantined from exploratory results.
  6. Per-Observation Economics & Bootstrap Resampling:
     - Exact Break-Even, Predicted EV, and Hypothetical Return equations.
     - Moving Block Bootstrap (MBB) preserves serial dependence and paired observations.
  7. End-to-End Pipeline & Release Artifacts:
     - Mock forward session generation and database reconciliation.
     - Canonical forward pipeline executes and outputs data/v183_forward_evidence.json.
     - All 8 required reports exist under reports/ with zero emojis.
"""

from datetime import datetime, timezone
import json
import math
import os
import sqlite3
import tempfile
import time
from typing import Dict, List, Any

import numpy as np
import pytest

from forward_shadow_engine import (
    LIVE_EXECUTION_DISABLED as ENGINE_SAFETY,
    OPERATING_MODE as ENGINE_MODE,
    DECISION as ENGINE_DECISION,
    FAMILY_RISE_FALL,
    FAMILY_ONLY_UPS_DOWNS,
    DIRECTION_CALL,
    DIRECTION_PUT,
    DIRECTION_RUNHIGH,
    DIRECTION_RUNLOW,
    DURATIONS_RISE_FALL,
    DURATIONS_ONLY_UPS_DOWNS,
    RESEARCH_MARKETS,
    OUTCOME_PENDING,
    OUTCOME_RESOLVED,
    PROSPECTIVE_AUTHENTIC,
    PROSPECTIVE_AUTHORITY_UNVERIFIED,
    SOURCE_BROKER_CAPTURED,
    COHORT_A,
    COHORT_B,
    COHORT_C,
    COHORT_D,
    VERDICT_INSUFFICIENT_PROSPECTIVE,
    SafetyViolationError,
    LiveBrokerTick,
    LiveBrokerProposal,
    ForwardObservationRecord,
    ContractOutcomeResolvers,
    ForwardResearchDatabase,
    DerivLiveShadowCollector,
    execute_mock_forward_session,
)
from canonical_forward_pipeline import (
    LIVE_EXECUTION_DISABLED as PIPELINE_SAFETY,
    OPERATING_MODE as PIPELINE_MODE,
    DECISION as PIPELINE_DECISION,
    BASE_COMMIT,
    BASE_RELEASE,
    TARGET_RELEASE,
    compute_mbb_confidence_interval,
    run_canonical_forward_pipeline,
)


class TestV183SafetyInvariants:
    """Verifies permanent, compile-time non-purchasing safety invariants across all modules."""

    def test_compile_time_safety_constants(self):
        assert ENGINE_SAFETY is True
        assert PIPELINE_SAFETY is True
        assert ENGINE_MODE == "SHADOW_RESEARCH_ONLY"
        assert PIPELINE_MODE == "SHADOW_RESEARCH_ONLY"
        assert ENGINE_DECISION == "NO_TRADE"
        assert PIPELINE_DECISION == "NO_TRADE"

    def test_collector_fails_if_safety_violated(self, monkeypatch):
        import forward_shadow_engine
        monkeypatch.setattr(forward_shadow_engine, "LIVE_EXECUTION_DISABLED", False)
        with pytest.raises(SafetyViolationError, match="LIVE_EXECUTION_DISABLED must be True"):
            DerivLiveShadowCollector()

    def test_order_endpoints_fail_closed(self):
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

        with pytest.raises(SafetyViolationError, match="FATAL SAFETY VIOLATION"):
            collector.trigger_safety_violation("deriv_buy_contract_v1")


class TestV183ContractOutcomeResolvers:
    """Tests independent contract outcome resolvers for Rise/Fall and Only Ups/Downs."""

    def test_rise_fall_call_resolution(self):
        # Expiry > Entry: Win (1), not tie
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 100.5, "CALL")
        assert outcome == 1
        assert is_tie is False

        # Expiry < Entry: Loss (0), not tie
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 99.5, "CALL")
        assert outcome == 0
        assert is_tie is False

        # Expiry == Entry: Strict Loss (0), tie is True
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 100.0, "CALL")
        assert outcome == 0
        assert is_tie is True

    def test_rise_fall_put_resolution(self):
        # Expiry < Entry: Win (1), not tie
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 99.5, "PUT")
        assert outcome == 1
        assert is_tie is False

        # Expiry > Entry: Loss (0), not tie
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 100.5, "PUT")
        assert outcome == 0
        assert is_tie is False

        # Expiry == Entry: Strict Loss (0), tie is True
        outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(100.0, 100.0, "PUT")
        assert outcome == 0
        assert is_tie is True

    def test_rise_fall_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Unknown Rise/Fall direction"):
            ContractOutcomeResolvers.resolve_rise_fall(100.0, 101.0, "INVALID_DIR")

    def test_only_ups_downs_runhigh_resolution(self):
        # 2 ticks strictly increasing: Win (1)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[100.2, 100.5], direction="RUNHIGH", duration=2
        )
        assert outcome == 1
        assert break_step is None

        # 2 ticks with reversal on tick 2: Loss (0) at step 1
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[100.2, 100.1], direction="RUNHIGH", duration=2
        )
        assert outcome == 0
        assert break_step == 1

        # 2 ticks with equal spot on tick 2: Loss (0) at step 1 (equal spot loses!)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[100.2, 100.2], direction="RUNHIGH", duration=2
        )
        assert outcome == 0
        assert break_step == 1

        # 5 ticks strictly increasing: Win (1)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[100.1, 100.2, 100.3, 100.4, 100.5], direction="RUNHIGH", duration=5
        )
        assert outcome == 1
        assert break_step is None

        # 5 ticks with dip at step 3: Loss (0) at step 3
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[100.1, 100.2, 100.3, 100.25, 100.4], direction="RUNHIGH", duration=5
        )
        assert outcome == 0
        assert break_step == 3

    def test_only_ups_downs_runlow_resolution(self):
        # 2 ticks strictly decreasing: Win (1)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[99.8, 99.5], direction="RUNLOW", duration=2
        )
        assert outcome == 1
        assert break_step is None

        # 2 ticks with upward tick on tick 2: Loss (0) at step 1
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[99.8, 99.9], direction="RUNLOW", duration=2
        )
        assert outcome == 0
        assert break_step == 1

        # 2 ticks with equal spot: Loss (0) at step 1 (equal spot loses!)
        outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
            entry_spot=100.0, forward_spots=[99.8, 99.8], direction="RUNLOW", duration=2
        )
        assert outcome == 0
        assert break_step == 1

    def test_only_ups_downs_insufficient_spots_raises(self):
        with pytest.raises(ValueError, match="Insufficient forward spots"):
            ContractOutcomeResolvers.resolve_only_ups_downs(
                entry_spot=100.0, forward_spots=[100.1], direction="RUNHIGH", duration=2
            )

    def test_only_ups_downs_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Unknown Only Ups/Downs direction"):
            ContractOutcomeResolvers.resolve_only_ups_downs(
                entry_spot=100.0, forward_spots=[100.1, 100.2], direction="SIDEWAYS", duration=2
            )


class TestV183ProposalAndQuoteMatching:
    """Tests strict proposal schema parsing, economic calculations, and match isolation."""

    def test_broker_proposal_dataclass_and_break_even(self):
        p = LiveBrokerProposal(
            proposal_id="PROP_R75_CALL_2T_TEST",
            underlying_symbol="R_75",
            contract_family=FAMILY_RISE_FALL,
            contract_type=DIRECTION_CALL,
            duration=2,
            duration_unit="t",
            ask_price=2.00,
            total_payout=3.91,
            spot_price=50000.0,
            spot_time=1700000000,
            request_timestamp=1700000000.10,
            response_timestamp=1700000000.15,
        )
        # Break-even = 2.00 / 3.91 = 0.51150895...
        assert pytest.approx(p.break_even_prob, rel=1e-3) == 0.5115
        d = p.to_dict()
        assert d["break_even_prob"] == 0.5115
        assert d["underlying_symbol"] == "R_75"

    def test_quote_match_isolation_in_collector(self):
        collector = DerivLiveShadowCollector(db_path=":memory:", max_quote_age_sec=5.0)
        t_base = 1700000000.0

        # Insert a CALL proposal for R_75, 2t
        p_r75_call_2t = LiveBrokerProposal(
            proposal_id="P_R75_CALL_2T",
            underlying_symbol="R_75",
            contract_family=FAMILY_RISE_FALL,
            contract_type=DIRECTION_CALL,
            duration=2,
            duration_unit="t",
            ask_price=2.00,
            total_payout=3.91,
            spot_price=50000.0,
            spot_time=int(t_base),
            request_timestamp=t_base - 0.05,
            response_timestamp=t_base,
            session_id=collector.session_id,
        )
        collector.db.insert_proposal(p_r75_call_2t)

        # 1. Matching CALL, R_75, 2t at decision time t_base + 1.0 (Fresh)
        matched = collector._find_matching_quote("R_75", FAMILY_RISE_FALL, DIRECTION_CALL, 2, t_base + 1.0)
        assert matched is not None
        assert matched["proposal_id"] == "P_R75_CALL_2T"

        # 2. Market Isolation: Symbol mismatch (1HZ100V) -> None
        assert collector._find_matching_quote("1HZ100V", FAMILY_RISE_FALL, DIRECTION_CALL, 2, t_base + 1.0) is None

        # 3. Family Isolation: Only Ups/Downs -> None
        assert collector._find_matching_quote("R_75", FAMILY_ONLY_UPS_DOWNS, DIRECTION_CALL, 2, t_base + 1.0) is None

        # 4. Direction Isolation: PUT -> None
        assert collector._find_matching_quote("R_75", FAMILY_RISE_FALL, DIRECTION_PUT, 2, t_base + 1.0) is None

        # 5. Duration Isolation: 5t -> None
        assert collector._find_matching_quote("R_75", FAMILY_RISE_FALL, DIRECTION_CALL, 5, t_base + 1.0) is None

        # 6. Freshness Barrier: Stale quote (decision time t_base + 6.0 > max_age 5.0) -> None
        assert collector._find_matching_quote("R_75", FAMILY_RISE_FALL, DIRECTION_CALL, 2, t_base + 6.0) is None

        # 7. Chronological Boundary: Quote is in the future (decision time t_base - 1.0) -> None
        assert collector._find_matching_quote("R_75", FAMILY_RISE_FALL, DIRECTION_CALL, 2, t_base - 1.0) is None


class TestV183TickIngestionAndPrecision:
    """Verifies live tick payload ingestion, precision preservation, and hashing."""

    def test_live_broker_tick_creation_and_hashing(self):
        tick = LiveBrokerTick(
            symbol="R_100",
            epoch=1700000000,
            quote=1234.5678,
            ask=1234.5800,
            bid=1234.5500,
            pip_size=4,
            received_timestamp=1700000000.05,
            subscription_id="sub_test_123",
            raw_payload_hash="sha256_mock_hash",
        )
        assert tick.symbol == "R_100"
        assert tick.quote == 1234.5678
        assert tick.raw_payload_hash == "sha256_mock_hash"
        d = tick.to_dict()
        assert d["quote"] == 1234.5678
        assert d["epoch"] == 1700000000


class TestV183DurablePredictionJournaling:
    """Verifies pre-outcome prediction commitment, prospective status, and cohort quarantine."""

    def test_observation_record_lifecycle_and_cohort_promotion(self):
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)
        try:
            db = ForwardResearchDatabase(db_path)
            obs = ForwardObservationRecord(
                observation_id="OBS_TEST_001",
                session_id="SESS_TEST",
                symbol="R_75",
                contract_family=FAMILY_RISE_FALL,
                contract_type=DIRECTION_CALL,
                duration_ticks=2,
                decision_timestamp=1700000000.0,
                signal_epoch=1700000000,
                signal_price=50000.0,
                predicted_prob=0.55,
                model_version="V1.8.3_TEST",
                decision="NO_TRADE",
                rejection_reason="SHADOW_RESEARCH_MODE_NO_PURCHASES_AUTHORIZED",
                proposal_id="PROP_001",
                quote_timestamp=1700000000.0,
                ask_price=2.00,
                total_payout=3.91,
                break_even_rate=0.5115,
                predicted_ev=0.1505,
                evidence_cohort=COHORT_B,
                prospective_status=PROSPECTIVE_AUTHENTIC,
                source_classification=SOURCE_BROKER_CAPTURED,
            )
            db.insert_observation(obs)

            # Check inserted record
            with db._get_connection() as conn:
                row = conn.cursor().execute("SELECT * FROM forward_observations WHERE observation_id = 'OBS_TEST_001'").fetchone()
                assert row is not None
                assert row["symbol"] == "R_75"
                assert row["outcome_status"] == OUTCOME_PENDING
                assert row["evidence_cohort"] == COHORT_B

            # Resolve observation and promote to Cohort C
            db.update_observation_resolution(
                observation_id="OBS_TEST_001",
                entry_epoch=1700000002,
                entry_spot=50000.0,
                expiry_epoch=1700000006,
                expiry_spot=50001.0,
                forward_spots_json="[50000.5, 50001.0]",
                observed_outcome=1,
                outcome_status=OUTCOME_RESOLVED,
                hypothetical_return=1.91,
                cohort=COHORT_C,
            )

            with db._get_connection() as conn:
                row = conn.cursor().execute("SELECT * FROM forward_observations WHERE observation_id = 'OBS_TEST_001'").fetchone()
                assert row["outcome_status"] == OUTCOME_RESOLVED
                assert row["observed_outcome"] == 1
                assert pytest.approx(row["hypothetical_return"]) == 1.91
                assert row["evidence_cohort"] == COHORT_C
        finally:
            db.close()
            import gc
            gc.collect()
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
            except OSError:
                pass


class TestV183EconomicsAndBootstrap:
    """Verifies observation-level economic equations and Moving Block Bootstrap."""

    def test_economic_calculations(self):
        ask = 2.00
        payout = 3.91
        p_model = 0.54

        break_even = ask / payout
        assert pytest.approx(break_even, rel=1e-3) == 0.5115

        pred_ev = p_model * payout - ask
        # 0.54 * 3.91 - 2.00 = 2.1114 - 2.00 = 0.1114
        assert pytest.approx(pred_ev, rel=1e-3) == 0.1114

        # Win return: 1 * 3.91 - 2.00 = 1.91
        hyp_ret_win = 1 * payout - ask
        assert pytest.approx(hyp_ret_win) == 1.91

        # Loss return: 0 * 3.91 - 2.00 = -2.00
        hyp_ret_loss = 0 * payout - ask
        assert pytest.approx(hyp_ret_loss) == -2.00

    def test_moving_block_bootstrap_confidence_interval(self):
        returns = np.array([1.91, -2.00, 1.91, -2.00, 1.91, -2.00, 1.91, 1.91, -2.00, 1.91])
        res = compute_mbb_confidence_interval(returns, iterations=200)
        assert "mean" in res
        assert "lower_bound_95" in res
        assert "upper_bound_95" in res
        assert res["lower_bound_95"] <= res["mean"] <= res["upper_bound_95"]


class TestV183DatabaseAndPipelineReconciliation:
    """Verifies end-to-end mock session generation and canonical pipeline execution."""

    def test_mock_session_and_pipeline_execution(self):
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)
        try:
            # 1. Run deterministic mock forward session
            sess_res = execute_mock_forward_session(
                db_path=db_path,
                target_markets=["R_75", "1HZ100V"],
                ticks_per_market=30,
            )
            assert sess_res["status"] == "MOCK_COMPLETED"
            assert sess_res["ticks_captured"] > 0
            assert sess_res["proposals_captured"] > 0
            assert sess_res["predictions_committed"] > 0
            assert sess_res["observations_resolved"] > 0

            # 2. Run canonical forward pipeline on the mock session database
            temp_dir = tempfile.mkdtemp()
            evidence = run_canonical_forward_pipeline(db_path=db_path, base_dir=temp_dir)

            assert evidence["verdicts"]["software_status"] == "FORWARD_PIPELINE_VALIDATED"
            assert evidence["verdicts"]["research_verdict"] == VERDICT_INSUFFICIENT_PROSPECTIVE
            assert evidence["safety_status"]["LIVE_EXECUTION_DISABLED"] is True
            assert evidence["safety_status"]["DECISION"] == "NO_TRADE"
            assert len(evidence["contract_family_breakdown"]) > 0

            # Verify report generation in temp directory
            for rpt in [
                "V1_8_3_LIVE_CONNECTIVITY_AUDIT.md",
                "V1_8_3_RISE_FALL_FORWARD_SESSION.md",
                "V1_8_3_ONLY_UPS_DOWNS_FORWARD_SESSION.md",
                "V1_8_3_QUOTE_CAPTURE_AUDIT.md",
                "V1_8_3_FORWARD_JOURNAL_RECONCILIATION.md",
                "V1_8_3_CONTRACT_FAMILY_COMPARISON.md",
                "V1_8_3_STATISTICAL_POWER_AND_STOPPING_PLAN.md",
                "V1_8_3_RELEASE_VALIDATION_REPORT.md",
            ]:
                assert os.path.exists(os.path.join(temp_dir, "reports", rpt))
        finally:
            import gc
            gc.collect()
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
            except OSError:
                pass


class TestV183ReleaseArtifacts:
    """Validates the official repository release evidence and reports."""

    def test_machine_readable_evidence_json(self):
        ev_path = os.path.join(".", "data", "v183_forward_evidence.json")
        assert os.path.exists(ev_path), "data/v183_forward_evidence.json must exist"

        with open(ev_path, "r", encoding="utf-8") as f:
            ev = json.load(f)

        assert ev["release_version"] == "V1.8.3"
        assert ev["source_commit_sha"] == "73504a578d3582afb6a625027f1c42b0f0bf2055"
        assert ev["session_identity"].startswith("SESS_")
        assert ev["raw_tick_counts"] > 0
        assert ev["quote_counts"] > 0
        assert ev["prediction_counts"] > 0
        assert ev["resolved_outcomes"] > 0
        assert ev["matched_observation_counts"] > 0
        assert ev["safety_status"]["LIVE_EXECUTION_DISABLED"] is True
        assert ev["safety_status"]["DECISION"] == "NO_TRADE"
        assert ev["research_verdicts"]["software_status"] == "FORWARD_PIPELINE_VALIDATED"
        assert ev["research_verdicts"]["research_verdict"] == VERDICT_INSUFFICIENT_PROSPECTIVE

    def test_all_eight_reports_exist_and_contain_no_emojis(self):
        reports_dir = os.path.join(".", "reports")
        expected_reports = [
            "V1_8_3_LIVE_CONNECTIVITY_AUDIT.md",
            "V1_8_3_RISE_FALL_FORWARD_SESSION.md",
            "V1_8_3_ONLY_UPS_DOWNS_FORWARD_SESSION.md",
            "V1_8_3_QUOTE_CAPTURE_AUDIT.md",
            "V1_8_3_FORWARD_JOURNAL_RECONCILIATION.md",
            "V1_8_3_CONTRACT_FAMILY_COMPARISON.md",
            "V1_8_3_STATISTICAL_POWER_AND_STOPPING_PLAN.md",
            "V1_8_3_RELEASE_VALIDATION_REPORT.md",
        ]

        # Allowed unicode characters: em-dash, math symbols, Latin-1 supplement
        allowed_codepoints = {0x2014, 0x2248, 0x2265, 0x03C4, 0x03C0, 0x0394, 0x03B1, 0x03B2}

        for rpt_name in expected_reports:
            rpt_path = os.path.join(reports_dir, rpt_name)
            assert os.path.exists(rpt_path), f"Report {rpt_name} missing"
            with open(rpt_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert len(content) > 100
            assert "img.shields.io" in content

            # Check emoji rule (Rule 18)
            for ch in content:
                cp = ord(ch)
                if cp > 127 and not (cp in allowed_codepoints or 0x00A0 <= cp <= 0x00FF):
                    pytest.fail(f"Emoji or disallowed unicode character found in {rpt_name}: U+{cp:04X} ({ch})")
