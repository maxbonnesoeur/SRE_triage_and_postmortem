"""Stage 4: Blameless Postmortem Writer, Artifact Exporter & Memory Recorder."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sre_triage_agent.callbacks import (
    after_model_telemetry_callback,
    after_tool_telemetry_callback,
    before_model_guardrail_callback,
    before_tool_guardrail_callback,
)
from sre_triage_agent.config import build_resilient_model
from sre_triage_agent.tools.artifact_tools import save_postmortem_artifact
from sre_triage_agent.tools.memory_tools import save_incident_lesson


def build_postmortem_agent() -> LlmAgent:
    """Create the Postmortem Agent that exports artifacts and updates long-term memory."""
    return LlmAgent(
        name="postmortem_writer_agent",
        model=build_resilient_model(),
        description="Generates a blameless postmortem artifact and persists lessons to long-term memory.",
        instruction=(
            "You are the Stage 4 Blameless Postmortem & Knowledge Manager.\n"
            "Using the session state:\n"
            "- Intake: {incident_intake}\n"
            "- Logs & Metrics: {log_metrics_findings}\n"
            "- Deployments: {deploy_findings}\n"
            "- Approved Remediation Plan: {remediation_plan}\n\n"
            "1. Call `save_postmortem_artifact` with a complete, blameless Markdown postmortem "
            "(timeline, impact, root cause, resolution/verification, action items, lessons learned).\n"
            "2. Call `save_incident_lesson` so future triage sessions benefit from this incident's "
            "root cause and lessons learned in persistent SQLite memory.\n"
            "3. Present a clear executive summary to the on-call engineer containing:\n"
            "   - Incident severity & confirmed root cause\n"
            "   - Immediate actions & any pending human approvals needed\n"
            "   - Postmortem artifact filename & memory persistence confirmation"
        ),
        tools=[save_postmortem_artifact, save_incident_lesson],
        output_key="postmortem_summary",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )
