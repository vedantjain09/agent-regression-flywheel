"""Django models for the back-office: the task-approval queue and verifier
overrides. This is deliberately a separate, CRUD-shaped data model from the
FastAPI side's Pydantic/SQLAlchemy schemas — in production both would point
at the same Postgres tables (Django's ORM can map onto the tasks table
defined in app/models/orm.py via `managed = False`), but the back-office's
job is reviewing and overriding what the mining pipeline produced, which is
a fundamentally forms-and-approval-workflow problem that Django handles
better out of the box than hand-building admin UI in FastAPI/React would.
"""
from __future__ import annotations

from django.db import models


class PendingTask(models.Model):
    """Mirrors app.schemas.task.Task for tasks still awaiting human review
    before they enter the regression suite (approved=False on the FastAPI
    side). An engineer approves, edits the verifier command, or rejects."""

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    external_id = models.UUIDField(unique=True, help_text="matches Task.id on the FastAPI/Postgres side")
    name = models.CharField(max_length=256)
    category = models.CharField(max_length=128)
    instruction = models.TextField()
    check_command = models.TextField(help_text="deterministic verifier command, editable before approval")

    origin_cluster_id = models.CharField(max_length=64, blank=True, null=True)
    origin_cluster_size = models.IntegerField(blank=True, null=True)
    origin_representative_summary = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.CharField(max_length=128, blank=True, null=True)
    review_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class VerifierOverride(models.Model):
    """When an on-call engineer disagrees with an LLM-as-judge verdict
    during review, the override is recorded here rather than silently
    changed, so the judge's calibration set (see schemas.task.
    LLMJudgeVerifierSpec) can be audited and improved over time."""

    task_external_id = models.UUIDField()
    trial_external_id = models.UUIDField()
    original_verdict = models.BooleanField()
    overridden_verdict = models.BooleanField()
    reason = models.TextField()
    overridden_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"override on trial {self.trial_external_id}: {self.original_verdict} -> {self.overridden_verdict}"
