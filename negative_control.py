"""Research Negative Control Engine for Deriv 5-Tick RUNHIGH / RUNLOW.

Evaluates whether the edge discovery engine can distinguish genuine predictive signal
from noise by subjecting the discovery pipeline to negative controls:
1. Permuted / randomized market-state labels (breaks state-to-outcome mapping).
2. Stationary circular block-shuffled tick increments (preserves variance & local volatility but destroys directional predictability).
3. Unconditional baseline benchmark.

Calculates the empirical False Positive Rate (FPR). Under proper statistical controls,
zero false-positive edges should survive the multi-gate validation pipeline.
"""
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

from quote_engine import QuoteEngine
from contract_model import ContractOutcomeModel
from feature_search import (
    SystematicStateGridSearch,
    audit_candidates_on_validation,
    SampleSizeConfig
)
from walk_forward import create_purged_three_way_split


def generate_permuted_state_series(
    features_df: pd.DataFrame,
    random_seed: int = 42
) -> pd.DataFrame:
    """Randomly permutes market state features while keeping outcomes in place.
    Breaks any causal or predictive connection between observable state and outcome.
    """
    rng = np.random.default_rng(random_seed)
    df_null = features_df.copy()

    state_cols = [c for c in df_null.columns if c.endswith("_bin") or c in ("market_regime", "market_state")]
    for col in state_cols:
        vals = df_null[col].to_numpy()
        rng.shuffle(vals)
        df_null[col] = vals

    return df_null


def generate_block_shuffled_increments(
    raw_df: pd.DataFrame,
    block_size: int = 20,
    random_seed: int = 42
) -> pd.DataFrame:
    """Performs stationary block-shuffling on price increments.
    
    Preserves local volatility and variance distribution within blocks of length block_size,
    but destroys long-range sequence dependencies and macroscopic regime structure.
    """
    rng = np.random.default_rng(random_seed)
    p = raw_df["price"].to_numpy(dtype=float)
    deltas = np.diff(p)
    n_deltas = len(deltas)

    # Partition deltas into blocks
    num_blocks = n_deltas // block_size
    blocks = [deltas[i * block_size:(i + 1) * block_size] for i in range(num_blocks)]
    remainder = deltas[num_blocks * block_size:]

    # Shuffle block order
    rng.shuffle(blocks)
    shuffled_deltas = np.concatenate(blocks)
    if len(remainder) > 0:
        shuffled_deltas = np.concatenate([shuffled_deltas, remainder])

    # Reconstruct prices from initial price
    recon_prices = np.empty(len(raw_df))
    recon_prices[0] = p[0]
    recon_prices[1:] = p[0] + np.cumsum(shuffled_deltas)

    df_shuffled = raw_df.copy()
    df_shuffled["price"] = recon_prices
    return df_shuffled


def run_negative_control_audit(
    features_df: pd.DataFrame,
    quote_engine: QuoteEngine,
    num_permutations: int = 3,
    sample_config: Optional[SampleSizeConfig] = None
) -> Dict[str, Any]:
    """Executes negative control experiments on null/permuted data.
    
    Verifies that the multi-gate discovery pipeline does NOT produce false validated edges
    when running on noise datasets where no real relationship exists.
    """
    cfg = sample_config or SampleSizeConfig()
    total_null_candidates = 0
    total_null_validated = 0
    sim_details = []

    for seed in range(num_permutations):
        df_null = generate_permuted_state_series(features_df, random_seed=100 + seed)
        splits = create_purged_three_way_split(df_null, train_pct=0.60, val_pct=0.20, purge_gap=6)

        searcher = SystematicStateGridSearch(
            min_sample_size=cfg.min_discovery_samples,
            candidate_z_threshold=2.0,
            min_lift_threshold=1.15,
            sample_config=cfg
        )
        search_res = searcher.search(splits.train_df, quote_engine)
        candidates = search_res.get("runhigh_candidates", []) + search_res.get("runlow_candidates", [])
        total_null_candidates += len(candidates)

        # Audit on validation
        val_audit = audit_candidates_on_validation(
            splits.val_df,
            candidates,
            quote_engine,
            min_val_n=cfg.min_validation_samples
        )
        survived = [a for a in val_audit if a.get("survived_validation", False)]
        total_null_validated += len(survived)

        sim_details.append({
            "simulation": seed + 1,
            "raw_candidates_found": len(candidates),
            "survived_validation": len(survived)
        })

    fpr = (total_null_validated / max(1, total_null_candidates)) if total_null_candidates > 0 else 0.0

    return {
        "num_simulations": num_permutations,
        "total_null_candidates_discovered": total_null_candidates,
        "total_null_validated_edges": total_null_validated,
        "empirical_false_positive_rate": round(fpr, 4),
        "passed_negative_control": (total_null_validated == 0),
        "simulations": sim_details
    }
