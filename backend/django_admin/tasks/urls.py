from rest_framework.routers import DefaultRouter

from .api import PendingTaskViewSet

router = DefaultRouter()
router.register(r"pending-tasks", PendingTaskViewSet, basename="pending-task")

urlpatterns = router.urls
