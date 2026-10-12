# MCP-сервер расписания (учебный проект)

Сервер продолжает предметную область ДЗ 1: поиск информации о занятии (`room`, `time`, `teacher`). Примеры в ноутбуке ДЗ 1 содержат аудиторию `204`, время `18:00` и преподавателя `А. Иванова`. Здесь расписание — **синтетическая учебная фикстура**, а не официальные данные.

## Инструменты

| Инструмент | Назначение | Когда не использовать |
|---|---|---|
| `schedule_search` | Поиск по тексту и необязательной дате | Если известен точный `event_id`, используйте `schedule_get`; свободную аудиторию проверяйте через `schedule_room_availability`. |
| `schedule_get` | Получение занятия по точному ID | Для поиска по преподавателю используйте `schedule_by_teacher`. |
| `schedule_by_teacher` | Поиск занятий преподавателя, опционально на дату | Для поиска по курсу или аудитории используйте `schedule_search`. |
| `schedule_room_availability` | Проверка аудитории на временной интервал | Для общего поиска занятий используйте `schedule_search`. |

Все инструменты требуют явный `schedule_handle`; пользовательских сессий сервер не хранит. Для фикстуры передавайте `demo-autumn-2026`. Закрытые параметры `response_format` и `schedule_handle` объявлены через enum. Схемы входа закрыты через `additionalProperties: false`; описания есть у всех аргументов.

Сервер использует `MCPServer` из Python SDK `mcp==2.2.0`, который поддерживает MCP 2026-07-28. Прогоны Inspector выполнялись с протокольной эпохой `modern`, чтобы клиент использовал stateless-запросы.

## Установка, тесты и запуск

Требуется Python 3.10+.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python -m server.server
```

Для MCP Inspector с установленными Node.js и npm:

```powershell
npx @modelcontextprotocol/inspector --cli .\.venv\Scripts\python.exe -m server.server -- --method tools/list --protocol-era modern --strict --format json
```

Сохранённые результаты Inspector: `logs/inspector_tools_list.json`, `logs/inspector_schedule_search.json`, `logs/inspector_schedule_get_error.json`. Список инструментов прошёл strict-проверку; отдельные логи показывают успешный вызов и ошибку с подсказкой.

## Размер ответов

Счётчик измеряет токены в текстовом JSON тела ответа (`content[0].text`), не включая MCP-конверт. Использованы `tiktoken 0.14.0`, кодировка `o200k_base`. Пересчёт: `python -m scripts.measure_response_tokens`.

| Пример | Аргументы | concise | detailed |
|---|---|---:|---:|
| Поиск занятия | `schedule_search(query="агент", date="2026-10-12")` | 75 | 124 |
| Карточка занятия | `schedule_get(event_id="class-001")` | 71 | 120 |
| Проверка аудитории | `schedule_room_availability(date="2026-10-12", room="204", start_time="18:15", duration_minutes=30)` | 45 | 190 |

## Эксперимент (задача 3)

Материалы лежат в [experiment/](experiment/). Пул формируется скриптом [build_dataset.py](experiment/build_dataset.py): 100 описаний (4 инструмента сервера, 24 близких отвлекающих инструмента расписания, 72 инструмента других доменов) и 30 запросов с разметкой. Запросы на английском, поскольку выбранная локальная модель эмбеддингов `sentence-transformers/all-MiniLM-L6-v2` англоязычная. В каждом срезе N присутствуют все 4 целевых инструмента; остальные выбираются детерминированно.

Ноутбук эксперимента: [experiment.ipynb](experiment/experiment.ipynb). Обе части работают локально с моделью Qwen3-4B из `D:\qwen-spec\models\Qwen3-4B`; скрипты не используют API и не требуют ключа. Конфигурация модели подтверждена как `qwen3` / `Qwen3ForCausalLM`. На этой машине обнаружена видеокарта RTX 4050 Laptop с 6 GiB памяти; загрузчик ограничивает её бюджетом 4 GiB и переносит оставшиеся веса на CPU. При необходимости задайте `QWEN3_GPU_MEMORY` и `QWEN3_CPU_MEMORY`.

Установка и запуск из PowerShell в корне `D:\Agents_course\hw2`:

```powershell
python -m pip install -r experiment\requirements-experiment.txt
python experiment\run_selection.py --dry-run
python experiment\run_selection.py
python experiment\analyze_selection.py
python experiment\run_loops.py --dry-run
python experiment\run_loops.py
python experiment\analyze_loops.py
```

Если прогон петель прервался, продолжите его в исходный лог, указав JSONL в `--resume-log`. Скрипт сверит уже записанные `(condition, task_id, repeat)` и добавит только недостающие эпизоды. Например: `python experiment\run_loops.py --resume-log "experiment\logs\loops_local_<UTC>.jsonl" --model-path "D:\qwen-spec\models\Qwen3-4B"`. Для анализа передайте этот лог явно: `python experiment\analyze_loops.py "experiment\logs\loops_local_<UTC>.jsonl"`.

Часть A выполняет 720 локальных генераций: 30 запросов × 4 значения N × 3 повтора × 2 варианта. Вариант B показывает top-5 по cosine similarity эмбеддингов `sentence-transformers/all-MiniLM-L6-v2`; эмбеддинг и Qwen загружаются только из локальных файлов. Часть B запускает 20 задач × 3 повтора в трёх условиях. Сырые ответы модели и точные количества токенов сохраняются в `selection_local_<UTC>.jsonl` и `loops_local_<UTC>.jsonl`. Анализаторы читают только эти локальные логи и оставляют ошибки/незавершённые попытки в знаменателе.

Старые логи с префиксами `selection_<UTC>.jsonl` и `loops_<UTC>.jsonl` оставлены только в рабочей копии и не входят в архив сдачи. Итоговый двухстраничный отчёт по эксперименту: `output/pdf/agent_course_hw2_report.pdf`; его исходник — `experiment/generate_report.py`. Теория задачи 1 находится в `task1_theory.md`, описание сервера и Inspector — в этом README. ZIP для сдачи: `output/submission/hw2_submission.zip`; он содержит локальные сырые логи, код, тесты, ноутбук, результаты и PDF, без виртуального окружения и секретов.

Ограничения: выборка запросов мала и составлена вручную; близкие отвлекающие инструменты синтетические; расписание содержит три синтетических события; локальная модель частично выполняется на CPU из-за объёма весов.
