"""
MediaCompile — Integrations REST Views.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Social and External Integrations)

Enforces:
1. Multi-Tenant Isolation: Users can view, sync, and disconnect only their own accounts.
2. Token Secrecy: Encrypted tokens are never returned in responses.
3. Live Sync & File Import: Supports background sync and user-provided export processing.
"""

import logging
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from .models import ConnectedAccount
from .serializers import (
    ConnectedAccountSerializer,
    ConnectAccountInputSerializer,
    ImportFileUploadSerializer
)
from .connectors.registry import get_connector, list_supported_connectors

logger = logging.getLogger(__name__)

class IntegrationsCatalogueView(APIView):
    """
    Catalogue endpoint returning available platforms, developer policy status,
    and the authenticated user's current connection state for each.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalogue = list_supported_connectors()
        user_accounts = ConnectedAccount.objects.filter(user=request.user)
        accounts_by_provider = {acc.provider: ConnectedAccountSerializer(acc).data for acc in user_accounts}

        for item in catalogue:
            p_id = item["id"]
            if p_id in accounts_by_provider:
                item["connected_account"] = accounts_by_provider[p_id]
                item["is_connected"] = accounts_by_provider[p_id]["status"] == ConnectedAccount.STATUS_ACTIVE
            else:
                item["connected_account"] = None
                item["is_connected"] = False

        return Response({
            "count": len(catalogue),
            "integrations": catalogue
        }, status=status.HTTP_200_OK)


class ConnectAccountView(APIView):
    """Register or update an authorized third-party connection with encrypted credentials."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConnectAccountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        provider = data['provider'].lower().strip()
        connector = get_connector(provider)
        if not connector:
            return Response(
                {"error": f"Provider '{provider}' is not supported for automated API connection."},
                status=status.HTTP_400_BAD_REQUEST
            )

        credentials = data['credentials']
        if not connector.test_connection(credentials):
            return Response(
                {"error": f"Failed to authenticate with {connector.display_name}. Please verify your access token."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create or update connected account
        account, created = ConnectedAccount.objects.get_or_create(
            user=request.user,
            provider=provider,
            external_account_id=data['external_account_id'],
            defaults={
                "account_name": data.get('account_name', ''),
                "account_email": data.get('account_email', ''),
                "granted_scopes": data.get('granted_scopes', connector.required_scopes),
                "status": ConnectedAccount.STATUS_ACTIVE,
            }
        )

        account.account_name = data.get('account_name', account.account_name)
        account.account_email = data.get('account_email', account.account_email)
        account.granted_scopes = data.get('granted_scopes', account.granted_scopes)
        account.status = ConnectedAccount.STATUS_ACTIVE
        account.set_credentials(credentials)
        account.save()

        return Response(
            ConnectedAccountSerializer(account).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class ConnectedAccountViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for user's connected third-party accounts.
    Strictly isolated to request.user.
    """
    serializer_class = ConnectedAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ConnectedAccount.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='sync')
    def sync_account(self, request, pk=None):
        """Execute on-demand sync for this connected account."""
        account = self.get_object()
        if account.status == ConnectedAccount.STATUS_REVOKED:
            return Response({"error": "Account is disconnected / revoked."}, status=status.HTTP_400_BAD_REQUEST)

        connector = get_connector(account.provider)
        if not connector:
            return Response({"error": f"Connector for {account.provider} not available."}, status=status.HTTP_400_BAD_REQUEST)

        # Execute sync
        creds = account.get_credentials()
        account.sync_status = 'syncing'
        account.save(update_fields=['sync_status'])

        result = connector.sync_content(request.user, credentials=creds)
        if result.success:
            account.sync_status = 'success'
            account.items_synced_count += result.items_synced
            account.error_message = ''
            account.save(update_fields=['sync_status', 'items_synced_count', 'error_message', 'updated_at'])
            return Response({
                "status": "success",
                "items_synced": result.items_synced,
                "items_skipped": result.items_skipped,
                "account": ConnectedAccountSerializer(account).data
            }, status=status.HTTP_200_OK)
        else:
            if result.details.get("status") == "expired":
                account.status = ConnectedAccount.STATUS_EXPIRED
            account.sync_status = 'failed'
            account.error_message = result.error_message or "Sync failed"
            account.save(update_fields=['status', 'sync_status', 'error_message', 'updated_at'])
            return Response({
                "status": "failed",
                "error": result.error_message,
                "account": ConnectedAccountSerializer(account).data
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='disconnect')
    def disconnect_account(self, request, pk=None):
        """Disconnect account, wipe encrypted tokens, and revoke access."""
        account = self.get_object()
        account.disconnect()
        return Response(ConnectedAccountSerializer(account).data, status=status.HTTP_200_OK)


class ImportExportView(APIView):
    """
    Import user-provided export archives (Netscape HTML bookmarks, Reddit CSV/JSON, Google Takeout JSON).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, provider):
        connector = get_connector(provider.lower().strip())
        if not connector:
            return Response({"error": f"Provider '{provider}' does not support file imports."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ImportFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data['file']

        raw_bytes = uploaded_file.read()
        result = connector.import_export_data(request.user, raw_bytes)

        if result.success:
            return Response({
                "status": "success",
                "provider": provider,
                "items_synced": result.items_synced,
                "items_skipped": result.items_skipped,
                "details": result.details
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                "status": "failed",
                "provider": provider,
                "error": result.error_message
            }, status=status.HTTP_400_BAD_REQUEST)
