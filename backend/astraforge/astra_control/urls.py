from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AstraControlSessionViewSet

router = DefaultRouter()
router.register(r"sessions", AstraControlSessionViewSet, basename="astra-control-session")

urlpatterns = [
    path("", include(router.urls)),
]
