"""
MediaCompile — Celery Background Tasks for Social and External Integrations.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Tasks per connector)

Enforces:
1. Asynchronous execution on Celery solo worker (Windows compatible).
2. Rate limit, token expiration, and error handling.
3. User tenant isolation and status updating.
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import ConnectedAccount
from .connectors.registry import get_connector

logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True, max_retries=2, default_retry_delay=10, ignore_result=True)
def sync_account_task(self, account_id: str):
    """Execute asynchronous content sync for a connected third-party account."""
    try:
        account = ConnectedAccount.objects.select_related('user').get(id=account_id)
    except ConnectedAccount.DoesNotExist:
        logger.error(f"sync_account_task: ConnectedAccount {account_id} not found.")
        return {"status": "error", "error": "Account not found"}

    if account.status == ConnectedAccount.STATUS_REVOKED:
        logger.info(f"sync_account_task: Account {account_id} is revoked. Aborting sync.")
        return {"status": "skipped", "reason": "revoked"}

    connector = get_connector(account.provider)
    if not connector:
        account.sync_status = 'failed'
        account.error_message = f"Unsupported provider: {account.provider}"
        account.save(update_fields=['sync_status', 'error_message', 'updated_at'])
        return {"status": "error", "error": account.error_message}

    account.sync_status = 'syncing'
    account.error_message = ''
    account.save(update_fields=['sync_status', 'error_message', 'updated_at'])

    try:
        creds = account.get_credentials()
        result = connector.sync_content(account.user, credentials=creds)

        if result.success:
            account.sync_status = 'success'
            account.items_synced_count += result.items_synced
            account.last_sync_at = timezone.now()
            account.error_message = ''
            account.save(update_fields=['sync_status', 'items_synced_count', 'last_sync_at', 'error_message', 'updated_at'])
            return {
                "status": "success",
                "items_synced": result.items_synced,
                "items_skipped": result.items_skipped
            }
        else:
            if result.details.get("status") == "expired":
                account.status = ConnectedAccount.STATUS_EXPIRED

            account.sync_status = 'failed'
            account.error_message = result.error_message or "Sync failed"
            account.save(update_fields=['status', 'sync_status', 'error_message', 'updated_at'])
            return {"status": "failed", "error": result.error_message}

    except Exception as exc:
        logger.exception(f"sync_account_task exception for account {account_id}: {exc}")
        account.sync_status = 'failed'
        account.error_message = str(exc)
        account.save(update_fields=['sync_status', 'error_message', 'updated_at'])
        raise self.retry(exc=exc)
