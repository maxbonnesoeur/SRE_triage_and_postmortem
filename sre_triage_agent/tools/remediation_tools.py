"""Operational remediation tools with explicit safety classification.

Destructive / production-mutating tools (`rollback_deployment`, `scale_service_replicas`)
are protected by `before_tool_callback` in `sre_triage_agent.callbacks`, requiring
explicit human approval before execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sre_triage_agent.data.mock_telemetry import (
    DEPLOYMENTS,
    FEATURE_FLAGS,
    INCIDENT_TICKETS,
    METRICS,
)

DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {"rollback_deployment", "scale_service_replicas"}
)


def create_incident_ticket(
    incident_id: str,
    service_name: str,
    severity: str,
    title: str,
    summary: str,
) -> dict[str, Any]:
    """Create or update a tracking ticket in the enterprise incident tracker (low-risk).

    Args:
        incident_id: Incident identifier (e.g., "INC-2026-0412").
        service_name: Impacted microservice name.
        severity: Severity level ("SEV1", "SEV2", "SEV3", "SEV4").
        title: Concise ticket title.
        summary: Key symptoms and current investigation summary.

    Returns:
        Created ticket metadata including ticket ID and timestamp.
    """
    ticket_id = f"OPS-{1000 + len(INCIDENT_TICKETS) + 1}"
    record = {
        "ticket_id": ticket_id,
        "incident_id": incident_id,
        "service_name": service_name,
        "severity": severity.upper(),
        "title": title,
        "summary": summary,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "open",
    }
    INCIDENT_TICKETS.append(record)
    return {"status": "ok", "ticket": record}


def toggle_feature_flag(
    service_name: str,
    flag_name: str,
    enabled: bool,
    reason: str,
) -> dict[str, Any]:
    """Toggle a kill-switch feature flag for a microservice (reversible mitigation).

    Args:
        service_name: Target microservice name.
        flag_name: Feature flag key to update.
        enabled: Desired boolean state (False to disable a faulty feature).
        reason: Concise evidence-backed justification for audit logging.

    Returns:
        Previous and updated feature flag state.
    """
    norm = service_name.strip().lower()
    flags = FEATURE_FLAGS.get(norm)
    if flags is None:
        return {"status": "error", "error": f"Unknown service '{service_name}'."}
    if flag_name not in flags:
        return {
            "status": "error",
            "error": f"Unknown feature flag '{flag_name}' for service '{norm}'.",
            "available_flags": sorted(flags.keys()),
        }

    previous = flags[flag_name]
    flags[flag_name] = enabled
    return {
        "status": "ok",
        "service": norm,
        "flag_name": flag_name,
        "previous_value": previous,
        "new_value": enabled,
        "reason": reason,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def rollback_deployment(
    service_name: str,
    target_version: str,
    reason: str,
    human_approval_token: str = "",
) -> dict[str, Any]:
    """Roll back a production service deployment to a known-good previous version.

    GUARDED OPERATION: Blocked by `before_tool_callback` unless an explicit
    human approval token is present in session state or arguments.

    Args:
        service_name: Target microservice name.
        target_version: Known-good version tag to restore (e.g., "v2.18.3").
        reason: Evidence-backed justification for the rollback.
        human_approval_token: Explicit approval token supplied by an on-call engineer.

    Returns:
        Rollback execution status and audit details.
    """
    norm = service_name.strip().lower()
    active = next(
        (d for d in DEPLOYMENTS if d.service.lower() == norm and d.status == "active"),
        None,
    )
    if not active:
        return {"status": "error", "error": f"No active deployment found for '{service_name}'."}

    previous_active = active.version
    active.status = "rolled_back"
    return {
        "status": "ok",
        "action": "rollback_deployment",
        "service": norm,
        "rolled_back_from": previous_active,
        "restored_version": target_version,
        "reason": reason,
        "approval_recorded": bool(human_approval_token),
        "executed_at": datetime.now(UTC).isoformat(),
    }


def scale_service_replicas(
    service_name: str,
    desired_replicas: int,
    reason: str,
    human_approval_token: str = "",
) -> dict[str, Any]:
    """Scale production replica count for a microservice within safe bounds (2-50).

    GUARDED OPERATION: Blocked by `before_tool_callback` unless explicitly approved.

    Args:
        service_name: Target microservice name.
        desired_replicas: Target number of replicas (must be between 2 and 50).
        reason: Evidence-backed justification for scaling.
        human_approval_token: Explicit approval token supplied by an on-call engineer.

    Returns:
        Scaling operation result with previous and new replica counts.
    """
    norm = service_name.strip().lower()
    if norm not in METRICS:
        return {"status": "error", "error": f"Unknown service '{service_name}'."}
    if not 2 <= desired_replicas <= 50:
        return {
            "status": "error",
            "error": "desired_replicas must be between 2 and 50 for safety compliance.",
        }

    previous_replicas = int(METRICS[norm].get("active_replicas", 2))
    METRICS[norm]["active_replicas"] = desired_replicas
    return {
        "status": "ok",
        "action": "scale_service_replicas",
        "service": norm,
        "previous_replicas": previous_replicas,
        "desired_replicas": desired_replicas,
        "reason": reason,
        "approval_recorded": bool(human_approval_token),
        "executed_at": datetime.now(UTC).isoformat(),
    }
