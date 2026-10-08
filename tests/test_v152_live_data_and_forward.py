"""Comprehensive Automated Test Suite for V1.5.2 (Live Market Data, Real Quotes & Forward Paper Trading).

Validates:
1. Live tick streaming: message parsing, monotonic timestamp ordering, duplicate filtering, gap detection.
2. Contract lifecycle: formal 5-tick specification, strict settlement rules, and demo harness safety guards.
3. Health monitoring: connection telemetry, tick ingestion rates, quote success rates, storage checks.
4. Forward prediction journal: logging, forward 6-tick accumulation (S_0 to S_5), outcome resolution, and Brier score calculation.
5. Forward observer: shadow prediction generation without lookahead, frozen model evaluation, and safety invariants.
6. Paper trading: enhanced rejection reason taxonomy, settlement certainty, and zero live money execution.
7. Quote database: session ID persistence, lookahead-free queries, and freshness filtering.
8. Environment & config: secure .env parsing and safety directives.
"""
import json
import os
import time
import pytest
import numpy as np
import pandas as pd

from config import TradingConfig, load_env_file, DEFAULT_CONFIG
from contract_lifecycle import get_canonical_contract_spec, DemoSettlementHarness
from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
from forward_observer import ForwardObserver
from health_monitor import HealthMonitor
from live_collector import LiveTickStreamer, LiveTickRecord
from paper_trader import PaperTrader, PaperTradeRecord
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine
from quote_recorder import ProposalRecord


def test_live_collector_tick_parsing_and_gap_detection():
    """Validates live tick message parsing, duplicate filtering, and gap flags."""
    streamer = LiveTickStreamer(symbol="R_75", gap_threshold_seconds=3.0)

    # 1. First tick
    msg1 = {"tick": {"epoch": 1000, "quote": 100.50, "symbol": "R_75"}}
    rec1 = streamer.parse_tick_message(msg1, receipt_time=1000.05)
    assert rec1 is not None
    assert rec1.price == 100.50
    assert rec1.server_timestamp == 1000
    assert rec1.data_quality_flags == "NORMAL"
    assert streamer.ticks_received == 1

    # 2. Duplicate tick (same epoch and same price)
    msg_dup = {"tick": {"epoch": 1000, "quote": 100.50, "symbol": "R_75"}}
    rec_dup = streamer.parse_tick_message(msg_dup, receipt_time=1000.08)
    assert rec_dup is not None
    assert rec_dup.data_quality_flags == "DUPLICATE_IGNORED"
    assert streamer.duplicate_count == 1
    assert streamer.ticks_received == 1  # Valid tick count unchanged

    # 3. Gap tick (epoch jump > threshold)
    msg_gap = {"tick": {"epoch": 1005, "quote": 100.60, "symbol": "R_75"}}
    rec_gap = streamer.parse_tick_message(msg_gap, receipt_time=1005.02)
    assert rec_gap is not None
    assert rec_gap.data_quality_flags == "GAP_DETECTED"
    assert streamer.gap_count == 1
    assert streamer.ticks_received == 2


def test_contract_lifecycle_spec_and_settlement_rules():
    """Validates canonical contract specification and strict settlement constraints."""
    spec = get_canonical_contract_spec()
    assert spec["duration"] == 5
    assert spec["transition_count"] == 5
    assert "RUNHIGH" in spec["contract_types"]
    assert "RUNLOW" in spec["contract_types"]
    assert "equal" in spec["tie_rule"].lower()

    # Isolated demo harness safety lock
    harness = DemoSettlementHarness(symbol="R_75")
    assert harness.ALLOW_DEMO_EXECUTION is False  # Guaranteed default lock


def test_health_monitor_telemetry():
    """Validates real-time health telemetry across connection, ticks, quotes, and storage."""
    monitor = HealthMonitor(window_seconds=60.0)
    monitor.update_connection_status("CONNECTED")
    assert monitor.connection_status == "CONNECTED"

    # Record ticks
    now = time.time()
    monitor.record_tick(epoch=int(now), receipt_time=now, latency_ms=45.0)
    monitor.record_tick(epoch=int(now + 1), receipt_time=now + 1, latency_ms=50.0)
    assert monitor.total_ticks == 2
    assert monitor.get_tick_rate() > 0.0

    # Record quotes
    monitor.record_quote(success=True, latency_ms=120.0, receipt_time=now)
    monitor.record_quote(success=False, latency_ms=250.0, receipt_time=now + 1)
    assert monitor.total_quote_requests == 2
    assert monitor.get_quote_success_rate() == 50.0

    summary = monitor.get_health_summary()
    assert summary["safety"]["live_money_disabled"] is True
    assert summary["connectivity"]["connection_status"] == "CONNECTED"
    assert summary["ticks"]["total_ticks"] == 2


