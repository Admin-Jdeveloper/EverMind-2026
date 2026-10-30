"""
MediaCompile — Rate Limiting & Throttling Classes.
Source of Truth: MediaCompile-prompt.md (Section 20: Phase 10 — Security & Rate Limiting)

Scoped rate limits backed by Redis cache:
- ingestion: 120/minute (protects CPU & background queue during URL/doc ingestion)
- search: 180/minute (protects pgvector CosineDistance query throughput)
- chat: 60/minute (protects LLM context generation and inference budget)
- export_import: 20/minute (protects heavy archive serialization)
- auth: 30/minute (protects login and identity exchange endpoints)
"""

import logging
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

logger = logging.getLogger(__name__)

class SafeThrottleMixin:
    """
    Guarantees high-availability API resilience.
    If the Redis cache is temporarily degraded, disconnected, or connection-limited,
    the throttle fails open instead of crashing business-critical API requests with 500 errors.
    """
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            logger.warning(
                f"[THROTTLE_BYPASS] Cache unavailable for throttle '{self.__class__.__name__}': {exc}. "
                "Failing open to maintain API availability."
            )
            return True

class SafeAnonRateThrottle(SafeThrottleMixin, AnonRateThrottle):
    pass

class SafeUserRateThrottle(SafeThrottleMixin, UserRateThrottle):
    pass

class IngestionRateThrottle(SafeThrottleMixin, UserRateThrottle):
    scope = 'ingestion'

class SearchRateThrottle(SafeThrottleMixin, UserRateThrottle):
    scope = 'search'

class ChatRateThrottle(SafeThrottleMixin, UserRateThrottle):
    scope = 'chat'

class ExportImportRateThrottle(SafeThrottleMixin, UserRateThrottle):
    scope = 'export_import'

class AuthRateThrottle(SafeThrottleMixin, AnonRateThrottle):
    scope = 'auth'
