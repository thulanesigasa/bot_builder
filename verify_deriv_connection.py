"""Live Deriv API Connection and RUNHIGH/RUNLOW Proposal Diagnostic Tool (V1.5.3).

Executes live WebSocket API verification WITHOUT purchasing contracts:
1. Low-level Network Pre-flight:
   - DNS Resolution (IPv4/IPv6, latency)
   - TCP Socket Handshake (Port 443)
   - TLS Handshake & Cipher Suite Negotiation (Strict Secure Validation)
2. WebSocket Protocol Level:
   - WebSocket Handshake with Bounded Retries
   - Explicit HTTP status classification (Distinguishes HTTP 520 Cloudflare edge errors)
   - Ping / Pong latency measurement
3. Market Data & Quoting Level:
   - Symbol availability audit (active_symbols)
   - Real-time tick subscription and validation
   - RUNHIGH and RUNLOW proposal queries
   - Financial quote sanity validation (ask > 0, payout > 0, implied probability)
   - Real quote persistence to SQLite quote database (data/quotes.db)
   - Graceful disconnection without dangling subscriptions

Statuses:
- CONNECTION_SUCCESS
- DNS_RESOLUTION_FAILED
- TCP_CONNECTION_FAILED
- TLS_HANDSHAKE_FAILED
- HTTP_EDGE_ERROR_520
- CONNECTION_FAILED
- AUTHENTICATION_FAILED
- SYMBOL_UNSUPPORTED
- CONTRACT_UNSUPPORTED
- TICK_STREAM_FAILED
- PROPOSAL_FAILED
- QUOTE_VALIDATION_FAILED
"""
import argparse
import asyncio
import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse
import websockets

from config import DEFAULT_CONFIG
from quote_database import QuoteDatabase
from quote_recorder import ProposalRecord


DEFAULT_DIAGNOSTIC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "reports",
    "deriv_api_diagnostic.json"
)