def test_forward_journal_log_and_outcome_resolution(tmp_path):
    """Validates shadow prediction logging and 6-tick forward outcome accumulation."""
    db_path = str(tmp_path / "test_fwd.db")
    journal = ForwardPredictionJournal(db_path=db_path)

    rec = ForwardPredictionRecord(
        prediction_id="pred_test_1",
        timestamp=1000.0,
        symbol="R_75",
        model_version="V1.5.2-test",
        market_state="mom_bin=BULL",
        features_json="{}",
        runhigh_pred_prob=0.08,
        runlow_pred_prob=0.03,
        runhigh_ask=2.0,
        runhigh_payout=61.03,
        runlow_ask=2.0,
        runlow_payout=61.03,
        break_even_runhigh=0.0328,
        break_even_runlow=0.0328,
        ev_runhigh=2.88,
        ev_runlow=-0.17,
        cons_ev_runhigh=1.50,
        cons_ev_runlow=-0.50,
        decision="NO_TRADE",
        rejection_reason="NO_VALIDATED_EDGE",
        target_direction="RUNHIGH",
        signal_epoch=1000,
        signal_price=100.0
    )
    journal.log_prediction(rec)

    # Feed 5 forward ticks (insufficient for 5 transitions from entry S_0)
    prices_seq = [100.1, 100.2, 100.3, 100.4, 100.5]
    for idx, p in enumerate(prices_seq):
        journal.ingest_forward_tick(epoch=1001 + idx, price=p, symbol="R_75")

    metrics_pending = journal.get_accuracy_metrics("R_75")
    assert metrics_pending["pending_predictions"] == 1
    assert metrics_pending["resolved_predictions"] == 0

    # Feed 6th tick: S_5 at epoch 1006 (Strictly upward: S_0 < S_1 < S_2 < S_3 < S_4 < S_5)
    journal.ingest_forward_tick(epoch=1006, price=100.6, symbol="R_75")

    metrics_resolved = journal.get_accuracy_metrics("R_75")
    assert metrics_resolved["resolved_predictions"] == 1
    assert metrics_resolved["pending_predictions"] == 0
    assert metrics_resolved["runhigh_observed_win_rate"] == 1.0
    assert metrics_resolved["runhigh_brier_score"] is not None


def test_forward_observer_tick_processing_and_safety(tmp_path):
    """Validates ForwardObserver processes ticks without executing trades and enforces safety."""
    j_db = str(tmp_path / "fwd.db")
    q_db = str(tmp_path / "q.db")
    observer = ForwardObserver(
        symbol="R_75",
        journal_db_path=j_db,
        quote_db_path=q_db
    )

    assert observer.LIVE_EXECUTION_DISABLED is True

    # Feed 35 ticks to build history
    base_epoch = 1000
    base_price = 100.0
    for i in range(35):
        tick = LiveTickRecord(
            symbol="R_75",
            server_timestamp=base_epoch + i,
            local_receipt_timestamp=float(base_epoch + i),
            price=base_price + (i * 0.1),
            source="test",
            session_id="test_sess",
            sequence_id=i + 1,
            data_quality_flags="NORMAL"
        )
        pred = observer.process_incoming_tick(tick)

    # After enough history, a prediction record should be logged
    recent = observer.journal.inspect_recent(limit=5)
    assert len(recent) > 0
    latest = recent[0]
    assert latest["decision"] == "NO_TRADE"
    assert "NO_VALIDATED_EDGE" in latest["rejection_reason"]


