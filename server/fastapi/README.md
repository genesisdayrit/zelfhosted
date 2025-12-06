# Zelfhosted API

AI-powered backend using FastAPI and LangGraph.

## Setup

1. **Install dependencies:**

```bash
uv sync
```

2. **Configure environment:**

Create a `.env` file in this directory:

```bash
OPENAI_API_KEY=sk-your-api-key-here
```

Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys).

3. **Run the server:**

```bash
uv run uvicorn main:app --reload
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root endpoint |
| `/health` | GET | Health check |
| `/chat` | POST | Chat with LangGraph agent |

### Chat Endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello! What is LangGraph?"}'
```

**Response:**

```json
{
  "response": "LangGraph is a framework for building stateful, multi-actor applications with LLMs..."
}
```

