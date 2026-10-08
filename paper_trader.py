"""Paper Trading Mode for Deriv 5-Tick RUNHIGH / RUNLOW (Only Ups / Only Downs) (V1.5.2).

CRITICAL ARCHITECTURAL DIRECTIVE (NO LIVE MONEY):
- This engine NEVER calls purchase/buy endpoints.
- Simulates paper trade evaluation using real market prices, proposals, and execution lifecycles.
- Strictly distinguishes between:
  1. HISTORICAL_RECONSTRUCTION (Offline historical backtesting)
  2. SHADOW_PREDICTION (Forward observation without hypothetical execution)
  3. FORWARD_PAPER_TRADE (Live synchronized paper execution)
  4. DEMO_ACCOUNT_EXECUTION (Isolated virtual demo test harness)
- Records predicted probabilities vs real-world outcomes for post-hoc edge verification.
"""
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Tuple
import os
import json
import uuid
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
    # Extended Telemetry Fields
    market_state: str = ""
    probability_uncertainty: Tuple[float, float] = (0.0, 0.0)
    actual_proposal_price: float = 2.0
    total_payout: float = 0.0
    conservative_expected_value: float = 0.0
    simulated_entry_timestamp: Optional[int] = None
    rejection_reason: str = ""
    # V1.5.2 Provenance & Execution Mode Fields
    signal_id: str = ""
    trade_mode: str = "FORWARD_PAPER_TRADE"  # HISTORICAL_RECONSTRUCTION, SHADOW_PREDICTION, FORWARD_PAPER_TRADE, DEMO_ACCOUNT_EXECUTION
    settlement_certainty: str = "CERTAIN"    # CERTAIN, UNCERTAIN_SETTLEMENT, INSUFFICIENT_FORWARD_TICKS

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
        min_required_conservative_ev: Optional[float] = 0.0
    ):
        self.quote_engine = quote_engine
        self.symbol = symbol
        self.default_stake = default_stake
        self.min_required_ev = min_required_ev
        self.min_required_conservative_ev = min_required_conservative_ev if min_required_conservative_ev is not None else 0.0
        self.records: List[PaperTradeRecord] = []
        self.cumulative_pnl: float = 0.0
        self.contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    def evaluate_opportunity(
        self,
        epoch: int,
        signal: str,
        estimated_prob: Optional[float],
        is_calibrated: bool = False,
        is_validated: bool = False,
        is_holdout_passed: bool = False,
        prices_window: Optional[List[float]] = None,
        signal_idx: int = 0,
        market_state: str = "",
        uncertainty: Optional[Tuple[float, float]] = None,
        conservative_ev: Optional[float] = None,
        trade_mode: str = "FORWARD_PAPER_TRADE",
        is_quote_stale: bool = False,
        has_data_gap: bool = False
    ) -> PaperTradeRecord:
        """Evaluates whether an observed state qualifies for a paper trade and resolves its forward outcome.
        
        Enforces the Dynamic EV & Validation Filter:
        Must satisfy:
        - estimated_prob is not None and > break_even
        - EV > min_required_ev
        - conservative_ev > min_required_conservative_ev (MANDATORY REQUIREMENT)
        - is_calibrated is True
        - is_validated is True
        - is_holdout_passed is True
        - Quote is available & fresh
        - No market data gaps
        Otherwise: records NO_TRADE with explicit taxonomic reason.
        """
        sig_id = str(uuid.uuid4())[:8]
        sig_norm = signal.upper() if signal else ""
        dir_key = "UP" if sig_norm in ("UP", "RUNHIGH", "RISE") else ("DOWN" if sig_norm in ("DOWN", "RUNLOW", "FALL") else None)
        contract_type = "RUNHIGH" if dir_key == "UP" else ("RUNLOW" if dir_key == "DOWN" else "NONE")

        if estimated_prob is None:
            rec = PaperTradeRecord(
                timestamp=epoch,
                symbol=self.symbol,
                direction=sig_norm or "NONE",
                contract_type=contract_type,
                estimated_probability=0.0,
                actual_quote=0.0,
                break_even_probability=0.0,
                EV=0.0,
                decision="NO_TRADE",
                actual_outcome=None,
                profit_if_traded=0.0,
                cumulative_PnL=round(self.cumulative_pnl, 2),
                status_reason="MODEL_NOT_AVAILABLE",
                market_state=market_state,
                probability_uncertainty=(0.0, 0.0),
                rejection_reason="MODEL_NOT_AVAILABLE",
                signal_id=sig_id,
                trade_mode=trade_mode,
                settlement_certainty="CERTAIN"
            )
            self.records.append(rec)
            return rec

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
                rejection_reason="NO_SIGNAL",
                signal_id=sig_id,
                trade_mode=trade_mode,
                settlement_certainty="CERTAIN"
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
                rejection_reason="QUOTE_UNAVAILABLE",
                signal_id=sig_id,
                trade_mode=trade_mode,
                settlement_certainty="CERTAIN"
            )
            self.records.append(rec)
            return rec

        be_prob = quote.implied_probability
        payout = quote.payout
        stake = quote.stake
        ev = (estimated_prob * payout) - stake
        cons_ev = conservative_ev if conservative_ev is not None else ((ci_bounds[0] * payout) - stake)

        # Multi-gate paper trade eligibility with taxonomic reasons
        reasons = []
        if is_quote_stale:
            reasons.append("QUOTE_STALE")
        if has_data_gap:
            reasons.append("MARKET_DATA_GAP")
        if estimated_prob <= be_prob:
            reasons.append("PROB_BELOW_BREAK_EVEN")
        if ev <= self.min_required_ev:
            reasons.append("NEGATIVE_EV")
            reasons.append("NEGATIVE_EXPECTED_EV")

        # Mandatory Conservative EV Gate
        eff_min_cons_ev = self.min_required_conservative_ev if self.min_required_conservative_ev is not None else 0.0
        if cons_ev <= eff_min_cons_ev:
            reasons.append("NEGATIVE_CONSERVATIVE_EV")
            reasons.append("CONSERVATIVE_EV_TOO_LOW")

        if not is_calibrated:
            reasons.append("UNVERIFIED_CALIBRATION")
            reasons.append("MODEL_UNCALIBRATED")
        if not is_validated:
            reasons.append("FAILED_VALIDATION")
        if not is_holdout_passed:
            reasons.append("FAILED_HOLDOUT")
        if not is_validated or not is_holdout_passed:
            reasons.append("NO_VALIDATED_EDGE")

        # Deduplicate reasons while preserving order
        seen_reasons = set()
        clean_reasons = []
        for r in reasons:
            if r not in seen_reasons:
                seen_reasons.add(r)
                clean_reasons.append(r)

        can_trade = len(clean_reasons) == 0
        decision = "PAPER_TRADE" if can_trade else "NO_TRADE"
        reason_str = "VALIDATED_EDGE" if can_trade else ";".join(clean_reasons)

        # Resolve forward outcome if prices window is provided (at least 7 ticks from signal: i to i+6)
        actual_outcome = None
        profit_if_traded = 0.0
        entry_timestamp = epoch + 1
        certainty = "CERTAIN"

        if prices_window is not None:
            if len(prices_window) >= signal_idx + 7:
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
            else:
                certainty = "INSUFFICIENT_FORWARD_TICKS"

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
            rejection_reason=reason_str,
            signal_id=sig_id,
            trade_mode=trade_mode,
            settlement_certainty=certainty
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
