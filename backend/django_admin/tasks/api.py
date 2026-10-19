"""DRF serializers + viewset: lets the Next.js dashboard drive the approval
queue through an API, not just through Django admin directly."""
from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from app.observability import metrics

from .models import PendingTask


class PendingTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingTask
        fields = "__all__"
        read_only_fields = ["external_id", "created_at", "reviewed_at"]


class PendingTaskViewSet(viewsets.ModelViewSet):
    queryset = PendingTask.objects.all().order_by("-origin_cluster_size", "-created_at")
    serializer_class = PendingTaskSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        task = self.get_object()
        if task.status != PendingTask.ReviewStatus.PENDING:
            return Response(
                {"error": f"Task already {task.status}"},
                status=400
            )
        task.status = PendingTask.ReviewStatus.APPROVED
        task.reviewed_by = request.data.get("reviewed_by", "unknown")
        task.review_notes = request.data.get("notes", "")
        task.reviewed_at = timezone.now()
        task.save()
        metrics.track_task_reviewed(reviewer=task.reviewed_by, task_id=str(task.external_id), decision="approved")
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        task = self.get_object()
        if task.status != PendingTask.ReviewStatus.PENDING:
            return Response(
                {"error": f"Task already {task.status}"},
                status=400
            )
        task.status = PendingTask.ReviewStatus.REJECTED
        task.reviewed_by = request.data.get("reviewed_by", "unknown")
        task.review_notes = request.data.get("notes", "")
        task.reviewed_at = timezone.now()
        task.save()
        metrics.track_task_reviewed(reviewer=task.reviewed_by, task_id=str(task.external_id), decision="rejected")
        return Response(self.get_serializer(task).data)
