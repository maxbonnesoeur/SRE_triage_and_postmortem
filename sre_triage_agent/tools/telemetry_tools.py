"""Read-only observability, deployment, and runbook tools for SRE investigation.

Every tool follows a consistent contract:
- Explicit type annotations and clear LLM-oriented docstrings.
- Defensive input normalization and structured error payloads (`status: "error"`).
- Bounded outputs (`limit` capped by Settings.max_log_lines) for context hygiene.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sre_triage_agent.config import get_settings
from sre_triage_agent.data.mock_telemetry import (
    ALERTS,
    DEPLOYMENTS,
    LOGS,
    METRICS,
    RUNBOOKS,
)


def list_active_alerts(service_name: str = "") -> dict[str, Any]:
    """List currently firing enterprise alerts, optionally filtered by service name.

    Args:
        service_name: Optional microservice name (e.g., "payments-api"). Leave empty
            to return all firing alerts across the fleet.

    Returns:
        Structured dictionary with `status`, `count`, and `alerts` list.
    """
    normalized = service_name.strip().lower()
    matched = [
        asdict(a)
        for a in ALERTS
        if a.status == "firing" and (not normalized or a.service.lower() == normalized)
    ]
    return {
        "status": "ok",
        "filter_service": normalized or "all",
        "count": len(matched),
        "alerts": matched,
    }


def query_service_logs(
    service_name: str,
    level: str = "",
    keyword: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Query structured application logs for a specific service.

    Args:
        service_name: Target microservice name (e.g., "payments-api", "auth-gateway").
        level: Optional severity filter ("ERROR", "WARN", "INFO").
        keyword: Optional case-insensitive substring filter on log messages.
        limit: Maximum number of log entries to return (capped for context hygiene).

    Returns:
        Structured dictionary with matched log entries or an error payload.
    """
    normalized = service_name.strip().lower()
    if not normalized:
        return {"status": "error", "error": "service_name must be a non-empty string."}

    max_lines = get_settings().max_log_lines
    capped_limit = max(1, min(limit, max_lines))
    level_upper = level.strip().upper()
    kw = keyword.strip().lower()

    matched = [
        asdict(entry)
        for entry in LOGS
        if entry.service.lower() == normalized
        and (not level_upper or entry.level.upper() == level_upper)
        and (not kw or kw in entry.message.lower())
    ][:capped_limit]

    if not matched:
        known = sorted({entry.service for entry in LOGS})
        return {
            "status": "not_found",
            "service": normalized,
            "logs": [],
            "hint": f"No logs matched. Known services: {', '.join(known)}",
        }

    return {
        "status": "ok",
        "service": normalized,
        "count": len(matched),
        "truncated_limit": capped_limit,
        "logs": matched,
    }


def get_service_metrics(service_name: str) -> dict[str, Any]:
    """Retrieve current golden-signal metrics (error rate, p99 latency, saturation) for a service.

    Args:
        service_name: Target microservice name (e.g., "payments-api").

    Returns:
        Dictionary containing current metrics vs baseline SLO figures.
    """
    normalized = service_name.strip().lower()
    metrics = METRICS.get(normalized)
    if not metrics:
        return {
            "status": "error",
            "error": f"Unknown service '{service_name}'.",
            "available_services": sorted(METRICS.keys()),
        }
    return {"status": "ok", "metrics": dict(metrics)}


def get_recent_deployments(service_name: str, limit: int = 5) -> dict[str, Any]:
    """Fetch recent production deployments and commit summaries for a service.

    Args:
        service_name: Target microservice name (e.g., "payments-api").
        limit: Maximum number of deployment records to return.

    Returns:
        Dictionary with recent deployments ordered newest-first.
    """
    normalized = service_name.strip().lower()
    capped = max(1, min(limit, 10))
    matched = [asdict(d) for d in DEPLOYMENTS if d.service.lower() == normalized][:capped]
    if not matched:
        return {
            "status": "not_found",
            "service": normalized,
            "deployments": [],
            "hint": "No deployments recorded for this service.",
        }
    return {
        "status": "ok",
        "service": normalized,
        "count": len(matched),
        "deployments": matched,
    }


def search_runbooks(service_name: str = "", symptom_query: str = "") -> dict[str, Any]:
    """Search SRE standard operating runbooks by service name and/or symptom keywords.

    Args:
        service_name: Optional microservice name to prioritize.
        symptom_query: Optional keywords describing the failure (e.g., "503 connection pool").

    Returns:
        Matching runbooks with diagnostic and mitigation procedures.
    """
    norm_service = service_name.strip().lower()
    terms = [t.lower() for t in symptom_query.split() if len(t) >= 2]

    scored: list[tuple[int, dict[str, Any]]] = []
    for rb in RUNBOOKS:
        score = 0
        if norm_service and rb.service.lower() == norm_service:
            score += 5
        haystack = " ".join([rb.title, *rb.triggers, *rb.mitigation_steps]).lower()
        for term in terms:
            if term in haystack:
                score += 2
        if score > 0 or (not norm_service and not terms):
            scored.append((score, asdict(rb)))

    scored.sort(key=lambda item: item[0], reverse=True)
    return {
        "status": "ok",
        "count": len(scored),
        "runbooks": [item[1] for item in scored],
    }
