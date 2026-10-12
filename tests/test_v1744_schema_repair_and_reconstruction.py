"""Automated Regression and Unit Tests for V1.7.4.4 Schema Integrity,

Strict 3-Way Classification, Independent Reconstruction & Prospective Authority.
"""
import math
import os
import sqlite3
import tempfile
import pytest

from dual_duration_research import (
    DualDurationEvaluator,
    ResearchObservation,
    adapt_prediction_record,
    EvidenceClass,
    EvaluationMode
)
from contract_specification import (
    evaluate_canonical_outcome,
    CANONICAL_RUNHIGH_2T_SPEC,
    CANONICAL_RUNLOW_2T_SPEC,
    CANONICAL_RUNHIGH_5T_SPEC,
    CANONICAL_RUNLOW_5T_SPEC
)


class TestV1744SchemaIntegrityAndAdapter:
    """Verifies Objective A: Schema Mapping & Objective B: Strict Classification."""

    def test_authoritative_field_mapping_and_zero_fallback(self):
        """Authoritative columns runhigh_pred_prob and runhigh_win are read with no theoretical fallbacks."""
        pred_row = {
            "prediction_id": "P101",
            "session_id": "S101",
            "contract_duration": 2,
            "timestamp": 1000.0,
            "model_id": "M_2T",
            "runhigh_pred_prob": 0.285,
            "runlow_pred_prob": 0.215,
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
            "outcome_status": "OUTCOME_RESOLVED",
            "feature_cutoff_timestamp": 999.0,
            "inference_completion_timestamp": 999.5,
            "journal_commit_timestamp": 1000.0
        }
        obs = adapt_prediction_record(pred_row)
        assert obs.prediction_id == "P101"
        assert obs.runhigh_pred_prob == 0.285
        assert obs.runlow_pred_prob == 0.215
        assert obs.runhigh_outcome == "WIN"
        assert obs.runlow_outcome == "LOSS"
        assert not obs.is_incomplete
        assert not obs.is_discrepant

    def test_missing_and_invalid_probabilities_never_receive_defaults(self):
        """Missing, NaN, Inf, and out-of-range probabilities remain None and never default to 0.25 or 0.03125."""
        # None probability
        row_none = {"prediction_id": "P_NONE", "contract_duration": 2, "runhigh_pred_prob": None}
        obs_none = adapt_prediction_record(row_none)
        assert obs_none.runhigh_pred_prob is None

        # Out-of-range probability (> 1.0)
        row_high = {"prediction_id": "P_HIGH", "contract_duration": 5, "runhigh_pred_prob": 1.5}
        obs_high = adapt_prediction_record(row_high)
        assert obs_high.runhigh_pred_prob is None

        # Negative probability (< 0.0)
        row_neg = {"prediction_id": "P_NEG", "contract_duration": 2, "runlow_pred_prob": -0.1}
        obs_neg = adapt_prediction_record(row_neg)
        assert obs_neg.runlow_pred_prob is None

        # NaN probability
        row_nan = {"prediction_id": "P_NAN", "contract_duration": 5, "runhigh_pred_prob": float("nan")}
        obs_nan = adapt_prediction_record(row_nan)
        assert obs_nan.runhigh_pred_prob is None

        # Authentic 0.0 probability must be preserved!
        row_zero = {"prediction_id": "P_ZERO", "contract_duration": 2, "runhigh_pred_prob": 0.0}
        obs_zero = adapt_prediction_record(row_zero)
        assert obs_zero.runhigh_pred_prob == 0.0

    def test_strict_three_way_outcome_classification(self):
        """Wins are 1.0, Losses are 0.0, everything else (None, pending, gap) is UNAVAILABLE (never silent loss)."""
        # Win
        obs_w = adapt_prediction_record({
            "runhigh_win": 1.0,
            "outcome_status": "OUTCOME_RESOLVED"
        })
        assert obs_w.runhigh_outcome == "WIN"

        # Loss
        obs_l = adapt_prediction_record({
            "runhigh_win": 0.0,
            "outcome_status": "OUTCOME_RESOLVED"
        })
        assert obs_l.runhigh_outcome == "LOSS"

        # None raw value
        obs_none = adapt_prediction_record({
            "runhigh_win": None,
            "outcome_status": "OUTCOME_RESOLVED"
        })
        assert obs_none.runhigh_outcome == "UNAVAILABLE"

        # Pending status
        obs_pend = adapt_prediction_record({
            "runhigh_win": 1.0,
            "outcome_status": "PENDING"
        })
        assert obs_pend.runhigh_outcome == "UNAVAILABLE"
        assert obs_pend.is_incomplete

        # Data gap status
        obs_gap = adapt_prediction_record({
            "runhigh_win": 0.0,
            "outcome_status": "DATA_GAP"
        })
        assert obs_gap.runhigh_outcome == "UNAVAILABLE"
        assert obs_gap.is_data_gap

    def test_cross_table_outcome_discrepancy_rejection(self):
        """Discrepancy between forward_predictions and forward_outcomes rejects observation to UNAVAILABLE."""
        pred_row = {
            "prediction_id": "P_DISC",
            "runhigh_win": 1.0,
            "runlow_win": 0.0,
            "outcome_status": "OUTCOME_RESOLVED"
        }
        outcome_row = {
            "prediction_id": "P_DISC",
            "runhigh_win": 0.0,  # Conflicting!
            "runlow_win": 0.0
        }
        obs = adapt_prediction_record(pred_row, outcome_row)
        assert obs.is_discrepant is True
        assert obs.runhigh_outcome == "UNAVAILABLE"
        assert obs.runlow_outcome == "UNAVAILABLE"

    def test_exact_session_prefix_uniqueness_and_ambiguity_rejection(self, tmp_path):
        """Prefix matching multiple sessions raises ValueError with list of matches."""
        db_path = str(tmp_path / "forward_predictions.db")
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE forward_predictions (session_id TEXT, prediction_id TEXT, timestamp REAL)")
        con.execute("INSERT INTO forward_predictions VALUES ('abcd-1111', 'p1', 100.0)")
        con.execute("INSERT INTO forward_predictions VALUES ('abcd-2222', 'p2', 101.0)")
        con.commit()
        con.close()

        ev = DualDurationEvaluator()
        with pytest.raises(ValueError, match="Ambiguous session_id prefix 'abcd' matches multiple sessions"):
            ev.evaluate_prospective_session("abcd", journal_db_path=db_path)

    def test_prospective_authority_rejects_disordered_timestamps(self, tmp_path):
        """Timestamps where feature_cutoff > inference_completion fall back to HISTORICAL_REPLAY."""
        db_path = str(tmp_path / "forward_predictions.db")
        con = sqlite3.connect(db_path)
        con.execute("""
            CREATE TABLE forward_predictions (
                session_id TEXT, prediction_id TEXT, timestamp REAL, contract_duration INTEGER,
                model_id TEXT, model_checksum TEXT, quote_id TEXT, runhigh_pred_prob REAL, runlow_pred_prob REAL,
                runhigh_win REAL, runlow_win REAL, outcome_status TEXT, feature_cutoff_timestamp REAL,
                inference_completion_timestamp REAL, journal_commit_timestamp REAL
            )
        """)
        con.execute("""
            INSERT INTO forward_predictions VALUES (
                'sess-disorder', 'p1', 1000.0, 2, 'M2T', 'chk', 'q1', 0.25, 0.25, 1.0, 0.0,
                'OUTCOME_RESOLVED', 1005.0, 1002.0, 1000.0  -- Disordered timestamps!
            )
        """)
        con.execute("""
            CREATE TABLE forward_outcomes (
                outcome_id TEXT, prediction_id TEXT, session_id TEXT, outcome_status TEXT,
                runhigh_win REAL, runlow_win REAL, resolution_timestamp REAL
            )
        """)
        con.commit()
        con.close()

        manifest = {"session_id": "sess-disorder", "mode": "SHADOW"}
        m_file = str(tmp_path / "manifest.json")
        import json
        with open(m_file, "w") as f:
            json.dump(manifest, f)

        ev = DualDurationEvaluator()
        report = ev.evaluate_prospective_session("sess-disorder", manifest_path=m_file, journal_db_path=db_path)
        assert report.evidence_class == EvidenceClass.HISTORICAL_REPLAY.value
        assert "PROSPECTIVE_AUTHORITY_REJECTED" in report.selection_bias_warning

    def test_canonical_two_tick_and_five_tick_reconstruction(self):
        """Reconstruct 2T and 5T outcomes independently using monotonic pricing logic."""
        # 2-tick RUNHIGH win: S0 < S1 < S2
        ticks_2t_win = [100.0, 101.5, 102.0]
        assert evaluate_canonical_outcome("RUNHIGH", ticks_2t_win, duration_ticks=2).is_win is True
        assert evaluate_canonical_outcome("RUNLOW", ticks_2t_win, duration_ticks=2).is_win is False

        # 2-tick equality loss: S0 < S1 == S2
        ticks_2t_eq = [100.0, 101.5, 101.5]
        assert evaluate_canonical_outcome("RUNHIGH", ticks_2t_eq, duration_ticks=2).is_win is False
        assert evaluate_canonical_outcome("RUNLOW", ticks_2t_eq, duration_ticks=2).is_win is False

        # 5-tick RUNLOW win: S0 > S1 > S2 > S3 > S4 > S5
        ticks_5t_win = [100.0, 99.0, 98.5, 97.0, 96.0, 95.5]
        assert evaluate_canonical_outcome("RUNLOW", ticks_5t_win, duration_ticks=5).is_win is True
        assert evaluate_canonical_outcome("RUNHIGH", ticks_5t_win, duration_ticks=5).is_win is False

        # 5-tick reversal loss
        ticks_5t_rev = [100.0, 99.0, 98.5, 97.0, 98.0, 95.5]
        assert evaluate_canonical_outcome("RUNLOW", ticks_5t_rev, duration_ticks=5).is_win is False


