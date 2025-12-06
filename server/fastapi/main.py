from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Annotated, Literal
from typing_extensions import TypedDict
import json
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage

load_dotenv()

app = FastAPI(
    title="Zelfhosted API",
    description="AI-powered backend for Zelfhosted",
    version="0.1.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Tools ---


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city and state, e.g. "San Francisco, CA"
    """
    # Fake implementation - replace with real API call later
    weather_data = {
        "San Francisco, CA": "Foggy, 58°F",
        "San Francisco": "Foggy, 58°F",
        "New York, NY": "Sunny, 72°F",
        "New York": "Sunny, 72°F",
        "Seattle, WA": "Rainy, 52°F",
        "Seattle": "Rainy, 52°F",
        "Los Angeles, CA": "Sunny, 85°F",
        "Los Angeles": "Sunny, 85°F",
        "Chicago, IL": "Windy, 65°F",
        "Chicago": "Windy, 65°F",
    }
    return weather_data.get(location, f"Weather data not available for {location}")


# Register all tools
tools = [get_weather]
tools_by_name = {t.name: t for t in tools}


# --- LangGraph Setup ---


class State(TypedDict):
    """State schema for the chatbot graph."""

    messages: Annotated[list, add_messages]


# Initialize the LLM with tools bound
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
llm_with_tools = llm.bind_tools(tools)


def chatbot(state: State):
    """LLM decides whether to call a tool or respond directly."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "chatbot"})

    return {"messages": [llm_with_tools.invoke(state["messages"])]}


def tool_node(state: State):
    """Execute the tool calls made by the LLM."""
    writer = get_stream_writer()
    results = []
    
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        # Emit tool_call event before execution
        writer({
            "type": "tool_call",
            "tool": tool_name,
            "args": tool_args,
        })
        
        # Execute the tool
        tool_fn = tools_by_name[tool_name]
        result = tool_fn.invoke(tool_args)
        
        # Emit tool_result event after execution
        writer({
            "type": "tool_result",
            "tool": tool_name,
            "result": str(result),
        })
        
        results.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
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
graph_builder.add_edge("tool_node", "chatbot")  # Loop back after tool execution

graph = graph_builder.compile()


# --- Request/Response Models ---


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


# --- Endpoints ---


@app.get("/")
async def root():
    return {"message": "Hello from Zelfhosted API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint using LangGraph (non-streaming)."""
    result = graph.invoke({"messages": [{"role": "user", "content": request.message}]})
    ai_message = result["messages"][-1]
    return ChatResponse(response=ai_message.content)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint - streams tokens and graph updates."""

    async def event_generator():
        # Stream messages (tokens), updates (node completion), and custom events
        async for mode, chunk in graph.astream(
            {"messages": [{"role": "user", "content": request.message}]},
            stream_mode=["messages", "updates", "custom"],
        ):
            if mode == "custom":
                # Custom events (like node_start) pass through directly
                yield f"data: {json.dumps(chunk)}\n\n"

            elif mode == "messages":
                # chunk is a tuple: (AIMessageChunk, metadata)
                msg_chunk, metadata = chunk
                if hasattr(msg_chunk, "content") and msg_chunk.content:
                    event = {
                        "type": "token",
                        "content": msg_chunk.content,
                    }
                    yield f"data: {json.dumps(event)}\n\n"

            elif mode == "updates":
                # chunk is a dict: {node_name: {state_updates}}
                for node_name, state_update in chunk.items():
                    event = {
                        "type": "node_complete",
                        "node": node_name,
                    }
                    yield f"data: {json.dumps(event)}\n\n"

        # Signal stream completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
