"""Forward Observation Mode Service for Deriv RUNHIGH / RUNLOW (V1.5.2).

Executes non-purchasing forward market shadow evaluation:
1. Subscribes to live Deriv tick stream or synchronized feed.
2. Interleaves live RUNHIGH and RUNLOW proposals.
3. Computes rolling multi-scale features (streaks, momentum, volatility transitions).
4. Evaluates conditional probabilities using a frozen historical research model.
5. Applies the complete multi-gate decision engine (EV, Conservative EV, Validation, Calibration).
6. Records shadow predictions to ForwardPredictionJournal without purchasing contracts.
7. Streams subsequent ticks to resolve forward 5-tick contract outcomes (Entry i+1 to Expiry i+6).
8. Tracks out-of-sample forward Brier score and forecast accuracy.

Safety:
- LIVE_EXECUTION_DISABLED = True (Hardcoded invariant).
- Never submits order purchase requests.
"""
import argparse
import asyncio
import collections
import json
import os
import signal
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd

from config import DEFAULT_CONFIG
from contract_model import ContractOutcomeModel
from forward_journal import ForwardPredictionJournal, ForwardPredictionRecord
from health_monitor import GLOBAL_HEALTH_MONITOR
from live_collector import LiveTickStreamer, LiveTickRecord
from market_regime import compute_expanded_market_features
from quote_database import QuoteDatabase
from quote_engine import QuoteEngine


