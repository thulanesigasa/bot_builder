"""Timestamp-Aware Synchronized Market Dataset Engine.

Combines:
- Historical or live ticks
- Forward-looking contract outcomes (Entry i+1 to Expiry i+6)
- Backward-looking market features and discrete regimes
- Timestamped RUNHIGH and RUNLOW proposal quotes
- Estimated conditional probabilities & uncertainty intervals
- Strict lookahead protection (quote response timestamp <= signal timestamp)
- Stores synchronized datasets in Parquet (if pyarrow available) or compressed CSV.
"""
import os
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from market_regime import compute_expanded_market_features
from quote_engine import QuoteEngine


class DatasetSynchronizer:
    """Synchronizes multi-source tick observations, market features, and quotes with lookahead guards."""

    def __init__(
        self,
        max_quote_freshness_seconds: float = 120.0,
        latency_buffer_seconds: float = 0.5
    ):
        self.max_quote_freshness_seconds = max_quote_freshness_seconds
        self.latency_buffer_seconds = latency_buffer_seconds

    def synchronize(
        self,
        raw_df: pd.DataFrame,
        quote_engine: QuoteEngine,
        symbol: str = "R_75"
    ) -> pd.DataFrame:
        """Constructs an integrated, timestamp-aligned research dataset.
        
        Strict Lookahead Protection Rules:
        - Features use only ticks at or before index i.
        - Outcomes evaluate forward ticks strictly from i+1 to i+6.
        - Proposal quotes must have been received at or before tick i's timestamp,
          within max_quote_freshness_seconds.
        - Future quotes are strictly discarded.
        """
        # 1. Outcomes
        contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
        outcomes_df = contract_model.compute_contract_outcomes(raw_df)

        # 2. Features and regimes
        features_df = compute_expanded_market_features(raw_df)

        # Merge core outcomes into features
        for col in ["entry_price", "exit_price", "runhigh_win", "runlow_win", "only_ups_win", "only_downs_win", "rise_win", "fall_win", "is_tie"]:
            if col in outcomes_df.columns:
                features_df[col] = outcomes_df[col]

        # 3. Synchronize Quotes
        synced_rows = []
        for idx, row in features_df.iterrows():
            epoch = int(row["epoch"]) if "epoch" in row and not pd.isna(row["epoch"]) else int(idx)

            # Query historical quote available AT OR BEFORE this epoch
            q_up_status, q_up = quote_engine.get_quote_status("UP", epoch=epoch)
            q_down_status, q_down = quote_engine.get_quote_status("DOWN", epoch=epoch)

            # Check freshness
            up_available = (q_up is not None and (epoch - q_up.quote_time) <= self.max_quote_freshness_seconds and (q_up.quote_time <= epoch))
            down_available = (q_down is not None and (epoch - q_down.quote_time) <= self.max_quote_freshness_seconds and (q_down.quote_time <= epoch))

            synced_rows.append({
                "quote_up_status": "QUOTE_AVAILABLE" if up_available else "QUOTE_UNAVAILABLE",
                "quote_down_status": "QUOTE_AVAILABLE" if down_available else "QUOTE_UNAVAILABLE",
                "up_ask": q_up.ask_price if up_available else np.nan,
                "up_payout": q_up.payout if up_available else np.nan,
                "up_implied_prob": q_up.implied_probability if up_available else np.nan,
                "down_ask": q_down.ask_price if down_available else np.nan,
                "down_payout": q_down.payout if down_available else np.nan,
                "down_implied_prob": q_down.implied_probability if down_available else np.nan,
            })

        quote_sync_df = pd.DataFrame(synced_rows, index=features_df.index)
        combined_df = pd.concat([features_df, quote_sync_df], axis=1)
        return combined_df

    @staticmethod
    def export_dataset(df: pd.DataFrame, base_path: str) -> str:
        """Saves dataset in Parquet format if available; falls back to CSV."""
        os.makedirs(os.path.dirname(os.path.abspath(base_path)), exist_ok=True)
        parquet_path = base_path if base_path.endswith(".parquet") else f"{base_path}.parquet"
        csv_path = base_path if base_path.endswith(".csv") else f"{base_path}.csv"

        try:
            df.to_parquet(parquet_path, index=False)
            return parquet_path
        except Exception:
            # Fallback to standard CSV
            df.to_csv(csv_path, index=False)
            return csv_path
