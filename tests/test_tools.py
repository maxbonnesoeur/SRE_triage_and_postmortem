"""Unit tests for telemetry, remediation, and artifact tools."""

from __future__ import annotations

import pytest

from sre_triage_agent.tools.artifact_tools import save_postmortem_artifact
from sre_triage_agent.tools.remediation_tools import (
    create_incident_ticket,
    scale_service_replicas,
    toggle_feature_flag,
)
from sre_triage_agent.tools.telemetry_tools import (
    get_recent_deployments,
    get_service_metrics,
    list_active_alerts,
    query_service_logs,
    search_runbooks,
)


def test_list_active_alerts_all_and_filtered() -> None:
    all_alerts = list_active_alerts()
    assert all_alerts["status"] == "ok"
    assert all_alerts["count"] == 3

    pay_alerts = list_active_alerts("payments-api")
    assert pay_alerts["count"] == 1
    assert pay_alerts["alerts"][0]["incident_id"] == "INC-2026-0412"


def test_query_service_logs_filtering_and_validation() -> None:
    res = query_service_logs("payments-api", level="ERROR", keyword="503")
    assert res["status"] == "ok"
    assert res["count"] == 1
    assert "503" in res["logs"][0]["message"]

    err = query_service_logs("")
    assert err["status"] == "error"


def test_get_service_metrics_and_unknown_service() -> None:
    ok = get_service_metrics("payments-api")
    assert ok["status"] == "ok"
    assert ok["metrics"]["db_pool_saturation_pct"] == 100.0

    bad = get_service_metrics("nonexistent-svc")
    assert bad["status"] == "error"
    assert "available_services" in bad


def test_get_recent_deployments_and_runbooks() -> None:
    deploys = get_recent_deployments("payments-api")
    assert deploys["status"] == "ok"
    assert deploys["deployments"][0]["version"] == "v2.18.4"

    rbs = search_runbooks(service_name="payments-api", symptom_query="connection pool")
    assert rbs["status"] == "ok"
    assert rbs["runbooks"][0]["runbook_id"] == "RB-PAY-001"


def test_remediation_tools_ticket_flag_and_bounds() -> None:
    ticket = create_incident_ticket(
        incident_id="INC-2026-0412",
        service_name="payments-api",
        severity="sev1",
        title="Payments 503 outage",
        summary="Pool exhausted after v2.18.4",
    )
    assert ticket["status"] == "ok"
    assert ticket["ticket"]["severity"] == "SEV1"

    flag = toggle_feature_flag(
        service_name="payments-api",
        flag_name="async_ledger_retry_v2",
        enabled=False,
        reason="Mitigate DB connection leak",
    )
    assert flag["status"] == "ok"
    assert flag["new_value"] is False

    # Restore flag for test hygiene
    toggle_feature_flag("payments-api", "async_ledger_retry_v2", True, "test restore")

    out_of_bounds = scale_service_replicas("payments-api", desired_replicas=999, reason="test")
    assert out_of_bounds["status"] == "error"


@pytest.mark.asyncio
async def test_save_postmortem_artifact_markdown_rendering() -> None:
    result = await save_postmortem_artifact(
        incident_id="INC-2026-0412",
        title="Payments API 503 Outage",
        severity="SEV1",
        service_name="payments-api",
        impact_summary="18.4% of checkout requests failed with HTTP 503.",
        root_cause="Connection pool leak in v2.18.4 ledger_writer.py.",
        timeline=["14:04Z v2.18.4 deployed", "14:12Z SEV1 alert fired"],
        resolution_summary="Rolled back to v2.18.3 and confirmed p99 < 400ms.",
        action_items=["Add async context manager regression test"],
        lessons_learned=["Gate DB pool saturation alerts at 80%"],
        tool_context=None,
    )
    assert result["status"] == "ok"
    assert result["filename"] == "postmortem_inc-2026-0412.md"
    assert "# Blameless Postmortem: INC-2026-0412" in result["markdown"]
