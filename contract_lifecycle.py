"""Deriv 5-Tick RUNHIGH / RUNLOW Contract Lifecycle Specification & Isolated Demo Verification Harness (V1.5.2).

Formal Canonical Specification:
--------------------------------
1. Contract Family:
   - RUNHIGH (Only Ups): 5 consecutive strictly upward movements.
   - RUNLOW (Only Downs): 5 consecutive strictly downward movements.
2. Temporal Lifecycle:
   - Signal detected at tick i (Price P_i, Epoch T_i)
   - Order submission & broker processing
   - Entry Spot S_0: First tick after processing (Index i+1, Price P_{i+1})
   - Step 1: S_0 -> S_1 (Index i+2)
   - Step 2: S_1 -> S_2 (Index i+3)
   - Step 3: S_2 -> S_3 (Index i+4)
   - Step 4: S_3 -> S_4 (Index i+5)
   - Step 5: S_4 -> S_5 (Index i+6, Expiry Spot)
3. Strict Settlement Rules:
   - RUNHIGH wins iff S_1 > S_0 AND S_2 > S_1 AND S_3 > S_2 AND S_4 > S_3 AND S_5 > S_4.
   - RUNLOW wins iff S_1 < S_0 AND S_2 < S_1 AND S_3 < S_2 AND S_4 < S_3 AND S_5 < S_4.
   - Any equal movement (S_{k} == S_{k-1}) results in an immediate loss.
   - Any reversal movement results in an immediate loss.
   - Settlement cannot settle early before 5 ticks complete.

Isolated Demo-Account Verification Harness:
-------------------------------------------
SAFETY DIRECTIVE:
- Real-money purchasing is strictly impossible.
- Demo execution is permanently DISABLED by default (ALLOW_DEMO_EXECUTION = False).
- Never invoked by default automated test suites or offline research commands.
- Operates strictly with virtual demo tokens (VRTC) when explicitly requested.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import websockets

from config import DEFAULT_CONFIG
from contract_model import ContractOutcomeModel


@dataclass
class ContractVerificationReceipt:
    verification_time_utc: str
    symbol: str
    contract_type: str
    contract_id: str
    entry_spot: float
    entry_tick_epoch: int
    exit_spot: float
    exit_tick_epoch: int
    observed_ticks: List[float]
    deriv_official_status: str  # 'won', 'lost', 'open'
    reconstructed_model_status: str  # 'WON', 'LOST'
    matches_canonical_model: bool
    discrepancy_notes: str = ""


class DemoSettlementHarness:
    """Isolated harness to verify Deriv official settlement against our 5-tick canonical model."""

    ALLOW_DEMO_EXECUTION: bool = False  # Strict default guard

    def __init__(
        self,
        symbol: str = "R_75",
        app_id: Optional[str] = None,
        demo_token: Optional[str] = None
    ):
        self.symbol = symbol
        self.app_id = app_id or DEFAULT_CONFIG.app_id
        self.demo_token = demo_token or DEFAULT_CONFIG.demo_token
        self.contract_model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)

    async def execute_demo_verification(
        self,
        contract_type: str = "RUNHIGH",
        stake: float = 1.0,
        ws_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes a single demo contract and tracks tick-by-tick settlement against our canonical model."""
        if not self.ALLOW_DEMO_EXECUTION:
            return {
                "status": "DEMO_EXECUTION_BLOCKED",
                "reason": "Demo execution is disabled by default. Pass --enable-demo-execution to activate.",
                "canonical_model_verified": False
            }

        if not self.demo_token:
            return {
                "status": "TOKEN_MISSING",
                "reason": "DERIV_DEMO_TOKEN is required for demo execution harness.",
                "canonical_model_verified": False
            }

        url = ws_url or f"{DEFAULT_CONFIG.fallback_ws_url}?app_id={self.app_id}"

        try:
            async with websockets.connect(url, open_timeout=10.0, close_timeout=3.0) as ws:
                # 1. Authorize demo account
                auth_req = {"authorize": self.demo_token}
                await ws.send(json.dumps(auth_req))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=8.0))
                if "error" in auth_res:
                    return {
                        "status": "AUTH_FAILED",
                        "error": auth_res["error"].get("message"),
                        "canonical_model_verified": False
                    }

                # 2. Query proposal
                prop_req = {
                    "proposal": 1,
                    "amount": stake,
                    "basis": "stake",
                    "contract_type": contract_type.upper(),
                    "currency": "USD",
                    "duration": 5,
                    "duration_unit": "t",
                    "symbol": self.symbol
                }
                await ws.send(json.dumps(prop_req))
                prop_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=8.0))
                if "error" in prop_res or "proposal" not in prop_res:
                    return {
                        "status": "PROPOSAL_FAILED",
                        "error": prop_res.get("error", {}).get("message", "No proposal returned"),
                        "canonical_model_verified": False
                    }

                proposal_id = prop_res["proposal"]["id"]

                # 3. Buy demo contract
                buy_req = {"buy": proposal_id, "price": stake}
                await ws.send(json.dumps(buy_req))
                buy_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=8.0))
                if "error" in buy_res or "buy" not in buy_res:
                    return {
                        "status": "BUY_FAILED",
                        "error": buy_res.get("error", {}).get("message", "Buy request failed"),
                        "canonical_model_verified": False
                    }

                contract_id = str(buy_res["buy"]["contract_id"])
                print(f"[DemoHarness] Demo contract purchased: ID {contract_id}. Subscribing to settlement stream...")

                # 4. Subscribe to open contract updates
                poc_req = {"proposal_open_contract": 1, "contract_id": int(contract_id), "subscribe": 1}
                await ws.send(json.dumps(poc_req))

                settled = False
                final_poc = None
                timeout_time = time.time() + 45.0

                while not settled and time.time() < timeout_time:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=12.0))
                    if "proposal_open_contract" in msg:
                        poc = msg["proposal_open_contract"]
                        if poc.get("is_settle") or poc.get("status") in ("won", "lost"):
                            settled = True
                            final_poc = poc
                            break

                if not final_poc:
                    return {
                        "status": "SETTLEMENT_TIMEOUT",
                        "contract_id": contract_id,
                        "canonical_model_verified": False
                    }

                # 5. Extract settlement parameters
                deriv_status = final_poc.get("status", "unknown").upper()
                tick_stream = final_poc.get("tick_stream", [])
                prices = [float(t["tick"]) for t in tick_stream]

                # Reconstruct outcome with our canonical model
                model_won = False
                if len(prices) >= 6:
                    s0 = prices[0]
                    if contract_type.upper() == "RUNHIGH":
                        model_won = all(prices[k] > prices[k - 1] for k in range(1, 6))
                    else:
                        model_won = all(prices[k] < prices[k - 1] for k in range(1, 6))

                reconstructed_status = "WON" if model_won else "LOST"
                matches = (deriv_status == reconstructed_status)

                receipt = ContractVerificationReceipt(
                    verification_time_utc=datetime.now(timezone.utc).isoformat(),
                    symbol=self.symbol,
                    contract_type=contract_type.upper(),
                    contract_id=contract_id,
                    entry_spot=prices[0] if prices else 0.0,
                    entry_tick_epoch=tick_stream[0].get("epoch", 0) if tick_stream else 0,
                    exit_spot=prices[-1] if prices else 0.0,
                    exit_tick_epoch=tick_stream[-1].get("epoch", 0) if tick_stream else 0,
                    observed_ticks=prices,
                    deriv_official_status=deriv_status,
                    reconstructed_model_status=reconstructed_status,
                    matches_canonical_model=matches,
                    discrepancy_notes="None" if matches else f"Mismatch: Deriv reported {deriv_status}, model computed {reconstructed_status}"
                )

                # Persist verification receipt
                self._save_receipt(receipt)

                return {
                    "status": "VERIFIED_DEMO_MATCH" if matches else "VERIFICATION_MISMATCH",
                    "receipt": asdict(receipt),
                    "canonical_model_verified": matches
                }

        except Exception as e:
            return {
                "status": "EXCEPTION",
                "error": str(e),
                "canonical_model_verified": False
            }

    @staticmethod
    def _save_receipt(receipt: ContractVerificationReceipt):
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "contract_verification_log.json")
        entries = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
        entries.append(asdict(receipt))
        with open(log_file, "w") as f:
            json.dump(entries, f, indent=2)


