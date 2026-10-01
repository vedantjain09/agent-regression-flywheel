"""Tests for the Django back-office task-approval API."""
import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from .models import PendingTask


class PendingTaskApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.task = PendingTask.objects.create(
            external_id=uuid.uuid4(),
            name="auto-cluster-42",
            category="auto-generated",
            instruction="Reproduce and resolve: agent times out on large file reads",
            check_command="python verify_large_file_read.py",
            origin_cluster_id="cluster-42",
            origin_cluster_size=7,
            origin_representative_summary="agent repeatedly times out on large file reads",
        )

    def test_list_pending_tasks(self):
        response = self.client.get("/api/pending-tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]) if "results" in response.data else len(response.data), 1)

    def test_filter_by_status(self):
        PendingTask.objects.create(
            external_id=uuid.uuid4(),
            name="already-approved",
            category="manual",
            instruction="x",
            check_command="true",
            status=PendingTask.ReviewStatus.APPROVED,
        )
        response = self.client.get("/api/pending-tasks/?status=pending")
        data = response.data["results"] if "results" in response.data else response.data
        self.assertTrue(all(t["status"] == "pending" for t in data))

    def test_approve_action_sets_status_and_reviewer(self):
        response = self.client.post(
            f"/api/pending-tasks/{self.task.id}/approve/",
            {"reviewed_by": "vedant", "notes": "looks like a real recurring failure"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, PendingTask.ReviewStatus.APPROVED)
        self.assertEqual(self.task.reviewed_by, "vedant")
        self.assertIsNotNone(self.task.reviewed_at)

    def test_reject_action_sets_status(self):
        response = self.client.post(
            f"/api/pending-tasks/{self.task.id}/reject/",
            {"reviewed_by": "vedant", "notes": "too flaky, likely infra noise not a real bug"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, PendingTask.ReviewStatus.REJECTED)

    def test_external_id_is_read_only_on_update(self):
        original_id = self.task.external_id
        response = self.client.patch(
            f"/api/pending-tasks/{self.task.id}/",
            {"external_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.external_id, original_id)
