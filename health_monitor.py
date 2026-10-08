"""System, Market Data, and Proposal Quote Health Monitoring Service (V1.6).

Tracks and reports operational health across:
- WebSocket connection state & latency
- Live tick ingestion rate (ticks/sec) and freshness
- Proposal quote request success/rejection rates
- Tick duplicate counts and timestamp gap occurrences
- Reconnection frequency and backoff states
- SQLite storage health (database accessibility, size, table counts)
- Prediction engine operational health
- Hardcoded safety invariants (LIVE_EXECUTION_DISABLED = True)
"""
import collections
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config import DEFAULT_CONFIG


class HealthMonitor:
    """Centralized health metrics aggregator for live streaming and quote services."""

    def __init__(self, window_seconds: float = 60.0, gap_staleness_seconds: float = 5.0):
        self.window_seconds = window_seconds
        self.gap_staleness_seconds = gap_staleness_seconds
        self.connection_status: str = "DISCONNECTED"
        self.reconnection_count: int = 0
        self.last_reconnect_time: Optional[float] = None
        self.session_id: Optional[str] = None

        # Tick metrics
        self.total_ticks: int = 0
        self.duplicate_ticks: int = 0
        self.gap_count: int = 0
        self.last_tick_time: Optional[float] = None
        self.last_tick_epoch: Optional[int] = None
        self.last_tick_latency_ms: float = 0.0
        self._tick_timestamps = collections.deque()
        self._last_gap_time: Optional[float] = None   # Wall time of most recent gap

        # Quote metrics
        self.total_quote_requests: int = 0
        self.quote_success_count: int = 0
        self.quote_rejection_count: int = 0
        self.last_quote_time: Optional[float] = None
        self.last_quote_latency_ms: float = 0.0
        self._quote_timestamps = collections.deque()

        # Prediction engine metrics
        self.total_predictions: int = 0
        self.resolved_predictions: int = 0
        self.uncalibrated_rejections: int = 0

    def update_connection_status(self, status: str):
        """Updates WebSocket connection state ('CONNECTED', 'DISCONNECTED', 'RECONNECTING')."""
        self.connection_status = status
        if status == "RECONNECTING":
            self.reconnection_count += 1
            self.last_reconnect_time = time.time()

    def set_session_id(self, session_id: str):
        """Associates the current collection session with this health monitor."""
        self.session_id = session_id

    def record_tick(self, epoch: int, receipt_time: Optional[float] = None, is_duplicate: bool = False, is_gap: bool = False, latency_ms: float = 0.0):
        """Records an ingested tick event."""
        now = receipt_time or time.time()
        self.total_ticks += 1
        self.last_tick_time = now
        self.last_tick_epoch = epoch
        self.last_tick_latency_ms = latency_ms

        if is_duplicate:
            self.duplicate_ticks += 1
        if is_gap:
            self.gap_count += 1
            self._last_gap_time = now

        self._tick_timestamps.append(now)
        self._prune_windows(now)

    def has_active_data_gap(self) -> bool:
        """Returns True if a data gap was detected within the last gap_staleness_seconds.

        Used by ForwardObserver to propagate real market data gap state into the
        centralized decision gate, preventing paper trade authorizations during
        periods of degraded tick integrity.
        """
        if self._last_gap_time is None:
            return False
        return (time.time() - self._last_gap_time) <= self.gap_staleness_seconds

    def record_quote(self, success: bool, latency_ms: float = 0.0, receipt_time: Optional[float] = None):
        """Records a quote proposal request/response event."""
        now = receipt_time or time.time()
        self.total_quote_requests += 1
        self.last_quote_time = now
        self.last_quote_latency_ms = latency_ms

        if success:
            self.quote_success_count += 1
        else:
            self.quote_rejection_count += 1

        self._quote_timestamps.append(now)
        self._prune_windows(now)

    def record_prediction(self, resolved: bool = False, was_uncalibrated: bool = False):
        """Records a forward prediction evaluation."""
        self.total_predictions += 1
        if resolved:
            self.resolved_predictions += 1
        if was_uncalibrated:
            self.uncalibrated_rejections += 1

    def _prune_windows(self, now: float):
        """Prunes event timestamps older than the sliding window."""
        cutoff = now - self.window_seconds
        while self._tick_timestamps and self._tick_timestamps[0] < cutoff:
            self._tick_timestamps.popleft()
        while self._quote_timestamps and self._quote_timestamps[0] < cutoff:
            self._quote_timestamps.popleft()

    def get_tick_rate(self) -> float:
        """Returns the current tick ingestion rate (ticks/second) over the sliding window."""
        now = time.time()
        self._prune_windows(now)
        count = len(self._tick_timestamps)
        return round(count / self.window_seconds, 2) if self.window_seconds > 0 else 0.0

    def get_quote_success_rate(self) -> float:
        """Returns the proportion of successful quote responses."""
        if self.total_quote_requests == 0:
            return 100.0
        return round((self.quote_success_count / self.total_quote_requests) * 100.0, 1)

    def check_storage_health(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Audits accessibility and integrity of SQLite quote storage."""
        target_path = db_path or DEFAULT_CONFIG.quotes_db_path
        if not os.path.exists(target_path):
            return {
                "db_path": target_path,
                "status": "NOT_INITIALIZED",
                "size_kb": 0.0,
                "quote_count": 0,
                "writable": False
            }

        size_kb = round(os.path.getsize(target_path) / 1024.0, 2)
        try:
            conn = sqlite3.connect(target_path, timeout=3.0)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM quotes")
            cnt = cur.fetchone()[0]
            conn.close()
            return {
                "db_path": target_path,
                "status": "HEALTHY",
                "size_kb": size_kb,
                "quote_count": cnt,
                "writable": os.access(target_path, os.W_OK)
            }
        except Exception as e:
            return {
                "db_path": target_path,
                "status": "ERROR",
                "error": str(e),
                "size_kb": size_kb,
                "quote_count": 0,
                "writable": False
            }

    def get_health_summary(self) -> Dict[str, Any]:
        """Returns a comprehensive system health summary dictionary."""
        now = time.time()
        tick_age = round(now - self.last_tick_time, 2) if self.last_tick_time else None
        quote_age = round(now - self.last_quote_time, 2) if self.last_quote_time else None
        storage = self.check_storage_health()

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "safety": {
                "live_money_disabled": True,
                "purchasing_allowed": False,
                "demo_execution_allowed": DEFAULT_CONFIG.enable_demo_execution
            },
            "connectivity": {
                "connection_status": self.connection_status,
                "reconnection_count": self.reconnection_count,
                "last_reconnect_time": self.last_reconnect_time,
                "has_active_data_gap": self.has_active_data_gap()
            },
            "ticks": {
                "total_ticks": self.total_ticks,
                "tick_rate_per_sec": self.get_tick_rate(),
                "last_tick_epoch": self.last_tick_epoch,
                "last_tick_age_seconds": tick_age,
                "last_tick_latency_ms": self.last_tick_latency_ms,
                "duplicate_ticks": self.duplicate_ticks,
                "gap_count": self.gap_count
            },
            "quotes": {
                "total_requests": self.total_quote_requests,
                "successful_quotes": self.quote_success_count,
                "rejected_quotes": self.quote_rejection_count,
                "success_rate_pct": self.get_quote_success_rate(),
                "last_quote_age_seconds": quote_age,
                "last_quote_latency_ms": self.last_quote_latency_ms
            },
            "predictions": {
                "total_predictions": self.total_predictions,
                "resolved_predictions": self.resolved_predictions,
                "uncalibrated_rejections": self.uncalibrated_rejections
            },
            "storage": storage
        }


# Global singleton instance for system-wide health observation
GLOBAL_HEALTH_MONITOR = HealthMonitor()


def main():
    print("=== DERIV MARKET DATA & QUOTE HEALTH MONITOR ===")
    summary = GLOBAL_HEALTH_MONITOR.get_health_summary()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
