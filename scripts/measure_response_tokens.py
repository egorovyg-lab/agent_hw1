"""Count MCP tool response text with a reproducible tokenizer."""

from __future__ import annotations

import anyio
import tiktoken
from mcp import Client

from server.server import mcp

EXAMPLES = [
    (
        "Search for the next agent practice",
        "schedule_search",
        {
            "schedule_handle": "demo-autumn-2026",
            "query": "агент",
            "date": "2026-10-12",
        },
    ),
    (
        "Get event class-001",
        "schedule_get",
        {
            "schedule_handle": "demo-autumn-2026",
            "event_id": "class-001",
        },
    ),
    (
        "Check room 204 at 18:15 for 30 minutes",
        "schedule_room_availability",
        {
            "schedule_handle": "demo-autumn-2026",
            "date": "2026-10-12",
            "room": "204",
            "start_time": "18:15",
            "duration_minutes": 30,
        },
    ),
]


async def main() -> None:
    encoding = tiktoken.get_encoding("o200k_base")
    async with Client(mcp) as client:
        for label, tool_name, base_args in EXAMPLES:
            counts = {}
            for response_format in ("concise", "detailed"):
                result = await client.call_tool(
                    tool_name,
                    {**base_args, "response_format": response_format},
                )
                if result.is_error:
                    raise RuntimeError(f"Unexpected tool error for {label}: {result.content}")
                text = next(item.text for item in result.content if getattr(item, "text", None))
                counts[response_format] = len(encoding.encode(text))
            print(f"{label}: concise={counts['concise']}, detailed={counts['detailed']}")


if __name__ == "__main__":
    anyio.run(main)

