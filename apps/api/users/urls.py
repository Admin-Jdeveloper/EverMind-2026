from django.urls import path
from .views import CurrentUserProfileView, RegisterUserView, VerifyCredentialsView, WorkspaceDeleteView

urlpatterns = [
    path('me/', CurrentUserProfileView.as_view(), name='current-user-profile'),
    path('profile/', CurrentUserProfileView.as_view(), name='user-profile'),
    path('workspace/', WorkspaceDeleteView.as_view(), name='workspace-delete'),
    path('register/', RegisterUserView.as_view(), name='register-user'),
    path('verify-credentials/', VerifyCredentialsView.as_view(), name='verify-credentials'),
]