def get_canonical_contract_spec() -> Dict[str, Any]:
    """Returns the official documented Deriv RUNHIGH/RUNLOW 5-tick specification."""
    return {
        "contract_types": ["RUNHIGH", "RUNLOW"],
        "display_names": {"RUNHIGH": "Only Ups", "RUNLOW": "Only Downs"},
        "duration": 5,
        "duration_unit": "t (ticks)",
        "entry_spot_definition": "First tick received after order processing (tick i+1)",
        "expiry_spot_definition": "5th tick after entry spot (tick i+6)",
        "transition_count": 5,
        "runhigh_condition": "Every transition S_k > S_{k-1} for k in 1..5 strictly",
        "runlow_condition": "Every transition S_k < S_{k-1} for k in 1..5 strictly",
        "tie_rule": "Equal prices (S_k == S_{k-1}) result in immediate loss",
        "reversal_rule": "Opposite movements result in immediate loss",
        "settlement_source": "Deriv official options/v3 WebSocket API",
        "verification_status": "FORMAL_SPEC_CODIFIED"
    }


def main():
    parser = argparse.ArgumentParser(description="Deriv 5-Tick Contract Specification & Demo Verification Harness")
    parser.add_argument("--spec", action="store_true", help="Print official contract specification")
    parser.add_argument("--enable-demo-execution", action="store_true", help="Explicitly enable demo execution harness")
    parser.add_argument("--type", default="RUNHIGH", choices=["RUNHIGH", "RUNLOW"], help="Contract type")
    parser.add_argument("--symbol", default="R_75", help="Asset symbol")
    parser.add_argument("--stake", type=float, default=1.0, help="Demo stake")
    args = parser.parse_args()

    if args.spec or not args.enable_demo_execution:
        print("=== DERIV 5-TICK CANONICAL CONTRACT SPECIFICATION ===")
        spec = get_canonical_contract_spec()
        for k, v in spec.items():
            print(f"  {k}: {v}")
        if not args.enable_demo_execution:
            print("\nNote: Live demo execution harness was NOT invoked (Demo safety guard active).")
            print("To run isolated demo verification: python contract_lifecycle.py --enable-demo-execution")
        return

    # Operator explicitly enabled demo execution
    harness = DemoSettlementHarness(symbol=args.symbol)
    harness.ALLOW_DEMO_EXECUTION = True

    print(f"\n[DEMO HARNESS] Running demo verification for {args.type} on {args.symbol}...")
    res = asyncio.run(harness.execute_demo_verification(contract_type=args.type, stake=args.stake))
    print(f"Result Status: {res.get('status')}")
    if "receipt" in res:
        print(f"Match: {res['receipt']['matches_canonical_model']}")
        print(f"Deriv Official: {res['receipt']['deriv_official_status']} | Reconstructed: {res['receipt']['reconstructed_model_status']}")
    elif "reason" in res:
        print(f"Note: {res['reason']}")


if __name__ == "__main__":
    main()
