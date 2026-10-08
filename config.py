"""Configuration settings and direction-specific quote parameters for Deriv 5-Tick UP/DOWN Engine.
Supports standard Rise/Fall as well as asymmetric high-payout contracts ($2 -> $61.03).
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradingConfig:
    # Asset & Contract
    symbol: str = "R_75"
    duration_ticks: int = 5
    contract_family: str = "rise_fall"  # 'rise_fall' or 'high_payout'

    # Direction-Specific Payouts (Default: 0.95 profit per $1 stake -> 1.95 total return)
    up_payout_ratio: float = 0.95
    down_payout_ratio: float = 0.95
    default_stake: float = 1.0

    # High-Payout Contract Preset ($2 -> $61.03)
    high_payout_stake: float = 2.0
    high_payout_total: float = 61.03

    # API Endpoints
    app_id: str = os.environ.get("DERIV_APP_ID", "1089")
    ws_url: str = os.environ.get("DERIV_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public")

    # Risk Management (Updated to conservative institutional parameters per V1.1)
    initial_balance: float = 1000.0
    risk_per_trade_pct: float = 0.0025  # 0.25% per trade (lowered from 1% to prevent loss cluster drawdowns)
    max_stake: float = 5.0
    max_consecutive_losses: int = 3
    cooldown_ticks: int = 50
    daily_loss_limit_pct: float = 0.05  # 5% max daily drawdown (resets per UTC day)

    # 3-Way Statistical Split Protocol
    train_pct: float = 0.60
    val_pct: float = 0.20
    holdout_pct: float = 0.20

    # Statistical Significance Gate
    z_score_threshold: float = 3.0  # Bonferroni multiple-testing guard
    bonferroni_alpha: float = 0.05


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

