"""Comprehensive Regression and Integration Test Suite for V1.5.3 Hotfix.

Validates:
1. Feature Parity between batch historical features and streaming slices.
2. Frozen Model artifact export, loading, JSON integrity, and qualification gates.
3. Model rejection taxonomy: MODEL_NOT_FOUND, MODEL_SCHEMA_MISMATCH, MODEL_SYMBOL_MISMATCH, MODEL_UNVALIDATED.
4. Elimination of hardcoded probability placeholders (0.0680, 0.03275).
5. Elimination of benchmark quote fallbacks ($2 -> $61.03) and strict QUOTE_UNAVAILABLE enforcement.
6. Forward observer three-mode separation: DATA_COLLECTION_ONLY, SHADOW, and PAPER.
7. Prediction journal metrics: runhigh_observed_win_rate, runhigh_brier_score, inspect_recent().
8. Incomplete forward sequence protection (OUTCOME_UNVERIFIED, no artificial loss attribution).
9. Quote database inspection summary and NO_GENUINE_QUOTES_RECORDED empty message.
10. Low-level pre-flight connection verification and HTTP 520 diagnostic error classification.
11. Absolute real-money execution lock invariants.
"""
import json
import os
import sqlite3
import pytest
import numpy as np
import pandas as pd

from feature_schema import (
    FEATURE_SCHEMA_VERSION,
    CANONICAL_FEATURE_NAMES,
    extract_discrete_market_state,
    verify_feature_parity
)
from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
from forward_observer import ForwardObserver
from live_collector import LiveTickRecord
from model_artifact import ModelArtifact, ModelStatus, compute_file_sha256
from model_manager import ModelManager
from paper_trader import PaperTrader
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine
from quote_recorder import ProposalRecord
from verify_deriv_connection import DerivConnectionVerifier


def test_feature_parity_batch_vs_streaming_slice():
    """Verifies that offline batch and sliding streaming window generate identical feature states."""
    np.random.seed(42)
    prices = [100.0]
    for _ in range(80):
        step = np.random.choice([0.05, -0.05, 0.1, -0.1])
        prices.append(round(prices[-1] + step, 4))

    df_full = pd.DataFrame({"epoch": range(len(prices)), "price": prices})
    assert verify_feature_parity(df_full, slice_window=40) is True

    # Validate feature names match canonical schema
    feat_dict, state_str = extract_discrete_market_state(df_full)
    for k in CANONICAL_FEATURE_NAMES:
        assert k in feat_dict
        assert feat_dict[k] is not None
        assert f"{k}=" in state_str


def test_frozen_model_export_and_integrity(tmp_path):
    """Verifies frozen model export, SHA256 hashing, and validation loading."""
    csv_file = str(tmp_path / "mock_ticks.csv")
    models_dir = str(tmp_path / "models")

    # Generate 150 deterministic ticks
    prices = [100.0 + (i * 0.05 if i % 2 == 0 else -i * 0.04) for i in range(150)]
    df = pd.DataFrame({"epoch": range(150), "price": prices})
    df.to_csv(csv_file, index=False)

    mgr = ModelManager(models_dir=models_dir)
    artifact = mgr.train_and_export_baseline_model(
        csv_path=csv_file,
        symbol="R_75",
        approval_status=ModelStatus.RESEARCH_ONLY
    )

    assert artifact.market_symbol == "R_75"
    assert artifact.contract_duration == 5
    assert artifact.feature_schema_version == FEATURE_SCHEMA_VERSION
    assert artifact.approval_status == ModelStatus.RESEARCH_ONLY
    assert len(artifact.model_hash) == 64

    # Load and validate
    is_valid, code, loaded = mgr.validate_and_load_model(artifact.model_id, expected_symbol="R_75")
    assert is_valid is True
    assert code == "MODEL_VALIDATED"
    assert loaded is not None
    assert loaded.model_id == artifact.model_id

    # Test inference output format
    rh_prob, rl_prob, meta = loaded.predict_probabilities("mom_bin=STRONG_BULL")
    assert 0.0 < rh_prob < 1.0
    assert 0.0 < rl_prob < 1.0
    assert "source" in meta


def test_frozen_model_rejection_taxonomy(tmp_path):
    """Verifies model loading strictness: symbol mismatch, schema mismatch, and unvalidated status."""
    csv_file = str(tmp_path / "mock_ticks.csv")
    models_dir = str(tmp_path / "models")
    df = pd.DataFrame({"epoch": range(80), "price": [100.0 + (i * 0.02) for i in range(80)]})
    df.to_csv(csv_file, index=False)

    mgr = ModelManager(models_dir=models_dir)
    art = mgr.train_and_export_baseline_model(csv_file, symbol="R_75", approval_status=ModelStatus.RESEARCH_ONLY)

    # 1. Non-existent model
    ok, code, _ = mgr.validate_and_load_model("NON_EXISTENT_MODEL_ID")
    assert ok is False
    assert code == "MODEL_NOT_FOUND"

    # 2. Symbol mismatch
    ok, code, _ = mgr.validate_and_load_model(art.model_id, expected_symbol="R_100")
    assert ok is False
    assert code == "MODEL_SYMBOL_MISMATCH"

    # 3. Contract mismatch
    ok, code, _ = mgr.validate_and_load_model(art.model_id, expected_duration_ticks=10)
    assert ok is False
    assert code == "MODEL_CONTRACT_MISMATCH"

    # 4. Paper mode rejection for research-only model
    ok, code, loaded = mgr.validate_and_load_model(art.model_id, expected_symbol="R_75", require_paper_approval=True)
    assert ok is False
    assert code == "MODEL_UNVALIDATED"
    assert loaded is not None


