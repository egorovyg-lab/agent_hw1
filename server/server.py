"""Read-only MCP tools for a small, synthetic lesson schedule."""

from __future__ import annotations

from datetime import date as Date, datetime, time as Time, timedelta
from enum import Enum
from typing import Annotated, Any

from pydantic import Field
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError


class ScheduleHandle(str, Enum):
    """Explicit handle for the demo schedule dataset."""

    DEMO_AUTUMN_2026 = "demo-autumn-2026"


class ResponseFormat(str, Enum):
    """Controls how much schedule data is returned."""

    CONCISE = "concise"
    DETAILED = "detailed"


EVENTS: tuple[dict[str, str], ...] = (
    {
        "event_id": "class-001",
        "date": "2026-10-12",
        "start_time": "18:00",
        "end_time": "19:30",
        "title": "Практикум по агентам",
        "course": "Курс по агентам",
        "room": "204",
        "teacher": "А. Иванова",
        "building": "Главный корпус",
        "source": "Синтетическая учебная запись; не официальное расписание.",
    },
    {
        "event_id": "class-002",
        "date": "2026-10-13",
        "start_time": "18:00",
        "end_time": "19:30",
        "title": "Семинар по инструментам",
        "course": "Курс по агентам",
        "room": "314",
        "teacher": "И. Петров",
        "building": "Главный корпус",
        "source": "Синтетическая учебная запись; не официальное расписание.",
    },
    {
        "event_id": "class-003",
        "date": "2026-10-15",
        "start_time": "16:00",
        "end_time": "17:30",
        "title": "Лабораторная: MCP",
        "course": "Курс по агентам",
        "room": "204",
        "teacher": "А. Иванова",
        "building": "Главный корпус",
        "source": "Синтетическая учебная запись; не официальное расписание.",
    },
)

HANDLE_TO_EVENTS: dict[ScheduleHandle, tuple[dict[str, str], ...]] = {
    ScheduleHandle.DEMO_AUTUMN_2026: EVENTS,
}

mcp = MCPServer(
    name="lesson-schedule",
    version="1.0.0",
    instructions=(
        "Инструменты работают с явным schedule_handle и синтетическим учебным расписанием. "
        "Используйте schedule_search для поиска, затем schedule_get для точной записи. "
        "Синтетические данные не подтверждают реальное расписание."
    ),
)


def _events_for(handle: ScheduleHandle) -> tuple[dict[str, str], ...]:
    events = HANDLE_TO_EVENTS.get(handle)
    if events is None:
        raise ToolError(
            "Неизвестный schedule_handle. Используйте доступный handle "
            "'demo-autumn-2026' или передайте handle из источника расписания."
        )
    return events


def _parse_date(value: str | None) -> Date | None:
    if value is None:
        return None
    try:
        return Date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError("Исправьте date: укажите дату в формате YYYY-MM-DD.") from None


def _event_view(event: dict[str, str], response_format: ResponseFormat) -> dict[str, str]:
    if response_format == ResponseFormat.CONCISE:
        keys = ("event_id", "date", "start_time", "end_time", "title", "room")
    else:
        keys = tuple(event)
    return {key: event[key] for key in keys}


def _format_events(events: list[dict[str, str]], response_format: ResponseFormat) -> dict[str, Any]:
    return {"events": [_event_view(event, response_format) for event in events]}


def _matches_query(event: dict[str, str], query: str) -> bool:
    needle = query.strip().casefold()
    if not needle:
        raise ToolError("Исправьте query: передайте непустые слова для поиска.")
    searchable = " ".join(event[k] for k in ("title", "course", "teacher", "room", "building"))
    return needle in searchable.casefold()


@mcp.tool(structured_output=False)
def schedule_search(
    schedule_handle: Annotated[
        ScheduleHandle,
        Field(description="Явный handle набора расписания; передавайте demo-autumn-2026 для учебной фикстуры."),
    ],
    query: Annotated[
        str,
        Field(description="Непустой текст для поиска в названии, курсе, преподавателе, аудитории или корпусе; не используйте вместо точного event_id.", min_length=1),
    ],
    date: Annotated[
        str | None,
        Field(description="Необязательный фильтр даты в формате YYYY-MM-DD; не указывайте здесь время занятия."),
    ] = None,
    response_format: Annotated[
        ResponseFormat,
        Field(description="concise для краткого списка; detailed — когда нужны все поля и источник записи."),
    ] = ResponseFormat.CONCISE,
) -> dict[str, Any]:
    """Найдите занятия по тексту и, при необходимости, дате. Когда не использовать: если уже известен точный event_id — вызовите schedule_get; для свободной аудитории вызовите schedule_room_availability."""
    target_date = _parse_date(date)
    events = _events_for(schedule_handle)
    matches = [
        event
        for event in events
        if _matches_query(event, query) and (target_date is None or event["date"] == target_date.isoformat())
    ]
    return _format_events(matches, response_format)


