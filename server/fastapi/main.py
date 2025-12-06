from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Annotated
from typing_extensions import TypedDict
import json
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI

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


# --- LangGraph Setup ---


class State(TypedDict):
    """State schema for the chatbot graph."""

    messages: Annotated[list, add_messages]


# Initialize the LLM with streaming enabled
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)


def chatbot(state: State):
    """Process messages through the LLM."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "chatbot"})

    return {"messages": [llm.invoke(state["messages"])]}


# Build the graph
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", END)
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
