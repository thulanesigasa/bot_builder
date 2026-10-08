"""Unit tests for V1.4: Edge Validation & Historical EV Engine.

Verifies all production research requirements:
1. Exact 5-tick contract lifecycle & canonical outcome rules (S_0 at i+1 -> S_5 at i+6)
   - 5 consecutive UP ticks = win
   - 4 UP + 1 DOWN = loss
   - 3 UP + equality = loss
   - 5 consecutive DOWN ticks = win
   - 4 DOWN + 1 UP = loss
   - equality = loss
   - insufficient ticks = invalid/no result
2. Empirical unconditional baseline calculation (P(RUNHIGH), P(RUNLOW), SE, CI)
3. State-conditional probability, relative lift, and absolute lift
4. Sample-size protection & rejection
5. Multiple-testing Bonferroni correction and significance status
6. Probability calibration (Brier score, BSS, ECE, reliability bins)
7. Historical quote schema, separation of RUNHIGH/RUNLOW, QUOTE_UNAVAILABLE handling
8. Payout basis semantics, true break-even, and EV calculations
9. Timestamp-aware quote-outcome joining with lookahead protection
10. Dynamic EV filter & NO_TRADE conditions
11. Edge quality status attribution across all validation gates
12. Paper trading simulation mode (LIVE_EXECUTION_DISABLED = True)
13. Historical data coverage checks and duration warnings
"""
import pytest
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from quote_engine import QuoteEngine, ProposalQuote, QuoteOutcomeJoiner
from probability import (
    calculate_unconditional_baseline,
    compute_probability_lift,
    compute_absolute_lift,
    calculate_break_even,
    calculate_true_break_even,
    calculate_expected_value,
    calculate_true_ev,
    calculate_confidence_interval,
    calculate_z_score,
    calculate_p_value,
    calculate_adjusted_p_value,
    evaluate_significance_status,
    compute_brier_score,
    compute_brier_skill_score,
    compute_calibration_curve,
    is_model_calibrated,
    bonferroni_critical_z
)
from feature_search import (
    SampleSizeConfig,
    EdgeCandidateReport,
    determine_edge_status
)
from features import check_data_coverage, validate_data
from paper_trader import PaperTrader, PaperTradeRecord


# ==============================================================================
# 1. EXACT CONTRACT DEFINITION & OUTCOME RULES
# ==============================================================================

def test_canonical_5tick_contract_outcomes_up_win():
    """5 consecutive UP ticks after entry S_0 strictly wins RUNHIGH."""
    # Signal at i=0. Entry S_0 at i=1 (price 10.0).
    # S_1=11, S_2=12, S_3=13, S_4=14, S_5=15 (Expiry).
    prices = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    
    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res is not None
    assert res.entry_price == 10.0
    assert res.exit_price == 15.0
    assert res.consecutive_steps == 5
    assert res.is_win is True
    assert res.is_tie is False

    # Also test vectorized compute_contract_outcomes
    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runhigh_win"] == 1.0
    assert out.loc[0, "runlow_win"] == 0.0


def test_canonical_5tick_contract_outcomes_4up_1down_loss():
    """4 UP + 1 DOWN must be an immediate loss for RUNHIGH."""
    # S_0=10.0 -> S_1=11 -> S_2=12 -> S_3=13 -> S_4=14 -> S_5=13.5 (DOWN reversal on step 5)
    prices = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 13.5]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res is not None
    assert res.is_win is False
    assert res.consecutive_steps == 4  # Survived 4 steps, failed on 5th

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runhigh_win"] == 0.0


def test_canonical_5tick_contract_outcomes_3up_equality_loss():
    """3 UP + equality on step 4 must be a loss for RUNHIGH."""
    # S_0=10.0 -> S_1=11 -> S_2=12 -> S_3=13 -> S_4=13 (FLAT) -> S_5=14
    prices = [9.0, 10.0, 11.0, 12.0, 13.0, 13.0, 14.0]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res is not None
    assert res.is_win is False
    assert res.consecutive_steps == 3

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runhigh_win"] == 0.0


