"""Centralized configuration for the SRE Triage & Postmortem Commander."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from google.adk.models.google_llm import Gemini
from google.genai import types
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
        default="gemini-3.8-flash",
        description="Default Gemini 3.8 Flash model for triage, investigation, and drafting.",
    )
    agent_pro_model: str = Field(
        default="gemini-3.8-flash",
        description="Gemini model for safety critique and root-cause synthesis.",
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

    # Resilience, Context Caching & History Compaction
    model_retry_attempts: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Exponential-backoff retry attempts for transient 429/500/503/504 LLM errors.",
    )
    context_cache_min_tokens: int = Field(
        default=4096,
        ge=0,
        description="Minimum prompt tokens before enabling Gemini 3 context caching.",
    )
    context_cache_ttl_seconds: int = Field(
        default=1800,
        ge=60,
        description="Context cache TTL in seconds.",
    )
    compaction_interval: int = Field(
        default=6,
        ge=2,
        description="Number of turns between automatic ADK event history compactions.",
    )
    compaction_overlap_size: int = Field(
        default=2,
        ge=0,
        description="Number of recent events preserved verbatim across compactions.",
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


def build_resilient_model(model_name: str | None = None) -> Gemini:
    """Create an ADK Gemini model wrapper with exponential-backoff HTTP retry options."""
    settings = get_settings()
    return Gemini(
        model=model_name or settings.agent_model,
        retry_options=types.HttpRetryOptions(
            attempts=settings.model_retry_attempts,
            initial_delay=1.0,
            max_delay=16.0,
            exp_base=2.0,
            http_status_codes=[429, 500, 503, 504],
        ),
    )
