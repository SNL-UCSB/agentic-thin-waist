from fastapi import FastAPI

from app.api.intent import router as intent_router

app = FastAPI(title="Orchestration Service", version="0.1.0")
app.include_router(intent_router)


@app.get("/health")
def health():
    return {"status": "healthy", "checks": {}}
