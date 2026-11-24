"""Structural tests verifying ADK multi-agent topology, schemas, and MCP server."""

from __future__ import annotations

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.models.google_llm import Gemini

from sre_triage_agent.agent import build_adk_app, build_root_agent
from sre_triage_agent.mcp_server.ops_mcp_server import (
    mcp,
    mcp_get_service_metrics,
    mcp_list_active_alerts,
)
from sre_triage_agent.schemas import IncidentIntake, RemediationAction, RemediationPlan, Severity


def test_multi_agent_topology_structure() -> None:
    commander = build_root_agent()
    assert isinstance(commander, LlmAgent)
    assert commander.name == "sre_incident_commander"
    assert len(commander.sub_agents) == 1

    pipeline = commander.sub_agents[0]
    assert isinstance(pipeline, SequentialAgent)
    assert len(pipeline.sub_agents) == 4

    intake, parallel_inv, remediation_loop, postmortem = pipeline.sub_agents
    assert isinstance(intake, LlmAgent)
    assert isinstance(parallel_inv, ParallelAgent)
    assert len(parallel_inv.sub_agents) == 3
    assert isinstance(remediation_loop, LoopAgent)
    assert len(remediation_loop.sub_agents) == 2
    assert isinstance(postmortem, LlmAgent)
    assert isinstance(commander.model, Gemini)
    assert commander.model.retry_options is not None
    assert commander.model.retry_options.attempts == 5

    adk_app = build_adk_app(commander)
    assert adk_app.context_cache_config is not None
    assert adk_app.events_compaction_config is not None
    assert adk_app.events_compaction_config.compaction_interval == 6


def test_pydantic_schemas_validation() -> None:
    intake = IncidentIntake(
        incident_id="INC-2026-0412",
        service_name="payments-api",
        severity=Severity.SEV1,
        symptoms=["18.4% 503s", "4820ms p99 latency"],
        suspected_blast_radius="Checkout payments in us-central1",
        triage_summary="SEV1 payments outage correlated with DB pool exhaustion.",
    )
    assert intake.severity == Severity.SEV1

    plan = RemediationPlan(
        incident_id="INC-2026-0412",
        service_name="payments-api",
        root_cause_hypothesis="DB connection pool leak in v2.18.4",
        confidence=0.94,
        immediate_actions=[
            RemediationAction(
                action_type="rollback_deployment",
                target_service="payments-api",
                parameters={"target_version": "v2.18.3"},
                risk_level="high",
                requires_human_approval=True,
                rationale="Deployment v2.18.4 landed 8 minutes before pool saturation.",
            )
        ],
        verification_steps=["p99 < 400ms for 5 minutes"],
        rollback_plan="Disable async_ledger_retry_v2 if rollback stalls.",
        critic_approved=True,
    )
    assert plan.critic_approved is True


def test_mcp_server_tools_callable() -> None:
    assert mcp.name == "enterprise-ops-mcp"
    alerts = mcp_list_active_alerts("payments-api")
    assert alerts["count"] == 1
    metrics = mcp_get_service_metrics("payments-api")
    assert metrics["metrics"]["error_rate_pct"] == 18.4
