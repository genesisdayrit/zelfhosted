from fastapi import FastAPI

app = FastAPI(
    title="Zelfhosted API",
    description="AI-powered backend for Zelfhosted",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {"message": "Hello from Zelfhosted API"}


@app.get("/health")
async def health():
    return {"status": "ok"}
