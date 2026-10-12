import anyio
import json
import pytest
from mcp import Client

from server.server import EVENTS, ScheduleHandle, mcp

HANDLE = ScheduleHandle.DEMO_AUTUMN_2026.value


def call_tool(name: str, arguments: dict):
    async def _call():
        async with Client(mcp, mode="2026-07-28") as client:
            return await client.call_tool(name, arguments)

    return anyio.run(_call)


def schema_map():
    return {tool.name: tool for tool in anyio.run(mcp.list_tools)}


def enum_values(schema, field_name: str):
    field = schema["properties"][field_name]
    if "enum" in field:
        return field["enum"]
    definition_name = field["$ref"].rsplit("/", 1)[-1]
    return schema["$defs"][definition_name]["enum"]

def payload(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(next(item.text for item in result.content if getattr(item, "text", None)))


def error_text(result) -> str:
    return " ".join(item.text for item in result.content if getattr(item, "text", None))



def test_modern_protocol_discovery_and_tools_list():
    async def _list_tools():
        async with Client(mcp, mode="2026-07-28") as client:
            return await client.list_tools()

    tools = anyio.run(_list_tools)
    tool_group = next(group for group in tools if group[0] == "tools")
    assert {tool.name for tool in tool_group[1]} == {
        "schedule_search",
        "schedule_get",
        "schedule_by_teacher",
        "schedule_room_availability",
    }


def test_tool_schemas_are_closed_and_documented():
    tools = schema_map()
    assert set(tools) == {
        "schedule_search",
        "schedule_get",
        "schedule_by_teacher",
        "schedule_room_availability",
    }
    for tool in tools.values():
        assert tool.description and "Когда не использовать" in tool.description
        assert tool.input_schema["additionalProperties"] is False
        assert tool.output_schema is None
        for property_schema in tool.input_schema["properties"].values():
            assert property_schema.get("description")
        assert enum_values(tool.input_schema, "response_format") == ["concise", "detailed"]
        assert enum_values(tool.input_schema, "schedule_handle") == [HANDLE]


def test_schedule_search_success_and_actionable_error():
    result = call_tool("schedule_search", {
        "schedule_handle": HANDLE,
        "query": "агент",
        "date": "2026-10-12",
        "response_format": "concise",
    })
    assert not result.is_error
    assert payload(result)["events"][0]["event_id"] == "class-001"
    assert "teacher" not in payload(result)["events"][0]

    error = call_tool("schedule_search", {
        "schedule_handle": HANDLE,
        "query": "агент",
        "date": "12/10/2026",
        "response_format": "concise",
    })
    assert error.is_error is True
    assert "YYYY-MM-DD" in error_text(error)


def test_schedule_get_success_and_actionable_error():
    result = call_tool("schedule_get", {
        "schedule_handle": HANDLE,
        "event_id": "class-001",
        "response_format": "detailed",
    })
    assert not result.is_error
    assert payload(result)["event"]["room"] == "204"
    assert "source" in payload(result)["event"]

    error = call_tool("schedule_get", {
        "schedule_handle": HANDLE,
        "event_id": "missing-id",
        "response_format": "detailed",
    })
    assert error.is_error is True
    assert "schedule_search" in error_text(error)
    assert "event_id" in error_text(error)


def test_schedule_by_teacher_success_and_actionable_error():
    result = call_tool("schedule_by_teacher", {
        "schedule_handle": HANDLE,
        "teacher": "иванова",
        "date": "2026-10-12",
        "response_format": "concise",
    })
    assert not result.is_error
    assert [event["event_id"] for event in payload(result)["events"]] == ["class-001"]

    error = call_tool("schedule_by_teacher", {
        "schedule_handle": HANDLE,
        "teacher": "   ",
        "date": None,
        "response_format": "concise",
    })
    assert error.is_error is True
    assert "teacher" in error_text(error)


def test_schedule_room_availability_success_and_actionable_error():
    result = call_tool("schedule_room_availability", {
        "schedule_handle": HANDLE,
        "date": "2026-10-12",
        "room": "204",
        "start_time": "18:15",
        "duration_minutes": 30,
        "response_format": "detailed",
    })
    assert not result.is_error
    assert payload(result)["available"] is False
    assert payload(result)["conflicts"][0]["event_id"] == "class-001"

    error = call_tool("schedule_room_availability", {
        "schedule_handle": HANDLE,
        "date": "2026-10-12",
        "room": "204",
        "start_time": "evening",
        "duration_minutes": 30,
        "response_format": "concise",
    })
    assert error.is_error is True
    assert "HH:MM" in error_text(error)


def test_schedule_handle_is_explicit_and_unknown_handle_is_rejected():
    error = call_tool("schedule_get", {
        "schedule_handle": "unknown-schedule",
        "event_id": "class-001",
        "response_format": "concise",
    })
    assert error.is_error is True
    assert "schedule_handle" in error_text(error) or "demo-autumn-2026" in error_text(error)


def test_fixture_matches_hw1_examples_but_is_labeled_synthetic():
    event = next(item for item in EVENTS if item["event_id"] == "class-001")
    assert event["room"] == "204"
    assert event["start_time"] == "18:00"
    assert event["teacher"] == "А. Иванова"
    assert "Синтетическая" in event["source"]







