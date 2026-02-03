import json
from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage

from tools import tools, tools_by_name

load_dotenv()


class State(TypedDict):
    """State schema for the chatbot graph with post-processor and formatter."""
    messages: Annotated[list, add_messages]
    user_location: dict | None  # Optional {lat, lon} from browser geolocation
    iteration_count: int  # Track tool call iterations to prevent infinite loops
    should_continue: bool | None  # Post-processor decision
    raw_final_response: str | None  # Store response before formatting


# Initialize LLMs
# Primary agent LLM with tools bound
agent_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
agent_llm_with_tools = agent_llm.bind_tools(tools)

# Evaluation LLM for post-processor (can be smaller/cheaper)
eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Formatter LLM for structured output (can be smaller/faster)
formatter_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Configuration
MAX_ITERATIONS = 5


def chatbot(state: State):
    """Primary LLM agent: decides whether to call tools or respond."""
    writer = get_stream_writer()
    writer({
        "type": "node_start",
        "node": "chatbot",
        "iteration": state.get("iteration_count", 0)
    })
    
    response = agent_llm_with_tools.invoke(state["messages"])
    
    return {"messages": [response]}


NEAR_ME_KEYWORDS = {"me", "near me", "nearby", "my location", "current location", "here"}


def tool_node(state: State):
    """Execute the tool calls made by the LLM."""
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
        
        # Post-process tool results
        result_for_llm = _post_process_tool_result(tool_name, result, writer)
        
        writer({
            "type": "tool_result",
            "tool": tool_name,
            "result": result_for_llm,
        })
        
        results.append(
            ToolMessage(content=result_for_llm, tool_call_id=tool_call["id"])
        )
    
    # Increment iteration count
    current_count = state.get("iteration_count", 0)
    
    return {
        "messages": results,
        "iteration_count": current_count + 1
    }


def _post_process_tool_result(tool_name: str, result: any, writer) -> str:
    """Process tool results and stream any custom events."""
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
            return result_data.get("text", result_str)
        except json.JSONDecodeError:
            return result_str
    
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
            return result_data.get("text", result_str)
        except json.JSONDecodeError:
            return result_str
    
    return result_str


def post_processor(state: State):
    """
    Evaluate whether to continue tool calling or proceed to formatting.
    This is the decision gate that prevents runaway tool loops.
    """
    writer = get_stream_writer()
    iteration_count = state.get("iteration_count", 0)
    
    # Check max iterations first (safety guard)
    if iteration_count >= MAX_ITERATIONS:
        writer({
            "type": "post_processor_decision",
            "should_continue": False,
            "reasoning": f"Reached max iterations ({MAX_ITERATIONS})",
            "iteration_count": iteration_count,
        })
        return {"should_continue": False}
    
    # Check if the last message has tool calls pending
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # LLM wants to make more tool calls - let it continue
        writer({
            "type": "post_processor_decision",
            "should_continue": True,
            "reasoning": "LLM has requested additional tool calls",
            "iteration_count": iteration_count,
        })
        return {"should_continue": True}
    
    # No tool calls pending - evaluate if we have enough information
    # Use a dedicated evaluation prompt
    evaluation_prompt = """You are evaluating whether the conversation has gathered enough information to provide a complete answer to the user's request.

Review the conversation history and determine:
1. Has sufficient information been gathered to answer the user's question?
2. Are there obvious gaps or missing details that require more tool calls?
3. Would continuing with more tool calls likely improve the answer significantly?

Respond with ONLY "CONTINUE" if more tool calls would help, or "COMPLETE" if we have enough information to answer."""
    
    eval_messages = [
        SystemMessage(content=evaluation_prompt),
        HumanMessage(content=f"Iteration count: {iteration_count}\n\nConversation:\n{state['messages']}")
    ]
    
    eval_result = eval_llm.invoke(eval_messages)
    should_continue = "CONTINUE" in eval_result.content.upper()
    
    writer({
        "type": "post_processor_decision",
        "should_continue": should_continue,
        "reasoning": eval_result.content if should_continue else "Sufficient information gathered",
        "iteration_count": iteration_count,
    })
    
    return {"should_continue": should_continue}


def formatter(state: State):
    """
    Second LLM that formats the agent's response for final output.
    Converts free-form reasoning into clean, structured responses.
    """
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "formatter"})
    
    # Get the last assistant message (the raw response)
    last_message = state["messages"][-1]
    raw_response = last_message.content if hasattr(last_message, "content") else str(last_message)
    
    # Formatting prompt
    format_prompt = """You are a response formatter. Your job is to take the agent's internal reasoning and produce a clean, helpful response for the user.

Guidelines:
- Remove any "thinking" or planning language
- Present information clearly and concisely
- Use markdown formatting when helpful (lists, bold, etc.)
- If the response references tool results, present them naturally
- Do not mention the tools or the iteration process

Format the following response:"""
    
    format_messages = [
        SystemMessage(content=format_prompt),
        HumanMessage(content=raw_response)
    ]
    
    formatted = formatter_llm.invoke(format_messages)
    
    writer({
        "type": "formatter_complete",
        "raw_length": len(raw_response),
        "formatted_length": len(formatted.content),
    })
    
    return {"raw_final_response": raw_response, "messages": [formatted]}


def route_from_chatbot(state: State) -> Literal["tool_node", "post_processor"]:
    """Route to tools if LLM made tool calls, otherwise go to post-processor."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return "post_processor"


def route_from_post_processor(state: State) -> Literal["chatbot", "formatter"]:
    """Route back to chatbot for more tool calls, or to formatter for final output."""
    should_continue = state.get("should_continue", False)
    if should_continue:
        return "chatbot"
    return "formatter"


# Build the graph
graph_builder = StateGraph(State)

# Add nodes
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tool_node", tool_node)
graph_builder.add_node("post_processor", post_processor)
graph_builder.add_node("formatter", formatter)

# Define edges
graph_builder.add_edge(START, "chatbot")

# From chatbot: either make tool calls or go to post-processor
graph_builder.add_conditional_edges(
    "chatbot",
    route_from_chatbot,
    ["tool_node", "post_processor"]
)

# From tool_node: always go to post-processor for evaluation
graph_builder.add_edge("tool_node", "post_processor")

# From post_processor: either continue loop or go to formatter
graph_builder.add_conditional_edges(
    "post_processor",
    route_from_post_processor,
    ["chatbot", "formatter"]
)

# From formatter: end the graph
graph_builder.add_edge("formatter", END)

graph = graph_builder.compile()
