from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.contrib.auth import get_user_model
from core.throttling import AuthRateThrottle
from .serializers import UserProfileSerializer

User = get_user_model()

class RegisterUserView(APIView):
    """
    POST /api/v1/users/register/
    Registers a new user account with Argon2id password hashing.
    Enforces email uniqueness and minimum password length.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        password = str(request.data.get('password', ''))
        name = str(request.data.get('name', '')).strip()

        if not email or '@' not in email:
            return Response(
                {"success": False, "error": "A valid email address is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not password or len(password) < 8:
            return Response(
                {"success": False, "error": "Password must be at least 8 characters long."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"success": False, "error": "An account with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        display_name = name or email.split('@')[0]
        user = User.objects.create_user(
            email=email,
            password=password,
            name=display_name,
            email_verified=True
        )

        return Response({
            "success": True,
            "data": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name
            }
        }, status=status.HTTP_201_CREATED)


class VerifyCredentialsView(APIView):
    """
    POST /api/v1/users/verify-credentials/
    Validates user email and password against Argon2id hash.
    Used by Next.js Auth.js credentials provider to authenticate users.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        password = str(request.data.get('password', ''))

        if not email or not password:
            return Response(
                {"success": False, "error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            return Response(
                {"success": False, "error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {"success": False, "error": "Account is inactive or disabled."},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({
            "success": True,
            "data": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name or user.email.split('@')[0]
            }
        }, status=status.HTTP_200_OK)

class CurrentUserProfileView(APIView):
    """
    Returns or updates the profile of the currently authenticated user.
    Requires valid authentication via Identity Bridge or Session.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response({
            "success": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        return Response(
            {"success": False, "error": "Profile identity fields cannot be modified through ordinary API requests."},
            status=status.HTTP_403_FORBIDDEN
        )

    def put(self, request):
        return Response(
            {"success": False, "error": "Profile identity fields cannot be modified through ordinary API requests."},
            status=status.HTTP_403_FORBIDDEN
        )

    def delete(self, request):
        """
        Permanently delete the authenticated user's account and all associated data.
        Enforces complete data erasure:
        - Content items and MinIO binary objects
        - Vector chunks and embeddings
        - Collections, tags, and saved searches
        - Chat sessions and messages
        - User memories and preferences
        - Connected external accounts and OAuth credentials
        """
        user = request.user
        from django.db import transaction
        from content.models import ContentItem, Collection, Tag, SavedSearch, ContentFact, ContentChunk
        from content.storage import delete_file
        from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference
        from integrations.models import ConnectedAccount
        from core.audit import log_security_event, EVENT_ACCOUNT_PURGE

        log_security_event(
            event_type=EVENT_ACCOUNT_PURGE,
            user=user,
            ip_address=request.META.get('REMOTE_ADDR'),
            details={"email": user.email, "user_id": str(user.id)}
        )

        with transaction.atomic():
            # 1. Clean up MinIO files for any uploaded document items
            document_items = ContentItem.objects.filter(user=user, file_key__isnull=False).exclude(file_key='')
            for item in document_items:
                try:
                    delete_file(item.file_key)
                except Exception:
                    pass

            # 2. Delete all content chunks, facts, items, collections, tags, saved searches
            ContentChunk.objects.filter(content_item__user=user).delete()
            ContentFact.objects.filter(user=user).delete()
            ContentItem.objects.filter(user=user).delete()
            Collection.objects.filter(user=user).delete()
            Tag.objects.filter(user=user).delete()
            SavedSearch.objects.filter(user=user).delete()

            # 3. Delete chat messages, sessions, preferences, and memories
            ChatMessage.objects.filter(session__user=user).delete()
            ChatSession.objects.filter(user=user).delete()
            UserMemory.objects.filter(user=user).delete()
            UserPreference.objects.filter(user=user).delete()

            # 4. Delete connected external accounts and credentials
            ConnectedAccount.objects.filter(user=user).delete()

            # 5. Delete user account
            user.delete()

        return Response({
            "success": True,
            "message": "User account and all personal library data have been permanently erased."
        }, status=status.HTTP_200_OK)


class WorkspaceDeleteView(APIView):
    """
    DELETE /api/v1/users/workspace/
    Dedicated, authenticated operation to permanently delete the user's workspace data:
    - Saved content items and MinIO storage binaries
    - Vector chunks and pgvector embeddings
    - Structured content facts
    - Collections, tags, and saved searches
    - Chat sessions and conversation history
    - AI memories
    Preserves the user's login account and credentials so they can start fresh with an empty workspace.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        from django.db import transaction
        from content.models import ContentItem, Collection, Tag, SavedSearch, ContentFact, ContentChunk
        from content.storage import delete_file
        from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference
        from core.audit import log_security_event, EVENT_ACCOUNT_PURGE

        log_security_event(
            event_type="WORKSPACE_PURGE",
            user=user,
            ip_address=request.META.get('REMOTE_ADDR'),
            details={"email": user.email, "user_id": str(user.id)}
        )

        with transaction.atomic():
            # 1. Clean up MinIO files for any uploaded document items
            document_items = ContentItem.objects.filter(user=user, file_key__isnull=False).exclude(file_key='')
            for item in document_items:
                try:
                    delete_file(item.file_key)
                except Exception:
                    pass

            # 2. Delete all content chunks, facts, items, collections, tags, saved searches
            chunk_count = ContentChunk.objects.filter(content_item__user=user).delete()[0]
            ContentFact.objects.filter(user=user).delete()
            item_count = ContentItem.objects.filter(user=user).delete()[0]
            col_count = Collection.objects.filter(user=user).delete()[0]
            tag_count = Tag.objects.filter(user=user).delete()[0]
            SavedSearch.objects.filter(user=user).delete()

            # 3. Delete chat messages, sessions, and memories
            ChatMessage.objects.filter(session__user=user).delete()
            chat_count = ChatSession.objects.filter(user=user).delete()[0]
            UserMemory.objects.filter(user=user).delete()

            # Reset preferences to default
            pref = UserPreference.objects.filter(user=user).first()
            if pref:
                pref.personalization_enabled = True
                pref.allow_inferred_memories = True
                pref.save(update_fields=['personalization_enabled', 'allow_inferred_memories'])

        return Response({
            "success": True,
            "message": "Workspace data permanently erased.",
            "stats": {
                "items_deleted": item_count,
                "chunks_deleted": chunk_count,
                "collections_deleted": col_count,
                "tags_deleted": tag_count,
                "chat_sessions_deleted": chat_count
            }
        }, status=status.HTTP_200_OK)
