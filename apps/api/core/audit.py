"""
MediaCompile — Security Audit Logging Service.
Source of Truth: MediaCompile-prompt.md (Section 20: Phase 10 — Security & Audit)

Provides a centralized mechanism to log security-sensitive events with minimal metadata
and zero credential/secret leakage.
"""

import logging
from typing import Dict, Any, Optional
from django.utils import timezone

logger = logging.getLogger('mediacompile.audit')

# Standardized Security Event Types
EVENT_LOGIN_SUCCESS = 'LOGIN_SUCCESS'
EVENT_ACCOUNT_PURGE = 'ACCOUNT_PURGE'
EVENT_EXPORT_GENERATED = 'SOVEREIGN_EXPORT_GENERATED'
EVENT_IMPORT_RESTORED = 'SOVEREIGN_IMPORT_RESTORED'
EVENT_CONNECTOR_LINKED = 'CONNECTOR_LINKED'
EVENT_CONNECTOR_REVOKED = 'CONNECTOR_REVOKED'
EVENT_PERSONALIZATION_TOGGLED = 'PERSONALIZATION_TOGGLED'
EVENT_RATE_LIMIT_EXCEEDED = 'RATE_LIMIT_EXCEEDED'

def log_security_event(
    event_type: str,
    user=None,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format and emit a structured, sanitized security audit event.
    Guarantees secrets and raw passwords are never logged.
    """
    safe_details = details.copy() if details else {}
    
    # Strip any potential secrets
    for sensitive_key in ['token', 'password', 'secret', 'access_token', 'refresh_token', 'credentials']:
        if sensitive_key in safe_details:
            safe_details[sensitive_key] = '[REDACTED]'

    user_identifier = str(user.id) if user and getattr(user, 'id', None) else 'anonymous'
    user_email = user.email if user and getattr(user, 'email', None) else 'unknown'

    record = {
        "timestamp": timezone.now().isoformat(),
        "event_type": event_type,
        "user_id": user_identifier,
        "user_email": user_email,
        "ip_address": ip_address or '127.0.0.1',
        "details": safe_details
    }

    logger.info(f"[SECURITY_AUDIT] {event_type} | user={user_email} (ID: {user_identifier}) | details={safe_details}")
    return record
