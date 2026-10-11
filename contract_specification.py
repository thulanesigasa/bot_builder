"""Canonical Contract Outcome & Broker Settlement Specification (V1.7.3).

Centrally defines the contract lifecycle, mathematical outcome evaluation,
and broker-settlement mapping for Deriv RUNHIGH and RUNLOW contracts.

Official Broker Documentation & References:
------------------------------------------
Broker: Deriv (Deriv Limited / Deriv Group Services)
API Endpoint: wss://api.derivws.com/trading/v1/options/ws/public
Documentation URL: https://developers.deriv.com/docs/api-guide/contracts/
Access Date: 2026-10-11
Contract Family: High/Low Run Contracts (Only Ups / Only Downs)
Deriv Contract Identifiers:
  - "RUNHIGH" (Commercial Name: "Only Ups")
  - "RUNLOW"  (Commercial Name: "Only Downs")
Underlying Synthetic Asset: Volatility 75 Index ("R_75")
Contract Duration: 5 ticks (duration: 5, duration_unit: "t")
Contract Basis: Stake (e.g. 2.00 USD)
Payout Terms: Fixed return on binary win (e.g. 61.07 USD); 0.00 on loss.

Broker Settlement Lifecycle & Rules:
------------------------------------
1. Contract Start: Order submitted and accepted by Deriv broker matching engine.
2. Entry Spot (S_0): The first tick arriving after contract start establishes the entry spot.
3. 5-Tick Transition Path:
     Step 1: S_0 -> S_1 (first forward tick after entry)
     Step 2: S_1 -> S_2 (second forward tick after entry)
     Step 3: S_2 -> S_3 (third forward tick after entry)
     Step 4: S_3 -> S_4 (fourth forward tick after entry)
     Step 5: S_4 -> S_5 (fifth forward tick after entry, Exit / Expiry Spot)
4. Monotonic Win Condition:
   - RUNHIGH (Only Ups): Wins iff S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4.
     Every consecutive tick movement must be strictly positive.
   - RUNLOW (Only Downs): Wins iff S_1 < S_0 AND S_2 < S_1 AND S_3 < S_2 AND S_4 < S_3 AND S_5 < S_4.
     Every consecutive tick movement must be strictly negative.
5. Immediate Loss Conditions:
   - Flat / Equal ticks (S_{k} == S_{k-1}) result in an immediate contract loss.
   - Reversal ticks (S_{k} < S_{k-1} for RUNHIGH, or S_{k} > S_{k-1} for RUNLOW) result in an immediate loss.
   - Dual Loss Reality: In oscillating market sequences (~92-94% empirical frequency),
     both RUNHIGH and RUNLOW lose simultaneously.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Any, Optional


# Canonical Outcome Classifications (V1.7.3 Part D Section 14)
class OutcomeClassification(str, Enum):
    RESEARCH_OUTCOME_RECONSTRUCTED = "RESEARCH_OUTCOME_RECONSTRUCTED"
    RESEARCH_OUTCOME_INCOMPLETE = "RESEARCH_OUTCOME_INCOMPLETE"
    RESEARCH_OUTCOME_DATA_GAP = "RESEARCH_OUTCOME_DATA_GAP"
    CONTRACT_MAPPING_UNVERIFIED = "CONTRACT_MAPPING_UNVERIFIED"
    DEMO_SETTLEMENT_MATCH_VERIFIED = "DEMO_SETTLEMENT_MATCH_VERIFIED"


# Legacy and Compatibility Status Aliases
STATUS_RESOLVED = "RESOLVED"
STATUS_RECONSTRUCTED = "OUTCOME_RECONSTRUCTED"
STATUS_DATA_GAP = "OUTCOME_DATA_GAP"
STATUS_INCOMPLETE = "OUTCOME_INCOMPLETE"
STATUS_PENDING = "OUTCOME_PENDING"


@dataclass(frozen=True)
class CanonicalContractSpec:
    contract_type: str                  # 'RUNHIGH' or 'RUNLOW'
    commercial_name: str                # 'Only Ups' or 'Only Downs'
    symbol: str = "R_75"
    duration_ticks: int = 5
    required_ticks_total: int = 6       # S_0 entry + 5 movements
    gap_threshold_seconds: float = 5.0
    official_source_url: str = "https://developers.deriv.com/docs/api-guide/contracts/"
    access_date: str = "2026-10-11"
    resolver_version: str = "V1.7.3"


CANONICAL_RUNHIGH_SPEC = CanonicalContractSpec(contract_type="RUNHIGH", commercial_name="Only Ups")
CANONICAL_RUNLOW_SPEC = CanonicalContractSpec(contract_type="RUNLOW", commercial_name="Only Downs")


def evaluate_5tick_monotonic_outcome(
    prices: List[float],
    require_full_sequence: bool = True
) -> Tuple[Optional[float], Optional[float], str]:
    """Centrally evaluates 5-tick monotonic contract outcomes for RUNHIGH and RUNLOW.
    
    Parameters:
        prices: List of prices starting with Entry Spot S_0, followed by S_1..S_5.
                Must contain exactly 6 prices for a complete evaluation.
        require_full_sequence: If True, sequences with len != 6 return None win rates.
        
    Returns:
        (runhigh_win, runlow_win, outcome_classification)
        - runhigh_win: 1.0 (win), 0.0 (loss), or None (incomplete)
        - runlow_win:  1.0 (win), 0.0 (loss), or None (incomplete)
        - classification: OutcomeClassification value string
    """
    if len(prices) < 6:
        if require_full_sequence:
            return None, None, OutcomeClassification.RESEARCH_OUTCOME_INCOMPLETE.value
        prices = prices  # fallback for partial inspections

    if len(prices) < 6:
        return None, None, OutcomeClassification.RESEARCH_OUTCOME_INCOMPLETE.value

    p = [float(x) for x in prices[:6]]

    # Strict 5-movement comparisons:
    # RUNHIGH: S_1 > S_0 and S_2 > S_1 and S_3 > S_2 and S_4 > S_3 and S_5 > S_4
    is_runhigh = all(p[k] > p[k - 1] for k in range(1, 6))
    
    # RUNLOW:  S_1 < S_0 and S_2 < S_1 and S_3 < S_2 and S_4 < S_3 and S_5 < S_4
    is_runlow = all(p[k] < p[k - 1] for k in range(1, 6))

    rh_win = 1.0 if is_runhigh else 0.0
    rl_win = 1.0 if is_runlow else 0.0

    return rh_win, rl_win, OutcomeClassification.RESEARCH_OUTCOME_RECONSTRUCTED.value


CONTRACT_TYPE_RUNHIGH = "RUNHIGH"
CONTRACT_TYPE_RUNLOW = "RUNLOW"

STATUS_OUTCOME_WON = "WON"
STATUS_OUTCOME_LOST = "LOST"
STATUS_OUTCOME_INCOMPLETE = "INCOMPLETE"
STATUS_OUTCOME_DATA_GAP = "DATA_GAP"

REASON_MONOTONIC_RUNHIGH_SATISFIED = "MONOTONIC_RUNHIGH_SATISFIED"
REASON_MONOTONIC_RUNLOW_SATISFIED = "MONOTONIC_RUNLOW_SATISFIED"
REASON_EQUALITY_VIOLATION = "EQUALITY_VIOLATION"
REASON_REVERSAL_VIOLATION = "REVERSAL_VIOLATION"
REASON_ALL_ABOVE_ENTRY_BUT_NOT_MONOTONIC = "ALL_ABOVE_ENTRY_BUT_NOT_MONOTONIC"
REASON_ALL_BELOW_ENTRY_BUT_NOT_MONOTONIC = "ALL_BELOW_ENTRY_BUT_NOT_MONOTONIC"
REASON_INSUFFICIENT_TICKS = "INSUFFICIENT_TICKS"
REASON_DATA_GAP_DETECTED = "DATA_GAP_DETECTED"


@dataclass(frozen=True)
class ContractOutcomeResult:
    contract_type: str
    outcome_status: str
    is_win: bool
    rejection_reason: str
    intermediate_evaluations: List[bool]
    prices: List[float]


def evaluate_canonical_outcome(
    contract_type: str,
    prices: List[float],
    data_gap: bool = False
) -> ContractOutcomeResult:
    """Evaluates a single contract outcome with step-by-step diagnostic verification."""
    if data_gap:
        return ContractOutcomeResult(
            contract_type=contract_type,
            outcome_status=STATUS_OUTCOME_DATA_GAP,
            is_win=False,
            rejection_reason=REASON_DATA_GAP_DETECTED,
            intermediate_evaluations=[],
            prices=prices,
        )

    if len(prices) < 6:
        return ContractOutcomeResult(
            contract_type=contract_type,
            outcome_status=STATUS_OUTCOME_INCOMPLETE,
            is_win=False,
            rejection_reason=REASON_INSUFFICIENT_TICKS,
            intermediate_evaluations=[],
            prices=prices,
        )

    p = [float(x) for x in prices[:6]]
    ctype = contract_type.upper()
    steps = []

    if ctype == CONTRACT_TYPE_RUNHIGH:
        # Check step-by-step
        has_equality = False
        has_reversal = False
        for k in range(1, 6):
            if p[k] == p[k - 1]:
                has_equality = True
                steps.append(False)
            elif p[k] > p[k - 1]:
                steps.append(True)
            else:
                has_reversal = True
                steps.append(False)

        all_above_entry = all(p[k] > p[0] for k in range(1, 6))

        if all(steps):
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_WON,
                is_win=True,
                rejection_reason=REASON_MONOTONIC_RUNHIGH_SATISFIED,
                intermediate_evaluations=steps,
                prices=p,
            )
        elif has_equality:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_EQUALITY_VIOLATION,
                intermediate_evaluations=steps,
                prices=p,
            )
        elif all_above_entry:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_ALL_ABOVE_ENTRY_BUT_NOT_MONOTONIC,
                intermediate_evaluations=steps,
                prices=p,
            )
        else:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_REVERSAL_VIOLATION,
                intermediate_evaluations=steps,
                prices=p,
            )

    elif ctype == CONTRACT_TYPE_RUNLOW:
        has_equality = False
        has_reversal = False
        for k in range(1, 6):
            if p[k] == p[k - 1]:
                has_equality = True
                steps.append(False)
            elif p[k] < p[k - 1]:
                steps.append(True)
            else:
                has_reversal = True
                steps.append(False)

        all_below_entry = all(p[k] < p[0] for k in range(1, 6))

        if all(steps):
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_WON,
                is_win=True,
                rejection_reason=REASON_MONOTONIC_RUNLOW_SATISFIED,
                intermediate_evaluations=steps,
                prices=p,
            )
        elif has_equality:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_EQUALITY_VIOLATION,
                intermediate_evaluations=steps,
                prices=p,
            )
        elif all_below_entry:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_ALL_BELOW_ENTRY_BUT_NOT_MONOTONIC,
                intermediate_evaluations=steps,
                prices=p,
            )
        else:
            return ContractOutcomeResult(
                contract_type=ctype,
                outcome_status=STATUS_OUTCOME_LOST,
                is_win=False,
                rejection_reason=REASON_REVERSAL_VIOLATION,
                intermediate_evaluations=steps,
                prices=p,
            )

    raise ValueError(f"Unknown contract_type: {contract_type}")


def evaluate_tick_stream_outcome(
    entry_price: float,
    subsequent_prices: List[float]
) -> Tuple[Optional[float], Optional[float], str]:
    """Evaluates outcome given S_0 entry price and exactly 5 subsequent forward ticks."""
    full_path = [entry_price] + list(subsequent_prices)
    return evaluate_5tick_monotonic_outcome(full_path)

