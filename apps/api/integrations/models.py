import uuid
from django.db import models
from django.conf import settings

class ConnectedAccount(models.Model):
    """External third-party authorized integration (YouTube, Reddit, etc.)."""
    
    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_REVOKED, 'Revoked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='connected_accounts')
    provider = models.CharField(max_length=64, db_index=True)
    external_account_id = models.CharField(max_length=255)
    account_email = models.EmailField(blank=True)
    account_name = models.CharField(max_length=255, blank=True, help_text="Display name or channel title")
    
    granted_scopes = models.JSONField(default=list, blank=True)
    encrypted_credentials = models.TextField(blank=True, help_text="Symmetrically encrypted token payload")
    
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    sync_status = models.CharField(max_length=32, default='idle', help_text="idle, syncing, success, failed")
    items_synced_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [['user', 'provider', 'external_account_id']]

    def __str__(self):
        return f"{self.user.email} - {self.provider}:{self.external_account_id} [{self.status}]"

    def set_credentials(self, credentials_dict: dict):
        """Encrypt and persist token credentials dictionary."""
        from .crypto import encrypt_credentials
        self.encrypted_credentials = encrypt_credentials(credentials_dict)

    def get_credentials(self) -> dict:
        """Decrypt and return credentials dictionary."""
        from .crypto import decrypt_credentials
        return decrypt_credentials(self.encrypted_credentials)

    def disconnect(self):
        """Revoke connection and purge encrypted token payload."""
        self.status = self.STATUS_REVOKED
        self.encrypted_credentials = ""
        self.sync_status = 'idle'
        self.save(update_fields=['status', 'encrypted_credentials', 'sync_status', 'updated_at'])

class IngestionJob(models.Model):
    """Background asynchronous task execution state."""
    
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_RETRYING = 'retrying'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_RETRYING, 'Retrying'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ingestion_jobs')
    content_item_id = models.UUIDField(null=True, blank=True)
    task_id = models.CharField(max_length=255, db_index=True, blank=True)
    
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_details = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"IngestionJob {self.id} [{self.status}]"