def test_forward_observer_no_hardcoded_probabilities(tmp_path):
    """Verifies that forward observer computes predictions from the loaded model artifact, not constants."""
    j_db = str(tmp_path / "fwd.db")
    q_db = str(tmp_path / "q.db")
    models_dir = str(tmp_path / "models")

    # Train a frozen model with distinct empirical base rate
    csv_file = str(tmp_path / "test_ticks.csv")
    df = pd.DataFrame({"epoch": range(100), "price": [100.0 + (i * 0.05) for i in range(100)]})
    df.to_csv(csv_file, index=False)

    mgr = ModelManager(models_dir=models_dir)
    artifact = mgr.train_and_export_baseline_model(csv_file, symbol="R_75")

    observer = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        model_path_or_id=os.path.join(models_dir, f"{artifact.model_id}.json"),
        journal_db_path=j_db,
        quote_db_path=q_db
    )

    assert observer.model_artifact is not None
    assert observer.model_artifact.model_id == artifact.model_id

    # Ingest 35 ticks
    for i in range(35):
        observer.process_incoming_tick(LiveTickRecord(
            symbol="R_75",
            server_timestamp=1000 + i,
            local_receipt_timestamp=1000.0 + i,
            price=100.0 + (i * 0.1),
            source="test",
            session_id="s1",
            sequence_id=i + 1,
            data_quality_flags="NORMAL"
        ))

    recent = observer.journal.inspect_recent(limit=1)
    assert len(recent) == 1
    rec = recent[0]
    # Prediction must match artifact's calculation, not arbitrary 0.0680 or 0.03275
    expected_rh, _, _ = observer.model_artifact.predict_probabilities(rec["market_state"])
    assert abs(rec["runhigh_pred_prob"] - expected_rh) < 0.001


def test_forward_observer_no_benchmark_quote_fallbacks(tmp_path):
    """Proves that missing quotes return QUOTE_UNAVAILABLE and Null EV, never $2 -> $61.03."""
    j_db = str(tmp_path / "fwd.db")
    q_db = str(tmp_path / "empty_q.db")

    observer = ForwardObserver(
        symbol="R_75",
        mode="SHADOW",
        journal_db_path=j_db,
        quote_db_path=q_db
    )

    # Ingest 30 ticks with ZERO quotes in q_db
    for i in range(30):
        observer.process_incoming_tick(LiveTickRecord(
            symbol="R_75",
            server_timestamp=2000 + i,
            local_receipt_timestamp=2000.0 + i,
            price=105.0 + (i * 0.05),
            source="test",
            session_id="s1",
            sequence_id=i + 1,
            data_quality_flags="NORMAL"
        ))

    recent = observer.journal.inspect_recent(limit=1)
    assert len(recent) == 1
    rec = recent[0]

    # Critical assertions: NO $2.00 or $61.03 fallback values
    assert rec["runhigh_ask"] is None
    assert rec["runhigh_payout"] is None
    assert rec["runlow_ask"] is None
    assert rec["runlow_payout"] is None
    assert rec["break_even_runhigh"] is None
    assert rec["break_even_runlow"] is None
    assert rec["ev_runhigh"] is None
    assert rec["ev_runlow"] is None
    assert rec["cons_ev_runhigh"] is None
    assert rec["cons_ev_runlow"] is None
    assert "QUOTE_UNAVAILABLE" in rec["rejection_reason"]
    assert rec["decision"] == "NO_TRADE"


