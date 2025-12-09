"""Root URL configuration for AstraForge."""

from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from astraforge.interfaces.frontend import views as frontend_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/", include("astraforge.interfaces.rest.urls")),
]

urlpatterns += [
    re_path(r"^assets/(?P<path>.*)$", frontend_views.frontend_assets, name="frontend-assets"),
    re_path(r"^(?!api(?:/|$))(?P<resource>.*)$", frontend_views.frontend_index, name="frontend-app"),
]
