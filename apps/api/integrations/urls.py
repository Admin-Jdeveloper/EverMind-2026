"""
MediaCompile — Integrations URL Routing.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    IntegrationsCatalogueView,
    ConnectAccountView,
    ConnectedAccountViewSet,
    ImportExportView
)

router = DefaultRouter()
router.register(r'accounts', ConnectedAccountViewSet, basename='connected-account')

urlpatterns = [
    path('', IntegrationsCatalogueView.as_view(), name='integrations-catalogue'),
    path('connect/', ConnectAccountView.as_view(), name='integrations-connect'),
    path('<str:provider>/import/', ImportExportView.as_view(), name='integrations-import'),
    path('', include(router.urls)),
]
