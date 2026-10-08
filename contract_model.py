"""Deriv contract lifecycle and execution modeling engine for RUNHIGH / RUNLOW (Only Ups / Only Downs).

Deriv 5-Tick RUNHIGH / RUNLOW Contract Lifecycle:
1. Signal detected at tick i.
2. Order submitted and processed by Deriv servers.
3. Entry Spot S_0 = tick i + 1 (the first tick after processing).
4. Contract duration = 5 successive tick movements:
     Step 1: S_0 -> S_1 (tick i + 2)
     Step 2: S_1 -> S_2 (tick i + 3)
     Step 3: S_2 -> S_3 (tick i + 4)
     Step 4: S_3 -> S_4 (tick i + 5)
     Step 5: S_4 -> S_5 (tick i + 6, Expiry Spot)
5. Outcome Evaluation:
   - RUNHIGH (Only Ups): Wins IF AND ONLY IF S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4.
     Any flat (<=) or downward tick results in IMMEDIATE LOSS.
   - RUNLOW (Only Downs): Wins IF AND ONLY IF S_1 < S_0 AND S_2 < S_1 AND S_3 < S_2 AND S_4 < S_3 AND S_5 < S_4.
     Any flat (>=) or upward tick results in IMMEDIATE LOSS.
6. Theoretical Random-Walk Baseline:
   (0.5)^5 = 0.03125 = 3.125%
7. Deriv Live Quote Benchmark ($2 stake -> $61.03 total return):
   Implied Break-Even Probability = 2.00 / 61.03 = 3.277%
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ContractOutcome:
    signal_idx: int
    entry_idx: int
    exit_idx: int
    entry_epoch: int
    exit_epoch: int
    entry_price: float
    exit_price: float
    contract_type: str  # 'RUNHIGH' or 'RUNLOW' (or 'CALL'/'PUT')
    is_win: bool
    is_tie: bool
    consecutive_steps: int  # how many consecutive steps survived before failure (0 to 5)
    path_prices: List[float]


class ContractOutcomeModel:
    """Models the exact execution lifecycle of Deriv 5-tick RUNHIGH/RUNLOW and CALL/PUT options."""

    def __init__(
        self,
        duration_ticks: int = 5,
        entry_offset: int = 1,
        contract_family: str = "run_high_low"
    ):
        self.duration_ticks = duration_ticks
        self.entry_offset = entry_offset
        self.contract_family = contract_family
        # Unambiguous 5-transition lifecycle: Entry S_0 at i+1 -> Expiry S_5 at i+6
        self.exit_offset = entry_offset + duration_ticks

    def compute_contract_outcomes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized computation of contract entry, exit, and outcomes across the dataset.
        
        Strict rules for 5-tick RUNHIGH / RUNLOW:
        - Entry Spot S_0 = tick i + 1
        - Expiry Spot S_5 = tick i + 6 (5 consecutive transitions after entry)
        - 'runhigh_win': all 5 transitions strictly rise (S_{k+1} > S_k for k=0..4)
        - 'runlow_win': all 5 transitions strictly fall (S_{k+1} < S_k for k=0..4)
        - Also computes 'rise_win' and 'fall_win' for comparative research.
        """
        p = df["price"].astype(float)
        epochs = df["epoch"].astype(int) if "epoch" in df.columns else pd.Series(df.index, index=df.index)

        res = pd.DataFrame(index=df.index)
        res["entry_price"] = p.shift(-self.entry_offset)
        res["exit_price"] = p.shift(-self.exit_offset)
        res["entry_epoch"] = epochs.shift(-self.entry_offset)
        res["exit_epoch"] = epochs.shift(-self.exit_offset)

        # 1. RUNHIGH and RUNLOW (5 consecutive uninterrupted movements)
        # S_0: p.shift(-1)
        # S_1: p.shift(-2)
        # S_2: p.shift(-3)
        # S_3: p.shift(-4)
        # S_4: p.shift(-5)
        # S_5: p.shift(-6)
        up_steps = []
        down_steps = []
        for step in range(self.entry_offset, self.exit_offset):
            t_curr = p.shift(-step)
            t_next = p.shift(-(step + 1))
            up_steps.append(t_next > t_curr)
            down_steps.append(t_next < t_curr)

        all_up = up_steps[0]
        all_down = down_steps[0]
        for u, d in zip(up_steps[1:], down_steps[1:]):
            all_up = all_up & u
            all_down = all_down & d

        res["runhigh_win"] = all_up.astype(float)
        res["runlow_win"] = all_down.astype(float)

        # Backward compatibility aliases
        res["only_ups_win"] = res["runhigh_win"]
        res["only_downs_win"] = res["runlow_win"]

        # 2. Comparative Rise / Fall (Binary outcome: S_5 > S_0)
        res["rise_win"] = (res["exit_price"] > res["entry_price"]).astype(float)
        res["fall_win"] = (res["exit_price"] < res["entry_price"]).astype(float)
        res["is_tie"] = (res["exit_price"] == res["entry_price"]).astype(float)
        res.loc[res["is_tie"] == 1.0, ["rise_win", "fall_win"]] = 0.0

        # Nullify edges where forward ticks extend beyond available data
        res.loc[res["exit_price"].isna(), ["runhigh_win", "runlow_win", "only_ups_win", "only_downs_win", "rise_win", "fall_win", "is_tie"]] = np.nan
        return res

    def evaluate_single_trade(
        self,
        prices: np.ndarray,
        epochs: np.ndarray,
        signal_idx: int,
        contract_type: str
    ) -> Optional[ContractOutcome]:
        """Evaluates a single trade execution along with step-level path metrics."""
        entry_idx = signal_idx + self.entry_offset
        exit_idx = signal_idx + self.exit_offset
        if exit_idx >= len(prices):
            return None

        entry_p = float(prices[entry_idx])
        exit_p = float(prices[exit_idx])
        path = [float(prices[idx]) for idx in range(entry_idx, exit_idx + 1)]

        c_norm = contract_type.upper()
        consecutive_count = 0
        is_win = False

        if c_norm in ("RUNHIGH", "ONLY_UPS", "UP"):
            # Check 5 transitions
            for k in range(len(path) - 1):
                if path[k + 1] > path[k]:
                    consecutive_count += 1
                else:
                    break
            is_win = (consecutive_count == self.duration_ticks)
        elif c_norm in ("RUNLOW", "ONLY_DOWNS", "DOWN"):
            for k in range(len(path) - 1):
                if path[k + 1] < path[k]:
                    consecutive_count += 1
                else:
                    break
            is_win = (consecutive_count == self.duration_ticks)
        elif c_norm in ("CALL", "RISE"):
            is_win = bool(exit_p > entry_p)
            consecutive_count = sum(1 for k in range(len(path) - 1) if path[k + 1] > path[k])
        elif c_norm in ("PUT", "FALL"):
            is_win = bool(exit_p < entry_p)
            consecutive_count = sum(1 for k in range(len(path) - 1) if path[k + 1] < path[k])
        else:
            raise ValueError(f"Unknown contract type: {contract_type}")

        is_tie = bool(exit_p == entry_p)

        return ContractOutcome(
            signal_idx=signal_idx,
            entry_idx=entry_idx,
            exit_idx=exit_idx,
            entry_epoch=int(epochs[entry_idx]) if epochs is not None else entry_idx,
            exit_epoch=int(epochs[exit_idx]) if epochs is not None else exit_idx,
            entry_price=entry_p,
            exit_price=exit_p,
            contract_type=contract_type,
            is_win=is_win,
            is_tie=is_tie,
            consecutive_steps=consecutive_count,
            path_prices=path
        )
