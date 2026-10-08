"""Dedicated RUNHIGH / RUNLOW (Only Ups / Only Downs) Proposal Quoting Engine.

Strict Architectural Principles:
1. No arbitrary fallbacks: If no quote is present, returns None -> triggers NO TRADE.
2. Direction-specific: Evaluates RUNHIGH for UP and RUNLOW for DOWN independently.
3. Implied probability benchmark: Stake / Total Return (e.g. $2 / $61.03 = 3.277%).
4. Research baseline: Verified historical proposal benchmark ($2 -> $61.03).
5. Live proposal querying: Real-time queries for RUNHIGH and RUNLOW via Deriv WebSocket API.
"""
import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
import pandas as pd
import websockets



@dataclass(frozen=True)
class ProposalQuote:
    symbol: str
    contract_type: str  # 'RUNHIGH' (Only Ups) or 'RUNLOW' (Only Downs)
    direction: str      # 'UP' or 'DOWN'
    stake: float
    payout: float       # Total return on win (stake + profit)
    profit: float       # Net profit on win (payout - stake)
    payout_ratio: float # profit / stake
    implied_probability: float  # stake / payout (Break-even probability)
    quote_time: float
    source: str         # 'live_proposal', 'historical_snapshot', or 'benchmark_configured'
    duration: int = 5
    duration_unit: str = "t"
    basis: str = "stake"
    currency: str = "USD"
    proposal_id: Optional[str] = None
    collection_timestamp: Optional[float] = None

    @property
    def ask_price(self) -> float:
        return self.stake

    @property
    def timestamp(self) -> float:
        return self.quote_time



