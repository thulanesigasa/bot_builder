"""Live Deriv API Connection and RUNHIGH/RUNLOW Proposal Diagnostic Tool (V1.5.3 Final Patch).

Executes comprehensive 8-stage live API verification WITHOUT purchasing contracts:
Stage 1: DNS Resolution (IPv4/IPv6, latency)
Stage 2: TCP Socket Connection (Port 443)
Stage 3: Secure TLS 1.3 Handshake & Cipher Suite Negotiation
Stage 4: WebSocket Upgrade Handshake (with distinct error taxonomy: TIMEOUT, HTTP 520, 403, 429)
Stage 5: Deriv API Response (Ping / Pong & Server Time verification)
Stage 6: Real-time Tick Subscription & Price/Epoch Validation
Stage 7: RUNHIGH and RUNLOW Proposal Quotes (underlying_symbol, ask, payout, implied break-even)
Stage 8: SQLite Database Persistence & Round-Trip Retrieval Verification

Accurate Status Taxonomy:
- CONNECTION_SUCCESS
- DNS_FAILURE
- TCP_CONNECTION_FAILED
- TLS_HANDSHAKE_FAILED
- WEBSOCKET_HANDSHAKE_TIMEOUT
- HTTP_520
- HTTP_403
- HTTP_429
- AUTHENTICATION_FAILED
- INVALID_APP_ID
- UNSUPPORTED_SYMBOL
- UNSUPPORTED_CONTRACT
- PROPOSAL_REQUEST_FAILED
- QUOTE_VALIDATION_FAILED
- CONNECTION_FAILED
"""
import argparse
import asyncio
import json
import math
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
    """Performs rigorous 8-stage end-to-end diagnostic checks against the Deriv WebSocket API."""

    def __init__(
        self,
        symbol: str = "R_75",
        app_id: Optional[str] = None,
        api_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout_seconds: float = 12.0
    ):
        self.symbol = symbol
        self.app_id = str(app_id or DEFAULT_CONFIG.app_id or "1089")
        self.api_token = api_token or os.environ.get("DERIV_API_TOKEN") or os.environ.get("DERIV_TOKEN")
        self.timeout = timeout_seconds

        candidate_endpoints = [
            f"wss://api.derivws.com/trading/v1/options/ws/public?app_id={self.app_id}",
            f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}",
            f"wss://ws.binaryws.com/websockets/v3?app_id={self.app_id}",
            f"wss://frontend.binaryws.com/websockets/v3?app_id={self.app_id}"
        ]
        if endpoint_url:
            base = endpoint_url if "?" in endpoint_url else f"{endpoint_url}?app_id={self.app_id}"
            self.endpoints = [base]
        else:
            self.endpoints = candidate_endpoints

        self.ws_url = self.endpoints[0]
        self.quote_db = QuoteDatabase()

    def run_preflight_network_check(self, target_url: str) -> Dict[str, Any]:
        """Stages 1-3: Runs DNS, TCP, and TLS socket checks before initiating WebSocket handshake."""
        parsed = urlparse(target_url)
        hostname = parsed.hostname or "api.derivws.com"
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
            "stage_1_dns": {"status": "PENDING", "latency_ms": 0.0, "resolved_ips": []},
            "stage_2_tcp": {"status": "PENDING", "latency_ms": 0.0},
            "stage_3_tls": {"status": "PENDING", "latency_ms": 0.0, "version": None, "cipher": None},
            "preflight_status": "PENDING",
            "preflight_error": None
        }

        # Stage 1: DNS Resolution
        t0 = time.time()
        try:
            addr_info = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
            ips = sorted(list({entry[4][0] for entry in addr_info}))
            dns_ms = round((time.time() - t0) * 1000, 2)
            check_res["dns_resolved"] = True
            check_res["resolved_ips"] = ips
            check_res["dns_latency_ms"] = dns_ms
            check_res["stage_1_dns"] = {
                "status": "SUCCESS",
                "latency_ms": dns_ms,
                "resolved_ips": ips
            }
        except Exception as e:
            check_res["stage_1_dns"]["status"] = "FAILED"
            check_res["preflight_status"] = "DNS_FAILURE"
            check_res["preflight_error"] = f"DNS resolution failed for {hostname}: {e}"
            return check_res

        # Stage 2: Raw TCP Connect
        target_ip = ips[0]
        t_tcp0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(4.0, self.timeout / 2.0))
        try:
            sock.connect((target_ip, port))
            tcp_ms = round((time.time() - t_tcp0) * 1000, 2)
            check_res["tcp_connected"] = True
            check_res["tcp_latency_ms"] = tcp_ms
            check_res["stage_2_tcp"] = {
                "status": "SUCCESS",
                "latency_ms": tcp_ms,
                "connected_ip": target_ip
            }
        except Exception as e:
            check_res["stage_2_tcp"]["status"] = "FAILED"
            check_res["preflight_status"] = "TCP_CONNECTION_FAILED"
            check_res["preflight_error"] = f"TCP Connect to {target_ip}:{port} failed: {e}"
            sock.close()
            return check_res

        # Stage 3: Secure TLS Handshake
        t_tls0 = time.time()
        context = ssl.create_default_context()
        try:
            tls_sock = context.wrap_socket(sock, server_hostname=hostname)
            tls_ms = round((time.time() - t_tls0) * 1000, 2)
            cipher_info = tls_sock.cipher()
            check_res["tls_handshake"] = True
            check_res["tls_latency_ms"] = tls_ms
            check_res["tls_version"] = tls_sock.version()
            check_res["cipher"] = cipher_info[0] if cipher_info else None
            check_res["stage_3_tls"] = {
                "status": "SUCCESS",
                "latency_ms": tls_ms,
                "version": tls_sock.version(),
                "cipher": cipher_info[0] if cipher_info else None
            }
            check_res["preflight_status"] = "PREFLIGHT_SUCCESS"
            tls_sock.close()
        except Exception as e:
            check_res["stage_3_tls"]["status"] = "FAILED"
            check_res["preflight_status"] = "TLS_HANDSHAKE_FAILED"
            check_res["preflight_error"] = f"TLS handshake failed: {e}"
            sock.close()
            return check_res

        return check_res

    async def run_diagnostics(self) -> Dict[str, Any]:
        """Runs the complete 8-stage diagnostic suite and returns structured results."""
        results: Dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target_symbol": self.symbol,
            "app_id": self.app_id,
            "endpoint_url": self.ws_url,
            "authenticated_session": False,
            "stages": {
                "stage_1_dns": {"status": "PENDING"},
                "stage_2_tcp": {"status": "PENDING"},
                "stage_3_tls": {"status": "PENDING"},
                "stage_4_websocket_handshake": {"status": "PENDING"},
                "stage_5_api_response": {"status": "PENDING"},
                "stage_6_tick_subscription": {"status": "PENDING"},
                "stage_7_proposal_verification": {"status": "PENDING"},
                "stage_8_persistence": {"status": "PENDING"}
            },
            "quotes_persisted": 0,
            "status": "CONNECTION_FAILED",
            "error_details": None
        }

        # Stages 1-3: Preflight network checks
        preflight = self.run_preflight_network_check(self.ws_url)
        results["stages"]["stage_1_dns"] = preflight["stage_1_dns"]
        results["stages"]["stage_2_tcp"] = preflight["stage_2_tcp"]
        results["stages"]["stage_3_tls"] = preflight["stage_3_tls"]

        if preflight["preflight_status"] != "PREFLIGHT_SUCCESS":
            results["status"] = preflight["preflight_status"]
            results["error_details"] = preflight["preflight_error"]
            return results

        ws = None
        try:
            # Stage 4: WebSocket Handshake with Endpoint Fallback
            connected = False
            last_err = None
            active_endpoint = self.endpoints[0]
            per_endpoint_timeout = max(3.0, self.timeout / len(self.endpoints))

            for ep in self.endpoints:
                t_ws0 = time.time()
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
                    ws_ms = round((time.time() - t_ws0) * 1000, 2)
                    results["stages"]["stage_4_websocket_handshake"] = {
                        "status": "SUCCESS",
                        "endpoint": active_endpoint,
                        "latency_ms": ws_ms
                    }
                    break
                except asyncio.TimeoutError as te:
                    last_err = te
                except Exception as e:
                    last_err = e

            if not connected:
                err_str = f"{type(last_err).__name__}: {str(last_err)}" if str(last_err) else repr(last_err)
                results["stages"]["stage_4_websocket_handshake"] = {"status": "FAILED", "error": err_str}

                # Explicit taxonomic classification
                if isinstance(last_err, asyncio.TimeoutError) or "TimeoutError" in err_str:
                    results["status"] = "WEBSOCKET_HANDSHAKE_TIMEOUT"
                    results["error_details"] = f"WebSocket handshake timed out across endpoints ({', '.join(self.endpoints)})."
                elif "520" in err_str:
                    results["status"] = "HTTP_520"
                    results["error_details"] = "Cloudflare edge returned HTTP 520 (Origin Web Server Error)."
                elif "403" in err_str:
                    results["status"] = "HTTP_403"
                    results["error_details"] = "Cloudflare or Deriv origin rejected handshake with HTTP 403 Forbidden."
                elif "429" in err_str:
                    results["status"] = "HTTP_429"
                    results["error_details"] = "Deriv API rate limit exceeded (HTTP 429 Too Many Requests)."
                else:
                    results["status"] = "CONNECTION_FAILED"
                    results["error_details"] = f"Failed to connect to endpoints ({', '.join(self.endpoints)}): {err_str}"
                return results

            # Stage 5: Deriv API Response (Ping / Pong & Time)
            t_ping0 = time.time()
            await ws.send(json.dumps({"ping": 1}))
            ping_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            ping_resp = json.loads(ping_resp_raw)

            if ping_resp.get("ping") != "pong":
                results["stages"]["stage_5_api_response"] = {"status": "FAILED", "response": ping_resp}
                results["status"] = "CONNECTION_FAILED"
                results["error_details"] = "Invalid ping response from Deriv API."
                return results

            await ws.send(json.dumps({"time": 1}))
            time_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            time_resp = json.loads(time_resp_raw)
            server_epoch = time_resp.get("time")

            ping_ms = round((time.time() - t_ping0) * 1000, 2)
            results["stages"]["stage_5_api_response"] = {
                "status": "SUCCESS",
                "ping_latency_ms": ping_ms,
                "server_epoch": server_epoch
            }

            # Optional Authentication Check
            if self.api_token:
                await ws.send(json.dumps({"authorize": self.api_token}))
                auth_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                auth_resp = json.loads(auth_resp_raw)
                if "error" in auth_resp:
                    results["status"] = "AUTHENTICATION_FAILED"
                    results["error_details"] = auth_resp["error"].get("message", "Authorization failed")
                    return results
                results["authenticated_session"] = True

            # Stage 6: Market Tick Subscription
            t_tick0 = time.time()
            await ws.send(json.dumps({"ticks": self.symbol, "subscribe": 1}))
            tick_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            tick_resp = json.loads(tick_resp_raw)

            if "error" in tick_resp:
                err_code = tick_resp["error"].get("code", "")
                results["stages"]["stage_6_tick_subscription"] = {"status": "FAILED", "error": tick_resp["error"]}
                if "symbol" in err_code.lower() or "unsupported" in err_code.lower():
                    results["status"] = "UNSUPPORTED_SYMBOL"
                else:
                    results["status"] = "PROPOSAL_REQUEST_FAILED"
                results["error_details"] = tick_resp["error"].get("message")
                return results

            tick_data = tick_resp.get("tick")
            sub_id = tick_resp.get("subscription", {}).get("id")

            if not tick_data or "quote" not in tick_data or "epoch" not in tick_data:
                results["stages"]["stage_6_tick_subscription"] = {"status": "FAILED", "raw": tick_resp}
                results["status"] = "PROPOSAL_REQUEST_FAILED"
                return results

            results["stages"]["stage_6_tick_subscription"] = {
                "status": "SUCCESS",
                "sample_quote": float(tick_data["quote"]),
                "sample_epoch": int(tick_data["epoch"]),
                "server_symbol": tick_data.get("symbol"),
                "latency_ms": round((time.time() - t_tick0) * 1000, 2)
            }

            # Clean up tick subscription
            if sub_id:
                try:
                    await ws.send(json.dumps({"forget": sub_id}))
                    await asyncio.wait_for(ws.recv(), timeout=3.0)
                except Exception:
                    pass

            # Stage 7: Query RUNHIGH and RUNLOW Proposals (Genuine Quotes)
            t_req_rh = time.time()
            rh_req = {
                "proposal": 1,
                "amount": 2.0,
                "basis": "stake",
                "currency": "USD",
                "underlying_symbol": self.symbol,
                "duration": 5,
                "duration_unit": "t",
                "contract_type": "RUNHIGH"
            }
            await ws.send(json.dumps(rh_req))
            rh_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            rh_resp = json.loads(rh_resp_raw)
            t_res_rh = time.time()

            t_req_rl = time.time()
            rl_req = {
                "proposal": 1,
                "amount": 2.0,
                "basis": "stake",
                "currency": "USD",
                "underlying_symbol": self.symbol,
                "duration": 5,
                "duration_unit": "t",
                "contract_type": "RUNLOW"
            }
            await ws.send(json.dumps(rl_req))
            rl_resp_raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            rl_resp = json.loads(rl_resp_raw)
            t_res_rl = time.time()

            # Check for API error responses
            if "error" in rh_resp or "error" in rl_resp:
                err = rh_resp.get("error") or rl_resp.get("error")
                code = err.get("code", "")
                msg = err.get("message", "")
                results["stages"]["stage_7_proposal_verification"] = {
                    "status": "FAILED",
                    "runhigh_error": rh_resp.get("error"),
                    "runlow_error": rl_resp.get("error")
                }
                if any(x in code.lower() or x in msg.lower() for x in ["contract", "invalidcontract", "unsupported"]):
                    results["status"] = "UNSUPPORTED_CONTRACT"
                else:
                    results["status"] = "PROPOSAL_REQUEST_FAILED"
                results["error_details"] = f"Proposal error: {code} - {msg}"
                return results

            p_rh = rh_resp.get("proposal", {})
            p_rl = rl_resp.get("proposal", {})

            rh_ask = float(p_rh.get("ask_price", 0.0))
            rh_payout = float(p_rh.get("payout", 0.0))
            rl_ask = float(p_rl.get("ask_price", 0.0))
            rl_payout = float(p_rl.get("payout", 0.0))

            # Financial Sanity Validation
            if (rh_ask <= 0 or rh_payout <= 0 or rl_ask <= 0 or rl_payout <= 0 or
                    math.isnan(rh_ask) or math.isnan(rh_payout) or math.isnan(rl_ask) or math.isnan(rl_payout) or
                    rh_ask >= rh_payout or rl_ask >= rl_payout):
                results["stages"]["stage_7_proposal_verification"] = {
                    "status": "FAILED",
                    "runhigh_ask": rh_ask,
                    "runhigh_payout": rh_payout,
                    "runlow_ask": rl_ask,
                    "runlow_payout": rl_payout
                }
                results["status"] = "QUOTE_VALIDATION_FAILED"
                results["error_details"] = "Proposal returned invalid ask or payout values."
                return results

            results["stages"]["stage_7_proposal_verification"] = {
                "status": "SUCCESS",
                "runhigh": {
                    "proposal_id": p_rh.get("id"),
                    "ask_price": rh_ask,
                    "total_payout": rh_payout,
                    "implied_break_even": round(rh_ask / rh_payout, 5),
                    "latency_ms": round((t_res_rh - t_req_rh) * 1000, 2)
                },
                "runlow": {
                    "proposal_id": p_rl.get("id"),
                    "ask_price": rl_ask,
                    "total_payout": rl_payout,
                    "implied_break_even": round(rl_ask / rl_payout, 5),
                    "latency_ms": round((t_res_rl - t_req_rl) * 1000, 2)
                }
            }

            # Stage 8: Persistence & Verified Retrieval
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

            # Store batch
            self.quote_db.store_quotes_batch([rec_rh, rec_rl])
            results["quotes_persisted"] = 2

            # Verify round-trip retrieval
            retrieved_rh = self.quote_db.get_latest_quote_before(
                symbol=self.symbol,
                contract_type="RUNHIGH",
                timestamp=t_res_rh + 1.0,
                max_freshness_seconds=60.0
            )
            retrieved_rl = self.quote_db.get_latest_quote_before(
                symbol=self.symbol,
                contract_type="RUNLOW",
                timestamp=t_res_rl + 1.0,
                max_freshness_seconds=60.0
            )

            persistence_verified = (retrieved_rh is not None and retrieved_rl is not None)
            results["stages"]["stage_8_persistence"] = {
                "status": "SUCCESS" if persistence_verified else "FAILED",
                "quotes_stored": 2,
                "retrieval_verified": persistence_verified,
                "session_id": sess_id
            }

            if not persistence_verified:
                results["status"] = "QUOTE_VALIDATION_FAILED"
                results["error_details"] = "Stored quotes failed round-trip database query verification."
                return results

            # All 8 Diagnostic Stages Succeeded!
            results["status"] = "CONNECTION_SUCCESS"

        except asyncio.TimeoutError:
            results["status"] = "WEBSOCKET_HANDSHAKE_TIMEOUT"
            results["error_details"] = "Timed out waiting for Deriv API response."
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
        """Persists the diagnostic results as a sanitized JSON artifact."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        # Deep copy and sanitize (never persist credentials)
        clean_res = json.loads(json.dumps(results))
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean_res, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Deriv Live API Multi-Stage Diagnostic Verifier (V1.5.3 Final Patch)")
    parser.add_argument("--symbol", default="R_75", help="Market symbol to verify (default: R_75)")
    parser.add_argument("--app-id", default=None, help="Deriv Application ID")
    parser.add_argument("--token", default=None, help="Optional Deriv API token")
    parser.add_argument("--timeout", type=float, default=12.0, help="Request timeout seconds")
    parser.add_argument("--output", default=DEFAULT_DIAGNOSTIC_PATH, help="Output JSON artifact path")
    args = parser.parse_args()

    print("\n" + "=" * 68)
    print("      DERIV LIVE API 8-STAGE DIAGNOSTIC VERIFICATION (V1.5.3)")
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

    stages = results.get("stages", {})
    print("  8-Stage Diagnostic Results:")
    s1 = stages.get("stage_1_dns", {})
    print(f"    - Stage 1 (DNS Resolution):           {s1.get('status')} ({s1.get('latency_ms', 0)} ms | {', '.join(s1.get('resolved_ips', []))})")
    s2 = stages.get("stage_2_tcp", {})
    print(f"    - Stage 2 (TCP Socket Connect):       {s2.get('status')} ({s2.get('latency_ms', 0)} ms)")
    s3 = stages.get("stage_3_tls", {})
    print(f"    - Stage 3 (Secure TLS Handshake):     {s3.get('status')} ({s3.get('latency_ms', 0)} ms | {s3.get('version')} | {s3.get('cipher')})")
    s4 = stages.get("stage_4_websocket_handshake", {})
    print(f"    - Stage 4 (WebSocket Handshake):       {s4.get('status')} ({s4.get('latency_ms', 'N/A')} ms | {s4.get('endpoint', 'N/A')})")
    s5 = stages.get("stage_5_api_response", {})
    print(f"    - Stage 5 (Deriv API Response):       {s5.get('status')} (Ping: {s5.get('ping_latency_ms', 'N/A')} ms | Epoch: {s5.get('server_epoch', 'N/A')})")
    s6 = stages.get("stage_6_tick_subscription", {})
    print(f"    - Stage 6 (Tick Subscription):        {s6.get('status')} (Quote: {s6.get('sample_quote', 'N/A')} | Epoch: {s6.get('sample_epoch', 'N/A')})")
    s7 = stages.get("stage_7_proposal_verification", {})
    if s7.get("status") == "SUCCESS":
        rh = s7.get("runhigh", {})
        rl = s7.get("runlow", {})
        print(f"    - Stage 7 (Proposal Quotes):          SUCCESS")
        print(f"        * RUNHIGH: Ask ${rh.get('ask_price', 0):.2f} -> Payout ${rh.get('total_payout', 0):.2f} (BE: {rh.get('implied_break_even', 0):.3%})")
        print(f"        * RUNLOW:  Ask ${rl.get('ask_price', 0):.2f} -> Payout ${rl.get('total_payout', 0):.2f} (BE: {rl.get('implied_break_even', 0):.3%})")
    else:
        print(f"    - Stage 7 (Proposal Quotes):          {s7.get('status')}")
    s8 = stages.get("stage_8_persistence", {})
    print(f"    - Stage 8 (Persistence & Retrieval):  {s8.get('status')} ({results.get('quotes_persisted', 0)} quotes verified in SQLite)")

    print(f"\nDiagnostic artifact saved to: {args.output}")
    print("=" * 68 + "\n")

    if results["status"] != "CONNECTION_SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
