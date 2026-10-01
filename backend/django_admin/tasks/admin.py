from django.contrib import admin

from .models import PendingTask, VerifierOverride


@admin.action(description="Approve selected tasks")
def approve_tasks(modeladmin, request, queryset):
    from django.utils import timezone

    queryset.update(status=PendingTask.ReviewStatus.APPROVED, reviewed_at=timezone.now())


@admin.action(description="Reject selected tasks")
def reject_tasks(modeladmin, request, queryset):
    from django.utils import timezone

    queryset.update(status=PendingTask.ReviewStatus.REJECTED, reviewed_at=timezone.now())


@admin.register(PendingTask)
class PendingTaskAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status", "origin_cluster_size", "created_at")
    list_filter = ("status", "category")
    search_fields = ("name", "instruction", "origin_cluster_id")
    actions = [approve_tasks, reject_tasks]
    readonly_fields = ("external_id", "created_at", "origin_cluster_id", "origin_cluster_size", "origin_representative_summary")


@admin.register(VerifierOverride)
class VerifierOverrideAdmin(admin.ModelAdmin):
    list_display = ("task_external_id", "trial_external_id", "original_verdict", "overridden_verdict", "overridden_by", "created_at")
    search_fields = ("task_external_id", "trial_external_id", "overridden_by")
