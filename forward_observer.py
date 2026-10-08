"""Forward Observation Mode Service for Deriv RUNHIGH / RUNLOW (V1.6.1).

Executes live, non-purchasing forward market observation:
1. Subscribes to live Deriv tick stream or synchronized feed.
2. Interleaves live RUNHIGH and RUNLOW proposals with strict timestamp auditing.
3. Computes rolling multi-scale features with verified feature parity (feature_schema.py).
4. Evaluates conditional probabilities using a verified frozen ModelArtifact (via ModelManager).
   NO hard-coded probability placeholders.
5. Prohibits all benchmark quote fallbacks ($2 -> $61.03): missing quotes return QUOTE_UNAVAILABLE with null EV.
6. Strictly requires model-derived uncertainty bound for conservative EV (NO arbitrary -0.015 fallbacks).
7. Wires persistent institutional risk management into centralized decision gate.
8. Applies multi-gate decision engine across explicit modes:
   - DATA_COLLECTION_ONLY: Records ticks and quotes, skips predictions.
   - SHADOW: Generates predictions using research models, logs to journal, strictly non-trading.
     Predictions are persisted EVEN when proposal quotes are temporarily unavailable.
   - PAPER: Simulates trading opportunities only when qualified by an approved model and genuine quotes.
9. Streams subsequent ticks to resolve forward 5-tick contract outcomes without lookahead.
10. Distinguishes reconstructed canonical outcomes from unverified sequences (OUTCOME_RECONSTRUCTED, OUTCOME_DATA_GAP, OUTCOME_INCOMPLETE).

Safety Directives:
- LIVE_EXECUTION_DISABLED = True (Hardcoded invariant).
- Real-money purchases are strictly disabled across all execution paths.
"""
import argparse
import asyncio
import collections
import json
import math
import os
import signal
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG
from contract_model import ContractOutcomeModel
from feature_schema import (
    FEATURE_SCHEMA_VERSION,
    CANONICAL_FEATURE_LOOKBACK,
    extract_discrete_market_state
)
from forward_journal import (
    ForwardPredictionJournal,
    ForwardPredictionRecord,
    STATUS_PENDING,
    STATUS_INCOMPLETE
)
from health_monitor import GLOBAL_HEALTH_MONITOR
from live_collector import LiveTickStreamer, LiveTickRecord
from model_artifact import ModelArtifact, ModelStatus
from model_manager import ModelManager
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine
from risk import RiskManager, DEFAULT_RISK_DB


