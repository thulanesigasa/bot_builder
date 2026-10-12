# V1.8.1 Data Provenance & Stream Integrity Audit Report

![Provenance](https://img.shields.io/badge/Data_Provenance-GENUINE_BROKER_API-brightgreen.svg)
![Integrity](https://img.shields.io/badge/Checksums-SHA--256_Verified-blue.svg)
![Coverage](https://img.shields.io/badge/Total_Ticks-1%2C043%2C184-brightgreen.svg)
![Safety](https://img.shields.io/badge/Live_Execution-DISABLED-red.svg)

---

## 1. Executive Summary & Source Authentication Mandate

In accordance with Section 7.1 and Section 7.3 of the V1.8.1 specification, this audit establishes the complete data provenance, cryptographic identity, and stream continuity across all six research markets:
- `R_100` — Volatility 100 Index
- `1HZ100V` — Volatility 100 (1s) Index
- `R_75` — Volatility 75 Index
- `1HZ75V` — Volatility 75 (1s) Index
- `R_50` — Volatility 50 Index
- `1HZ50V` — Volatility 50 (1s) Index

### Source Invariant
Under no circumstances may simulated test fixtures or synthetic random walks acquire live-broker provenance status. Every modeled historical sequence is verified against persisted Deriv WebSocket API raw payloads.

---

## 2. Dataset Cryptographic Identity & Provenance Registry

| Symbol | File Path | SHA-256 Checksum (Hex) | Tick Count | Time Span | Sampling Mean dt | Duplicates | Inversions | Gaps (>3x dt) | Verified Source Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`R_100`** | `data/R_100_ticks.csv` | `1183d4912f403b23d825953103ad96b663812339729b61b1a2f2740d53fce0e7` | 200,000 | 105.67h | 1.9020s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |
| **`1HZ100V`** | `data/1HZ100V_ticks.csv` | `016d17f6c6fafd28f2cfdf025a1f649297800721ebaa921132ea3dfb93708918` | 200,000 | 57.18h | 1.0293s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |
| **`R_75`** | `data/R_75_master.csv` | `8273d215bf93f46dafe85558d601b0728c114df344f6b2169b1836db5153282b` | 43,184 | 24.00h | 2.0001s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |
| **`1HZ75V`** | `data/1HZ75V_ticks.csv` | `5457813174cef8b4618e388ffc96ca2604924a2efbf168b4efc91c342fef8725` | 200,000 | 57.23h | 1.0302s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |
| **`R_50`** | `data/R_50_ticks.csv` | `c20ae183b04d549b062ec7e24a46ee2366b17c9fb377013baeb2801e0a29339e` | 200,000 | 105.63h | 1.9013s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |
| **`1HZ50V`** | `data/1HZ50V_ticks.csv` | `277f6c2cc0a9f79b79d89fb8a50584601ef6f864769dde689da7bf564fa16707` | 200,000 | 57.26h | 1.0306s | 0 | 0 | 0 | `GENUINE_BROKER_API` (`ws.derivws.com/v3`) |

---

## 3. Investigation of Artificial Directional Bias (Resolving Section 7.2)

In Release V1.8.0, apparent downward imbalances were observed on certain chronological holdout subsets:
- `R_100` at 10 ticks: observed holdout PUT win rate ~53.84%
- `1HZ50V` at 10 ticks: observed holdout PUT win rate ~54.20%
- `1HZ50V` at 5 ticks: observed holdout PUT win rate ~53.11%

### 3.1 Empirical Root Cause Analysis
To determine whether these downward biases represented true structural asymmetries or chronological sample-selection artifacts, the full 200,000-tick sequences were partitioned into four non-overlapping blocks of 50,000 ticks:

| Dataset Block | `R_100` 10-Tick CALL | `R_100` 10-Tick PUT | `1HZ50V` 10-Tick CALL | `1HZ50V` 10-Tick PUT |
| :--- | :--- | :--- | :--- | :--- |
| **Block 1 (Ticks 0k–50k)** | 49.64% | 50.36% | 49.98% | 50.02% |
| **Block 2 (Ticks 50k–100k)** | 50.67% | 49.33% | 50.12% | 49.86% |
| **Block 3 (Ticks 100k–150k)** | 49.40% | 50.59% | 50.13% | 49.86% |
| **Block 4 (Ticks 150k–200k)** | 50.57% | 49.43% | 49.46% | 50.52% |
| **FULL 200,000 TICKS** | **50.07%** | **49.93%** | **49.91%** | **50.07%** |

### 3.2 Audit Verdict
1. **Unconditional Symmetry Confirmed**: Across the entire 200,000-tick historical record, the unconditional directional probability is within 0.09% of exactly 50.00%.
2. **Short-Window Drift Artifact**: The apparent 53.8%–54.2% PUT win rates were strictly artifacts of evaluating a localized 5,000-tick holdout window (~1.5 to 3.0 hours) that coincided with a transient negative random walk excursion.
3. **Absence of Persistent Bias**: No persistent structural downward bias exists in either market. Evaluating strategies on short chronological holdouts without adjusting for local regime drift induces severe retrospective selection bias.

---

*Report certified by `data_provenance.py` — Release V1.8.1 Scientific Integrity Suite*
