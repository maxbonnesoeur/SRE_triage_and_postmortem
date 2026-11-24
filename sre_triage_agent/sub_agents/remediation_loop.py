"""Stage 3: Iterative Remediation Planner & Safety Critic LoopAgent."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools.tool_context import ToolContext

from sre_triage_agent.callbacks import (
    after_model_telemetry_callback,
    after_tool_telemetry_callback,
    before_model_guardrail_callback,
    before_tool_guardrail_callback,
)
from sre_triage_agent.config import get_settings
from sre_triage_agent.tools.remediation_tools import (
    create_incident_ticket,
    rollback_deployment,
    scale_service_replicas,
    toggle_feature_flag,
)


def approve_remediation_plan(summary: str, tool_context: ToolContext) -> dict[str, Any]:
    """Approve the remediation plan and exit the Planner/Critic refinement loop.

    Args:
        summary: Short confirmation explaining why the remediation plan meets all safety gates.
        tool_context: ADK ToolContext used to escalate and terminate the LoopAgent.

    Returns:
        Approval confirmation dictionary.
    """
    tool_context.state["remediation_approved"] = True
    tool_context.state["safety_approval_summary"] = summary
    tool_context.actions.escalate = True
    return {
        "status": "approved",
        "escalated": True,
        "summary": summary,
    }


def build_remediation_loop_agent() -> LoopAgent:
    """Create the LoopAgent pairing RemediationPlanner with SafetyCritic."""
    settings = get_settings()

    remediation_planner = LlmAgent(
        name="remediation_planner",
        model=settings.agent_model,
        description="Synthesizes parallel investigation findings into a safe, actionable remediation plan.",
        instruction=(
            "You are the Remediation Planner.\n"
            "Synthesize the investigation findings below:\n"
            "- Intake: {incident_intake}\n"
            "- Logs & Metrics: {log_metrics_findings}\n"
            "- Deployments: {deploy_findings}\n"
            "- Runbooks & Past Memory: {runbook_memory_findings}\n"
            "- Prior Safety Critique (if any): {safety_critique?}\n\n"
            "Requirements:\n"
            "1. State the highest-confidence root cause hypothesis and confidence score (0-100%).\n"
            "2. Open a tracking ticket via `create_incident_ticket` if not already opened.\n"
            "3. Propose ordered mitigation steps. Prefer low-risk reversible actions first. "
            "For destructive ops (`rollback_deployment`, `scale_service_replicas`), clearly note "
            "that human approval is required (do NOT bypass guardrails).\n"
            "4. Include explicit verification metrics (target SLO thresholds) and a fallback rollback plan.\n"
            "5. If a prior safety critique raised gaps, address every point explicitly."
        ),
        tools=[
            create_incident_ticket,
            toggle_feature_flag,
            rollback_deployment,
            scale_service_replicas,
        ],
        output_key="remediation_plan",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )

    safety_critic = LlmAgent(
        name="safety_critic",
        model=settings.agent_model,
        description="Audits remediation plans for evidence grounding, blast radius, verification, and rollback safety.",
        instruction=(
            "You are the SRE Safety Critic.\n"
            "Review the proposed remediation plan:\n{remediation_plan}\n\n"
            "Verify ALL 4 safety gates:\n"
            "1. Root cause is grounded in concrete logs, metrics, or deployment evidence.\n"
            "2. Destructive production actions explicitly note human-in-the-loop approval requirements.\n"
            "3. Measurable verification steps (exact SLO metrics) are included.\n"
            "4. A clear fallback/rollback plan exists.\n\n"
            "If ALL 4 gates pass, call `approve_remediation_plan` immediately with a concise summary.\n"
            "If any gate is missing, DO NOT call `approve_remediation_plan`; instead output a crisp "
            "bulleted list of required fixes for the next iteration."
        ),
        tools=[approve_remediation_plan],
        output_key="safety_critique",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )

    return LoopAgent(
        name="remediation_refinement_loop",
        description="Iteratively refines and safety-audits the incident remediation plan.",
        sub_agents=[remediation_planner, safety_critic],
        max_iterations=settings.max_remediation_iterations,
    )
