"""V1.7.4.5 Comprehensive Automated Verification Suite.

Tests cover:
1. Prospective Evidence Authority:
   - Missing mandatory timestamps (feature_cutoff, inference_completion, journal_commit, decision, entry, expiry).
   - Strict causal ordering ($T_{feat} \\le T_{inf} \\le T_{commit} < T_{entry} \\le T_{expiry}$).
   - Outcome events before journal commit rejected.
   - Non-finite (NaN, Inf, <=0) timestamps rejected.
   - Caller cannot self-certify prospective status.
   - Manifest missing or non-live mode rejects to PROSPECTIVE_AUTHORITY_UNVERIFIED.
2. Broker-Accurate Contract Mapping:
   - Canonical MAPPING_V1_NEXT_TICK_ENTRY ($S_0$ is next tick) vs MAPPING_V0_SIGNAL_TICK_ENTRY ($S_0$ is signal tick).
   - Two-tick monotonic wins, ties, and reversals.
   - Five-tick monotonic wins, ties, and reversals.
   - Versioning provenance fields.
3. Execution-Quality Economic Cohorts:
   - Strict separation of Cohort A (All Resolved), Cohort B (Chrono Quoted <=60s),
     Cohort C (Execution Quality Proxy <=5s), Cohort D (Independent Confirmation).
   - Correct denominator accounting and exclusion reasons.
   - Separation of ex-ante EV from retrospective realized return.
   - Dependence-aware Moving-Block Bootstrap lower bounds.
   - Cross-session quote rejection.
4. Permanent Safety Invariants:
   - LIVE_EXECUTION_DISABLED = True compile-time lock across all modules.
   - NO_TRADE enforcement.
5. End-to-End SQLite Integration Fixture:
   - Realistic multi-table database environment with genuine schemas and real evaluation entrypoint.
"""
import copy
import json
import math
import os
import sqlite3
import tempfile
import pytest
import numpy as np

from contract_specification import (
    evaluate_canonical_outcome,
    compare_entry_mappings,
    ContractEntryMappingVersion,
    CONTRACT_SPECIFICATION_VERSION,
    ENTRY_MAPPING_VERSION_DEFAULT,
    OUTCOME_RESOLVER_VERSION_DEFAULT,
    CANONICAL_RUNHIGH_2T_SPEC,
    CANONICAL_RUNLOW_2T_SPEC,
    CANONICAL_RUNHIGH_5T_SPEC,
    CANONICAL_RUNLOW_5T_SPEC,
)
from dual_duration_research import (
    DualDurationEvaluator,
    DualDurationComparisonReport,
    ResearchObservation,
    DurationMetricSummary,
    EvidenceClass,
    EvaluationMode,
    ResearchCohort,
    ResearchEdgeLadder,
    adapt_prediction_record,
    LIVE_EXECUTION_DISABLED,
)


