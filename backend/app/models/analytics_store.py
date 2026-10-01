"""Two-tier analytics storage: DuckDB for fast local iteration, Snowflake as
the durable warehouse for the full trace history.

The intended workflow: while developing/tuning the clustering algorithm in
mining/cluster.py, pull a window of traces into a local Parquet file and
query it with DuckDB in milliseconds. Once the approach is settled, the same
query logic runs against Snowflake over the full history on a schedule.

Both backends are wrapped behind the same minimal interface so the mining
service doesn't care which one it's talking to.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

import duckdb


@dataclass
class TraceRecord:
    trace_id: str
    agent_version: str
    timestamp: str
    error_type: str | None
    embedding: list[float]
    summary: str


class TraceStore(abc.ABC):
    @abc.abstractmethod
    def query_recent(self, hours: int, limit: int = 10_000) -> list[TraceRecord]:
        ...

    @abc.abstractmethod
    def write_batch(self, records: list[TraceRecord]) -> int:
        ...


class DuckDBTraceStore(TraceStore):
    """Local/ad-hoc store, backed by a Parquet file or in-memory table.
    Used for fast iteration on the mining algorithm before it's promoted
    into the Snowflake batch pipeline below."""

    def __init__(self, path: str = ":memory:") -> None:
        self._con = duckdb.connect(path)
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id VARCHAR,
                agent_version VARCHAR,
                timestamp TIMESTAMP,
                error_type VARCHAR,
                embedding DOUBLE[],
                summary VARCHAR
            )
            """
        )

    def write_batch(self, records: list[TraceRecord]) -> int:
        if not records:
            return 0
        self._con.executemany(
            "INSERT INTO traces VALUES (?, ?, ?, ?, ?, ?)",
            [
                (r.trace_id, r.agent_version, r.timestamp, r.error_type, r.embedding, r.summary)
                for r in records
            ],
        )
        return len(records)

    def query_recent(self, hours: int, limit: int = 10_000) -> list[TraceRecord]:
        rows = self._con.execute(
            """
            SELECT trace_id, agent_version, timestamp, error_type, embedding, summary
            FROM traces
            WHERE timestamp >= now() - (? || ' hours')::interval
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [hours, limit],
        ).fetchall()
        return [
            TraceRecord(
                trace_id=r[0],
                agent_version=r[1],
                timestamp=str(r[2]),
                error_type=r[3],
                embedding=list(r[4]) if r[4] is not None else [],
                summary=r[5],
            )
            for r in rows
        ]


class SnowflakeTraceStore(TraceStore):
    """Durable warehouse target. Connection is lazy and optional — in
    environments without Snowflake credentials configured (e.g. local dev,
    CI) this degrades to a no-op so the rest of the pipeline is still
    testable without a live warehouse."""

    def __init__(self, connection_params: dict[str, Any] | None = None) -> None:
        self._connection_params = connection_params
        self._conn = None
        if connection_params:
            try:
                import snowflake.connector  # type: ignore

                self._conn = snowflake.connector.connect(**connection_params)
            except ImportError:
                self._conn = None

    @property
    def is_live(self) -> bool:
        return self._conn is not None

    def write_batch(self, records: list[TraceRecord]) -> int:
        if not self._conn:
            return 0  # no-op in dev/CI without credentials
        cur = self._conn.cursor()
        try:
            cur.executemany(
                "INSERT INTO traces (trace_id, agent_version, timestamp, error_type, embedding, summary) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (r.trace_id, r.agent_version, r.timestamp, r.error_type, r.embedding, r.summary)
                    for r in records
                ],
            )
            return len(records)
        finally:
            cur.close()

    def query_recent(self, hours: int, limit: int = 10_000) -> list[TraceRecord]:
        if not self._conn:
            return []
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT trace_id, agent_version, timestamp, error_type, embedding, summary "
                "FROM traces WHERE timestamp >= DATEADD(hour, %s, CURRENT_TIMESTAMP()) * -1 "
                "ORDER BY timestamp DESC LIMIT %s",
                (hours, limit),
            )
            return [
                TraceRecord(trace_id=r[0], agent_version=r[1], timestamp=str(r[2]), error_type=r[3], embedding=r[4], summary=r[5])
                for r in cur.fetchall()
            ]
        finally:
            cur.close()
