"""SQLAlchemy models — canonical state lives in Postgres.

These mirror the Pydantic schemas in schemas.py but are the durable,
queryable, foreign-key-enforced source of truth. The Pydantic models are
what the API and Temporal workflows pass around in memory; these are what
gets written to disk.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(128))
    instruction: Mapped[str] = mapped_column(Text)
    environment_spec: Mapped[dict] = mapped_column(JSON)
    verifier_spec: Mapped[dict] = mapped_column(JSON)
    origin_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trials: Mapped[list["TrialRow"]] = relationship(back_populates="task")


class TrialRow(Base):
    __tablename__ = "trials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    agent_version: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    sandbox_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verifier_output: Mapped[dict] = mapped_column(JSON, default=dict)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    trace_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    task: Mapped["TaskRow"] = relationship(back_populates="trials")


class RegressionRunRow(Base):
    __tablename__ = "regression_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_version: Mapped[str] = mapped_column(String(64))
    candidate_version: Mapped[str] = mapped_column(String(64))
    task_ids: Mapped[list] = mapped_column(JSON)
    seeds_per_task: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # filled in once the significance test runs
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    significant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)


class FailureClusterRow(Base):
    """A cluster discovered by the mining service, before (or instead of)
    being promoted into a Task. Kept even for clusters that never become
    tasks, so the mining pipeline's output is auditable."""

    __tablename__ = "failure_clusters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    representative_summary: Mapped[str] = mapped_column(Text)
    source_trace_ids: Mapped[list] = mapped_column(JSON)
    size: Mapped[int] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    promoted_to_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