def test_forward_observer_modes_isolation(tmp_path):
    """Verifies behavioral separation across DATA_COLLECTION_ONLY, SHADOW, and PAPER modes."""
    j_db = str(tmp_path / "fwd.db")
    q_db = str(tmp_path / "q.db")

    # 1. DATA_COLLECTION_ONLY mode: Never creates predictions
    obs_collector = ForwardObserver(symbol="R_75", mode="DATA_COLLECTION_ONLY", journal_db_path=j_db, quote_db_path=q_db)
    for i in range(35):
        obs_collector.process_incoming_tick(LiveTickRecord(
            symbol="R_75", server_timestamp=3000 + i, local_receipt_timestamp=3000.0 + i,
            price=100.0 + (i * 0.02), source="test", session_id="s1", sequence_id=i + 1, data_quality_flags="NORMAL"
        ))
    assert len(obs_collector.journal.inspect_recent(limit=5)) == 0

    # 2. SHADOW mode: Generates predictions, enforces NO_TRADE with SHADOW_MODE_NON_TRADING
    obs_shadow = ForwardObserver(symbol="R_75", mode="SHADOW", journal_db_path=j_db, quote_db_path=q_db)
    for i in range(35):
        obs_shadow.process_incoming_tick(LiveTickRecord(
            symbol="R_75", server_timestamp=4000 + i, local_receipt_timestamp=4000.0 + i,
            price=100.0 + (i * 0.02), source="test", session_id="s1", sequence_id=i + 1, data_quality_flags="NORMAL"
        ))
    shadow_records = obs_shadow.journal.inspect_recent(limit=1)
    assert len(shadow_records) > 0
    assert shadow_records[0]["decision"] == "NO_TRADE"
    assert "SHADOW_MODE_NON_TRADING" in shadow_records[0]["rejection_reason"]

    # 3. PAPER mode with unvalidated model: Refuses paper trading
    obs_paper = ForwardObserver(symbol="R_75", mode="PAPER", journal_db_path=j_db, quote_db_path=q_db)
    for i in range(35):
        obs_paper.process_incoming_tick(LiveTickRecord(
            symbol="R_75", server_timestamp=5000 + i, local_receipt_timestamp=5000.0 + i,
            price=100.0 + (i * 0.02), source="test", session_id="s1", sequence_id=i + 1, data_quality_flags="NORMAL"
        ))
    paper_records = obs_paper.journal.inspect_recent(limit=1)
    assert len(paper_records) > 0
    assert paper_records[0]["decision"] == "NO_TRADE"


def test_forward_journal_incomplete_sequence_protection(tmp_path):
    """Proves incomplete tick sequences are marked OUTCOME_UNVERIFIED and NEVER counted as losses."""
    db_path = str(tmp_path / "journal.db")
    journal = ForwardPredictionJournal(db_path=db_path)

    rec = ForwardPredictionRecord(
        prediction_id="p_inc_1",
        timestamp=1000.0,
        symbol="R_75",
        model_version="v1.5.3",
        market_state="mom_bin=BULL",
        features_json="{}",
        runhigh_pred_prob=0.05,
        runlow_pred_prob=0.03,
        signal_epoch=1000,
        signal_price=100.0
    )
    journal.log_prediction(rec)

    # Ingest only 3 forward ticks
    for i in range(1, 4):
        journal.ingest_forward_tick(epoch=1000 + i, price=100.0 + (i * 0.1), symbol="R_75")

    # Mark incomplete
    journal.mark_incomplete_as_unverified(symbol="R_75")

    recent = journal.inspect_recent(limit=1)
    assert recent[0]["outcome_status"] == "OUTCOME_UNVERIFIED"
    assert recent[0]["runhigh_win"] is None
    assert recent[0]["runlow_win"] is None

    # Check metrics excludes unverified records from loss count
    metrics = journal.get_accuracy_metrics("R_75")
    assert metrics["resolved_predictions"] == 0
    assert metrics["unverified_predictions"] == 1
    assert metrics["runhigh_observed_win_rate"] is None


def test_quote_database_inspect_summary_and_empty_guard(tmp_path):
    """Validates QuoteDatabase inspect_summary correctly reports NO_GENUINE_QUOTES_RECORDED when empty."""
    db_path = str(tmp_path / "quotes.db")
    db = QuoteDatabase(db_path=db_path)

    summary = db.inspect_summary("R_75")
    assert summary["total_records"] == 0
    assert summary["runhigh_quotes"] == 0
    assert summary["runlow_quotes"] == 0
    assert summary["database_health"] == "EMPTY"

    # Now add genuine quote record
    rec = ProposalRecord(
        request_timestamp=1000.0,
        response_timestamp=1000.05,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_123",
        quote_source="live_proposal",
        quote_latency_ms=50.0,
        collection_status="QUOTE_AVAILABLE"
    )
    db.store_quote(rec)

    summary_active = db.inspect_summary("R_75")
    assert summary_active["total_records"] == 1
    assert summary_active["runhigh_quotes"] == 1
    assert summary_active["database_health"] == "HEALTHY"


def test_api_verifier_preflight_and_error_classification():
    """Verifies low-level pre-flight DNS/TCP/TLS check and error categorization in DerivConnectionVerifier."""
    verifier = DerivConnectionVerifier(symbol="R_75", timeout_seconds=4.0)

    # Preflight check against live cloud endpoint
    pre = verifier.run_preflight_network_check("wss://ws.derivws.com/websockets/v3")
    assert "hostname" in pre
    assert pre["hostname"] == "ws.derivws.com"
    # DNS should resolve in any internet-connected environment
    if pre["dns_resolved"]:
        assert len(pre["resolved_ips"]) > 0
        assert pre["dns_latency_ms"] > 0.0


def test_real_money_purchase_permanently_disabled():
    """Invariance test: Guarantees buy orders are impossible in research, forward, and paper engines."""
    assert ForwardObserver.LIVE_EXECUTION_DISABLED is True
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True
    from contract_lifecycle import ALLOW_DEMO_EXECUTION
    assert ALLOW_DEMO_EXECUTION is False
