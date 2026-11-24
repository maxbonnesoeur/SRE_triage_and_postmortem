"""Root ADK multi-agent orchestration for the SRE Triage & Postmortem Commander.

Architecture:
    root_agent (LlmAgent: sre_incident_commander)
      ├── Direct read-only tools: list_active_alerts, search_past_incidents
      ├── Guarded execution tools: rollback_deployment, scale_service_replicas (require approval token)
      └── Sub-agent: incident_triage_pipeline (SequentialAgent)
            ├── 1. incident_intake_agent (LlmAgent)
            ├── 2. parallel_investigation_agent (ParallelAgent)
            │     ├── log_metrics_investigator (LlmAgent)
            │     ├── deploy_correlator (LlmAgent)
            │     └── runbook_memory_researcher (LlmAgent)
            ├── 3. remediation_refinement_loop (LoopAgent)
            │     ├── remediation_planner (LlmAgent)
            │     └── safety_critic (LlmAgent -> approve_remediation_plan)
            └── 4. postmortem_writer_agent (LlmAgent -> artifact + SQLite memory)
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.apps.app import App, ContextCacheConfig, EventsCompactionConfig

from sre_triage_agent.callbacks import (
    after_agent_async_memory_callback,
    after_model_telemetry_callback,
    after_tool_telemetry_callback,
    before_model_guardrail_callback,
    before_tool_guardrail_callback,
)
from sre_triage_agent.config import build_resilient_model, get_settings
from sre_triage_agent.observability import configure_observability
from sre_triage_agent.sub_agents.intake_agent import build_intake_agent
from sre_triage_agent.sub_agents.investigators import build_parallel_investigation_agent
from sre_triage_agent.sub_agents.postmortem_agent import build_postmortem_agent
from sre_triage_agent.sub_agents.remediation_loop import build_remediation_loop_agent
from sre_triage_agent.tools.memory_tools import search_past_incidents
from sre_triage_agent.tools.remediation_tools import (
    rollback_deployment,
    scale_service_replicas,
)
from sre_triage_agent.tools.telemetry_tools import list_active_alerts


def build_incident_triage_pipeline() -> SequentialAgent:
    """Build the 4-stage SequentialAgent incident triage & postmortem workflow."""
    return SequentialAgent(
        name="incident_triage_pipeline",
        description=(
            "End-to-end 4-stage incident response workflow: Intake -> Parallel Investigation "
            "(Logs/Metrics, Deploys, Runbooks/Memory) -> Safety-Audited Remediation Loop -> "
            "Blameless Postmortem & Long-Term Memory Persistence."
        ),
        sub_agents=[
            build_intake_agent(),
            build_parallel_investigation_agent(),
            build_remediation_loop_agent(),
            build_postmortem_agent(),
        ],
    )


def build_root_agent() -> LlmAgent:
    """Build the top-level Incident Commander agent discovered by ADK CLI/Web."""
    configure_observability()
    triage_pipeline = build_incident_triage_pipeline()

    return LlmAgent(
        name="sre_incident_commander",
        model=build_resilient_model(),
        description=(
            "Enterprise SRE Incident Commander that triages active alerts, orchestrates "
            "parallel root-cause investigations, enforces production safety guardrails, "
            "and generates blameless postmortems with persistent institutional memory."
        ),
        instruction=(
            "You are the Enterprise SRE Incident Commander.\n"
            "Decide the best response path for the user:\n"
            "1. For quick status checks (e.g., 'what alerts are firing?' or 'have we seen "
            "this error before?'), answer directly using `list_active_alerts` or `search_past_incidents`.\n"
            "2. For any request to triage, investigate, diagnose, mitigate, or write a postmortem "
            "for an incident or service outage, delegate to `incident_triage_pipeline`.\n"
            "3. When an on-call engineer explicitly provides an approval token to execute a "
            "previously proposed `rollback_deployment` or `scale_service_replicas`, invoke the "
            "corresponding tool with `human_approval_token` and report the exact execution result.\n"
            "Always remain concise, factual, blameless, and transparent about safety guardrails."
        ),
        tools=[
            list_active_alerts,
            search_past_incidents,
            rollback_deployment,
            scale_service_replicas,
        ],
        sub_agents=[triage_pipeline],
        before_model_callback=before_model_guardrail_callback,
        after_model_callback=after_model_telemetry_callback,
        before_tool_callback=before_tool_guardrail_callback,
        after_tool_callback=after_tool_telemetry_callback,
        after_agent_callback=after_agent_async_memory_callback,
    )


def build_adk_app(agent: LlmAgent | None = None) -> App:
    """Wrap the root agent in an ADK App with context caching & history compaction."""
    settings = get_settings()
    return App(
        name="sre_triage_agent",
        root_agent=agent or build_root_agent(),
        context_cache_config=ContextCacheConfig(
            min_tokens=settings.context_cache_min_tokens,
            ttl_seconds=settings.context_cache_ttl_seconds,
            cache_intervals=10,
        ),
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=settings.compaction_interval,
            overlap_size=settings.compaction_overlap_size,
        ),
    )


# Standard ADK entrypoints exported for `adk web`, `adk run`, and `adk eval`
root_agent = build_root_agent()
app = build_adk_app(root_agent)