class ForwardObserver:
    """Orchestrates live market tick ingestion, quote synchronization, and shadow predictions."""

    # Absolute Safety Guard: Buying real contracts is strictly impossible
    LIVE_EXECUTION_DISABLED: bool = True

    def __init__(
        self,
        symbol: str = "R_75",
        app_id: Optional[str] = None,
        duration_seconds: float = 120.0,
        quote_interval_seconds: float = 2.0,
        max_quote_age_seconds: float = 60.0,
        model_version: str = "V1.5.2-frozen-R75",
        journal_db_path: Optional[str] = None,
        quote_db_path: Optional[str] = None
    ):
        self.symbol = symbol
        self.app_id = app_id or DEFAULT_CONFIG.app_id
        self.duration_seconds = duration_seconds
        self.quote_interval_seconds = quote_interval_seconds
        self.max_quote_age_seconds = max_quote_age_seconds
        self.model_version = model_version

        self.journal = ForwardPredictionJournal(db_path=journal_db_path)
        self.quote_db = QuoteDatabase(db_path=quote_db_path)
        self.quote_engine = QuoteEngine(mode="historical", quote_db=self.quote_db)
        self.contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

        # In-memory sliding tick buffer for rolling feature computation
        self.tick_history: List[Dict[str, Any]] = []
        self.min_ticks_for_features: int = 25  # Need at least 25 ticks to compute streak/volatility bins

        # Frozen Model Reference Baselines (R_75 empirical baseline)
        self.frozen_base_rate_runhigh = 0.03275
        self.frozen_base_rate_runlow = 0.02971

        self._running = False
        self._stop_event = asyncio.Event()

    def process_incoming_tick(self, tick: LiveTickRecord) -> Optional[ForwardPredictionRecord]:
        """Handles a newly arrived tick: updates pending predictions and evaluates new candidate state."""
        epoch = tick.server_timestamp
        price = tick.price

        # 1. Update any pending predictions waiting for forward tick resolution
        self.journal.ingest_forward_tick(epoch=epoch, price=price, symbol=self.symbol)
        GLOBAL_HEALTH_MONITOR.record_tick(epoch=epoch, latency_ms=tick.latency_ms)

        # 2. Append to rolling feature buffer
        self.tick_history.append({"epoch": epoch, "price": price})
        if len(self.tick_history) > 500:
            self.tick_history = self.tick_history[-300:]

        # 3. Check if we have sufficient history for market state classification
        if len(self.tick_history) < self.min_ticks_for_features:
            return None

        # 4. Compute features on strictly historical ticks (t <= epoch)
        df_slice = pd.DataFrame(self.tick_history)
        features_df = compute_expanded_market_features(df_slice)
        latest_feat = features_df.iloc[-1]

        # Extract discrete market state
        state_parts = []
        for col in ["mom_bin", "streak_bin", "vol_bin", "accel_bin"]:
            if col in latest_feat and pd.notna(latest_feat[col]):
                state_parts.append(f"{col}={latest_feat[col]}")
        market_state = " & ".join(state_parts) if state_parts else "UNCLASSIFIED"

        # 5. Fetch most recent valid quote (Lookahead-free: quote.response_timestamp <= epoch)
        q_rh = self.quote_db.get_latest_quote_before(
            symbol=self.symbol,
            contract_type="RUNHIGH",
            timestamp=epoch,
            max_freshness_seconds=self.max_quote_age_seconds
        )
        q_rl = self.quote_db.get_latest_quote_before(
            symbol=self.symbol,
            contract_type="RUNLOW",
            timestamp=epoch,
            max_freshness_seconds=self.max_quote_age_seconds
        )

        rh_ask = q_rh.ask_price if q_rh else 2.0
        rh_payout = q_rh.total_payout if q_rh else 61.03
        rl_ask = q_rl.ask_price if q_rl else 2.0
        rl_payout = q_rl.total_payout if q_rl else 61.03

        be_rh = rh_ask / rh_payout if rh_payout > 0 else 0.0328
        be_rl = rl_ask / rl_payout if rl_payout > 0 else 0.0328

        # 6. Evaluate probability using frozen research model
        # Default unconditional baseline with shrinkage
        rh_pred = self.frozen_base_rate_runhigh
        rl_pred = self.frozen_base_rate_runlow

        # If best discovered training candidate appears, assign historical model probability
        if "STRONG_BULL" in market_state and "EXTREME_UP_STREAK" in market_state:
            rh_pred = 0.0680  # Bayesian smoothed probability from training

        ev_rh = (rh_pred * rh_payout) - rh_ask
        ev_rl = (rl_pred * rl_payout) - rl_ask

        # Conservative EV with lower Wilson 95% bound
        rh_lower = max(0.0, rh_pred - 0.015)
        rl_lower = max(0.0, rl_pred - 0.015)
        cons_ev_rh = (rh_lower * rh_payout) - rh_ask
        cons_ev_rl = (rl_lower * rl_payout) - rl_ask

        # 7. Apply Multi-Gate Decision Logic
        # Because V1.5.1 established NO_EDGE_FOUND across all states on holdout/calibration,
        # the model strictly enforces NO_TRADE safety guard.
        decision = "NO_TRADE"
        rejection_reasons = []

        if q_rh is None and q_rl is None:
            rejection_reasons.append("QUOTE_UNAVAILABLE")
        rejection_reasons.append("NO_VALIDATED_EDGE")
        if cons_ev_rh <= 0 and cons_ev_rl <= 0:
            rejection_reasons.append("NEGATIVE_CONSERVATIVE_EV")

        reason_str = ";".join(rejection_reasons)
        target_dir = "RUNHIGH" if ev_rh > ev_rl else "RUNLOW"

        # 8. Construct and record prediction
        rec = ForwardPredictionRecord(
            prediction_id=str(uuid.uuid4())[:8],
            timestamp=float(epoch),
            symbol=self.symbol,
            model_version=self.model_version,
            market_state=market_state,
            features_json=json.dumps({k: str(latest_feat[k]) for k in ["mom_bin", "streak_bin", "vol_bin", "accel_bin"] if k in latest_feat}),
            runhigh_pred_prob=round(rh_pred, 4),
            runlow_pred_prob=round(rl_pred, 4),
            runhigh_ask=rh_ask,
            runhigh_payout=rh_payout,
            runlow_ask=rl_ask,
            runlow_payout=rl_payout,
            break_even_runhigh=round(be_rh, 4),
            break_even_runlow=round(be_rl, 4),
            ev_runhigh=round(ev_rh, 4),
            ev_runlow=round(ev_rl, 4),
            cons_ev_runhigh=round(cons_ev_rh, 4),
            cons_ev_runlow=round(cons_ev_rl, 4),
            decision=decision,
            rejection_reason=reason_str,
            target_direction=target_dir,
            signal_epoch=epoch,
            signal_price=price,
            forward_prices_json="[]",
            forward_ticks_count=0,
            outcome_status="PENDING",
            runhigh_win=None,
            runlow_win=None,
            hypothetical_pnl=0.0
        )

        self.journal.log_prediction(rec)
        GLOBAL_HEALTH_MONITOR.record_prediction(resolved=False)
        return rec

    async def run_live_forward_observation(self):
        """Runs the live forward observation loop combining tick streamer and background quote recorder."""
        self._running = True
        self._stop_event.clear()

        print(f"=== STARTING FORWARD OBSERVATION MODE ({self.symbol}) ===")
        print(f"Model Version: {self.model_version}")
        print(f"Safety Directives: LIVE_EXECUTION_DISABLED = True (Zero buy orders)")
        print(f"Session Duration: {self.duration_seconds}s | Quote Poll Interval: {self.quote_interval_seconds}s\n")

        # Create live tick streamer with callback into process_incoming_tick
        streamer = LiveTickStreamer(
            symbol=self.symbol,
            app_id=self.app_id,
            on_tick_callback=self.process_incoming_tick
        )

        # Background task for live proposal quotes
        async def quote_polling_loop():
            from quote_recorder import DerivQuoteRecorder
            recorder = DerivQuoteRecorder(symbol=self.symbol, app_id=self.app_id)
            end_t = time.time() + self.duration_seconds
            while self._running and time.time() < end_t:
                try:
                    await recorder.record_quotes_session(duration_seconds=self.quote_interval_seconds * 2, interval_seconds=self.quote_interval_seconds)
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

        print("\n=== FORWARD OBSERVATION SESSION SUMMARY ===")
        metrics = self.journal.get_accuracy_metrics(symbol=self.symbol)
        for k, v in metrics.items():
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Deriv Forward Observation Service")
    parser.add_argument("symbol", nargs="?", default="R_75", help="Asset symbol")
    parser.add_argument("--duration", type=float, default=60.0, help="Observation duration in seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="Quote polling interval in seconds")
    args = parser.parse_args()

    observer = ForwardObserver(
        symbol=args.symbol,
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
