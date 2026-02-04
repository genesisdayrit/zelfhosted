from pydantic import BaseModel
from typing import Literal


class Location(BaseModel):
    lat: float
    lon: float


class MessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[MessageItem]  # Full conversation history
    location: Location | None = None  # Optional browser geolocation


class ChatResponse(BaseModel):
    response: str


# --- New models for post-processor and formatter ---

class FormatRequest(BaseModel):
    """Schema for requesting structured output formatting."""
    original_response: str
    format_type: Literal["json", "markdown", "summary"] = "markdown"


class FormatResponse(BaseModel):
    """Schema for formatted output."""
    formatted_response: str
    format_type: str


class PostProcessorDecision(BaseModel):
    """Schema for post-processor evaluation result."""
    should_continue: bool
    reasoning: str
    tool_calls_made: int
    iteration_count: int
