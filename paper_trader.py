"""Paper Trading Mode for Deriv 5-Tick RUNHIGH / RUNLOW (Only Ups / Only Downs).

CRITICAL ARCHITECTURAL DIRECTIVE (NO LIVE MONEY):
- This engine NEVER calls purchase/buy endpoints.
- Simulates paper trade evaluation using real market prices, proposals, and execution lifecycles.
- Records predicted probabilities vs real-world outcomes for post-hoc edge verification.
"""
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import os
import json
import numpy as np
import pandas as pd

from quote_engine import QuoteEngine, ProposalQuote
from contract_model import ContractOutcomeModel


@dataclass
class PaperTradeRecord:
    timestamp: int
    symbol: str
    direction: str  # 'RUNHIGH' or 'RUNLOW'
    contract_type: str
    estimated_probability: float
    actual_quote: float  # Payout amount
    break_even_probability: float
    EV: float
    decision: str  # 'PAPER_TRADE' or 'NO_TRADE'
    actual_outcome: Optional[float]  # 1.0 (win), 0.0 (loss), or None
    profit_if_traded: float
    cumulative_PnL: float
    status_reason: str = "NORMAL"
    # V1.5 Extended Telemetry Fields
    market_state: str = ""
    probability_uncertainty: Tuple[float, float] = (0.0, 0.0)
    actual_proposal_price: float = 2.0
    total_payout: float = 0.0
    conservative_expected_value: float = 0.0
    simulated_entry_timestamp: Optional[int] = None
    rejection_reason: str = ""

    @property
    def selected_direction(self) -> str:
        return self.direction

    @property
    def hypothetical_pnl(self) -> float:
        return self.profit_if_traded

    @property
    def cumulative_hypothetical_pnl(self) -> float:
        return self.cumulative_PnL