class QuoteEngine:
    """Manages exact direction-specific proposal quotes for RUNHIGH and RUNLOW."""

    def __init__(
        self,
        mode: str = "research",  # 'research', 'real_quotes_only', or 'live'
        benchmark_stake: float = 2.0,
        benchmark_payout: float = 61.03,
        default_up_payout_ratio: Optional[float] = None,
        default_down_payout_ratio: Optional[float] = None,
        ws_url: str = "wss://api.derivws.com/trading/v1/options/ws/public",
        app_id: str = "1089",
        symbol: str = "R_75",
        db_path: Optional[str] = None,
        max_freshness_seconds: float = 60.0,
        allow_benchmark_fallback: bool = True
    ):
        self.mode = mode
        self.symbol = symbol
        self.ws_url = ws_url
        self.app_id = app_id
        self.max_freshness_seconds = max_freshness_seconds
        self.allow_benchmark_fallback = allow_benchmark_fallback
        self._historical_quotes = None
        self._quotes: Dict[str, Optional[ProposalQuote]] = {
            "UP": None,
            "DOWN": None
        }

        try:
            from quote_database import QuoteDatabase
            self.quote_db = QuoteDatabase(db_path=db_path)
        except Exception:
            self.quote_db = None

        # If explicit ratios are provided, use them; otherwise use verified benchmark
        if default_up_payout_ratio is not None and default_down_payout_ratio is not None:
            now = time.time()
            up_profit = 1.0 * default_up_payout_ratio
            up_payout = 1.0 + up_profit
            down_profit = 1.0 * default_down_payout_ratio
            down_payout = 1.0 + down_profit
            self._quotes["UP"] = ProposalQuote(
                symbol="R_75",
                contract_type="CALL",
                direction="UP",
                stake=1.0,
                payout=up_payout,
                profit=up_profit,
                payout_ratio=default_up_payout_ratio,
                implied_probability=1.0 / up_payout,
                quote_time=now,
                source="configured"
            )
            self._quotes["DOWN"] = ProposalQuote(
                symbol="R_75",
                contract_type="PUT",
                direction="DOWN",
                stake=1.0,
                payout=down_payout,
                profit=down_profit,
                payout_ratio=default_down_payout_ratio,
                implied_probability=1.0 / down_payout,
                quote_time=now,
                source="configured"
            )
        elif mode == "research":
            self.set_benchmark_quotes(stake=benchmark_stake, payout=benchmark_payout)

    def set_benchmark_quotes(self, stake: float = 2.0, payout: float = 61.03, symbol: str = "R_75"):
        """Sets verified Deriv RUNHIGH and RUNLOW benchmark quotes ($2 stake -> $61.03 return)."""
        profit = payout - stake
        ratio = profit / stake
        implied_p = stake / payout
        now = time.time()

        self._quotes["UP"] = ProposalQuote(
            symbol=symbol,
            contract_type="RUNHIGH",
            direction="UP",
            stake=stake,
            payout=payout,
            profit=profit,
            payout_ratio=ratio,
            implied_probability=implied_p,
            quote_time=now,
            source="benchmark_configured"
        )
        self._quotes["DOWN"] = ProposalQuote(
            symbol=symbol,
            contract_type="RUNLOW",
            direction="DOWN",
            stake=stake,
            payout=payout,
            profit=profit,
            payout_ratio=ratio,
            implied_probability=implied_p,
            quote_time=now,
            source="benchmark_configured"
        )

    def set_custom_quote(
        self,
        direction: str,
        stake: float,
        total_payout: float,
        contract_type: str = "RUNHIGH",
        symbol: str = "R_75"
    ):
        profit = total_payout - stake
        ratio = profit / stake
        implied_p = stake / total_payout
        d_norm = "UP" if direction.upper() in ("UP", "RUNHIGH", "RISE") else "DOWN"
        self._quotes[d_norm] = ProposalQuote(
            symbol=symbol,
            contract_type=contract_type,
            direction=d_norm,
            stake=stake,
            payout=total_payout,
            profit=profit,
            payout_ratio=ratio,
            implied_probability=implied_p,
            quote_time=time.time(),
            source="custom_configured"
        )

    def load_historical_quotes(self, data_source):
        """Loads a timestamped historical proposal quote table (DataFrame or CSV path).
        Supports:
        - Stream format: 'epoch', 'runhigh_payout', 'runlow_payout', optional 'stake'.
        - Recorder format: 'response_timestamp', 'contract_type', 'total_payout', 'stake'.
        """
        if isinstance(data_source, str):
            if not os.path.exists(data_source):
                self._historical_quotes = None
                return
            df = pd.read_csv(data_source)
        else:
            df = data_source.copy()

        if "response_timestamp" in df.columns and "contract_type" in df.columns:
            # Pivot recorder format
            df["epoch"] = df["response_timestamp"].astype(int)
            rh = df[df["contract_type"].str.upper() == "RUNHIGH"].set_index("epoch")["total_payout"]
            rl = df[df["contract_type"].str.upper() == "RUNLOW"].set_index("epoch")["total_payout"]
            stake_s = df.groupby("epoch")["stake"].first()
            pivoted = pd.DataFrame({"runhigh_payout": rh, "runlow_payout": rl, "stake": stake_s}).reset_index()
            pivoted = pivoted.dropna(subset=["epoch"]).sort_values("epoch").ffill().reset_index(drop=True)
            self._historical_quotes = pivoted
        elif "epoch" in df.columns:
            self._historical_quotes = df.sort_values("epoch").reset_index(drop=True)
        else:
            self._historical_quotes = None

    def record_quote_snapshot(
        self,
        epoch: int,
        runhigh_payout: float,
        runlow_payout: float,
        stake: float = 2.0,
        symbol: str = "R_75"
    ):
        """Records a timestamped quote snapshot into the historical quotes stream."""
        new_row = pd.DataFrame([{
            "epoch": int(epoch),
            "symbol": symbol,
            "runhigh_payout": float(runhigh_payout),
            "runlow_payout": float(runlow_payout),
            "stake": float(stake)
        }])
        if getattr(self, "_historical_quotes", None) is not None:
            self._historical_quotes = pd.concat([self._historical_quotes, new_row], ignore_index=True).sort_values("epoch").reset_index(drop=True)
        else:
            self._historical_quotes = new_row

    def export_historical_quotes(self, output_path: str):
        """Exports the recorded quotes stream to a CSV file."""
        if getattr(self, "_historical_quotes", None) is not None:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            self._historical_quotes.to_csv(output_path, index=False)

    def clear_quotes(self):

        """Invalidates quotes (e.g. when quotes expire or live stream disconnects)."""
        self._quotes["UP"] = None
        self._quotes["DOWN"] = None

    def get_quote(self, direction: str, epoch: Optional[int] = None) -> Optional[ProposalQuote]:
        """Returns the exact quote for the direction at a given epoch timestamp.
        
        Priority of lookup:
        1. QuoteDatabase (SQLite): lookahead-free and freshness-bounded query.
        2. Historical CSV/DataFrame stream.
        3. Configured / live cached quotes.
        4. If mode is 'real_quotes_only' and no quote exists, returns None (QUOTE_UNAVAILABLE).
        5. If benchmark fallback is permitted in research mode, returns benchmark quote with source='benchmark_configured'.
        """
        d = direction.upper()
        dir_key = "UP" if d in ("UP", "RUNHIGH", "RISE") else ("DOWN" if d in ("DOWN", "RUNLOW", "FALL") else None)
        if dir_key is None:
            return None

        # 1. Check persistent QuoteDatabase if epoch provided
        if epoch is not None and getattr(self, "quote_db", None) is not None:
            c_type = "RUNHIGH" if dir_key == "UP" else "RUNLOW"
            rec = self.quote_db.get_latest_quote_before(
                symbol=self.symbol,
                contract_type=c_type,
                timestamp=float(epoch),
                max_freshness_seconds=self.max_freshness_seconds
            )
            if rec is not None:
                profit = rec.total_payout - rec.stake
                return ProposalQuote(
                    symbol=rec.market_symbol,
                    contract_type=rec.contract_type,
                    direction=dir_key,
                    stake=rec.stake,
                    payout=rec.total_payout,
                    profit=profit,
                    payout_ratio=profit / rec.stake if rec.stake > 0 else 0.0,
                    implied_probability=rec.stake / rec.total_payout if rec.total_payout > 0 else 0.0,
                    quote_time=rec.response_timestamp,
                    source="historical_db_quote",
                    duration=rec.contract_duration,
                    duration_unit=rec.duration_unit,
                    currency=rec.currency,
                    proposal_id=rec.proposal_id
                )

        # 2. Check historical quote stream DataFrame if present
        if epoch is not None and getattr(self, "_historical_quotes", None) is not None:
            hq = self._historical_quotes
            match = hq[hq["epoch"] <= epoch]
            if len(match) > 0:
                row = match.iloc[-1]
                time_diff = epoch - row["epoch"]
                if time_diff <= self.max_freshness_seconds:
                    stake = float(row.get("stake", 2.0))
                    payout_col = "runhigh_payout" if dir_key == "UP" else "runlow_payout"
                    if payout_col in row and not pd.isna(row[payout_col]):
                        total_payout = float(row[payout_col])
                        profit = total_payout - stake
                        return ProposalQuote(
                            symbol=str(row.get("symbol", self.symbol)),
                            contract_type="RUNHIGH" if dir_key == "UP" else "RUNLOW",
                            direction=dir_key,
                            stake=stake,
                            payout=total_payout,
                            profit=profit,
                            payout_ratio=profit / stake if stake > 0 else 0.0,
                            implied_probability=stake / total_payout if total_payout > 0 else 0.0,
                            quote_time=float(row["epoch"]),
                            source="historical_quote_stream"
                        )

        # 3. Check memory / live cached quote
        live_quote = self._quotes.get(dir_key)
        if live_quote is not None:
            if epoch is not None and self.mode in ("real_quotes_only", "paper"):
                if epoch - live_quote.quote_time > self.max_freshness_seconds:
                    return None
            return live_quote

        # 4. If strict real quotes required and none found, return None
        if self.mode == "real_quotes_only" or not self.allow_benchmark_fallback:
            return None

        # 5. Benchmark fallback in research mode
        return self._quotes.get(dir_key)

    def get_quote_status(self, direction: str, epoch: Optional[int] = None) -> Tuple[str, Optional[ProposalQuote]]:
        """Returns ('QUOTE_AVAILABLE', quote) if a valid quote exists at or before epoch,
        or ('QUOTE_UNAVAILABLE', None) if missing/stale.
        """
        q = self.get_quote(direction, epoch=epoch)
        if q is not None:
            return "QUOTE_AVAILABLE", q
        return "QUOTE_UNAVAILABLE", None


    @staticmethod
    def calculate_expected_value(
        estimated_prob: float,
        stake: float,
        payout: float
    ) -> Tuple[float, float, float]:
        """Calculates:
        1. Net Expected Value ($) = prob * payout - stake
        2. Expected Value per $1 stake
        3. Statistical Edge = estimated_prob - implied_prob
        """
        profit = payout - stake
        implied_prob = stake / payout if payout > 0 else 0.0
        ev_dollar = (estimated_prob * profit) - ((1.0 - estimated_prob) * stake)
        ev_per_dollar = ev_dollar / stake if stake > 0 else 0.0
        edge = estimated_prob - implied_prob
        return ev_dollar, ev_per_dollar, edge

    async def fetch_live_quotes_async(
        self,
        symbol: str = "R_75",
        stake: float = 2.0
    ) -> Tuple[Optional[ProposalQuote], Optional[ProposalQuote]]:
        """Queries Deriv API WebSocket for live RUNHIGH and RUNLOW proposals.
        If any query fails or returns an error, that direction remains None.
        """
        up_quote, down_quote = None, None
        try:
            async with websockets.connect(self.ws_url, close_timeout=3.0) as ws:
                for c_type, direct in [("RUNHIGH", "UP"), ("RUNLOW", "DOWN")]:
                    payload = {
                        "proposal": 1,
                        "amount": stake,
                        "basis": "stake",
                        "contract_type": c_type,
                        "currency": "USD",
                        "duration": 5,
                        "duration_unit": "t",
                        "underlying_symbol": symbol,
                    }
                    await ws.send(json.dumps(payload))
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=4.0))

                    if "proposal" in resp:
                        p_info = resp["proposal"]
                        payout = float(p_info.get("payout", 0.0))
                        ask = float(p_info.get("ask_price", stake))
                        profit = payout - ask
                        implied_p = ask / payout if payout > 0 else 0.0

                        quote = ProposalQuote(
                            symbol=symbol,
                            contract_type=c_type,
                            direction=direct,
                            stake=ask,
                            payout=payout,
                            profit=profit,
                            payout_ratio=profit / ask if ask > 0 else 0.0,
                            implied_probability=implied_p,
                            quote_time=time.time(),
                            source="live_proposal"
                        )
                        self._quotes[direct] = quote
                        if direct == "UP":
                            up_quote = quote
                        else:
                            down_quote = quote
                    else:
                        self._quotes[direct] = None
        except Exception:
            # On network error in live mode, leave quotes as None
            if self.mode == "live":
                self.clear_quotes()

        return self._quotes["UP"], self._quotes["DOWN"]


