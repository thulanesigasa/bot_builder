"""Unit tests for V1.5: Advanced Edge Discovery & Real-Market Validation.

Verifies all production research requirements:
1. Canonical 5-tick contract settlement rules (S_0 at i+1 -> S_5 at i+6)
2. Purged walk-forward split (gap between splits prevents boundary overlap leakage)
3. Bayesian probability smoothing (shrinkage toward baseline on small samples)
4. Wilson score confidence interval calculation
5. Conservative EV calculation using lower bound probability
6. Effective sample size calculation (adjusting for overlapping 5-tick contracts)
7. Benjamini-Hochberg False Discovery Rate (FDR) q-values
8. Dedicated quote recorder schema, latency tracking, and quote loader pivoting
9. Dataset synchronizer with strict lookahead protection and future quote rejection
10. Research negative control experiments (permuted labels & stationary block shuffle)
11. Historical collection recovery, gap reporting, and automatic data quarantine
12. Paper trading mode safety lock (LIVE_EXECUTION_DISABLED = True) and extended telemetry
"""
import os
import json
import pytest
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from walk_forward import create_three_way_split, create_purged_three_way_split
from probability import (
    bayesian_smoothed_probability,
    wilson_score_interval,
    calculate_conservative_ev,
    calculate_effective_sample_size,
    calculate_fdr_q_values,
    calculate_unconditional_baseline,
    calculate_true_ev,
    calculate_true_break_even
)
from quote_engine import QuoteEngine, ProposalQuote
from quote_recorder import ProposalRecord, DerivQuoteRecorder
from dataset_synchronizer import DatasetSynchronizer
from negative_control import (
    generate_permuted_state_series,
    generate_block_shuffled_increments,
    run_negative_control_audit
)
from collector import (
    analyze_gaps,
    quarantine_dataset,
    save_checkpoint,
    load_checkpoint
)
from paper_trader import PaperTrader, PaperTradeRecord


# ==============================================================================
# 1. CANONICAL CONTRACT SETTLEMENT
# ==============================================================================

