"""Unit tests for safety guardrails, PII redaction, and telemetry callbacks."""

from __future__ import annotations

from types import SimpleNamespace

from sre_triage_agent.callbacks import (
    after_tool_telemetry_callback,
    before_tool_guardrail_callback,
    redact_sensitive_text,
)
from sre_triage_agent.observability import metrics_registry


def test_redact_sensitive_text_scrubs_secrets_and_ssn() -> None:
    fake_key = "AIza" + "SyD1234567890abcdefghijk"
    fake_bearer = "Bearer " + "eyJhbGciOiJIUzI1NiJ9"
    raw = f"Error with key {fake_key} and {fake_bearer} ssn 123-45-6789"
    cleaned, changed = redact_sensitive_text(raw)
    assert changed is True
    assert "AIzaSyD" not in cleaned
    assert "eyJhbGci" not in cleaned
    assert "123-45-6789" not in cleaned
    assert "[REDACTED_GOOGLE_API_KEY]" in cleaned
    assert "[REDACTED_SSN]" in cleaned


def test_before_tool_guardrail_blocks_destructive_without_approval() -> None:
    fake_tool = SimpleNamespace(name="rollback_deployment")
    fake_ctx = SimpleNamespace(state={})

    blocked = before_tool_guardrail_callback(
        tool=fake_tool,  # type: ignore[arg-type]
        args={"service_name": "payments-api", "target_version": "v2.18.3"},
        tool_context=fake_ctx,  # type: ignore[arg-type]
    )
    assert blocked is not None
    assert blocked["status"] == "blocked_pending_approval"
    assert metrics_registry.snapshot()["guardrail_blocks_total"] == 1


def test_before_tool_guardrail_allows_with_approval_token() -> None:
    fake_tool = SimpleNamespace(name="rollback_deployment")
    fake_ctx = SimpleNamespace(state={})

    allowed = before_tool_guardrail_callback(
        tool=fake_tool,  # type: ignore[arg-type]
        args={
            "service_name": "payments-api",
            "target_version": "v2.18.3",
            "human_approval_token": "ONCALL-ACK-412",
        },
        tool_context=fake_ctx,  # type: ignore[arg-type]
    )
    assert allowed is None


def test_after_tool_telemetry_records_counts_and_errors() -> None:
    fake_tool = SimpleNamespace(name="get_service_metrics")
    fake_ctx = SimpleNamespace(state={})
    before_tool_guardrail_callback(fake_tool, {}, fake_ctx)  # type: ignore[arg-type]
    after_tool_telemetry_callback(
        tool=fake_tool,  # type: ignore[arg-type]
        args={},
        tool_context=fake_ctx,  # type: ignore[arg-type]
        tool_response={"status": "error", "error": "boom"},
    )
    snap = metrics_registry.snapshot()
    assert snap["tool_calls_total"] == 1
    assert snap["tool_intents_total"] == 1
    assert snap["tool_errors_total"] == 1
    assert snap["tool_calls_by_name"]["get_service_metrics"] == 1
