"""Run local Qwen3-4B tool selection; this script makes no network/API calls."""
from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from local_model import DEFAULT_MODEL_PATH, LocalQwen

ROOT = Path(__file__).parent
TOOLS = json.loads((ROOT / "data/tools.json").read_text(encoding="utf-8"))
QUERIES = json.loads((ROOT / "data/queries.json").read_text(encoding="utf-8"))
NS = (5, 20, 50, 100)
REPEATS = 3
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def embedder():
    """Load cached English MiniLM; local_files_only prevents network access."""
    try:
        from transformers import AutoModel, AutoTokenizer
        import torch
    except ImportError as exc:
        raise RuntimeError("Install experiment/requirements-experiment.txt first.") from exc
    tok = AutoTokenizer.from_pretrained(EMBEDDING_MODEL, local_files_only=True)
    model = AutoModel.from_pretrained(EMBEDDING_MODEL, local_files_only=True).eval()

    def encode(texts: list[str]):
        with torch.no_grad():
            batch = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
            out = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1)
            vecs = (out * mask).sum(1) / mask.sum(1).clamp(min=1)
            vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)
            return vecs.cpu().numpy()
    return encode


def select_tool(model: LocalQwen, query: str, candidates: list[dict], *, seed: int) -> dict:
    compact = "\n".join(f"{c['name']}: {c['description']}" for c in candidates)
    messages = [
        {"role": "system", "content": "Choose the single best tool for the user's request. Return only its exact name from the list, without explanation. If uncertain, still choose the closest listed tool."},
        {"role": "user", "content": f"Request: {query}\n\nAvailable tools:\n{compact}\n\nBest tool:"},
    ]
    result = model.generate(messages, max_new_tokens=24, seed=seed)
    raw = result["text"]
    names = {c["name"] for c in candidates}
    matches = re.findall(r"[A-Za-z][A-Za-z0-9_]*", raw)
    answer = next((item for item in matches if item in names), "")
    return {"answer": answer, "raw_response": raw, "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"]}


def main():
    ap = argparse.ArgumentParser(description="Локальный эксперимент выбора инструмента на Qwen3-4B")
    ap.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH), help="Путь к локальной папке Qwen3-4B")
    ap.add_argument("--dry-run", action="store_true", help="Проверить план и локальные файлы эмбеддингов без запуска Qwen")
    ap.add_argument("--limit", type=int, default=30, help="Число запросов (для полного эксперимента оставьте 30)")
    args = ap.parse_args()
    model_path = Path(args.model_path).expanduser()
    if not model_path.is_dir() or not (model_path / "config.json").exists():
        raise SystemExit(f"Локальная модель не найдена: {model_path}")

    encode = embedder()
    tool_vecs = encode([f"{x['name']}. {x['description']}" for x in TOOLS])
    core = [x for x in TOOLS if x["kind"] == "gold"]
    if len(core) != 4:
        raise SystemExit(f"Ожидалось ровно 4 целевых инструмента, найдено {len(core)}")
    rng = random.Random(20261011)
    candidates_by_qn = {}
    for q in QUERIES[:args.limit]:
        negs = [x for x in TOOLS if x["kind"] != "gold"]
        rng.shuffle(negs)
        for n in NS:
            candidates_by_qn[q["id"], n] = core + negs[:n - len(core)]
    total = len(QUERIES[:args.limit]) * len(NS) * REPEATS * 2
    if args.dry_run:
        print(f"Локальная модель: {model_path}")
        print(f"План: {len(QUERIES[:args.limit])} запросов x 4 N x 3 повтора x 2 варианта = {total} генераций Qwen")
        print(f"Эмбеддинги: {len(tool_vecs)} x {tool_vecs.shape[1]}; API-вызовы: 0")
        return

    print(f"Загружаю локальную модель {model_path} ...", flush=True)
    model = LocalQwen(model_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = ROOT / "logs" / f"selection_local_{stamp}.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    call_no = 0
    with log_path.open("w", encoding="utf-8") as log:
        for q_idx, q in enumerate(QUERIES[:args.limit]):
            qvec = encode([q["query"]])[0]
            for n in NS:
                candidates = candidates_by_qn[q["id"], n]
                indexes = [TOOLS.index(c) for c in candidates]
                sims = tool_vecs[indexes] @ qvec
                top_indices = sorted(range(len(candidates)), key=lambda i: float(sims[i]), reverse=True)[:5]
                retrieved = [candidates[i] for i in top_indices]
                recall5 = int(q["gold_tool"] in {x["name"] for x in retrieved})
                for arm, shown in (("A_all", candidates), ("B_top5", retrieved)):
                    for rep in range(1, REPEATS + 1):
                        call_no += 1
                        rec = {"query_id": q["id"], "query": q["query"], "gold_tool": q["gold_tool"], "N": n,
                               "arm": arm, "repeat": rep, "shown_tools": [x["name"] for x in shown],
                               "retrieval_top5": [x["name"] for x in retrieved], "recall_at_5": recall5,
                               "status": "pending", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                               "backend": "local_transformers", "model_path": str(model.path),
                               "embedding_model": EMBEDDING_MODEL}
                        try:
                            output = select_tool(model, q["query"], shown, seed=20261011 + q_idx * 10000 + n * 100 + (0 if arm == "A_all" else 50) + rep)
                            rec.update(status="success", answer=output["answer"], raw_response=output["raw_response"],
                                       correct=output["answer"] == q["gold_tool"], input_tokens=output["input_tokens"],
                                       output_tokens=output["output_tokens"])
                        except Exception as exc:
                            rec.update(status="failed", error=type(exc).__name__ + ": " + str(exc)[:400])
                        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        log.flush()
                        print(f"{call_no}/{total} {q['id']} N={n} {arm} r{rep}: {rec['status']}", flush=True)
    print(f"Сырой локальный лог: {log_path}")


if __name__ == "__main__":
    main()
