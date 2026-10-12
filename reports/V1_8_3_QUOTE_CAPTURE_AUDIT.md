# Deriv Multi-Market V1.8.3 — Broker Quote Capture & Inventory Audit

![Quote Source](https://img.shields.io/badge/Quote%20Origin-GENUINE%20DERIV%20API-brightgreen.svg)
![Proposals Captured](https://img.shields.io/badge/Proposals%20Logged-13-blue.svg)
![Quote Match Isolation](https://img.shields.io/badge/Match%20Isolation-ENFORCED-success.svg)

## 1. Proposal Quote Capture Inventory
- Total authentic broker proposals captured: `13`
- Total observations matched with genuine proposals: `24`
- Execution-quality SHADOW proxy observations (Cohort C): `16`

## 2. Strict Matching & Isolation Rules
The following strict isolation rules are enforced at database and engine boundaries:
1. **Contract Family Isolation**: Rise/Fall proposals (`CALL`, `PUT`) never match Only Ups/Downs predictions (`RUNHIGH`, `RUNLOW`).
2. **Direction Isolation**: `CALL` never matches `PUT`.
3. **Duration Isolation**: 2-tick proposal quotes never match 5-tick predictions.
4. **Market Isolation**: `R_75` quotes never match `1HZ100V` predictions.
5. **Freshness Barrier**: Quotes older than 5.0 seconds from the decision timestamp are rejected.
6. **Chronological Boundary**: Future quotes ($t_{\text{quote}} > t_{\text{decision}}$) are rejected.
