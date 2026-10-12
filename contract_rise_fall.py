"""Dedicated Deriv Rise/Fall (CALL/PUT) Contract Specification & Audit Engine (V1.8.0).

Defines canonical broker semantics for Rise/Fall contracts:
  - Rise (CALL): Wins iff ExpirySpot > EntrySpot (strictly higher)
  - Fall (PUT):  Wins iff ExpirySpot < EntrySpot (strictly lower)
  - Equality:    ExpirySpot == EntrySpot is a strict broker LOSS (0) for both CALL and PUT

Non-Purchasing Entry Proxies:
  - MAPPING_V1_NEXT_TICK_ENTRY (Canonical Broker Proxy):
      Entry spot is the 1st forward tick after signal decision commitment.
      Expiry spot is the D-th tick following the entry tick (index D in forward ticks).
  - MAPPING_V0_SIGNAL_TICK_ENTRY (Research Legacy Proxy):
      Entry spot is the signal tick price at decision time.
      Expiry spot is the D-th tick following signal (index D-1 in forward ticks).

Safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

LIVE_EXECUTION_DISABLED: bool = True

MAPPING_V1_NEXT_TICK_ENTRY = "MAPPING_V1_NEXT_TICK_ENTRY"
MAPPING_V0_SIGNAL_TICK_ENTRY = "MAPPING_V0_SIGNAL_TICK_ENTRY"


class RiseFallDirection(str, Enum):
    """Canonical contract directions for Rise/Fall."""
    CALL = "CALL"  # Rise
    PUT = "PUT"    # Fall


class RiseFallOutcome(int, Enum):
    """Contract binary outcome."""
    LOSS = 0
    WIN = 1


@dataclass
class RiseFallContractSpec:
    """Canonical broker specification for Rise/Fall contract."""
    contract_type: str                  # 'CALL' or 'PUT'
    duration_ticks: int                 # 1 to 10 ticks
    symbol: str                         # e.g. 'R_100', '1HZ100V', etc.
    entry_mapping: str = MAPPING_V1_NEXT_TICK_ENTRY
    barrier_equality_rule: str = "STRICT_INEQUALITY_LOSS_ON_TIE"

    def __post_init__(self):
        c = self.contract_type.upper()
        if c in ("RISE", "CALL"):
            self.contract_type = RiseFallDirection.CALL.value
        elif c in ("FALL", "PUT"):
            self.contract_type = RiseFallDirection.PUT.value
        else:
            raise ValueError(f"Invalid Rise/Fall contract_type: {self.contract_type}. Must be CALL or PUT.")

        if self.duration_ticks < 1 or self.duration_ticks > 10:
            raise ValueError(
                f"Invalid duration_ticks: {self.duration_ticks}. Deriv tick contracts require 1 <= duration <= 10."
            )


@dataclass
class RiseFallEvaluationResult:
    """Detailed evaluation result of a resolved Rise/Fall contract."""
    contract_type: str
    duration_ticks: int
    entry_mapping: str
    signal_price: float
    entry_spot: float
    expiry_spot: float
    outcome: int                        # 1 for WIN, 0 for LOSS
    is_win: bool
    is_tie: bool
    price_delta: float
    forward_tick_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "duration_ticks": self.duration_ticks,
            "entry_mapping": self.entry_mapping,
            "signal_price": self.signal_price,
            "entry_spot": self.entry_spot,
            "expiry_spot": self.expiry_spot,
            "outcome": self.outcome,
            "is_win": self.is_win,
            "is_tie": self.is_tie,
            "price_delta": self.price_delta,
            "forward_tick_count": self.forward_tick_count,
        }


@dataclass
class EntryMappingDiscrepancyRecord:
    """Record comparing outcome under V0 vs V1 entry mappings on the same tick sequence."""
    contract_type: str
    duration_ticks: int
    signal_price: float
    forward_ticks: List[float]
    v0_entry_spot: float
    v0_expiry_spot: float
    v0_outcome: int
    v1_entry_spot: float
    v1_expiry_spot: float
    v1_outcome: int
    outcomes_disagree: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "duration_ticks": self.duration_ticks,
            "signal_price": self.signal_price,
            "forward_ticks": self.forward_ticks,
            "v0_entry_spot": self.v0_entry_spot,
            "v0_expiry_spot": self.v0_expiry_spot,
            "v0_outcome": self.v0_outcome,
            "v1_entry_spot": self.v1_entry_spot,
            "v1_expiry_spot": self.v1_expiry_spot,
            "v1_outcome": self.v1_outcome,
            "outcomes_disagree": self.outcomes_disagree,
        }


class RiseFallOutcomeResolver:
    """Resolves Rise/Fall contract outcomes according to Deriv broker semantics."""

    @staticmethod
    def evaluate_spots(
        entry_spot: float,
        expiry_spot: float,
        contract_type: str,
    ) -> int:
        """Core canonical outcome evaluator.
        
        Broker semantics (Deriv API longcode verification):
          - CALL / RISE: 1 if expiry_spot > entry_spot else 0
          - PUT / FALL:  1 if expiry_spot < entry_spot else 0
          - Tie (expiry == entry): 0 for both (strictly higher/lower required)
        """
        c = contract_type.upper()
        if expiry_spot == entry_spot:
            # Strict inequality: tie is a loss for both CALL and PUT
            return RiseFallOutcome.LOSS.value

        if c in ("CALL", "RISE"):
            return RiseFallOutcome.WIN.value if expiry_spot > entry_spot else RiseFallOutcome.LOSS.value
        elif c in ("PUT", "FALL"):
            return RiseFallOutcome.WIN.value if expiry_spot < entry_spot else RiseFallOutcome.LOSS.value
        else:
            raise ValueError(f"Unknown contract_type: {contract_type}. Expected CALL or PUT.")

    @classmethod
    def evaluate_contract(
        cls,
        signal_price: float,
        forward_ticks: List[float],
        contract_type: str,
        duration_ticks: int,
        entry_mapping: str = MAPPING_V1_NEXT_TICK_ENTRY,
    ) -> RiseFallEvaluationResult:
        """Evaluates a Rise/Fall contract given signal price and subsequent forward ticks.
        
        Args:
            signal_price: Market price at decision epoch.
            forward_ticks: Subsequent forward tick prices received strictly after signal.
            contract_type: 'CALL' or 'PUT'.
            duration_ticks: Duration D (1 to 10 ticks).
            entry_mapping: MAPPING_V1_NEXT_TICK_ENTRY or MAPPING_V0_SIGNAL_TICK_ENTRY.
        """
        c = contract_type.upper()
        if c in ("RISE", "CALL"):
            norm_c = RiseFallDirection.CALL.value
        elif c in ("FALL", "PUT"):
            norm_c = RiseFallDirection.PUT.value
        else:
            raise ValueError(f"Unknown contract_type: {contract_type}")

        if duration_ticks < 1 or duration_ticks > 10:
            raise ValueError(f"duration_ticks must be between 1 and 10, got {duration_ticks}")

        n_forward = len(forward_ticks)

        if entry_mapping == MAPPING_V1_NEXT_TICK_ENTRY:
            # Broker standard: entry spot is forward_ticks[0]
            # Expiry spot is forward_ticks[duration_ticks]
            # Requires at least duration_ticks + 1 forward ticks!
            needed_ticks = duration_ticks + 1
            if n_forward < needed_ticks:
                raise ValueError(
                    f"Insufficient forward ticks for V1 next-tick entry: needed {needed_ticks}, got {n_forward}."
                )
            entry_spot = forward_ticks[0]
            expiry_spot = forward_ticks[duration_ticks]
        elif entry_mapping == MAPPING_V0_SIGNAL_TICK_ENTRY:
            # Signal tick entry: entry spot is signal_price
            # Expiry spot is forward_ticks[duration_ticks - 1]
            # Requires at least duration_ticks forward ticks!
            needed_ticks = duration_ticks
            if n_forward < needed_ticks:
                raise ValueError(
                    f"Insufficient forward ticks for V0 signal-tick entry: needed {needed_ticks}, got {n_forward}."
                )
            entry_spot = signal_price
            expiry_spot = forward_ticks[duration_ticks - 1]
        else:
            raise ValueError(f"Unknown entry_mapping: {entry_mapping}")

        outcome = cls.evaluate_spots(entry_spot=entry_spot, expiry_spot=expiry_spot, contract_type=norm_c)
        is_tie = (expiry_spot == entry_spot)
        delta = round(expiry_spot - entry_spot, 6)

        return RiseFallEvaluationResult(
            contract_type=norm_c,
            duration_ticks=duration_ticks,
            entry_mapping=entry_mapping,
            signal_price=signal_price,
            entry_spot=entry_spot,
            expiry_spot=expiry_spot,
            outcome=outcome,
            is_win=(outcome == 1),
            is_tie=is_tie,
            price_delta=delta,
            forward_tick_count=n_forward,
        )

    @classmethod
    def audit_entry_mapping_discrepancy(
        cls,
        signal_price: float,
        forward_ticks: List[float],
        contract_type: str,
        duration_ticks: int,
    ) -> EntryMappingDiscrepancyRecord:
        """Directly audits whether V0 and V1 entry mappings produce different outcomes."""
        res_v0 = cls.evaluate_contract(
            signal_price=signal_price,
            forward_ticks=forward_ticks,
            contract_type=contract_type,
            duration_ticks=duration_ticks,
            entry_mapping=MAPPING_V0_SIGNAL_TICK_ENTRY,
        )
        res_v1 = cls.evaluate_contract(
            signal_price=signal_price,
            forward_ticks=forward_ticks,
            contract_type=contract_type,
            duration_ticks=duration_ticks,
            entry_mapping=MAPPING_V1_NEXT_TICK_ENTRY,
        )

        disagree = (res_v0.outcome != res_v1.outcome)

        return EntryMappingDiscrepancyRecord(
            contract_type=contract_type,
            duration_ticks=duration_ticks,
            signal_price=signal_price,
            forward_ticks=forward_ticks[: duration_ticks + 2],
            v0_entry_spot=res_v0.entry_spot,
            v0_expiry_spot=res_v0.expiry_spot,
            v0_outcome=res_v0.outcome,
            v1_entry_spot=res_v1.entry_spot,
            v1_expiry_spot=res_v1.expiry_spot,
            v1_outcome=res_v1.outcome,
            outcomes_disagree=disagree,
        )