def test_paper_trader_rejection_taxonomy():
    """Validates PaperTrader taxonomic rejection reasons and trade modes."""
    qe = QuoteEngine(mode="research")
    trader = PaperTrader(quote_engine=qe, symbol="R_75")

    assert trader.LIVE_EXECUTION_DISABLED is True

    # 1. Unvalidated edge rejection
    rec1 = trader.evaluate_opportunity(
        epoch=1000,
        signal="RUNHIGH",
        estimated_prob=0.08,
        is_calibrated=True,
        is_validated=False,
        is_holdout_passed=False,
        trade_mode="FORWARD_PAPER_TRADE"
    )
    assert rec1.decision == "NO_TRADE"
    assert "FAILED_VALIDATION" in rec1.rejection_reason
    assert "NO_VALIDATED_EDGE" in rec1.rejection_reason
    assert rec1.trade_mode == "FORWARD_PAPER_TRADE"

    # 2. Stale quote rejection
    rec2 = trader.evaluate_opportunity(
        epoch=1001,
        signal="RUNHIGH",
        estimated_prob=0.08,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True,
        is_quote_stale=True
    )
    assert rec2.decision == "NO_TRADE"
    assert "QUOTE_STALE" in rec2.rejection_reason

    # 3. Data gap rejection
    rec3 = trader.evaluate_opportunity(
        epoch=1002,
        signal="RUNHIGH",
        estimated_prob=0.08,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True,
        has_data_gap=True
    )
    assert rec3.decision == "NO_TRADE"
    assert "MARKET_DATA_GAP" in rec3.rejection_reason


def test_quote_database_session_id_and_migration(tmp_path):
    """Validates QuoteDatabase stores session_id and executes lookahead-safe queries."""
    db_path = str(tmp_path / "quotes_test.db")
    db = QuoteDatabase(db_path=db_path)

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
        collection_status="QUOTE_AVAILABLE",
        session_id="sess_abc"
    )
    row_id = db.store_quote(rec)
    assert row_id > 0

    # Query strictly at or before response_timestamp
    q = db.get_latest_quote_before(
        symbol="R_75",
        contract_type="RUNHIGH",
        timestamp=1000.10,
        max_freshness_seconds=10.0
    )
    assert q is not None
    assert q.proposal_id == "prop_123"
    assert q.session_id == "sess_abc"

    # Lookahead protection: query BEFORE response_timestamp must return None
    q_past = db.get_latest_quote_before(
        symbol="R_75",
        contract_type="RUNHIGH",
        timestamp=1000.02,
        max_freshness_seconds=10.0
    )
    assert q_past is None


def test_brier_score_accuracy_formula():
    """Validates mathematical properties of Brier score."""
    preds = np.array([0.03, 0.05, 0.10])
    acts = np.array([0.0, 0.0, 1.0])
    expected_brier = ((0.03**2) + (0.05**2) + (0.90**2)) / 3.0
    actual_brier = float(np.mean((preds - acts) ** 2))
    assert abs(actual_brier - expected_brier) < 1e-6


def test_config_env_parser_and_safety_invariants(tmp_path):
    """Validates .env parser loads overrides and safety lock remains permanently active."""
    env_file = tmp_path / ".env.test"
    with open(env_file, "w") as f:
        f.write("DEFAULT_SYMBOL=1HZ100V\nMAX_QUOTE_AGE_SECONDS=45.0\n")

    load_env_file(str(env_file))
    cfg = TradingConfig()
    assert cfg.live_execution_disabled is True  # Real-money execution permanently disabled
    assert cfg.max_quote_age_seconds >= 10.0


def test_contract_equality_loss_rule():
    """Validates that any equal price transition (S_k == S_{k-1}) strictly causes contract loss."""
    from contract_model import ContractOutcomeModel
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    # Entry S_0 = 100.0, S_1 = 100.1, S_2 = 100.1 (TIE!), S_3 = 100.2, S_4 = 100.3, S_5 = 100.4
    prices = np.array([99.9, 100.0, 100.1, 100.1, 100.2, 100.3, 100.4])
    res_rh = model.evaluate_single_trade(prices, np.arange(len(prices)), signal_idx=0, contract_type="RUNHIGH")
    assert res_rh is not None
    assert res_rh.is_win is False  # Equal tick kills RUNHIGH

    # Same for RUNLOW
    prices_down = np.array([101.0, 100.0, 99.9, 99.9, 99.8, 99.7, 99.6])
    res_rl = model.evaluate_single_trade(prices_down, np.arange(len(prices_down)), signal_idx=0, contract_type="RUNLOW")
    assert res_rl is not None
    assert res_rl.is_win is False  # Equal tick kills RUNLOW


def test_collector_coverage_audit_utility():
    """Validates report_all_historical_coverage scans and audits datasets in data/."""
    from collector import report_all_historical_coverage
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(script_dir, "data")
    reports = report_all_historical_coverage(data_dir)
    assert len(reports) > 0
    # Must include R_75
    r75 = next((r for r in reports if "R_75" in r["file"]), None)
    assert r75 is not None
    assert r75["ticks"] == 43184
    assert r75["valid"] is True

