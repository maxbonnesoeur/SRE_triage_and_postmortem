"""Artifact generation tools for exporting structured Markdown postmortems."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from google.adk.tools.tool_context import ToolContext
from google.genai import types


def format_postmortem_markdown(
    incident_id: str,
    title: str,
    severity: str,
    service_name: str,
    impact_summary: str,
    root_cause: str,
    timeline: list[str],
    resolution_summary: str,
    action_items: list[str],
    lessons_learned: list[str],
) -> str:
    """Render a standardized blameless postmortem in GitHub-Flavored Markdown."""
    timeline_md = "\n".join(f"- {item}" for item in timeline) or "- Timeline pending."
    actions_md = "\n".join(f"- [ ] {item}" for item in action_items) or "- [ ] Follow up with service owner."
    lessons_md = "\n".join(f"- {item}" for item in lessons_learned) or "- Document detection improvements."

    return (
        f"# Blameless Postmortem: {incident_id} — {title}\n\n"
        f"- **Service:** `{service_name}`\n"
        f"- **Severity:** `{severity.upper()}`\n"
        f"- **Generated At:** `{datetime.now(UTC).isoformat()}`\n\n"
        f"## 1. Customer & System Impact\n{impact_summary}\n\n"
        f"## 2. Root Cause\n{root_cause}\n\n"
        f"## 3. Incident Timeline\n{timeline_md}\n\n"
        f"## 4. Resolution & Verification\n{resolution_summary}\n\n"
        f"## 5. Follow-Up Action Items\n{actions_md}\n\n"
        f"## 6. Lessons Learned\n{lessons_md}\n"
    )


async def save_postmortem_artifact(
    incident_id: str,
    title: str,
    severity: str,
    service_name: str,
    impact_summary: str,
    root_cause: str,
    timeline: list[str],
    resolution_summary: str,
    action_items: list[str],
    lessons_learned: list[str],
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Generate and persist a Markdown blameless postmortem as an ADK artifact.

    Args:
        incident_id: Incident identifier (e.g., "INC-2026-0412").
        title: Concise incident title.
        severity: Incident severity ("SEV1"-"SEV4").
        service_name: Primary impacted microservice.
        impact_summary: Description of customer and SLO impact.
        root_cause: Evidence-backed root cause analysis.
        timeline: Chronological list of key incident events.
        resolution_summary: Mitigation executed or recommended and verification steps.
        action_items: Concrete engineering follow-up items with owners/priorities.
        lessons_learned: Key takeaways for preventing recurrence.
        tool_context: ADK ToolContext used to save the downloadable artifact.

    Returns:
        Artifact filename, version (if saved via ArtifactService), and Markdown preview.
    """
    markdown = format_postmortem_markdown(
        incident_id=incident_id,
        title=title,
        severity=severity,
        service_name=service_name,
        impact_summary=impact_summary,
        root_cause=root_cause,
        timeline=timeline,
        resolution_summary=resolution_summary,
        action_items=action_items,
        lessons_learned=lessons_learned,
    )
    filename = f"postmortem_{incident_id.lower().replace(' ', '_')}.md"
    version: int | None = None

    if tool_context is not None:
        tool_context.state["postmortem_markdown"] = markdown
        tool_context.state["postmortem_filename"] = filename
        try:
            artifact_part = types.Part.from_bytes(
                data=markdown.encode("utf-8"),
                mime_type="text/markdown",
            )
            version = await tool_context.save_artifact(
                filename=filename,
                artifact=artifact_part,
            )
        except ValueError:
            # ArtifactService may not be configured in minimal unit-test runners.
            version = None

    return {
        "status": "ok",
        "filename": filename,
        "artifact_version": version,
        "character_count": len(markdown),
        "markdown": markdown,
    }
