# V1.8.1 Quote-Level Economics & Evidence Eligibility Audit Report

![Quote Engine](https://img.shields.io/badge/Quote_Engine-PER--OBSERVATION_MATCHING-brightgreen.svg)
![Fail Closed](https://img.shields.io/badge/Missing_Quotes-FAIL_CLOSED-red.svg)
![Reference Mode](https://img.shields.io/badge/Reference_Economics-PROHIBITED_FROM_QUALIFYING-orange.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Defect Remediation

In Release V1.8.0, the hypothesis evaluator evaluated strategy economics using fixed parameter assumptions:
$$\text{typical\_quote} = (2.00, 3.91) \implies \text{BreakEven} = \frac{2.00}{3.91} \approx 0.5115$$
While a constant reference quote is useful for descriptive illustrations, **it is invalid as authenticated quote-level empirical evidence**. Under real broker conditions:
1. Payout ratios fluctuate based on synthetic index volatility, market hours, and order sizing.
2. Quoted prices may become stale or expire before decision execution.
3. Matching a fixed quote across thousands of observations masks periods where the broker hurdle was substantially higher or quotes were unavailable.

Release V1.8.1 introduces `quote_economics_engine.py`, establishing a rigorous, per-observation quote matching architecture. Fixed quote assumptions are permanently prohibited from satisfying candidate qualification.

---

## 2. Per-Observation Matching Architecture (`quote_economics_engine.py`)

Every individual decision $i$ evaluated by the platform must be individually paired with an authentic broker proposal response satisfying strict multidimensional matching rules:

### 2.1 Multidimensional Matching Requirements

An observation at decision epoch $t_{\text{dec}}$ matches a candidate quote record $q$ if and only if:
1. **Market Match**: $q.\text{market\_symbol} == \text{symbol}_{\text{obs}}$.
2. **Contract Direction Match**: $q.\text{contract\_type} == \text{contract\_type}_{\text{obs}}$ (strictly mapped: `CALL` / `RISE` vs `PUT` / `FALL`).
3. **Duration Match**: $q.\text{contract\_duration} == \text{duration}_{\text{obs}}$ (e.g., 2, 3, 5, 10 ticks).
4. **Currency and Basis**: $q.\text{currency} == \text{"USD"}$ and $q.\text{basis} == \text{"stake"}$.
5. **Strict Chronological Receipt**: $q.\text{response\_timestamp} \le t_{\text{dec}}$ (quote was received strictly at or before decision commitment).
6. **Freshness Invariant**: Quote age $\Delta t = t_{\text{dec}} - q.\text{response\_timestamp} \le \tau_{\text{max}}$.
   - Execution-Quality Freshness: $\tau_{\text{max}} = 5.0\text{ seconds}$.
   - Chronological Window: $\tau_{\text{max}} = 60.0\text{ seconds}$.
7. **Price Term Validity**: $q.\text{ask\_price} > 0.0$ and $q.\text{total\_payout} > q.\text{ask\_price}$.

### 2.2 Per-Observation Economic Metrics

Aggregation occurs strictly **after** validating and calculating individual observations:
$$\text{break\_even}_i = \frac{\text{ask\_price}_i}{\text{total\_payout}_i}$$
$$\text{predicted\_ev}_i = (P_{\text{model}, i} \times \text{total\_payout}_i) - \text{ask\_price}_i$$
$$\text{realized\_return}_i = (\text{outcome}_i \times \text{total\_payout}_i) - \text{ask\_price}_i$$

---

## 3. Strict Fail-Closed Protocol & Rejection Taxonomy

If an observation fails any matching criterion, the engine fails closed without inventing prices:

| Matching Condition | Engine Classification | Evidence Status | Candidate Impact |
| :--- | :--- | :--- | :--- |
| No proposal record found prior to $t_{\text{dec}}$ | `QUOTE_UNAVAILABLE` | Ineligible | Cannot qualify |
| Quote received after $t_{\text{dec}}$ ($t_{\text{resp}} > t_{\text{dec}}$) | `FUTURE_QUOTE` | Ineligible (Lookahead violation) | Discarded |
| Quote age $\Delta t > 5.0\text{s}$ | `STALE_QUOTE` | Ineligible | Cannot qualify |
| Cross-market symbol mismatch | `CROSS_MARKET_MISMATCH` | Ineligible | Discarded |
| Cross-duration mismatch | `CROSS_DURATION_MISMATCH` | Ineligible | Discarded |
| Invalid price terms ($\text{payout} \le \text{ask}$) | `INVALID_PRICE_TERMS` | Ineligible | Discarded |
| Constant illustrative fallback applied | `REFERENCE_PRICE_APPLIED` | `REFERENCE_ECONOMICS_ONLY` | Prohibited from qualifying |

---

## 4. Separation of Evaluation Modes

To maintain empirical integrity, the platform formally decouples:

### Mode 1: `QUOTE_VERIFIED`
- Requires authentic, persisted broker proposal responses.
- Evaluates per-observation economics using exact matched proposal parameters.
- Only datasets achieving $\ge 50\%$ quote eligibility coverage with positive predicted EV, positive realized EV, and positive conservative bounds may qualify as candidates.

### Mode 2: `REFERENCE_ECONOMICS_ONLY`
- Applies fixed illustrative parameters (e.g., $\$2.00 / \$3.91$).
- Labeled explicitly as `REFERENCE_ECONOMICS_ONLY` in machine-readable JSON and Markdown reports.
- **Strict Invariant**: Reference economics mode can NEVER satisfy candidate qualification. Any hypothesis evaluated under reference mode automatically receives verdict `REFERENCE_ECONOMICS_ONLY`.

---

## 5. Quote Provenance Verification

In historical database audits (`quotes.db` and session journals):
1. **Correlation Identity**: Proposal IDs (`id`) and Quote IDs (`quote_id`) are mapped directly to Deriv API JSON-RPC responses.
2. **Session Journaling**: Proposal timestamps are synchronized with server epoch receipts.
3. **No Synthetic Proposals**: Generated examples or test mocks are quarantined from empirical research stores.

---

## 6. Conclusion

By implementing `QuoteLevelEconomicEngine`, Release V1.8.1 guarantees that no trading candidate can be declared without authentic, timely, and verified broker pricing. Constant payout assumptions can no longer bypass real-world broker execution friction.
