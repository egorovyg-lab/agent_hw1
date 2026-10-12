"""Summarize raw selection logs; bootstrap the 30 query IDs, not individual runs."""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
LOGDIR = ROOT / "logs"
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)


def read_logs(paths):
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"WARN malformed log line: {path}", file=sys.stderr)
    return rows


def main():
    paths = [Path(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else sorted(LOGDIR.glob("selection_local_*.jsonl"))
    rows = read_logs(paths)
    queries = json.loads((ROOT / "data/queries.json").read_text(encoding="utf-8"))
    query_ids = [q["id"] for q in queries]
    groups = defaultdict(list)
    for row in rows:
        groups[row["N"], row["arm"]].append(row)
    summaries = []
    rng = random.Random(52026)
    for n in (5, 20, 50, 100):
        for arm in ("A_all", "B_top5"):
            group = groups[n, arm]
            by_q = defaultdict(list)
            for row in group:
                by_q[row["query_id"]].append(row)
            # Any missing attempt remains in the query denominator and contributes 0.
            scores = {qid: sum(bool(r.get("correct")) for r in by_q[qid]) / 3 for qid in query_ids}
            estimate = sum(scores.values()) / len(query_ids)
            successful_calls = sum(r.get("status") == "success" for r in group)
            boot = []
            if successful_calls:
                for _ in range(10000):
                    sample = [rng.choice(query_ids) for __ in query_ids]
                    boot.append(sum(scores[x] for x in sample) / len(sample))
                boot.sort()
            tokens = [r.get("input_tokens") if isinstance(r.get("input_tokens"), (int, float)) else r.get("estimated_input_tokens")
                      for r in group if isinstance(r.get("input_tokens"), (int, float)) or isinstance(r.get("estimated_input_tokens"), (int, float))]
            # Recall is one query-level observation, repeated in each run and arm.
            r_at_5 = [int(by_q[qid][0].get("recall_at_5", 0)) for qid in query_ids if by_q[qid]]
            result = {"N": n, "arm": arm, "query_count": len(query_ids), "attempted": len(group),
                      "expected_attempts": len(query_ids) * 3, "successes": sum(r.get("status") == "success" for r in group),
                      "failed_or_missing": len(query_ids) * 3 - sum(r.get("status") == "success" for r in group),
                      "accuracy": estimate if successful_calls else None,
                      "accuracy_ci95_low": boot[249] if successful_calls else None,
                      "accuracy_ci95_high": boot[9749] if successful_calls else None,
                      "selection_evaluable": bool(successful_calls),
                      "recall_at_5": sum(r_at_5) / len(query_ids), "mean_input_tokens": sum(tokens) / (len(query_ids) * 3) if tokens else None,
                      "token_count_coverage": len(tokens), "token_denominator": len(query_ids) * 3,
                      "token_counts_exact": sum(isinstance(r.get("input_tokens"), (int, float)) for r in group)}
            summaries.append(result)
    csv_path = OUT / "selection_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=summaries[0].keys())
        w.writeheader(); w.writerows(summaries)
    (OUT / "selection_summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Read {len(rows)} attempt records from {len(paths)} log(s); expected per condition = 90.")
    for s in summaries:
        accuracy_text = (f"{s['accuracy']:.3f} [{s['accuracy_ci95_low']:.3f}, {s['accuracy_ci95_high']:.3f}]"
                         if s["selection_evaluable"] else "N/A (no successful model responses)")
        print(f"N={s['N']:3} {s['arm']:7} accuracy={accuracy_text} "
              f"Recall@5={s['recall_at_5']:.3f} input_tokens={s['mean_input_tokens']} coverage={s['token_count_coverage']}/{s['token_denominator']} "
              f"failed_or_missing={s['failed_or_missing']}")
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7.2, 4.4))
        for arm, label, marker in (("A_all", "A: all N", "o"), ("B_top5", "B: embedding top-5", "s")):
            data = [s for s in summaries if s["arm"] == arm]
            xs = [s["N"] for s in data]
            ys = [s["accuracy"] if s["accuracy"] is not None else float("nan") for s in data]
            err = [[s["accuracy"] - s["accuracy_ci95_low"] if s["accuracy"] is not None else float("nan") for s in data],
                   [s["accuracy_ci95_high"] - s["accuracy"] if s["accuracy"] is not None else float("nan") for s in data]]
            ax.errorbar(xs, ys, yerr=err, marker=marker, capsize=4, label=label)
        ax.set(xlabel="Candidate pool size N", ylabel="Tool selection accuracy", ylim=(0, 1.02), xticks=[5, 20, 50, 100])
        ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
        fig.savefig(OUT / "selection_accuracy.png", dpi=180)
        plt.close(fig)
    except ImportError:
        print("matplotlib not installed; CSV/JSON summaries are still available.")


if __name__ == "__main__":
    main()
