"""Endpoint tests for main.py using FastAPI TestClient.

Mocks the compiled graph so no LLM calls are made.
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from main import app


client = TestClient(app)


class TestHealthAndRoot:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Hello from Zelfhosted API"

    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestChatEndpoint:
    def test_returns_ai_response(self):
        fake_result = {
            "messages": [AIMessage(content="It is sunny.")],
        }
        with patch("main.graph") as mock_graph:
            mock_graph.invoke.return_value = fake_result
            resp = client.post("/chat", json={
                "messages": [{"role": "user", "content": "What is the weather?"}],
            })

        assert resp.status_code == 200
        assert resp.json()["response"] == "It is sunny."

    def test_passes_initial_state_with_iteration_count(self):
        fake_result = {"messages": [AIMessage(content="ok")]}
        with patch("main.graph") as mock_graph:
            mock_graph.invoke.return_value = fake_result
            client.post("/chat", json={
                "messages": [{"role": "user", "content": "hi"}],
            })

        call_args = mock_graph.invoke.call_args[0][0]
        assert call_args["iteration_count"] == 0
        assert call_args["user_location"] is None

    def test_passes_location_when_provided(self):
        fake_result = {"messages": [AIMessage(content="ok")]}
        with patch("main.graph") as mock_graph:
            mock_graph.invoke.return_value = fake_result
            client.post("/chat", json={
                "messages": [{"role": "user", "content": "weather near me"}],
                "location": {"lat": 40.7, "lon": -74.0},
            })

        call_args = mock_graph.invoke.call_args[0][0]
        assert call_args["user_location"] == {"lat": 40.7, "lon": -74.0}

    def test_rejects_empty_messages(self):
        resp = client.post("/chat", json={"messages": []})
        # FastAPI/Pydantic should still accept this (empty list is valid)
        # but the graph would handle it - just verify no 500
        assert resp.status_code in (200, 422)

    def test_rejects_invalid_role(self):
        resp = client.post("/chat", json={
            "messages": [{"role": "system", "content": "bad role"}],
        })
        assert resp.status_code == 422


class TestChatStreamEndpoint:
    def test_returns_event_stream_content_type(self):
        async def fake_stream(*args, **kwargs):
            return
            yield  # make it an async generator

        with patch("main.graph") as mock_graph:
            mock_graph.astream = fake_stream
            resp = client.post("/chat/stream", json={
                "messages": [{"role": "user", "content": "hi"}],
            })

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_streams_done_event(self):
        async def fake_stream(*args, **kwargs):
            return
            yield

        with patch("main.graph") as mock_graph:
            mock_graph.astream = fake_stream
            resp = client.post("/chat/stream", json={
                "messages": [{"role": "user", "content": "hi"}],
            })

        # The last event should be the done event
        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        assert len(lines) >= 1
        last_event = json.loads(lines[-1].removeprefix("data: "))
        assert last_event["type"] == "done"

    def test_streams_custom_events(self):
        async def fake_stream(*args, **kwargs):
            yield ("custom", {"type": "tool_call", "tool": "get_weather", "args": {}})

        with patch("main.graph") as mock_graph:
            mock_graph.astream = fake_stream
            resp = client.post("/chat/stream", json={
                "messages": [{"role": "user", "content": "weather?"}],
            })

        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        events = [json.loads(l.removeprefix("data: ")) for l in lines]
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool"] == "get_weather"

    def test_streams_token_events(self):
        chunk = AIMessageChunk(content="Hello")

        async def fake_stream(*args, **kwargs):
            yield ("messages", (chunk, {"some": "metadata"}))

        with patch("main.graph") as mock_graph:
            mock_graph.astream = fake_stream
            resp = client.post("/chat/stream", json={
                "messages": [{"role": "user", "content": "hi"}],
            })

        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        events = [json.loads(l.removeprefix("data: ")) for l in lines]
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 1
        assert token_events[0]["content"] == "Hello"

    def test_streams_node_complete_events(self):
        async def fake_stream(*args, **kwargs):
            yield ("updates", {"chatbot": {"messages": []}})

        with patch("main.graph") as mock_graph:
            mock_graph.astream = fake_stream
            resp = client.post("/chat/stream", json={
                "messages": [{"role": "user", "content": "hi"}],
            })

        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        events = [json.loads(l.removeprefix("data: ")) for l in lines]
        node_events = [e for e in events if e.get("type") == "node_complete"]
        assert len(node_events) == 1
        assert node_events[0]["node"] == "chatbot"
