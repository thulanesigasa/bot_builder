# V1.8.3.2 Strict Cohort Eligibility Audit

![Validator Version](https://img.shields.io/badge/Validator-v1.8.3.2-blue.svg)
![Tiers](https://img.shields.io/badge/Verification-6%20INDEPENDENT%20TIERS-brightgreen.svg)
![Safety](https://img.shields.io/badge/Safety-NO%20TRADE-orange.svg)

## 1. Six-Tier Authority Matrix
To qualify for Cohort C, an observation must achieve an explicit `True` verdict on all six evaluation tiers:

| Tier | Evaluation Domain | Verification Conditions | Failure Mode |
| :--- | :--- | :--- | :--- |
| **Tier A** | Source Authenticity | Symbol in `RESEARCH_MARKETS`, signal tick present in `broker_ticks`, `source_classification == SOURCE_BROKER_CAPTURED`. | Rejection from Cohort C |
| **Tier B** | Prospective Chronology | `journal_commit_timestamp` > 0, `first_future_tick_receipt_ts` > 0, `first_future_epoch > signal_epoch`, `lead_time >= 0`. | Rejection from Cohort C (demoted to Cohort B if quoted) |
| **Tier C** | Model Provenance | Model registered in `AuthoritativeModelRegistry`, checksum matches registered digest, no mock placeholders. | Rejection from Cohort C (demoted to Cohort B if quoted) |
| **Tier D** | Quote Authority | Proposal exists in `broker_proposals`, symbol/type/duration/unit match, response $\le$ decision TS, age $\le 5.0$s. | Rejection from Cohort C & B (demoted to Cohort A) |
| **Tier E** | Outcome Integrity | Outcome status resolved, forward ticks count $\ge$ duration, independent outcome resolution matches recorded outcome. | Quarantined from all cohorts |
| **Tier F** | Economic Integrity | Ask and payout positive, $\text{BreakEven} = \text{Ask}/\text{Payout}$, $\text{Return} = y \times \text{Payout} - \text{Ask}$ reconciles. | Rejection from Cohort C |

## 2. Decision Logic & Fail-Closed Routing
```text
Observation Input
       |
       +---> [Tiers A, B, C, D, E, F ALL PASS] ---------> COHORT C (Strict Prospective Economic Feasibility)
       |
       +---> [Tier D PASS, but Tier B or C FAILS] ------> COHORT B (Quote-Matched Exploratory Observation)
       |
       +---> [Tier E PASS, but Tier D FAILS] -----------> COHORT A (Pure Prospective Prediction Evaluation)
       |
       +---> [Tier E FAILS or Incomplete] --------------> QUARANTINED / UNRESOLVED
```
