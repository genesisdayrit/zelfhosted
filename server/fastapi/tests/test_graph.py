"""Unit tests for graph.py components.

Tests the post-processor logic (truncation, embed extraction, iteration guard,
system prompt injection) without making real LLM or tool calls.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from graph import (
    _truncate,
    _post_process_tool_result,
    should_continue,
    tool_node,
    chatbot,
    preprocessor,
    supervisor,
    supervisor_should_continue,
    exit_node,
    MAX_ITERATIONS,
    MAX_SUPERVISOR_TURNS,
    MAX_TOOL_RESULT_LENGTH,
    SYSTEM_PROMPT,
    SUPERVISOR_PROMPT,
    State,
)
from tests.conftest import FakeWriter, make_ai_message, make_state


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_exact_limit_unchanged(self):
        text = "a" * MAX_TOOL_RESULT_LENGTH
        assert _truncate(text) == text

    def test_over_limit_truncated(self):
        text = "a" * (MAX_TOOL_RESULT_LENGTH + 500)
        result = _truncate(text)
        assert len(result) < len(text)
        assert result.endswith("[Result truncated]")
        assert result.startswith("a" * 100)

    def test_empty_string(self):
        assert _truncate("") == ""


# ---------------------------------------------------------------------------
# _post_process_tool_result
# ---------------------------------------------------------------------------

class TestPostProcessToolResult:
    def test_generic_tool_passes_through(self):
        writer = FakeWriter()
        result = _post_process_tool_result("get_weather", "Sunny, 72F", writer)
        assert result == "Sunny, 72F"
        assert writer.events == []

    def test_generic_tool_truncates_long_result(self):
        writer = FakeWriter()
        long_result = "x" * (MAX_TOOL_RESULT_LENGTH + 100)
        result = _post_process_tool_result("get_weather", long_result, writer)
        assert result.endswith("[Result truncated]")

    def test_youtube_extracts_embeds(self):
        writer = FakeWriter()
        tool_result = json.dumps({
            "videos": [
                {"id": "abc123", "title": "Test Song", "channel": "TestChannel"},
                {"id": "def456", "title": "Song 2", "channel": "Ch2"},
            ],
            "text": "Found 2 videos",
        })
        result = _post_process_tool_result("search_youtube_song", tool_result, writer)
        assert result == "Found 2 videos"
        embeds = writer.events_of_type("youtube_embed")
        assert len(embeds) == 2
        assert embeds[0]["video_id"] == "abc123"
        assert embeds[1]["video_id"] == "def456"

    def test_youtube_error_returns_error_text(self):
        writer = FakeWriter()
        tool_result = json.dumps({
            "videos": [],
            "text": "Found 0 videos",
            "error": "No results found",
        })
        result = _post_process_tool_result("search_youtube_song", tool_result, writer)
        assert result == "No results found"

    def test_youtube_invalid_json_falls_through(self):
        writer = FakeWriter()
        result = _post_process_tool_result("search_youtube_song", "not json", writer)
        assert result == "not json"
        assert writer.events == []

    def test_spotify_extracts_embeds(self):
        writer = FakeWriter()
        tool_result = json.dumps({
            "results": [
                {"type": "track", "id": "sp1", "name": "Track 1", "artist": "Artist 1"},
                {"type": "album", "id": "sp2", "name": "Album 1", "artist": "Artist 2"},
            ],
            "text": "Found 2 results",
        })
        result = _post_process_tool_result("search_spotify", tool_result, writer)
        assert result == "Found 2 results"
        embeds = writer.events_of_type("spotify_embed")
        assert len(embeds) == 2
        assert embeds[0]["content_type"] == "track"
        assert embeds[1]["id"] == "sp2"

    def test_spotify_owner_fallback(self):
        writer = FakeWriter()
        tool_result = json.dumps({
            "results": [
                {"type": "playlist", "id": "pl1", "name": "My Playlist", "owner": "user123"},
            ],
            "text": "Found 1 playlist",
        })
        result = _post_process_tool_result("search_spotify", tool_result, writer)
        embeds = writer.events_of_type("spotify_embed")
        assert embeds[0]["artist"] == "user123"

    def test_spotify_invalid_json_falls_through(self):
        writer = FakeWriter()
        result = _post_process_tool_result("search_spotify", "not json", writer)
        assert result == "not json"


# ---------------------------------------------------------------------------
# should_continue
# ---------------------------------------------------------------------------

class TestShouldContinue:
    def test_routes_to_tools_when_tool_calls_present(self):
        msg = make_ai_message(tool_calls=[{"id": "1", "name": "get_weather", "args": {}}])
        state = make_state(messages=[msg])
        assert should_continue(state) == "tool_node"

    def test_routes_to_exit_when_no_tool_calls_and_no_tools_used(self):
        msg = make_ai_message(content="Hello!")
        state = make_state(messages=[msg], iteration_count=0)
        assert should_continue(state) == "exit"

    def test_routes_to_supervisor_after_tool_use(self):
        msg = make_ai_message(content="The weather is sunny.")
        state = make_state(messages=[msg], iteration_count=1, supervisor_turns=0)
        assert should_continue(state) == "supervisor"

    def test_skips_supervisor_when_turns_exceeded(self):
        msg = make_ai_message(content="Done.")
        state = make_state(messages=[msg], iteration_count=1, supervisor_turns=MAX_SUPERVISOR_TURNS + 1)
        assert should_continue(state) == "exit"

    def test_iteration_guard_stops_at_max(self):
        msg = make_ai_message(tool_calls=[{"id": "1", "name": "get_weather", "args": {}}])
        state = make_state(messages=[msg], iteration_count=MAX_ITERATIONS)
        assert should_continue(state) == "exit"

    def test_iteration_guard_allows_below_max(self):
        msg = make_ai_message(tool_calls=[{"id": "1", "name": "get_weather", "args": {}}])
        state = make_state(messages=[msg], iteration_count=MAX_ITERATIONS - 1)
        assert should_continue(state) == "tool_node"

    def test_iteration_guard_stops_above_max(self):
        msg = make_ai_message(tool_calls=[{"id": "1", "name": "get_weather", "args": {}}])
        state = make_state(messages=[msg], iteration_count=MAX_ITERATIONS + 5)
        assert should_continue(state) == "exit"

    def test_defaults_iteration_count_to_zero(self):
        """State without iteration_count should behave as count=0."""
        msg = make_ai_message(tool_calls=[{"id": "1", "name": "get_weather", "args": {}}])
        state = {"messages": [msg], "user_location": None}
        assert should_continue(state) == "tool_node"


# ---------------------------------------------------------------------------
# tool_node
# ---------------------------------------------------------------------------

class TestToolNode:
    def test_increments_iteration_count(self, mock_stream_writer):
        fake_tool = MagicMock(return_value="Sunny, 72F")
        msg = make_ai_message(tool_calls=[{"id": "call1", "name": "get_weather", "args": {"location": "NYC"}}])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 3}
            result = tool_node(state)

        assert result["iteration_count"] == 4

    def test_increments_from_zero(self, mock_stream_writer):
        fake_tool = MagicMock(return_value="result")
        msg = make_ai_message(tool_calls=[{"id": "call1", "name": "get_weather", "args": {"location": "LA"}}])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 0}
            result = tool_node(state)

        assert result["iteration_count"] == 1

    def test_returns_tool_messages(self, mock_stream_writer):
        fake_tool = MagicMock()
        fake_tool.invoke.return_value = "42 degrees"
        msg = make_ai_message(tool_calls=[{"id": "call1", "name": "get_weather", "args": {"location": "Chicago"}}])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 0}
            result = tool_node(state)

        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert result["messages"][0].content == "42 degrees"

    def test_multiple_tool_calls(self, mock_stream_writer):
        fake_weather = MagicMock(return_value="Sunny")
        fake_arxiv = MagicMock(return_value="Paper about AI")
        msg = make_ai_message(tool_calls=[
            {"id": "c1", "name": "get_weather", "args": {"location": "NYC"}},
            {"id": "c2", "name": "get_arxiv_articles", "args": {"query": "LLM"}},
        ])

        with patch.dict("graph.tools_by_name", {
            "get_weather": fake_weather,
            "get_arxiv_articles": fake_arxiv,
        }):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 1}
            result = tool_node(state)

        assert len(result["messages"]) == 2
        assert result["iteration_count"] == 2

    def test_location_injection_subway(self, mock_stream_writer):
        fake_tool = MagicMock(return_value="Station nearby")
        msg = make_ai_message(tool_calls=[{
            "id": "c1",
            "name": "get_nearby_subway_stations",
            "args": {"location": "near me"},
        }])

        with patch.dict("graph.tools_by_name", {"get_nearby_subway_stations": fake_tool}):
            state: State = {
                "messages": [msg],
                "user_location": {"lat": 40.7, "lon": -74.0},
                "iteration_count": 0,
            }
            tool_node(state)

        call_args = fake_tool.invoke.call_args[0][0]
        assert call_args["user_lat"] == 40.7
        assert call_args["user_lon"] == -74.0

    def test_location_injection_weather(self, mock_stream_writer):
        fake_tool = MagicMock(return_value="Local weather")
        msg = make_ai_message(tool_calls=[{
            "id": "c1",
            "name": "get_weather",
            "args": {"location": "nearby"},
        }])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {
                "messages": [msg],
                "user_location": {"lat": 34.0, "lon": -118.2},
                "iteration_count": 0,
            }
            tool_node(state)

        call_args = fake_tool.invoke.call_args[0][0]
        assert call_args["user_lat"] == 34.0
        assert call_args["user_lon"] == -118.2

    def test_no_location_injection_without_user_location(self, mock_stream_writer):
        fake_tool = MagicMock(return_value="Weather data")
        msg = make_ai_message(tool_calls=[{
            "id": "c1",
            "name": "get_weather",
            "args": {"location": "near me"},
        }])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 0}
            tool_node(state)

        call_args = fake_tool.invoke.call_args[0][0]
        assert "user_lat" not in call_args

    def test_streams_tool_call_and_result_events(self, mock_stream_writer):
        fake_tool = MagicMock()
        fake_tool.invoke.return_value = "result"
        msg = make_ai_message(tool_calls=[{"id": "c1", "name": "get_weather", "args": {"location": "SF"}}])

        with patch.dict("graph.tools_by_name", {"get_weather": fake_tool}):
            state: State = {"messages": [msg], "user_location": None, "iteration_count": 0}
            tool_node(state)

        call_events = mock_stream_writer.events_of_type("tool_call")
        result_events = mock_stream_writer.events_of_type("tool_result")
        assert len(call_events) == 1
        assert call_events[0]["tool"] == "get_weather"
        assert len(result_events) == 1
        assert result_events[0]["result"] == "result"


# ---------------------------------------------------------------------------
# chatbot (system prompt injection)
# ---------------------------------------------------------------------------

class TestChatbot:
    def test_injects_system_prompt(self, mock_stream_writer):
        fake_response = AIMessage(content="Hi there!")
        mock_llm = MagicMock(return_value=fake_response)

        with patch("graph.llm_with_tools", mock_llm):
            state: State = {
                "messages": [HumanMessage(content="Hello")],
                "user_location": None,
                "iteration_count": 0,
            }
            chatbot(state)

        invoked_messages = mock_llm.invoke.call_args[0][0]
        assert isinstance(invoked_messages[0], SystemMessage)
        assert invoked_messages[0].content == SYSTEM_PROMPT
        assert isinstance(invoked_messages[1], HumanMessage)

    def test_does_not_double_inject_system_prompt(self, mock_stream_writer):
        fake_response = AIMessage(content="Hi!")
        mock_llm = MagicMock(return_value=fake_response)

        with patch("graph.llm_with_tools", mock_llm):
            state: State = {
                "messages": [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content="Hello"),
                ],
                "user_location": None,
                "iteration_count": 0,
            }
            chatbot(state)

        invoked_messages = mock_llm.invoke.call_args[0][0]
        system_messages = [m for m in invoked_messages if isinstance(m, SystemMessage)]
        assert len(system_messages) == 1

    def test_returns_llm_response_in_messages(self, mock_stream_writer):
        fake_response = AIMessage(content="The answer is 42")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response

        with patch("graph.llm_with_tools", mock_llm):
            state: State = {
                "messages": [HumanMessage(content="What is the answer?")],
                "user_location": None,
                "iteration_count": 0,
            }
            result = chatbot(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "The answer is 42"

    def test_streams_node_start_event(self, mock_stream_writer):
        fake_response = AIMessage(content="Hi")
        mock_llm = MagicMock(return_value=fake_response)

        with patch("graph.llm_with_tools", mock_llm):
            state: State = {
                "messages": [HumanMessage(content="Hey")],
                "user_location": None,
                "iteration_count": 0,
            }
            chatbot(state)

        start_events = mock_stream_writer.events_of_type("node_start")
        assert len(start_events) == 1
        assert start_events[0]["node"] == "chatbot"


# ---------------------------------------------------------------------------
# preprocessor
# ---------------------------------------------------------------------------

class TestPreprocessor:
    def test_returns_empty_dict(self, mock_stream_writer):
        state = make_state(messages=[HumanMessage(content="hi")])
        result = preprocessor(state)
        assert result == {}

    def test_streams_node_start_event(self, mock_stream_writer):
        state = make_state(messages=[HumanMessage(content="hi")])
        preprocessor(state)
        start_events = mock_stream_writer.events_of_type("node_start")
        assert len(start_events) == 1
        assert start_events[0]["node"] == "preprocessor"


# ---------------------------------------------------------------------------
# supervisor
# ---------------------------------------------------------------------------

class TestSupervisor:
    def test_pass_evaluation(self, mock_stream_writer):
        fake_eval = AIMessage(content="PASS")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm):
            state = make_state(
                messages=[HumanMessage(content="weather?"), AIMessage(content="It's sunny.")],
                supervisor_turns=0,
            )
            result = supervisor(state)

        assert result["supervisor_decision"] == "PASS"
        assert result["supervisor_turns"] == 1

    def test_retry_evaluation(self, mock_stream_writer):
        fake_eval = AIMessage(content="RETRY - response is incomplete")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm):
            state = make_state(
                messages=[HumanMessage(content="weather?"), AIMessage(content="...")],
                supervisor_turns=0,
            )
            result = supervisor(state)

        assert result["supervisor_decision"] == "RETRY"
        assert result["supervisor_turns"] == 1

    def test_increments_supervisor_turns(self, mock_stream_writer):
        fake_eval = AIMessage(content="PASS")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm):
            state = make_state(
                messages=[HumanMessage(content="hi"), AIMessage(content="hello")],
                supervisor_turns=2,
            )
            result = supervisor(state)

        assert result["supervisor_turns"] == 3

    def test_uses_base_llm_not_tools(self, mock_stream_writer):
        fake_eval = AIMessage(content="PASS")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm) as patched:
            state = make_state(
                messages=[HumanMessage(content="hi"), AIMessage(content="hello")],
            )
            supervisor(state)

        patched.invoke.assert_called_once()

    def test_streams_evaluation_event(self, mock_stream_writer):
        fake_eval = AIMessage(content="PASS")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm):
            state = make_state(
                messages=[HumanMessage(content="hi"), AIMessage(content="hello")],
            )
            supervisor(state)

        eval_events = mock_stream_writer.events_of_type("supervisor_evaluation")
        assert len(eval_events) == 1
        assert eval_events[0]["decision"] == "PASS"

    def test_injects_supervisor_prompt(self, mock_stream_writer):
        fake_eval = AIMessage(content="PASS")
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_eval

        with patch("graph.llm", mock_llm):
            state = make_state(
                messages=[HumanMessage(content="hi"), AIMessage(content="hello")],
            )
            supervisor(state)

        invoked_messages = mock_llm.invoke.call_args[0][0]
        assert isinstance(invoked_messages[0], SystemMessage)
        assert invoked_messages[0].content == SUPERVISOR_PROMPT


# ---------------------------------------------------------------------------
# supervisor_should_continue
# ---------------------------------------------------------------------------

class TestSupervisorShouldContinue:
    def test_retry_routes_to_chatbot(self):
        state = make_state(supervisor_turns=1, supervisor_decision="RETRY")
        assert supervisor_should_continue(state) == "chatbot"

    def test_pass_routes_to_exit(self):
        state = make_state(supervisor_turns=1, supervisor_decision="PASS")
        assert supervisor_should_continue(state) == "exit"

    def test_exceeds_max_turns_forces_exit(self):
        state = make_state(supervisor_turns=MAX_SUPERVISOR_TURNS + 1, supervisor_decision="RETRY")
        assert supervisor_should_continue(state) == "exit"

    def test_at_max_turns_allows_decision(self):
        state = make_state(supervisor_turns=MAX_SUPERVISOR_TURNS, supervisor_decision="RETRY")
        assert supervisor_should_continue(state) == "chatbot"

    def test_none_decision_routes_to_exit(self):
        state = make_state(supervisor_turns=0, supervisor_decision=None)
        assert supervisor_should_continue(state) == "exit"


# ---------------------------------------------------------------------------
# exit_node
# ---------------------------------------------------------------------------

class TestExitNode:
    def test_returns_empty_dict(self, mock_stream_writer):
        state = make_state(messages=[AIMessage(content="done")])
        result = exit_node(state)
        assert result == {}

    def test_streams_node_start_event(self, mock_stream_writer):
        state = make_state(messages=[AIMessage(content="done")])
        exit_node(state)
        start_events = mock_stream_writer.events_of_type("node_start")
        assert len(start_events) == 1
        assert start_events[0]["node"] == "exit"
