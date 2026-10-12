# Deriv Multi-Market V1.8.3 — Live Connectivity & Capability Audit

![Connectivity Status](https://img.shields.io/badge/Deriv%20WebSocket-CONNECTION_SUCCESS-brightgreen.svg)
![Protocol](https://img.shields.io/badge/Protocol-TLS%201.3%20%2F%20WSS-blue.svg)
![App ID](https://img.shields.io/badge/App%20ID-1089-lightgrey.svg)
![Live Safety](https://img.shields.io/badge/Live%20Orders-DISABLED-red.svg)

## 1. Executive Summary
This audit verifies live public WebSocket connectivity to the Deriv API infrastructure.
The connection diagnostic confirmed:
- DNS Resolution: 23.33 ms (`104.18.12.218`, `104.18.13.218`)
- TCP Socket Connection: 9.36 ms (Port 443)
- Secure TLS 1.3 Handshake: 41.27 ms (`TLS_AES_256_GCM_SHA384`)
- WebSocket Handshake: `wss://api.derivws.com/trading/v1/options/ws/public?app_id=1089`
- Server Ping / Pong: 509.26 ms latency

## 2. Six-Market Contract Capability Matrix
| Symbol | Index Name | Base Tick Cadence | Rise/Fall Durations | Only Ups/Downs Durations | Availability Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`R_100`** | Volatility 100 Index | 2.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |
| **`1HZ100V`** | Volatility 100 (1s) Index | 1.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |
| **`R_75`** | Volatility 75 Index | 2.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |
| **`1HZ75V`** | Volatility 75 (1s) Index | 1.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |
| **`R_50`** | Volatility 50 Index | 2.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |
| **`1HZ50V`** | Volatility 50 (1s) Index | 1.0s | 2t, 3t, 5t, 10t | 2t, 5t | **SUPPORTED** |

## 3. Options API Schema Verification
Under Deriv API v1/options, proposal requests strictly require:
- Parameter `underlying_symbol` (not `symbol`).
- Field `contract_type`: `CALL`, `PUT`, `RUNHIGH`, `RUNLOW`.
- Field `duration_unit`: `"t"` for tick contracts.
- Payout terms are returned in real-time with genuine quote IDs.
