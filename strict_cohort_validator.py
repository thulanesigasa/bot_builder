"""Authoritative Strict Cohort Eligibility Validator (V1.8.3.2).

Enforces that an observation enters strict Cohort C ONLY when independently verified
source authenticity, prospective chronology, model provenance, broker quote integrity,
contract outcome reconstruction, and economic calculations all support its eligibility.

Core architectural principle:
No observation may certify its own scientific authority. Stored database labels
(such as evidence_cohort, prospective_status, model_type, model_is_verified)
are treated as untrusted annotations and must be independently re-evaluated from source records.

Permanent safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""

from dataclasses import dataclass, field, asdict
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from forward_shadow_engine import (
    FAMILY_RISE_FALL,
    FAMILY_ONLY_UPS_DOWNS,
    DIRECTION_CALL,
    DIRECTION_PUT,
    DIRECTION_RUNHIGH,
    DIRECTION_RUNLOW,
    RESEARCH_MARKETS,
    OUTCOME_RESOLVED,
    COHORT_A,
    COHORT_B,
    COHORT_C,
    COHORT_D,
    SOURCE_BROKER_CAPTURED,
    ContractOutcomeResolvers,
    LIVE_EXECUTION_DISABLED,
)
from model_registry import (
    AuthoritativeModelRegistry,
    MODEL_TYPE_UNVERIFIED,
    MODEL_TYPE_TRAINED_FROZEN,
    MODEL_TYPE_DETERMINISTIC_BASELINE,
    MODEL_TYPE_CONSTANT_BASELINE,
)

VALIDATOR_VERSION: str = "1.8.3.2"


@dataclass
class CohortEligibilityDecision:
    """Immutable, versioned eligibility verdict for an individual observation."""
    observation_id: str
    session_id: str
    symbol: str
    contract_family: str
    contract_type: str
    duration_ticks: int
    
    # Independent category verdicts (True if verified, False if failed)
    source_authenticity_verdict: bool
    source_reason: str
    
    prediction_chronology_verdict: bool
    chronology_reason: str
    
    model_provenance_verdict: bool
    model_reason: str
    
    quote_verification_verdict: bool
    quote_reason: str
    
    outcome_integrity_verdict: bool
    outcome_reason: str
    
    economic_integrity_verdict: bool
    economic_reason: str
    
    # Final derived evidence cohort
    final_evidence_cohort: str
    previous_stored_cohort: Optional[str] = None
    
    # Complete list of reasons if excluded from Cohort C
    rejection_reasons: List[str] = field(default_factory=list)
    validator_version: str = VALIDATOR_VERSION
    input_evidence_references: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_cohort_c_eligible(self) -> bool:
        return self.final_evidence_cohort == COHORT_C

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrictCohortAuthorityValidator:
    """Independent validator certifying scientific authority from verifiable ground truth."""

    def __init__(
        self,
        db_conn: Optional[sqlite3.Connection] = None,
        model_registry: Optional[AuthoritativeModelRegistry] = None,
        max_quote_age_sec: float = 5.0,
        clock_tolerance_sec: float = 0.001,  # 1ms clock tolerance
    ):
        self.conn = db_conn
        if self.conn:
            self.conn.row_factory = sqlite3.Row
        self.registry = model_registry or AuthoritativeModelRegistry()
        self.max_quote_age_sec = max_quote_age_sec
        self.clock_tolerance_sec = clock_tolerance_sec

    def validate_observation(
        self, obs: Dict[str, Any], conn: Optional[sqlite3.Connection] = None
    ) -> CohortEligibilityDecision:
        """Independently evaluates an observation record without trusting its self-assigned labels."""
        active_conn = conn or self.conn
        rejection_reasons: List[str] = []
        input_refs: Dict[str, Any] = {
            "observation_id": obs.get("observation_id"),
            "session_id": obs.get("session_id"),
            "proposal_id": obs.get("proposal_id"),
            "signal_epoch": obs.get("signal_epoch"),
            "model_version": obs.get("model_version"),
        }

        # ---------------------------------------------------------------------
        # 1. SOURCE AUTHENTICITY VALIDATION
        # ---------------------------------------------------------------------
        source_valid = True
        source_reason = "Verified authentic market and broker source."
        symbol = obs.get("symbol", "")
        if symbol not in RESEARCH_MARKETS:
            source_valid = False
            source_reason = f"Symbol '{symbol}' not in authorized research markets: {RESEARCH_MARKETS}."
            rejection_reasons.append(source_reason)

        # Missing source evidence is not a passing verification result.
        src_class = obs.get("source_classification")
        if src_class != SOURCE_BROKER_CAPTURED:
            source_valid = False
            source_reason = "Missing or unverified broker source classification."
            rejection_reasons.append(source_reason)

        if active_conn is None:
            source_valid = False
            source_reason = "Source verification requires a database connection."
            rejection_reasons.append(source_reason)
        else:
            cur = active_conn.cursor()
            table_check = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_ticks'"
            ).fetchone()
            if not table_check:
                source_valid = False
                source_reason = "Required broker_ticks source table is missing."
                rejection_reasons.append(source_reason)
            elif source_valid:
                cur.execute(
                    "SELECT COUNT(*) FROM broker_ticks WHERE symbol = ? AND epoch = ?",
                    (symbol, obs.get("signal_epoch")),
                )
                if cur.fetchone()[0] == 0:
                    source_valid = False
                    source_reason = (
                        f"Signal tick (epoch {obs.get('signal_epoch')}) "
                        "not found in persisted broker_ticks."
                    )
                    rejection_reasons.append(source_reason)

        # ---------------------------------------------------------------------
        # 2. PROSPECTIVE CHRONOLOGY VALIDATION
        # ---------------------------------------------------------------------
        chronology_valid = True
        chronology_reason = "Verified prospective pre-outcome commitment."
        commit_ts = obs.get("journal_commit_timestamp")
        first_future_ts = obs.get("first_future_tick_receipt_ts")
        first_future_epoch = obs.get("first_future_tick_epoch")
        signal_epoch = obs.get("signal_epoch", 0)
        expiry_epoch = obs.get("expiry_epoch")

        if commit_ts is None or commit_ts <= 0:
            chronology_valid = False
            chronology_reason = "Missing journal_commit_timestamp; durable pre-outcome commitment cannot be proven."
            rejection_reasons.append(chronology_reason)
        elif first_future_ts is None or first_future_ts <= 0:
            chronology_valid = False
            chronology_reason = "Missing first_future_tick_receipt_ts; future tick sequence not recorded."
            rejection_reasons.append(chronology_reason)
        else:
            lead_time_s = first_future_ts - commit_ts
            input_refs["lead_time_ms"] = round(lead_time_s * 1000.0, 2)
            if lead_time_s < -self.clock_tolerance_sec:
                chronology_valid = False
                chronology_reason = f"Chronology violation: First future tick arrived {-lead_time_s*1000:.2f}ms BEFORE journal commit completion."
                rejection_reasons.append(chronology_reason)

        if first_future_epoch is None or expiry_epoch is None:
            chronology_valid = False
            chronology_reason = "Missing future or expiry epoch; tick ordering cannot be proven."
            rejection_reasons.append(chronology_reason)
        elif first_future_epoch <= signal_epoch or expiry_epoch < first_future_epoch:
            chronology_valid = False
            chronology_reason = "Invalid chronological order of signal, entry and expiry epochs."
            rejection_reasons.append(chronology_reason)

        # ---------------------------------------------------------------------
        # 3. MODEL PROVENANCE VALIDATION
        # ---------------------------------------------------------------------
        model_valid = True
        model_reason = "Verified registered model provenance and true checksum."
        model_ver = obs.get("model_version")
        model_chk = obs.get("true_model_checksum") or obs.get("model_checksum") or ""

        is_verified, model_type, model_rec = self.registry.verify_model_provenance(
            model_id=model_ver or "", reported_checksum=model_chk
        )

        if not is_verified:
            model_valid = False
            model_reason = f"Model verification failed for '{model_ver}': {model_rec.description}"
            rejection_reasons.append(model_reason)
        elif model_type == MODEL_TYPE_UNVERIFIED:
            model_valid = False
            model_reason = f"Model '{model_ver}' classified as UNVERIFIED_MODEL_SOURCE."
            rejection_reasons.append(model_reason)

        input_refs["model_type"] = model_type
        input_refs["verified_model_checksum"] = model_chk

        # ---------------------------------------------------------------------
        # 4. QUOTE AUTHORITY VALIDATION
        # ---------------------------------------------------------------------
        quote_valid = True
        quote_reason = "Verified genuine broker proposal quote matching contract parameters."
        prop_id = obs.get("proposal_id")
        ask_price = obs.get("ask_price")
        total_payout = obs.get("total_payout")
        decision_ts = obs.get("decision_timestamp", 0.0)

        if not prop_id:
            quote_valid = False
            quote_reason = "No proposal_id associated with observation; unpriced record."
            rejection_reasons.append(quote_reason)
        elif ask_price is None or total_payout is None or ask_price <= 0 or total_payout <= 0:
            quote_valid = False
            quote_reason = f"Invalid quote pricing terms: ask={ask_price}, payout={total_payout}."
            rejection_reasons.append(quote_reason)
        elif active_conn:
            # Check physical broker_proposals table
            cur = active_conn.cursor()
            bp_check = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_proposals'"
            ).fetchone()
            if not bp_check:
                quote_valid = False
                quote_reason = "broker_proposals table does not exist in database."
                rejection_reasons.append(quote_reason)
            else:
                cur.execute("SELECT * FROM broker_proposals WHERE proposal_id = ?", (prop_id,))
                prop_row = cur.fetchone()
                if not prop_row:
                    quote_valid = False
                    quote_reason = f"Proposal ID '{prop_id}' not found in broker_proposals table."
                    rejection_reasons.append(quote_reason)
                else:
                    p_dict = dict(prop_row)
                    input_refs["proposal_response_ts"] = p_dict.get("response_timestamp")
                if prop_row:
                    p_dict = dict(prop_row)
                    if p_dict.get("session_id") != obs.get("session_id"):
                        quote_valid = False
                        quote_reason = "Quote session does not match observation session."
                        rejection_reasons.append(quote_reason)
                    if p_dict.get("contract_family") != obs.get("contract_family"):
                        quote_valid = False
                        quote_reason = "Cross-family proposal match is prohibited."
                        rejection_reasons.append(quote_reason)
                    # Symbol match
                    if p_dict.get("underlying_symbol") != symbol:
                        quote_valid = False
                        quote_reason = f"Cross-market quote mismatch: proposal symbol '{p_dict.get('underlying_symbol')}' != observation '{symbol}'."
                        rejection_reasons.append(quote_reason)
                    # Contract type match
                    if p_dict.get("contract_type") != obs.get("contract_type"):
                        quote_valid = False
                        quote_reason = f"Cross-contract quote mismatch: proposal type '{p_dict.get('contract_type')}' != observation '{obs.get('contract_type')}'."
                        rejection_reasons.append(quote_reason)
                    # Duration match
                    if p_dict.get("duration") != obs.get("duration_ticks"):
                        quote_valid = False
                        quote_reason = f"Cross-duration quote mismatch: proposal duration {p_dict.get('duration')} != observation {obs.get('duration_ticks')}."
                        rejection_reasons.append(quote_reason)
                    # Duration unit
                    if p_dict.get("duration_unit") != "t":
                        quote_valid = False
                        quote_reason = f"Invalid duration unit: proposal unit '{p_dict.get('duration_unit')}' != 't'."
                        rejection_reasons.append(quote_reason)
                    # Quote chronology
                    prop_resp_ts = p_dict.get("response_timestamp", 0.0)
                    if prop_resp_ts > decision_ts + 0.001:
                        quote_valid = False
                        quote_reason = f"Future quote chronology violation: response_timestamp ({prop_resp_ts}) > decision_timestamp ({decision_ts})."
                        rejection_reasons.append(quote_reason)
                    # Quote freshness
                    quote_age = decision_ts - prop_resp_ts
                    input_refs["quote_age_sec"] = round(quote_age, 4)
                    if quote_age > self.max_quote_age_sec:
                        quote_valid = False
                        quote_reason = f"Stale quote: age {quote_age:.2f}s exceeds maximum threshold {self.max_quote_age_sec}s."
                        rejection_reasons.append(quote_reason)
                    # Terms consistency
                    if abs(p_dict.get("ask_price", 0.0) - ask_price) > 1e-4:
                        quote_valid = False
                        quote_reason = f"Ask price discrepancy: proposal ask {p_dict.get('ask_price')} != observation ask {ask_price}."
                        rejection_reasons.append(quote_reason)
                    if abs(p_dict.get("total_payout", 0.0) - total_payout) > 1e-4:
                        quote_valid = False
                        quote_reason = f"Payout discrepancy: proposal payout {p_dict.get('total_payout')} != observation payout {total_payout}."
                        rejection_reasons.append(quote_reason)

        # ---------------------------------------------------------------------
        # 5. OUTCOME INTEGRITY VALIDATION
        # ---------------------------------------------------------------------
        outcome_valid = True
        outcome_reason = "Verified independent contract outcome reconstruction."
        outcome_status = obs.get("outcome_status")
        observed_outcome = obs.get("observed_outcome")
        entry_spot = obs.get("entry_spot")
        expiry_spot = obs.get("expiry_spot")
        spots_raw = obs.get("forward_spots_json", "[]")
        dur = obs.get("duration_ticks", 0)
        fam = obs.get("contract_family", "")
        ctype = obs.get("contract_type", "")

        if outcome_status != OUTCOME_RESOLVED:
            outcome_valid = False
            outcome_reason = f"Outcome status is '{outcome_status}', not '{OUTCOME_RESOLVED}'."
            rejection_reasons.append(outcome_reason)
        elif observed_outcome not in (0, 1):
            outcome_valid = False
            outcome_reason = f"Invalid observed outcome value: {observed_outcome}."
            rejection_reasons.append(outcome_reason)
        elif entry_spot is None or expiry_spot is None:
            outcome_valid = False
            outcome_reason = "Missing entry_spot or expiry_spot."
            rejection_reasons.append(outcome_reason)
        else:
            try:
                forward_spots = json.loads(spots_raw) if isinstance(spots_raw, str) else list(spots_raw)
            except Exception:
                forward_spots = []

            if len(forward_spots) < dur:
                outcome_valid = False
                outcome_reason = f"Incomplete forward spots sequence: {len(forward_spots)} < required {dur} ticks."
                rejection_reasons.append(outcome_reason)
            else:
                # Independently reconstruct outcome
                try:
                    if fam == FAMILY_RISE_FALL:
                        reconstructed_outcome, is_tie = ContractOutcomeResolvers.resolve_rise_fall(
                            entry_spot=entry_spot, expiry_spot=expiry_spot, direction=ctype
                        )
                    elif fam == FAMILY_ONLY_UPS_DOWNS:
                        reconstructed_outcome, break_step = ContractOutcomeResolvers.resolve_only_ups_downs(
                            entry_spot=entry_spot,
                            forward_spots=forward_spots[:dur],
                            direction=ctype,
                            duration=dur,
                        )
                    else:
                        reconstructed_outcome = -1
                        outcome_reason = f"Unknown contract family: '{fam}'."
                        outcome_valid = False

                    if reconstructed_outcome != observed_outcome:
                        outcome_valid = False
                        outcome_reason = (
                            f"Outcome reconstruction mismatch: independently computed {reconstructed_outcome} "
                            f"!= recorded observed_outcome {observed_outcome}."
                        )
                        rejection_reasons.append(outcome_reason)

                except Exception as ex:
                    outcome_valid = False
                    outcome_reason = f"Outcome resolver execution error: {str(ex)}"
                    rejection_reasons.append(outcome_reason)

        # ---------------------------------------------------------------------
        # 6. ECONOMIC INTEGRITY VALIDATION
        # ---------------------------------------------------------------------
        economic_valid = True
        economic_reason = "Verified per-observation economic arithmetic."
        hyp_return = obs.get("hypothetical_return")

        if quote_valid and outcome_valid:
            if hyp_return is None:
                economic_valid = False
                economic_reason = "Priced observation has NULL hypothetical_return."
                rejection_reasons.append(economic_reason)
            else:
                expected_return = round((observed_outcome * total_payout) - ask_price, 4)
                if abs(expected_return - hyp_return) > 1e-4:
                    economic_valid = False
                    economic_reason = f"Hypothetical return arithmetic mismatch: expected {expected_return}, recorded {hyp_return}."
                    rejection_reasons.append(economic_reason)

                # Check break even if present
                be_rate = obs.get("break_even_rate")
                if be_rate is not None:
                    expected_be = round(ask_price / total_payout, 4)
                    if abs(expected_be - be_rate) > 1e-3:
                        economic_valid = False
                        economic_reason = f"Break even arithmetic mismatch: expected {expected_be}, recorded {be_rate}."
                        rejection_reasons.append(economic_reason)
        else:
            if hyp_return is not None and not quote_valid:
                economic_valid = False
                economic_reason = "Unquoted observation cannot have non-null hypothetical return."
                rejection_reasons.append(economic_reason)

        # ---------------------------------------------------------------------
        # FINAL COHORT ASSIGNMENT
        # ---------------------------------------------------------------------
        # Cohort C: Requires ALL source, prospective, model, quote, outcome, and economic checks
        if (
            source_valid
            and chronology_valid
            and model_valid
            and quote_valid
            and outcome_valid
            and economic_valid
        ):
            final_cohort = COHORT_C
        elif quote_valid and (not chronology_valid or not model_valid):
            # Quote was valid and matched, but prospective chronology or model authority is unverified
            final_cohort = COHORT_B
        elif outcome_valid:
            # Resolved outcome with pure predictive quality
            final_cohort = COHORT_A
        else:
            final_cohort = "QUARANTINED_UNRESOLVED"

        return CohortEligibilityDecision(
            observation_id=obs.get("observation_id", ""),
            session_id=obs.get("session_id", ""),
            symbol=symbol,
            contract_family=fam,
            contract_type=ctype,
            duration_ticks=dur,
            source_authenticity_verdict=source_valid,
            source_reason=source_reason,
            prediction_chronology_verdict=chronology_valid,
            chronology_reason=chronology_reason,
            model_provenance_verdict=model_valid,
            model_reason=model_reason,
            quote_verification_verdict=quote_valid,
            quote_reason=quote_reason,
            outcome_integrity_verdict=outcome_valid,
            outcome_reason=outcome_reason,
            economic_integrity_verdict=economic_valid,
            economic_reason=economic_reason,
            final_evidence_cohort=final_cohort,
            previous_stored_cohort=obs.get("evidence_cohort"),
            rejection_reasons=rejection_reasons,
            validator_version=VALIDATOR_VERSION,
            input_evidence_references=input_refs,
        )
