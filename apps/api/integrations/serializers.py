"""
MediaCompile — Integrations Serializers.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Tasks per connector)
"""

from rest_framework import serializers
from .models import ConnectedAccount, IngestionJob

class ConnectedAccountSerializer(serializers.ModelSerializer):
    """
    Public serializer for connected accounts.
    Enforces strict token secrecy: encrypted_credentials is NEVER exposed.
    """
    class Meta:
        model = ConnectedAccount
        fields = [
            'id',
            'provider',
            'external_account_id',
            'account_name',
            'account_email',
            'granted_scopes',
            'status',
            'sync_status',
            'items_synced_count',
            'last_sync_at',
            'error_message',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'status',
            'sync_status',
            'items_synced_count',
            'last_sync_at',
            'error_message',
            'created_at',
            'updated_at'
        ]

class ConnectAccountInputSerializer(serializers.Serializer):
    """Input serializer for registering an authorized third-party connection."""
    provider = serializers.CharField(max_length=64, required=True)
    external_account_id = serializers.CharField(max_length=255, required=True)
    account_name = serializers.CharField(max_length=255, required=False, default="", allow_blank=True)
    account_email = serializers.EmailField(required=False, default="", allow_blank=True)
    granted_scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    credentials = serializers.DictField(required=True, help_text="Tokens and secrets to be encrypted at rest")

class ImportFileUploadSerializer(serializers.Serializer):
    """Input serializer for uploading user exports (bookmarks HTML/JSON, Reddit CSV/JSON, Takeout JSON)."""
    file = serializers.FileField(required=True)
