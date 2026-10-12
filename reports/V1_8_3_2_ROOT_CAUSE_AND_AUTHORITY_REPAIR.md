# V1.8.3.2 Root Cause & Authority Repair Report

![Authority Status](https://img.shields.io/badge/Authority-INDEPENDENTLY%20VERIFIED-brightgreen.svg)
![Cohort C Verification](https://img.shields.io/badge/Cohort%20C-GROUND%20TRUTH%20ENFORCED-blue.svg)
![Safety Invariant](https://img.shields.io/badge/Safety-LIVE%20DISABLED-red.svg)
![Decision](https://img.shields.io/badge/Decision-NO%20TRADE-orange.svg)

## 1. Executive Summary & Defect Overview
In V1.8.3.1, the reporting queries corrected the mixed economic denominator defect by requiring non-null quotes and hypothetical returns. However, the system still suffered from two critical authority defects:

1. **Non-Verified Cohort C Promotion**: Observations were promoted to Cohort C solely on the presence of non-null fields (`proposal_id`, `ask_price`, `total_payout`, `hypothetical_return`), without verifying:
   - Whether the proposal actually existed in `broker_proposals` table.
   - Whether the quote was fresh ($\le 5.0$s) and received before decision commitment.
   - Whether the prediction had verifiable pre-outcome commitment timestamps.
   - Whether the model was registered and cryptographically authentic.
2. **Hardcoded Model Verification Bypass**: In `forward_shadow_engine.py`, the outcome resolver passed `model_is_verified=True` directly into the chronology auditor, completely bypassing per-observation model validation.

## 2. Core Architectural Repair: Strict Cohort Authority Validator
V1.8.3.2 introduces `StrictCohortAuthorityValidator`, operating under the non-negotiable principle:
**No observation may certify its own scientific authority.**
Stored annotations (`evidence_cohort`, `prospective_status`, `model_type`, `model_is_verified`) are treated as untrusted metadata. Scientific authority is earned strictly by evaluating ground truth records across six independent tiers:
- Tier A: Source Authenticity (genuine broker ticks, symbol in research markets).
- Tier B: Prospective Chronology (verified commit timestamp, strictly positive lead time before future ticks).
- Tier C: Model Provenance (per-observation check against `AuthoritativeModelRegistry`, valid checksum).
- Tier D: Quote Authority (proposal present in `broker_proposals`, matching parameters, fresh, pre-decision).
- Tier E: Outcome Integrity (next-tick entry mapping, exact expiry, strict equality/monotonicity resolution).
- Tier F: Economic Integrity (internal arithmetic reconciles within floating precision).
