from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Annotated, Literal
from typing_extensions import TypedDict
import json
import httpx
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage, AIMessageChunk

load_dotenv()

# HTTP client for external API calls
http_client = httpx.Client(timeout=10.0)

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


def geocode_location(location: str) -> tuple[float, float, str] | None:
    """Convert a location name to coordinates using Open-Meteo Geocoding API.
    
    Returns (latitude, longitude, display_name) or None if not found.
    """
    # Clean up US-style "City, STATE" formats - try the city name first
    search_name = location
    if "," in location:
        # Extract just the city name for better geocoding results
        city_part = location.split(",")[0].strip()
        search_name = city_part
    
    response = http_client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": search_name, "count": 1, "language": "en", "format": "json"},
    )
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    if not data.get("results"):
        # If city-only search failed, try the original location string
        if search_name != location:
            response = http_client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            if response.status_code == 200:
                data = response.json()
        
        if not data.get("results"):
            return None
    
    result = data["results"][0]
    display_name = result.get("name", location)
    if result.get("admin1"):  # State/region
        display_name += f", {result['admin1']}"
    if result.get("country"):
        display_name += f", {result['country']}"
    
    return (result["latitude"], result["longitude"], display_name)


def get_weather_code_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return weather_codes.get(code, "Unknown conditions")


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city and state, e.g. "San Francisco, CA"
    """
    # First, geocode the location to get coordinates
    geo_result = geocode_location(location)
    if not geo_result:
        return f"Could not find location: {location}"
    
    lat, lon, display_name = geo_result
    
    # Fetch current weather from Open-Meteo API
    response = http_client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        },
    )
    
    if response.status_code != 200:
        return f"Error fetching weather data for {location}"
    
    data = response.json()
    current = data.get("current", {})
    
    temp = current.get("temperature_2m", "N/A")
    humidity = current.get("relative_humidity_2m", "N/A")
    weather_code = current.get("weather_code", 0)
    wind_speed = current.get("wind_speed_10m", "N/A")
    
    condition = get_weather_code_description(weather_code)
    
    return f"{display_name}: {condition}, {temp}°F, Humidity: {humidity}%, Wind: {wind_speed} mph"


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
                # chunk is a tuple: (MessageChunk, metadata)
                msg_chunk, metadata = chunk
                # Only stream AI message tokens, not tool results
                if isinstance(msg_chunk, AIMessageChunk) and msg_chunk.content:
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
