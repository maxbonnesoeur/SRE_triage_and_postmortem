"""Session and Memory service factory for ADK Runner and FastAPI server."""

from __future__ import annotations

import logging
from typing import Any

from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

from sre_triage_agent.config import get_settings

logger = logging.getLogger(__name__)


def build_session_service(use_database: bool = False) -> Any:
    """Create an ADK SessionService with graceful fallback to InMemorySessionService.

    When `use_database=True`, attempts to instantiate `DatabaseSessionService`
    using `Settings.session_db_url` (e.g., SQLite or Cloud SQL Postgres).
    """
    if use_database:
        settings = get_settings()
        try:
            from google.adk.sessions import DatabaseSessionService

            logger.info("Initializing DatabaseSessionService at %s", settings.session_db_url)
            return DatabaseSessionService(db_url=settings.session_db_url)
        except Exception as exc:  # pragma: no cover - optional driver fallback
            logger.warning(
                "Falling back to InMemorySessionService (DatabaseSessionService unavailable: %s)",
                exc,
            )
    return InMemorySessionService()


def build_memory_service() -> InMemoryMemoryService:
    """Create the ADK MemoryService for session-to-memory ingestion."""
    return InMemoryMemoryService()
