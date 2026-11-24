"""Centralized configuration for the SRE Triage & Postmortem Commander."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="SRE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Model configuration
    agent_model: str = Field(
        default="gemini-2.5-flash",
        description="Default fast Gemini model for triage, investigation, and drafting.",
    )
    agent_pro_model: str = Field(
        default="gemini-2.5-pro",
        description="Higher-reasoning Gemini model for safety critique and root-cause synthesis.",
    )

    # Persistence & Memory
    memory_db_path: Path = Field(
        default=Path("./data/incident_memory.db"),
        description="SQLite path for persistent long-term incident memory.",
    )
    session_db_url: str = Field(
        default="sqlite+aiosqlite:///./data/adk_sessions.db",
        description="Session persistence URL for ADK DatabaseSessionService.",
    )

    # Orchestration & Guardrails
    use_mcp_tools: bool = Field(
        default=False,
        description="When true, attach the local stdio MCP server via ADK McpToolset.",
    )
    require_approval_for_destructive_ops: bool = Field(
        default=True,
        description="Require explicit human approval token before destructive remediation tools.",
    )
    max_remediation_iterations: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Maximum planner/critic iterations in the remediation LoopAgent.",
    )
    max_log_lines: int = Field(
        default=25,
        ge=5,
        le=100,
        description="Upper bound on returned log entries for context-window hygiene.",
    )

    # Observability & Tracing
    service_name: str = Field(default="sre-triage-agent")
    log_level: str = Field(default="INFO")
    otel_exporter: Literal["none", "console", "otlp", "gcp_trace"] = Field(
        default="none",
        description="OpenTelemetry span exporter backend.",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4318/v1/traces",
        description="OTLP HTTP endpoint when otel_exporter='otlp'.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