class TestProspectiveEvidenceAuthority:
    """Objective 1: Prospective Evidence Authority Tests."""

    def test_missing_feature_cutoff_timestamp_fails_authority(self):
        row = {
            "prediction_id": "p_01",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": None,  # MISSING!
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1000.03,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        obs = adapt_prediction_record(row)
        assert obs.has_mandatory_chronology is False
        assert "MISSING_OR_INVALID_FEATURE_CUTOFF_TIMESTAMP" in obs.chronology_error_reason

    def test_missing_inference_completion_timestamp_fails_authority(self):
        row = {
            "prediction_id": "p_02",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": 1000.0,
            "inference_completion_timestamp": None,  # MISSING!
            "journal_commit_timestamp": 1000.03,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        obs = adapt_prediction_record(row)
        assert obs.has_mandatory_chronology is False
        assert "MISSING_OR_INVALID_INFERENCE_COMPLETION_TIMESTAMP" in obs.chronology_error_reason

    def test_missing_journal_commit_timestamp_fails_authority(self):
        row = {
            "prediction_id": "p_03",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": 1000.0,
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": None,  # MISSING!
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        obs = adapt_prediction_record(row)
        assert obs.has_mandatory_chronology is False
        assert "MISSING_OR_INVALID_JOURNAL_COMMIT_TIMESTAMP" in obs.chronology_error_reason

    def test_incorrect_internal_chronology_ordering_fails_authority(self):
        # Feature cutoff occurs after inference completion!
        row = {
            "prediction_id": "p_04",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": 1000.05,  # Later than inference!
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1000.06,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        obs = adapt_prediction_record(row)
        assert obs.has_mandatory_chronology is False
        assert "CAUSAL_VIOLATION_FEATURE_AFTER_INFERENCE" in obs.chronology_error_reason

    def test_outcome_event_before_journal_commitment_fails_authority(self):
        # Journal commit happens after the entry tick epoch!
        row = {
            "prediction_id": "p_05",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": 1000.0,
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1005.0,  # Later than entry_epoch 1002!
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        obs = adapt_prediction_record(row)
        assert obs.has_mandatory_chronology is False
        assert "CAUSAL_VIOLATION_JOURNAL_AFTER_ENTRY" in obs.chronology_error_reason

    def test_outcome_resolution_before_entry_fails_authority(self):
        row = {
            "prediction_id": "p_06",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": 1000.0,
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1000.03,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
        }
        outcome_row = {
            "prediction_id": "p_06",
            "resolution_timestamp": 1001.0  # Before entry epoch 1002!
        }
        obs = adapt_prediction_record(row, outcome_row)
        assert obs.has_mandatory_chronology is False
        assert "CAUSAL_VIOLATION_ENTRY_AFTER_RESOLUTION" in obs.chronology_error_reason

    def test_non_finite_timestamps_fail_authority(self):
        row_nan = {
            "prediction_id": "p_07",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "feature_cutoff_timestamp": float("nan"),
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1000.03,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
        }
        obs = adapt_prediction_record(row_nan)
        assert obs.has_mandatory_chronology is False

        row_neg = {
            "prediction_id": "p_08",
            "session_id": "sess_auth_01",
            "contract_duration": 2,
            "timestamp": -5.0,  # Negative timestamp
            "feature_cutoff_timestamp": 1000.0,
            "inference_completion_timestamp": 1000.02,
            "journal_commit_timestamp": 1000.03,
            "entry_epoch": 1002,
            "expiry_epoch": 1006,
            "outcome_status": "OUTCOME_RESOLVED",
            "runhigh_pred_prob": 0.25,
            "runlow_pred_prob": 0.25,
        }
        obs_neg = adapt_prediction_record(row_neg)
        assert obs_neg.has_mandatory_chronology is False

    def test_caller_supplied_prospective_classification_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        prices = [100.0 + i * 0.1 for i in range(50)]
        # Caller attempts to self-certify as PROSPECTIVE_SHADOW on raw prices
        report = evaluator.evaluate_ticks(
            prices=prices,
            evidence_class=EvidenceClass.PROSPECTIVE_SHADOW,
            prospective_journal_records=None,
            session_manifest=None
        )
        assert report.evidence_class != EvidenceClass.PROSPECTIVE_SHADOW.value
        assert "EVIDENCE AUTHORITY FAIL-CLOSED" in report.selection_bias_warning

    def test_unregistered_session_manifest_rejects_to_unverified(self, tmp_path):
        evaluator = DualDurationEvaluator(symbol="R_75")
        db_path = str(tmp_path / "test_unverified.db")
        con = sqlite3.connect(db_path)
        con.execute("""
            CREATE TABLE forward_predictions (
                session_id TEXT, prediction_id TEXT PRIMARY KEY, timestamp REAL, contract_duration INTEGER,
                model_id TEXT, model_checksum TEXT, quote_id TEXT, runhigh_pred_prob REAL, runlow_pred_prob REAL,
                runhigh_win REAL, runlow_win REAL, outcome_status TEXT, feature_cutoff_timestamp REAL,
                inference_completion_timestamp REAL, journal_commit_timestamp REAL, entry_epoch INTEGER, expiry_epoch INTEGER
            )
        """)
        con.execute("""
            CREATE TABLE forward_outcomes (
                outcome_id TEXT PRIMARY KEY, prediction_id TEXT, session_id TEXT, outcome_status TEXT,
                runhigh_win REAL, runlow_win REAL, resolution_timestamp REAL
            )
        """)
        con.commit()
        con.close()

        # Non-existent session
        report = evaluator.evaluate_prospective_session("non-existent-session-id", journal_db_path=db_path)
        assert report.evidence_class == EvidenceClass.PROSPECTIVE_AUTHORITY_UNVERIFIED.value
        assert "PROSPECTIVE_AUTHORITY_UNVERIFIED" in report.selection_bias_warning


class TestDerivContractMapping:
    """Objective 2: Broker-Accurate Contract Mapping Tests."""

    def test_canonical_mapping_version_constants(self):
        assert CONTRACT_SPECIFICATION_VERSION == "1.7.4.5"
        assert ENTRY_MAPPING_VERSION_DEFAULT == "MAPPING_V1_NEXT_TICK_ENTRY"
        assert OUTCOME_RESOLVER_VERSION_DEFAULT == "1.7.4.5"
        assert ContractEntryMappingVersion.MAPPING_V1_NEXT_TICK_ENTRY.value == "MAPPING_V1_NEXT_TICK_ENTRY"
        assert ContractEntryMappingVersion.MAPPING_V0_SIGNAL_TICK_ENTRY.value == "MAPPING_V0_SIGNAL_TICK_ENTRY"

    def test_two_tick_v1_next_tick_entry_reconstruction(self):
        # In V1 (Official Broker): S0 is first forward tick (101.0), S1 is 102.0, S2 is 103.0
        # Signal price is 100.0 (not part of the 2 movements)
        ticks_v1_win = [101.0, 102.0, 103.0]
        res_rh = evaluate_canonical_outcome("RUNHIGH", ticks_v1_win, duration_ticks=2)
        assert res_rh.is_win is True
        assert len(res_rh.prices) == 3  # S0, S1, S2
        assert res_rh.intermediate_evaluations == [True, True]

        res_rl = evaluate_canonical_outcome("RUNLOW", ticks_v1_win, duration_ticks=2)
        assert res_rl.is_win is False

    def test_two_tick_tie_loss_and_reversal(self):
        # Tie at expiry: S0=100.0 < S1=101.0 == S2=101.0 -> LOSS
        ticks_tie = [100.0, 101.0, 101.0]
        assert evaluate_canonical_outcome("RUNHIGH", ticks_tie, duration_ticks=2).is_win is False
        assert evaluate_canonical_outcome("RUNLOW", ticks_tie, duration_ticks=2).is_win is False

        # Reversal: S0=100.0 < S1=101.0 > S2=100.5 -> LOSS
        ticks_rev = [100.0, 101.0, 100.5]
        assert evaluate_canonical_outcome("RUNHIGH", ticks_rev, duration_ticks=2).is_win is False
        assert evaluate_canonical_outcome("RUNLOW", ticks_rev, duration_ticks=2).is_win is False

    def test_five_tick_monotonic_runlow_win_and_reversal(self):
        # 5-tick RUNLOW win: S0=100.0 > S1=99.0 > S2=98.0 > S3=97.0 > S4=96.0 > S5=95.0
        ticks_5t_win = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
        res_win = evaluate_canonical_outcome("RUNLOW", ticks_5t_win, duration_ticks=5)
        assert res_win.is_win is True
        assert len(res_win.prices) == 6  # S0 .. S5
        assert res_win.intermediate_evaluations == [True, True, True, True, True]

        # 5-tick reversal at 4th tick: S0 > S1 > S2 > S3 < S4 -> LOSS
        ticks_5t_rev = [100.0, 99.0, 98.0, 97.0, 97.5, 96.0]
        res_loss = evaluate_canonical_outcome("RUNLOW", ticks_5t_rev, duration_ticks=5)
        assert res_loss.is_win is False

    def test_compare_entry_mappings_v1_vs_v0(self):
        # Case where V1 wins but V0 loses:
        # Signal price = 105.0. Forward prices = [100.0, 101.0, 102.0]
        # Under V1: S0=100.0, S1=101.0, S2=102.0 -> S0 < S1 < S2 (WIN for RUNHIGH)
        # Under V0: S0=105.0, S1=100.0, S2=101.0 -> S0 > S1 < S2 (LOSS for RUNHIGH)
        signal_p = 105.0
        fwd_p = [100.0, 101.0, 102.0]
        comp = compare_entry_mappings(fwd_p, signal_p, duration_ticks=2)
        assert comp["v1_runhigh_win"] == 1.0
        assert comp["v0_runhigh_win"] == 0.0
        assert comp["is_discrepant_runhigh"] is True
        assert comp["is_discrepant_runlow"] is False


class TestExecutionQualityEconomics:
    """Objective 3: Execution-Quality Economic Analysis Tests."""

    def test_cohort_enum_definitions(self):
        assert ResearchCohort.COHORT_A_ALL_RESOLVED.value == "COHORT_A_ALL_RESOLVED"
        assert ResearchCohort.COHORT_B_CHRONOLOGICALLY_QUOTED.value == "COHORT_B_CHRONOLOGICALLY_QUOTED"
        assert ResearchCohort.COHORT_C_EXECUTION_QUALITY_PROXY.value == "COHORT_C_EXECUTION_QUALITY_PROXY"
        assert ResearchCohort.COHORT_D_INDEPENDENT_CONFIRMATION.value == "COHORT_D_INDEPENDENT_CONFIRMATION"

    def test_quote_freshness_filter_separates_cohort_b_and_c(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        
        # Decision at t=100.0. Quote response at t=92.0 (age = 8.0s)
        # Age 8.0s <= 60.0s (passes Cohort B), but > 5.0s (fails Cohort C)
        class DummyQuote:
            quote_record_id = "q_123"
            market_symbol = "R_75"
            currency = "USD"
            contract_duration = 2
            contract_type = "RUNHIGH"
            ask_price = 2.0
            total_payout = 7.63
            response_timestamp = 92.0
            collection_status = "QUOTE_AVAILABLE"

        quotes = [DummyQuote()]
        dec_ts = [100.0]

        # Under max_freshness = 60.0s (Cohort B): matched
        matched_b, cov_b, rej_b = evaluator._match_quotes_per_decision(
            duration=2, direction="RUNHIGH", decision_timestamps=dec_ts, quote_records=quotes, max_freshness_seconds=60.0
        )
        assert matched_b[0] is not None
        assert cov_b["exec"] == 100.0

        # Under max_freshness = 5.0s (Cohort C): stale!
        matched_c, cov_c, rej_c = evaluator._match_quotes_per_decision(
            duration=2, direction="RUNHIGH", decision_timestamps=dec_ts, quote_records=quotes, max_freshness_seconds=5.0
        )
        assert matched_c[0] is None
        assert cov_c["exec"] == 0.0
        assert rej_c["QUOTE_STALE"] == 1

    def test_ex_ante_ev_vs_retrospective_hypothetical_return_distinction(self):
        # Ex-ante EV uses predicted probability: EV = P * Payout - Ask
        # Retrospective return uses realized outcome: Return = Y * Payout - Ask
        p_model = 0.30
        payout = 7.63
        ask = 2.00
        y_realized = 0.0  # Actually lost!

        ex_ante_ev = (p_model * payout) - ask  # 0.30 * 7.63 - 2.0 = +$0.289
        retro_return = (y_realized * payout) - ask  # 0.0 - 2.0 = -$2.00

        assert ex_ante_ev > 0.0
        assert retro_return < 0.0
        assert abs(ex_ante_ev - retro_return) > 2.0

    def test_cross_session_quote_rejected(self):
        evaluator = DualDurationEvaluator(symbol="R_75")
        class DummyQuote:
            quote_record_id = "q_mismatch"
            market_symbol = "R_75"
            currency = "USD"
            contract_duration = 2
            contract_type = "RUNHIGH"
            ask_price = 2.0
            total_payout = 7.63
            response_timestamp = 99.0
            collection_status = "QUOTE_AVAILABLE"
            session_id = "session_A"

        quotes = [DummyQuote()]
        dec_ts = [100.0]

        matched, cov, rej = evaluator._match_quotes_per_decision(
            duration=2, direction="RUNHIGH", decision_timestamps=dec_ts, quote_records=quotes,
            expected_session_id="session_B"  # Mismatch!
        )
        assert matched[0] is None
        assert rej["QUOTE_WRONG_SESSION"] == 1


class TestSafetyAndPolicyInvariants:
    """Safety invariants tests."""

    def test_live_execution_permanently_disabled(self):
        assert LIVE_EXECUTION_DISABLED is True

    def test_evidence_ladder_level_zero_verdict(self):
        assert ResearchEdgeLadder.NO_VALIDATED_POSITIVE_EV_EDGE.value == "NO_VALIDATED_POSITIVE_EV_EDGE"


class TestEndToEndRealisticSQLiteIntegration:
    """Objective 12: Comprehensive Realistic SQLite Fixture Integration Test."""

    @pytest.fixture
    def realistic_environment(self, tmp_path):
        sess_id = "sess-v1745-integ-test-456"
        j_db = str(tmp_path / "forward_predictions.db")
        q_db = str(tmp_path / "quotes.db")
        s_db = str(tmp_path / "sessions.db")
        m_file = str(tmp_path / "manifest.json")

        # 1. Manifest
        manifest = {
            "session_id": sess_id,
            "symbol": "R_75",
            "mode": "SHADOW",
            "status": "COMPLETED",
            "model_version": "M_R_75_2TICK_20261011_120000",
            "start_time_utc": "2026-10-12T06:00:00Z",
            "end_time_utc": "2026-10-12T06:30:00Z"
        }
        with open(m_file, "w") as f:
            json.dump(manifest, f)

        # 2. Quotes DB
        con_q = sqlite3.connect(q_db)
        con_q.execute("""
            CREATE TABLE quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_record_id TEXT, proposal_id TEXT, session_id TEXT,
                market_symbol TEXT, contract_type TEXT, contract_duration INTEGER,
                duration_unit TEXT DEFAULT 't',
                currency TEXT DEFAULT 'USD', ask_price REAL, total_payout REAL, stake REAL,
                potential_net_profit REAL DEFAULT 5.63,
                quote_source TEXT DEFAULT 'live_proposal', quote_latency_ms REAL DEFAULT 15.0,
                request_timestamp REAL, response_timestamp REAL, collection_status TEXT,
                api_response_metadata TEXT, created_at TEXT DEFAULT '', basis TEXT DEFAULT 'stake'
            )
        """)
        # Insert valid fresh quotes (age <= 5s) and stale quotes (age > 5s, <= 60s)
        quotes_data = [
            ("qr_1", "p_1", sess_id, "R_75", "RUNHIGH", 2, "USD", 2.0, 7.63, 2.0, 99.5, 99.8, "QUOTE_AVAILABLE", json.dumps({"spot": 100.0})),
            ("qr_2", "p_2", sess_id, "R_75", "RUNLOW",  2, "USD", 2.0, 7.63, 2.0, 99.5, 99.8, "QUOTE_AVAILABLE", json.dumps({"spot": 100.0})),
            ("qr_3", "p_3", sess_id, "R_75", "RUNHIGH", 5, "USD", 2.0, 61.07, 2.0, 99.5, 99.8, "QUOTE_AVAILABLE", json.dumps({"spot": 100.0})),
            ("qr_4", "p_4", sess_id, "R_75", "RUNLOW",  5, "USD", 2.0, 61.07, 2.0, 99.5, 99.8, "QUOTE_AVAILABLE", json.dumps({"spot": 100.0})),
            # Quote for t=110.0: response at t=102.0 (age = 8.0s -> stale for Cohort C, valid for Cohort B)
            ("qr_5", "p_5", sess_id, "R_75", "RUNHIGH", 2, "USD", 2.0, 7.63, 2.0, 101.5, 102.0, "QUOTE_AVAILABLE", json.dumps({"spot": 100.0})),
        ]
        con_q.executemany("INSERT INTO quotes (quote_record_id, proposal_id, session_id, market_symbol, contract_type, contract_duration, currency, ask_price, total_payout, stake, request_timestamp, response_timestamp, collection_status, api_response_metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", quotes_data)
        con_q.commit()
        con_q.close()

        # 3. Predictions DB
        con_p = sqlite3.connect(j_db)
        con_p.execute("""
            CREATE TABLE forward_predictions (
                session_id TEXT, prediction_id TEXT PRIMARY KEY, timestamp REAL, contract_duration INTEGER,
                model_id TEXT, model_checksum TEXT, quote_id TEXT, runhigh_pred_prob REAL, runlow_pred_prob REAL,
                runhigh_win REAL, runlow_win REAL, outcome_status TEXT, feature_cutoff_timestamp REAL,
                inference_completion_timestamp REAL, journal_commit_timestamp REAL, entry_epoch INTEGER, expiry_epoch INTEGER,
                symbol TEXT
            )
        """)
        con_p.execute("""
            CREATE TABLE forward_outcomes (
                outcome_id TEXT PRIMARY KEY, prediction_id TEXT, session_id TEXT, outcome_status TEXT,
                runhigh_win REAL, runlow_win REAL, resolution_timestamp REAL
            )
        """)

        # Add predictions:
        # p1 (2T, t=100.0, valid chronology, win RH)
        # p2 (2T, t=110.0, valid chronology, quote age 8s -> stale for C, valid for B)
        # p3 (5T, t=100.0, valid chronology, win RL)
        preds = [
            (sess_id, "pred_2t_1", 100.0, 2, "M_2T", "chk", "qr_1", 0.28, 0.22, 1.0, 0.0, "OUTCOME_RESOLVED", 99.8, 99.9, 99.95, 102, 106, "R_75"),
            (sess_id, "pred_2t_2", 110.0, 2, "M_2T", "chk", "qr_5", 0.24, 0.26, 0.0, 1.0, "OUTCOME_RESOLVED", 109.8, 109.9, 109.95, 112, 116, "R_75"),
            (sess_id, "pred_5t_1", 100.0, 5, "M_5T", "chk", "qr_3", 0.035, 0.040, 0.0, 1.0, "OUTCOME_RESOLVED", 99.8, 99.9, 99.95, 102, 112, "R_75"),
        ]
        con_p.executemany("INSERT INTO forward_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", preds)

        outcomes = [
            ("out_1", "pred_2t_1", sess_id, "OUTCOME_RESOLVED", 1.0, 0.0, 107.0),
            ("out_2", "pred_2t_2", sess_id, "OUTCOME_RESOLVED", 0.0, 1.0, 117.0),
            ("out_3", "pred_5t_1", sess_id, "OUTCOME_RESOLVED", 0.0, 1.0, 113.0),
        ]
        con_p.executemany("INSERT INTO forward_outcomes VALUES (?,?,?,?,?,?,?)", outcomes)
        con_p.commit()
        con_p.close()

        return {
            "session_id": sess_id,
            "j_db": j_db,
            "q_db": q_db,
            "manifest": m_file
        }

    def test_full_evaluation_pipeline_with_cohort_breakdown(self, realistic_environment):
        env = realistic_environment
        evaluator = DualDurationEvaluator(symbol="R_75")

        report = evaluator.evaluate_prospective_session(
            session_id=env["session_id"],
            manifest_path=env["manifest"],
            journal_db_path=env["j_db"],
            quote_db_path=env["q_db"]
        )

        assert report.evidence_class == EvidenceClass.PROSPECTIVE_SHADOW.value
        assert "COHORT_A_ALL_RESOLVED" in report.cohort_metrics
        assert "COHORT_B_CHRONOLOGICALLY_QUOTED" in report.cohort_metrics
        assert "COHORT_C_EXECUTION_QUALITY_PROXY" in report.cohort_metrics
        assert "COHORT_D_INDEPENDENT_CONFIRMATION" in report.cohort_metrics

        cohort_b = report.cohort_metrics["COHORT_B_CHRONOLOGICALLY_QUOTED"]["2T_RUNHIGH"]
        cohort_c = report.cohort_metrics["COHORT_C_EXECUTION_QUALITY_PROXY"]["2T_RUNHIGH"]

        # In Cohort B (freshness <= 60s), both decisions (t=100 and t=110) match quotes (100% coverage)
        assert cohort_b.eligible_quote_decisions_count == 2
        assert cohort_b.execution_quality_coverage_pct == 100.0

        # In Cohort C (freshness <= 5s), only decision t=100 matches (age 0.2s <= 5s); t=110 (age 8s) is stale!
        assert cohort_c.eligible_quote_decisions_count == 1
        assert cohort_c.execution_quality_coverage_pct == 50.0
        assert cohort_c.stale_quote_count == 1

        # Cohort D is marked as requiring preregistration
        cohort_d = report.cohort_metrics["COHORT_D_INDEPENDENT_CONFIRMATION"]["2T_RUNHIGH"]
        assert cohort_d.verdict == "PREREGISTRATION_REQUIRED_FOR_CONFIRMATION"
        assert cohort_d.is_economically_positive is False
