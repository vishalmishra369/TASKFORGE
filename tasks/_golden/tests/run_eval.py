"""Reward = 0.0 if any pass_to_pass test fails, else the share of fail_to_pass tests that pass.

Runs the whole tests/ directory once (avoids huge argv lists) and reads per-test outcomes.
Writes /logs/verifier/reward.txt. If pytest produced no report at all, no reward is written
(null reward = environment crash, as the organisers define it).
"""
import json
import subprocess
import sys

F2P = json.load(open("/tests/fail_to_pass.json"))
P2P = json.load(open("/tests/pass_to_pass.json"))
OUT = "/tmp/report.json"

subprocess.run(
    [sys.executable, "-m", "pytest", "tests", "-p", "no:cacheprovider", "-q",
     "--continue-on-collection-errors", "--json-report", f"--json-report-file={OUT}"],
    cwd="/app",
)
try:
    rep = json.load(open(OUT))
except Exception:
    print("no pytest report produced: environment crash")
    sys.exit(1)

outcome = {t["nodeid"]: t["outcome"] for t in rep.get("tests", [])}
regressions_ok = all(outcome.get(t) == "passed" for t in P2P)
share = (sum(outcome.get(t) == "passed" for t in F2P) / len(F2P)) if F2P else 0.0
reward = share if regressions_ok else 0.0
open("/logs/verifier/reward.txt", "w").write(str(reward))
bad = [t for t in P2P if outcome.get(t) != "passed"][:10]
print(f"regressions_ok={regressions_ok} feature_share={share} reward={reward} first_regressions={bad}")
