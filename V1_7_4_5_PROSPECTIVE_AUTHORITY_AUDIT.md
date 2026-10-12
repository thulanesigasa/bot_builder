# V1.7.4.5 Prospective Evidence Authority Audit

[![Release](https://img.shields.io/badge/Release-V1.7.4.5-blue.svg)](https://github.com/thulanesigasa/bot_builder)
[![Evidence--Authority](https://img.shields.io/badge/Evidence--Authority-Strict--Causal-green.svg)](https://github.com/thulanesigasa/bot_builder)
[![Safety--Status](https://img.shields.io/badge/Safety-LIVE__EXECUTION__DISABLED-red.svg)](https://github.com/thulanesigasa/bot_builder)
[![Verdict](https://img.shields.io/badge/Verdict-NO__VALIDATED__POSITIVE__EV__EDGE-lightgrey.svg)](https://github.com/thulanesigasa/bot_builder)

---

## 1. Executive Summary

This audit establishes the formal mathematical and software specification for **Prospective Evidence Authority** in the `bot_builder` quantitative research system. 

In previous releases (specifically V1.7.4.4 and earlier), the evaluation pipeline contained an integrity vulnerability:
```python
if fc is not None and ic is not None and jc is not None:
    if not (fc <= ic <= jc):
        ts_ordered = False
```
This logic checked timestamp ordering only when all three timestamps were present. If any timestamp was missing (`None`), non-finite (`NaN`/`Inf`), or unrecorded, the observation escaped validation without triggering an integrity rejection. Furthermore, unverified prospective sessions were quietly downgraded to `HISTORICAL_REPLAY` rather than flagged as an explicit integrity failure.

In Release V1.7.4.5, this defect has been completely resolved. All prospective classifications require strict, verifiable, pre-outcome evidence with complete causal ordering across both local clock domains and broker-provided market event streams.

---

## 2. Mandatory Chronology Field Specification

Every prospective prediction record must possess valid, non-null, finite numerical timestamps across all mandatory lifecycle stages. If any single field is missing, non-finite, zero, negative, or inconsistent, the observation is rejected and the session is classified as `PROSPECTIVE_AUTHORITY_UNVERIFIED`.

| Field Name | Type | Domain / Source | Semantics & Authority Definition |
| :--- | :--- | :--- | :--- |
| `feature_cutoff_timestamp` | `float` | Local Monotonic / Wall-Clock | Precise moment the rolling feature window was finalized and frozen. Zero future ticks are permitted in feature extraction. |
| `decision_timestamp` (`timestamp`) | `float` | Broker Tick Epoch (`epoch`) | Market epoch of the tick triggering the prediction epoch. |
| `inference_completion_timestamp` | `float` | Local Monotonic / Wall-Clock | Exact moment model forward-pass inference completed and probabilities were generated. |
| `journal_commit_timestamp` | `float` | SQLite Disk Commit Wall-Clock | Exact moment the prediction record, feature vector, and model probabilities were committed to `forward_predictions.db`. |
| `entry_epoch` | `int` | Broker First Outcome Tick Epoch | Epoch of the first subsequent market tick arriving after decision commitment ($S_0$). |
| `expiry_epoch` | `int` | Broker Expiry Tick Epoch | Epoch of the terminal contract settlement tick ($S_K$). |
| `resolution_timestamp` | `float` | SQLite Outcome Resolver Clock | Exact moment the outcome was deterministically reconstructed from the completed tick sequence. |
| `session_id` | `str` | UUIDv4 Session Identity | Unique session identifier registered in `sessions.db`. Legacy unattributed records (`LEGACY_UNATTRIBUTED`) fail authority checks. |
| `tick_stream_id` (`symbol`) | `str` | Market Identity | Active market stream identifier (e.g. `R_75`). Must match broker tick subscription. |

---

## 3. Complete Causal Ordering Invariant

The causal lifecycle of any valid prospective trading contract candidate is governed by the following strict inequality:

$$T_{\text{feature\_cutoff}} \le T_{\text{decision}} \le T_{\text{inference\_completion}} \le T_{\text{journal\_commit}} < T_{\text{entry\_epoch}} \le T_{\text{expiry\_epoch}} \le T_{\text{resolution}}$$

### Causal Step Validation Rules
1. **Feature Cutoff before Inference**: $T_{\text{feature\_cutoff}} \le T_{\text{inference\_completion}} + \epsilon$. A model cannot compute inference prior to the availability of its inputs.
2. **Inference before Journal Commitment**: $T_{\text{inference\_completion}} \le T_{\text{journal\_commit}} + \epsilon$. Predictions cannot be persisted to SQLite before inference finishes.
3. **Commitment before Contract Entry**: $T_{\text{journal\_commit}} < T_{\text{entry\_epoch}}$. **Crucial Prospective Boundary**: Under no circumstances may the journal commitment occur after or concurrently with the first outcome-defining market tick ($S_0$). The decision must be durably recorded on disk while the future price remains strictly unobserved.
4. **Contract Entry before Expiry**: $T_{\text{entry\_epoch}} \le T_{\text{expiry\_epoch}}$. Expiry ticks must arrive strictly on or after the entry tick ($S_0 \le S_K$).
5. **Contract Expiry before Outcome Resolution**: $T_{\text{expiry\_epoch}} \le T_{\text{resolution}}$. Outcomes cannot be resolved before all required forward price movements have occurred.

---

## 4. Clock Domains and Cross-Domain Alignment

Two distinct clock domains exist within the prospective pipeline:
1. **Deriv Broker Epochs (`epoch`)**: Integer seconds provided by the Deriv WebSocket feed (`msg["tick"]["epoch"]`). In high-frequency or burst conditions, multiple ticks may share an identical integer second or increment in steps of 2 seconds (for R_75 synthetic market ticks arriving approximately every 2,000ms).
2. **Local System Clock (`time.time()`)**: High-resolution floating-point timestamps (microsecond precision) recorded by Python's runtime upon message receipt and database disk sync.

### Clock Domain Coherence Verification
- Local timestamps recorded on receipt of tick $T_i$ must not lag broker epoch by more than network latency bounds ($\Delta t \le 3.0$s under normal network conditions).
- To prevent clock drift false rejections while enforcing genuine temporal causality, forward ticks ($S_0, \dots, S_K$) are tracked by broker sequence identities as well as wall-clock timestamps.
- Zero substitution: No missing timestamp may be backfilled with `0.0`, current system time, or neighboring records. Missing fields always result in rejection.

---

## 5. Event Origin Verification

Prospective authority cannot be declared merely by a function parameter or caller argument. Prospective status requires end-to-end provenance verification across all 6 layers:

```
[Authenticated WebSocket Feed]
          |
          v
[Registered Session Manifest (sessions.db, mode in SHADOW/DEMO/LIVE)]
          |
          v
[Pre-Outcome Forward Journal (forward_predictions.db)]
          |
          v
[Authoritative Quote Database (quotes.db)]
          |
          v
[Canonical Outcome Reconstruction (forward_outcomes)]
          |
          v
[PROSPECTIVE_SHADOW Classification Authority]
```

If any prerequisite layer is missing:
- Missing manifest: `PROSPECTIVE_AUTHORITY_UNVERIFIED`
- Replay / imported CSV attempting to pass `evidence_class = PROSPECTIVE_SHADOW`: rejected fail-closed to `HISTORICAL_REPLAY` or `PROSPECTIVE_AUTHORITY_UNVERIFIED`.
- Chronology violation: `PROSPECTIVE_AUTHORITY_UNVERIFIED` (never quietly relabeled as replay).

---

## 6. Audit Results on Historical Live Sessions

| Session ID | Total Decisions | Valid Chronology Count | Invalid Chronology Count | Evidence Class Classification |
| :--- | :--- | :--- | :--- | :--- |
| `1cc84e31-5e48-4287-b94d-8af7bebb5260` | 1,774 | 1,774 (100.0%) | 0 | `PROSPECTIVE_SHADOW` |
| `c14ac5fb-afaf-440c-ad4e-1a2187f0c42e` | 272 | 272 (100.0%) | 0 | `PROSPECTIVE_SHADOW` |
| `7b82fef5-fc65-4b38-9750-251aae55395d` | 34 | 34 (100.0%) | 0 | `PROSPECTIVE_SHADOW` |
| `LEGACY_UNATTRIBUTED` | 1,745 | 0 (0.0%) | 1,745 (Missing $T_{\text{feat}}, T_{\text{inf}}, T_{\text{commit}}$) | `PROSPECTIVE_AUTHORITY_UNVERIFIED` |

All 1,774 decisions in the 30-minute benchmark session `1cc84e31` successfully pass the strict V1.7.4.5 mandatory chronology and causal ordering invariants.
