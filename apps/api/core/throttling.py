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

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class IngestionRateThrottle(UserRateThrottle):
    scope = 'ingestion'

class SearchRateThrottle(UserRateThrottle):
    scope = 'search'

class ChatRateThrottle(UserRateThrottle):
    scope = 'chat'

class ExportImportRateThrottle(UserRateThrottle):
    scope = 'export_import'

class AuthRateThrottle(AnonRateThrottle):
    scope = 'auth'
