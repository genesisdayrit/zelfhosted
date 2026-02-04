import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
import json

from graph import graph
from models import ChatRequest, ChatResponse

app = FastAPI(
    title="Zelfhosted API",
    description="AI-powered backend for Zelfhosted",
    version="0.1.0",
)

# Default CORS origins (localhost for dev)
cors_origins = [
    "http://localhost:3000",  # Next.js dev
    "http://localhost:8081",  # Expo web dev
]

# Add additional origins from environment variable (comma-separated)
extra_origins = os.getenv("CORS_ORIGINS", "")
if extra_origins:
    cors_origins.extend([origin.strip() for origin in extra_origins.split(",")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Hello from Zelfhosted API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint using LangGraph (non-streaming)."""
    initial_state = {
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "user_location": request.location.model_dump() if request.location else None,
        "iteration_count": 0,
        "supervisor_turns": 0,
        "supervisor_decision": None,
    }
    result = graph.invoke(initial_state)
    ai_message = result["messages"][-1]
    return ChatResponse(response=ai_message.content)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint - streams tokens and graph updates."""
    initial_state = {
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "user_location": request.location.model_dump() if request.location else None,
        "iteration_count": 0,
        "supervisor_turns": 0,
        "supervisor_decision": None,
    }

    async def event_generator():
        async for mode, chunk in graph.astream(
            initial_state,
            stream_mode=["messages", "updates", "custom"],
        ):
            if mode == "custom":
                yield f"data: {json.dumps(chunk)}\n\n"

            elif mode == "messages":
                msg_chunk, metadata = chunk
                if isinstance(msg_chunk, AIMessageChunk) and msg_chunk.content:
                    event = {
                        "type": "token",
                        "content": msg_chunk.content,
                    }
                    yield f"data: {json.dumps(event)}\n\n"

            elif mode == "updates":
                for node_name, state_update in chunk.items():
                    event = {
                        "type": "node_complete",
                        "node": node_name,
                    }
                    yield f"data: {json.dumps(event)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