def test_canonical_5tick_contract_outcomes_down_win():
    """5 consecutive DOWN ticks strictly wins RUNLOW."""
    # S_0=100.0 -> S_1=99 -> S_2=98 -> S_3=97 -> S_4=96 -> S_5=95
    prices = [101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNLOW"
    )
    assert res is not None
    assert res.entry_price == 100.0
    assert res.exit_price == 95.0
    assert res.consecutive_steps == 5
    assert res.is_win is True

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runlow_win"] == 1.0
    assert out.loc[0, "runhigh_win"] == 0.0


def test_canonical_5tick_contract_outcomes_4down_1up_loss():
    """4 DOWN + 1 UP must be an immediate loss for RUNLOW."""
    # S_0=100.0 -> S_1=99 -> S_2=98 -> S_3=97 -> S_4=96 -> S_5=97 (UP reversal on step 5)
    prices = [101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 97.0]
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNLOW"
    )
    assert res is not None
    assert res.is_win is False
    assert res.consecutive_steps == 4

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runlow_win"] == 0.0


def test_canonical_5tick_contract_outcomes_equality_loss():
    """Equal price anywhere in the contract is an immediate loss for both RUNHIGH and RUNLOW."""
    # S_0=50 -> S_1=50 -> S_2=50 -> S_3=50 -> S_4=50 -> S_5=50
    prices = [50.0] * 7
    epochs = list(range(1000, 1007))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res_up = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    res_down = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNLOW"
    )
    assert res_up.is_win is False
    assert res_down.is_win is False
    assert res_up.is_tie is True

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert out.loc[0, "runhigh_win"] == 0.0
    assert out.loc[0, "runlow_win"] == 0.0
    assert out.loc[0, "is_tie"] == 1.0


def test_canonical_5tick_contract_outcomes_insufficient_ticks():
    """Insufficient forward ticks returns None or NaN, never an invented outcome."""
    # Only 5 ticks total: signal at 0 needs up to tick 6 (7 total ticks)
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    epochs = list(range(1000, 1005))
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    res = model.evaluate_single_trade(
        prices=np.array(prices),
        epochs=np.array(epochs),
        signal_idx=0,
        contract_type="RUNHIGH"
    )
    assert res is None

    df = pd.DataFrame({"epoch": epochs, "price": prices})
    out = model.compute_contract_outcomes(df)
    assert pd.isna(out.loc[0, "runhigh_win"])


# ==============================================================================
# 2. BASELINE PROBABILITY ENGINE
# ==============================================================================

def test_empirical_unconditional_baseline_calculation():
    """Empirical baseline calculates observations, wins, losses, SE, and 95% Wald CI."""
    np.random.seed(42)
    # 1000 outcomes with 35 wins
    wins = np.zeros(1000)
    wins[:35] = 1.0
    np.random.shuffle(wins)

    df = pd.DataFrame({
        "runhigh_win": wins,
        "runlow_win": np.zeros(1000)
    })
    baselines = calculate_unconditional_baseline(df, symbol="TEST_SYM")

    assert "RUNHIGH" in baselines
    assert "RUNLOW" in baselines
    rh = baselines["RUNHIGH"]
    assert rh.symbol == "TEST_SYM"
    assert rh.observations == 1000
    assert rh.wins == 35
    assert rh.losses == 965
    assert rh.empirical_prob == 0.035
    assert round(rh.standard_error, 4) == round(np.sqrt(0.035 * 0.965 / 1000), 4)
    assert rh.ci_lower < rh.empirical_prob < rh.ci_upper
    assert rh.theoretical_ref == 0.03125


# ==============================================================================
# 3. STATE-CONDITIONAL PROBABILITY & LIFTS
# ==============================================================================

def test_state_conditional_probability_and_lift():
    """Computes relative lift (cond / base) and absolute lift (cond - base)."""
    base_p = 0.03125
    cond_p = 0.0625

    rel_lift = compute_probability_lift(cond_p, base_p)
    abs_lift = compute_absolute_lift(cond_p, base_p)

    assert round(rel_lift, 2) == 2.0
    assert round(abs_lift, 5) == 0.03125


