"""Operational Forward Research Session Launcher (V1.6.4).

Primary CLI entry point for initiating and managing live non-purchasing forward market observation:
    python run_forward_session.py --mode SHADOW --symbol R_75
    python run_forward_session.py --mode SHADOW --symbol R_75 --duration 3600
    python run_forward_session.py --mode DATA_COLLECTION_ONLY --symbol R_75 --duration 1800
    python run_forward_session.py --smoke-test --symbol R_75
    python run_forward_session.py --diagnose --symbol R_75

Lifecycle execution sequence:
  1. Verifies supported symbol availability.
  2. Verifies Deriv API endpoint reachability.
  3. Discovers and validates compatible frozen ModelArtifact with dynamic lookback.
  4. Preloads historical ticks for zero-wait warmup prior to live stream start.
  5. Initializes SQLite forward prediction journal, quote database, and persistent risk state.
  6. Creates a registered ForwardSession in sessions.db.
  7. Subscribes to live Deriv ticks and records proposals.
  8. Computes rolling discrete market features without lookahead.
  9. Executes frozen model inference and logs prediction before outcome is known.
  10. Streams subsequent ticks to reconstruct canonical 5-tick contract outcomes.
  11. Persists resolved/incomplete records immutably.
  12. Handles SIGINT/SIGTERM gracefully, generating end-of-session JSON & text reports.

Safety Mandate:
  LIVE_EXECUTION_DISABLED is permanently True.
  No purchase/buy requests are ever issued to Deriv API endpoints.
"""
import argparse
import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional, List

from config import DEFAULT_CONFIG
from forward_collection_service import ForwardCollectionService, LIVE_EXECUTION_DISABLED
from model_manager import ModelManager
from model_artifact import ModelArtifact, ModelStatus


SUPPORTED_SYMBOLS: List[str] = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V"
]


def print_banner(symbol: str, mode: str, duration: Optional[float], max_obs: Optional[int]):
    print("\n" + "=" * 70)
    print("  DERIV ONLY UPS / ONLY DOWNS QUANTITATIVE RESEARCH ENGINE")
    print("  FORWARD OBSERVATION, RECONCILIATION & EVIDENCE SYSTEM (V1.6.4)")
    print("=" * 70)
    print(f"  Target Symbol       : {symbol}")
    print(f"  Execution Mode      : {mode}")
    print(f"  Safety Status       : REAL-MONEY TRADING DISABLED (Zero buy orders)")
    print(f"  Duration            : {'Continuous / Indefinite' if not duration else f'{duration:.0f} seconds'}")
    if max_obs:
        print(f"  Max Observations    : {max_obs}")
    print("=" * 70 + "\n")


def verify_environment(symbol: str, mode: str, model_path: Optional[str] = None):
    """Verifies symbol support, API endpoint configuration, and frozen model availability."""
    print("[Preflight] 1. Verifying symbol compatibility...")
    if symbol not in SUPPORTED_SYMBOLS:
        print(f"[Preflight] WARNING: {symbol} is not in the canonical tested symbol list ({SUPPORTED_SYMBOLS}). Proceeding anyway.")
    else:
        print(f"[Preflight] Symbol {symbol} is confirmed supported.")

    print("[Preflight] 2. Checking frozen statistical model...")
    mgr = ModelManager()
    target_model = model_path or mgr.get_latest_model_for_symbol(symbol)
    if target_model:
        is_valid, code, art = mgr.validate_and_load_model(
            model_path_or_id=target_model,
            expected_symbol=symbol,
            require_paper_approval=(mode == "PAPER")
        )
        if art:
            print(f"[Preflight] Model loaded: {art.model_id} (Approval: {art.approval_status})")
        else:
            print(f"[Preflight] Model validation note: {code}. Shadow observation will operate with unvalidated research model.")
    else:
        if mode == "PAPER":
            raise RuntimeError(f"PAPER mode requires a validated model for {symbol}. None found.")
        print("[Preflight] No frozen model found. Shadow mode will run baseline empirical collection.")

    print("[Preflight] 3. Safety directives confirmed: LIVE_EXECUTION_DISABLED = True.")


