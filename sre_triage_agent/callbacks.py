"""ADK lifecycle callbacks for safety guardrails, PII redaction, and telemetry."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from sre_triage_agent.config import get_settings
from sre_triage_agent.observability import get_tracer, metrics_registry
from sre_triage_agent.tools.remediation_tools import DESTRUCTIVE_TOOLS

logger = logging.getLogger("sre_triage_agent.callbacks")

# Regex patterns for scrubbing credentials & secrets before model invocation
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AIza[0-9A-Za-z\-_]{20,}"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"sk-[0-9A-Za-z]{20,}"), "[REDACTED_API_SECRET]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
]


def redact_sensitive_text(text: str) -> tuple[str, bool]:
    """Redact API keys, bearer tokens, and sensitive IDs from text."""
    redacted = text
    changed = False
    for pattern, replacement in _SECRET_PATTERNS:
        updated, count = pattern.subn(replacement, redacted)
        if count > 0:
            changed = True
            redacted = updated
    return redacted, changed


def before_model_guardrail_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Scrub secrets/PII from outbound model requests and record timing metadata."""
    callback_context.state["_model_call_start_ts"] = time.perf_counter()

    redacted_any = False
    for content in llm_request.contents or []:
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                cleaned, changed = redact_sensitive_text(text)
                if changed:
                    part.text = cleaned
                    redacted_any = True

    if redacted_any:
        metrics_registry.record_pii_redaction()
        logger.warning(
            "Redacted sensitive token/PII before LLM call",
            extra={"agent_name": callback_context.agent_name, "guardrail": "pii_redaction"},
        )
    return None


def after_model_telemetry_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Capture LLM latency, token counts, and OpenTelemetry span attributes."""
    start_ts = callback_context.state.get("_model_call_start_ts")
    latency_ms = round((time.perf_counter() - start_ts) * 1000, 2) if start_ts else 0.0

    usage = getattr(llm_response, "usage_metadata", None)
    prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    metrics_registry.record_model_call(
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
    )

    with get_tracer().start_as_current_span("sre_agent.llm_call") as span:
        span.set_attribute("agent.name", callback_context.agent_name)
        span.set_attribute("llm.latency_ms", latency_ms)
        span.set_attribute("llm.prompt_tokens", prompt_tokens)
        span.set_attribute("llm.output_tokens", output_tokens)

    logger.info(
        "Completed LLM invocation",
        extra={
            "agent_name": callback_context.agent_name,
            "latency_ms": latency_ms,
            "status": "ok",
        },
    )
    return None


def before_tool_guardrail_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """Enforce human-in-the-loop approval before destructive production tool calls."""
    tool_name = tool.name
    tool_context.state[f"_tool_start_{tool_name}"] = time.perf_counter()

    settings = get_settings()
    if tool_name in DESTRUCTIVE_TOOLS and settings.require_approval_for_destructive_ops:
        approval_token = str(args.get("human_approval_token", "") or "").strip()
        session_approved = bool(tool_context.state.get("approved_destructive_ops", False))
        if not approval_token and not session_approved:
            metrics_registry.record_guardrail_block()
            logger.warning(
                "Blocked destructive tool call pending human approval",
                extra={
                    "tool_name": tool_name,
                    "guardrail": "human_approval_required",
                    "status": "blocked",
                },
            )
            return {
                "status": "blocked_pending_approval",
                "tool": tool_name,
                "requested_args": args,
                "message": (
                    f"Safety guardrail blocked `{tool_name}` because it mutates production state. "
                    "Present the exact change, blast radius, and rollback plan to the on-call "
                    "engineer and request an explicit `human_approval_token` before retrying."
                ),
            }
    return None


def after_tool_telemetry_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Record tool latency, outcome status, and OpenTelemetry trace spans."""
    tool_name = tool.name
    start_ts = tool_context.state.get(f"_tool_start_{tool_name}")
    latency_ms = round((time.perf_counter() - start_ts) * 1000, 2) if start_ts else 0.0

    status = str(tool_response.get("status", "ok")) if isinstance(tool_response, dict) else "ok"
    is_error = status == "error"
    metrics_registry.record_tool_call(
        tool_name=tool_name,
        latency_ms=latency_ms,
        is_error=is_error,
    )

    with get_tracer().start_as_current_span(f"sre_agent.tool.{tool_name}") as span:
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("tool.status", status)
        span.set_attribute("tool.latency_ms", latency_ms)

    logger.info(
        "Completed tool execution",
        extra={
            "tool_name": tool_name,
            "latency_ms": latency_ms,
            "status": status,
        },
    )
    return None