@mcp.tool(structured_output=False)
def schedule_get(
    schedule_handle: Annotated[
        ScheduleHandle,
        Field(description="Явный handle набора расписания; передавайте demo-autumn-2026 для учебной фикстуры."),
    ],
    event_id: Annotated[
        str,
        Field(description="Точный идентификатор события, полученный из schedule_search; не передавайте название занятия вместо ID.", min_length=1),
    ],
    response_format: Annotated[
        ResponseFormat,
        Field(description="concise для основных полей; detailed — когда нужны преподаватель, курс, корпус и источник."),
    ] = ResponseFormat.DETAILED,
) -> dict[str, Any]:
    """Получите одну запись занятия по точному идентификатору. Когда не использовать: для поиска по теме или преподавателю используйте schedule_search или schedule_by_teacher."""
    events = _events_for(schedule_handle)
    for event in events:
        if event["event_id"] == event_id.strip():
            return {"event": _event_view(event, response_format)}
    raise ToolError(
        f"Событие '{event_id}' не найдено. Сначала вызовите schedule_search и скопируйте event_id из результата."
    )


@mcp.tool(structured_output=False)
def schedule_by_teacher(
    schedule_handle: Annotated[
        ScheduleHandle,
        Field(description="Явный handle набора расписания; передавайте demo-autumn-2026 для учебной фикстуры."),
    ],
    teacher: Annotated[
        str,
        Field(description="Имя или часть имени преподавателя; не используйте для поиска по названию курса.", min_length=1),
    ],
    date: Annotated[
        str | None,
        Field(description="Необязательная дата в формате YYYY-MM-DD; не задавайте диапазон этим полем."),
    ] = None,
    response_format: Annotated[
        ResponseFormat,
        Field(description="concise для краткого списка; detailed — когда нужны все поля и источники записей."),
    ] = ResponseFormat.CONCISE,
) -> dict[str, Any]:
    """Найдите занятия преподавателя. Когда не использовать: для поиска по названию или аудитории используйте schedule_search; для конкретного события по ID используйте schedule_get."""
    target_date = _parse_date(date)
    events = _events_for(schedule_handle)
    needle = teacher.strip().casefold()
    if not needle:
        raise ToolError("Исправьте teacher: укажите непустое имя или часть имени преподавателя.")
    matches = [
        event
        for event in events
        if needle in event["teacher"].casefold()
        and (target_date is None or event["date"] == target_date.isoformat())
    ]
    return _format_events(matches, response_format)


@mcp.tool(structured_output=False)
def schedule_room_availability(
    schedule_handle: Annotated[
        ScheduleHandle,
        Field(description="Явный handle набора расписания; передавайте demo-autumn-2026 для учебной фикстуры."),
    ],
    date: Annotated[
        str,
        Field(description="Дата проверки в формате YYYY-MM-DD; не передавайте диапазон дат.", min_length=1),
    ],
    room: Annotated[
        str,
        Field(description="Точный номер или обозначение аудитории; для поиска по корпусу используйте schedule_search.", min_length=1),
    ],
    start_time: Annotated[
        str,
        Field(description="Начало проверяемого интервала в местном времени, формате HH:MM.", min_length=1),
    ],
    duration_minutes: Annotated[
        int,
        Field(description="Длительность интервала в минутах; должна быть положительным числом.", gt=0),
    ],
    response_format: Annotated[
        ResponseFormat,
        Field(description="concise для статуса занятости; detailed — когда нужны конфликтующие события и их источники."),
    ] = ResponseFormat.CONCISE,
) -> dict[str, Any]:
    """Проверьте, занята ли аудитория в указанном интервале. Когда не использовать: для просмотра всех занятий комнаты или поиска курса используйте schedule_search."""
    parsed_date = _parse_date(date)
    try:
        start = Time.fromisoformat(start_time)
    except (TypeError, ValueError):
        raise ToolError("Исправьте start_time: используйте местное время в формате HH:MM, например 18:00.") from None
    if start.second or start.microsecond:
        raise ToolError("Исправьте start_time: укажите время с точностью до минуты в формате HH:MM.")
    room_name = room.strip()
    if not room_name:
        raise ToolError("Исправьте room: передайте непустой номер или обозначение аудитории.")
    start_at = datetime.combine(parsed_date, start)
    end_at = start_at + timedelta(minutes=duration_minutes)
    conflicts: list[dict[str, str]] = []
    for event in _events_for(schedule_handle):
        if event["date"] != parsed_date.isoformat() or event["room"].casefold() != room_name.casefold():
            continue
        event_start = datetime.combine(parsed_date, Time.fromisoformat(event["start_time"]))
        event_end = datetime.combine(parsed_date, Time.fromisoformat(event["end_time"]))
        if start_at < event_end and event_start < end_at:
            conflicts.append(event)
    available = not conflicts
    result: dict[str, Any] = {
        "date": parsed_date.isoformat(),
        "room": room_name,
        "start_time": start.isoformat(timespec="minutes"),
        "duration_minutes": duration_minutes,
        "available": available,
    }
    if response_format == ResponseFormat.DETAILED:
        result["conflicts"] = [_event_view(event, ResponseFormat.DETAILED) for event in conflicts]
        result["source_note"] = "Проверка выполнена только по синтетической учебной фикстуре."
    return result


# MCPServer derives these schemas from the typed function signatures. Close each
# top-level object so clients do not advertise support for arbitrary arguments.
_TOOL_NAMES = (
    "schedule_search",
    "schedule_get",
    "schedule_by_teacher",
    "schedule_room_availability",
)
for _name in _TOOL_NAMES:
    _registered = mcp._tool_manager.get_tool(_name)
    if _registered is None:  # pragma: no cover - protects import-time registration
        raise RuntimeError(f"Tool registration failed: {_name}")
    _registered.parameters["additionalProperties"] = False


if __name__ == "__main__":
    mcp.run(transport="stdio")

