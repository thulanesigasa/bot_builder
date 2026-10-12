# Deriv Multi-Market Rise/Fall V1.8.2 — Data Authenticity Reassessment Report

![Data Integrity](https://img.shields.io/badge/Data%20Integrity-VERIFIED-brightgreen.svg)
![Source Authenticity](https://img.shields.io/badge/Source%20Authenticity-VERIFIED-blue.svg)
![Fail Closed Default](https://img.shields.io/badge/Fail%20Closed-ENFORCED-success.svg)

## 1. Overview of Data Provenance Enforcement
In V1.8.1, the provenance engine defaulted open if companion JSON parsing failed.
In V1.8.2, `DataProvenanceAuditor` enforces strict fail-closed verification:
- Default status is `UNVERIFIED_SOURCE`.
- Cryptographic SHA-256 checksums are verified on every file.
- Lineage is verified for duplicates, clock inversions, and interval gaps.
- Decouples file integrity (`FILE_INTEGRITY_VERIFIED`), source authenticity (`STATUS_SOURCE_AUTHENTICITY_VERIFIED`), and transformation lineage (`STATUS_LINEAGE_VERIFIED`).

## 2. Six-Market Provenance Audit Manifest
| Symbol | Path | File Size | SHA-256 Checksum | Source Classification | Lineage Status | Research Eligible |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R_100** | `data/R_100_ticks.csv` | 1.83 MB | `1f33f6...8116` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |
| **1HZ100V** | `data/1HZ100V_ticks.csv` | 4.09 MB | `168fb9...58ea` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |
| **R_75** | `data/R_75_master.csv` | 965 KB | `8273d2...d7a3` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |
| **1HZ75V** | `data/1HZ75V_ticks.csv` | 4.08 MB | `6e828e...98f4` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |
| **R_50** | `data/R_50_ticks.csv` | 1.93 MB | `dbdd9e...ba4a` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |
| **1HZ50V** | `data/1HZ50V_ticks.csv` | 4.02 MB | `8638b9...c558` | `GENUINE_BROKER_API` | `LINEAGE_VERIFIED` | YES |

## 3. Findings & Limitations
1. All 6 datasets are confirmed as authentic historical captures from Deriv API (`wss://ws.derivws.com/websockets/v3`, app_id 1089).
2. Clock inversions: 0 across all 6 datasets.
3. Timestamp duplicates: 0 across all 6 datasets.
4. However, historical CSV captures do NOT contain live binary WebSocket frames or simultaneous proposal quote streams.
   Therefore, pricing evidence must be supplied by explicit proposal quote captures.
