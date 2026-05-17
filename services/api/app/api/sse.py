import json
from typing import Any


def format_sse_event(*, event: str, data: dict[str, Any]) -> str:
    """Format a single Server-Sent Event frame as a wire-format string.

    Frames follow the EventSource spec: an event name line and a data line,
    terminated by a blank line. Data is JSON-encoded so consumers can call
    `JSON.parse` directly on `MessageEvent.data`.
    """
    payload = json.dumps(data, default=str, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
