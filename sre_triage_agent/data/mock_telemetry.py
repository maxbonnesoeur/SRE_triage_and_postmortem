"""Realistic enterprise telemetry, deployment, and runbook fixtures.

Provides deterministic, self-contained operational data for three enterprise
incident scenarios so the agent can be demonstrated, tested, and evaluated
without requiring paid third-party observability credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlertRecord:
    alert_id: str
    incident_id: str
    service: str
    severity: str
    title: str
    status: str
    triggered_at: str
    summary: str


@dataclass
class LogEntry:
    timestamp: str
    service: str
    level: str
    message: str
    trace_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentRecord:
    deploy_id: str
    service: str
    version: str
    previous_version: str
    deployed_at: str
    author: str
    commit_sha: str
    change_summary: str
    status: str = "active"


@dataclass
class RunbookRecord:
    runbook_id: str
    service: str
    title: str
    triggers: list[str]
    diagnostic_steps: list[str]
    mitigation_steps: list[str]
    escalation_team: str


ALERTS: list[AlertRecord] = [
    AlertRecord(
        alert_id="ALT-9001",
        incident_id="INC-2026-0412",
        service="payments-api",
        severity="SEV1",
        title="High HTTP 503 Error Rate & P99 Latency Spike",
        status="firing",
        triggered_at="2026-11-23T14:12:00Z",
        summary=(
            "payments-api 5xx error rate jumped from 0.1% to 18.4% and p99 latency "
            "exceeded 4800ms (SLO: 400ms) across us-central1."
        ),
    ),
    AlertRecord(
        alert_id="ALT-9002",
        incident_id="INC-2026-0419",
        service="auth-gateway",
        severity="SEV2",
        title="Elevated HTTP 401 Failures & Session Cache Evictions",
        status="firing",
        triggered_at="2026-11-23T15:05:00Z",
        summary=(
            "auth-gateway unauthorized rate climbed to 9.2% while Redis session cache "
            "eviction rate spiked 14x."
        ),
    ),
    AlertRecord(
        alert_id="ALT-9003",
        incident_id="INC-2026-0425",
        service="order-fulfillment",
        severity="SEV2",
        title="Worker Pod OOMKills & Kafka Consumer Lag",
        status="firing",
        triggered_at="2026-11-23T15:40:00Z",
        summary=(
            "order-fulfillment workers restarted 11 times with exit code 137 (OOMKilled); "
            "orders.created consumer lag surpassed 42,000 messages."
        ),
    ),
]

LOGS: list[LogEntry] = [
    # payments-api logs
    LogEntry(
        timestamp="2026-11-23T14:10:12Z",
        service="payments-api",
        level="WARN",
        message="DB connection pool utilization reached 92% (46/50 active connections)",
        trace_id="tr-pay-101",
        metadata={"pool": "primary-pg", "active": 46, "max": 50},
    ),
    LogEntry(
        timestamp="2026-11-23T14:11:04Z",
        service="payments-api",
        level="ERROR",
        message="TimeoutError acquiring DB connection from pool after 3000ms in ledger_writer.py",
        trace_id="tr-pay-102",
        metadata={"pool": "primary-pg", "wait_ms": 3000, "version": "v2.18.4"},
    ),
    LogEntry(
        timestamp="2026-11-23T14:11:45Z",
        service="payments-api",
        level="ERROR",
        message="HTTP 503 Service Unavailable returned on POST /v2/charges (unclosed transaction detected)",
        trace_id="tr-pay-103",
        metadata={"endpoint": "/v2/charges", "status_code": 503, "version": "v2.18.4"},
    ),
    LogEntry(
        timestamp="2026-11-23T14:12:18Z",
        service="payments-api",
        level="ERROR",
        message="Circuit breaker OPEN for downstream ledger-db due to exhausted connection pool",
        trace_id="tr-pay-104",
        metadata={"circuit_breaker": "ledger-db", "state": "OPEN"},
    ),
    # auth-gateway logs
    LogEntry(
        timestamp="2026-11-23T15:02:11Z",
        service="auth-gateway",
        level="WARN",
        message="Redis session cluster memory at 98.7%; maxmemory-policy volatile-lru evicting active sessions",
        trace_id="tr-auth-201",
        metadata={"cluster": "redis-sessions-prod", "memory_pct": 98.7},
    ),
    LogEntry(
        timestamp="2026-11-23T15:04:33Z",
        service="auth-gateway",
        level="ERROR",
        message="Session token lookup miss for valid JWT; returning HTTP 401",
        trace_id="tr-auth-202",
        metadata={"reason": "cache_evicted", "version": "v4.9.1"},
    ),
    # order-fulfillment logs
    LogEntry(
        timestamp="2026-11-23T15:38:05Z",
        service="order-fulfillment",
        level="WARN",
        message="Kafka poll batch size configured to 2000 messages; heap usage at 91%",
        trace_id="tr-ord-301",
        metadata={"batch_size": 2000, "heap_pct": 91},
    ),
    LogEntry(
        timestamp="2026-11-23T15:39:42Z",
        service="order-fulfillment",
        level="ERROR",
        message="Container worker-7f8d terminated with OOMKilled (Exit Code 137) during batch hydration",
        trace_id="tr-ord-302",
        metadata={"exit_code": 137, "version": "v1.12.0"},
    ),
]

METRICS: dict[str, dict[str, Any]] = {
    "payments-api": {
        "service": "payments-api",
        "window": "last_15m",
        "error_rate_pct": 18.4,
        "baseline_error_rate_pct": 0.12,
        "p99_latency_ms": 4820,
        "baseline_p99_latency_ms": 210,
        "rps": 1420,
        "cpu_utilization_pct": 41.0,
        "memory_utilization_pct": 63.0,
        "db_pool_saturation_pct": 100.0,
        "active_replicas": 6,
    },
    "auth-gateway": {
        "service": "auth-gateway",
        "window": "last_15m",
        "error_rate_pct": 9.2,
        "baseline_error_rate_pct": 0.4,
        "p99_latency_ms": 340,
        "baseline_p99_latency_ms": 85,
        "rps": 4850,
        "cpu_utilization_pct": 54.0,
        "memory_utilization_pct": 58.0,
        "redis_evictions_per_sec": 620,
        "active_replicas": 10,
    },
    "order-fulfillment": {
        "service": "order-fulfillment",
        "window": "last_15m",
        "error_rate_pct": 6.8,
        "baseline_error_rate_pct": 0.2,
        "p99_latency_ms": 2100,
        "baseline_p99_latency_ms": 450,
        "kafka_consumer_lag": 42800,
        "cpu_utilization_pct": 68.0,
        "memory_utilization_pct": 97.5,
        "oom_kills_15m": 11,
        "active_replicas": 4,
    },
}

DEPLOYMENTS: list[DeploymentRecord] = [
    DeploymentRecord(
        deploy_id="DEP-7841",
        service="payments-api",
        version="v2.18.4",
        previous_version="v2.18.3",
        deployed_at="2026-11-23T14:04:00Z",
        author="ci-release-bot",
        commit_sha="a91f3c2",
        change_summary=(
            "Refactor async ledger_writer transaction handling; introduced manual session "
            "checkout without guaranteed context-manager release on retry paths."
        ),
    ),
    DeploymentRecord(
        deploy_id="DEP-7830",
        service="payments-api",
        version="v2.18.3",
        previous_version="v2.18.2",
        deployed_at="2026-11-21T18:20:00Z",
        author="ci-release-bot",
        commit_sha="4d7e11a",
        change_summary="Update Stripe webhook retry backoff jitter.",
        status="superseded",
    ),
    DeploymentRecord(
        deploy_id="DEP-7845",
        service="auth-gateway",
        version="v4.9.1",
        previous_version="v4.9.0",
        deployed_at="2026-11-23T14:55:00Z",
        author="ci-release-bot",
        commit_sha="c82b90e",
        change_summary="Extend default session TTL from 24h to 14d without resizing Redis cluster.",
    ),
    DeploymentRecord(
        deploy_id="DEP-7849",
        service="order-fulfillment",
        version="v1.12.0",
        previous_version="v1.11.8",
        deployed_at="2026-11-23T15:30:00Z",
        author="ci-release-bot",
        commit_sha="f03a77d",
        change_summary="Increase Kafka consumer max_poll_records from 200 to 2000 for throughput.",
    ),
]

RUNBOOKS: list[RunbookRecord] = [
    RunbookRecord(
        runbook_id="RB-PAY-001",
        service="payments-api",
        title="Payments API DB Connection Pool Exhaustion & 503 Recovery",
        triggers=["503", "connection pool", "ledger-db", "p99 latency"],
        diagnostic_steps=[
            "Check db_pool_saturation_pct and recent deployments within 30 minutes.",
            "Inspect ERROR logs for unclosed transactions or pool acquisition timeouts.",
        ],
        mitigation_steps=[
            "If a deployment occurred within 30 minutes of onset, rollback to previous_version.",
            "Alternatively disable feature flag `async_ledger_retry_v2` if rollback is blocked.",
            "Verify p99 latency drops below 400ms and error rate < 0.5% for 5 consecutive minutes.",
        ],
        escalation_team="payments-oncall@example.com",
    ),
    RunbookRecord(
        runbook_id="RB-AUTH-002",
        service="auth-gateway",
        title="Auth Gateway Redis Session Eviction & 401 Spike",
        triggers=["401", "redis", "eviction", "session"],
        diagnostic_steps=[
            "Inspect redis_evictions_per_sec and recent TTL or auth-gateway config rollouts.",
            "Confirm JWT signing keys have not rotated unexpectedly.",
        ],
        mitigation_steps=[
            "Rollback recent session TTL config deployment to previous_version.",
            "Scale auth-gateway only if CPU > 80%; otherwise prioritize cache pressure relief.",
        ],
        escalation_team="identity-sre@example.com",
    ),
    RunbookRecord(
        runbook_id="RB-ORD-003",
        service="order-fulfillment",
        title="Order Fulfillment Worker OOMKilled & Consumer Lag",
        triggers=["oom", "137", "kafka", "consumer lag", "batch"],
        diagnostic_steps=[
            "Check oom_kills_15m, memory_utilization_pct, and recent batch-size config changes.",
        ],
        mitigation_steps=[
            "Rollback deployment that increased batch size or toggle `high_throughput_batch_mode` off.",
            "Temporarily scale worker replicas to drain Kafka consumer lag safely.",
        ],
        escalation_team="fulfillment-platform@example.com",
    ),
]

# Mutable runtime state for simulated safe/guarded operational actions
FEATURE_FLAGS: dict[str, dict[str, bool]] = {
    "payments-api": {"async_ledger_retry_v2": True, "strict_idempotency": True},
    "auth-gateway": {"extended_session_ttl_14d": True, "mfa_step_up": True},
    "order-fulfillment": {"high_throughput_batch_mode": True},
}

INCIDENT_TICKETS: list[dict[str, Any]] = []
