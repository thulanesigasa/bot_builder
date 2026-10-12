# V1.8.3.1 Model Provenance & Authenticity Audit

![Model Registry](https://img.shields.io/badge/Model%20Registry-AUTHENTIC-brightgreen.svg)
![Placeholder Checksums](https://img.shields.io/badge/Placeholders-ELIMINATED-red.svg)
![Classification](https://img.shields.io/badge/Classification-FAIL%20CLOSED-blue.svg)
![Safety](https://img.shields.io/badge/Safety-NO%20TRADE-orange.svg)

## 1. Executive Summary & Defect Elimination
In V1.8.3, placeholder checksums such as:
- `sha256_mock_a8f9c1e2`
- `sha256_mock_e4d3c2b1`
- `sha256_v183_frozen_model`
were published in evidence files. Furthermore, probabilities were derived from a causal heuristic while the release labeled it `V1.8.3_CAUSAL_LOGISTIC`.

V1.8.3.1 completely eliminates all placeholder checksums and establishes `AuthoritativeModelRegistry`.

## 2. Model Classification Hierarchy
Every prediction source is strictly categorized into one of four mutually exclusive types:
1. `TRAINED_FROZEN_MODEL`: Serialized model file with verified 64-character SHA-256 digest on disk.
2. `DETERMINISTIC_CAUSAL_BASELINE`: Causal decision rule or heuristic with canonical JSON spec digest.
3. `CONSTANT_PROBABILITY_BASELINE`: Fixed reference probabilities (e.g. 50/50 base rates).
4. `UNVERIFIED_MODEL_SOURCE`: Fail-closed classification for missing, modified, or placeholder checksums.

## 3. Registered Model Inventory

### 1. `BASELINE_CAUSAL_MOMENTUM_V1`
- **Model Type**: `DETERMINISTIC_CAUSAL_BASELINE`
- **Model Family**: `CAUSAL_STREAK_MOMENTUM_BASELINE`
- **True SHA-256**: `2fbd3f7e368c3c58c22c7475174f24b70276a927a8b7afd0a74481c67bce8cd6`
- **Description**: Deterministic causal momentum heuristic tilting around theoretical base rates.
- **Feature Schema**: `1.8.3_CAUSAL_STREAK`

### 2. `M_R_75_2TICK_20261011_120000`
- **Model Type**: `TRAINED_FROZEN_MODEL`
- **Model Family**: `EMPIRICAL_STATE_CONDITIONAL`
- **Artifact Path**: `models\M_R_75_2TICK_20261011_120000.json`
- **True File SHA-256**: `943def871f3a4e6be0380701042ae2341c796cfc39ce151ce20bcb222bbc331d`
- **Training Dataset**: `R_75_master.csv`

### 3. `M_R_75_5TICK_20261008_132512`
- **Model Type**: `TRAINED_FROZEN_MODEL`
- **Model Family**: `EMPIRICAL_STATE_CONDITIONAL`
- **Artifact Path**: `models\M_R_75_5TICK_20261008_132512.json`
- **True File SHA-256**: `e038fb5efa788d46006ef58f7515f166e470f38e9f50b3b82d3fe6a284f4221a`
- **Training Dataset**: `R_75_master.csv`

## 4. Rejection Policy
Any model ID reporting a placeholder digest (e.g. `sha256_mock_*`) or failing cryptographic verification is immediately classified as `UNVERIFIED_MODEL_SOURCE` and quarantined.
