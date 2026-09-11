"""Headless runner for the ten versioned Developer Lab golden scenarios."""
import argparse, json, os, sys, time, urllib.request

LAB=os.getenv("DEVELOPER_LAB_URL","http://developer-lab:3100")

def request(path,method="GET",body=None):
    raw=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(LAB+path,data=raw,method=method,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response: return json.loads(response.read())

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("scenario",nargs="?",default="all"); parser.add_argument("--steps",type=int,default=30); args=parser.parse_args()
    scenarios=request("/api/developer-lab/scenarios")["scenarios"]
    selected=scenarios if args.scenario=="all" else [row for row in scenarios if row["id"]==args.scenario]
    if not selected: raise SystemExit("Unknown golden scenario")
    failed=0
    for scenario in selected:
        run=request("/api/developer-lab/runs","POST",{"scenario_id":scenario["id"],"seed":8124})
        request(f"/api/developer-lab/runs/{run['id']}/speed","POST",{"speed":300})
        for _ in range(args.steps): request(f"/api/developer-lab/runs/{run['id']}/step","POST",{}); time.sleep(.02)
        assertions=request(f"/api/developer-lab/runs/{run['id']}/assertions")
        evaluated=request("/api/developer-lab/assertions/evaluate","POST",{"run_id":run["id"],"scenario_id":scenario["id"],"started_at":run["started_at"],"assertions":assertions["assertions"]})
        request(f"/api/developer-lab/runs/{run['id']}/assertions","POST",{"updates":evaluated["updates"]})
        result=request(f"/api/developer-lab/runs/{run['id']}/assertions")["result"]
        status=("FAIL" if result["assertions_failed"] else
                "INCOMPLETE" if result["assertions_waiting"] else "PASS")
        failed += status != "PASS"
        print(f"{scenario['code']} {scenario['name']:<42} {status}  passed={result['assertions_passed']} waiting={result['assertions_waiting']} failed={result['assertions_failed']}")
    raise SystemExit(1 if failed else 0)

if __name__=="__main__": main()
