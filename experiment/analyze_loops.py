"""Summarize local loop episodes, including inference failures and unfinished episodes."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else sorted((ROOT / "logs").glob("loops_local_*.jsonl"))
rows = []
for path in paths:
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN malformed row in {path}")
summaries = []
for condition in ("unstable_no_guard", "unstable_loopguard", "hint_no_guard"):
    group = [r for r in rows if r["condition"] == condition]
    n = len(group)
    failures = sum(r.get("status") == "failed" for r in group)
    valid_episodes = max(0, n - failures)
    loops = sum(bool(r.get("loop")) for r in group)
    summaries.append({
        "condition": condition, "episodes_expected": 60, "episodes_logged": n,
        "failed_or_incomplete": sum(r.get("status") not in ("completed", "guard_stopped", "max_steps") for r in group) + max(0, 60 - n),
        "valid_episodes": valid_episodes, "evaluable": valid_episodes > 0,
        "loop_episodes": loops, "loop_rate": loops / 60 if valid_episodes else None,
        "mean_tool_steps": sum(int(r.get("tool_steps", 0)) for r in group) / 60 if valid_episodes else None,
        "mean_total_tokens": sum(int(r.get("total_tokens", 0)) for r in group) / 60 if valid_episodes else None,
        "successes": sum(bool(r.get("success")) for r in group), "success_rate": sum(bool(r.get("success")) for r in group) / 60,
        "guard_stops": sum(r.get("status") == "guard_stopped" for r in group),
        "three_identical": sum(r.get("loop_kind") == "three_identical" for r in group),
        "ABAB": sum(r.get("loop_kind") == "ABAB" for r in group),
        "runtime_failures": failures,
        "max_steps_episodes": sum(r.get("status") == "max_steps" for r in group),
    })
out = ROOT / "results"
out.mkdir(exist_ok=True)
with (out / "loop_summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=summaries[0].keys()); w.writeheader(); w.writerows(summaries)
(out / "loop_summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Read {len(rows)} episodes from {len(paths)} log(s); expected 60 per condition. Failed and unfinished episodes remain in the success denominator.")
for s in summaries:
    if not s["evaluable"]:
        print(f"{s['condition']:20} NOT EVALUABLE: {s['runtime_failures']}/60 local inference failures before any usable agent episode; do not interpret loop/step/token metrics.")
    else:
        missing = max(0, 60 - s['episodes_logged'])
        print(f"{s['condition']:20} logged={s['episodes_logged']:2}/60 missing={missing:2} valid={s['valid_episodes']:2} loops={s['loop_episodes']:2} ({s['loop_rate']:.3f}) steps={s['mean_tool_steps']:.2f} tokens={s['mean_total_tokens']:.1f} success={s['successes']}/60 ({s['success_rate']:.3f}) failed={s['runtime_failures']} unfinished={s['max_steps_episodes']}")
