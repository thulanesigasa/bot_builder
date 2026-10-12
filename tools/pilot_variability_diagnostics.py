"""Read-only pilot variability diagnostics. Never qualifies trading profitability."""
import argparse, json, math, sqlite3, statistics
from collections import defaultdict
from pathlib import Path

def analyze(directory):
    path=Path(directory)
    grouped=defaultdict(list); totals=[]
    for i in range(1,5):
        source=path/f"session_{i}.db"
        economic=path/f"session_{i}_economics.json"
        if not source.is_file() or not economic.is_file():
            raise ValueError(f"Missing pilot artifact for session {i}")
        detail=json.loads(economic.read_text(encoding="utf-8"))[0]["sessions"][0]
        ids=detail["strict_eligible_observation_ids"]
        totals.append({"session":i,"committed":detail["committed"],
                       "resolved":detail["resolved"],"strict_eligible":len(ids)})
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro",uri=True) as conn:
            conn.row_factory=sqlite3.Row
            for oid in ids:
                row=conn.execute("SELECT contract_type,duration_ticks,hypothetical_return,observed_outcome,ask_price,total_payout,predicted_prob FROM forward_observations WHERE observation_id=?",(oid,)).fetchone()
                if row is None or row["hypothetical_return"] is None:
                    raise ValueError("Missing resolved strict observation: "+oid)
                expected=float(row["observed_outcome"])*float(row["total_payout"])-float(row["ask_price"])
                if abs(float(row["hypothetical_return"])-expected)>1e-4:
                    raise ValueError("Economic mismatch: "+oid)
                key=(row["contract_type"],row["duration_ticks"])
                grouped[key].append((i,expected,float(row["predicted_prob"])*float(row["total_payout"])-float(row["ask_price"])))
    groups=[]
    for (direction,duration),v in sorted(grouped.items()):
        returns=[a for _,a,_ in v]
        session_means=[statistics.mean(a for j,a,_ in v if j==i) for i in range(1,5)]
        groups.append({"contract":direction,"duration_ticks":duration,"priced_n":len(v),
            "mean_return":statistics.mean(returns),
            "sample_return_sd":statistics.stdev(returns) if len(returns)>1 else None,
            "session_means":session_means,
            "mean_predicted_ev":statistics.mean(p for _,_,p in v),
            "zero_wins":all(a<0 for a in returns)})
    return {"source":"four-session strictly priced resolved pilot records","sessions":totals,"groups":groups,
      "confirmation_ready":False,
      "power_diagnostic":"NOT_ESTIMABLE: only four consecutive sessions; overlapping contracts, 5-tick zero-win groups and potential serial dependence prevent defensible precision, independence or powered-sample inference",
      "verdict":"NO_VALIDATED_POSITIVE_EV_EDGE"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pilot-dir",required=True)
    p.add_argument("--output",default="pilot-variability.json")
    args=p.parse_args()
    result=analyze(args.pilot_dir)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("PILOT_VARIABILITY",json.dumps({"groups":len(result["groups"]),"priced_n":sum(x["priced_n"] for x in result["groups"]),"confirmation_ready":False}))
if __name__=="__main__":
    main()
