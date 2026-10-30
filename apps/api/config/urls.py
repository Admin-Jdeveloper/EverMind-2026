from django.contrib import admin
from django.urls import path, include
from core.views import HealthCheckView, DatabaseDiagnosticsView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', HealthCheckView.as_view(), name='api-health-check'),
    path('api/v1/diagnostics/db/', DatabaseDiagnosticsView.as_view(), name='database-diagnostics'),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/content/', include('content.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/integrations/', include('integrations.urls')),
]