class DerivConnectionVerifier:
    """Performs end-to-end diagnostic checks against the Deriv WebSocket API."""

    def __init__(
        self,
        symbol: str = "R_75",
        app_id: Optional[str] = None,
        api_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout_seconds: float = 12.0
    ):
        self.symbol = symbol
        self.app_id = app_id or DEFAULT_CONFIG.app_id or "1089"
        self.api_token = api_token or os.environ.get("DERIV_API_TOKEN") or os.environ.get("DERIV_TOKEN")
        self.timeout = timeout_seconds

        candidate_endpoints = [
            f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}",
            f"wss://ws.binaryws.com/websockets/v3?app_id={self.app_id}",
            f"wss://frontend.binaryws.com/websockets/v3?app_id={self.app_id}"
        ]
        if endpoint_url:
            self.endpoints = [f"{endpoint_url}?app_id={self.app_id}"]
        else:
            self.endpoints = candidate_endpoints

        self.ws_url = self.endpoints[0]
        self.quote_db = QuoteDatabase()

    def run_preflight_network_check(self, target_url: str) -> Dict[str, Any]:
        """Runs DNS, TCP, and TLS socket checks before initiating WebSocket handshake."""
        parsed = urlparse(target_url)
        hostname = parsed.hostname or "ws.derivws.com"
        port = parsed.port or 443
        check_res: Dict[str, Any] = {
            "hostname": hostname,
            "port": port,
            "dns_resolved": False,
            "resolved_ips": [],
            "dns_latency_ms": 0.0,
            "tcp_connected": False,
            "tcp_latency_ms": 0.0,
            "tls_handshake": False,
            "tls_latency_ms": 0.0,
            "tls_version": None,
            "cipher": None,
            "preflight_status": "PENDING",
            "preflight_error": None
        }

        # 1. DNS Resolution
        t0 = time.time()
        try:
            addr_info = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
            ips = sorted(list({entry[4][0] for entry in addr_info}))
            check_res["dns_resolved"] = True
            check_res["resolved_ips"] = ips
            check_res["dns_latency_ms"] = round((time.time() - t0) * 1000, 2)
        except Exception as e:
            check_res["preflight_status"] = "DNS_RESOLUTION_FAILED"
            check_res["preflight_error"] = str(e)
            return check_res

        # 2. Raw TCP Connect
        target_ip = ips[0]
        t_tcp0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(4.0, self.timeout / 2.0))
        try:
            sock.connect((target_ip, port))
            check_res["tcp_connected"] = True
            check_res["tcp_latency_ms"] = round((time.time() - t_tcp0) * 1000, 2)
        except Exception as e:
            check_res["preflight_status"] = "TCP_CONNECTION_FAILED"
            check_res["preflight_error"] = f"TCP Connect to {target_ip}:{port} failed: {e}"
            sock.close()
            return check_res

        # 3. Secure TLS Handshake
        t_tls0 = time.time()
        context = ssl.create_default_context()
        try:
            tls_sock = context.wrap_socket(sock, server_hostname=hostname)
            check_res["tls_handshake"] = True
            check_res["tls_latency_ms"] = round((time.time() - t_tls0) * 1000, 2)
            check_res["tls_version"] = tls_sock.version()
            check_res["cipher"] = tls_sock.cipher()[0] if tls_sock.cipher() else None
            check_res["preflight_status"] = "PREFLIGHT_SUCCESS"
            tls_sock.close()
        except Exception as e:
            check_res["preflight_status"] = "TLS_HANDSHAKE_FAILED"
            check_res["preflight_error"] = f"TLS handshake failed: {e}"
            sock.close()
            return check_res

        return check_res

    async def run_diagnostics(self) -> Dict[str, Any]:
        """Runs the complete diagnostic suite and returns structured results."""
        results: Dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target_symbol": self.symbol,
            "app_id": self.app_id,
            "endpoint_url": self.ws_url,
            "authenticated_session": False,
            "preflight": {},
            "steps": {},
            "quotes_persisted": 0,
            "status": "CONNECTION_FAILED",
            "error_details": None
        }

        # Step 0: Pre-flight network check
        preflight = self.run_preflight_network_check(self.ws_url)
        results["preflight"] = preflight
        if preflight["preflight_status"] != "PREFLIGHT_SUCCESS":
            results["status"] = preflight["preflight_status"]
            results["error_details"] = preflight["preflight_error"]
            return results

        ws = None
        try:
            # Step 1: Connect WebSocket with endpoint fallback
            connected = False
            last_err = None
            active_endpoint = self.endpoints[0]
            per_endpoint_timeout = max(3.0, self.timeout / len(self.endpoints))

            for ep in self.endpoints:
                t0 = time.time()
                try:
                    ws = await asyncio.wait_for(
                        websockets.connect(
                            ep,
                            ping_timeout=5,
                            close_timeout=3
                        ),
                        timeout=per_endpoint_timeout
                    )
                    connected = True
                    active_endpoint = ep
                    results["endpoint_url"] = ep
                    break
                except Exception as e:
                    last_err = e

            if not connected:
                err_str = f"{type(last_err).__name__}: {str(last_err)}" if str(last_err) else repr(last_err)
                results["steps"]["websocket_connection"] = {"success": False, "error": err_str}
                if "520" in err_str:
                    results["status"] = "HTTP_EDGE_ERROR_520"
                    results["error_details"] = (
                        "Deriv Cloudflare edge server returned HTTP 520 (Origin Web Server Returned an Unknown Error). "
                        "The network gateway or origin server rejected the WebSocket upgrade handshake."
                    )
                else:
                    results["status"] = "CONNECTION_FAILED"
                    results["error_details"] = f"Failed to connect to endpoints ({', '.join(self.endpoints)}): {err_str}"
                return results

            conn_latency_ms = round((time.time() - t0) * 1000, 2)
            results["steps"]["websocket_connection"] = {
                "success": True,
                "endpoint": active_endpoint,
                "latency_ms": conn_latency_ms
            }

            # Step 2: Ping / Pong Test
            t_ping0 = time.time()
            await ws.send(json.dumps({"ping": 1}))
            ping_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            ping_resp = json.loads(ping_resp_raw)
            if ping_resp.get("ping") != "pong":
                results["steps"]["ping_test"] = {"success": False, "response": ping_resp}
                results["status"] = "CONNECTION_FAILED"
                return results
            results["steps"]["ping_test"] = {
                "success": True,
                "latency_ms": round((time.time() - t_ping0) * 1000, 2)
            }

            # Step 3: Optional Authentication
            if self.api_token:
                await ws.send(json.dumps({"authorize": self.api_token}))
                auth_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                auth_resp = json.loads(auth_resp_raw)
                if "error" in auth_resp:
                    results["steps"]["authentication"] = {"success": False, "error": auth_resp["error"]}
                    results["status"] = "AUTHENTICATION_FAILED"
                    results["error_details"] = auth_resp["error"].get("message", "Authorization failed")
                    return results
                results["authenticated_session"] = True
                results["steps"]["authentication"] = {
                    "success": True,
                    "account_currency": auth_resp.get("authorize", {}).get("currency"),
                    "is_virtual": bool(auth_resp.get("authorize", {}).get("is_virtual"))
                }
            else:
                results["steps"]["authentication"] = {
                    "success": True,
                    "mode": "PUBLIC_MARKET_DATA_ONLY"
                }

            # Step 4: Active Symbols Listing
            await ws.send(json.dumps({"active_symbols": "brief", "product_type": "basic"}))
            symbols_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            symbols_resp = json.loads(symbols_resp_raw)
            active_list = symbols_resp.get("active_symbols", [])
            found_symbol = any(s.get("symbol") == self.symbol for s in active_list)
            if not found_symbol and active_list:
                results["steps"]["symbol_support"] = {
                    "success": False,
                    "target": self.symbol,
                    "total_available": len(active_list)
                }
                results["status"] = "SYMBOL_UNSUPPORTED"
                results["error_details"] = f"Symbol {self.symbol} not found in active symbols."
                return results
            results["steps"]["symbol_support"] = {
                "success": True,
                "symbol_found": self.symbol,
                "total_active_symbols": len(active_list)
            }

            # Step 5: Market Tick Subscription
            await ws.send(json.dumps({"ticks": self.symbol, "subscribe": 1}))
            tick_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            tick_resp = json.loads(tick_resp_raw)

            if "error" in tick_resp:
                results["steps"]["tick_subscription"] = {"success": False, "error": tick_resp["error"]}
                results["status"] = "TICK_STREAM_FAILED"
                results["error_details"] = tick_resp["error"].get("message")
                return results

            tick_data = tick_resp.get("tick")
            sub_id = tick_resp.get("subscription", {}).get("id")

            if not tick_data or "quote" not in tick_data or "epoch" not in tick_data:
                results["steps"]["tick_subscription"] = {"success": False, "raw": tick_resp}
                results["status"] = "TICK_STREAM_FAILED"
                return results

            results["steps"]["tick_subscription"] = {
                "success": True,
                "sample_quote": float(tick_data["quote"]),
                "sample_epoch": int(tick_data["epoch"]),
                "server_symbol": tick_data.get("symbol")
            }

            # Forget tick subscription to leave clean state
            if sub_id:
                try:
                    await ws.send(json.dumps({"forget": sub_id}))
                    await asyncio.wait_for(ws.recv(), timeout=3.0)
                except Exception:
                    pass

            # Step 6: Query RUNHIGH Proposal
            t_req_rh = time.time()
            rh_req = {
                "proposal": 1,
                "amount": 2.0,
                "basis": "stake",
                "currency": "USD",
                "symbol": self.symbol,
                "duration": 5,
                "duration_unit": "t",
                "contract_type": "RUNHIGH"
            }
            await ws.send(json.dumps(rh_req))
            rh_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            rh_resp = json.loads(rh_resp_raw)
            t_res_rh = time.time()

            # Step 7: Query RUNLOW Proposal
            t_req_rl = time.time()
            rl_req = {
                "proposal": 1,
                "amount": 2.0,
                "basis": "stake",
                "currency": "USD",
                "symbol": self.symbol,
                "duration": 5,
                "duration_unit": "t",
                "contract_type": "RUNLOW"
            }
            await ws.send(json.dumps(rl_req))
            rl_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            rl_resp = json.loads(rl_resp_raw)
            t_res_rl = time.time()

            # Step 8: Validate Proposal Responses
            if "error" in rh_resp or "error" in rl_resp:
                err = rh_resp.get("error") or rl_resp.get("error")
                code = err.get("code", "")
                msg = err.get("message", "")
                results["steps"]["proposal_queries"] = {
                    "success": False,
                    "runhigh_error": rh_resp.get("error"),
                    "runlow_error": rl_resp.get("error")
                }
                if any(x in code.lower() or x in msg.lower() for x in ["contract", "invalidcontract", "unsupported"]):
                    results["status"] = "CONTRACT_UNSUPPORTED"
                else:
                    results["status"] = "PROPOSAL_FAILED"
                results["error_details"] = f"Proposal error: {code} - {msg}"
                return results

            p_rh = rh_resp.get("proposal", {})
            p_rl = rl_resp.get("proposal", {})

            rh_ask = float(p_rh.get("ask_price", 0.0))
            rh_payout = float(p_rh.get("payout", 0.0))
            rl_ask = float(p_rl.get("ask_price", 0.0))
            rl_payout = float(p_rl.get("payout", 0.0))

            if rh_ask <= 0 or rh_payout <= 0 or rl_ask <= 0 or rl_payout <= 0:
                results["steps"]["proposal_queries"] = {
                    "success": False,
                    "runhigh_ask": rh_ask,
                    "runhigh_payout": rh_payout,
                    "runlow_ask": rl_ask,
                    "runlow_payout": rl_payout
                }
                results["status"] = "QUOTE_VALIDATION_FAILED"
                results["error_details"] = "Proposal returned non-positive ask or payout values."
                return results

            # Persist genuine quotes to database
            sess_id = f"diag_{int(time.time())}"
            rec_rh = ProposalRecord(
                request_timestamp=t_req_rh,
                response_timestamp=t_res_rh,
                market_symbol=self.symbol,
                contract_type="RUNHIGH",
                contract_duration=5,
                duration_unit="t",
                stake=rh_ask,
                total_payout=rh_payout,
                potential_net_profit=round(rh_payout - rh_ask, 2),
                currency="USD",
                proposal_id=str(p_rh.get("id")),
                quote_source="live_proposal",
                quote_latency_ms=round((t_res_rh - t_req_rh) * 1000, 2),
                collection_status="QUOTE_AVAILABLE",
                session_id=sess_id
            )
            rec_rl = ProposalRecord(
                request_timestamp=t_req_rl,
                response_timestamp=t_res_rl,
                market_symbol=self.symbol,
                contract_type="RUNLOW",
                contract_duration=5,
                duration_unit="t",
                stake=rl_ask,
                total_payout=rl_payout,
                potential_net_profit=round(rl_payout - rl_ask, 2),
                currency="USD",
                proposal_id=str(p_rl.get("id")),
                quote_source="live_proposal",
                quote_latency_ms=round((t_res_rl - t_req_rl) * 1000, 2),
                collection_status="QUOTE_AVAILABLE",
                session_id=sess_id
            )
            self.quote_db.store_quotes_batch([rec_rh, rec_rl])
            results["quotes_persisted"] = 2

            results["steps"]["proposal_queries"] = {
                "success": True,
                "runhigh": {
                    "id": p_rh.get("id"),
                    "ask_price": rh_ask,
                    "total_payout": rh_payout,
                    "implied_break_even": round(rh_ask / rh_payout, 5)
                },
                "runlow": {
                    "id": p_rl.get("id"),
                    "ask_price": rl_ask,
                    "total_payout": rl_payout,
                    "implied_break_even": round(rl_ask / rl_payout, 5)
                }
            }

            # All diagnostic verification gates passed!
            results["status"] = "CONNECTION_SUCCESS"

        except asyncio.TimeoutError:
            results["status"] = "CONNECTION_FAILED"
            results["error_details"] = "Timed out waiting for API response."
        except Exception as e:
            results["status"] = "CONNECTION_FAILED"
            results["error_details"] = f"Unexpected error during diagnostic: {str(e)}"
        finally:
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

        return results

    def save_diagnostic_report(self, results: Dict[str, Any], filepath: str = DEFAULT_DIAGNOSTIC_PATH):
        """Persists the diagnostic results as a JSON artifact."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Deriv Live API Connection Verifier (V1.5.3 Hotfix)")
    parser.add_argument("--symbol", default="R_75", help="Market symbol to verify (default: R_75)")
    parser.add_argument("--app-id", default=None, help="Deriv Application ID")
    parser.add_argument("--token", default=None, help="Optional Deriv API token")
    parser.add_argument("--timeout", type=float, default=12.0, help="Request timeout seconds")
    parser.add_argument("--output", default=DEFAULT_DIAGNOSTIC_PATH, help="Output JSON artifact path")
    args = parser.parse_args()

    print("\n" + "=" * 68)
    print("      DERIV LIVE API DIAGNOSTIC VERIFICATION (V1.5.3 HOTFIX)")
    print("=" * 68)
    print(f"  Target Symbol:    {args.symbol}")
    print(f"  Contract Family:  RUNHIGH / RUNLOW (5-tick Only Ups / Only Downs)")
    print(f"  Safety Directive: Purchases strictly disabled (Diagnostics only)")
    print(f"  Timeout:          {args.timeout}s\n")

    verifier = DerivConnectionVerifier(
        symbol=args.symbol,
        app_id=args.app_id,
        api_token=args.token,
        timeout_seconds=args.timeout
    )

    results = asyncio.run(verifier.run_diagnostics())
    verifier.save_diagnostic_report(results, filepath=args.output)

    print(f"Diagnostic Result Status: [{results['status']}]")
    if results.get("error_details"):
        print(f"  Details: {results['error_details']}\n")

    pre = results.get("preflight", {})
    if pre:
        print("  Pre-flight Checks:")
        print(f"    - DNS Resolution:     {'SUCCESS' if pre.get('dns_resolved') else 'FAILED'} (IPs: {', '.join(pre.get('resolved_ips', []))} | {pre.get('dns_latency_ms', 0)} ms)")
        print(f"    - TCP Connection:     {'SUCCESS' if pre.get('tcp_connected') else 'FAILED'} ({pre.get('tcp_latency_ms', 0)} ms)")
        print(f"    - TLS Handshake:      {'SUCCESS' if pre.get('tls_handshake') else 'FAILED'} (Version: {pre.get('tls_version')} | Cipher: {pre.get('cipher')} | {pre.get('tls_latency_ms', 0)} ms)")

    steps = results.get("steps", {})
    if "websocket_connection" in steps:
        s = steps["websocket_connection"]
        print(f"\n  WebSocket Session:")
        print(f"    - Handshake:          {'SUCCESS' if s.get('success') else 'FAILED'} ({s.get('latency_ms', 'N/A')} ms)")
    if "ping_test" in steps:
        s = steps["ping_test"]
        print(f"    - Ping Response:      {'SUCCESS' if s.get('success') else 'FAILED'} ({s.get('latency_ms', 'N/A')} ms)")
    if "authentication" in steps:
        s = steps["authentication"]
        print(f"    - Authentication:     {'SUCCESS' if s.get('success') else 'FAILED'} (Mode: {s.get('mode', 'TOKEN')})")
    if "symbol_support" in steps:
        s = steps["symbol_support"]
        print(f"    - Symbol Support:     {'SUCCESS' if s.get('success') else 'FAILED'} ({s.get('symbol_found', 'N/A')})")
    if "tick_subscription" in steps:
        s = steps["tick_subscription"]
        print(f"    - Tick Stream:        {'SUCCESS' if s.get('success') else 'FAILED'} (Sample: {s.get('sample_quote', 'N/A')})")
    if "proposal_queries" in steps:
        s = steps["proposal_queries"]
        if s.get("success"):
            rh = s["runhigh"]
            rl = s["runlow"]
            print(f"    - RUNHIGH Proposal:   SUCCESS (Ask: ${rh['ask_price']:.2f} -> Payout: ${rh['total_payout']:.2f} | BE: {rh['implied_break_even']:.3%})")
            print(f"    - RUNLOW Proposal:    SUCCESS (Ask: ${rl['ask_price']:.2f} -> Payout: ${rl['total_payout']:.2f} | BE: {rl['implied_break_even']:.3%})")
            print(f"    - Quotes Persisted:   {results.get('quotes_persisted', 0)} records -> data/quotes.db")
        else:
            print(f"    - Proposal Queries:   FAILED")

    print(f"\nDiagnostic artifact saved to: {args.output}")
    print("=" * 68 + "\n")

    if results["status"] != "CONNECTION_SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
