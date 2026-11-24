"""API & A2A discovery endpoint tests for the FastAPI production server."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import app

client = TestClient(app)


def test_healthz_and_readyz() -> None:
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["agent"] == "sre_incident_commander"
    assert body["memory_records"] >= 2


def test_a2a_agent_card() -> None:
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    card = res.json()
    assert card["name"] == "SRE Triage & Postmortem Commander"
    assert len(card["skills"]) == 3


def test_metrics_and_memory_endpoints() -> None:
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "tool_calls_total" in metrics.json()

    mem = client.get("/api/v1/memory", params={"service_name": "payments-api"})
    assert mem.status_code == 200
    assert mem.json()["count"] >= 1
