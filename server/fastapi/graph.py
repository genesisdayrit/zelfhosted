import json
from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage, SystemMessage

from tools import tools, tools_by_name

load_dotenv()


class State(TypedDict):
    """State schema for the chatbot graph."""
    messages: Annotated[list, add_messages]
    user_location: dict | None  # Optional {lat, lon} from browser geolocation
    iteration_count: int  # Track tool call iterations to prevent infinite loops
    supervisor_turns: int  # Track supervisor evaluations (capped at MAX_SUPERVISOR_TURNS)
    supervisor_decision: str | None  # "PASS" or "RETRY" from last supervisor evaluation


# Initialize the LLM with tools bound
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
llm_with_tools = llm.bind_tools(tools)

# Configuration
MAX_ITERATIONS = 8
MAX_TOOL_RESULT_LENGTH = 4000
MAX_SUPERVISOR_TURNS = 1

SYSTEM_PROMPT = """You are a helpful personal assistant with access to various tools.

Response formatting guidelines:
- Be concise and direct. No filler phrases like "I'll look that up."
- Integrate tool results naturally into your response.
- Use markdown: **bold** for emphasis, bullet lists, headers for sections.
- Do not mention tools, internal processes, or iteration counts.
- For music/video requests, give a brief response. Embeds display automatically.
- For data-heavy responses (weather, subway), use structured formatting."""

SUPERVISOR_PROMPT = """You are a response quality evaluator. Given the conversation and the assistant's latest response, determine if the response adequately addresses the user's request.

Evaluate:
1. Does the response directly answer the question asked?
2. Is the response complete (not cut off or missing key information)?
3. If tools were used, are the results properly incorporated?

Respond with ONLY one of:
- "PASS" if the response is adequate
- "RETRY" if the response needs improvement (explain briefly why after the word RETRY)

Do not provide the improved response yourself. Just evaluate."""


def preprocessor(state: State):
    """Prepare context for the chatbot. Extensibility point for future enrichment."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "preprocessor"})
    return {}


def chatbot(state: State):
    """LLM decides whether to call a tool or respond directly."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "chatbot"})
    messages = state["messages"]
    # Inject system prompt if not already present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
    return {"messages": [llm_with_tools.invoke(messages)]}


NEAR_ME_KEYWORDS = {"me", "near me", "nearby", "my location", "current location", "here"}


def _truncate(text: str) -> str:
    """Truncate tool results that exceed the maximum length."""
    if len(text) <= MAX_TOOL_RESULT_LENGTH:
        return text
    return text[:MAX_TOOL_RESULT_LENGTH] + "\n\n[Result truncated]"


def _post_process_tool_result(tool_name: str, result, writer) -> str:
    """Post-process tool results: extract embeds, truncate oversized results."""
    result_str = str(result)

    # YouTube: stream embeds, return text summary
    if tool_name == "search_youtube_song":
        try:
            result_data = json.loads(result_str)
            for video in result_data.get("videos", []):
                writer({
                    "type": "youtube_embed",
                    "video_id": video["id"],
                    "title": video["title"],
                    "channel": video.get("channel", ""),
                })
            text = result_data.get("text", result_str)
            if result_data.get("error"):
                text = result_data["error"]
            return _truncate(text)
        except json.JSONDecodeError:
            pass

    # Spotify: stream embeds, return text summary
    if tool_name == "search_spotify":
        try:
            result_data = json.loads(result_str)
            for item in result_data.get("results", []):
                writer({
                    "type": "spotify_embed",
                    "content_type": item["type"],
                    "id": item["id"],
                    "name": item["name"],
                    "artist": item.get("artist", item.get("owner", "")),
                })
            text = result_data.get("text", result_str)
            if result_data.get("error"):
                text = result_data["error"]
            return _truncate(text)
        except json.JSONDecodeError:
            pass

    return _truncate(result_str)