class ForwardObserver:
    """Orchestrates live market tick ingestion, quote synchronization, frozen model inference, and shadow journaling."""

    # Absolute Safety Guard: Buying real contracts is strictly impossible
    LIVE_EXECUTION_DISABLED: bool = True

    def __init__(
        self,
        symbol: str = "R_75",
        mode: str = "SHADOW",  # 'DATA_COLLECTION_ONLY', 'SHADOW', 'PAPER'
        model_path_or_id: Optional[str] = None,
        app_id: Optional[str] = None,
        duration_seconds: float = 120.0,
        quote_interval_seconds: float = 2.0,
        max_quote_age_seconds: float = 60.0,
        model_version: str = "V1.6.1",
        journal_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None,
        session_id: str = "",
        risk_db_path: Optional[str] = None
    ):
        self.symbol = symbol
        self.mode = mode.upper()
        if self.mode not in ("DATA_COLLECTION_ONLY", "SHADOW", "PAPER"):
            self.mode = "SHADOW"

        self.app_id = app_id or DEFAULT_CONFIG.app_id
        self.duration_seconds = duration_seconds
        self.quote_interval_seconds = quote_interval_seconds
        self.max_quote_age_seconds = max_quote_age_seconds
        self.model_version = model_version
        self.session_id = session_id or str(uuid.uuid4())

        self.journal = ForwardPredictionJournal(db_path=journal_db_path, enforce_session_id=True)
        self.quote_db = QuoteDatabase(db_path=quote_db_path)
        self.quote_engine = QuoteEngine(mode="real_quotes_only", quote_db=self.quote_db, allow_benchmark_fallback=False)
        self.contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
        self.risk_manager = RiskManager(db_path=risk_db_path or DEFAULT_RISK_DB, symbol=self.symbol)

        # In-memory sliding tick buffer for rolling feature computation
        self.tick_history: List[Dict[str, Any]] = []
        self.min_ticks_for_features: int = CANONICAL_FEATURE_LOOKBACK
        self.warmup_ticks_count: int = 0
        self.live_ticks_count: int = 0

        # Model Manager & Frozen Model Loading
        self.model_manager = ModelManager()
        self.model_artifact: Optional[ModelArtifact] = None
        self.model_status_code: str = "MODEL_NOT_LOADED"

        if self.mode in ("SHADOW", "PAPER"):
            self._init_frozen_model(model_path_or_id)

        self._running = False
        self._stop_event = asyncio.Event()

    def _init_frozen_model(self, model_path_or_id: Optional[str]):
        """Discovers, validates, and loads the frozen prediction model."""
        target_model = model_path_or_id
        if not target_model:
            target_model = self.model_manager.get_latest_model_for_symbol(self.symbol)

        if not target_model:
            # Check if training data exists to produce an initial frozen research model
            script_dir = os.path.dirname(os.path.abspath(__file__))
            master_csv = os.path.join(script_dir, "data", f"{self.symbol}_master.csv")
            ticks_csv = os.path.join(script_dir, "data", f"{self.symbol}_ticks.csv")
            csv_cand = master_csv if os.path.exists(master_csv) else (ticks_csv if os.path.exists(ticks_csv) else None)
            if csv_cand:
                try:
                    self.model_manager.train_and_export_baseline_model(
                        csv_path=csv_cand,
                        symbol=self.symbol,
                        approval_status=ModelStatus.RESEARCH_ONLY
                    )
                    target_model = self.model_manager.get_latest_model_for_symbol(self.symbol)
                except Exception:
                    pass

        if not target_model:
            self.model_status_code = "MODEL_NOT_FOUND"
            return

        is_valid, code, artifact = self.model_manager.validate_and_load_model(
            model_path_or_id=target_model,
            expected_symbol=self.symbol,
            expected_contract_family="RUNHIGH_RUNLOW",
            expected_duration_ticks=5,
            require_paper_approval=(self.mode == "PAPER")
        )

        self.model_status_code = code
        if is_valid or (code == "MODEL_UNVALIDATED" and self.mode == "SHADOW"):
            self.model_artifact = artifact
            if artifact:
                self.model_version = f"{artifact.model_id} ({artifact.model_version})"

    def process_incoming_tick(self, tick: LiveTickRecord) -> Optional[ForwardPredictionRecord]:
        """Handles a newly arrived tick: updates pending predictions and evaluates new candidate state."""
        epoch = int(tick.server_timestamp)
        price = float(tick.price)

        # 1. Update any pending predictions waiting for forward tick resolution
        self.journal.ingest_forward_tick(epoch=epoch, price=price, symbol=self.symbol)
        GLOBAL_HEALTH_MONITOR.record_tick(epoch=epoch, latency_ms=tick.latency_ms)

        # 2. Append to rolling feature buffer
        self.tick_history.append({"epoch": epoch, "price": price})
        if len(self.tick_history) > 500:
            self.tick_history = self.tick_history[-300:]

        # If DATA_COLLECTION_ONLY, we only collect data and resolve forward ticks
        if self.mode == "DATA_COLLECTION_ONLY":
            return None

        # 3. Check if we have sufficient history for market state classification
        if len(self.tick_history) < self.min_ticks_for_features:
            self.warmup_ticks_count += 1
            return None

        self.live_ticks_count += 1

        # 4. Compute features on strictly historical ticks with verified parity
        feat_dict, market_state = extract_discrete_market_state(self.tick_history)
        if market_state in ("INSUFFICIENT_TICKS", "UNCLASSIFIED"):
            return None

        # 5. Fetch most recent valid quote (Lookahead-free: quote.response_timestamp <= epoch)
        q_rh = self.quote_db.get_latest_quote_before(
            symbol=self.symbol,
            contract_type="RUNHIGH",
            timestamp=float(epoch),
            max_freshness_seconds=self.max_quote_age_seconds
        )
        q_rl = self.quote_db.get_latest_quote_before(
            symbol=self.symbol,
            contract_type="RUNLOW",
            timestamp=float(epoch),
            max_freshness_seconds=self.max_quote_age_seconds
        )

        # 6. Evaluate probability strictly from Frozen Model (NO hardcoded values)
        rh_pred: Optional[float] = None
        rl_pred: Optional[float] = None
        rh_lower: Optional[float] = None
        rl_lower: Optional[float] = None

        if self.model_artifact is not None:
            rh_p, rl_p, pred_meta = self.model_artifact.predict_probabilities(market_state)
            rh_pred = float(rh_p)
            rl_pred = float(rl_p)
            rh_lower = pred_meta.get("lower_bound_runhigh")
            rl_lower = pred_meta.get("lower_bound_runlow")
        else:
            # Strictly NO fallback probabilities!
            rh_pred = None
            rl_pred = None
            rh_lower = None
            rl_lower = None

        # 7. Quote Validation & Financial Metric Calculation (NO benchmark fallbacks, NO arbitrary conservative EV fallbacks)
        rh_ask: Optional[float] = None
        rh_payout: Optional[float] = None
        rl_ask: Optional[float] = None
        rl_payout: Optional[float] = None
        be_rh: Optional[float] = None
        be_rl: Optional[float] = None
        ev_rh: Optional[float] = None
        ev_rl: Optional[float] = None
        cons_ev_rh: Optional[float] = None
        cons_ev_rl: Optional[float] = None

        if q_rh is not None and q_rh.ask_price > 0 and q_rh.total_payout > 0:
            rh_ask = float(q_rh.ask_price)
            rh_payout = float(q_rh.total_payout)
            be_rh = rh_ask / rh_payout
            if rh_pred is not None:
                ev_rh = (rh_pred * rh_payout) - rh_ask
                # V1.6.1: Strictly require genuine model lower bound — NO arbitrary -0.015 fallback
                if rh_lower is not None and not math.isnan(rh_lower) and rh_lower > 0:
                    cons_ev_rh = (rh_lower * rh_payout) - rh_ask
                else:
                    cons_ev_rh = None

        if q_rl is not None and q_rl.ask_price > 0 and q_rl.total_payout > 0:
            rl_ask = float(q_rl.ask_price)
            rl_payout = float(q_rl.total_payout)
            be_rl = rl_ask / rl_payout
            if rl_pred is not None:
                ev_rl = (rl_pred * rl_payout) - rl_ask
                # V1.6.1: Strictly require genuine model lower bound — NO arbitrary -0.015 fallback
                if rl_lower is not None and not math.isnan(rl_lower) and rl_lower > 0:
                    cons_ev_rl = (rl_lower * rl_payout) - rl_ask
                else:
                    cons_ev_rl = None

        # 8. Query real persistent risk state (V1.6.1 Section 6)
        risk_snap = self.risk_manager.get_state(tick_idx=len(self.tick_history), epoch=epoch)

        # 9. Apply Centralized Multi-Gate Decision Logic
        from decision_gate import evaluate_paper_trade_eligibility, DecisionReason

        gate_rh = evaluate_paper_trade_eligibility(
            symbol=self.symbol,
            contract_type="RUNHIGH",
            duration_ticks=5,
            model_artifact=self.model_artifact,
            estimated_prob=rh_pred,
            lower_prob_bound=rh_lower,
            ask_price=rh_ask,
            total_payout=rh_payout,
            quote_epoch=getattr(q_rh, "response_timestamp", None) if q_rh else None,
            current_epoch=float(epoch),
            execution_mode=self.mode,
            market_state=market_state,
            min_expected_ev=DEFAULT_CONFIG.min_expected_ev,
            min_conservative_ev=DEFAULT_CONFIG.min_conservative_ev,
            min_probability_margin=DEFAULT_CONFIG.min_probability_margin,
            max_quote_age_seconds=self.max_quote_age_seconds,
            min_validation_sample=DEFAULT_CONFIG.min_validation_sample,
            current_stake=rh_ask or DEFAULT_CONFIG.default_stake,
            max_stake=DEFAULT_CONFIG.max_stake,
            has_data_gap=GLOBAL_HEALTH_MONITOR.has_active_data_gap(),
            quote_record=q_rh,
            is_risk_state_available=self.risk_manager.is_valid(),
            is_in_cooldown=risk_snap.is_paused,
            outstanding_positions_count=risk_snap.outstanding_positions_count,
            current_exposure=risk_snap.current_exposure,
            current_daily_pnl=risk_snap.daily_pnl,
            current_consecutive_losses=risk_snap.consecutive_losses,
            current_daily_drawdown_pct=risk_snap.max_drawdown_pct
        )

        gate_rl = evaluate_paper_trade_eligibility(
            symbol=self.symbol,
            contract_type="RUNLOW",
            duration_ticks=5,
            model_artifact=self.model_artifact,
            estimated_prob=rl_pred,
            lower_prob_bound=rl_lower,
            ask_price=rl_ask,
            total_payout=rl_payout,
            quote_epoch=getattr(q_rl, "response_timestamp", None) if q_rl else None,
            current_epoch=float(epoch),
            execution_mode=self.mode,
            market_state=market_state,
            min_expected_ev=DEFAULT_CONFIG.min_expected_ev,
            min_conservative_ev=DEFAULT_CONFIG.min_conservative_ev,
            min_probability_margin=DEFAULT_CONFIG.min_probability_margin,
            max_quote_age_seconds=self.max_quote_age_seconds,
            min_validation_sample=DEFAULT_CONFIG.min_validation_sample,
            current_stake=rl_ask or DEFAULT_CONFIG.default_stake,
            max_stake=DEFAULT_CONFIG.max_stake,
            has_data_gap=GLOBAL_HEALTH_MONITOR.has_active_data_gap(),
            quote_record=q_rl,
            is_risk_state_available=self.risk_manager.is_valid(),
            is_in_cooldown=risk_snap.is_paused,
            outstanding_positions_count=risk_snap.outstanding_positions_count,
            current_exposure=risk_snap.current_exposure,
            current_daily_pnl=risk_snap.daily_pnl,
            current_consecutive_losses=risk_snap.consecutive_losses,
            current_daily_drawdown_pct=risk_snap.max_drawdown_pct
        )

        decision = "NO_TRADE"
        target_dir = "NONE"
        reason_str = ""

        # Prioritize direction with superior conservative EV if both or either qualify
        if gate_rh.is_eligible and (not gate_rl.is_eligible or (cons_ev_rh or 0) >= (cons_ev_rl or 0)):
            decision = "PAPER_TRADE"
            target_dir = "RUNHIGH"
            reason_str = DecisionReason.PAPER_TRADE_APPROVED.value
        elif gate_rl.is_eligible:
            decision = "PAPER_TRADE"
            target_dir = "RUNLOW"
            reason_str = DecisionReason.PAPER_TRADE_APPROVED.value
        else:
            decision = "NO_TRADE"
            if ev_rh is not None and ev_rl is not None:
                target_dir = "RUNHIGH" if ev_rh > ev_rl else "RUNLOW"
            elif rh_pred is not None and rl_pred is not None:
                target_dir = "RUNHIGH" if rh_pred > rl_pred else "RUNLOW"
            else:
                target_dir = "NONE"

            combined_reasons = []
            for r in gate_rh.rejection_reasons + gate_rl.rejection_reasons:
                if r not in combined_reasons:
                    combined_reasons.append(r)
            reason_str = ";".join(combined_reasons) if combined_reasons else DecisionReason.NO_TRADE.value

        # 10. Construct and record prediction (SHADOW predictions recorded even if quotes are absent)
        rec = ForwardPredictionRecord(
            prediction_id=str(uuid.uuid4())[:8],
            session_id=self.session_id,
            timestamp=float(epoch),
            symbol=self.symbol,
            model_version=self.model_version,
            market_state=market_state,
            features_json=json.dumps(feat_dict),
            runhigh_pred_prob=round(rh_pred, 5) if rh_pred is not None else None,
            runlow_pred_prob=round(rl_pred, 5) if rl_pred is not None else None,
            runhigh_ask=round(rh_ask, 2) if rh_ask is not None else None,
            runhigh_payout=round(rh_payout, 2) if rh_payout is not None else None,
            runlow_ask=round(rl_ask, 2) if rl_ask is not None else None,
            runlow_payout=round(rl_payout, 2) if rl_payout is not None else None,
            break_even_runhigh=round(be_rh, 5) if be_rh is not None else None,
            break_even_runlow=round(be_rl, 5) if be_rl is not None else None,
            ev_runhigh=round(ev_rh, 4) if ev_rh is not None else None,
            ev_runlow=round(ev_rl, 4) if ev_rl is not None else None,
            cons_ev_runhigh=round(cons_ev_rh, 4) if cons_ev_rh is not None else None,
            cons_ev_runlow=round(cons_ev_rl, 4) if cons_ev_rl is not None else None,
            decision=decision,
            rejection_reason=reason_str,
            target_direction=target_dir,
            signal_epoch=epoch,
            signal_price=price,
            forward_prices_json="[]",
            forward_ticks_count=0,
            outcome_status=STATUS_PENDING,
            runhigh_win=None,
            runlow_win=None,
            hypothetical_pnl=0.0,
            execution_mode=self.mode,
            model_id=self.model_artifact.model_id if self.model_artifact else "NONE",
            feature_schema_version=FEATURE_SCHEMA_VERSION
        )

        self.journal.log_prediction(rec)
        GLOBAL_HEALTH_MONITOR.record_prediction(resolved=False)
        return rec

    async def run_live_forward_observation(self):
        """Runs the live forward observation loop combining tick streamer and background quote recorder."""
        self._running = True
        self._stop_event.clear()

        print(f"\n=== STARTING FORWARD OBSERVATION ({self.symbol}) ===")
        print(f"Session ID:        {self.session_id[:8]}")
        print(f"Mode:              {self.mode}")
        print(f"Model ID / Ver:    {self.model_version}")
        print(f"Model Load Status: {self.model_status_code}")
        print(f"Safety Guard:      LIVE_EXECUTION_DISABLED = True (Zero buy orders)")
        print(f"Session Duration:  {self.duration_seconds}s | Quote Poll Interval: {self.quote_interval_seconds}s\n")

        # Create live tick streamer with callback into process_incoming_tick
        streamer = LiveTickStreamer(
            symbol=self.symbol,
            app_id=self.app_id,
            on_tick_callback=self.process_incoming_tick,
            session_id=self.session_id
        )

        # Background task for live proposal quotes
        async def quote_polling_loop():
            from quote_recorder import DerivQuoteRecorder
            recorder = DerivQuoteRecorder(
                symbol=self.symbol,
                app_id=self.app_id,
                session_id=self.session_id
            )
            end_t = time.time() + self.duration_seconds
            while self._running and time.time() < end_t:
                try:
                    await recorder.record_quotes_session(
                        duration_seconds=self.quote_interval_seconds * 2,
                        interval_seconds=self.quote_interval_seconds
                    )
                except Exception:
                    pass
                await asyncio.sleep(self.quote_interval_seconds)

        quote_task = asyncio.create_task(quote_polling_loop())

        try:
            await streamer.run_streaming_session(duration_seconds=self.duration_seconds)
        finally:
            self._running = False
            quote_task.cancel()
            streamer.stop()
            # Mark incomplete observations as OUTCOME_INCOMPLETE
            self.journal.mark_incomplete_as_unverified(symbol=self.symbol, target_status=STATUS_INCOMPLETE)

        print("\n=== FORWARD OBSERVATION SESSION SUMMARY ===")
        metrics = self.journal.get_accuracy_metrics(symbol=self.symbol)
        for k, v in metrics.items():
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Deriv Forward Observation Service (V1.6.1)")
    parser.add_argument("symbol", nargs="?", default="R_75", help="Asset symbol")
    parser.add_argument("--mode", default="SHADOW", choices=["DATA_COLLECTION_ONLY", "SHADOW", "PAPER"], help="Observation execution mode")
    parser.add_argument("--model", default=None, help="Path or ID of frozen model artifact")
    parser.add_argument("--duration", type=float, default=60.0, help="Observation duration in seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="Quote polling interval in seconds")
    args = parser.parse_args()

    observer = ForwardObserver(
        symbol=args.symbol,
        mode=args.mode,
        model_path_or_id=args.model,
        duration_seconds=args.duration,
        quote_interval_seconds=args.interval
    )

    def handle_sig(sig, frame):
        print("\nShutdown signal received. Stopping observer...")
        observer._running = False

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        asyncio.run(observer.run_live_forward_observation())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
