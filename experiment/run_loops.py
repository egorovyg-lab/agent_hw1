"""Run the loop experiment with local Qwen3-4B. No API or network access."""
from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from local_model import DEFAULT_MODEL_PATH, LocalQwen

ROOT = Path(__file__).parent
LOGDIR = ROOT / "logs"
MAX_STEPS = 12
TASKS = [
    f"Find the lesson about {topic} in room {room} on {date}. Return its title and time."
    for topic, room, date in [
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"), ("tools", "314", "October 13"),
        ("agents", "204", "October 12"), ("MCP", "204", "October 15"),
    ]
]
CONDITIONS = ("unstable_no_guard", "unstable_loopguard", "hint_no_guard")
EVENTS = [
    {"event_id": "class-001", "date": "2026-10-12", "start_time": "18:00", "end_time": "19:30", "title": "Agents Practicum", "room": "204", "teacher": "A. Ivanova"},
    {"event_id": "class-002", "date": "2026-10-13", "start_time": "18:00", "end_time": "19:30", "title": "Tools Seminar", "room": "314", "teacher": "I. Petrov"},
    {"event_id": "class-003", "date": "2026-10-15", "start_time": "16:00", "end_time": "17:30", "title": "MCP Lab", "room": "204", "teacher": "A. Ivanova"},
]
SYSTEM = """You are an agent that may call one local tool. Decide what to do next. Reply with exactly one line in one of these forms:
CALL schedule_search {"query":"short search words"}
FINAL short answer
Use CALL when you need schedule data; after a useful result, reply FINAL. If a tool result is empty, try a changed query. Do not write analysis or markdown fences."""


def parse_action(text: str) -> tuple[str, dict | str]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    call = re.search(r"CALL\s+schedule_search\s*(\{.*?\})", text, flags=re.DOTALL | re.IGNORECASE)
    if call:
        try:
            args = json.loads(call.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError("Исправьте JSON в вызове schedule_search.") from exc
        if not isinstance(args, dict) or not isinstance(args.get("query"), str) or not args["query"].strip():
            raise ValueError("Вызов должен содержать непустой строковый аргумент query.")
        return "call", args
    final = re.search(r"FINAL\s*:?[ \t]*(.*)", text, flags=re.DOTALL | re.IGNORECASE)
    if final:
        return "final", final.group(1).strip()
    # Accept a plain short answer as a final response rather than inventing a tool call.
    return "final", text


def detect_loop(signatures: list[str]) -> str | None:
    if len(signatures) >= 3 and signatures[-1] == signatures[-2] == signatures[-3]:
        return "three_identical"
    if len(signatures) >= 4 and signatures[-4] == signatures[-2] and signatures[-3] == signatures[-1] and signatures[-4] != signatures[-3]:
        return "ABAB"
    return None


def execute_search(task: str, query: str) -> str:
    """Synthetic local fixture for the unstable tool; no external data is contacted."""
    del query  # The fixture answer is keyed to the labeled task, to isolate retry behavior.
    if "MCP" in task:
        selected = EVENTS[2]
    elif "314" in task:
        selected = EVENTS[1]
    else:
        selected = EVENTS[0]
    return json.dumps({"events": [selected]}, ensure_ascii=False)


def run_episode(model: LocalQwen, condition: str, task_id: int, task: str, repeat: int) -> dict:
    seed = 900000 + task_id * 10 + repeat
    rng = random.Random(seed)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    signatures, steps, trace = [], [], []
    total_input_tokens = total_output_tokens = 0
    had_nonempty = False
    loop_kind = None
    status, final, error = "running", "", None
    for step in range(1, MAX_STEPS + 1):
        try:
            result = model.generate(messages, max_new_tokens=96, seed=seed + step)
            raw = result["text"]
            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]
            trace.append({"step": step, "raw_response": raw, "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"]})
            action, payload = parse_action(raw)
        except Exception as exc:
            status, error = "failed", type(exc).__name__ + ": " + str(exc)[:300]
            break
        if action == "final":
            status, final = "completed", str(payload)
            break
        signature = json.dumps({"tool": "schedule_search", "arguments": payload}, sort_keys=True, ensure_ascii=False)
        signatures.append(signature)
        steps.append({"step": step, "tool": "schedule_search", "arguments": payload})
        if condition == "unstable_loopguard" and detect_loop(signatures):
            loop_kind = detect_loop(signatures)
            status = "guard_stopped"
            break
        if rng.random() < 0.5:
            tool_result = "nothing found; try a different date" if condition == "hint_no_guard" else ""
        else:
            tool_result = execute_search(task, payload["query"])
            had_nonempty = True
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"schedule_search result: {tool_result}\nChoose another action."})
    else:
        status = "max_steps"
        loop_kind = detect_loop(signatures)
    if status == "running":
        status = "max_steps"
    loop_kind = loop_kind or detect_loop(signatures)
    return {"condition": condition, "task_id": task_id, "task": task, "repeat": repeat, "seed": seed,
            "backend": "local_transformers", "model_path": str(model.path), "status": status,
            "success": status == "completed" and had_nonempty, "loop": bool(loop_kind), "loop_kind": loop_kind,
            "tool_steps": len(steps), "steps": steps, "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens, "total_tokens": total_input_tokens + total_output_tokens,
            "final_response": final, "error": error, "raw_model_trace": trace}


