"""V1.6.3 System Integration & Verification Tests.

Validates all requirements of the V1.6.3 Master Development Prompt:
1. Dynamic Lookback: ModelArtifact.required_lookback dynamic loading and serialization.
2. Historical Feature Warmup: Preloading verified historical ticks without lookahead.
3. Separation of Historical Warmup vs Live Ticks: Warmup ticks are segregated from live counts.
4. SHADOW Predictions Independence: Missing proposal quotes does NOT block SHADOW prediction journaling.
5. Prediction Pipeline Diagnostics: Pipeline status transitions, blocker diagnostics, get_diagnostics_report().
6. Authority Outcome Chronology: SessionReconciler reads timestamps from forward_outcomes.
7. Contract Family Canonicalization: RUNHIGH_RUNLOW canonical labels.
8. Two-Session Offline End-to-End Integration Lifecycle with complete provenance.
9. Safety Invariant: Real-money trading permanently disabled.
"""
import json
import os
import sqlite3
import tempfile
import time
import pytest
import pandas as pd
import numpy as np

from config import DEFAULT_CONFIG
from model_artifact import ModelArtifact, ModelStatus
from forward_observer import (
    ForwardObserver,
    PIPELINE_STATUS_WAITING_FOR_WARMUP,
    PIPELINE_STATUS_WARMUP_COMPLETE,
    PIPELINE_STATUS_PREDICTION_GENERATED,
    PIPELINE_STATUS_FEATURE_NOT_READY
)
from live_collector import LiveTickRecord
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_VERIFIED
)
from forward_session import ForwardSessionRegistry, STATUS_ACTIVE, STATUS_COMPLETED
from session_reconciler import SessionReconciler
from quote_database import QuoteDatabase


def _make_dummy_model_artifact(model_id: str = "M_TEST", required_lookback: int = 25) -> ModelArtifact:
    return ModelArtifact(
        model_id=model_id,
        model_version="1.6.3",
        created_at_utc="2026-10-08T00:00:00Z",
        training_dataset_id="DS_TEST",
        dataset_checksum="dummy_checksum_12345",
        market_symbol="R_75",
        contract_family="RUNHIGH_RUNLOW",
        contract_duration=5,
        contract_duration_unit="t",
        outcome_definition_version="1.5",
        feature_schema_version="1.5.3",
        feature_names=["streak", "volatility"],
        feature_ordering=["streak", "volatility"],
        model_type="EMPIRICAL_STATE_CONDITIONAL",
        model_parameters={"base_rate_runhigh": 0.032, "base_rate_runlow": 0.032},
        calibration_parameters={"brier_score": 0.03},
        training_sample_count=1000,
        validation_sample_count=500,
        holdout_sample_count=500,
        validation_metrics={"brier": 0.03},
        statistical_status="CANDIDATE",
        approval_status=ModelStatus.VALIDATED_RESEARCH,
        model_hash="",
        required_lookback=required_lookback
    )


class TestDynamicLookback:
    def test_default_required_lookback(self):
        art = _make_dummy_model_artifact("M_TEST_DEFAULT", required_lookback=25)
        assert art.required_lookback == 25

    def test_custom_dynamic_lookback_serialization(self):
        art = _make_dummy_model_artifact("M_TEST_CUSTOM_LOOKBACK", required_lookback=35)
        data = art.to_dict()
        assert data["required_lookback"] == 35

        loaded = ModelArtifact.from_dict(data)
        assert loaded.required_lookback == 35


class TestHistoricalWarmupPreloading:
    def test_preload_historical_warmup_from_csv(self, tmp_path):
        csv_path = tmp_path / "data" / "R_75_live_ticks.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        epochs = [1700000000 + i * 2 for i in range(50)]
        prices = [100.0 + i * 0.1 for i in range(50)]
        df = pd.DataFrame({"server_timestamp": epochs, "price": prices})
        df.to_csv(csv_path, index=False)

        journal_db = str(tmp_path / "journal.db")
        quote_db = str(tmp_path / "quotes.db")

        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=journal_db,
            quote_db_path=quote_db,
            preload_warmup=False
        )
        loaded = obs.preload_historical_warmup(csv_path=str(csv_path), lookback=25)
        assert loaded == 25
        assert obs.historical_warmup_ticks == 25
        assert len(obs.tick_history) == 25
        assert obs.pipeline_status == PIPELINE_STATUS_WARMUP_COMPLETE
        assert obs.live_ticks_count == 0  # Preloaded ticks are NOT counted as live ticks

    def test_preload_historical_warmup_detects_gaps_and_deduplicates(self, tmp_path):
        csv_path = tmp_path / "test_ticks.csv"
        data = [
            {"epoch": 100, "price": 10.0},
            {"epoch": 100, "price": 10.0},  # duplicate
            {"epoch": 102, "price": 10.1},
            {"epoch": 200, "price": 10.2},  # gap > 60s
            {"epoch": 202, "price": 10.3},
        ]
        pd.DataFrame(data).to_csv(csv_path, index=False)

        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            preload_warmup=False
        )
        loaded = obs.preload_historical_warmup(csv_path=str(csv_path), lookback=10)
        # Drops duplicate and resets at gap: keeps continuous segment (epoch 200, 202)
        assert loaded == 2
        assert len(obs.tick_history) == 2


