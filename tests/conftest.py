"""Shared pytest fixtures for isolated testing."""

from __future__ import annotations

from pathlib import Path

import pytest

from sre_triage_agent.memory.incident_memory import IncidentMemoryStore
from sre_triage_agent.observability import metrics_registry
from sre_triage_agent.tools.memory_tools import set_memory_store


@pytest.fixture(autouse=True)
def isolated_memory_and_metrics(tmp_path: Path):
    """Provide a fresh SQLite memory store and clean metrics registry for every test."""
    db_path = tmp_path / "test_incident_memory.db"
    store = IncidentMemoryStore(db_path=db_path, seed=True)
    set_memory_store(store)
    metrics_registry.reset()
    yield store
    set_memory_store(None)
    metrics_registry.reset()
