# V1.7.4 DUAL-DURATION MODEL REPORT: 2-TICK & 5-TICK INDEPENDENT ARCHITECTURES

[![Version](https://img.shields.io/badge/Version-V1.7.4-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Model-Architecture](https://img.shields.io/badge/Architecture-Dual--Duration%20Independent-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Models-Verified](https://img.shields.io/badge/Models-2T%20%7C%205T%20Frozen-brightgreen.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety-Invariant](https://img.shields.io/badge/Live%20Trading-Permanently%20Disabled-red.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary & Model Isolation Mandate

In accordance with Master Development Prompt V1.7.4 Part D & E, this report documents the dual-duration quantitative model architecture for Deriv Volatility 75 (`R_75`).

### Core Architectural Guarantees
1. **Preservation of Existing 5-Tick Model**: The authoritative 5-tick frozen model artifact (`M_R_75_5TICK_20261008_132512.json`) was completely preserved. None of its parameters, priors, or validation metrics were modified or overwritten.
2. **Independent 2-Tick Model**: A separately versioned 2-tick frozen model artifact (`M_R_75_2TICK_20261011_120000.json`) was trained, calibrated, and serialized with independent provenance.
3. **Strict Identity Separation**: Every model explicitly declares its `contract_duration`, `model_id`, `model_version`, and cryptographic `model_hash`. Cross-duration substitutions are strictly blocked by Gate 4 (`MODEL_CONTRACT_MISMATCH`).

---

## 2. Model Specifications & Cryptographic Provenance

| Parameter / Metadata | 5-Tick Frozen Model | 2-Tick Frozen Model |
| :--- | :--- | :--- |
| **Model Identifier** | `M_R_75_5TICK_20261008_132512` | `M_R_75_2TICK_20261011_120000` |
| **Model Version** | `1.5.3` | `1.7.4` |
| **Contract Duration** | **5 ticks** (`5t`) | **2 ticks** (`2t`) |
| **Contract Family** | `RUNHIGH_RUNLOW` (Only Ups / Only Downs) | `RUNHIGH_RUNLOW` (Only Ups / Only Downs) |
| **Underlying Symbol** | `R_75` (Volatility 75 Index) | `R_75` (Volatility 75 Index) |
| **Training Dataset** | `R_75_master.csv` (43,184 ticks) | `R_75_master.csv` (43,184 ticks) |
| **Dataset SHA-256** | `8273d215bf93f46d3e12d0d82e46f1ebfca59138180ebfcf8cda7d4a9bedd7a3` | `8273d215bf93f46d3e12d0d82e46f1ebfca59138180ebfcf8cda7d4a9bedd7a3` |
| **Effective Training Samples** | 43,153 observations | 43,156 observations |
| **Feature Schema Version** | `1.5.3` | `1.5.3` (Canonical Parity) |
| **Approval Status** | `VALIDATED_RESEARCH` (Simulated Paper) | `RESEARCH_ONLY` (Shadow Only) |

---

## 3. Feature Conditioning & Schema Definitions

Both models share the canonical feature schema defined in `feature_schema.py` to ensure exact mathematical parity:

1. **`mom_bin` (Momentum)**: 5-tick price return discretized into `STRONG_BULL` ($> +0.005$), `MILD_BULL`, `NEUTRAL`, `MILD_BEAR`, and `STRONG_BEAR` ($< -0.005$).
2. **`streak_bin` (Consecutive Streak)**: Count of consecutive directional price changes: `EXTREME_UP_STREAK` ($\ge 4$), `HIGH_UP_STREAK` ($2..3$), `NEUTRAL_STREAK` ($-1..1$), `HIGH_DOWN_STREAK` ($-3..-2$), `EXTREME_DOWN_STREAK` ($\le -4$).
3. **`vol_bin` (Short-Term Volatility)**: 5-tick rolling standard deviation categorized into `HIGH_VOL` vs `LOW_VOL`.
4. **`accel_bin` (Price Acceleration)**: Second difference of price ($\Delta P_t - \Delta P_{t-1}$): `ACCEL_UP` ($> 0$) vs `ACCEL_DOWN` ($< 0$).

---

## 4. Empirical Base Rates vs. Economic Hurdle Baselines

### Theoretical and Empirical Comparison

| Metric | 5-Tick Model (5T) | 2-Tick Model (2T) | Mathematical Basis |
| :--- | :---: | :---: | :--- |
| **Theoretical Symmetric Baseline** | **3.125%** ($(0.5)^5$) | **25.000%** ($(0.5)^2$) | Random walk assumption ($P(\text{up}) = P(\text{down}) = 0.5$) |
| **Empirical Base Rate RUNHIGH** | **3.277%** (0.03277) | **25.341%** (0.25341) | Observed historical frequency on `R_75_master` |
| **Empirical Base Rate RUNLOW** | **2.973%** (0.02973) | **24.752%** (0.24752) | Observed historical frequency on `R_75_master` |
| **Deriv Proposal Break-Even Hurdle** | **3.275%** ($2.00 / 61.07$) | **26.212%** ($2.00 / 7.63$) | Exact quote break-even ($Ask / Payout$) |
| **Unconditional RUNHIGH Edge** | **+0.002%** (+0.00002) | **-0.871%** (-0.00871) | Base rate minus economic hurdle |
| **Unconditional RUNLOW Edge** | **-0.302%** (-0.00302) | **-1.460%** (-0.01460) | Base rate minus economic hurdle |
| **Unconditional Ordinary EV / $2** | **+$0.0013** (RUNHIGH) | **-$0.0665** (RUNHIGH) | $\text{BaseRate} \times \text{Payout} - \text{Stake}$ |
| **Unconditional Ordinary EV / $2** | **-$0.1812** (RUNLOW) | **-$0.1114** (RUNLOW) | $\text{BaseRate} \times \text{Payout} - \text{Stake}$ |

### Key Findings
1. **2-Tick Base Rates Suffer from Negative Expected Value**: Although the 2-tick contract produces a winning outcome on ~25% of all ticks, its required break-even hurdle is **26.212%**. Without extreme conditioning, the unconditional 2-tick strategy loses money systematically.
2. **5-Tick Base Rate Sits on the Breakeven Threshold**: RUNHIGH's base rate (3.277%) is almost perfectly identical to the broker's 3.275% pricing threshold, yielding an unconditional EV of virtually zero (+$0.0013).

---

## 5. Bayesian Shrinkage & Calibration Parameters

Both models utilize Empirical Bayes shrinkage to guard against small-sample estimation noise in rarely visited feature states:

$$P_{\text{smoothed}} = \frac{k + M \cdot P_0}{n + M}$$

Where:
- $k$: observed wins in feature state
- $n$: sample count in feature state
- $M$: shrinkage prior pseudo-weight (set to $M = 50.0$)
- $P_0$: unconditional empirical base rate

Uncertainty quantification is computed using exact Wilson score 95% confidence intervals to establish rigorous statistical lower bounds ($P_{\text{lower}}$) for conservative EV gating.