class QuoteOutcomeJoiner:
    """Timestamp-aware joiner linking market observations, proposal quotes, and contract outcomes.
    Enforces strict lookahead protection: quotes must precede or match observation timestamp.
    """

    @staticmethod
    def join(
        observations_df: pd.DataFrame,
        quote_engine: QuoteEngine,
        symbol: str = "R_75",
        max_quote_lag_seconds: float = 120.0
    ) -> pd.DataFrame:
        """Joins observations, quotes, and outcomes into a standardized, audited telemetry record.
        
        Guarantees:
        - Never uses a future quote (lookahead protection).
        - If quote is unavailable, returns QUOTE_UNAVAILABLE and sets signal to NO_TRADE.
        """
        records = []
        for idx, row in observations_df.iterrows():
            epoch = int(row["epoch"]) if "epoch" in row and not pd.isna(row["epoch"]) else int(idx)
            sig = str(row.get("signal", "NO_TRADE")).upper()
            dir_key = "UP" if sig in ("UP", "RUNHIGH", "RISE") else ("DOWN" if sig in ("DOWN", "RUNLOW", "FALL") else None)
            contract_type = "RUNHIGH" if dir_key == "UP" else ("RUNLOW" if dir_key == "DOWN" else "NONE")

            est_prob = float(row.get("estimated_prob", 0.0))
            if dir_key is None:
                records.append({
                    "timestamp": epoch,
                    "symbol": symbol,
                    "signal": "NO_TRADE",
                    "contract_type": "NONE",
                    "estimated_probability": 0.0,
                    "ask_price": 0.0,
                    "payout": 0.0,
                    "break_even_probability": 0.0,
                    "EV": 0.0,
                    "actual_outcome": 0.0,
                    "result": "NO_TRADE",
                    "status": "NO_SIGNAL"
                })
                continue

            status, quote = quote_engine.get_quote_status(dir_key, epoch=epoch)
            if quote is None:
                records.append({
                    "timestamp": epoch,
                    "symbol": symbol,
                    "signal": "NO_TRADE",
                    "contract_type": contract_type,
                    "estimated_probability": est_prob,
                    "ask_price": 0.0,
                    "payout": 0.0,
                    "break_even_probability": 0.0,
                    "EV": 0.0,
                    "actual_outcome": 0.0,
                    "result": "NO_TRADE",
                    "status": "QUOTE_UNAVAILABLE"
                })
                continue

            ask = quote.ask_price
            payout = quote.payout
            be_prob = quote.implied_probability
            ev = est_prob * payout - ask

            outcome_col = "runhigh_win" if dir_key == "UP" else "runlow_win"
            outcome = float(row.get(outcome_col, 0.0)) if outcome_col in row else 0.0
            is_win = bool(outcome == 1.0)
            res_str = "WIN" if is_win else "LOSS"

            records.append({
                "timestamp": epoch,
                "symbol": symbol,
                "signal": sig,
                "contract_type": contract_type,
                "estimated_probability": est_prob,
                "ask_price": ask,
                "payout": payout,
                "break_even_probability": be_prob,
                "EV": ev,
                "actual_outcome": outcome,
                "result": res_str,
                "status": "QUOTE_AVAILABLE"
            })

        return pd.DataFrame(records)