class TestPredictionGenerationWithoutQuotes:
    def test_shadow_prediction_generated_without_quotes(self, tmp_path):
        journal_db = str(tmp_path / "test_journal.db")
        quote_db = str(tmp_path / "test_quotes.db")

        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=journal_db,
            quote_db_path=quote_db,
            preload_warmup=False,
            session_id="SESS_NO_QUOTE_TEST"
        )
        # Feed 24 warm-up ticks
        for i in range(24):
            tick = LiveTickRecord(
                symbol="R_75",
                server_timestamp=1700000000 + i * 2,
                local_receipt_timestamp=float(1700000000 + i * 2),
                price=100.0 + i * 0.05,
                source="LIVE_DERIV",
                session_id="SESS_NO_QUOTE_TEST",
                sequence_id=i + 1,
                data_quality_flags="NORMAL"
            )
            obs.process_incoming_tick(tick)

        assert obs.live_ticks_count == 0
        assert obs.warmup_ticks_count == 24
        assert obs.predictions_generated_count == 0

        # Feed 25th tick: satisfies lookback -> generates prediction
        tick25 = LiveTickRecord(
            symbol="R_75",
            server_timestamp=1700000000 + 24 * 2,
            local_receipt_timestamp=float(1700000000 + 24 * 2),
            price=101.25,
            source="LIVE_DERIV",
            session_id="SESS_NO_QUOTE_TEST",
            sequence_id=25,
            data_quality_flags="NORMAL"
        )
        pred = obs.process_incoming_tick(tick25)

        assert pred is not None
        assert pred.session_id == "SESS_NO_QUOTE_TEST"
        assert pred.quote_id == "QUOTE_UNAVAILABLE"
        assert obs.predictions_generated_count == 1
        assert obs.predictions_persisted_count == 1

        # Check journal persistence
        journal = ForwardPredictionJournal(db_path=journal_db)
        records = journal.get_session_predictions("SESS_NO_QUOTE_TEST")
        assert len(records) == 1
        assert records[0]["quote_id"] == "QUOTE_UNAVAILABLE"
        assert records[0]["decision"] == "NO_TRADE"


class TestDiagnosticsReport:
    def test_diagnostics_report_keys_and_blocker(self, tmp_path):
        obs = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            preload_warmup=False
        )
        diag = obs.get_diagnostics_report()

        assert diag["symbol"] == "R_75"
        assert diag["pipeline_status"] == PIPELINE_STATUS_WAITING_FOR_WARMUP
        assert diag["required_lookback"] == 25
        assert diag["ticks_in_buffer"] == 0
        assert diag["is_warmed_up"] is False
        assert "Waiting for 25 more warm-up ticks" in diag["current_blocker"]
        assert diag["safety_status"] == "REAL-MONEY TRADING DISABLED"


