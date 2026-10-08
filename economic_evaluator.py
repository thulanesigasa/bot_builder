"""Economic Edge & Genuine Proposal Pricing Evaluation Engine (V1.7 Part D & F).

Performs lookahead-free quote alignment, genuine proposal-based expected value calculation,
conservative uncertainty-bound assessment, hypothetical PnL attribution, and pricing sensitivity analysis.

Formulas:
  P_break_even     = Ask_price / Total_payout
  EV               = (P_win * Total_payout) - Ask_price
  Expected_ROI     = EV / Ask_price
  Conservative_EV  = (P_lower_bound * Total_payout) - Ask_price
"""
from typing import Dict, Any, List, Optional, Tuple
import math


class EconomicEvaluator:
    """Evaluates genuine economic viability and profitability hurdles."""

    def __init__(self, conservative_margin: float = 0.0):
        self.conservative_margin = conservative_margin

    @staticmethod
    def calculate_break_even_probability(stake: float, payout: float) -> float:
        if payout <= 0:
            return 0.0
        return stake / payout

    @staticmethod
    def calculate_expected_value(prob: float, stake: float, payout: float) -> float:
        return (prob * payout) - stake

    @staticmethod
    def calculate_conservative_ev(lower_bound_prob: Optional[float], stake: float, payout: float) -> Optional[float]:
        if lower_bound_prob is None or lower_bound_prob <= 0:
            return None
        return (lower_bound_prob * payout) - stake

    @staticmethod
    def find_lookahead_free_quote(
        quotes: List[Any],
        contract_type: str,
        decision_timestamp: float,
        max_age_seconds: float = 60.0
    ) -> Optional[Any]:
        """Finds the most recent quote for contract_type strictly before decision_timestamp."""
        target_type = contract_type.upper()
        if target_type in ("UP", "RISE"):
            target_type = "RUNHIGH"
        elif target_type in ("DOWN", "FALL"):
            target_type = "RUNLOW"

        valid = []
        for q in quotes:
            c_type = getattr(q, "contract_type", None) or (q.get("contract_type") if isinstance(q, dict) else None)
            if not c_type:
                continue
            c_type = str(c_type).upper()
            if c_type in ("UP", "RISE"):
                c_type = "RUNHIGH"
            elif c_type in ("DOWN", "FALL"):
                c_type = "RUNLOW"

            if c_type != target_type:
                continue

            resp_t = getattr(q, "response_timestamp", None) or (q.get("response_timestamp") if isinstance(q, dict) else None)
            if resp_t is None:
                continue
            resp_t = float(resp_t)

            # Strict lookahead protection: response must arrive <= decision_timestamp
            if resp_t <= decision_timestamp and (decision_timestamp - resp_t) <= max_age_seconds:
                valid.append((resp_t, q))

        if not valid:
            return None

        # Sort by response timestamp descending (most recent first)
        valid.sort(key=lambda x: x[0], reverse=True)
        return valid[0][1]

    def evaluate_quote_economics(
        self,
        predictions: List[Dict[str, Any]],
        direction: str = "RUNHIGH"
    ) -> Dict[str, Any]:
        """Calculates genuine quote-based break-even hurdles, expected values, and PnL."""

        eligible = [
            p for p in predictions
            if p.get("outcome_status") in ("RESOLVED", "OUTCOME_RECONSTRUCTED", "OUTCOME_VERIFIED")
        ]
        if not eligible:
            return {
                "direction": direction,
                "total_predictions": 0,
                "predictions_with_quotes": 0,
                "quote_coverage_pct": 0.0,
                "mean_ask": None,
                "mean_payout": None,
                "mean_break_even_pct": None,
                "mean_ordinary_ev": None,
                "mean_conservative_ev": None,
                "hypothetical_cumulative_pnl": 0.0,
                "max_drawdown": 0.0
            }

        dir_key = direction.upper()
        ask_key = "runhigh_ask" if dir_key == "RUNHIGH" else "runlow_ask"
        payout_key = "runhigh_payout" if dir_key == "RUNHIGH" else "runlow_payout"
        prob_key = "runhigh_pred_prob" if dir_key == "RUNHIGH" else "runlow_pred_prob"
        win_key = "runhigh_win" if dir_key == "RUNHIGH" else "runlow_win"
        features_key = "features_json"

        n_total = len(eligible)
        quotes_count = 0
        asks = []
        payouts = []
        bes = []
        ordinary_evs = []
        conservative_evs = []
        pnls = []

        cumulative_pnl = 0.0
        peak_pnl = 0.0
        max_dd = 0.0

        for p in eligible:
            ask = p.get(ask_key)
            payout = p.get(payout_key)
            prob = p.get(prob_key)
            win = p.get(win_key)

            if ask is not None and payout is not None and float(ask) > 0 and float(payout) > 0:
                ask_val = float(ask)
                payout_val = float(payout)
                quotes_count += 1
                asks.append(ask_val)
                payouts.append(payout_val)

                # Break-even hurdle
                be = ask_val / payout_val
                bes.append(be)

                # Ordinary EV
                if prob is not None:
                    p_val = float(prob)
                    ev = (p_val * payout_val) - ask_val
                    ordinary_evs.append(ev)

                # Conservative EV using lower probability bound
                lower_bound = p.get("runhigh_lower") if dir_key == "RUNHIGH" else p.get("runlow_lower")
                if lower_bound is None:
                    # Check if lower bound was recorded in prediction dictionary or parameters
                    lower_bound = p.get("cons_ev_runhigh" if dir_key == "RUNHIGH" else "cons_ev_runlow")
                
                # Rule 20: If uncertainty interval unavailable, conservative EV must remain unavailable
                if lower_bound is not None and isinstance(lower_bound, (int, float)) and lower_bound > 0:
                    c_ev = (float(lower_bound) * payout_val) - ask_val
                    conservative_evs.append(c_ev)

                # Hypothetical P/L attribution
                if win is not None:
                    is_win = (float(win) == 1.0)
                    trade_pnl = (payout_val - ask_val) if is_win else -ask_val
                    pnls.append(trade_pnl)
                    cumulative_pnl += trade_pnl
                    if cumulative_pnl > peak_pnl:
                        peak_pnl = cumulative_pnl
                    dd = peak_pnl - cumulative_pnl
                    if dd > max_dd:
                        max_dd = dd

        coverage_pct = round((quotes_count / n_total) * 100.0, 2) if n_total > 0 else 0.0

        return {
            "direction": dir_key,
            "total_predictions": n_total,
            "predictions_with_quotes": quotes_count,
            "quote_coverage_pct": coverage_pct,
            "mean_ask": round(sum(asks) / len(asks), 4) if asks else None,
            "mean_payout": round(sum(payouts) / len(payouts), 4) if payouts else None,
            "mean_break_even_pct": round((sum(bes) / len(bes)) * 100.0, 3) if bes else None,
            "mean_ordinary_ev": round(sum(ordinary_evs) / len(ordinary_evs), 4) if ordinary_evs else None,
            "mean_conservative_ev": round(sum(conservative_evs) / len(conservative_evs), 4) if conservative_evs else None,
            "hypothetical_cumulative_pnl": round(cumulative_pnl, 2),
            "max_drawdown": round(max_dd, 2)
        }

    # Alias for multi-session aggregator
    evaluate_quote_economic_performance = evaluate_quote_economics

    @classmethod
    def pricing_sensitivity_stress_analysis(
        cls,
        arg1: float,
        arg2: float,
        arg3: float,
        lower_bound_prob: Optional[float] = None
    ) -> Dict[str, Any]:
        """Evaluates how economic conclusions change across simulated adverse pricing conditions (Part F Section 16)."""
        # Support both (estimated_prob, base_stake, base_payout) and (base_stake, base_payout, estimated_prob)
        if arg1 < 1.0 and arg3 >= 1.0:
            estimated_prob = float(arg1)
            base_ask = float(arg2)
            base_payout = float(arg3)
        else:
            base_ask = float(arg1)
            base_payout = float(arg2)
            estimated_prob = float(arg3)

        scenarios = {
            "base_observed": {
                "ask": base_ask,
                "payout": base_payout,
                "ev": round((estimated_prob * base_payout) - base_ask, 4),
                "description": "Actual observed proposal quote terms"
            },
            "payout_haircut_5pct": {
                "ask": base_ask,
                "payout": base_payout * 0.95,
                "ev": round((estimated_prob * (base_payout * 0.95)) - base_ask, 4),
                "description": "5% reduction in provider total payout"
            },
            "payout_haircut_10pct": {
                "ask": base_ask,
                "payout": base_payout * 0.90,
                "ev": round((estimated_prob * (base_payout * 0.90)) - base_ask, 4),
                "description": "10% adverse pricing haircut in provider total payout"
            },
            "latency_premium_2pct": {
                "ask": base_ask * 1.02,
                "payout": base_payout,
                "ev": round((estimated_prob * base_payout) - (base_ask * 1.02), 4),
                "description": "2% slippage/penalty on ask price due to execution latency"
            },
            "combined_severe_stress": {
                "ask": base_ask * 1.03,
                "payout": base_payout * 0.92,
                "ev": round((estimated_prob * (base_payout * 0.92)) - (base_ask * 1.03), 4),
                "description": "3% ask premium and 8% payout reduction under volatile conditions"
            }
        }

        results: Dict[str, Any] = {}
        for sc_name, sc_data in scenarios.items():
            ask = sc_data["ask"]
            payout = sc_data["payout"]
            be = ask / payout
            ev = sc_data["ev"]
            cons_ev = ((lower_bound_prob * payout) - ask) if lower_bound_prob is not None else None
            roi = (ev / ask) if ask > 0 else 0.0

            results[sc_name] = {
                "ask": round(ask, 4),
                "payout": round(payout, 4),
                "break_even_pct": round(be * 100.0, 3),
                "ordinary_ev": round(ev, 4),
                "ev": round(ev, 4),
                "expected_roi_pct": round(roi * 100.0, 2),
                "conservative_ev": round(cons_ev, 4) if cons_ev is not None else None,
                "is_viable": (ev > 0.0 and (cons_ev is None or cons_ev > 0.0)),
                "description": sc_data["description"]
            }

        return {
            "estimated_prob": round(estimated_prob, 5),
            "lower_bound_prob": round(lower_bound_prob, 5) if lower_bound_prob is not None else None,
            "scenarios": results
        }