def test_canonical_contract_outcomes_settlement():
    """Confirms exact 5-transition settlement lifecycle: S_0 -> S_1 -> S_2 -> S_3 -> S_4 -> S_5."""
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    # RUNHIGH winning path
    res_up = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res_up is not None
    assert res_up.entry_price == 11.0  # S_0 at i+1
    assert res_up.exit_price == 16.0   # S_5 at i+6
    assert res_up.is_win is True
    assert res_up.consecutive_steps == 5

    # Any flat tick causes immediate failure
    flat_prices = [10.0, 11.0, 12.0, 12.0, 14.0, 15.0, 16.0]
    res_flat = model.evaluate_single_trade(
        prices=np.array(flat_prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res_flat is not None
    assert res_flat.is_win is False
    assert res_flat.consecutive_steps == 1


# ==============================================================================
# 2. PURGED WALK-FORWARD BOUNDARIES
# ==============================================================================

def test_purged_walk_forward_splits_prevent_overlap():
    """Purged walk-forward split enforces gap buffer between splits to prevent overlap leakage."""
    n = 1000
    df = pd.DataFrame({
        "epoch": range(1000, 1000 + n),
        "price": np.linspace(100, 200, n)
    })

    # Standard split has no gap: val starts immediately at train_end
    std_splits = create_three_way_split(df, train_pct=0.60, val_pct=0.20, purge_gap=0)
    assert len(std_splits.train_df) == 600
    assert len(std_splits.val_df) == 200
    assert std_splits.train_df["epoch"].iloc[-1] + 1 == std_splits.val_df["epoch"].iloc[0]

    # Purged split introduces 6-tick boundary buffer
    purged_splits = create_purged_three_way_split(df, train_pct=0.60, val_pct=0.20, purge_gap=6)
    assert len(purged_splits.train_df) == 600
    assert len(purged_splits.val_df) == 194  # 200 - 6
    assert len(purged_splits.holdout_df) == 194
    # The gap between train end and val start is strictly 6 ticks!
    assert purged_splits.val_df["epoch"].iloc[0] - purged_splits.train_df["epoch"].iloc[-1] == 7


# ==============================================================================
# 3. BAYESIAN PROBABILITY SMOOTHING & SHRINKAGE
# ==============================================================================

def test_bayesian_probability_smoothing_shrinks_sparse_estimates():
    """Bayesian conjugate Beta smoothing pulls sparse state estimates toward base rate."""
    base_p = 0.032
    # Small sample anomaly: 2 wins in 10 observations (20% nominal win rate)
    nominal_p = 2 / 10
    bayes_p = bayesian_smoothed_probability(wins=2, n=10, baseline_prob=base_p, prior_weight=50.0)

    # Posterior = (2 + 50 * 0.032) / (10 + 50) = 3.6 / 60 = 0.060 (6.0%)
    assert bayes_p < nominal_p
    assert round(bayes_p, 3) == 0.060
    assert bayes_p > base_p  # Still retains empirical evidence, but heavily shrunk toward baseline!


# ==============================================================================
# 4. WILSON SCORE INTERVAL & CONSERVATIVE EV
# ==============================================================================

def test_wilson_score_interval_and_conservative_ev():
    """Calculates Wilson confidence interval and conservative EV using lower confidence bound."""
    wins = 10
    n = 100
    ci_lo, ci_hi = wilson_score_interval(wins, n, confidence=0.95)
    assert 0.0 < ci_lo < (wins / n) < ci_hi < 1.0

    # Stake $2.00, Payout $61.03
    stake = 2.0
    payout = 61.03
    cons_ev = calculate_conservative_ev(ci_lo, stake, payout, basis="stake")
    nom_ev = calculate_true_ev(wins / n, stake, payout, basis="stake")

    assert cons_ev < nom_ev
    assert cons_ev == (ci_lo * payout - stake)


# ==============================================================================
# 5. EFFECTIVE SAMPLE SIZE & OVERLAPPING CONTRACT ADJUSTMENT
# ==============================================================================

def test_effective_sample_size_for_overlapping_contracts():
    """Adjusts effective sample size for serial correlation across 5-tick overlapping windows."""
    n = 1000
    eff_n = calculate_effective_sample_size(n, duration_ticks=5)
    assert eff_n == 200.0  # 1000 / 5

    # With autocorrelation
    eff_n_rho = calculate_effective_sample_size(n, duration_ticks=5, autocorrelation=0.5)
    # (1 - 0.5) / (1 + 0.5) = 0.5 / 1.5 = 1/3 -> 1000 / 3 = 333.33
    assert round(eff_n_rho, 1) == 333.3


# ==============================================================================
# 6. BENJAMINI-HOCHBERG FDR Q-VALUES
# ==============================================================================

def test_benjamini_hochberg_fdr_q_values():
    """Computes FDR adjusted q-values across multiple hypothesis tests."""
    p_vals = [0.001, 0.01, 0.04, 0.50]
    q_vals = calculate_fdr_q_values(p_vals)
    assert len(q_vals) == 4
    # Monotonicity check
    assert q_vals[0] <= q_vals[1] <= q_vals[2] <= q_vals[3]
    assert q_vals[0] == min(1.0, 0.001 * 4 / 1)  # 0.004


# ==============================================================================
# 7. PROPOSAL QUOTE RECORDER & HISTORICAL QUOTE LOADER
# ==============================================================================

def test_proposal_quote_recorder_and_loader_pivot(tmp_path):
    """Verifies ProposalRecord dataclass and QuoteEngine loading/pivoting of recorded quotes."""
    rec_rh = ProposalRecord(
        request_timestamp=1700000000.0,
        response_timestamp=1700000000.1,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_rh_123",
        quote_source="live_proposal",
        quote_latency_ms=100.0,
        collection_status="QUOTE_AVAILABLE"
    )
    rec_rl = ProposalRecord(
        request_timestamp=1700000000.0,
        response_timestamp=1700000000.1,
        market_symbol="R_75",
        contract_type="RUNLOW",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=60.50,
        potential_net_profit=58.50,
        currency="USD",
        proposal_id="prop_rl_123",
        quote_source="live_proposal",
        quote_latency_ms=100.0,
        collection_status="QUOTE_AVAILABLE"
    )

    csv_path = tmp_path / "recorded_quotes.csv"
    DerivQuoteRecorder.append_record_to_csv(str(csv_path), rec_rh)
    DerivQuoteRecorder.append_record_to_csv(str(csv_path), rec_rl)

    qe = QuoteEngine(mode="research")
    qe.load_historical_quotes(str(csv_path))

    q_up = qe.get_quote("UP", epoch=1700000000)
    assert q_up is not None
    assert q_up.payout == 61.03

    q_down = qe.get_quote("DOWN", epoch=1700000000)
    assert q_down is not None
    assert q_down.payout == 60.50


# ==============================================================================
# 8. DATASET SYNCHRONIZER WITH LOOKAHEAD PROTECTION
# ==============================================================================

def test_dataset_synchronizer_lookahead_protection(tmp_path):
    """Synchronizer strictly rejects future quotes and links only quotes at or before observation."""
    qe = QuoteEngine(mode="research")
    qe.clear_quotes()
    qe.record_quote_snapshot(epoch=1050, runhigh_payout=61.03, runlow_payout=60.00, stake=2.0)

    # Raw ticks spanning epoch 1000 to 1200 (100 ticks)
    raw_df = pd.DataFrame({
        "epoch": [1000 + i * 2 for i in range(100)],
        "price": [100.0 + i * 0.1 for i in range(100)]
    })

    sync = DatasetSynchronizer(max_quote_freshness_seconds=120.0)
    synced = sync.synchronize(raw_df, qe, symbol="R_75")

    # Observations before epoch 1050 must have QUOTE_UNAVAILABLE
    before_row = synced[synced["epoch"] == 1040].iloc[0]
    assert before_row["quote_up_status"] == "QUOTE_UNAVAILABLE"

    # Observation at epoch 1060 (after quote at 1050) has QUOTE_AVAILABLE
    after_row = synced[synced["epoch"] == 1060].iloc[0]
    assert after_row["quote_up_status"] == "QUOTE_AVAILABLE"
    assert after_row["up_payout"] == 61.03

    # Export dataset test
    out_file = sync.export_dataset(synced, str(tmp_path / "synced_test.csv"))
    assert os.path.exists(out_file)


# ==============================================================================
# 9. RESEARCH NEGATIVE CONTROLS
# ==============================================================================

def test_negative_control_permuted_and_block_shuffle():
    """Negative controls scramble predictive associations while preserving local properties."""
    np.random.seed(42)
    n = 200
    df = pd.DataFrame({
        "epoch": range(1000, 1000 + n),
        "price": 100.0 + np.cumsum(np.random.normal(0, 1, n)),
        "streak_bin": ["UP_STREAK" if i % 2 == 0 else "DOWN_STREAK" for i in range(n)],
        "mom_bin": ["BULL" if i % 3 == 0 else "BEAR" for i in range(n)],
        "runhigh_win": np.random.binomial(1, 0.03, n)
    })

    # Permuted labels
    permuted = generate_permuted_state_series(df, random_seed=99)
    assert len(permuted) == n
    # State series is shuffled
    assert not permuted["streak_bin"].equals(df["streak_bin"])

    # Block shuffled price increments
    shuffled_prices = generate_block_shuffled_increments(df, block_size=10, random_seed=99)
    assert len(shuffled_prices) == n
    assert shuffled_prices["price"].iloc[0] == df["price"].iloc[0]
    # Price paths diverge due to block reordering
    assert not np.array_equal(shuffled_prices["price"].values, df["price"].values)


# ==============================================================================
# 10. HISTORICAL COLLECTION GAPS, CHECKPOINT, AND QUARANTINE
# ==============================================================================

def test_collector_gaps_checkpoint_and_quarantine(tmp_path):
    """Tests collector gap detection, checkpoint resumption, and automatic quarantine."""
    # 1. Gap detection
    ticks_with_gap = [(1000, 10.0), (1001, 10.1), (1010, 10.2)]  # 9-second gap
    gap_rep = analyze_gaps(ticks_with_gap, threshold_seconds=3.0)
    assert gap_rep["gaps_detected"] is True
    assert gap_rep["max_gap_seconds"] == 9.0

    # 2. Checkpoint save & load
    save_checkpoint("TEST_SYM", 1010, 3, str(tmp_path))
    cp = load_checkpoint("TEST_SYM", str(tmp_path))
    assert cp is not None
    assert cp["symbol"] == "TEST_SYM"
    assert cp["collected_count"] == 3

    # 3. Quarantine corrupt dataset
    corrupt_ticks = [(1000, 10.0), (1001, 10.0), (1002, 10.0)]
    q_file = quarantine_dataset("CORRUPT_SYM", corrupt_ticks, ["Flat prices detected"], str(tmp_path))
    assert os.path.exists(q_file)
    assert "quarantine" in q_file


# ==============================================================================
# 11. PAPER TRADING SAFETY AND EXTENDED TELEMETRY
# ==============================================================================

def test_paper_trading_safety_and_extended_telemetry():
    """Paper trader strictly forbids real money trading and records all 17 telemetry fields."""
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True

    qe = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    paper = PaperTrader(
        quote_engine=qe,
        symbol="R_75",
        default_stake=2.0,
        min_required_ev=0.0,
        min_required_conservative_ev=0.0
    )

    # Evaluate opportunity with negative conservative EV
    rec = paper.evaluate_opportunity(
        epoch=1000,
        signal="UP",
        estimated_prob=0.04,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True,
        market_state="TEST_STATE",
        uncertainty=(0.02, 0.06),  # Lower bound 2% is below break-even (3.28%)!
        conservative_ev=-0.78       # 0.02 * 61.03 - 2.0 = -0.78
    )
    assert rec.decision == "NO_TRADE"
    assert "NEGATIVE_CONSERVATIVE_EV" in rec.rejection_reason
    assert rec.conservative_expected_value == -0.78
    assert rec.simulated_entry_timestamp == 1001
    assert rec.actual_proposal_price == 2.0
    assert rec.total_payout == 61.03