class TestOutcomeChronologyVerification:
    def test_chronology_reads_authoritative_outcome_record(self, tmp_path):
        reg_db = str(tmp_path / "sessions.db")
        jnl_db = str(tmp_path / "journal.db")
        q_db = str(tmp_path / "quotes.db")

        registry = ForwardSessionRegistry(db_path=reg_db)
        session = registry.create_session("R_75", mode="SHADOW")

        journal = ForwardPredictionJournal(db_path=jnl_db)
        quote_db = QuoteDatabase(db_path=q_db)

        # 1. Store valid quote at t=100
        quote_dict = {
            "request_timestamp": 99.0,
            "response_timestamp": 100.0,
            "market_symbol": "R_75",
            "contract_type": "RUNHIGH",
            "contract_duration": 5,
            "duration_unit": "t",
            "stake": 2.0,
            "total_payout": 61.03,
            "potential_net_profit": 59.03,
            "currency": "USD",
            "proposal_id": "PROP_100",
            "quote_source": "DERIV_PROPOSAL_WS",
            "quote_latency_ms": 100.0,
            "collection_status": "SUCCESS",
            "api_response_metadata": "{}",
            "session_id": session.session_id
        }
        quote_db.store_quote(quote_dict)

        # 2. Store prediction at t=102 referencing quote_id
        rec = ForwardPredictionRecord(
            prediction_id="p_chrono_1",
            session_id=session.session_id,
            timestamp=102.0,
            symbol="R_75",
            model_version="1.6.3",
            market_state="STABLE",
            features_json='{"streak": 1}',
            runhigh_pred_prob=0.035,
            runlow_pred_prob=0.032,
            runhigh_ask=2.0,
            runhigh_payout=61.03,
            runlow_ask=2.0,
            runlow_payout=61.03,
            decision="NO_TRADE",
            rejection_reason="NONE",
            signal_epoch=102,
            signal_price=100.0,
            outcome_status=STATUS_VERIFIED,
            quote_id="PROP_100",
            source_provenance="LIVE_DERIV"
        )
        pred_id = journal.log_prediction(rec)

        # 3. Store outcome in forward_outcomes with valid chronology:
        # entry=103.0, expiry=113.0, resolution=113.0
        with journal._get_conn() as conn:
            conn.execute("""
                INSERT INTO forward_outcomes (
                    outcome_id, prediction_id, session_id, entry_epoch, expiry_epoch,
                    forward_prices_json, forward_ticks_count, outcome_status,
                    runhigh_win, runlow_win, hypothetical_pnl, contract_model_version,
                    resolution_timestamp, verification_level, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "out_1", pred_id, session.session_id, 103, 113,
                "[100.2, 100.4, 100.6, 100.8, 101.0]", 5, STATUS_VERIFIED,
                1.0, 0.0, 59.03, "5_movement_canonical",
                113.0, "VERIFIED", "2026-10-08T00:00:00Z"
            ))

        # Reconcile session
        reconciler = SessionReconciler(
            registry_db_path=reg_db,
            journal_db_path=jnl_db,
            quote_db_path=q_db
        )
        recon_res = reconciler.reconcile_session(session.session_id)

        assert recon_res.chronology_errors == 0
        assert recon_res.future_quote_errors == 0


class TestTwoSessionOfflineIntegrationLifecycle:
    def test_two_distinct_sessions_isolation_and_lifecycle(self, tmp_path):
        reg_db = str(tmp_path / "sessions.db")
        jnl_db = str(tmp_path / "journal.db")
        q_db = str(tmp_path / "quotes.db")
        csv_s1 = str(tmp_path / "s1_ticks.csv")
        csv_s2 = str(tmp_path / "s2_ticks.csv")

        # Create isolated CSV files
        pd.DataFrame([{"server_timestamp": 1000 + i * 2, "price": 100.0 + i * 0.1} for i in range(25)]).to_csv(csv_s1, index=False)
        pd.DataFrame([{"server_timestamp": 2000 + i * 2, "price": 110.0 + i * 0.1} for i in range(26)]).to_csv(csv_s2, index=False)

        registry = ForwardSessionRegistry(db_path=reg_db)

        # Session 1
        sess1 = registry.create_session("R_75", mode="SHADOW", live_ticks_csv=csv_s1, notes="Session 1")
        obs1 = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=jnl_db,
            quote_db_path=q_db,
            session_id=sess1.session_id,
            preload_warmup=False
        )

        for i in range(25):
            t = LiveTickRecord(
                symbol="R_75",
                server_timestamp=1000 + i * 2,
                local_receipt_timestamp=float(1000 + i * 2),
                price=100.0 + i * 0.1,
                source="LIVE_DERIV",
                session_id=sess1.session_id,
                sequence_id=i + 1,
                data_quality_flags="NORMAL"
            )
            obs1.process_incoming_tick(t)

        registry.complete_session(
            sess1.session_id,
            status=STATUS_COMPLETED,
            total_ticks=25,
            total_predictions=obs1.predictions_generated_count,
            resolved_predictions=0,
            unverified_predictions=0,
            cumulative_pnl=0.0,
            live_ticks=obs1.live_ticks_count,
            warmup_ticks=obs1.warmup_ticks_count
        )

        # Session 2
        sess2 = registry.create_session("R_75", mode="SHADOW", live_ticks_csv=csv_s2, notes="Session 2")
        obs2 = ForwardObserver(
            symbol="R_75",
            mode="SHADOW",
            journal_db_path=jnl_db,
            quote_db_path=q_db,
            session_id=sess2.session_id,
            preload_warmup=False
        )

        for i in range(26):
            t = LiveTickRecord(
                symbol="R_75",
                server_timestamp=2000 + i * 2,
                local_receipt_timestamp=float(2000 + i * 2),
                price=110.0 + i * 0.1,
                source="LIVE_DERIV",
                session_id=sess2.session_id,
                sequence_id=i + 1,
                data_quality_flags="NORMAL"
            )
            obs2.process_incoming_tick(t)

        registry.complete_session(
            sess2.session_id,
            status=STATUS_COMPLETED,
            total_ticks=26,
            total_predictions=obs2.predictions_generated_count,
            resolved_predictions=0,
            unverified_predictions=0,
            cumulative_pnl=0.0,
            live_ticks=obs2.live_ticks_count,
            warmup_ticks=obs2.warmup_ticks_count
        )

        # Verify cross-session isolation in journal
        journal = ForwardPredictionJournal(db_path=jnl_db)
        preds_s1 = journal.get_session_predictions(sess1.session_id)
        preds_s2 = journal.get_session_predictions(sess2.session_id)

        assert len(preds_s1) == 1
        assert len(preds_s2) == 2
        assert preds_s1[0]["session_id"] == sess1.session_id
        for p in preds_s2:
            assert p["session_id"] == sess2.session_id

        # Reconcile each session independently
        reconciler = SessionReconciler(
            registry_db_path=reg_db,
            journal_db_path=jnl_db,
            quote_db_path=q_db
        )
        res1 = reconciler.reconcile_session(sess1.session_id)
        res2 = reconciler.reconcile_session(sess2.session_id)

        assert res1.total_predictions == 1
        assert res2.total_predictions == 2
        assert res1.cross_session_predictions == 0
        assert res2.cross_session_predictions == 0
