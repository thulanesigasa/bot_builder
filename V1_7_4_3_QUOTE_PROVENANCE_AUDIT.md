# V1.7.4.3 Quote Provenance Audit & Economic Verification Report

![Status](https://img.shields.io/badge/Audit-PASSED-brightgreen)
![Release](https://img.shields.io/badge/Release-V1.7.4.3-blue)
![Provenance](https://img.shields.io/badge/Quote_Provenance-STRICT_VERIFIED-success)
![Safety](https://img.shields.io/badge/Real_Money_Trading-PERMANENTLY_DISABLED-red)

---

## 1. Executive Summary

This audit report documents the formal validation of the **Strict Quote Provenance System** implemented in `bot_builder` Release V1.7.4.3. The primary mandate of this release is the elimination of all permissive, ambiguous, stale, lookahead, or unverified broker quote associations in prospective economic research on the Deriv Volatility 75 Index (`R_75`).

Under V1.7.4.3:
1. **Explicit Multi-Dimension Matcher**: Quote eligibility requires verified values across 8 core dimensions: database record identity, market symbol, contract duration, contract direction, currency (`USD`), response timestamp causality, freshness, and session attribution. Missing mandatory fields fail closed immediately with zero synthetic default values.
2. **Composite Quote Identity**: Protects against proposal ID reuse by establishing an immutable composite identity: `(quote_record_id, proposal_id, session_id, response_timestamp, contract_parameters)`. Duplicate proposal IDs represent legitimate sequential responses and never overwrite earlier records.
3. **Strict Causal Timestamp Verification**: Enforces $t_{\text{response}} \le t_{\text{decision}}$ with strictly zero future-timestamp tolerance ($0.0\,\text{s}$). Clock consistency requires $t_{\text{request}} \le t_{\text{response}}$.
4. **Tick-Aware Quote Invalidation**: Discards the naive assumption that quotes remain valid solely due to wall-clock time. If underlying spot price changes between quote receipt and decision point, the quote is marked `QUOTE_INVALIDATED_BY_INTERVENING_TICK` and `QUOTE_VALIDITY_UNVERIFIED`.
5. **Quote-Specific Economic Valuation**: All expected value (EV) and break-even calculations derive strictly from individual matched quote ask prices and total payouts. Reference scenario payouts are excluded from economic qualification.

---

## 2. Strict Quote Matching Architecture

### 2.1 Multi-Dimensional Validation Pipeline

Every decision point at time $t_{\text{decision}}$ undergoes sequential validation against recorded broker quotes in `dual_duration_research.py`:

```
+-------------------------------------------------------------------------+
|                  Quote Record Pool (quote_records)                     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| 1. Contract Parameter & Identity Gate                                   |
|    - Quote Identity: quote_record_id or persistent ID != None/empty    |
|    - Market Symbol: q_sym == 'R_75' (missing fails closed)              |
|    - Currency: q_curr == 'USD' (missing fails closed, no default)       |
|    - Contract Duration: q_dur == duration (2 or 5 ticks)                |
|    - Contract Direction: q_type in ('RUNHIGH', 'RUNLOW', aliases)       |
|    - Session Attribution: q_sess == expected_session_id                 |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| 2. Chronological Causality Gate                                         |
|    - Causality: response_timestamp <= decision_timestamp (zero lookahead)|
|    - Clock Provenance: request_timestamp <= response_timestamp         |
|    - Non-null/Non-NaN timestamps                                        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| 3. Economic Evaluability Gate                                           |
|    - Ask Price > 0 and Total Payout > 0                                 |
|    - Ask Price < Total Payout                                           |
|    - Collection Status == 'QUOTE_AVAILABLE'                             |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| 4. Execution Quality & Freshness Gate                                   |
|    - Wall-Clock Freshness: (decision_timestamp - response_ts) <= max_age|
|    - Ambiguity Check: No conflicting prices at identical timestamps    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| 5. Tick-Aware Market Invalidation Gate                                  |
|    - Intervening Ticks: No price movement between quote and decision    |
|    - Max Intervening Ticks: <= max_allowed (default 2 ticks)            |
|    - Spot Verification: quote spot matches market tick spot             |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                     ELIGIBLE ECONOMIC QUOTE                             |
+-------------------------------------------------------------------------+
```

---

## 3. Rejection Taxonomy & Coverage Classification

### 3.1 Standardized Rejection Codes

| Rejection Code | Description | Fail-Closed Consequence |
| :--- | :--- | :--- |
| `QUOTE_ID_MISSING` | Quote record lacks persistent identifier | Rejected from candidate pool |
| `QUOTE_MISSING_SYMBOL` | `market_symbol` is empty or null | Never defaulted to `R_75`; rejected |
| `QUOTE_WRONG_SYMBOL` | `market_symbol` != target symbol | Mismatched asset; rejected |
| `QUOTE_MISSING_CURRENCY` | `currency` is empty or null | Never defaulted to `USD`; rejected |
| `QUOTE_CURRENCY_MISMATCH` | `currency` != `'USD'` | Non-USD pricing rejected |
| `QUOTE_WRONG_DURATION` | `contract_duration` != decision duration | Cross-duration contamination blocked |
| `QUOTE_WRONG_DIRECTION` | `contract_type` != decision direction | Cross-direction contamination blocked |
| `QUOTE_WRONG_SESSION` | `session_id` != expected session ID | Cross-session leakage blocked |
| `QUOTE_LOOKAHEAD_REJECTED` | `response_timestamp > decision_timestamp` | Strict lookahead violation blocked |
| `QUOTE_RESPONSE_TIME_MISSING` | Missing or NaN response timestamp | Unverifiable causality blocked |
| `QUOTE_PRICE_OR_PAYOUT_INVALID`| Ask <= 0, payout <= 0, or ask >= payout | Non-viable economic terms blocked |
| `QUOTE_STALE` | Quote age exceeds freshness window | Stale broker proposal blocked |
| `QUOTE_AMBIGUOUS_PROPOSAL` | Conflicting prices for same proposal | Conflicting data rejected |
| `QUOTE_INVALIDATED_BY_INTERVENING_TICK` | Underlying spot moved after quote | Price-invalidated proposal blocked |
| `QUOTE_VALIDITY_UNVERIFIED` | Continuing validity cannot be verified | Demoted from executable status |
| `NO_QUOTES_PROVIDED` | Quote records empty for decision | EV marked unavailable (`None`) |

### 3.2 Granular Coverage Metrics

The system reports coverage across four distinct verification dimensions:
- **Raw Association Coverage (`raw_cov`)**: Decisions with at least one quote matching basic contract identity.
- **Chronological Validity Coverage (`chrono_cov`)**: Decisions with at least one quote received prior to the decision point ($t_{\text{resp}} \le t_{\text{dec}}$).
- **Economic Evaluability Coverage (`econ_cov`)**: Decisions with at least one chronologically valid quote bearing viable economic pricing ($\text{ask} > 0$, $\text{payout} > \text{ask}$).
- **Execution Quality Coverage (`exec_cov`)**: Decisions with a valid quote satisfying freshness, tick continuity, and proposal clarity.

---

## 4. Quote-Specific Economic Calculations

### 4.1 Strict Formulae

For each eligible matched decision $i \in \{1, \dots, m\}$:
- **Individual Break-Even Hurdle**:
  $$\text{BreakEven}_i = \frac{\text{AskPrice}_i}{\text{TotalPayout}_i}$$
- **Individual Model Expected Value**:
  $$\text{EV}_i = P_{\text{model}, i} \times \text{TotalPayout}_i - \text{AskPrice}_i$$
- **Individual Realized Hypothetical Return**:
  $$R_i = y_i \times \text{TotalPayout}_i - \text{AskPrice}_i \quad \text{where } y_i \in \{0, 1\}$$
- **Aggregate Ordinary EV**:
  $$\overline{\text{EV}} = \frac{1}{m} \sum_{i=1}^m \text{EV}_i$$
- **Dependence-Aware Conservative EV**:
  Calculated using Moving-Block Bootstrap (MBB) with block size $b = \max(2, \text{duration} + 1)$ across per-decision realized returns $\{R_i\}_{i=1}^m$ at the 5th percentile ($95\%$ lower confidence bound).
  If $m < \max(30, 2b)$, conservative EV is marked strictly `None` (`INSUFFICIENT_SAMPLE`).

### 4.2 Exclusion of Fixed Reference Fallbacks

Prior versions used fallback reference parameters ($7.63$ for 2T, $61.07$ for 5T) when quotes were missing. In V1.7.4.3:
- If eligible quote count $m = 0$, quote-verified EV is strictly `None`.
- Reference scenario evaluations operate under `EvaluationMode.REFERENCE_SCENARIO` and fail closed into verdict `REFERENCE_SCENARIO_ONLY`.
- Zero synthetic substitution is permitted under any circumstances.

---

## 5. Audit Results Summary

| Test Category | Invariant Tested | Test Count | Result |
| :--- | :--- | :--- | :--- |
| Missing Fields Fail-Closed | Symbol, Currency, Direction, Duration, Identity | 5 | PASSED |
| Session Attribution | Cross-session quote rejection | 1 | PASSED |
| Composite Identity | Proposal ID reuse with distinct records | 1 | PASSED |
| Causality Verification | Lookahead quote rejection ($t_{\text{resp}} > t_{\text{dec}}$) | 1 | PASSED |
| Tick-Aware Invalidation | Intervening price change rejection | 1 | PASSED |
| Full 14-Dimension Stats | Complete rejection accounting | 1 | PASSED |
| Variable Price EV | EV uses actual quotes vs reference | 1 | PASSED |
| Reference Scenario Isolation| Positive reference EV cannot qualify | 1 | PASSED |
| Missing Quote Fail-Closed | Empty quotes yield `None` EV | 1 | PASSED |
| **Total Provenance Tests** | | **13** | **100% PASSED** |

---

## 6. Remaining Limitations

1. **Non-Purchasing Operating Mode**: Because real-money trading is permanently disabled (`LIVE_EXECUTION_DISABLED = True`), all collected quotes represent broker proposals, not executed contract receipts. Fill price slippage cannot be observed.
2. **WebSocket Rate Limits**: High-frequency proposal polling is bounded to $\ge 2.0\,\text{s}$ intervals to adhere to broker API rate limits.
