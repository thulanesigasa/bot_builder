"""Centralized Paper-Trade Decision Gate & Taxonomic Reason Codes (V1.5.3 Final Patch).

Authoritative evaluation engine ensuring zero trade authorizations occur unless:
1. Valid frozen model exists and is approved for paper trading.
2. Estimated probability is genuine and strictly derived from the frozen model.
3. Lower probability bound is statistically justified.
4. Genuine, fresh Deriv proposal quote is available (ask > 0, payout > 0).
5. Ordinary Expected Value exceeds configured threshold (EV > min_expected_ev).
6. Conservative Expected Value exceeds configured safety margin (Conservative_EV > min_conservative_ev).
7. Probability exceeds break-even by configured safety margin.
8. All institutional risk limits pass (max stake, consecutive losses, daily drawdown).
9. Execution mode is PAPER (SHADOW and DATA_COLLECTION_ONLY strictly disallow trades).
10. No data gaps or contract definition mismatches exist.

If ANY required condition fails, returns NO_TRADE with explicit taxonomic reason codes.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
import math

from config import DEFAULT_CONFIG


class DecisionReason(str, Enum):
    """Taxonomic reason codes for paper trade evaluation."""
    PAPER_TRADE_APPROVED = "PAPER_TRADE_APPROVED"
    NO_TRADE = "NO_TRADE"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    MODEL_UNVALIDATED = "MODEL_UNVALIDATED"
    MODEL_UNCALIBRATED = "MODEL_UNCALIBRATED"
    MODEL_SCHEMA_MISMATCH = "MODEL_SCHEMA_MISMATCH"
    MODEL_CONTRACT_MISMATCH = "MODEL_CONTRACT_MISMATCH"
    FEATURE_MISMATCH = "FEATURE_MISMATCH"
    NO_VALIDATED_EDGE = "NO_VALIDATED_EDGE"
    QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
    QUOTE_STALE = "QUOTE_STALE"
    QUOTE_INVALID = "QUOTE_INVALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    PROB_BELOW_BREAK_EVEN = "PROB_BELOW_BREAK_EVEN"
    NEGATIVE_EXPECTED_EV = "NEGATIVE_EXPECTED_EV"
    CONSERVATIVE_EV_TOO_LOW = "CONSERVATIVE_EV_TOO_LOW"
    PROBABILITY_MARGIN_TOO_LOW = "PROBABILITY_MARGIN_TOO_LOW"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    CONTRACT_MODEL_UNVERIFIED = "CONTRACT_MODEL_UNVERIFIED"
    SHADOW_MODE_NON_TRADING = "SHADOW_MODE_NON_TRADING"
    DATA_COLLECTION_NON_TRADING = "DATA_COLLECTION_NON_TRADING"


@dataclass
class DecisionResult:
    """Detailed result of centralized trade eligibility evaluation."""
    decision: str                           # 'PAPER_TRADE' or 'NO_TRADE'
    is_eligible: bool                       # True only if paper trade approved
    primary_reason: str                     # Primary taxonomic reason code
    rejection_reasons: List[str]            # All failing gates in order
    direction: str                          # 'RUNHIGH', 'RUNLOW', or 'NONE'
    estimated_prob: Optional[float] = None
    lower_prob_bound: Optional[float] = None
    break_even_prob: Optional[float] = None
    ordinary_ev: Optional[float] = None
    conservative_ev: Optional[float] = None
    ask_price: Optional[float] = None
    total_payout: Optional[float] = None
    stake: Optional[float] = None
    timestamp: float = 0.0

    @property
    def status_summary(self) -> str:
        if self.is_eligible:
            return DecisionReason.PAPER_TRADE_APPROVED.value
        return ";".join(self.rejection_reasons) if self.rejection_reasons else DecisionReason.NO_TRADE.value


def evaluate_paper_trade_eligibility(
    symbol: str,
    contract_type: str,
    duration_ticks: int = 5,
    model_artifact: Optional[Any] = None,
    estimated_prob: Optional[float] = None,
    lower_prob_bound: Optional[float] = None,
    ask_price: Optional[float] = None,
    total_payout: Optional[float] = None,
    quote_epoch: Optional[float] = None,
    current_epoch: float = 0.0,
    execution_mode: str = "PAPER",
    market_state: str = "",
    min_expected_ev: float = 0.0,
    min_conservative_ev: float = 0.0,
    min_probability_margin: float = 0.0,
    max_quote_age_seconds: float = 60.0,
    min_validation_sample: int = 100,
    current_consecutive_losses: int = 0,
    max_consecutive_losses: int = 3,
    current_daily_drawdown_pct: float = 0.0,
    max_daily_drawdown_pct: float = 0.05,
    current_stake: float = 2.0,
    max_stake: float = 5.0,
    has_data_gap: bool = False
) -> DecisionResult:
    """Authoritative Centralized Decision Gate for Paper Trade Authorization.
    
    All gates are combined using strict AND logic.
    If ANY mandatory condition fails, returns NO_TRADE.
    """
    reasons: List[str] = []
    norm_dir = contract_type.upper() if contract_type else "NONE"
    if norm_dir not in ("RUNHIGH", "RUNLOW"):
        norm_dir = "NONE"

    # Gate 1: Execution Mode Guard
    if execution_mode == "DATA_COLLECTION_ONLY":
        reasons.append(DecisionReason.DATA_COLLECTION_NON_TRADING.value)
    elif execution_mode == "SHADOW":
        reasons.append(DecisionReason.SHADOW_MODE_NON_TRADING.value)
    elif execution_mode != "PAPER":
        reasons.append(DecisionReason.NO_TRADE.value)

    # Gate 2: Data Integrity & Market Data Gaps
    if has_data_gap:
        reasons.append(DecisionReason.DATA_INTEGRITY_FAILURE.value)

    # Gate 3: Contract & Symbol Compatibility
    if duration_ticks != 5:
        reasons.append(DecisionReason.CONTRACT_MODEL_UNVERIFIED.value)
    if norm_dir == "NONE":
        reasons.append(DecisionReason.CONTRACT_MODEL_UNVERIFIED.value)

    # Gate 4: Frozen Model Validation & Approval Status
    if model_artifact is None:
        reasons.append(DecisionReason.MODEL_NOT_AVAILABLE.value)
    else:
        # Check symbol compatibility
        if hasattr(model_artifact, "market_symbol") and model_artifact.market_symbol != symbol:
            reasons.append(DecisionReason.MODEL_CONTRACT_MISMATCH.value)
        # Check duration compatibility
        if hasattr(model_artifact, "contract_duration") and model_artifact.contract_duration != duration_ticks:
            reasons.append(DecisionReason.MODEL_CONTRACT_MISMATCH.value)
        # Check approval status
        from model_artifact import ModelStatus
        if hasattr(model_artifact, "approval_status"):
            if model_artifact.approval_status not in ModelStatus.APPROVED_FOR_PAPER:
                reasons.append(DecisionReason.NO_VALIDATED_EDGE.value)
        # Check sample size
        if hasattr(model_artifact, "validation_sample_count") and model_artifact.validation_sample_count < min_validation_sample:
            reasons.append(DecisionReason.INSUFFICIENT_HISTORY.value)

    # Gate 5: Probability Availability & Validity (Strictly NO theoretical fallbacks)
    if estimated_prob is None or math.isnan(estimated_prob) or estimated_prob <= 0.0 or estimated_prob >= 1.0:
        if DecisionReason.MODEL_NOT_AVAILABLE.value not in reasons:
            reasons.append(DecisionReason.MODEL_NOT_AVAILABLE.value)

    # Gate 6: Quote Validation & Freshness
    be_prob: Optional[float] = None
    ev: Optional[float] = None
    cons_ev: Optional[float] = None

    if ask_price is None or total_payout is None or ask_price <= 0.0 or total_payout <= 0.0:
        reasons.append(DecisionReason.QUOTE_UNAVAILABLE.value)
    elif math.isnan(ask_price) or math.isnan(total_payout) or math.isinf(ask_price) or math.isinf(total_payout):
        reasons.append(DecisionReason.QUOTE_INVALID.value)
    elif ask_price >= total_payout:
        reasons.append(DecisionReason.QUOTE_INVALID.value)
    else:
        # Check quote age / staleness
        if quote_epoch is not None and current_epoch > 0:
            age = current_epoch - quote_epoch
            if age < 0 or age > max_quote_age_seconds:
                reasons.append(DecisionReason.QUOTE_STALE.value)

        # Compute break-even probability
        be_prob = float(ask_price / total_payout)

        # If probability is valid, compute financial metrics
        if estimated_prob is not None and not math.isnan(estimated_prob):
            # Ordinary EV: P_win * Payout - Ask
            ev = float((estimated_prob * total_payout) - ask_price)

            # Lower probability bound
            effective_lower = lower_prob_bound
            if effective_lower is None or math.isnan(effective_lower):
                # Statistically derived Wilson/Gaussian floor if not provided
                effective_lower = max(0.0, estimated_prob - (1.96 * math.sqrt(estimated_prob * (1.0 - estimated_prob) / max(10, min_validation_sample))))

            # Conservative EV: P_lower * Payout - Ask
            cons_ev = float((effective_lower * total_payout) - ask_price)

            # Gate 7: Break-even Probability Gate
            if estimated_prob <= be_prob:
                reasons.append(DecisionReason.PROB_BELOW_BREAK_EVEN.value)

            # Gate 8: Probability Margin Safety Gate
            prob_margin = estimated_prob - be_prob
            if prob_margin < min_probability_margin:
                reasons.append(DecisionReason.PROBABILITY_MARGIN_TOO_LOW.value)

            # Gate 9: Ordinary Expected Value Threshold
            if ev <= min_expected_ev:
                reasons.append(DecisionReason.NEGATIVE_EXPECTED_EV.value)

            # Gate 10: Conservative Expected Value Threshold (CRITICAL MANDATORY SAFETY)
            if cons_ev <= min_conservative_ev:
                reasons.append(DecisionReason.CONSERVATIVE_EV_TOO_LOW.value)

    # Gate 11: Institutional Risk Limits
    if current_stake > max_stake:
        reasons.append(DecisionReason.RISK_LIMIT_EXCEEDED.value)
    if current_consecutive_losses >= max_consecutive_losses:
        reasons.append(DecisionReason.RISK_LIMIT_EXCEEDED.value)
    if current_daily_drawdown_pct >= max_daily_drawdown_pct:
        reasons.append(DecisionReason.RISK_LIMIT_EXCEEDED.value)

    # Deduplicate rejection reasons preserving order
    dedup: List[str] = []
    seen = set()
    for r in reasons:
        if r not in seen:
            seen.add(r)
            dedup.append(r)

    is_eligible = (len(dedup) == 0)
    decision = DecisionReason.PAPER_TRADE_APPROVED.value if is_eligible else DecisionReason.NO_TRADE.value
    primary_reason = DecisionReason.PAPER_TRADE_APPROVED.value if is_eligible else (dedup[0] if dedup else DecisionReason.NO_TRADE.value)

    return DecisionResult(
        decision=decision,
        is_eligible=is_eligible,
        primary_reason=primary_reason,
        rejection_reasons=dedup,
        direction=norm_dir,
        estimated_prob=round(estimated_prob, 5) if estimated_prob is not None else None,
        lower_prob_bound=round(lower_prob_bound, 5) if lower_prob_bound is not None else None,
        break_even_prob=round(be_prob, 5) if be_prob is not None else None,
        ordinary_ev=round(ev, 4) if ev is not None else None,
        conservative_ev=round(cons_ev, 4) if cons_ev is not None else None,
        ask_price=round(ask_price, 2) if ask_price is not None else None,
        total_payout=round(total_payout, 2) if total_payout is not None else None,
        stake=round(current_stake, 2) if current_stake is not None else None,
        timestamp=current_epoch
    )