# ==============================================================================
# 4. SAMPLE SIZE PROTECTION
# ==============================================================================

def test_sample_size_rejection_guard():
    """Samples below minimum discovery threshold must be rejected with LOW_SAMPLE."""
    cfg = SampleSizeConfig(min_discovery_samples=50, min_validation_samples=20, min_holdout_samples=20)
    
    status = determine_edge_status(
        sample_size=35,  # Below 50!
        adj_p_value=0.01,
        expected_value=1.5,
        conditional_prob=0.08,
        break_even_prob=0.0328,
        calibration_ok=True,
        validation_survived=True,
        holdout_survived=True,
        sample_config=cfg
    )
    assert status == "LOW_SAMPLE"


# ==============================================================================
# 5. MULTIPLE-TESTING PROTECTION
# ==============================================================================

def test_multiple_testing_correction_and_status():
    """Bonferroni correction multiplies raw p-value by number of tests, capping at 1.0."""
    raw_p = 0.002
    num_tests = 100
    adj_p = calculate_adjusted_p_value(raw_p, num_tests)
    assert round(adj_p, 4) == 0.2000

    # Status determination under ALPHA = 0.05
    status_not_sig = evaluate_significance_status(raw_p, adj_p, n=100, min_samples=50, alpha=0.05)
    assert status_not_sig == "NOT_SIGNIFICANT"

    # Truly significant test (e.g. raw_p = 0.00001 with 100 tests -> adj_p = 0.001)
    adj_p_sig = calculate_adjusted_p_value(0.00001, 100)
    status_sig = evaluate_significance_status(0.00001, adj_p_sig, n=100, min_samples=50, alpha=0.05)
    assert status_sig == "STATISTICALLY_SIGNIFICANT"

    # Insufficient sample
    status_insuf = evaluate_significance_status(0.00001, adj_p_sig, n=30, min_samples=50, alpha=0.05)
    assert status_insuf == "INSUFFICIENT_SAMPLE"


# ==============================================================================
# 6. PROBABILITY CALIBRATION
# ==============================================================================

def test_probability_calibration_and_reliability_bins():
    """Tests Brier score, BSS, Expected Calibration Error, and model calibration checker."""
    y_true = np.array([1, 0, 0, 0, 1, 0, 0, 0, 0, 0])
    # Model predicting near true outcome rate
    y_prob_good = np.array([0.8, 0.1, 0.1, 0.1, 0.7, 0.05, 0.05, 0.1, 0.05, 0.05])
    
    cal_good = compute_calibration_curve(y_true, y_prob_good, n_bins=3, baseline_prob=0.20)
    assert cal_good["brier_score"] < cal_good["baseline_brier_score"]
    assert cal_good["brier_skill_score"] > 0.0
    assert is_model_calibrated(cal_good, max_ece=0.20, min_bss=0.0) is True

    # Overfitted/poorly calibrated model
    y_prob_bad = np.array([0.1, 0.9, 0.8, 0.9, 0.1, 0.7, 0.8, 0.9, 0.8, 0.9])
    cal_bad = compute_calibration_curve(y_true, y_prob_bad, n_bins=3, baseline_prob=0.20)
    assert cal_bad["brier_skill_score"] < 0.0
    assert is_model_calibrated(cal_bad) is False


# ==============================================================================
# 7. HISTORICAL QUOTE SCHEMA & MISSING QUOTE HANDLING
# ==============================================================================

def test_historical_quote_schema_and_missing_quote_handling():
    """Historical quote schema contains all required metadata and returns QUOTE_UNAVAILABLE on missing."""
    quote = ProposalQuote(
        symbol="R_75",
        contract_type="RUNHIGH",
        direction="UP",
        stake=2.0,
        payout=61.03,
        profit=59.03,
        payout_ratio=29.515,
        implied_probability=2.0 / 61.03,
        quote_time=1700000000.0,
        source="live_proposal",
        duration=5,
        duration_unit="t",
        basis="stake",
        currency="USD",
        proposal_id="prop_12345",
        collection_timestamp=1700000000.5
    )
    assert quote.ask_price == 2.0
    assert quote.timestamp == 1700000000.0
    assert quote.proposal_id == "prop_12345"
    assert quote.basis == "stake"

    # QuoteEngine in live mode without quotes
    qe = QuoteEngine(mode="live")
    status, q = qe.get_quote_status("UP")
    assert status == "QUOTE_UNAVAILABLE"
    assert q is None


