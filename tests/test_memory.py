"""Unit tests for persistent SQLite long-term incident memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from sre_triage_agent.memory.incident_memory import IncidentMemoryStore
from sre_triage_agent.tools.memory_tools import (
    get_memory_store,
    save_incident_lesson,
    search_past_incidents,
)


def test_seeded_memory_recalls_payments_incident() -> None:
    res = search_past_incidents(service_name="payments-api", symptom_query="connection pool")
    assert res["status"] == "ok"
    assert res["count"] >= 1
    assert res["past_incidents"][0]["incident_id"] == "INC-2026-0198"


def test_memory_persists_across_store_restarts(tmp_path: Path) -> None:
    db_file = tmp_path / "persist.db"
    store_a = IncidentMemoryStore(db_path=db_file, seed=False)
    store_a.save_incident(
        incident_id="INC-2026-9999",
        service_name="billing-worker",
        severity="SEV2",
        symptoms="Queue backlog grew 10x",
        root_cause="Deadlock on invoice_locks table",
        resolution="Deployed lock-ordering patch",
        lessons_learned=["Enforce deterministic lock acquisition order"],
    )

    # Re-open from disk in a brand new instance
    store_b = IncidentMemoryStore(db_path=db_file, seed=False)
    assert store_b.count() == 1
    found = store_b.search(service_name="billing-worker", query="deadlock")
    assert len(found) == 1
    assert found[0]["incident_id"] == "INC-2026-9999"


@pytest.mark.asyncio
async def test_save_incident_lesson_tool_async_background() -> None:
    res = await save_incident_lesson(
        incident_id="INC-2026-0425",
        service_name="order-fulfillment",
        severity="SEV2",
        symptoms="Worker OOMKilled exit 137",
        root_cause="Kafka poll batch size increased 10x in v1.12.0",
        resolution="Rolled back v1.12.0",
        lessons_learned=["Load-test consumer memory before raising max_poll_records"],
    )
    assert res["status"] == "queued_async"
    await get_memory_store().flush_pending_writes()

    recalled = search_past_incidents(service_name="order-fulfillment", symptom_query="OOMKilled")
    assert recalled["past_incidents"][0]["incident_id"] == "INC-2026-0425"
