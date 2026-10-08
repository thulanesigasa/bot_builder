# V1.6 FORWARD RESEARCH UPGRADE REPORT
## Deriv Only Ups / Only Downs Quantitative Trading System

**Release:** V1.6
**Date:** 2026-10-08
**Baseline:** V1.5.3 (97 tests passing)
**Result:** 144 tests passing (+47 new tests)

---

## 1. Objective

Transition from software development into genuine forward-market research using:
- Recorded Deriv tick data
- Actual proposal prices
- Frozen statistical models
- Strict safety controls
- Reproducible session management

This phase does not increase trade frequency.
The objective is to establish independent evidence of prediction quality.

---

## 2. New Components

### `forward_session.py`
- `ForwardSession` dataclass with UUID, config snapshot, full lifecycle state
- `ForwardSessionRegistry` — SQLite-backed session CRUD
- Config snapshot (JSON) captures exact TradingConfig at session start
- `create_session()`, `complete_session()`, `update_session_stats()`, `list_sessions()`

### `performance_tracker.py`
- `PerformanceTracker` — reads `forward_predictions.db`, computes:
  - Cumulative hypothetical PnL (real quote prices only)
  - Win rate, Sharpe ratio, max drawdown
  - EV accuracy (predicted vs realized)
  - Brier scores (RH and RL)
  - Per-market-state breakdown
  - Quote coverage % (genuine vs missing)

### `forward_validation_gate.py`
- `ForwardValidationGate` — formalises model promotion process
- Gates evaluated:
  1. Minimum resolved predictions (default 200)
  2. RUNHIGH win rate z-score ≥ 2.0
  3. RUNLOW win rate z-score ≥ 2.0
  4. Brier score improvement ≥ 5% vs naive baseline
  5. Cumulative PnL ≥ 0
  6. Quote coverage ≥ 70%
- Demotion triggers: drawdown > threshold, Brier worse than naive
- All evaluations persisted to `data/validation_gate.db`

### `session_reporter.py`
- `SessionReporter` — generates session and daily reports
- Outputs: JSON (machine-readable) + plain text (human-readable)
- Saved to `reports/` with timestamped filenames
- Includes: predictions, economic performance, validation gate, health telemetry

### `forward_collection_service.py`
- `ForwardCollectionService` — long-running, auto-reconnecting collection loop
- Creates/manages a `ForwardSession` on startup
- Runs tick streaming + quote polling + shadow predictions in one process
- Exponential backoff reconnection (up to 60s max)
- Periodic stat flush to session registry (every 50 ticks or 30s)
- Generates end-of-session report at shutdown

---

## 3. Modified Components

### `health_monitor.py` → V1.6
- Added `has_active_data_gap() -> bool` — tracks gap staleness window
- Added `set_session_id()` for session-aware telemetry
- `get_health_summary()` now includes `has_active_data_gap` and `session_id`

### `forward_observer.py` → V1.6
- Both decision gate calls now use `GLOBAL_HEALTH_MONITOR.has_active_data_gap()`
- Eliminates static `has_data_gap=False` — real gap state propagates into eligibility gate

### `config.py` → V1.6
- Added session registry path: `sessions_db_path`
- Added reports directory: `reports_dir`
- Added validation gate thresholds (6 parameters)
- Added `gap_staleness_seconds` for HealthMonitor
- Added stat flush intervals

---

## 4. Safety Invariants (Unchanged)

| Invariant | Status |
|---|---|
| `LIVE_EXECUTION_DISABLED = True` | Hardcoded in ForwardObserver, PaperTrader, ForwardCollectionService |
| No purchase/buy API calls | Confirmed — zero buy order paths |
| Conservative EV gate | Active in decision_gate.py |
| Real quotes only | No benchmark fallback allowed |
| Probability None when model absent | Enforced in forward_observer.py |

---

## 5. Test Results

```
144 passed in 19.60s
```

**+47 new tests** covering:
- ForwardSession CRUD (7 tests)
- PerformanceTracker metrics (6 tests)
- ForwardValidationGate logic (6 tests)
- SessionReporter rendering (3 tests)
- HealthMonitor V1.6 methods (8 tests)
- Gap propagation to decision gate (2 tests)
- Collection service safety invariants (3 tests)
- End-to-end safety checks (6 tests)

---

## 6. Data Flow — V1.6

```
ForwardCollectionService
  ├── creates ForwardSession (registry)
  ├── LiveTickStreamer ──[tick callback]──► ForwardObserver
  │     ├── GLOBAL_HEALTH_MONITOR.has_active_data_gap()
  │     ├── evaluate_paper_trade_eligibility() (decision_gate)
  │     └── ForwardPredictionJournal.log_prediction()
  ├── DerivQuoteRecorder ──► QuoteDatabase
  ├── periodic: ForwardSessionRegistry.update_session_stats()
  └── on shutdown:
        ├── ForwardPredictionJournal.mark_incomplete_as_unverified()
        ├── ForwardSessionRegistry.complete_session()
        └── SessionReporter.generate_session_report()
```

---

## 7. Promotion Pathway

```
RESEARCH_ONLY (shadow observation)
    │
    │  Accumulate ≥ 200 resolved predictions
    │  RH z-score ≥ 2.0 AND RL z-score ≥ 2.0
    │  Brier improvement ≥ 5% vs naive
    │  Cumulative PnL ≥ 0
    │  Quote coverage ≥ 70%
    ▼
APPROVED_FOR_PAPER (paper simulation)
    │
    │  Drawdown > $20 OR Brier worse than naive
    ▼
DEMOTE (back to RESEARCH_ONLY)
```

---

## 8. Usage

```bash
# Sustained shadow collection (indefinite)
python forward_collection_service.py R_75 --mode SHADOW

# Timed shadow session
python forward_collection_service.py R_75 --mode SHADOW --duration 3600

# Data collection only (no predictions)
python forward_collection_service.py R_75 --mode DATA_COLLECTION_ONLY

# Run validation gate
python forward_validation_gate.py R_75 LATEST

# Generate daily report
python session_reporter.py R_75

# View economic performance
python performance_tracker.py
```