# ==============================================================================
# 8. PAYOUT BASIS, TRUE BREAK-EVEN, AND EV CALCULATION
# ==============================================================================

def test_payout_basis_break_even_and_ev_calculation():
    """Tests break-even and EV distinguishing total return (basis='stake') vs net profit (basis='profit')."""
    # 1. Basis == 'stake' (Deriv RunHigh: Stake $2.00, Payout $61.03 total return)
    be_stake = calculate_true_break_even(stake=2.0, payout=61.03, basis="stake")
    assert round(be_stake, 5) == round(2.0 / 61.03, 5)

    ev_stake = calculate_true_ev(prob=0.05, stake=2.0, payout=61.03, basis="stake")
    # EV = 0.05 * 61.03 - 2.0 = 3.0515 - 2.0 = 1.0515
    assert round(ev_stake, 4) == round(0.05 * 61.03 - 2.0, 4)

    # 2. Basis == 'profit' (Payout is net profit e.g. $59.03)
    be_profit = calculate_true_break_even(stake=2.0, payout=59.03, basis="profit")
    # BE = stake / (stake + payout) = 2.0 / 61.03
    assert round(be_profit, 5) == round(2.0 / 61.03, 5)

    ev_profit = calculate_true_ev(prob=0.05, stake=2.0, payout=59.03, basis="profit")
    # EV = 0.05 * 59.03 - (1 - 0.05) * 2.0 = 2.9515 - 1.90 = 1.0515
    assert round(ev_profit, 4) == round(0.05 * 59.03 - 0.95 * 2.0, 4)


# ==============================================================================
# 9. LOOKAHEAD PROTECTION & TIMESTAMP JOINING
# ==============================================================================

def test_quote_outcome_join_lookahead_protection():
    """Quotes available strictly in the future must NOT be joined to earlier observations."""
    qe = QuoteEngine(mode="research")
    qe.clear_quotes()

    # Record quote at epoch 1050
    qe.record_quote_snapshot(epoch=1050, runhigh_payout=61.03, runlow_payout=61.03, stake=2.0)

    # Observation at epoch 1000 (BEFORE the quote existed)
    obs_df = pd.DataFrame([{
        "epoch": 1000,
        "signal": "UP",
        "estimated_prob": 0.05,
        "runhigh_win": 1.0
    }])

    joined = QuoteOutcomeJoiner.join(obs_df, qe, symbol="R_75")
    # Because quote is in the future, it must be QUOTE_UNAVAILABLE and signal NO_TRADE
    assert joined.loc[0, "status"] == "QUOTE_UNAVAILABLE"
    assert joined.loc[0, "signal"] == "NO_TRADE"
    assert joined.loc[0, "result"] == "NO_TRADE"

    # Observation at epoch 1055 (AFTER the quote existed)
    obs_df2 = pd.DataFrame([{
        "epoch": 1055,
        "signal": "UP",
        "estimated_prob": 0.05,
        "runhigh_win": 1.0
    }])
    joined2 = QuoteOutcomeJoiner.join(obs_df2, qe, symbol="R_75")
    assert joined2.loc[0, "status"] == "QUOTE_AVAILABLE"
    assert joined2.loc[0, "signal"] == "UP"
    assert joined2.loc[0, "result"] == "WIN"


# ==============================================================================
# 10. DYNAMIC EV FILTER & GATE ATTRIBUTION
# ==============================================================================

