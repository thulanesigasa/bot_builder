"""Configuration settings and direction-specific quote parameters for Deriv 5-Tick UP/DOWN Engine (V1.5.2).
Supports standard Rise/Fall as well as asymmetric high-payout contracts ($2 -> $61.03).
Provides secure environment variable loading with .env support and strict safety defaults.
"""
import os
from dataclasses import dataclass
from typing import Optional


def load_env_file(filepath: str = ".env"):
    """Lightweight .env parser that populates os.environ without requiring external dependencies."""
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# Attempt to load .env on import
load_env_file()


@dataclass(frozen=True)
class TradingConfig:
    # Asset & Contract
    symbol: str = os.environ.get("DEFAULT_SYMBOL", "R_75")
    duration_ticks: int = int(os.environ.get("DURATION_TICKS", "5"))
    contract_family: str = "rise_fall"  # 'rise_fall' or 'high_payout'
    currency: str = os.environ.get("CURRENCY", "USD")

    # Direction-Specific Payouts (Default: 0.95 profit per $1 stake -> 1.95 total return)
    up_payout_ratio: float = 0.95
    down_payout_ratio: float = 0.95
    default_stake: float = float(os.environ.get("DEFAULT_STAKE", "2.0"))

    # High-Payout Contract Preset ($2 -> $61.03)
    high_payout_stake: float = 2.0
    high_payout_total: float = 61.03

    # API Endpoints
    app_id: str = os.environ.get("DERIV_APP_ID", "1089")
    ws_url: str = os.environ.get("DERIV_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public")
    fallback_ws_url: str = os.environ.get("DERIV_FALLBACK_WS_URL", "wss://ws.derivws.com/websockets/v3")

    # Live Data & Quote Polling Constraints
    max_quote_age_seconds: float = float(os.environ.get("MAX_QUOTE_AGE_SECONDS", "60.0"))
    quote_poll_interval: float = float(os.environ.get("QUOTE_POLL_INTERVAL_SECONDS", "2.0"))
    tick_gap_threshold_seconds: float = float(os.environ.get("TICK_GAP_THRESHOLD_SECONDS", "3.0"))
    live_tick_flush_interval: int = int(os.environ.get("LIVE_TICK_FLUSH_INTERVAL_TICKS", "25"))

    # Storage Paths
    quotes_db_path: str = os.environ.get("QUOTES_DB_PATH", "data/quotes.db")
    forward_predictions_db_path: str = os.environ.get("FORWARD_PREDICTIONS_DB_PATH", "data/forward_predictions.db")
    live_ticks_dir: str = os.environ.get("LIVE_TICKS_DIR", "data")

    # Risk Management (Updated to conservative institutional parameters per V1.1)
    initial_balance: float = 1000.0
    risk_per_trade_pct: float = 0.0025  # 0.25% per trade
    max_stake: float = 5.0
    max_consecutive_losses: int = 3
    cooldown_ticks: int = 50
    daily_loss_limit_pct: float = 0.05  # 5% max daily drawdown (resets per UTC day)

    # 3-Way Statistical Split Protocol
    train_pct: float = 0.60
    val_pct: float = 0.20
    holdout_pct: float = 0.20

    # Statistical Significance Gate
    z_score_threshold: float = 3.0
    bonferroni_alpha: float = 0.05

    # Connection Settings & Timeouts
    connect_timeout: float = float(os.environ.get("DERIV_CONNECT_TIMEOUT", "10.0"))
    handshake_timeout: float = float(os.environ.get("DERIV_HANDSHAKE_TIMEOUT", "5.0"))
    request_timeout: float = float(os.environ.get("DERIV_REQUEST_TIMEOUT", "5.0"))
    max_retries: int = int(os.environ.get("DERIV_MAX_RETRIES", "3"))
    retry_backoff: float = float(os.environ.get("DERIV_RETRY_BACKOFF", "1.5"))
    ping_interval: float = float(os.environ.get("DERIV_PING_INTERVAL", "15.0"))
    ping_timeout: float = float(os.environ.get("DERIV_PING_TIMEOUT", "5.0"))

    # Decision Gates & Conservative EV Thresholds
    min_expected_ev: float = float(os.environ.get("MIN_EXPECTED_EV", "0.0"))
    min_conservative_ev: float = float(os.environ.get("MIN_CONSERVATIVE_EV", "0.0"))
    min_probability_margin: float = float(os.environ.get("MIN_PROBABILITY_MARGIN", "0.0"))
    min_validation_sample: int = int(os.environ.get("MIN_VALIDATION_SAMPLE", "100"))
    max_simulated_risk: float = float(os.environ.get("MAX_SIMULATED_RISK", "10.0"))

    # Safety Directives
    live_execution_disabled: bool = True  # Permanently locked: Real money execution is impossible
    demo_token: Optional[str] = os.environ.get("DERIV_DEMO_TOKEN", None)
    enable_demo_execution: bool = os.environ.get("ENABLE_DEMO_EXECUTION", "False").lower() in ("true", "1", "yes")


DEFAULT_CONFIG = TradingConfig()


async def query_proposal_payout_async(symbol: str = "R_75", app_id: str = "1089") -> Optional[float]:
    """Queries Deriv API WebSocket for live RUNHIGH proposal payout ratio."""
    try:
        from quote_engine import QuoteEngine
        qe = QuoteEngine(mode="live", app_id=app_id)
        up_q, _ = await qe.fetch_live_quotes_async(symbol=symbol, stake=2.0)
        if up_q is not None and up_q.payout > 0:
            return up_q.payout_ratio
    except Exception:
        pass
    return None
