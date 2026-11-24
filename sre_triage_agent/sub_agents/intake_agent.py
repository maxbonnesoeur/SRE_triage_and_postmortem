"""Stage 1: Incident Intake & Severity Classification Agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sre_triage_agent.callbacks import (
    after_model_telemetry_callback,
    after_tool_telemetry_callback,
    before_model_guardrail_callback,
    before_tool_guardrail_callback,
)
from sre_triage_agent.config import build_resilient_model
from sre_triage_agent.tools.telemetry_tools import list_active_alerts


def build_intake_agent() -> LlmAgent:
    """Create the Intake Agent that normalizes alerts and classifies severity."""
    return LlmAgent(
        name="incident_intake_agent",
        model=build_resilient_model(),
        description="Classifies incident severity, identifies impacted service, and captures symptoms.",
        instruction=(
            "You are the Stage 1 Incident Intake Specialist.\n"
            "1. Call `list_active_alerts` to verify firing alerts matching the user's request.\n"
            "2. Identify the exact `incident_id`, `service_name`, `severity` (SEV1-SEV4), "
            "key symptoms, and suspected customer blast radius.\n"
            "3. Output a crisp, structured intake brief (bulleted with Incident ID, Service, "
            "Severity, Trigger Time, Symptoms, and Blast Radius) so downstream parallel "
            "investigators have exact identifiers to query."
        ),
        tools=[list_active_alerts],
        output_key="incident_intake",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )
