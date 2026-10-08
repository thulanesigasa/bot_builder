"""Dedicated Live and Historical Deriv Proposal Quote Recorder for RUNHIGH / RUNLOW (V1.5.2).

Collects real-time proposal responses from Deriv WebSocket API without purchasing contracts.
Stores detailed quote records for both RUNHIGH (Only Ups) and RUNLOW (Only Downs) contracts,
capturing latency, exact payout amounts, ask prices, proposal IDs, session IDs, and collection status.

Usage:
    python quote_recorder.py [symbol] [--duration seconds] [--interval seconds] [--app-id id]
    Example: python quote_recorder.py R_75 --duration 60 --interval 2
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
import websockets

from health_monitor import GLOBAL_HEALTH_MONITOR


DEFAULT_APP_ID = "1089"
PRIMARY_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
FALLBACK_WS_URL = "wss://ws.derivws.com/websockets/v3"


@dataclass
class ProposalRecord:
    request_timestamp: float
    response_timestamp: float
    market_symbol: str
    contract_type: str         # 'RUNHIGH' or 'RUNLOW'
    contract_duration: int     # 5
    duration_unit: str         # 't'
    stake: float               # Ask price / stake
    total_payout: float        # Total return on win
    potential_net_profit: float
    currency: str
    proposal_id: str
    quote_source: str          # 'live_proposal' or 'historical_snapshot'
    quote_latency_ms: float
    collection_status: str     # 'QUOTE_AVAILABLE' or 'QUOTE_UNAVAILABLE'
    api_response_metadata: str = ""
    session_id: str = ""

    @property
    def ask_price(self) -> float:
        return self.stake

    @property
    def implied_probability(self) -> float:
        return self.stake / self.total_payout if self.total_payout > 0 else 0.0


class DerivQuoteRecorder:
    """Records real-time or replay RUNHIGH and RUNLOW proposals without purchasing contracts."""

    def __init__(
        self,
        symbol: str = "R_75",
        app_id: str = DEFAULT_APP_ID,
        ws_url: Optional[str] = None,
        default_stake: float = 2.0,
        db_path: Optional[str] = None
    ):
        self.symbol = symbol
        self.app_id = app_id
        self.ws_url = ws_url or PRIMARY_WS_URL
        self.default_stake = default_stake
        self.session_id = str(uuid.uuid4())[:8]
        self.records: List[ProposalRecord] = []
        try:
            from quote_database import QuoteDatabase
            self.quote_db: Optional[QuoteDatabase] = QuoteDatabase(db_path=db_path)
        except Exception:
            self.quote_db = None

    async def fetch_single_direction_quote(
        self,
        ws,
        contract_type: str,
        stake: float = 2.0,
        timeout: float = 4.0
    ) -> ProposalRecord:
        """Sends proposal request for RUNHIGH or RUNLOW and records precise latency and response."""
        req_time = time.time()
        payload = {
            "proposal": 1,
            "amount": stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": 5,
            "duration_unit": "t",
            "underlying_symbol": self.symbol,
        }

        try:
            await ws.send(json.dumps(payload))
            raw_resp = await asyncio.wait_for(ws.recv(), timeout=timeout)
            resp_time = time.time()
            latency_ms = (resp_time - req_time) * 1000.0

            data = json.loads(raw_resp)
            if "proposal" in data:
                p = data["proposal"]
                payout = float(p.get("payout", 0.0))
                ask = float(p.get("ask_price", stake))
                net_profit = payout - ask
                prop_id = str(p.get("id", "NONE"))
                meta = json.dumps({
                    "spot": p.get("spot"),
                    "spot_time": p.get("spot_time")
                })
                rec = ProposalRecord(
                    request_timestamp=req_time,
                    response_timestamp=resp_time,
                    market_symbol=self.symbol,
                    contract_type=contract_type,
                    contract_duration=5,
                    duration_unit="t",
                    stake=ask,
                    total_payout=payout,
                    potential_net_profit=net_profit,
                    currency="USD",
                    proposal_id=prop_id,
                    quote_source="live_proposal",
                    quote_latency_ms=round(latency_ms, 2),
                    collection_status="QUOTE_AVAILABLE",
                    api_response_metadata=meta,
                    session_id=self.session_id
                )
                GLOBAL_HEALTH_MONITOR.record_quote(success=True, latency_ms=latency_ms)
                return rec
            else:
                err_msg = data.get("error", {}).get("message", "Proposal error")
                rec = ProposalRecord(
                    request_timestamp=req_time,
                    response_timestamp=resp_time,
                    market_symbol=self.symbol,
                    contract_type=contract_type,
                    contract_duration=5,
                    duration_unit="t",
                    stake=stake,
                    total_payout=0.0,
                    potential_net_profit=0.0,
                    currency="USD",
                    proposal_id="NONE",
                    quote_source="live_proposal",
                    quote_latency_ms=round(latency_ms, 2),
                    collection_status="QUOTE_UNAVAILABLE",
                    api_response_metadata=json.dumps({"error": err_msg}),
                    session_id=self.session_id
                )
                GLOBAL_HEALTH_MONITOR.record_quote(success=False, latency_ms=latency_ms)
                return rec
        except Exception as e:
            resp_time = time.time()
            latency_ms = (resp_time - req_time) * 1000.0
            rec = ProposalRecord(
                request_timestamp=req_time,
                response_timestamp=resp_time,
                market_symbol=self.symbol,
                contract_type=contract_type,
                contract_duration=5,
                duration_unit="t",
                stake=stake,
                total_payout=0.0,
                potential_net_profit=0.0,
                currency="USD",
                proposal_id="NONE",
                quote_source="live_proposal",
                quote_latency_ms=round(latency_ms, 2),
                collection_status="QUOTE_UNAVAILABLE",
                api_response_metadata=json.dumps({"exception": str(e)}),
                session_id=self.session_id
            )
            GLOBAL_HEALTH_MONITOR.record_quote(success=False, latency_ms=latency_ms)
            return rec

    async def record_quotes_session(
        self,
        duration_seconds: float = 60.0,
        interval_seconds: float = 2.0,
        output_csv: Optional[str] = None
    ) -> List[ProposalRecord]:
        """Runs continuous polling session recording direction-specific quotes."""
        session_records = []
        end_time = time.time() + duration_seconds

        primary_url = f"{self.ws_url}?app_id={self.app_id}" if "?" not in self.ws_url else self.ws_url
        endpoints = [
            primary_url,
            f"{FALLBACK_WS_URL}?app_id={self.app_id}"
        ]

        active_ws = None
        for endpoint in endpoints:
            try:
                active_ws = await websockets.connect(endpoint, open_timeout=5.0, close_timeout=3.0)
                break
            except Exception:
                continue

        if not active_ws:
            print("Warning: Could not connect to Deriv WebSocket endpoint. Quotes unavailable.")
            return session_records

        try:
            while time.time() < end_time:
                # Record RUNHIGH
                rh_rec = await self.fetch_single_direction_quote(active_ws, "RUNHIGH", stake=self.default_stake)
                session_records.append(rh_rec)
                self.records.append(rh_rec)

                # Record RUNLOW
                rl_rec = await self.fetch_single_direction_quote(active_ws, "RUNLOW", stake=self.default_stake)
                session_records.append(rl_rec)
                self.records.append(rl_rec)

                if output_csv:
                    self.append_record_to_csv(output_csv, rh_rec)
                    self.append_record_to_csv(output_csv, rl_rec)

                if self.quote_db is not None:
                    try:
                        self.quote_db.store_quote(rh_rec)
                        self.quote_db.store_quote(rl_rec)
                    except Exception:
                        pass

                await asyncio.sleep(interval_seconds)
        finally:
            await active_ws.close()

        return session_records

    @staticmethod
    def append_record_to_csv(file_path: str, record: ProposalRecord):
        """Appends a quote record to CSV file, writing header if file does not exist."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        file_exists = os.path.exists(file_path)
        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(record).keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(asdict(record))


def main():
    parser = argparse.ArgumentParser(description="Deriv RUNHIGH/RUNLOW Live Quote Recorder")
    parser.add_argument("symbol", nargs="?", default="R_75", help="Underlying synthetic index symbol")
    parser.add_argument("--duration", type=float, default=60.0, help="Recording duration in seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--stake", type=float, default=2.0, help="Default stake for proposals")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Deriv App ID")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "data", f"{args.symbol}_quotes.csv")

    print(f"Starting quote recorder for {args.symbol} for {args.duration}s (interval={args.interval}s)...")
    print(f"Output file: {output_path}")

    recorder = DerivQuoteRecorder(symbol=args.symbol, app_id=args.app_id, default_stake=args.stake)
    records = asyncio.run(recorder.record_quotes_session(
        duration_seconds=args.duration,
        interval_seconds=args.interval,
        output_csv=output_path
    ))

    avail = sum(1 for r in records if r.collection_status == "QUOTE_AVAILABLE")
    print(f"\nRecording finished. Total quotes captured: {len(records)} ({avail} available).")


if __name__ == "__main__":
    main()
