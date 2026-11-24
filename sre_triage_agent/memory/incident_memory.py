"""Persistent SQLite-backed long-term incident memory store.

Provides cross-session institutional memory so the SRE Triage Agent learns from
historical outages, root causes, and verified mitigations across restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sre_triage_agent.config import get_settings

logger = logging.getLogger("sre_triage_agent.memory")

SEED_INCIDENTS: list[dict[str, Any]] = [
    {
        "incident_id": "INC-2026-0198",
        "service_name": "payments-api",
        "severity": "SEV1",
        "symptoms": "HTTP 503 spike and p99 latency > 4s; DB connection pool saturated at 100%",
        "root_cause": (
            "Unclosed SQLAlchemy session inside retry block leaked PostgreSQL pool connections "
            "under peak checkout traffic."
        ),
        "resolution": "Rolled back release to previous stable tag and added pool leak unit test.",
        "lessons_learned": [
            "Always wrap DB sessions in async context managers on retry paths.",
            "Alert when DB pool saturation exceeds 80% for 2 minutes.",
        ],
        "resolved_at": "2026-09-14T19:42:00Z",
    },
    {
        "incident_id": "INC-2026-0274",
        "service_name": "auth-gateway",
        "severity": "SEV2",
        "symptoms": "Elevated 401 responses and sudden spike in Redis session key evictions",
        "root_cause": "Session TTL configuration change doubled memory footprint without scaling Redis.",
        "resolution": "Reverted session TTL config and enabled memory-headroom preflight checks.",
        "lessons_learned": [
            "Capacity-test Redis memory before extending session TTLs.",
        ],
        "resolved_at": "2026-10-08T11:15:00Z",
    },
]


class IncidentMemoryStore:
    """SQLite-backed long-term memory for past incidents and postmortem lessons."""

    def __init__(self, db_path: Path | str | None = None, seed: bool = True) -> None:
        resolved_path = Path(db_path) if db_path is not None else get_settings().memory_db_path
        self.db_path = resolved_path
        self._memory_conn: sqlite3.Connection | None = None
        self._pending_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        if str(self.db_path) == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        if seed:
            self._seed_if_empty()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_memories (
                    incident_id TEXT PRIMARY KEY,
                    service_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    symptoms TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    lessons_learned_json TEXT NOT NULL,
                    resolved_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_incident_memories_service
                ON incident_memories(service_name)
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM incident_memories").fetchone()[0]
            if count == 0:
                for item in SEED_INCIDENTS:
                    self._upsert_row(conn, item)

    @staticmethod
    def _upsert_row(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO incident_memories (
                incident_id, service_name, severity, symptoms,
                root_cause, resolution, lessons_learned_json, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                service_name=excluded.service_name,
                severity=excluded.severity,
                symptoms=excluded.symptoms,
                root_cause=excluded.root_cause,
                resolution=excluded.resolution,
                lessons_learned_json=excluded.lessons_learned_json,
                resolved_at=excluded.resolved_at
            """,
            (
                record["incident_id"],
                record["service_name"].strip().lower(),
                record["severity"].strip().upper(),
                record["symptoms"],
                record["root_cause"],
                record["resolution"],
                json.dumps(record.get("lessons_learned", [])),
                record.get("resolved_at") or datetime.now(UTC).isoformat(),
            ),
        )

    def save_incident(
        self,
        incident_id: str,
        service_name: str,
        severity: str,
        symptoms: str,
        root_cause: str,
        resolution: str,
        lessons_learned: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist or update a resolved incident in long-term memory."""
        record = {
            "incident_id": incident_id.strip(),
            "service_name": service_name.strip().lower(),
            "severity": severity.strip().upper(),
            "symptoms": symptoms.strip(),
            "root_cause": root_cause.strip(),
            "resolution": resolution.strip(),
            "lessons_learned": lessons_learned or [],
            "resolved_at": datetime.now(UTC).isoformat(),
        }
        with self._connect() as conn:
            self._upsert_row(conn, record)
        return record

    def search(
        self,
        service_name: str = "",
        query: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant historical incidents ranked by service & token overlap."""
        norm_service = service_name.strip().lower()
        terms = [t.lower() for t in query.split() if len(t) >= 2]

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM incident_memories ORDER BY resolved_at DESC"
            ).fetchall()

        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            item = {
                "incident_id": row["incident_id"],
                "service_name": row["service_name"],
                "severity": row["severity"],
                "symptoms": row["symptoms"],
                "root_cause": row["root_cause"],
                "resolution": row["resolution"],
                "lessons_learned": json.loads(row["lessons_learned_json"]),
                "resolved_at": row["resolved_at"],
            }
            score = 0
            if norm_service and item["service_name"] == norm_service:
                score += 6
            haystack = " ".join(
                [
                    item["service_name"],
                    item["symptoms"],
                    item["root_cause"],
                    item["resolution"],
                    *item["lessons_learned"],
                ]
            ).lower()
            for term in terms:
                if term in haystack:
                    score += 2
            if score > 0 or (not norm_service and not terms):
                scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[: max(1, min(limit, 20))]]

    def count(self) -> int:
        """Return total number of stored incident memories."""
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM incident_memories").fetchone()[0])

    async def save_incident_async(
        self,
        incident_id: str,
        service_name: str,
        severity: str,
        symptoms: str,
        root_cause: str,
        resolution: str,
        lessons_learned: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a resolved incident asynchronously without blocking the event loop."""
        return await asyncio.to_thread(
            self.save_incident,
            incident_id,
            service_name,
            severity,
            symptoms,
            root_cause,
            resolution,
            lessons_learned,
        )

    def schedule_save_incident(
        self,
        incident_id: str,
        service_name: str,
        severity: str,
        symptoms: str,
        root_cause: str,
        resolution: str,
        lessons_learned: list[str] | None = None,
    ) -> asyncio.Task[dict[str, Any]]:
        """Offload incident memory consolidation to a tracked async background task."""
        task: asyncio.Task[dict[str, Any]] = asyncio.create_task(
            self.save_incident_async(
                incident_id=incident_id,
                service_name=service_name,
                severity=severity,
                symptoms=symptoms,
                root_cause=root_cause,
                resolution=resolution,
                lessons_learned=lessons_learned,
            ),
            name=f"memory-save-{incident_id}",
        )
        self._pending_tasks.add(task)

        def _on_done(done_task: asyncio.Task[dict[str, Any]]) -> None:
            self._pending_tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                logger.error(
                    "Background incident memory consolidation failed: %s",
                    exc,
                    extra={"incident_id": incident_id, "status": "error"},
                )

        task.add_done_callback(_on_done)
        return task

    async def flush_pending_writes(self) -> None:
        """Await all in-flight background memory consolidation tasks."""
        if not self._pending_tasks:
            return
        await asyncio.gather(*list(self._pending_tasks), return_exceptions=True)