def tool_node(state: State):
    """Execute tool calls, post-process results, increment iteration counter."""
    writer = get_stream_writer()
    results = []
    user_location = state.get("user_location")

    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"].copy()

        # Inject user coordinates for location-aware tools
        if tool_name in ("get_nearby_subway_arrivals", "get_nearby_subway_stations"):
            location_arg = tool_args.get("location", "").lower().strip()
            if location_arg in NEAR_ME_KEYWORDS and user_location:
                tool_args["user_lat"] = user_location["lat"]
                tool_args["user_lon"] = user_location["lon"]

        if tool_name == "get_weather":
            location_arg = tool_args.get("location", "").lower().strip()
            if location_arg in NEAR_ME_KEYWORDS and user_location:
                tool_args["user_lat"] = user_location["lat"]
                tool_args["user_lon"] = user_location["lon"]

        writer({
            "type": "tool_call",
            "tool": tool_name,
            "args": tool_args,
        })

        tool_fn = tools_by_name[tool_name]
        result = tool_fn.invoke(tool_args)

        # Post-process: extract embeds, truncate oversized results
        result_for_llm = _post_process_tool_result(tool_name, result, writer)

        writer({
            "type": "tool_result",
            "tool": tool_name,
            "result": result_for_llm,
        })

        results.append(
            ToolMessage(content=result_for_llm, tool_call_id=tool_call["id"])
        )

    current_count = state.get("iteration_count", 0)
    return {
        "messages": results,
        "iteration_count": current_count + 1,
    }


def supervisor(state: State):
    """Evaluate chatbot response quality. May trigger another chatbot pass."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "supervisor"})

    messages = state["messages"]
    eval_messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        *messages,
    ]

    evaluation = llm.invoke(eval_messages)
    decision = "RETRY" if evaluation.content.strip().upper().startswith("RETRY") else "PASS"

    current_turns = state.get("supervisor_turns", 0)

    writer({
        "type": "supervisor_evaluation",
        "decision": decision,
        "detail": evaluation.content,
        "turn": current_turns + 1,
    })

    return {
        "supervisor_turns": current_turns + 1,
        "supervisor_decision": decision,
    }


def supervisor_should_continue(state: State) -> Literal["chatbot", "exit"]:
    """Route based on supervisor evaluation. Cap at MAX_SUPERVISOR_TURNS."""
    if state.get("supervisor_turns", 0) > MAX_SUPERVISOR_TURNS:
        return "exit"
    if state.get("supervisor_decision") == "RETRY":
        return "chatbot"
    return "exit"


def exit_node(state: State):
    """Finalization point. Extensibility hook for future cleanup logic."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "exit"})
    return {}


def should_continue(state: State) -> Literal["tool_node", "supervisor", "exit"]:
    """Route chatbot output: tools, supervisor review, or direct exit."""
    # Safety guard: force termination after MAX_ITERATIONS tool loops
    if state.get("iteration_count", 0) >= MAX_ITERATIONS:
        return "exit"

    last_message = state["messages"][-1]

    # If LLM wants to call tools, route to tool_node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"

    # Route to supervisor when tools were used (response synthesizes tool results)
    # and supervisor hasn't exceeded its turn cap
    if (state.get("iteration_count", 0) > 0
            and state.get("supervisor_turns", 0) <= MAX_SUPERVISOR_TURNS):
        return "supervisor"

    # Simple responses (no tools used) go straight to exit
    return "exit"


# Build the graph
graph_builder = StateGraph(State)
graph_builder.add_node("preprocessor", preprocessor)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tool_node", tool_node)
graph_builder.add_node("supervisor", supervisor)
graph_builder.add_node("exit", exit_node)

graph_builder.add_edge(START, "preprocessor")
graph_builder.add_edge("preprocessor", "chatbot")
graph_builder.add_conditional_edges("chatbot", should_continue, ["tool_node", "supervisor", "exit"])
graph_builder.add_edge("tool_node", "chatbot")
graph_builder.add_conditional_edges("supervisor", supervisor_should_continue, ["chatbot", "exit"])
graph_builder.add_edge("exit", "__end__")

graph = graph_builder.compile()

