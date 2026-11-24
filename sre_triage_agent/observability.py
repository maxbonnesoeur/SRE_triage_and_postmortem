"""OpenTelemetry tracing, structured JSON logging, and runtime metrics registry."""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from sre_triage_agent.config import get_settings

_observability_configured = False
_lock = threading.Lock()


class StructuredJsonFormatter(logging.Formatter):
    """Emits Cloud Logging-compatible structured JSON log lines."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        span_ctx = trace.get_current_span().get_span_context()
        trace_id = format(span_ctx.trace_id, "032x") if span_ctx and span_ctx.is_valid else None
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if trace_id:
            payload["trace_id"] = trace_id
        for key in (
            "agent_name",
            "tool_name",
            "phase",
            "intended_args",
            "latency_ms",
            "status",
            "incident_id",
            "guardrail",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class MetricsRegistry:
    """Thread-safe runtime telemetry counters exposed via API and callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.tool_calls_total: int = 0
            self.tool_intents_total: int = 0
            self.tool_errors_total: int = 0
            self.guardrail_blocks_total: int = 0
            self.pii_redactions_total: int = 0
            self.async_memory_tasks_total: int = 0
            self.model_calls_total: int = 0
            self.prompt_tokens_total: int = 0
            self.output_tokens_total: int = 0
            self.tool_calls_by_name: dict[str, int] = {}
            self.tool_latency_ms_sum: dict[str, float] = {}

    def record_tool_intent(self) -> None:
        with self._lock:
            self.tool_intents_total += 1

    def record_async_memory_task(self) -> None:
        with self._lock:
            self.async_memory_tasks_total += 1

    def record_tool_call(self, tool_name: str, latency_ms: float = 0.0, is_error: bool = False) -> None:
        with self._lock:
            self.tool_calls_total += 1
            self.tool_calls_by_name[tool_name] = self.tool_calls_by_name.get(tool_name, 0) + 1
            self.tool_latency_ms_sum[tool_name] = (
                self.tool_latency_ms_sum.get(tool_name, 0.0) + latency_ms
            )
            if is_error:
                self.tool_errors_total += 1

    def record_guardrail_block(self) -> None:
        with self._lock:
            self.guardrail_blocks_total += 1

    def record_pii_redaction(self) -> None:
        with self._lock:
            self.pii_redactions_total += 1

    def record_model_call(self, prompt_tokens: int = 0, output_tokens: int = 0) -> None:
        with self._lock:
            self.model_calls_total += 1
            self.prompt_tokens_total += max(0, prompt_tokens)
            self.output_tokens_total += max(0, output_tokens)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_latency = {
                name: round(self.tool_latency_ms_sum.get(name, 0.0) / count, 2)
                for name, count in self.tool_calls_by_name.items()
                if count > 0
            }
            return {
                "tool_calls_total": self.tool_calls_total,
                "tool_intents_total": self.tool_intents_total,
                "tool_errors_total": self.tool_errors_total,
                "guardrail_blocks_total": self.guardrail_blocks_total,
                "pii_redactions_total": self.pii_redactions_total,
                "async_memory_tasks_total": self.async_memory_tasks_total,
                "model_calls_total": self.model_calls_total,
                "prompt_tokens_total": self.prompt_tokens_total,
                "output_tokens_total": self.output_tokens_total,
                "tool_calls_by_name": dict(self.tool_calls_by_name),
                "tool_avg_latency_ms": avg_latency,
            }


metrics_registry = MetricsRegistry()


def configure_observability() -> trace.Tracer:
    """Configure structured JSON logging and OpenTelemetry tracing once per process."""
    global _observability_configured
    settings = get_settings()

    with _lock:
        if not _observability_configured:
            root_logger = logging.getLogger("sre_triage_agent")
            root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
            if not root_logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(StructuredJsonFormatter(settings.service_name))
                root_logger.addHandler(handler)
                root_logger.propagate = False

            resource = Resource.create({"service.name": settings.service_name})
            provider = TracerProvider(resource=resource)

            if settings.otel_exporter == "console":
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            elif settings.otel_exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
                )
            elif settings.otel_exporter == "gcp_trace":  # pragma: no cover - cloud only
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))

            trace.set_tracer_provider(provider)
            _observability_configured = True

    return trace.get_tracer(settings.service_name)


def get_tracer() -> trace.Tracer:
    """Return the configured OpenTelemetry tracer."""
    return trace.get_tracer(get_settings().service_name)