def main():
    parser = argparse.ArgumentParser(
        description="Deriv Forward Statistical Validation & Research Collection Service (V1.7)"
    )
    parser.add_argument("--symbol", default="R_75", help="Deriv synthetic asset symbol (default: R_75)")
    parser.add_argument(
        "--mode",
        default="SHADOW",
        choices=["DATA_COLLECTION_ONLY", "SHADOW", "PAPER"],
        help="Observation mode (default: SHADOW)"
    )
    parser.add_argument(
        "--stage",
        default="EXPLORATORY",
        choices=["EXPLORATORY", "VALIDATION", "CONFIRMATION"],
        help="Research session stage (default: EXPLORATORY)"
    )
    parser.add_argument("--duration", type=float, default=3600.0, help="Session duration in seconds (default: 3600; 0 for continuous)")
    parser.add_argument("--max-observations", type=int, default=None, help="Maximum predictions before graceful exit")
    parser.add_argument("--target-resolved", type=int, default=None, help="Milestone target for resolved predictions before concluding session")
    parser.add_argument("--quote-interval", type=float, default=2.0, help="Quote polling interval in seconds (default: 2.0)")
    parser.add_argument("--buffer-capacity", type=int, default=500, help="In-memory tick buffer capacity (default: 500)")
    parser.add_argument("--flush-interval", type=int, default=50, help="Database stat flush frequency in ticks (default: 50)")
    parser.add_argument("--reconnect-attempts", type=int, default=10, help="Max WebSocket reconnection attempts (default: 10)")
    parser.add_argument("--model", default=None, help="Explicit path or ID of frozen model artifact")
    parser.add_argument("--report-dir", default="reports", help="Directory for output reports (default: reports)")
    parser.add_argument("--notes", default="", help="Optional notes stored in session registry")
    parser.add_argument("--manifest", default=None, help="Path to pre-registered ConfirmationManifest JSON file (mandatory for CONFIRMATION stage)")
    parser.add_argument("--smoke-test", action="store_true", help="Run a brief 30-second live smoke test session")
    parser.add_argument("--diagnose", action="store_true", help="Run prediction pipeline diagnostics and report current status without running collection")
    parser.add_argument("--no-preload-warmup", action="store_true", help="Disable preloading historical warmup ticks")
    parser.add_argument("--grace-seconds", type=float, default=30.0, help="Max grace window seconds to resolve pending outcomes at session end (default: 30.0)")
    parser.add_argument("--cutoff-seconds", type=float, default=20.0, help="Seconds before session end to halt new prediction creation (default: 20.0)")
    args = parser.parse_args()

    stage_map = {
        "EXPLORATORY": "EXPLORATORY_FORWARD",
        "VALIDATION": "VALIDATION_FORWARD",
        "CONFIRMATION": "CONFIRMATION_FORWARD"
    }
    stage_val = stage_map.get(args.stage.upper(), "EXPLORATORY_FORWARD")

    confirmation_manifest = None
    if stage_val == "CONFIRMATION_FORWARD":
        if not args.manifest:
            print("[Error] Mandatory admission check failed: CONFIRMATION stage requires a pre-registered ConfirmationManifest file via --manifest <path>.")
            sys.exit(1)
        if not os.path.exists(args.manifest):
            print(f"[Error] Specified confirmation manifest file does not exist: {args.manifest}")
            sys.exit(1)
        try:
            from confirmation_specification import ConfirmationManifest
            confirmation_manifest = ConfirmationManifest.load_from_file(args.manifest)
            print(f"[Confirmation Preflight] Loaded pre-registered manifest: {confirmation_manifest.specification_id} (Checksum: {confirmation_manifest.manifest_checksum[:12]}...)")
        except Exception as e:
            print(f"[Error] Invalid or tampered confirmation manifest: {e}")
            sys.exit(1)

    if args.diagnose:
        from forward_observer import ForwardObserver
        print("\n=======================================================")
        print("  OPERATIONAL PREDICTION PIPELINE DIAGNOSTICS (V1.7)")
        print("=======================================================")
        print(f"  Target Symbol       : {args.symbol}")
        print(f"  Mode                : {args.mode}")
        print(f"  Research Stage      : {stage_val}")
        obs = ForwardObserver(
            symbol=args.symbol,
            mode=args.mode,
            model_path_or_id=args.model,
            preload_warmup=not args.no_preload_warmup
        )
        report = obs.get_diagnostics_report()
        print("\n[Diagnostics Results]")
        print(f"  Pipeline Status       : {report.get('pipeline_status')}")
        print(f"  Warmup Status         : {report.get('warmup_status')}")
        print(f"  Model ID              : {report.get('model_id')}")
        print(f"  Model Status          : {report.get('model_status')}")
        print(f"  Required Lookback     : {report.get('required_lookback')} ticks")
        print(f"  Preloaded Warmup      : {report.get('historical_warmup_ticks')} ticks")
        print(f"  Buffer Ticks          : {report.get('ticks_in_buffer')} ticks")
        print(f"  Warmup Completed      : {report.get('is_warmed_up')}")
        print(f"  Live Ticks Received   : {report.get('live_ticks_received')}")
        print(f"  Predictions Generated : {report.get('predictions_generated')}")
        print(f"  Predictions Persisted : {report.get('predictions_persisted')}")
        print(f"  Active Pending        : {report.get('active_pending_count')}")
        print(f"  Current Blocker       : {report.get('current_blocker') or 'None (Ready for inference)'}")
        print(f"  Last Pipeline Event   : {report.get('last_pipeline_event')}")
        print(f"  Safety Directive      : {report.get('safety_status')}")
        print("=======================================================\n")
        return

    # Smoke test preset
    duration = 30.0 if args.smoke_test else (args.duration if args.duration and args.duration > 0 else None)
    max_obs = 10 if args.smoke_test else args.max_observations
    notes = "V1.7 Live Smoke Test" if args.smoke_test else args.notes

    print_banner(symbol=args.symbol, mode=args.mode, duration=duration, max_obs=max_obs)

    try:
        verify_environment(symbol=args.symbol, mode=args.mode, model_path=args.model)
    except Exception as e:
        print(f"[Error] Preflight verification failed: {e}")
        sys.exit(1)

    service = ForwardCollectionService(
        symbol=args.symbol,
        mode=args.mode,
        duration_seconds=duration,
        max_observations=max_obs,
        quote_interval_seconds=args.quote_interval,
        model_path_or_id=args.model,
        max_reconnect_attempts=args.reconnect_attempts,
        tick_buffer_capacity=args.buffer_capacity,
        flush_interval_ticks=args.flush_interval,
        reports_dir=args.report_dir,
        notes=notes,
        preload_warmup=not args.no_preload_warmup,
        prediction_cutoff_seconds=args.cutoff_seconds,
        max_resolution_grace_seconds=args.grace_seconds,
        research_stage=stage_val,
        target_resolved_predictions=args.target_resolved,
        confirmation_manifest=confirmation_manifest,
        enforce_confirmation_admission=(stage_val == "CONFIRMATION_FORWARD")
    )

    def handle_sig(sig, frame):
        print("\n[Shutdown] Signal received. Terminating collection gracefully and persisting records...")
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
