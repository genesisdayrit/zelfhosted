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

