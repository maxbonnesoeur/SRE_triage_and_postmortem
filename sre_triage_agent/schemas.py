"""Strict Pydantic v2 schemas for structured agent handoffs and outputs."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Enterprise incident severity levels."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class IncidentIntake(BaseModel):
    """Structured triage output produced by the Intake Agent."""

    incident_id: str = Field(description="Unique incident identifier (e.g., INC-2026-0412).")
    service_name: str = Field(description="Primary impacted microservice name.")
    severity: Severity = Field(description="Assigned incident severity (SEV1-SEV4).")
    symptoms: list[str] = Field(
        default_factory=list,
        description="Key observed symptoms from alerts or user description.",
    )
    suspected_blast_radius: str = Field(
        description="Customer or downstream service impact scope.",
    )
    triage_summary: str = Field(description="Concise 1-2 sentence triage summary.")


class RemediationAction(BaseModel):
    """A single proposed remediation step with explicit safety metadata."""

    action_type: Literal[
        "rollback_deployment",
        "scale_service_replicas",
        "toggle_feature_flag",
        "create_incident_ticket",
        "manual_verification",
    ]
    target_service: str = Field(description="Target service name.")
    parameters: dict[str, str | int | bool] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = Field(default="medium")
    requires_human_approval: bool = Field(
        default=True,
        description="True for state-mutating production changes.",
    )
    rationale: str = Field(description="Evidence-backed reason for this action.")


class RemediationPlan(BaseModel):
    """Structured remediation plan refined by the Planner/Critic LoopAgent."""

    incident_id: str
    service_name: str
    root_cause_hypothesis: str = Field(description="Primary root cause supported by evidence.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    supporting_evidence: list[str] = Field(default_factory=list)
    immediate_actions: list[RemediationAction] = Field(default_factory=list)
    verification_steps: list[str] = Field(
        default_factory=list,
        description="Concrete metrics/health checks to confirm recovery.",
    )
    rollback_plan: str = Field(description="Fallback procedure if remediation fails.")
    critic_approved: bool = Field(default=False)


class PostmortemReport(BaseModel):
    """Blameless postmortem report persisted to memory and exported as an artifact."""

    incident_id: str
    title: str
    severity: Severity
    service_name: str
    impact_summary: str
    root_cause: str
    contributing_factors: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    resolution_summary: str
    action_items: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
