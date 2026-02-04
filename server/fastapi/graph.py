import json
from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage

from tools import tools, tools_by_name

load_dotenv()


class State(TypedDict):
    """State schema for the chatbot graph."""
    messages: Annotated[list, add_messages]
    user_location: dict | None  # Optional {lat, lon} from browser geolocation


# Initialize the LLM with tools bound
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
llm_with_tools = llm.bind_tools(tools)


def chatbot(state: State):
    """LLM decides whether to call a tool or respond directly."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "chatbot"})
    return {"messages": [llm_with_tools.invoke(state["messages"])]}


NEAR_ME_KEYWORDS = {"me", "near me", "nearby", "my location", "current location", "here"}


def tool_node(state: State):
    """Execute the tool calls made by the LLM."""
    writer = get_stream_writer()
    results = []
    user_location = state.get("user_location")
    
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"].copy()  # Copy to avoid mutating original
        
        # Inject user coordinates for location-aware tools when "near me" is requested
        if tool_name in ("get_nearby_subway_arrivals", "get_nearby_subway_stations"):
            location_arg = tool_args.get("location", "").lower().strip()
            if location_arg in NEAR_ME_KEYWORDS and user_location:
                # Replace "near me" with actual coordinates
                tool_args["user_lat"] = user_location["lat"]
                tool_args["user_lon"] = user_location["lon"]
        
        # Inject user coordinates for weather tool when "near me" is requested
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
        
        # Handle YouTube tool specially - stream embed events for each video
        result_for_llm = str(result)
        if tool_name == "search_youtube_song":
            try:
                result_data = json.loads(result)
                # Stream embed events for each video
                for video in result_data.get("videos", []):
                    writer({
                        "type": "youtube_embed",
                        "video_id": video["id"],
                        "title": video["title"],
                        "channel": video.get("channel", ""),
                    })
                # Give LLM just the text summary
                result_for_llm = result_data.get("text", str(result))
                if result_data.get("error"):
                    result_for_llm = result_data["error"]
            except json.JSONDecodeError:
                pass  # Fall back to raw result

        # Handle Spotify tool specially - stream embed events for each result
        if tool_name == "search_spotify":
            try:
                result_data = json.loads(result)
                # Stream embed events for each result
                for item in result_data.get("results", []):
                    writer({
                        "type": "spotify_embed",
                        "content_type": item["type"],
                        "id": item["id"],
                        "name": item["name"],
                        "artist": item.get("artist", item.get("owner", "")),
                    })
                # Give LLM just the text summary
                result_for_llm = result_data.get("text", str(result))
                if result_data.get("error"):
                    result_for_llm = result_data["error"]
            except json.JSONDecodeError:
                pass  # Fall back to raw result
        
        writer({
            "type": "tool_result",
            "tool": tool_name,
            "result": result_for_llm,
        })
        
        results.append(
            ToolMessage(content=result_for_llm, tool_call_id=tool_call["id"])
        )
    
    return {"messages": results}


def should_continue(state: State) -> Literal["tool_node", "__end__"]:
    """Route to tool_node if LLM made tool calls, otherwise end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return "__end__"


# Build the graph
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tool_node", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", should_continue, ["tool_node", "__end__"])
graph_builder.add_edge("tool_node", "chatbot")

graph = graph_builder.compile()

