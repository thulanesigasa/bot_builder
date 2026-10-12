# V1.7.4.4 Root Cause Investigation & Schema Remediation Report

![Release](https://img.shields.io/badge/Release-V1.7.4.4-0A84FF)
![Status](https://img.shields.io/badge/Status-AUDITED_%26_RESOLVED-30D158)
![Market](https://img.shields.io/badge/Market-Deriv_Volatility_75_Index-FF9F0A)
![Safety](https://img.shields.io/badge/Safety-LIVE_EXECUTION_DISABLED-FF453A)
![Zero_Emojis](https://img.shields.io/badge/Style-Zero_Emojis_Enforced-64D2FF)

---

## 1. Executive Summary & Defect Overview

During the validation audit of the V1.7.4.3 release, an anomalous experimental result was detected in the prospective dual-duration evaluation report: across all four evaluated contract configurations (2T RUNHIGH, 2T RUNLOW, 5T RUNHIGH, 5T RUNLOW), the 300-second paired live session recorded exactly **0 wins** and **136 losses** per configuration, with reported mean predicted probabilities identically matching the theoretical random walk baselines ($0.2500$ for 2-tick and $0.03125$ for 5-tick).

An exhaustive investigation across the underlying SQLite databases, live tick archives, and evaluation source code confirmed that this result was **not caused by market failure, trading engine failure, or model prediction failure**. Rather, it was caused entirely by a **database-schema column name mismatch** inside the prospective session evaluator in `dual_duration_research.py`.

The forward collection service (`forward_collection_service.py`), paired observer (`forward_observer.py`), and journal database (`forward_journal.py`) had correctly recorded genuine model predictions and authentic market outcomes into the database. However, the evaluation layer attempted to read non-existent column names, falling back to permissive defaults that converted every valid winning outcome into a synthetic loss ($0.0$) and every frozen model probability into a theoretical baseline constant.

---

## 2. Technical Anatomy of the Failure

### 2.1 Permissive Dictionary Lookups & Silent Defaults

In V1.7.4.3 `dual_duration_research.py`, the evaluation loop inspected prediction rows returned from `data/forward_predictions.db` using the following logic:

```python
# DEFECTIVE V1.7.4.3 EVALUATION ACCESS PATTERN:
out_high = p.get("outcome_runhigh")
out_low = p.get("outcome_runlow")

y_true.append(1.0 if out_high == 1 else 0.0)
p_rh = p.get("prob_runhigh") or 0.25
p_rl = p.get("prob_runlow") or 0.25
```

### 2.2 Authoritative Database Schema vs Evaluator Queries

A direct schema introspection of `data/forward_predictions.db` reveals the authoritative column names defined in `forward_journal.py`:

| Evaluator Field Attempted (V1.7.4.3) | Authoritative Schema Column (`forward_predictions`) | Result of Permissive `.get()` | Downstream Impact |
| :--- | :--- | :--- | :--- |
| `outcome_runhigh` | `runhigh_win` | `None` | `1.0 if None == 1 else 0.0` $\rightarrow$ `0.0` (Forced Loss) |
| `outcome_runlow` | `runlow_win` | `None` | `1.0 if None == 1 else 0.0` $\rightarrow$ `0.0` (Forced Loss) |
| `prob_runhigh` | `runhigh_pred_prob` | `None` | `None or 0.25` $\rightarrow$ `0.25` (Fallback Baseline) |
| `prob_runlow` | `runlow_pred_prob` | `None` | `None or 0.25` $\rightarrow$ `0.25` (Fallback Baseline) |

Because `.get()` silently returned `None` when the key was missing:
1. Every resolved winning outcome was evaluated as `out_high == 1` being `False`, silently mapping into `0.0`.
2. As a consequence, all 136 decisions were classified as losses ($0$ wins, $136$ losses, $0.00\%$ win rate).
3. The genuine, time-varying frozen model probabilities (e.g. $0.2561$, $0.2374$, $0.0337$) were overwritten by `or 0.25` / `or 0.03125`.

---

## 3. Authoritative Evidence Recovery

To establish whether genuine wins existed in the database, `data/forward_predictions.db` and the linked `forward_outcomes` table were directly queried using the authoritative column names:

### Session `c14ac5fb-afaf-440c-ad4e-1a2187f0c42e` (300-Second Paired Session)

| Configuration | Total Observations | Stored Wins (`runhigh_win` / `runlow_win`) | Stored Losses | Authentic Win Rate | Stored Mean Probability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 136 | **42** | 94 | **30.88%** | 0.2561 |
| **2T RUNLOW** | 136 | **19** | 117 | **13.97%** | 0.2374 |
| **5T RUNHIGH** | 136 | **10** | 126 | **7.35%** | 0.0337 |
| **5T RUNLOW** | 136 | **1** | 135 | **0.74%** | 0.0303 |

### Session `7b82fef5-fc65-4b38-9750-251aae55395d` (60-Second Live Preflight)

| Configuration | Total Observations | Stored Wins | Stored Losses | Authentic Win Rate | Stored Mean Probability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2T RUNHIGH** | 17 | **1** | 16 | **5.88%** | 0.2522 |
| **2T RUNLOW** | 17 | **7** | 10 | **41.18%** | 0.2319 |
| **5T RUNHIGH** | 17 | **0** | 17 | **0.00%** | 0.0323 |
| **5T RUNLOW** | 17 | **3** | 14 | **17.65%** | 0.0302 |

The stored records conclusively prove that genuine wins occurred during both prospective sessions, and genuine frozen model probabilities were actively computed and journaled.

---

## 4. Architectural Remediation (V1.7.4.4)

### 4.1 Strict Canonical Record Adaptation Layer

The permissive dictionary lookup has been permanently replaced by a typed `ResearchObservation` dataclass and canonical adapter `adapt_prediction_record(pred_row, outcome_row)` in `dual_duration_research.py`.

```python
@dataclass(frozen=True)
class ResearchObservation:
    prediction_id: str
    session_id: str
    contract_duration: int
    decision_timestamp: float
    model_id: str
    model_checksum: str
    quote_id: Optional[str]
    runhigh_pred_prob: Optional[float]
    runlow_pred_prob: Optional[float]
    runhigh_outcome: str        # 'WIN', 'LOSS', 'UNAVAILABLE'
    runlow_outcome: str         # 'WIN', 'LOSS', 'UNAVAILABLE'
    outcome_status: str
    ...
```

### 4.2 Strict Three-Way Outcome Classification

The binary ternary conversion `1.0 if stored == 1 else 0.0` has been prohibited. Outgoing records are strictly mapped to three states:
- `WIN`: Authoritative stored outcome is explicitly $1.0$.
- `LOSS`: Authoritative stored outcome is explicitly $0.0$.
- `UNAVAILABLE`: Missing, pending, data-gap, or discrepant records.

Under no circumstances can an incomplete outcome, a data gap, or a database conflict be silently coerced into a loss.

### 4.3 Prohibition of Theoretical Probability Fallbacks

Model probabilities must be authentic floating-point numbers in the closed interval $[0.0, 1.0]$. Genuine $0.0$ probabilities are preserved. Nulls, `NaN` values, infinities, and unrecorded fields raise exclusion warnings and are classified as `missing_probability_count`. Substitution of theoretical random-walk constants ($0.25$ / $0.03125$) is strictly banned.

### 4.4 Unambiguous Session Lookup

Session lookups using short prefixes must resolve uniquely across the database. Any prefix that matches multiple session records triggers an immediate `ValueError`, preventing accidental cross-session contamination.

---

## 5. Verification & Regression Coverage

The repair is verified by automated regression test suite `tests/test_v1744_schema_repair_and_reconstruction.py`, testing:
1. `test_authoritative_field_mapping_and_zero_fallback`: Validates authoritative schema adaptation and prohibits zero defaults.
2. `test_missing_and_invalid_probabilities_never_receive_defaults`: Asserts null/NaN handling.
3. `test_strict_three_way_outcome_classification`: Asserts pending and data gaps are never losses.
4. `test_cross_table_outcome_discrepancy_rejection`: Cross-checks `forward_predictions` vs `forward_outcomes`.
5. `test_exact_session_prefix_uniqueness_and_ambiguity_rejection`: Validates prefix uniqueness.
6. `test_prospective_authority_rejects_disordered_timestamps`: Enforces causal timestamp order ($T_{feat} \le T_{inf} \le T_{commit}$).
7. `test_end_to_end_evaluation_regression`: Real SQLite database fixture execution verifying all wins, losses, and EV.
