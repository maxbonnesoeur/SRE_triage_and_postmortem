"""ADK tools connecting agents to persistent long-term incident memory."""

from __future__ import annotations

from typing import Any

from google.adk.tools.tool_context import ToolContext

from sre_triage_agent.memory.incident_memory import IncidentMemoryStore

_default_store: IncidentMemoryStore | None = None


def get_memory_store() -> IncidentMemoryStore:
    """Return a lazily initialized process-wide IncidentMemoryStore."""
    global _default_store
    if _default_store is None:
        _default_store = IncidentMemoryStore()
    return _default_store


def set_memory_store(store: IncidentMemoryStore | None) -> None:
    """Override the default store (primarily for isolated unit testing)."""
    global _default_store
    _default_store = store


def search_past_incidents(
    service_name: str = "",
    symptom_query: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """Search long-term institutional memory for similar past incidents and resolutions.

    Args:
        service_name: Microservice name to prioritize (e.g., "payments-api").
        symptom_query: Keywords describing observed symptoms (e.g., "503 pool").
        limit: Maximum number of historical incidents to return.

    Returns:
        Dictionary with matching historical incidents, root causes, and lessons learned.
    """
    matches = get_memory_store().search(
        service_name=service_name,
        query=symptom_query,
        limit=limit,
    )
    return {
        "status": "ok",
        "count": len(matches),
        "past_incidents": matches,
    }


def save_incident_lesson(
    incident_id: str,
    service_name: str,
    severity: str,
    symptoms: str,
    root_cause: str,
    resolution: str,
    lessons_learned: list[str],
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Persist a resolved incident and its lessons learned into long-term SQLite memory.

    Args:
        incident_id: Unique incident ID (e.g., "INC-2026-0412").
        service_name: Impacted microservice name.
        severity: Incident severity ("SEV1", "SEV2", "SEV3", "SEV4").
        symptoms: Summary of observed symptoms.
        root_cause: Confirmed or highest-confidence root cause.
        resolution: Mitigation/resolution applied or recommended.
        lessons_learned: Actionable engineering takeaways for future incidents.
        tool_context: Optional ADK ToolContext to update session state.

    Returns:
        Confirmation payload with the persisted memory record.
    """
    saved = get_memory_store().save_incident(
        incident_id=incident_id,
        service_name=service_name,
        severity=severity,
        symptoms=symptoms,
        root_cause=root_cause,
        resolution=resolution,
        lessons_learned=lessons_learned,
    )
    if tool_context is not None:
        tool_context.state["last_persisted_incident_id"] = saved["incident_id"]
    return {"status": "ok", "saved_memory": saved}
