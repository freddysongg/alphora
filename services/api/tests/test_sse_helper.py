import json

from app.api.sse import format_sse_event


def test_format_sse_event_includes_event_and_data_lines() -> None:
    output = format_sse_event(event="log", data={"message": "hello", "level": "info"})
    lines = output.splitlines()
    assert lines[0] == "event: log"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == {"message": "hello", "level": "info"}
    assert output.endswith("\n\n")


def test_format_sse_event_serializes_dates_as_strings() -> None:
    from datetime import UTC, datetime

    timestamp = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)
    output = format_sse_event(event="end", data={"at": timestamp})
    payload = json.loads(output.splitlines()[1].removeprefix("data: "))
    assert payload["at"].startswith("2026-05-15")
