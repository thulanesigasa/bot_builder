# V1.8.0 Market Capability Matrix

![Status](https://img.shields.io/badge/Status-VERIFIED-blue.svg)
![Target Markets](https://img.shields.io/badge/Markets-6_Target_Indices-indigo.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

## 1. Executive Summary & Broker Identification

This document establishes the authoritative six-market capability matrix for the Deriv
Rise/Fall quantitative research engine in V1.8.0. Every symbol, precision, and duration constraint
was verified via live WebSocket queries against `api.derivws.com`.

| Market Identifier | Display Name | Tick Interval | Pip Precision | Min Duration | Max Duration | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `R_100` | Volatility 100 Index | 2.0s | 2 | 1t | 10t | ACTIVE |
| `1HZ100V` | Volatility 100 (1s) Index | 1.0s | 2 | 1t | 10t | ACTIVE |
| `R_75` | Volatility 75 Index | 2.0s | 4 | 1t | 10t | ACTIVE |
| `1HZ75V` | Volatility 75 (1s) Index | 1.0s | 4 | 1t | 10t | ACTIVE |
| `R_50` | Volatility 50 Index | 2.0s | 4 | 1t | 10t | ACTIVE |
| `1HZ50V` | Volatility 50 (1s) Index | 1.0s | 4 | 1t | 10t | ACTIVE |

## 2. Multi-Market Capability Matrix (Market x Contract x Duration)

| Market | Contract | 2 Ticks | 3 Ticks | 5 Ticks | 10 Ticks | 20 Ticks | Status Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `R_100` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `R_100` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ100V` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ100V` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `R_75` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `R_75` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ75V` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ75V` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `R_50` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `R_50` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ50V` | CALL | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |
| `1HZ50V` | PUT | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | Available (Hurdle 51.15%) | UNSUPPORTED (Max 10t) | SUPPORTED (2-10t) / UNSUPPORTED (20t) |

## 3. Capability Audit Observations

1. **20-Tick Duration Rejection**: Deriv contract rules limit tick-denominated contracts to a maximum
   of 10 ticks (`min_contract_duration: 1t`, `max_contract_duration: 10t`). Any 20-tick request is rejected
   with `ContractBuyValidationError: Number of ticks must be between 1 and 10`.
   This combination is classified as `UNSUPPORTED_CONTRACT_COMBINATION` and not a strategy failure.
2. **Supported Research Durations**: The broker supports 2t, 3t, 5t, and 10t Rise (`CALL`) and Fall (`PUT`)
   contracts across all 6 markets.
3. **Quote Economics Consistency**: All 6 markets quote a standard $2.00 stake with a $3.91 payout
   (net profit $1.91, return ~95.5%), establishing an authentic quote break-even hurdle of 51.15%.

---
*Report generated automatically by `market_discovery.py` — V1.8.0 Release Suite*