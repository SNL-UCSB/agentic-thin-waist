from fastapi import FastAPI

from app.api.intent import router as intent_router
from app.engine.executor import DownstreamClients

app = FastAPI(title="Orchestration Service", version="0.1.0")
app.include_router(intent_router)


@app.get("/health")
def health():
    clients = DownstreamClients()
    checks = clients.health()
    overall = "healthy" if all(v == "reachable" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
