"""Stage 2: Parallel Multi-Signal Investigation Agents.

Runs three independent investigators concurrently using ADK `ParallelAgent`:
1. `log_metrics_investigator`: Correlates error logs and golden-signal metrics.
2. `deploy_correlator`: Checks recent releases and code/config changes.
3. `runbook_memory_researcher`: Retrieves SRE runbooks and long-term past incidents.
"""

from __future__ import annotations

import sys
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent

from sre_triage_agent.callbacks import (
    after_model_telemetry_callback,
    after_tool_telemetry_callback,
    before_model_guardrail_callback,
    before_tool_guardrail_callback,
)
from sre_triage_agent.config import get_settings
from sre_triage_agent.tools.memory_tools import search_past_incidents
from sre_triage_agent.tools.telemetry_tools import (
    get_recent_deployments,
    get_service_metrics,
    query_service_logs,
    search_runbooks,
)


def _build_optional_mcp_toolset() -> Any | None:
    """Optionally construct an ADK McpToolset connected to the local ops MCP server."""
    settings = get_settings()
    if not settings.use_mcp_tools:
        return None
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    from mcp import StdioServerParameters

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "sre_triage_agent.mcp_server.ops_mcp_server"],
            )
        )
    )


def build_parallel_investigation_agent() -> ParallelAgent:
    """Create the ParallelAgent that fans out across logs/metrics, deploys, and memory."""
    settings = get_settings()
    mcp_toolset = _build_optional_mcp_toolset()

    log_metrics_tools: list[Any] = (
        [mcp_toolset] if mcp_toolset is not None else [query_service_logs, get_service_metrics]
    )
    deploy_tools: list[Any] = (
        [mcp_toolset] if mcp_toolset is not None else [get_recent_deployments]
    )

    log_metrics_investigator = LlmAgent(
        name="log_metrics_investigator",
        model=settings.agent_model,
        description="Analyzes structured logs and golden-signal metrics for anomalies.",
        instruction=(
            "You are the Telemetry & Logs Investigator.\n"
            "Context from intake:\n{incident_intake}\n\n"
            "1. Query both service metrics and ERROR/WARN logs for the impacted service.\n"
            "2. Highlight SLO deviations (error rate, p99 latency, saturation, OOMs/evictions) "
            "and cite specific log timestamps and trace IDs.\n"
            "3. Keep your findings concise and evidence-backed."
        ),
        tools=log_metrics_tools,
        output_key="log_metrics_findings",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )

    deploy_correlator = LlmAgent(
        name="deploy_correlator",
        model=settings.agent_model,
        description="Correlates recent production deployments and config changes with incident onset.",
        instruction=(
            "You are the Release & Change Correlator.\n"
            "Context from intake:\n{incident_intake}\n\n"
            "1. Fetch recent deployments for the impacted service.\n"
            "2. Identify any deployment that landed shortly before the incident triggered, "
            "noting `version`, `previous_version`, `commit_sha`, and `change_summary`.\n"
            "3. Assess whether a rollback candidate exists."
        ),
        tools=deploy_tools,
        output_key="deploy_findings",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )

    runbook_memory_researcher = LlmAgent(
        name="runbook_memory_researcher",
        model=settings.agent_model,
        description="Retrieves SRE runbooks and historical incident lessons from long-term memory.",
        instruction=(
            "You are the Runbook & Institutional Memory Researcher.\n"
            "Context from intake:\n{incident_intake}\n\n"
            "1. Call `search_runbooks` for the impacted service and symptoms.\n"
            "2. Call `search_past_incidents` to check long-term memory for prior recurrences.\n"
            "3. Summarize matching runbook IDs, recommended mitigations, escalation team, "
            "and any relevant lessons learned from historical incidents."
        ),
        tools=[search_runbooks, search_past_incidents],
        output_key="runbook_memory_findings",
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
    )

    return ParallelAgent(
        name="parallel_investigation_agent",
        description="Concurrently investigates telemetry, recent deployments, runbooks, and incident memory.",
        sub_agents=[
            log_metrics_investigator,
            deploy_correlator,
            runbook_memory_researcher,
        ],
    )
