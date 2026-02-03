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
    version="0.2.0",
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
        "should_continue": None,
        "raw_final_response": None,
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
        "should_continue": None,
        "raw_final_response": None,
    }

    async def event_generator():
        iteration_count = 0
        
        async for mode, chunk in graph.astream(
            initial_state,
            stream_mode=["messages", "updates", "custom"],
        ):
            if mode == "custom":
                # Pass through custom events (node_start, tool_call, etc.)
                event_type = chunk.get("type", "")
                
                # Track iteration count from events
                if event_type == "node_start" and chunk.get("node") == "chatbot":
                    iteration_count = chunk.get("iteration", 0)
                
                # Handle post-processor decision event
                if event_type == "post_processor_decision":
                    yield f"data: {json.dumps({
                        "type": "decision",
                        "continue": chunk.get("should_continue"),
                        "reasoning": chunk.get("reasoning"),
                        "iteration": chunk.get("iteration_count"),
                    })}\n\n"
                    continue
                
                # Handle formatter completion
                if event_type == "formatter_complete":
                    yield f"data: {json.dumps({
                        "type": "formatting_complete",
                        "raw_length": chunk.get("raw_length"),
                        "formatted_length": chunk.get("formatted_length"),
                    })}\n\n"
                    continue
                
                # Pass through other custom events (youtube_embed, spotify_embed, etc.)
                yield f"data: {json.dumps(chunk)}\n\n"

            elif mode == "messages":
                msg_chunk, metadata = chunk
                if isinstance(msg_chunk, AIMessageChunk) and msg_chunk.content:
                    event = {
                        "type": "token",
                        "content": msg_chunk.content,
                        "iteration": iteration_count,
                    }
                    yield f"data: {json.dumps(event)}\n\n"

            elif mode == "updates":
                for node_name, state_update in chunk.items():
                    event = {
                        "type": "node_complete",
                        "node": node_name,
                        "iteration": iteration_count,
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
