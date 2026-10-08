"""Sustained Forward Collection Service (V1.6).

Provides a long-running, auto-reconnecting forward observation service that:
  1. Creates and registers a new ForwardSession on startup.
  2. Instantiates ForwardObserver with that session's paths.
  3. Runs tick collection + quote recording + shadow/paper prediction in one loop.
  4. Auto-reconnects with exponential backoff on WebSocket failures.
  5. Restores all subscriptions on reconnect (ticks + proposal polling).
  6. Periodically (every N ticks or T seconds) updates session stats in the registry.
  7. Generates a session report via SessionReporter at clean shutdown.
  8. Propagates real-time data-gap state from HealthMonitor into decision gate.

Safety Directive:
  LIVE_EXECUTION_DISABLED is permanently True.
  No real-money orders are placed under any circumstances.

Usage:
    python forward_collection_service.py [symbol] [--mode SHADOW] [--duration 3600]
    python forward_collection_service.py R_75 --mode SHADOW --duration 7200
    python forward_collection_service.py R_75 --mode DATA_COLLECTION_ONLY
"""
import argparse
import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from config import DEFAULT_CONFIG
from forward_journal import ForwardPredictionJournal
from forward_observer import ForwardObserver
from forward_session import ForwardSessionRegistry, ForwardSession
from health_monitor import GLOBAL_HEALTH_MONITOR
from live_collector import LiveTickStreamer, LiveTickRecord
from model_manager import ModelManager
from session_reporter import SessionReporter


# Absolute safety constant — cannot be modified at runtime
LIVE_EXECUTION_DISABLED: bool = True


