"""
MediaCompile — Integrations Credential Encryption & Token Privacy Service.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Social and External Integrations)

Features:
1. Symmetrical encryption at rest for third-party OAuth access tokens, refresh tokens, and secrets.
2. Uses cryptography.fernet.Fernet with derived or dedicated 256-bit encryption key.
3. Token secrecy & log redaction: cleanses sensitive tokens from serialization and error output.
"""

import base64
import hashlib
import json
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

def _get_encryption_key() -> bytes:
    """
    Retrieve or derive a URL-safe base64-encoded 32-byte Fernet key.
    Uses settings.INTEGRATION_ENCRYPTION_KEY if provided;
    otherwise derives deterministically from settings.SECRET_KEY via SHA256.
    """
    configured = getattr(settings, 'INTEGRATION_ENCRYPTION_KEY', None)
    if configured:
        if isinstance(configured, str):
            configured = configured.strip().encode('utf-8')
        try:
            # Validate valid Fernet key
            Fernet(configured)
            return configured
        except Exception:
            pass

    # Derive 32-byte key from Django secret key
    secret_bytes = settings.SECRET_KEY.encode('utf-8')
    derived_32 = hashlib.sha256(b"mediacompile-token-encryption:" + secret_bytes).digest()
    return base64.urlsafe_b64encode(derived_32)

def encrypt_credentials(payload: Dict[str, Any]) -> str:
    """Encrypt a dictionary of OAuth credentials to an opaque ASCII ciphertext string."""
    if not payload:
        return ""
    key = _get_encryption_key()
    fernet = Fernet(key)
    raw_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    token = fernet.encrypt(raw_json)
    return token.decode('ascii')

def decrypt_credentials(ciphertext: str) -> Dict[str, Any]:
    """Decrypt an opaque ciphertext string back into the credentials dictionary."""
    if not ciphertext or not ciphertext.strip():
        return {}
    key = _get_encryption_key()
    fernet = Fernet(key)
    try:
        decrypted_bytes = fernet.decrypt(ciphertext.strip().encode('ascii'))
        return json.loads(decrypted_bytes.decode('utf-8'))
    except (InvalidToken, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to decrypt credentials payload: {e}")
        return {}

def redact_credentials(creds: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a safe dictionary representation with sensitive secret values masked.
    Safe for API output or diagnostic logging.
    """
    if not creds:
        return {}
    redacted = {}
    sensitive_keys = {'access_token', 'refresh_token', 'client_secret', 'token', 'secret', 'password'}
    for k, v in creds.items():
        if k.lower() in sensitive_keys and isinstance(v, str) and v:
            if len(v) <= 8:
                redacted[k] = "***"
            else:
                redacted[k] = f"{v[:4]}...{v[-4:]}"
        else:
            redacted[k] = v
    return redacted
