import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage


class FakeWriter:
    """Captures stream events for assertion."""

    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)

    def events_of_type(self, event_type: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == event_type]


@pytest.fixture
def writer():
    return FakeWriter()


@pytest.fixture
def mock_stream_writer(writer):
    """Patches get_stream_writer to return our FakeWriter."""
    with patch("graph.get_stream_writer", return_value=writer):
        yield writer


def make_ai_message(content: str = "", tool_calls: list | None = None) -> AIMessage:
    """Helper to create an AIMessage with optional tool_calls."""
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg
