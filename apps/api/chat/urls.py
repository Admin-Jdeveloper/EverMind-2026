from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChatSessionViewSet,
    UserMemoryViewSet,
    UserPreferenceView,
    TopicSummariesView
)

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')
router.register(r'memories', UserMemoryViewSet, basename='chat-memory')

urlpatterns = [
    path('preferences/', UserPreferenceView.as_view(), name='chat-preferences'),
    path('topics/', TopicSummariesView.as_view(), name='chat-topics'),
    path('', include(router.urls)),
]
