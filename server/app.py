"""Production FastAPI server with A2A Agent Card, health probes, and ADK Runner.

Run locally:
    uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from google.adk.runners import Runner
from google.genai import types
from pydantic import BaseModel, Field

from sre_triage_agent.agent import root_agent
from sre_triage_agent.config import get_settings
from sre_triage_agent.memory.session_factory import build_memory_service, build_session_service
from sre_triage_agent.observability import configure_observability, metrics_registry
from sre_triage_agent.tools.memory_tools import get_memory_store

APP_NAME = "sre_triage_agent"

configure_observability()

app = FastAPI(
    title="SRE Triage & Postmortem Commander",
    description=(
        "Enterprise multi-agent incident triage, safety-audited remediation planning, "
        "and blameless postmortem generation powered by Google ADK."
    ),
    version="0.1.0",
)

_session_service = build_session_service(use_database=False)
_memory_service = build_memory_service()
_runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
    memory_service=_memory_service,
)


class TriageRequest(BaseModel):
    """Request payload for invoking the SRE Incident Commander."""

    message: str = Field(..., min_length=1, description="Incident alert or SRE query.")
    user_id: str = Field(default="oncall-engineer")
    session_id: str | None = Field(
        default=None,
        description="Optional existing session ID to continue a multi-turn investigation.",
    )
    approved_destructive_ops: bool = Field(
        default=False,
        description="Set true only when an on-call engineer explicitly approves production mutations.",
    )


class TriageResponse(BaseModel):
    """Structured API response from the SRE Incident Commander."""

    session_id: str
    response: str
    postmortem_filename: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Cloud Run liveness probe."""
    return {"status": "ok", "service": get_settings().service_name}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    """Cloud Run readiness probe verifying agent and memory store readiness."""
    memory_count = get_memory_store().count()
    return {
        "status": "ready",
        "agent": root_agent.name,
        "memory_records": memory_count,
    }


@app.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    """Expose runtime tool latency, token usage, and guardrail enforcement metrics."""
    return metrics_registry.snapshot()


@app.get("/.well-known/agent.json")
async def a2a_agent_card() -> dict[str, Any]:
    """Expose an Agent2Agent (A2A) protocol discovery card for inter-agent delegation."""
    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")
    return {
        "name": "SRE Triage & Postmortem Commander",
        "description": root_agent.description,
        "url": base_url,
        "version": "0.1.0",
        "protocolVersion": "0.2.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "text/markdown", "application/json"],
        "skills": [
            {
                "id": "incident-triage",
                "name": "Parallel Multi-Signal Incident Triage",
                "description": "Correlates alerts, logs, golden-signal metrics, deployments, runbooks, and past incidents.",
                "tags": ["sre", "incident-response", "observability", "root-cause"],
            },
            {
                "id": "guarded-remediation",
                "name": "Safety-Audited Remediation Planning",
                "description": "Refines mitigation plans via Planner/Critic loop with human-in-the-loop approval gates.",
                "tags": ["remediation", "guardrails", "hitl"],
            },
            {
                "id": "blameless-postmortem",
                "name": "Blameless Postmortem & Memory Persistence",
                "description": "Exports Markdown postmortem artifacts and persists institutional lessons to SQLite.",
                "tags": ["postmortem", "memory", "artifacts"],
            },
        ],
    }


@app.get("/api/v1/memory")
async def list_incident_memory(service_name: str = "", query: str = "", limit: int = 10) -> dict[str, Any]:
    """Inspect historical incident memories persisted in SQLite."""
    items = get_memory_store().search(service_name=service_name, query=query, limit=limit)
    return {"count": len(items), "incidents": items}


@app.post("/api/v1/triage", response_model=TriageResponse)
async def run_triage(request: TriageRequest) -> TriageResponse:
    """Execute a turn against the SRE Incident Commander via ADK Runner."""
    session_id = request.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    existing = await _session_service.get_session(
        app_name=APP_NAME,
        user_id=request.user_id,
        session_id=session_id,
    )
    if existing is None:
        await _session_service.create_session(
            app_name=APP_NAME,
            user_id=request.user_id,
            session_id=session_id,
            state={"approved_destructive_ops": request.approved_destructive_ops},
        )

    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=request.message)],
    )

    final_chunks: list[str] = []
    try:
        async for event in _runner.run_async(
            user_id=request.user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    text = getattr(part, "text", None)
                    if isinstance(text, str) and text:
                        final_chunks.append(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

    updated_session = await _session_service.get_session(
        app_name=APP_NAME,
        user_id=request.user_id,
        session_id=session_id,
    )
    postmortem_file = (
        updated_session.state.get("postmortem_filename") if updated_session else None
    )

    return TriageResponse(
        session_id=session_id,
        response="\n".join(final_chunks).strip() or "No textual response generated.",
        postmortem_filename=postmortem_file,
        metrics=metrics_registry.snapshot(),
    )


def main() -> None:
    """Entrypoint for `sre-triage-server`."""
    uvicorn.run(
        "server.app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
