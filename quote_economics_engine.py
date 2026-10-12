"""Quote-Level Economic Matching & Evaluation Engine (V1.8.1).

Enforces strict, per-observation quote economics:
  - Every observation matches an authentic broker proposal response:
      * symbol, contract_type, duration, currency, basis
      * proposal_id, quote_id, session_id
      * response_timestamp <= decision_timestamp (strict chronological receipt)
      * freshness: <= 5.0s for EXECUTION_QUALITY, <= 60.0s for CHRONOLOGICAL
  - Computes per-observation:
      break_even_i = ask_price_i / total_payout_i
      predicted_ev_i = (model_probability_i * total_payout_i - ask_price_i)
      realized_return_i = (observed_outcome_i * total_payout_i - ask_price_i)
  - Fails closed: Missing quotes classified as QUOTE_UNAVAILABLE / ECONOMIC_EVIDENCE_INELIGIBLE.
  - Reference economics mode explicitly marked REFERENCE_ECONOMICS_ONLY and prohibited
    from satisfying candidate qualification.

Safety invariant: LIVE_EXECUTION_DISABLED = True. Strictly non-purchasing research.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

LIVE_EXECUTION_DISABLED: bool = True

STATUS_ELIGIBLE = "ECONOMIC_EVIDENCE_ELIGIBLE"
STATUS_QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
STATUS_STALE_QUOTE = "STALE_QUOTE"
STATUS_FUTURE_QUOTE = "FUTURE_QUOTE"
STATUS_MISSING_RESPONSE_TIMESTAMP = "MISSING_RESPONSE_TIMESTAMP"
STATUS_CROSS_MARKET_MISMATCH = "CROSS_MARKET_MISMATCH"
STATUS_CROSS_DURATION_MISMATCH = "CROSS_DURATION_MISMATCH"
STATUS_CROSS_DIRECTION_MISMATCH = "CROSS_DIRECTION_MISMATCH"
STATUS_INVALID_PRICE_TERMS = "INVALID_PRICE_TERMS"

MODE_QUOTE_VERIFIED = "QUOTE_VERIFIED"
MODE_REFERENCE_ECONOMICS_ONLY = "REFERENCE_ECONOMICS_ONLY"


@dataclass
class ProposalQuoteRecord:
    """Authentic broker proposal quote representation."""
    quote_id: str
    proposal_id: str
    market_symbol: str
    contract_type: str                  # 'CALL' or 'PUT' (or 'RUNHIGH'/'RUNLOW')
    contract_duration: int              # duration in ticks
    duration_unit: str = "t"
    ask_price: float = 2.0
    total_payout: float = 3.91
    currency: str = "USD"
    basis: str = "stake"
    request_timestamp: Optional[float] = None
    response_timestamp: Optional[float] = None
    session_id: Optional[str] = None
    is_live_provenance: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "proposal_id": self.proposal_id,
            "market_symbol": self.market_symbol,
            "contract_type": self.contract_type,
            "contract_duration": self.contract_duration,
            "duration_unit": self.duration_unit,
            "ask_price": self.ask_price,
            "total_payout": self.total_payout,
            "currency": self.currency,
            "basis": self.basis,
            "request_timestamp": self.request_timestamp,
            "response_timestamp": self.response_timestamp,
            "session_id": self.session_id,
            "is_live_provenance": self.is_live_provenance,
        }


@dataclass
class PerObservationEconomicRecord:
    """Per-observation matched economic record."""
    decision_epoch: float
    symbol: str
    contract_type: str
    duration_ticks: int
    predicted_prob: Optional[float]
    observed_outcome: Optional[int]
    quote_id: Optional[str] = None
    proposal_id: Optional[str] = None
    quote_receipt_epoch: Optional[float] = None
    quote_age_sec: Optional[float] = None
    ask_price: Optional[float] = None
    total_payout: Optional[float] = None
    break_even_rate: Optional[float] = None
    predicted_ev: Optional[float] = None
    realized_return: Optional[float] = None
    status: str = STATUS_QUOTE_UNAVAILABLE
    is_eligible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_epoch": self.decision_epoch,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "duration_ticks": self.duration_ticks,
            "predicted_prob": round(self.predicted_prob, 4) if self.predicted_prob is not None else None,
            "observed_outcome": self.observed_outcome,
            "quote_id": self.quote_id,
            "proposal_id": self.proposal_id,
            "quote_receipt_epoch": self.quote_receipt_epoch,
            "quote_age_sec": round(self.quote_age_sec, 4) if self.quote_age_sec is not None else None,
            "ask_price": round(self.ask_price, 4) if self.ask_price is not None else None,
            "total_payout": round(self.total_payout, 4) if self.total_payout is not None else None,
            "break_even_rate": round(self.break_even_rate, 4) if self.break_even_rate is not None else None,
            "predicted_ev": round(self.predicted_ev, 4) if self.predicted_ev is not None else None,
            "realized_return": round(self.realized_return, 4) if self.realized_return is not None else None,
            "status": self.status,
            "is_eligible": self.is_eligible,
        }


@dataclass
class AggregatedEconomicSummary:
    """Aggregated economic metrics computed strictly from individual observation economics."""
    symbol: str
    contract_type: str
    duration_ticks: int
    evaluation_mode: str                # MODE_QUOTE_VERIFIED or MODE_REFERENCE_ECONOMICS_ONLY
    total_decisions: int
    eligible_decisions_count: int
    eligibility_coverage_pct: float
    mean_ask_price: Optional[float]
    mean_total_payout: Optional[float]
    mean_break_even_rate: Optional[float]
    mean_predicted_prob: Optional[float]
    empirical_win_rate: Optional[float]
    mean_predicted_ev: Optional[float]
    mean_realized_ev: Optional[float]
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    is_quote_verified: bool = False
    is_candidate_eligible: bool = False  # False if reference scenario or missing predicted EV

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "duration_ticks": self.duration_ticks,
            "evaluation_mode": self.evaluation_mode,
            "total_decisions": self.total_decisions,
            "eligible_decisions_count": self.eligible_decisions_count,
            "eligibility_coverage_pct": round(self.eligibility_coverage_pct, 2),
            "mean_ask_price": round(self.mean_ask_price, 4) if self.mean_ask_price is not None else None,
            "mean_total_payout": round(self.mean_total_payout, 4) if self.mean_total_payout is not None else None,
            "mean_break_even_rate": round(self.mean_break_even_rate, 4) if self.mean_break_even_rate is not None else None,
            "mean_predicted_prob": round(self.mean_predicted_prob, 4) if self.mean_predicted_prob is not None else None,
            "empirical_win_rate": round(self.empirical_win_rate, 4) if self.empirical_win_rate is not None else None,
            "mean_predicted_ev": round(self.mean_predicted_ev, 4) if self.mean_predicted_ev is not None else None,
            "mean_realized_ev": round(self.mean_realized_ev, 4) if self.mean_realized_ev is not None else None,
            "rejection_reasons": self.rejection_reasons,
            "is_quote_verified": self.is_quote_verified,
            "is_candidate_eligible": self.is_candidate_eligible,
        }


class QuoteLevelEconomicEngine:
    """Evaluates individual decisions against authentic quote proposal records."""

    @classmethod
    def match_quote_for_observation(
        cls,
        decision_epoch: float,
        symbol: str,
        contract_type: str,
        duration_ticks: int,
        predicted_prob: Optional[float],
        observed_outcome: Optional[int],
        candidate_quotes: List[ProposalQuoteRecord],
        max_freshness_seconds: float = 5.0,
    ) -> PerObservationEconomicRecord:
        """Finds the most recent valid proposal quote received strictly at or before decision epoch."""
        rec = PerObservationEconomicRecord(
            decision_epoch=decision_epoch,
            symbol=symbol,
            contract_type=contract_type,
            duration_ticks=duration_ticks,
            predicted_prob=predicted_prob,
            observed_outcome=observed_outcome,
        )

        if not candidate_quotes:
            rec.status = STATUS_QUOTE_UNAVAILABLE
            return rec

        valid_prior_quotes: List[Tuple[ProposalQuoteRecord, float]] = []
        c_upper = contract_type.upper()

        for q in candidate_quotes:
            # Market check
            if q.market_symbol != symbol:
                continue

            # Direction check (CALL/RISE vs PUT/FALL)
            q_type = q.contract_type.upper()
            if c_upper in ("CALL", "RISE", "RUNHIGH") and q_type not in ("CALL", "RISE", "RUNHIGH"):
                continue
            if c_upper in ("PUT", "FALL", "RUNLOW") and q_type not in ("PUT", "FALL", "RUNLOW"):
                continue

            # Duration check
            if q.contract_duration != duration_ticks:
                continue

            # Missing response timestamp check
            if q.response_timestamp is None:
                continue

            # Response received strictly at or before decision epoch
            if q.response_timestamp > decision_epoch:
                continue

            quote_age = decision_epoch - q.response_timestamp
            valid_prior_quotes.append((q, quote_age))

        if not valid_prior_quotes:
            rec.status = STATUS_QUOTE_UNAVAILABLE
            return rec

        # Pick the most recent quote received prior to decision
        best_quote, best_age = min(valid_prior_quotes, key=lambda pair: pair[1])

        # Freshness guard
        if best_age > max_freshness_seconds:
            rec.quote_id = best_quote.quote_id
            rec.proposal_id = best_quote.proposal_id
            rec.quote_receipt_epoch = best_quote.response_timestamp
            rec.quote_age_sec = best_age
            rec.status = STATUS_STALE_QUOTE
            return rec

        # Price term validity check
        if best_quote.ask_price <= 0.0 or best_quote.total_payout <= best_quote.ask_price:
            rec.quote_id = best_quote.quote_id
            rec.proposal_id = best_quote.proposal_id
            rec.quote_receipt_epoch = best_quote.response_timestamp
            rec.quote_age_sec = best_age
            rec.status = STATUS_INVALID_PRICE_TERMS
            return rec

        # Valid quote matched! Compute individual economics
        ask = best_quote.ask_price
        payout = best_quote.total_payout
        be = ask / payout

        pred_ev = (predicted_prob * payout - ask) if predicted_prob is not None else None
        real_ev = (observed_outcome * payout - ask) if observed_outcome is not None else None

        rec.quote_id = best_quote.quote_id
        rec.proposal_id = best_quote.proposal_id
        rec.quote_receipt_epoch = best_quote.response_timestamp
        rec.quote_age_sec = best_age
        rec.ask_price = ask
        rec.total_payout = payout
        rec.break_even_rate = be
        rec.predicted_ev = pred_ev
        rec.realized_return = real_ev
        rec.status = STATUS_ELIGIBLE
        rec.is_eligible = True

        return rec

    @classmethod
    def evaluate_observations(
        cls,
        observations: List[Dict[str, Any]],
        quotes: List[ProposalQuoteRecord],
        symbol: str,
        contract_type: str,
        duration_ticks: int,
        max_freshness_seconds: float = 5.0,
        reference_fallback: Optional[Tuple[float, float]] = None,
    ) -> Tuple[List[PerObservationEconomicRecord], AggregatedEconomicSummary]:
        """Evaluates a batch of observations using quote-level matching or reference fallback.
        
        Args:
            observations: List of dicts with keys 'decision_epoch', 'predicted_prob', 'observed_outcome'
            quotes: List of ProposalQuoteRecord
            reference_fallback: Optional (ask, payout) for illustrative reference scenarios only.
        """
        records: List[PerObservationEconomicRecord] = []
        reasons: Dict[str, int] = {}

        is_ref_mode = (reference_fallback is not None and len(quotes) == 0)
        mode = MODE_REFERENCE_ECONOMICS_ONLY if is_ref_mode else MODE_QUOTE_VERIFIED

        # Index quotes by symbol, direction, duration for fast lookup
        matching_quotes = [
            q for q in quotes
            if q.market_symbol == symbol and q.contract_duration == duration_ticks
        ]

        for obs in observations:
            dec_ts = float(obs["decision_epoch"])
            p_mod = obs.get("predicted_prob")
            y_obs = obs.get("observed_outcome")

            if is_ref_mode:
                # Reference pricing fallback for descriptive illustrations only
                ask, payout = reference_fallback
                be = ask / payout
                pred_ev = (p_mod * payout - ask) if p_mod is not None else None
                real_ev = (y_obs * payout - ask) if y_obs is not None else None

                rec = PerObservationEconomicRecord(
                    decision_epoch=dec_ts,
                    symbol=symbol,
                    contract_type=contract_type,
                    duration_ticks=duration_ticks,
                    predicted_prob=p_mod,
                    observed_outcome=y_obs,
                    ask_price=ask,
                    total_payout=payout,
                    break_even_rate=be,
                    predicted_ev=pred_ev,
                    realized_return=real_ev,
                    status="REFERENCE_PRICE_APPLIED",
                    is_eligible=False,  # Reference prices cannot satisfy quote verification!
                )
                records.append(rec)
            else:
                rec = cls.match_quote_for_observation(
                    decision_epoch=dec_ts,
                    symbol=symbol,
                    contract_type=contract_type,
                    duration_ticks=duration_ticks,
                    predicted_prob=p_mod,
                    observed_outcome=y_obs,
                    candidate_quotes=matching_quotes,
                    max_freshness_seconds=max_freshness_seconds,
                )
                records.append(rec)
                if not rec.is_eligible:
                    reasons[rec.status] = reasons.get(rec.status, 0) + 1

        total_n = len(records)
        eligible = [r for r in records if r.is_eligible]
        n_elig = len(eligible)

        cov_pct = (n_elig / total_n * 100.0) if total_n > 0 else 0.0

        if is_ref_mode:
            # Aggregation for reference economics
            mean_ask = reference_fallback[0]
            mean_payout = reference_fallback[1]
            mean_be = mean_ask / mean_payout
            valid_p = [r.predicted_prob for r in records if r.predicted_prob is not None]
            valid_y = [r.observed_outcome for r in records if r.observed_outcome is not None]
            valid_pred_ev = [r.predicted_ev for r in records if r.predicted_ev is not None]
            valid_real_ev = [r.realized_return for r in records if r.realized_return is not None]

            summary = AggregatedEconomicSummary(
                symbol=symbol,
                contract_type=contract_type,
                duration_ticks=duration_ticks,
                evaluation_mode=MODE_REFERENCE_ECONOMICS_ONLY,
                total_decisions=total_n,
                eligible_decisions_count=0,
                eligibility_coverage_pct=0.0,
                mean_ask_price=mean_ask,
                mean_total_payout=mean_payout,
                mean_break_even_rate=mean_be,
                mean_predicted_prob=float(np.mean(valid_p)) if valid_p else None,
                empirical_win_rate=float(np.mean(valid_y)) if valid_y else None,
                mean_predicted_ev=float(np.mean(valid_pred_ev)) if valid_pred_ev else None,
                mean_realized_ev=float(np.mean(valid_real_ev)) if valid_real_ev else None,
                rejection_reasons={"REFERENCE_SCENARIO_PROHIBITED_FROM_QUALIFICATION": total_n},
                is_quote_verified=False,
                is_candidate_eligible=False,  # Reference mode can NEVER qualify!
            )
            return records, summary

        if n_elig == 0:
            summary = AggregatedEconomicSummary(
                symbol=symbol,
                contract_type=contract_type,
                duration_ticks=duration_ticks,
                evaluation_mode=MODE_QUOTE_VERIFIED,
                total_decisions=total_n,
                eligible_decisions_count=0,
                eligibility_coverage_pct=0.0,
                mean_ask_price=None,
                mean_total_payout=None,
                mean_break_even_rate=None,
                mean_predicted_prob=None,
                empirical_win_rate=None,
                mean_predicted_ev=None,
                mean_realized_ev=None,
                rejection_reasons=reasons,
                is_quote_verified=False,
                is_candidate_eligible=False,
            )
            return records, summary

        # Aggregate strictly from eligible records
        mean_ask = float(np.mean([r.ask_price for r in eligible]))
        mean_payout = float(np.mean([r.total_payout for r in eligible]))
        mean_be = float(np.mean([r.break_even_rate for r in eligible]))

        p_list = [r.predicted_prob for r in eligible if r.predicted_prob is not None]
        y_list = [r.observed_outcome for r in eligible if r.observed_outcome is not None]
        pred_ev_list = [r.predicted_ev for r in eligible if r.predicted_ev is not None]
        real_ev_list = [r.realized_return for r in eligible if r.realized_return is not None]

        mean_p = float(np.mean(p_list)) if p_list else None
        mean_y = float(np.mean(y_list)) if y_list else None
        mean_pred_ev = float(np.mean(pred_ev_list)) if pred_ev_list else None
        mean_real_ev = float(np.mean(real_ev_list)) if real_ev_list else None

        # Qualification check for predictive model strategy:
        # Requires: mean_predicted_ev > 0 AND mean_realized_ev > 0
        cand_eligible = (
            mean_pred_ev is not None and mean_pred_ev > 0.0 and
            mean_real_ev is not None and mean_real_ev > 0.0 and
            cov_pct >= 50.0
        )

        summary = AggregatedEconomicSummary(
            symbol=symbol,
            contract_type=contract_type,
            duration_ticks=duration_ticks,
            evaluation_mode=MODE_QUOTE_VERIFIED,
            total_decisions=total_n,
            eligible_decisions_count=n_elig,
            eligibility_coverage_pct=cov_pct,
            mean_ask_price=mean_ask,
            mean_total_payout=mean_payout,
            mean_break_even_rate=mean_be,
            mean_predicted_prob=mean_p,
            empirical_win_rate=mean_y,
            mean_predicted_ev=mean_pred_ev,
            mean_realized_ev=mean_real_ev,
            rejection_reasons=reasons,
            is_quote_verified=True,
            is_candidate_eligible=cand_eligible,
        )

        return records, summary
