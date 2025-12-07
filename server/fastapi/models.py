from pydantic import BaseModel


class Location(BaseModel):
    lat: float
    lon: float


class ChatRequest(BaseModel):
    message: str
    location: Location | None = None  # Optional browser geolocation


class ChatResponse(BaseModel):
    response: str