class TestV1744EndToEndDatabaseRegression:
    """Mandatory Section 13.1 end-to-end integration regression with genuine SQLite fixture."""

    @pytest.fixture
    def mock_prospective_environment(self, tmp_path):
        """Constructs an SQLite database fixture containing:
        - 2T RUNHIGH win, 2T RUNLOW win, 2T losses
        - 5T RUNHIGH win, 5T RUNLOW win, 5T losses
        - One incomplete (PENDING) outcome
        - One data-gap outcome
        - Nonconstant stored model probabilities
        - Genuine quote records
        """
        j_db = str(tmp_path / "forward_predictions.db")
        q_db = str(tmp_path / "quotes.db")
        m_file = str(tmp_path / "manifest.json")
        sess_id = "test-session-e2e-1234567890abcdef"

        import json
        manifest = {
            "session_id": sess_id,
            "mode": "SHADOW",
            "symbol": "R_75",
            "status": "COMPLETED"
        }
        with open(m_file, "w") as f:
            json.dump(manifest, f)

        # Quotes DB
        from quote_database import QuoteDatabase
        q_database = QuoteDatabase(db_path=q_db)
        from quote_recorder import ProposalRecord

        # 2T quote
        q_database.store_quote(ProposalRecord(
            quote_record_id=f"QR_{sess_id}_p1_100",
            proposal_id="prop_2t_rh",
            request_timestamp=99.0,
            response_timestamp=99.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=2,
            duration_unit="t",
            stake=2.0,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            quote_source="live_proposal",
            quote_latency_ms=10.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess_id
        ))
        q_database.store_quote(ProposalRecord(
            quote_record_id=f"QR_{sess_id}_p2_100",
            proposal_id="prop_2t_rl",
            request_timestamp=99.0,
            response_timestamp=99.5,
            market_symbol="R_75",
            contract_type="RUNLOW",
            contract_duration=2,
            duration_unit="t",
            stake=2.0,
            total_payout=7.63,
            potential_net_profit=5.63,
            currency="USD",
            quote_source="live_proposal",
            quote_latency_ms=10.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess_id
        ))
        # 5T quote
        q_database.store_quote(ProposalRecord(
            quote_record_id=f"QR_{sess_id}_p3_100",
            proposal_id="prop_5t_rh",
            request_timestamp=99.0,
            response_timestamp=99.5,
            market_symbol="R_75",
            contract_type="RUNHIGH",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.07,
            potential_net_profit=59.07,
            currency="USD",
            quote_source="live_proposal",
            quote_latency_ms=10.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess_id
        ))
        q_database.store_quote(ProposalRecord(
            quote_record_id=f"QR_{sess_id}_p4_100",
            proposal_id="prop_5t_rl",
            request_timestamp=99.0,
            response_timestamp=99.5,
            market_symbol="R_75",
            contract_type="RUNLOW",
            contract_duration=5,
            duration_unit="t",
            stake=2.0,
            total_payout=61.07,
            potential_net_profit=59.07,
            currency="USD",
            quote_source="live_proposal",
            quote_latency_ms=10.0,
            collection_status="QUOTE_AVAILABLE",
            session_id=sess_id
        ))

        # Predictions DB
        con = sqlite3.connect(j_db)
        con.execute("""
            CREATE TABLE forward_predictions (
                session_id TEXT, prediction_id TEXT PRIMARY KEY, timestamp REAL, contract_duration INTEGER,
                model_id TEXT, model_checksum TEXT, quote_id TEXT, runhigh_pred_prob REAL, runlow_pred_prob REAL,
                runhigh_win REAL, runlow_win REAL, outcome_status TEXT, feature_cutoff_timestamp REAL,
                inference_completion_timestamp REAL, journal_commit_timestamp REAL
            )
        """)
        con.execute("""
            CREATE TABLE forward_outcomes (
                outcome_id TEXT PRIMARY KEY, prediction_id TEXT, session_id TEXT, outcome_status TEXT,
                runhigh_win REAL, runlow_win REAL, resolution_timestamp REAL
            )
        """)

        # Add 2T rows (total 6: 1 RH win, 1 RL win, 2 losses, 1 pending, 1 data_gap)
        records_2t = [
            ("p_2t_1", 100.0, 2, 0.28, 0.22, 1.0, 0.0, "OUTCOME_RESOLVED"), # 2T RH win
            ("p_2t_2", 102.0, 2, 0.21, 0.29, 0.0, 1.0, "OUTCOME_RESOLVED"), # 2T RL win
            ("p_2t_3", 104.0, 2, 0.24, 0.24, 0.0, 0.0, "OUTCOME_RESOLVED"), # loss
            ("p_2t_4", 106.0, 2, 0.25, 0.23, 0.0, 0.0, "OUTCOME_RESOLVED"), # loss
            ("p_2t_5", 108.0, 2, 0.26, 0.24, None, None, "PENDING"),         # pending incomplete
            ("p_2t_6", 110.0, 2, 0.27, 0.23, 0.0, 0.0, "DATA_GAP"),         # data gap
        ]

        # Add 5T rows (total 5: 1 RH win, 1 RL win, 3 losses)
        records_5t = [
            ("p_5t_1", 100.0, 5, 0.040, 0.025, 1.0, 0.0, "OUTCOME_RESOLVED"), # 5T RH win
            ("p_5t_2", 102.0, 5, 0.025, 0.042, 0.0, 1.0, "OUTCOME_RESOLVED"), # 5T RL win
            ("p_5t_3", 104.0, 5, 0.030, 0.031, 0.0, 0.0, "OUTCOME_RESOLVED"), # loss
            ("p_5t_4", 106.0, 5, 0.032, 0.029, 0.0, 0.0, "OUTCOME_RESOLVED"), # loss
            ("p_5t_5", 108.0, 5, 0.031, 0.030, 0.0, 0.0, "OUTCOME_RESOLVED"), # loss
        ]

        for pid, ts, dur, pr_h, pr_l, w_h, w_l, status in records_2t + records_5t:
            con.execute("""
                INSERT INTO forward_predictions VALUES (
                    ?, ?, ?, ?, 'M_FROZEN', 'chk123', 'q_id', ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (sess_id, pid, ts, dur, pr_h, pr_l, w_h, w_l, status, ts - 0.5, ts - 0.2, ts))

            if status == "OUTCOME_RESOLVED":
                con.execute("""
                    INSERT INTO forward_outcomes VALUES (
                        ?, ?, ?, ?, ?, ?, ?
                    )
                """, (f"o_{pid}", pid, sess_id, status, w_h, w_l, ts + 5.0))

        con.commit()
        con.close()

        return {
            "session_id": sess_id,
            "j_db": j_db,
            "q_db": q_db,
            "manifest": m_file
        }

    def test_end_to_end_evaluation_regression(self, mock_prospective_environment):
        """Executes full evaluate_prospective_session on the genuine-schema SQLite fixture."""
        env = mock_prospective_environment
        ev = DualDurationEvaluator()

        report = ev.evaluate_prospective_session(
            session_id=env["session_id"],
            manifest_path=env["manifest"],
            journal_db_path=env["j_db"],
            quote_db_path=env["q_db"]
        )

        assert report.evidence_class == EvidenceClass.PROSPECTIVE_SHADOW.value
        assert report.evaluation_mode == EvaluationMode.QUOTE_VERIFIED.value

        m_2t_rh = report.metrics["2T_RUNHIGH"]
        m_2t_rl = report.metrics["2T_RUNLOW"]
        m_5t_rh = report.metrics["5T_RUNHIGH"]
        m_5t_rl = report.metrics["5T_RUNLOW"]

        # Assert: Total predictions vs resolved outcomes
        assert m_2t_rh.total_predictions == 6
        assert m_2t_rh.resolved_outcomes == 4  # 6 total minus 1 pending minus 1 data gap!
        assert m_2t_rh.incomplete_count == 1
        assert m_2t_rh.data_gap_count == 1

        # Assert: Verified wins counted correctly
        assert m_2t_rh.wins == 1
        assert m_2t_rh.losses == 3
        assert m_2t_rh.empirical_win_rate == 0.25  # 1 / 4 resolved (not 1 / 6)

        assert m_2t_rl.wins == 1
        assert m_2t_rl.losses == 3
        assert m_2t_rl.empirical_win_rate == 0.25

        assert m_5t_rh.total_predictions == 5
        assert m_5t_rh.resolved_outcomes == 5
        assert m_5t_rh.wins == 1
        assert m_5t_rh.losses == 4
        assert m_5t_rh.empirical_win_rate == 0.20

        assert m_5t_rl.wins == 1
        assert m_5t_rl.losses == 4
        assert m_5t_rl.empirical_win_rate == 0.20

        # Assert: Mean model probabilities come from stored nonconstant fields (NOT defaults!)
        # 2T RH probabilities for resolved rows: 0.28, 0.21, 0.24, 0.25 -> mean = 0.245
        assert round(m_2t_rh.mean_predicted_prob, 3) == 0.245
        assert m_2t_rh.mean_predicted_prob != 0.250000

        # Assert: Ex-ante EV uses model probabilities
        assert m_2t_rh.ordinary_ev is not None

        # Assert: Retrospective returns computed from actual outcomes
        assert m_2t_rh.retrospective_realized_return is not None

        # Assert: Cross-duration isolation
        assert m_2t_rh.duration == 2
        assert m_5t_rh.duration == 5
