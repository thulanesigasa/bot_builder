"""Independent adaptive anti-martingale research sizing state machine.

This module does NOT submit MetaTrader orders; exposure ceilings are evaluated
by the eventual MQL5 paper executor against actual symbol specifications.
"""
from dataclasses import dataclass

@dataclass
class AdaptiveState:
    balance: float = 50.0
    stage: int = 0
    peak: float = 50.0
    halted: bool = False

# Stage changes only after a fully closed basket, never a single still-open leg.
# Start at 7 simulated positions; loss reduces to 4, 3, 1.
POSITIONS = (7, 8, 9, 10)
LOSS_POSITIONS = (4, 3, 1)
MIN_LOT = 0.01
MAX_FRACTIONAL_DRAWDOWN = 0.70  # stress-test ceiling, not guaranteed live risk

def allowable_positions(state: AdaptiveState) -> int:
    if state.halted: return 0
    if state.stage >= 0:
        return POSITIONS[min(state.stage,len(POSITIONS)-1)]
    return LOSS_POSITIONS[min(-state.stage-1,len(LOSS_POSITIONS)-1)]

def finish_cycle(state: AdaptiveState, net_pnl: float) -> AdaptiveState:
    if state.halted:
        return state
    initial = state.balance
    state.balance += net_pnl
    state.peak = max(state.peak,state.balance)
    if state.balance <= 50.0*(1.0-MAX_FRACTIONAL_DRAWDOWN) or state.balance<=0:
        state.halted=True
        return state
    if net_pnl > 0:
        state.stage=min(state.stage+1, len(POSITIONS)-1)
    elif net_pnl < 0:
        state.stage=max(state.stage-1,-len(LOSS_POSITIONS))
    return state

def evaluate_basket(state:AdaptiveState, min_lot_stop_loss_usd:float,
                    available_margin_usd:float, margin_per_min_lot_usd:float,
                    lot:float=MIN_LOT)->dict:
    n=allowable_positions(state)
    if any(v<=0 for v in (min_lot_stop_loss_usd, margin_per_min_lot_usd,lot)):
        return {"permitted":False,"reason":"INVALID_BROKER_SPEC","positions":0}
    if lot < MIN_LOT:
        return {"permitted":False,"reason":"BELOW_MIN_LOT","positions":0}
    # Snapshot caps aggregate realized STOP risk, plus a margin feasibility check.
    max_risk=max(0.0,state.balance-50.0*(1.0-MAX_FRACTIONAL_DRAWDOWN))
    required_loss=n*(lot/MIN_LOT)*min_lot_stop_loss_usd
    required_margin=n*(lot/MIN_LOT)*margin_per_min_lot_usd
    ok=(not state.halted and n>0 and required_loss<=max_risk
        and required_margin<=available_margin_usd)
    return {"permitted":ok,"reason":"PAPER_BASKET_ONLY" if ok else "RISK_OR_MARGIN_BLOCK",
            "positions":n if ok else 0,"requested_positions":n,
            "aggregate_stop_risk":required_loss,"required_margin":required_margin}
