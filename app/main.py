"""HTTP entrypoint that serves the ADK agents in ../agents (used by Cloud Run)."""

import os
from pathlib import Path

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = str(Path(__file__).resolve().parent.parent / "agents")

# Sessions are in-memory unless SESSION_SERVICE_URI points at a persistent
# store (e.g. a Cloud SQL "postgresql+asyncpg://..." URL or "agentengine://...").
app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    session_service_uri=os.getenv("SESSION_SERVICE_URI") or None,
    use_local_storage=False,
    allow_origins=[o for o in os.getenv("ALLOW_ORIGINS", "").split(",") if o],
    web=os.getenv("SERVE_WEB_UI", "false").lower() == "true",
    trace_to_cloud=os.getenv("TRACE_TO_CLOUD", "false").lower() == "true",
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
