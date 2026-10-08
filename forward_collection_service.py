"""Sustained Forward Collection Service (V1.6.1).

Provides a long-running, auto-reconnecting forward observation service that:
  1. Creates and registers a new ForwardSession on startup with unique session ID.
  2. Instantiates ForwardObserver with that session's ID and database paths.
  3. Runs tick collection + quote recording + shadow/paper prediction in one loop.
  4. Auto-reconnects with exponential backoff on WebSocket failures up to configured attempts.
  5. Enforces observation bounds (duration, maximum observations count, flush policy).
  6. Restores all subscriptions on reconnect (ticks + proposal polling).
  7. Periodically updates session stats in the registry.
  8. Generates a session report via SessionReporter at clean shutdown.
  9. Propagates real-time data-gap state from HealthMonitor into decision gate.

Safety Directive:
  LIVE_EXECUTION_DISABLED is permanently True.
  No real-money orders are placed under any circumstances.

Usage:
    python forward_collection_service.py [symbol] [--mode SHADOW] [--duration 3600]
    python forward_collection_service.py R_75 --mode SHADOW --duration 7200 --max-observations 500
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
from forward_journal import ForwardPredictionJournal, STATUS_INCOMPLETE
from forward_observer import ForwardObserver
from forward_session import ForwardSessionRegistry, ForwardSession
from health_monitor import GLOBAL_HEALTH_MONITOR
from live_collector import LiveTickStreamer, LiveTickRecord
from model_manager import ModelManager
from session_reporter import SessionReporter


# Absolute safety constant — cannot be modified at runtime
LIVE_EXECUTION_DISABLED: bool = True


class ForwardCollectionService:
    """Long-running forward data collection and shadow prediction service (V1.6.1)."""

    LIVE_EXECUTION_DISABLED: bool = True

    def __init__(
        self,
        symbol: str = "R_75",
        mode: str = "SHADOW",
        duration_seconds: Optional[float] = None,  # None = run indefinitely
        max_observations: Optional[int] = None,    # Max predictions before stopping
        quote_interval_seconds: float = 2.0,
        max_quote_age_seconds: float = 60.0,
        app_id: Optional[str] = None,
        model_path_or_id: Optional[str] = None,
        max_reconnect_attempts: int = 10,
        tick_buffer_capacity: int = 500,
        flush_interval_ticks: int = 50,
        flush_interval_secs: float = 30.0,
        reports_dir: Optional[str] = None,
        notes: str = "",
        preload_warmup: bool = True,
        prediction_cutoff_seconds: float = 20.0,
        max_resolution_grace_seconds: float = 30.0,
        resolve_on_shutdown: bool = True
    ):
        if LIVE_EXECUTION_DISABLED is not True:
            raise RuntimeError("Safety invariant violated: LIVE_EXECUTION_DISABLED must be True.")

        self.symbol = symbol
        self.mode = mode.upper()
        if self.mode not in ("DATA_COLLECTION_ONLY", "SHADOW", "PAPER"):
            self.mode = "SHADOW"
        self.duration_seconds = duration_seconds
        self.max_observations = max_observations
        self.quote_interval_seconds = max(1.0, quote_interval_seconds)  # Rate limit protection
        self.max_quote_age_seconds = max_quote_age_seconds
        self.app_id = app_id or DEFAULT_CONFIG.app_id
        self.model_path_or_id = model_path_or_id
        self.max_reconnect_attempts = max_reconnect_attempts
        self.tick_buffer_capacity = tick_buffer_capacity
        self.flush_interval_ticks = flush_interval_ticks
        self.flush_interval_secs = flush_interval_secs
        self.reports_dir = reports_dir
        self.notes = notes
        self.preload_warmup = preload_warmup
        self.prediction_cutoff_seconds = max(0.0, prediction_cutoff_seconds)
        self.max_resolution_grace_seconds = max(0.0, max_resolution_grace_seconds)
        self.resolve_on_shutdown = resolve_on_shutdown

        # Resolve model ID for session registration
        mgr = ModelManager()
        if model_path_or_id:
            self._model_id = os.path.basename(model_path_or_id)
            self._model_version = "user-specified"
        else:
            latest = mgr.get_latest_model_for_symbol(symbol)
            self._model_id = os.path.basename(latest) if latest else "NONE"
            self._model_version = "auto-latest"

        # Create session in registry and recover interrupted sessions
        self.registry = ForwardSessionRegistry()
        recovered = self.registry.recover_interrupted_sessions()
        if recovered:
            print(f"[Service] Auto-recovered {len(recovered)} dangling session(s) to INTERRUPTED state.")

        self.session: ForwardSession = self.registry.create_session(
            symbol=symbol,
            mode=self.mode,
            model_id=self._model_id,
            model_version=self._model_version,
            planned_duration_seconds=duration_seconds or 0.0,
            notes=notes
        )
        print(f"[Service] Session created: {self.session.session_id[:8]} | Mode: {self.mode}")

        # Components with session_id linkage
        self.journal = ForwardPredictionJournal(db_path=self.session.journal_db_path, enforce_session_id=True)
        self.observer = ForwardObserver(
            symbol=symbol,
            mode=self.mode,
            model_path_or_id=model_path_or_id,
            app_id=self.app_id,
            duration_seconds=duration_seconds or 86400.0,
            quote_interval_seconds=self.quote_interval_seconds,
            max_quote_age_seconds=max_quote_age_seconds,
            journal_db_path=self.session.journal_db_path,
            quote_db_path=self.session.quote_db_path,
            session_id=self.session.session_id,
            preload_warmup=self.preload_warmup
        )
        self.reporter = SessionReporter(
            reports_dir=self.reports_dir,
            journal=self.journal,
            registry=self.registry
        )

        self._running = False
        self._stop_event = asyncio.Event()
        self._ticks_since_flush = 0
        self._last_flush_time = time.time()
        self._total_ticks = 0
        self._duplicate_ticks = 0
        self._rejected_ticks = 0
        self._total_predictions = 0

    def _on_tick(self, tick: LiveTickRecord):
        """Tick callback — delegates to observer and tracks health."""
        GLOBAL_HEALTH_MONITOR.record_tick(
            epoch=int(tick.server_timestamp),
            is_duplicate=(tick.data_quality_flags == "DUPLICATE_IGNORED"),
            is_gap=(tick.data_quality_flags == "GAP_DETECTED"),
            latency_ms=tick.latency_ms
        )

        if tick.data_quality_flags == "DUPLICATE_IGNORED":
            self._duplicate_ticks += 1
            return

        # Check prediction cutoff near end of session (V1.6.4 Part D Section 9)
        if self.duration_seconds and hasattr(self, "_session_end_time"):
            if time.time() >= (self._session_end_time - self.prediction_cutoff_seconds):
                if not self.observer.prediction_cutoff_active:
                    self.observer.prediction_cutoff_active = True
                    print(f"\n[Service] Prediction cutoff reached ({self.prediction_cutoff_seconds:.0f}s before session end). Halting new predictions; continuing observation to resolve pending outcomes.")

        # Delegate to observer (evaluates features, inference, journal)
        pred = self.observer.process_incoming_tick(tick)
        if pred is not None:
            self._total_predictions += 1

        self._total_ticks += 1
        self._ticks_since_flush += 1

        # Check maximum observations control (V1.6.1 Section 14)
        if self.max_observations and self._total_predictions >= self.max_observations:
            print(f"[Service] Reached maximum observation target ({self._total_predictions}/{self.max_observations}). Stopping gracefully...")
            self._running = False
            self._stop_event.set()

        # Periodic stat flush to registry
        now = time.time()
        if (self._ticks_since_flush >= self.flush_interval_ticks or
                now - self._last_flush_time >= self.flush_interval_secs):
            self._flush_stats()

    def _flush_stats(self):
        """Writes current session metrics to the registry."""
        metrics = self.journal.get_accuracy_metrics(symbol=self.symbol, session_id=self.session.session_id)
        pnl = metrics.get("cumulative_pnl", 0.0) or 0.0
        self.registry.update_session_stats(
            session_id=self.session.session_id,
            total_ticks=self._total_ticks,
            total_predictions=metrics.get("total_predictions", 0),
            resolved_predictions=metrics.get("resolved_predictions", 0),
            unverified_predictions=metrics.get("unverified_predictions", 0),
            cumulative_pnl=pnl,
            live_ticks=self.observer.live_ticks_count,
            warmup_ticks=self.observer.warmup_ticks_count,
            duplicate_ticks=self._duplicate_ticks,
            rejected_ticks=self._rejected_ticks
        )
        self._ticks_since_flush = 0
        self._last_flush_time = time.time()

    async def _quote_polling_loop(self):
        """Background task polling Deriv proposal quotes at regular intervals."""
        from quote_recorder import DerivQuoteRecorder
        recorder = DerivQuoteRecorder(symbol=self.symbol, app_id=self.app_id, session_id=self.session.session_id)
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
        from forward_session import STATUS_ACTIVE, STATUS_COMPLETED, STATUS_INTERRUPTED
        self.registry.set_session_status(self.session.session_id, STATUS_ACTIVE)
        GLOBAL_HEALTH_MONITOR.update_connection_status("CONNECTING")

        print(f"\n{'=' * 65}")
        print(f"  DERIV FORWARD COLLECTION SERVICE — V1.6.3")
        print(f"{'=' * 65}")
        print(f"  Symbol           : {self.symbol}")
        print(f"  Mode             : {self.mode}")
        print(f"  Model ID         : {self._model_id}")
        print(f"  Session ID       : {self.session.session_id[:8]}")
        print(f"  Warmup Preload   : {'ENABLED' if self.preload_warmup else 'DISABLED'}")
        print(f"  Safety Guard     : LIVE_EXECUTION_DISABLED = True")
        print(f"  Duration         : {'Indefinite' if not self.duration_seconds else f'{self.duration_seconds}s'}")
        if self.max_observations:
            print(f"  Max Observations : {self.max_observations}")
        print(f"  Quote Polling    : Every {self.quote_interval_seconds}s")
        print(f"{'=' * 65}\n")

        end_t = (time.time() + self.duration_seconds) if self.duration_seconds else float("inf")
        self._session_end_time = end_t

        # Start background quote poller
        quote_task = asyncio.create_task(self._quote_polling_loop())

        max_backoff = 60.0
        retry_count = 0
        service_error = False

        try:
            while self._running and time.time() < end_t:
                streamer = LiveTickStreamer(
                    symbol=self.symbol,
                    app_id=self.app_id,
                    output_csv=self.session.live_ticks_csv,
                    on_tick_callback=self._on_tick,
                    session_id=self.session.session_id
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
                    if retry_count > self.max_reconnect_attempts:
                        print(f"[Service] Max reconnect attempts reached ({self.max_reconnect_attempts}). Stopping...")
                        service_error = True
                        break
                    backoff = min(max_backoff, 2.0 ** min(retry_count, 6))
                    print(f"[Service] Reconnecting in {backoff:.1f}s (attempt {retry_count}/{self.max_reconnect_attempts})...")
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass

                if self._stop_event.is_set():
                    break

                retry_count = 0

            # Controlled Resolution Grace Window (V1.6.4 Part D Section 9)
            if (not service_error and self.resolve_on_shutdown and
                    getattr(self.journal, "resolver", None) and
                    self.journal.resolver.active_pending_count > 0 and
                    self.max_resolution_grace_seconds > 0):
                pending_cnt = self.journal.resolver.active_pending_count
                print(f"\n[Service] Nominal session duration reached. Entering resolution grace window for {pending_cnt} pending prediction(s) (up to {self.max_resolution_grace_seconds:.0f}s)...")
                grace_end = time.time() + self.max_resolution_grace_seconds
                self.observer.prediction_cutoff_active = True

                while self._running and time.time() < grace_end and self.journal.resolver.active_pending_count > 0:
                    streamer_grace = LiveTickStreamer(
                        symbol=self.symbol,
                        app_id=self.app_id,
                        output_csv=self.session.live_ticks_csv,
                        on_tick_callback=self._on_tick,
                        session_id=self.session.session_id
                    )
                    rem_grace = max(1.0, grace_end - time.time())
                    try:
                        await streamer_grace.run_streaming_session(duration_seconds=min(rem_grace, 6.0))
                    except Exception as ge:
                        print(f"[Service] Grace streaming notice: {ge}")
                        break
                    if self.journal.resolver.active_pending_count == 0:
                        print(f"[Service] All pending forward outcomes resolved successfully during grace window!")
                        break

        except Exception as e:
            print(f"[Service] Unexpected error in collection loop: {e}")
            service_error = True
        finally:
            self._running = False
            quote_task.cancel()

            # Print pipeline diagnostics
            try:
                diag = self.observer.get_diagnostics_report()
                print("\n[Service Diagnostics Report]")
                print(f"  Pipeline Status     : {diag.get('pipeline_status')}")
                print(f"  Warmup Completed    : {diag.get('warmup_completed')}")
                print(f"  Required Lookback   : {diag.get('required_lookback')}")
                print(f"  Warmup Ticks Preload: {diag.get('warmup_ticks_preloaded')}")
                print(f"  Live Ticks Received : {diag.get('live_ticks_received')}")
                print(f"  Predictions Made    : {diag.get('predictions_generated')}")
                print(f"  Active Pending      : {diag.get('active_pending_count')}")
                if diag.get("last_pipeline_error"):
                    print(f"  Last Pipeline Error : {diag.get('last_pipeline_error')}")
            except Exception as e:
                print(f"[Service] Diagnostics extraction error: {e}")

            # Final stat flush and outcome marking (mark incomplete as OUTCOME_INCOMPLETE)
            self.journal.mark_incomplete_as_unverified(symbol=self.symbol, target_status=STATUS_INCOMPLETE)
            self._flush_stats()

            # Complete session in registry with authoritative status
            final_metrics = self.journal.get_accuracy_metrics(symbol=self.symbol, session_id=self.session.session_id)
            final_status = STATUS_INTERRUPTED if service_error else STATUS_COMPLETED
            self.registry.complete_session(
                session_id=self.session.session_id,
                status=final_status,
                total_ticks=self._total_ticks,
                total_predictions=final_metrics.get("total_predictions", 0),
                resolved_predictions=final_metrics.get("resolved_predictions", 0),
                unverified_predictions=final_metrics.get("unverified_predictions", 0),
                cumulative_pnl=final_metrics.get("cumulative_pnl", 0.0) or 0.0,
                live_ticks=self.observer.live_ticks_count,
                warmup_ticks=self.observer.warmup_ticks_count,
                duplicate_ticks=self._duplicate_ticks,
                rejected_ticks=self._rejected_ticks,
                notes=self.notes
            )
            GLOBAL_HEALTH_MONITOR.update_connection_status("DISCONNECTED")

            # Run automated reconciliation engine (V1.6.2 Section 12)
            try:
                from session_reconciler import SessionReconciler
                reconciler = SessionReconciler(
                    registry_db_path=self.registry.db_path,
                    journal_db_path=self.session.journal_db_path,
                    quote_db_path=self.session.quote_db_path
                )
                recon_res = reconciler.reconcile_session(self.session.session_id)
                print(f"\n{recon_res.summary_text()}\n")
            except Exception as e:
                print(f"[Service] Warning: Could not run reconciliation: {e}")

            # Generate end-of-session report
            try:
                report = self.reporter.generate_session_report(
                    session=self.session,
                    health_snapshot=GLOBAL_HEALTH_MONITOR.get_health_summary()
                )
                print(f"[Service] End-of-session report generated in: {self.reporter.reports_dir}")
            except Exception as e:
                print(f"[Service] Warning: Could not generate session report: {e}")

            print(f"\n[Service] Forward collection session completed gracefully.")


def main():
    parser = argparse.ArgumentParser(description="Sustained Forward Collection Service (V1.6.3)")
    parser.add_argument("symbol", nargs="?", default="R_75", help="Asset symbol (e.g. R_75)")
    parser.add_argument("--mode", default="SHADOW", choices=["DATA_COLLECTION_ONLY", "SHADOW", "PAPER"], help="Observation mode")
    parser.add_argument("--duration", type=float, default=None, help="Session duration in seconds (omitted = indefinite)")
    parser.add_argument("--max-observations", type=int, default=None, help="Maximum predictions before stopping")
    parser.add_argument("--interval", type=float, default=2.0, help="Quote polling interval in seconds")
    parser.add_argument("--model", default=None, help="Path or ID of frozen model artifact")
    parser.add_argument("--reconnect-attempts", type=int, default=10, help="Maximum reconnect attempts")
    parser.add_argument("--flush-interval", type=int, default=50, help="Stat flush interval in ticks")
    parser.add_argument("--report-dir", default=None, help="Directory for reports")
    parser.add_argument("--notes", default="", help="Session notes")
    parser.add_argument("--no-preload-warmup", action="store_true", help="Disable preloading historical warmup ticks")
    args = parser.parse_args()

    service = ForwardCollectionService(
        symbol=args.symbol,
        mode=args.mode,
        duration_seconds=args.duration,
        max_observations=args.max_observations,
        quote_interval_seconds=args.interval,
        model_path_or_id=args.model,
        max_reconnect_attempts=args.reconnect_attempts,
        flush_interval_ticks=args.flush_interval,
        reports_dir=args.report_dir,
        notes=args.notes,
        preload_warmup=not args.no_preload_warmup
    )

    def handle_sig(sig, frame):
        print("\nShutdown signal received. Stopping collection service...")
        service._running = False
        service._stop_event.set()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