def read_resume_keys(path: Path) -> set[tuple[str, int, int]]:
    if not path.is_file():
        raise SystemExit(f"Лог для продолжения не найден: {path}")
    expected = {(condition, task_id, repeat)
                for condition in CONDITIONS for task_id in range(1, len(TASKS) + 1) for repeat in range(1, 4)}
    completed: set[tuple[str, int, int]] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            key = (str(row["condition"]), int(row["task_id"]), int(row["repeat"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Некорректная запись в {path}, строка {line_no}: {exc}") from exc
        if key not in expected:
            raise SystemExit(f"Неожиданный эпизод {key} в {path}, строка {line_no}; лог не изменён.")
        if key in completed:
            raise SystemExit(f"Дубликат эпизода {key} в {path}; лог не изменён.")
        if row.get("backend") != "local_transformers":
            raise SystemExit(f"В строке {line_no} не локальная запись; лог не изменён.")
        completed.add(key)
    return completed


def main():
    ap = argparse.ArgumentParser(description="Локальный эксперимент петель на Qwen3-4B")
    ap.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH), help="Путь к локальной папке Qwen3-4B")
    ap.add_argument("--dry-run", action="store_true", help="Проверить план без загрузки Qwen")
    ap.add_argument("--limit-tasks", type=int, default=20, help="Число задач (для полного эксперимента оставьте 20)")
    ap.add_argument("--resume-log", help="Продолжить пропущенные эпизоды в указанном существующем JSONL")
    args = ap.parse_args()
    model_path = Path(args.model_path).expanduser()
    if not model_path.is_dir() or not (model_path / "config.json").exists():
        raise SystemExit(f"Локальная модель не найдена: {model_path}")
    n_tasks = min(max(args.limit_tasks, 1), len(TASKS))
    if args.resume_log and n_tasks != len(TASKS):
        raise SystemExit("Для --resume-log используйте полный набор из 20 задач; существующий лог не изменён.")

    resume_path = Path(args.resume_log).expanduser() if args.resume_log else None
    done = read_resume_keys(resume_path) if resume_path else set()
    total = n_tasks * 9
    expected = {(condition, task_id, repeat)
                for condition in CONDITIONS for task_id in range(1, n_tasks + 1) for repeat in range(1, 4)}
    remaining = expected - done
    if resume_path:
        print(f"Продолжение лога: {resume_path}; уже записано {len(done)}/180, осталось {len(remaining)}.")
        if not remaining:
            print("Все 180 эпизодов уже есть в этом логе; ничего не запускаю.")
            return
    else:
        print(f"Модель: {model_path}; локально, без API. Эпизодов: {n_tasks} задач x 3 повтора x 3 условия = {total}.")
    if args.dry_run:
        if resume_path:
            print("Будут выполнены только отсутствующие ключи:", sorted(remaining))
        else:
            print("Пробный запуск завершён; Qwen не загружалась.")
        return

    print("Загружаю локальную модель ...", flush=True)
    model = LocalQwen(model_path)
    LOGDIR.mkdir(exist_ok=True)
    if resume_path:
        path = resume_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("r+b") as log_file:
            log_file.seek(0, 2)
            if log_file.tell() > 0:
                log_file.seek(-1, 2)
                if log_file.read(1) != b"\n":
                    log_file.seek(0, 2)
                    log_file.write(b"\n")
        mode = "a"
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = LOGDIR / f"loops_local_{stamp}.jsonl"
        mode = "w"

    completed_now = 0
    with path.open(mode, encoding="utf-8") as f:
        for condition in CONDITIONS:
            for task_id, task in enumerate(TASKS[:n_tasks], 1):
                for repeat in range(1, 4):
                    key = (condition, task_id, repeat)
                    if key in done:
                        continue
                    record = run_episode(model, condition, task_id, task, repeat)
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    done.add(key)
                    completed_now += 1
                    print(f"{len(done)}/{total} {condition} task={task_id}/{n_tasks} r{repeat}: {record['status']} steps={record['tool_steps']} loop={record['loop']}", flush=True)
    print(f"Добавлено эпизодов: {completed_now}. Полный локальный лог: {path}")


if __name__ == "__main__":
    main()