class ForwardCollectionService:
    """Long-running forward data collection and shadow prediction service."""

    STAT_FLUSH_INTERVAL_TICKS = 50   # Update registry stats every N ticks
    STAT_FLUSH_INTERVAL_SECS = 30.0  # Or every N seconds (whichever comes first)

    def __init__(
        self,
        symbol: str = "R_75",
        mode: str = "SHADOW",
        duration_seconds: Optional[float] = None,  # None = run indefinitely
        quote_interval_seconds: float = 2.0,
        max_quote_age_seconds: float = 60.0,
        app_id: Optional[str] = None,
        model_path_or_id: Optional[str] = None,
        notes: str = ""
    ):
        if LIVE_EXECUTION_DISABLED is not True:
            raise RuntimeError("Safety invariant violated: LIVE_EXECUTION_DISABLED must be True.")

        self.symbol = symbol
        self.mode = mode.upper()
        if self.mode not in ("DATA_COLLECTION_ONLY", "SHADOW", "PAPER"):
            self.mode = "SHADOW"
        self.duration_seconds = duration_seconds
        self.quote_interval_seconds = quote_interval_seconds
        self.max_quote_age_seconds = max_quote_age_seconds
        self.app_id = app_id or DEFAULT_CONFIG.app_id
        self.model_path_or_id = model_path_or_id
        self.notes = notes

        # Resolve model ID for session registration
        mgr = ModelManager()
        if model_path_or_id:
            self._model_id = os.path.basename(model_path_or_id)
            self._model_version = "user-specified"
        else:
            latest = mgr.get_latest_model_for_symbol(symbol)
            self._model_id = os.path.basename(latest) if latest else "NONE"
            self._model_version = "auto-latest"

        # Create session in registry
        self.registry = ForwardSessionRegistry()
        self.session: ForwardSession = self.registry.create_session(
            symbol=symbol,
            mode=self.mode,
            model_id=self._model_id,
            model_version=self._model_version,
            planned_duration_seconds=duration_seconds or 0.0,
            notes=notes
        )
        print(f"[Service] Session created: {self.session.session_id[:8]} | Mode: {self.mode}")

        # Components
        self.journal = ForwardPredictionJournal(db_path=self.session.journal_db_path)
        self.observer = ForwardObserver(
            symbol=symbol,
            mode=self.mode,
            model_path_or_id=model_path_or_id,
            app_id=self.app_id,
            duration_seconds=duration_seconds or 86400.0,
            quote_interval_seconds=quote_interval_seconds,
            max_quote_age_seconds=max_quote_age_seconds,
            journal_db_path=self.session.journal_db_path,
            quote_db_path=self.session.quote_db_path
        )
        self.reporter = SessionReporter(journal=self.journal, registry=self.registry)

        self._running = False
        self._stop_event = asyncio.Event()
        self._ticks_since_flush = 0
        self._last_flush_time = time.time()
        self._total_ticks = 0

    def _on_tick(self, tick: LiveTickRecord):
        """Tick callback — delegates to observer and tracks health."""
        GLOBAL_HEALTH_MONITOR.record_tick(
            epoch=int(tick.server_timestamp),
            is_duplicate=(tick.data_quality_flags == "DUPLICATE_IGNORED"),
            is_gap=(tick.data_quality_flags == "GAP_DETECTED"),
            latency_ms=tick.latency_ms
        )

        if tick.data_quality_flags == "DUPLICATE_IGNORED":
            return

        # Propagate real gap state into observer for decision gate
        self.observer.process_incoming_tick(tick)

        self._total_ticks += 1
        self._ticks_since_flush += 1

        # Periodic stat flush to registry
        now = time.time()
        if (self._ticks_since_flush >= self.STAT_FLUSH_INTERVAL_TICKS or
                now - self._last_flush_time >= self.STAT_FLUSH_INTERVAL_SECS):
            self._flush_stats()

    def _flush_stats(self):
        """Writes current session metrics to the registry."""
        metrics = self.journal.get_accuracy_metrics(symbol=self.symbol)
        pnl = metrics.get("cumulative_pnl", 0.0) or 0.0
        self.registry.update_session_stats(
            session_id=self.session.session_id,
            total_ticks=self._total_ticks,
            total_predictions=metrics.get("total_predictions", 0),
            resolved_predictions=metrics.get("resolved_predictions", 0),
            unverified_predictions=metrics.get("unverified_predictions", 0),
            cumulative_pnl=pnl
        )
        self._ticks_since_flush = 0
        self._last_flush_time = time.time()

    async def _quote_polling_loop(self):
        """Background task polling Deriv proposal quotes at regular intervals."""
        from quote_recorder import DerivQuoteRecorder
        recorder = DerivQuoteRecorder(symbol=self.symbol, app_id=self.app_id)
        end_t = (time.time() + self.duration_seconds) if self.duration_seconds else float("inf")

        while self._running and time.time() < end_t:
            try:
                await recorder.record_quotes_session(
                    duration_seconds=self.quote_interval_seconds * 2,
                    interval_seconds=self.quote_interval_seconds
                )
                GLOBAL_HEALTH_MONITOR.record_quote(success=True)
            except Exception:
                GLOBAL_HEALTH_MONITOR.record_quote(success=False)
            await asyncio.sleep(self.quote_interval_seconds)

    async def run(self):
        """Starts the sustained collection loop with auto-reconnect."""
        self._running = True
        self._stop_event.clear()
        GLOBAL_HEALTH_MONITOR.update_connection_status("CONNECTING")

        print(f"\n{'=' * 60}")
        print(f"  DERIV FORWARD COLLECTION SERVICE — V1.6")
        print(f"{'=' * 60}")
        print(f"  Symbol           : {self.symbol}")
        print(f"  Mode             : {self.mode}")
        print(f"  Model ID         : {self._model_id}")
        print(f"  Session          : {self.session.session_id[:8]}")
        print(f"  Safety Guard     : LIVE_EXECUTION_DISABLED = True")
        print(f"  Duration         : {'Indefinite' if not self.duration_seconds else f'{self.duration_seconds}s'}")
        print(f"{'=' * 60}\n")

        end_t = (time.time() + self.duration_seconds) if self.duration_seconds else float("inf")

        # Start background quote poller
        quote_task = asyncio.create_task(self._quote_polling_loop())

        max_backoff = 60.0
        retry_count = 0

        try:
            while self._running and time.time() < end_t:
                streamer = LiveTickStreamer(
                    symbol=self.symbol,
                    app_id=self.app_id,
                    output_csv=self.session.live_ticks_csv,
                    on_tick_callback=self._on_tick
                )
                GLOBAL_HEALTH_MONITOR.update_connection_status("CONNECTING")
                remaining = max(1.0, end_t - time.time()) if self.duration_seconds else None

                try:
                    await streamer.run_streaming_session(duration_seconds=remaining)
                    # Clean exit (duration exhausted)
                    break
                except Exception as e:
                    print(f"[Service] Streamer error: {e}")
                    GLOBAL_HEALTH_MONITOR.update_connection_status("RECONNECTING")
                    retry_count += 1
                    backoff = min(max_backoff, 2.0 ** min(retry_count, 6))
                    print(f"[Service] Reconnecting in {backoff:.1f}s (attempt {retry_count})...")
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass

                if self._stop_event.is_set():
                    break

                retry_count = 0

        finally:
            self._running = False
            quote_task.cancel()

            # Final stat flush and outcome marking
            self.journal.mark_incomplete_as_unverified(symbol=self.symbol)
            self._flush_stats()

            # Complete session
            final_metrics = self.journal.get_accuracy_metrics(symbol=self.symbol)
            self.registry.complete_session(
                session_id=self.session.session_id,
                status="COMPLETED",
                total_ticks=self._total_ticks,
                total_predictions=final_metrics.get("total_predictions", 0),
                resolved_predictions=final_metrics.get("resolved_predictions", 0),
                unverified_predictions=final_metrics.get("unverified_predictions", 0),
                cumulative_pnl=final_metrics.get("cumulative_pnl", 0.0) or 0.0,
                notes=self.notes
            )

            GLOBAL_HEALTH_MONITOR.update_connection_status("DISCONNECTED")

            # Generate session report
            updated_session = self.registry.get_session(self.session.session_id)
            if updated_session:
                health = GLOBAL_HEALTH_MONITOR.get_health_summary()
                try:
                    report = self.reporter.generate_session_report(
                        session=updated_session,
                        health_snapshot=health
                    )
                    print(self.reporter._render_text_report(report))
                except Exception as e:
                    print(f"[Service] Report generation error: {e}")

            print(f"\n[Service] Session {self.session.session_id[:8]} complete.")
            print(f"[Service] Total ticks: {self._total_ticks}")
            print(f"[Service] Total predictions: {final_metrics.get('total_predictions', 0)}")

    def stop(self):
        """Signals the service to stop gracefully."""
        print("\n[Service] Shutdown requested.")
        self._running = False
        self._stop_event.set()


def main():
    parser = argparse.ArgumentParser(
        description="Deriv Sustained Forward Collection Service (V1.6)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("symbol", nargs="?", default="R_75",
                        help="Asset symbol (e.g. R_75)")
    parser.add_argument("--mode", default="SHADOW",
                        choices=["DATA_COLLECTION_ONLY", "SHADOW", "PAPER"],
                        help="Observation mode")
    parser.add_argument("--duration", type=float, default=None,
                        help="Session duration in seconds (omit for indefinite)")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Quote polling interval (seconds)")
    parser.add_argument("--model", default=None,
                        help="Frozen model path or ID")
    parser.add_argument("--app-id", default=DEFAULT_CONFIG.app_id,
                        help="Deriv App ID")
    parser.add_argument("--notes", default="",
                        help="Free-text notes for this session")
    args = parser.parse_args()

    service = ForwardCollectionService(
        symbol=args.symbol,
        mode=args.mode,
        duration_seconds=args.duration,
        quote_interval_seconds=args.interval,
        model_path_or_id=args.model,
        app_id=args.app_id,
        notes=args.notes
    )

    def handle_sig(sig, frame):
        service.stop()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        service.stop()


if __name__ == "__main__":
    main()