def test_edge_status_attribution_gates():
    """Tests all scientific rejection statuses: LOW_SAMPLE, NOT_SIGNIFICANT, NEGATIVE_EV,
    POOR_CALIBRATION, FAILED_VALIDATION, FAILED_HOLDOUT, and VALIDATED_EDGE.
    """
    cfg = SampleSizeConfig(min_discovery_samples=50, min_validation_samples=20, min_holdout_samples=20)

    # 1. LOW_SAMPLE
    s1 = determine_edge_status(sample_size=30, adj_p_value=0.01, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg)
    assert s1 == "LOW_SAMPLE"

    # 2. NOT_SIGNIFICANT
    s2 = determine_edge_status(sample_size=100, adj_p_value=0.25, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg)
    assert s2 == "NOT_SIGNIFICANT"

    # 3. NEGATIVE_EV
    s3 = determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=-0.5,
                               conditional_prob=0.02, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg)
    assert s3 == "NEGATIVE_EV"

    # 4. POOR_CALIBRATION
    s4 = determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=False, validation_survived=True, holdout_survived=True, sample_config=cfg)
    assert s4 == "POOR_CALIBRATION"

    # 5. FAILED_VALIDATION
    s5 = determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=False, holdout_survived=True, sample_config=cfg)
    assert s5 == "FAILED_VALIDATION"

    # 6. FAILED_HOLDOUT
    s6 = determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=True, holdout_survived=False, sample_config=cfg)
    assert s6 == "FAILED_HOLDOUT"

    # 7. VALIDATED_EDGE (all gates passed!)
    s7 = determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.0,
                               conditional_prob=0.08, break_even_prob=0.0328,
                               calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg)
    assert s7 == "VALIDATED_EDGE"


# ==============================================================================
# 11. PAPER TRADING SIMULATION MODE
# ==============================================================================

def test_paper_trading_mode_safety_and_journaling(tmp_path):
    """Paper trader strictly executes ZERO live orders (LIVE_EXECUTION_DISABLED = True),
    enforces multi-gate trade eligibility, and logs journal.
    """
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True

    qe = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    paper = PaperTrader(quote_engine=qe, symbol="R_75", default_stake=2.0)

    # 1. Unvalidated setup -> rejected to NO_TRADE
    rec1 = paper.evaluate_opportunity(
        epoch=1000,
        signal="UP",
        estimated_prob=0.08,
        is_calibrated=False,  # Uncalibrated!
        is_validated=True,
        is_holdout_passed=True
    )
    assert rec1.decision == "NO_TRADE"
    assert "UNVERIFIED_CALIBRATION" in rec1.status_reason

    # 2. Validated setup with forward price window (winning path)
    # Entry S_0=10 -> S_1=11 -> S_2=12 -> S_3=13 -> S_4=14 -> S_5=15
    prices = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    rec2 = paper.evaluate_opportunity(
        epoch=1001,
        signal="UP",
        estimated_prob=0.08,
        is_calibrated=True,
        is_validated=True,
        is_holdout_passed=True,
        prices_window=prices,
        signal_idx=0
    )
    assert rec2.decision == "PAPER_TRADE"
    assert rec2.actual_outcome == 1.0
    assert rec2.profit_if_traded == round(61.03 - 2.0, 2)
    assert paper.cumulative_pnl == round(61.03 - 2.0, 2)

    # 3. Export journal test
    journal_path = tmp_path / "paper_journal.csv"
    paper.export_journal(str(journal_path))
    assert journal_path.exists()
    df_j = pd.read_csv(str(journal_path))
    assert len(df_j) == 2


# ==============================================================================
# 12. HISTORICAL DATA COVERAGE AUDIT
# ==============================================================================

def test_historical_data_coverage_audit():
    """Coverage audit reports ticks, calendar dates, duration, and usable windows."""
    epochs = [1700000000 + i for i in range(100)]
    prices = [100.0 + i * 0.1 for i in range(100)]
    df = pd.DataFrame({"epoch": epochs, "price": prices})

    cov = check_data_coverage(df, duration_ticks=5)
    assert cov["total_ticks"] == 100
    assert cov["observations"] == 100
    assert cov["usable_contract_windows"] == 94  # 100 - (1 entry_offset + 5 duration) = 94
    assert cov["duration_days"] < 1.0
    assert cov["is_sufficient"] is False
    assert len(cov["warnings"]) > 0