class PaperTrader:
    """Safe paper-trading engine tracking hypothetical performance under real market conditions."""

    # Explicit Safety Constraint: Zero live-order execution capability
    LIVE_EXECUTION_DISABLED: bool = True

    def __init__(
        self,
        quote_engine: QuoteEngine,
        symbol: str = "R_75",
        default_stake: float = 2.0,
        min_required_ev: float = 0.0,
        min_required_conservative_ev: Optional[float] = None
    ):
        self.quote_engine = quote_engine
        self.symbol = symbol
        self.default_stake = default_stake
        self.min_required_ev = min_required_ev
        self.min_required_conservative_ev = min_required_conservative_ev
        self.records: List[PaperTradeRecord] = []
        self.cumulative_pnl: float = 0.0
        self.contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    def evaluate_opportunity(
        self,
        epoch: int,
        signal: str,
        estimated_prob: float,
        is_calibrated: bool = False,
        is_validated: bool = False,
        is_holdout_passed: bool = False,
        prices_window: Optional[List[float]] = None,
        signal_idx: int = 0,
        market_state: str = "",
        uncertainty: Optional[Tuple[float, float]] = None,
        conservative_ev: Optional[float] = None
    ) -> PaperTradeRecord:
        """Evaluates whether an observed state qualifies for a paper trade and resolves its forward outcome.
        
        Enforces the Dynamic EV & Validation Filter:
        Must satisfy:
        - estimated_prob > break_even
        - EV > min_required_ev
        - conservative_ev > 0 (if enforced)
        - is_calibrated is True
        - is_validated is True
        - is_holdout_passed is True
        - Quote is available
        Otherwise: records NO_TRADE.
        """
        sig_norm = signal.upper()
        dir_key = "UP" if sig_norm in ("UP", "RUNHIGH", "RISE") else ("DOWN" if sig_norm in ("DOWN", "RUNLOW", "FALL") else None)
        contract_type = "RUNHIGH" if dir_key == "UP" else ("RUNLOW" if dir_key == "DOWN" else "NONE")
        ci_bounds = uncertainty if uncertainty is not None else (max(0.0, estimated_prob - 0.02), min(1.0, estimated_prob + 0.02))

        if dir_key is None:
            rec = PaperTradeRecord(
                timestamp=epoch,
                symbol=self.symbol,
                direction="NONE",
                contract_type="NONE",
                estimated_probability=0.0,
                actual_quote=0.0,
                break_even_probability=0.0,
                EV=0.0,
                decision="NO_TRADE",
                actual_outcome=None,
                profit_if_traded=0.0,
                cumulative_PnL=round(self.cumulative_pnl, 2),
                status_reason="NO_SIGNAL",
                market_state=market_state,
                probability_uncertainty=(0.0, 0.0),
                rejection_reason="NO_SIGNAL"
            )
            self.records.append(rec)
            return rec

        status, quote = self.quote_engine.get_quote_status(dir_key, epoch=epoch)
        if quote is None:
            rec = PaperTradeRecord(
                timestamp=epoch,
                symbol=self.symbol,
                direction=sig_norm,
                contract_type=contract_type,
                estimated_probability=estimated_prob,
                actual_quote=0.0,
                break_even_probability=0.0,
                EV=0.0,
                decision="NO_TRADE",
                actual_outcome=None,
                profit_if_traded=0.0,
                cumulative_PnL=round(self.cumulative_pnl, 2),
                status_reason="QUOTE_UNAVAILABLE",
                market_state=market_state,
                probability_uncertainty=ci_bounds,
                rejection_reason="QUOTE_UNAVAILABLE"
            )
            self.records.append(rec)
            return rec

        be_prob = quote.implied_probability
        payout = quote.payout
        stake = quote.stake
        ev = (estimated_prob * payout) - stake
        cons_ev = conservative_ev if conservative_ev is not None else ((ci_bounds[0] * payout) - stake)

        # Multi-gate paper trade eligibility
        reasons = []
        if estimated_prob <= be_prob:
            reasons.append("PROB_BELOW_BREAK_EVEN")
        if ev <= self.min_required_ev:
            reasons.append("NEGATIVE_EV")
        if self.min_required_conservative_ev is not None and cons_ev <= self.min_required_conservative_ev:
            reasons.append("NEGATIVE_CONSERVATIVE_EV")
        if not is_calibrated:
            reasons.append("UNVERIFIED_CALIBRATION")
        if not is_validated:
            reasons.append("FAILED_VALIDATION")
        if not is_holdout_passed:
            reasons.append("FAILED_HOLDOUT")

        can_trade = len(reasons) == 0
        decision = "PAPER_TRADE" if can_trade else "NO_TRADE"
        reason_str = "VALIDATED_EDGE" if can_trade else ";".join(reasons)

        # Resolve forward outcome if prices window is provided (at least 7 ticks from signal: i to i+6)
        actual_outcome = None
        profit_if_traded = 0.0
        entry_timestamp = epoch + 1

        if prices_window is not None and len(prices_window) >= signal_idx + 7:
            prices_arr = np.array(prices_window, dtype=float)
            outcome_res = self.contract_model.evaluate_single_trade(
                prices=prices_arr,
                epochs=np.arange(len(prices_arr)),
                signal_idx=signal_idx,
                contract_type=contract_type
            )
            if outcome_res is not None:
                actual_outcome = 1.0 if outcome_res.is_win else 0.0
                if can_trade:
                    profit_if_traded = (payout - stake) if outcome_res.is_win else -stake
                    self.cumulative_pnl += profit_if_traded

        rec = PaperTradeRecord(
            timestamp=epoch,
            symbol=self.symbol,
            direction=sig_norm,
            contract_type=contract_type,
            estimated_probability=estimated_prob,
            actual_quote=payout,
            break_even_probability=be_prob,
            EV=round(ev, 4),
            decision=decision,
            actual_outcome=actual_outcome,
            profit_if_traded=round(profit_if_traded, 2),
            cumulative_PnL=round(self.cumulative_pnl, 2),
            status_reason=reason_str,
            market_state=market_state,
            probability_uncertainty=ci_bounds,
            actual_proposal_price=stake,
            total_payout=payout,
            conservative_expected_value=round(cons_ev, 4),
            simulated_entry_timestamp=entry_timestamp,
            rejection_reason=reason_str
        )
        self.records.append(rec)
        return rec


    def export_journal(self, file_path: str):
        """Exports paper trades to a CSV file."""
        if not self.records:
            return
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        df = pd.DataFrame([asdict(r) for r in self.records])
        df.to_csv(file_path, index=False)

    def summarize(self) -> Dict[str, Any]:
        """Summarizes paper trading journal metrics."""
        paper_trades = [r for r in self.records if r.decision == "PAPER_TRADE"]
        resolved = [r for r in paper_trades if r.actual_outcome is not None]
        wins = sum(1 for r in resolved if r.actual_outcome == 1.0)
        n = len(resolved)
        wr = (wins / n) if n > 0 else 0.0

        return {
            "total_evaluations": len(self.records),
            "paper_trades_taken": len(paper_trades),
            "resolved_trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": wr,
            "cumulative_pnl": round(self.cumulative_pnl, 2)
        }
