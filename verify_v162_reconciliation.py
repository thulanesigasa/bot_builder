"""V1.6.2 Verification Script: Multi-Session Offline Reconciliation and Reporting.

Demonstrates and verifies:
1. Two independent sessions created with unique session IDs.
2. Distinct ticks, quotes, predictions, and outcomes logged and attributed per session.
3. Strict referential integrity and isolation between sessions.
4. Automated reconciliation execution via SessionReconciler.
5. Generation of session-specific Markdown reports.
"""
import os
import sys
import time
import json
import uuid
import tempfile
from datetime import datetime, timezone

from forward_session import (
    ForwardSessionRegistry, STATUS_ACTIVE, STATUS_COMPLETED,
    RECON_STATUS_RECONCILED
)
from forward_journal import (
    ForwardPredictionJournal, ForwardPredictionRecord,
    STATUS_RESOLVED, STATUS_VERIFIED
)
from quote_database import QuoteDatabase
from quote_recorder import ProposalRecord
from session_reconciler import SessionReconciler
from session_reporter import SessionReporter

def run_two_session_reconciliation_verification():
    print("=" * 70)
    print("V1.6.2 DETERMINISTIC TWO-SESSION RECONCILIATION VERIFICATION")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp(prefix="v162_recon_")
    s_db = os.path.join(temp_dir, "sessions.db")
    j_db = os.path.join(temp_dir, "forward_predictions.db")
    q_db = os.path.join(temp_dir, "quotes.db")

    reg = ForwardSessionRegistry(db_path=s_db)
    journal = ForwardPredictionJournal(db_path=j_db, enforce_session_id=True)
    quotes = QuoteDatabase(db_path=q_db)

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION 1: SHADOW-ALPHA
    # ─────────────────────────────────────────────────────────────────────────
    csv_1 = os.path.join(temp_dir, "session_alpha_ticks.csv")
    sess_1 = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_DISCRETE_NB",
        model_version="1.0.0",
        planned_duration_seconds=1800.0,
        journal_db_path=j_db,
        quote_db_path=q_db,
        live_ticks_csv=csv_1,
        notes="Session Alpha Deterministic Run"
    )
    s1_id = sess_1.session_id
    print(f"\n[+] Created Session Alpha: {s1_id}")

    # Log 2 quotes for Session Alpha
    t0 = 1710000000.0
    quotes.store_quote(ProposalRecord(
        request_timestamp=t0 - 1.0,
        response_timestamp=t0 - 0.5,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.0,
        potential_net_profit=59.0,
        currency="USD",
        proposal_id=f"q_alpha_1",
        quote_source="live_proposal",
        quote_latency_ms=45.0,
        collection_status="QUOTE_AVAILABLE",
        session_id=s1_id
    ))
    quotes.store_quote(ProposalRecord(
        request_timestamp=t0 + 29.0,
        response_timestamp=t0 + 29.5,
        market_symbol="R_75",
        contract_type="RUNLOW",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.0,
        potential_net_profit=59.0,
        currency="USD",
        proposal_id=f"q_alpha_2",
        quote_source="live_proposal",
        quote_latency_ms=42.0,
        collection_status="QUOTE_AVAILABLE",
        session_id=s1_id
    ))

    # Log Prediction 1 for Session Alpha
    p1 = ForwardPredictionRecord(
        prediction_id=f"pred_alpha_001",
        timestamp=t0,
        symbol="R_75",
        model_version="1.0.0",
        market_state="COMPRESSED",
        features_json='{"volatility": 0.0012, "spread": 0.05}',
        session_id=s1_id,
        runhigh_pred_prob=0.065,
        runlow_pred_prob=0.021,
        runhigh_ask=2.0,
        runhigh_payout=61.0,
        break_even_runhigh=0.0328,
        ev_runhigh=1.965,
        cons_ev_runhigh=0.55,
        decision="PAPER_TRADE",
        target_direction="RUNHIGH",
        signal_epoch=int(t0),
        signal_price=1050.20,
        quote_id="q_alpha_1",
        model_id="M_DISCRETE_NB",
        source_provenance="LIVE_DERIV"
    )
    journal.log_prediction(p1)

    # Ingest 6 upward ticks for prediction 1
    for step in range(1, 7):
        journal.ingest_forward_tick(epoch=int(t0) + step, price=1050.20 + step * 0.15, symbol="R_75")

    # Log Prediction 2 for Session Alpha
    t1 = t0 + 30.0
    p2 = ForwardPredictionRecord(
        prediction_id=f"pred_alpha_002",
        timestamp=t1,
        symbol="R_75",
        model_version="1.0.0",
        market_state="EXPANDING",
        features_json='{"volatility": 0.0025, "spread": 0.08}',
        session_id=s1_id,
        runhigh_pred_prob=0.015,
        runlow_pred_prob=0.072,
        runlow_ask=2.0,
        runlow_payout=61.0,
        break_even_runlow=0.0328,
        ev_runlow=2.392,
        cons_ev_runlow=0.72,
        decision="PAPER_TRADE",
        target_direction="RUNLOW",
        signal_epoch=int(t1),
        signal_price=1051.10,
        quote_id="q_alpha_2",
        model_id="M_DISCRETE_NB",
        source_provenance="LIVE_DERIV"
    )
    journal.log_prediction(p2)

    # Ingest 6 downward ticks for prediction 2
    for step in range(1, 7):
        journal.ingest_forward_tick(epoch=int(t1) + step, price=1051.10 - step * 0.12, symbol="R_75")

    # Complete Session Alpha
    reg.complete_session(
        session_id=s1_id,
        status=STATUS_COMPLETED,
        total_ticks=50,
        live_ticks=26,
        warmup_ticks=24,
        total_predictions=2,
        resolved_predictions=2,
        notes="Clean Alpha completion"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION 2: SHADOW-BETA
    # ─────────────────────────────────────────────────────────────────────────
    csv_2 = os.path.join(temp_dir, "session_beta_ticks.csv")
    sess_2 = reg.create_session(
        symbol="R_75",
        mode="SHADOW",
        model_id="M_DISCRETE_NB",
        model_version="1.0.0",
        planned_duration_seconds=1800.0,
        journal_db_path=j_db,
        quote_db_path=q_db,
        live_ticks_csv=csv_2,
        notes="Session Beta Deterministic Run"
    )
    s2_id = sess_2.session_id
    print(f"[+] Created Session Beta : {s2_id}")

    # Log 1 quote for Session Beta
    t2 = t0 + 100.0
    quotes.store_quote(ProposalRecord(
        request_timestamp=t2 - 1.0,
        response_timestamp=t2 - 0.4,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.0,
        potential_net_profit=59.0,
        currency="USD",
        proposal_id=f"q_beta_1",
        quote_source="live_proposal",
        quote_latency_ms=40.0,
        collection_status="QUOTE_AVAILABLE",
        session_id=s2_id
    ))

    # Log 1 prediction for Session Beta (loss)
    p3 = ForwardPredictionRecord(
        prediction_id=f"pred_beta_001",
        timestamp=t2,
        symbol="R_75",
        model_version="1.0.0",
        market_state="COMPRESSED",
        features_json='{"volatility": 0.0011, "spread": 0.05}',
        session_id=s2_id,
        runhigh_pred_prob=0.045,
        runlow_pred_prob=0.018,
        runhigh_ask=2.0,
        runhigh_payout=61.0,
        break_even_runhigh=0.0328,
        ev_runhigh=0.745,
        cons_ev_runhigh=-0.20,
        decision="NO_TRADE",
        target_direction="NONE",
        signal_epoch=int(t2),
        signal_price=1049.50,
        quote_id="q_beta_1",
        model_id="M_DISCRETE_NB",
        source_provenance="LIVE_DERIV"
    )
    journal.log_prediction(p3)

    # Ingest 6 alternating ticks (loss for both RUNHIGH and RUNLOW)
    for step in range(1, 7):
        journal.ingest_forward_tick(epoch=int(t2) + step, price=1049.50 + (1 if step % 2 == 1 else -1) * 0.10, symbol="R_75")

    # Complete Session Beta
    reg.complete_session(
        session_id=s2_id,
        status=STATUS_COMPLETED,
        total_ticks=40,
        live_ticks=16,
        warmup_ticks=24,
        total_predictions=1,
        resolved_predictions=1,
        notes="Clean Beta completion"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # RECONCILIATION
    # ─────────────────────────────────────────────────────────────────────────
    reconciler = SessionReconciler(registry_db_path=s_db, journal_db_path=j_db, quote_db_path=q_db)
    
    rep_1 = reconciler.reconcile_session(s1_id)
    reg.update_reconciliation_status(s1_id, rep_1.status)
    print(f"\nReconciliation Report Alpha:")
    print(f"  Status: {rep_1.status}")
    print(f"  Verified: {rep_1.is_verified}")
    print(f"  Predictions: {rep_1.total_predictions}, Resolved: {rep_1.resolved_outcomes}, Quotes: {rep_1.quotes_linked_to_session}")
    print(f"  Issues: {rep_1.issues}")
    assert rep_1.status == RECON_STATUS_RECONCILED
    assert rep_1.is_verified is True

    rep_2 = reconciler.reconcile_session(s2_id)
    reg.update_reconciliation_status(s2_id, rep_2.status)
    print(f"\nReconciliation Report Beta:")
    print(f"  Status: {rep_2.status}")
    print(f"  Verified: {rep_2.is_verified}")
    print(f"  Predictions: {rep_2.total_predictions}, Resolved: {rep_2.resolved_outcomes}, Quotes: {rep_2.quotes_linked_to_session}")
    print(f"  Issues: {rep_2.issues}")
    assert rep_2.status == RECON_STATUS_RECONCILED
    assert rep_2.is_verified is True

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION-SPECIFIC REPORT GENERATION
    # ─────────────────────────────────────────────────────────────────────────
    reporter = SessionReporter(
        reports_dir=os.path.join(temp_dir, "reports"),
        journal=journal,
        registry=reg,
        quote_db=quotes,
        reconciler=reconciler
    )
    rep_dict_1 = reporter.generate_session_report(s1_id)
    rep_dict_2 = reporter.generate_session_report(s2_id)

    print(f"\n[+] Generated Report Alpha: {rep_dict_1.get('session', {}).get('session_id')}")
    print(f"[+] Generated Report Beta : {rep_dict_2.get('session', {}).get('session_id')}")
    print("\nAlpha Report Statistical Evidence:")
    print(json.dumps(rep_dict_1.get("statistical_evidence"), indent=2))
    print("\nBeta Report Statistical Evidence:")
    print(json.dumps(rep_dict_2.get("statistical_evidence"), indent=2))

    print("\n" + "=" * 70)
    print("[SUCCESS] ALL TWO-SESSION RECONCILIATION CHECKS PASSED DETERMINISTICALLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_two_session_reconciliation_verification()
