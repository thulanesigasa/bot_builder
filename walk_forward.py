"""Walk-Forward validation engine and 3-Way Dataset Split (Train 60% / Val 20% / Holdout 20%).
Prevents overfitting by holding out an untouched 20% test dataset and evaluating
edge persistence across sliding walk-forward windows.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from quote_engine import QuoteEngine
from feature_search import evaluate_setup_edge
from strategy import ALL_SETUPS


@dataclass
class DatasetSplits:
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    holdout_df: pd.DataFrame


def create_three_way_split(
    df: pd.DataFrame,
    train_pct: float = 0.60,
    val_pct: float = 0.20,
    purge_gap: int = 0
) -> DatasetSplits:
    """Splits dataset chronologically into:
    - Train (60%): Strategy discovery
    - Validation (20%): Setup tuning & filtering
    - Final Holdout (20%): STRICT UNTOUCHED EXAM
    
    When purge_gap > 0 (e.g. 6 ticks for 5-transition contracts: i to i+6),
    a boundary buffer is purged between Train/Validation and Validation/Holdout
    to guarantee zero lookahead leakage from overlapping forward contract windows.
    """
    n = len(df)
    train_end = int(n * train_pct)
    val_start = min(n, train_end + purge_gap)
    val_end = int(n * (train_pct + val_pct))
    holdout_start = min(n, val_end + purge_gap)

    return DatasetSplits(
        train_df=df.iloc[:train_end].copy(),
        val_df=df.iloc[val_start:val_end].copy(),
        holdout_df=df.iloc[holdout_start:].copy()
    )


def create_purged_three_way_split(
    df: pd.DataFrame,
    train_pct: float = 0.60,
    val_pct: float = 0.20,
    purge_gap: int = 6
) -> DatasetSplits:
    """Convenience factory creating a strictly purged 3-way split preventing overlapping boundary leakage."""
    return create_three_way_split(df, train_pct=train_pct, val_pct=val_pct, purge_gap=purge_gap)



class WalkForwardAnalyzer:
    """Implements rolling or anchored walk-forward block validation."""

    def __init__(
        self,
        n_blocks: int = 4,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20
    ):
        self.n_blocks = n_blocks
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio

    def run_walk_forward(
        self,
        features_df: pd.DataFrame,
        quote_engine: QuoteEngine
    ) -> List[Dict[str, Any]]:
        """Splits features into rolling chronological blocks and assesses edge persistence."""
        total_len = len(features_df)
        block_size = total_len // self.n_blocks

        if block_size < 1000:
            raise ValueError(f"Dataset too small ({total_len} rows) for {self.n_blocks} walk-forward blocks.")

        block_results = []
        for i in range(self.n_blocks):
            start_idx = i * block_size
            end_idx = min(start_idx + block_size, total_len) if i == self.n_blocks - 1 else (i + 1) * block_size
            block_df = features_df.iloc[start_idx:end_idx]

            splits = create_three_way_split(block_df, self.train_ratio, self.val_ratio)

            # Discover best setup on Train
            candidates = []
            for name, (fn, side) in ALL_SETUPS.items():
                train_edge = evaluate_setup_edge(splits.train_df, fn(splits.train_df), side, quote_engine)
                if train_edge["n"] >= 20:
                    candidates.append((name, fn, side, train_edge))

            if not candidates:
                continue

            best_name, best_fn, best_side, best_train = max(candidates, key=lambda c: c[3]["z_score"])

            # Evaluate on Validation
            val_edge = evaluate_setup_edge(splits.val_df, best_fn(splits.val_df), best_side, quote_engine)

            # Evaluate on Holdout (The Honest Exam)
            holdout_edge = evaluate_setup_edge(splits.holdout_df, best_fn(splits.holdout_df), best_side, quote_engine)

            block_results.append({
                "block": i + 1,
                "start_epoch": int(block_df["epoch"].iloc[0]),
                "end_epoch": int(block_df["epoch"].iloc[-1]),
                "selected_setup": best_name,
                "train_n": best_train["n"],
                "train_wr": best_train["win_rate"],
                "train_z": best_train["z_score"],
                "val_n": val_edge["n"],
                "val_wr": val_edge["win_rate"],
                "val_z": val_edge["z_score"],
                "holdout_n": holdout_edge["n"],
                "holdout_wr": holdout_edge["win_rate"],
                "holdout_z": holdout_edge["z_score"],
                "holdout_edge": holdout_edge["edge"],
                "persists_in_holdout": holdout_edge["win_rate"] > quote_engine.get_quote(best_side).implied_probability
            })

        return block_results


def main():
    import sys
    from contract_model import ContractOutcomeModel
    from market_regime import compute_expanded_market_features

    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/R_75_master.csv"
    n_blocks = int(sys.argv[2]) if len(sys.argv) > 2 else 4

    print(f"Loading data for Walk-Forward Analysis: {csv_path}")
    raw_df = pd.read_csv(csv_path)

    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    outcomes = model.compute_contract_outcomes(raw_df)
    features = compute_expanded_market_features(raw_df)
    for col in ["entry_price", "exit_price", "rise_win", "fall_win", "is_tie", "only_ups_win", "only_downs_win"]:
        if col in outcomes.columns:
            features[col] = outcomes[col]
    features = features.dropna()

    quote_engine = QuoteEngine()
    analyzer = WalkForwardAnalyzer(n_blocks=n_blocks)
    results = analyzer.run_walk_forward(features, quote_engine)

    print("\n" + "=" * 80)
    print("                    WALK-FORWARD ROLLING VALIDATION REPORT")
    print("=" * 80)
    print(f"{'BLOCK':<6} {'SETUP SELECTED':<32} {'TRAIN z':>8} {'VAL z':>8} {'HOLDOUT WR':>11} {'HOLDOUT z':>10} {'PERSISTS?'}")
    print("-" * 80)
    for r in results:
        status = "YES" if r["persists_in_holdout"] else "NO"
        print(f"B{r['block']:<5} {r['selected_setup']:<32} {r['train_z']:>+8.2f} {r['val_z']:>+8.2f} {r['holdout_wr']:>10.2%} {r['holdout_z']:>+10.2f} {status:>9}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
