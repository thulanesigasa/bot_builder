"""Fail-closed independent confirmation readiness gate.

Do not mistake an exploratory winner for an independently validated edge.
No live execution or Deriv network access is permitted by this module.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from forward_shadow_engine import LIVE_EXECUTION_DISABLED, DECISION

REQUIRED = (
    "primary_market", "primary_contract", "primary_duration_ticks",
    "frozen_model_sha256", "analysis_code_sha256", "primary_alternative",
    "alpha", "power", "minimum_economically_relevant_ev",
    "expected_return_stddev", "dependence_inflation_factor",
    "expected_quote_coverage", "fixed_eligible_sample_size",
    "maximum_collection_sessions", "preregistration_utc",
    "confirmation_start_utc", "pilot_observations_excluded",
)

def evaluate(plan):
    reasons = []
    if LIVE_EXECUTION_DISABLED is not True or DECISION != "NO_TRADE":
        reasons.append("NON_PURCHASING_INVARIANT_FAILED")
    for field in REQUIRED:
        if field not in plan or plan[field] is None:
            reasons.append("MISSING_"+field.upper())
    if reasons:
        return {"ready": False, "reasons": reasons, "required_eligible_n": None}
    if plan["primary_market"] not in ("R_100","1HZ100V","R_75","1HZ75V","R_50","1HZ50V"):
        reasons.append("INVALID_MARKET")
    if plan["primary_contract"] not in ("CALL","PUT","RUNHIGH","RUNLOW"):
        reasons.append("INVALID_CONTRACT")
    if plan["primary_duration_ticks"] not in (2,5):
        reasons.append("INVALID_DURATION")
    if plan["primary_alternative"] != "mean_net_return_greater_than_zero":
        reasons.append("INVALID_ALTERNATIVE")
    if not plan["pilot_observations_excluded"]:
        reasons.append("EXPLORATORY_OBSERVATIONS_REUSED")
    for k in ("frozen_model_sha256", "analysis_code_sha256"):
        s = str(plan[k])
        if len(s)!=64 or any(c not in "0123456789abcdef" for c in s):
            reasons.append("INVALID_"+k.upper())
    try:
        alpha=float(plan["alpha"]); power=float(plan["power"])
        effect=float(plan["minimum_economically_relevant_ev"])
        std=float(plan["expected_return_stddev"])
        inflation=float(plan["dependence_inflation_factor"])
        coverage=float(plan["expected_quote_coverage"])
        fixed_n=int(plan["fixed_eligible_sample_size"])
        max_sessions=int(plan["maximum_collection_sessions"])
        if not (0<alpha<=0.05 and 0.8<=power<1 and effect>0 and std>0
                and inflation>=1 and 0<coverage<=1 and fixed_n>0 and max_sessions>0):
            reasons.append("INVALID_POWER_INPUTS")
    except (ValueError,TypeError,OverflowError):
        reasons.append("INVALID_POWER_INPUTS")
    if not (str(plan["preregistration_utc"]) < str(plan["confirmation_start_utc"])):
        reasons.append("NON_PROSPECTIVE_START")
    if reasons:
        return {"ready":False,"reasons":reasons,"required_eligible_n":None}
    # Conservative normal-approximation planning diagnostic, NOT itself
    # a reliable final block-bootstrap-based power guarantee.
    z_alpha=1.6448536269514722 if alpha==0.05 else 2.3263478740408408 if alpha==0.01 else None
    z_power=0.8416212335729143 if power==0.8 else None
    if z_alpha is None or z_power is None:
        return {"ready":False,"reasons":["ALPHA_POWER_LOOKUP_NOT_SUPPORTED"],"required_eligible_n":None}
    required_n=math.ceil(((z_alpha+z_power)*std/effect)**2*inflation)
    if fixed_n<required_n:
        reasons.append("FIXED_ELIGIBLE_N_BELOW_PLANNING_LOWER_BOUND")
    # A maximum session count cannot prove attainment; coverage estimate
    # and observed quote throughput need a separate feasibility calculation.
    return {"ready":not reasons,"reasons":reasons,"required_eligible_n":required_n,
            "planning_caveat":"Normal approximation; block dependence/power needs independent validation"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",required=True)
    parser.add_argument("--output",default="confirmation-readiness.json")
    args=parser.parse_args()
    data=json.loads(Path(args.plan).read_text(encoding="utf-8"))
    outcome=evaluate(data)
    raw=json.dumps(data,sort_keys=True,separators=(",",":")).encode()
    result={"plan_sha256":hashlib.sha256(raw).hexdigest(),**outcome}
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    if not outcome["ready"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()
