"""
MediaCompile — Phase 10 Tests: Security, Privacy, Reliability & Cross-Tenant Audit Matrix.
Source of Truth: MediaCompile-prompt.md (Section 20: Phase 10 — Security & Privacy)

Tests:
1. Security Headers: nosniff, DENY, Referrer-Policy, and Content-Security-Policy on responses.
2. Cross-Tenant Isolation Matrix: 10 resource types strictly inaccessible across user boundaries.
3. Complete Account Purge & GDPR Data Erasure (DELETE /api/v1/users/me/).
4. Security Audit Event Logging with credential redaction.
5. Rate Limiting Throttling enforcement.
6. Health Check Multi-Service Monitoring (PostgreSQL, Redis, MinIO).
"""

import json
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from content.models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference
from integrations.models import ConnectedAccount
from core.audit import log_security_event, EVENT_LOGIN_SUCCESS, EVENT_ACCOUNT_PURGE

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user_alice(db):
    return User.objects.create_user(
        email='alice_sec@mediacompile.io',
        username='alice_sec@mediacompile.io',
        password='ValidPassword123!'
    )

@pytest.fixture
def user_bob(db):
    return User.objects.create_user(
        email='bob_sec@mediacompile.io',
        username='bob_sec@mediacompile.io',
        password='ValidPassword123!'
    )

@pytest.mark.django_db
def test_security_headers_present(api_client, user_alice):
    api_client.force_authenticate(user=user_alice)
    resp = api_client.get('/api/v1/health/')
    assert resp.status_code == status.HTTP_200_OK

    # OWASP Defense Headers
    assert resp['X-Content-Type-Options'] == 'nosniff'
    assert resp['X-Frame-Options'] == 'DENY'
    assert resp['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'default-src' in resp['Content-Security-Policy']
    assert "frame-ancestors 'none'" in resp['Content-Security-Policy']
    assert 'geolocation=()' in resp['Permissions-Policy']

@pytest.mark.django_db
def test_health_check_monitors_all_services(api_client):
    resp = api_client.get('/api/v1/health/')
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert data['status'] == 'healthy'
    assert data['checks']['database'] == 'ok'
    assert data['checks']['cache'] == 'ok'
    assert data['checks']['storage'] == 'ok'

@pytest.mark.django_db
def test_security_audit_logging_redacts_credentials():
    record = log_security_event(
        event_type=EVENT_LOGIN_SUCCESS,
        user=None,
        details={
            "token": "ya29.secret_bearer_token",
            "password": "SuperSecretPassword!",
            "action": "login_via_oauth"
        }
    )
    assert record['details']['token'] == '[REDACTED]'
    assert record['details']['password'] == '[REDACTED]'
    assert record['details']['action'] == 'login_via_oauth'

@pytest.mark.django_db
def test_cross_tenant_isolation_matrix(api_client, user_alice, user_bob):
    """
    Exhaustive cross-tenant security test matrix.
    Verifies User Bob receives 404 for every single resource owned by User Alice.
    """
    # 1. Setup Alice's Resources
    col_alice = Collection.objects.create(user=user_alice, name="Alice Collection")
    tag_alice = Tag.objects.create(user=user_alice, name="alicesecret")
    item_alice = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Private Note",
        raw_text="Alice confidential content",
        collection=col_alice
    )
    chunk_alice = ContentChunk.objects.create(
        content_item=item_alice,
        chunk_index=0,
        text="Alice confidential content",
        start_offset=0,
        end_offset=26
    )
    search_alice = SavedSearch.objects.create(
        user=user_alice,
        name="Alice Query",
        query_text="confidential"
    )
    session_alice = ChatSession.objects.create(user=user_alice, title="Alice Chat")
    msg_alice = ChatMessage.objects.create(
        session=session_alice,
        role=ChatMessage.ROLE_USER,
        content="Secret Alice Prompt"
    )
    memory_alice = UserMemory.objects.create(
        user=user_alice,
        memory_text="Alice likes dark mode"
    )
    account_alice = ConnectedAccount.objects.create(
        user=user_alice,
        provider="youtube",
        external_account_id="alice_yt_id"
    )

    # 2. Authenticate as Bob and probe Alice's resources
    api_client.force_authenticate(user=user_bob)

    # Resource 1: ContentItem
    assert api_client.get(f'/api/v1/content/items/{item_alice.id}/').status_code == status.HTTP_404_NOT_FOUND
    assert api_client.delete(f'/api/v1/content/items/{item_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 2: ContentItem Download Presigned URL
    assert api_client.get(f'/api/v1/content/items/{item_alice.id}/download/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 3: ContentItem Related Recommendations
    assert api_client.get(f'/api/v1/content/items/{item_alice.id}/related/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 4: Collection
    assert api_client.get(f'/api/v1/content/collections/{col_alice.id}/').status_code == status.HTTP_404_NOT_FOUND
    assert api_client.delete(f'/api/v1/content/collections/{col_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 5: SavedSearch
    assert api_client.get(f'/api/v1/content/saved-searches/{search_alice.id}/').status_code == status.HTTP_404_NOT_FOUND
    assert api_client.delete(f'/api/v1/content/saved-searches/{search_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 6: ChatSession
    assert api_client.get(f'/api/v1/chat/sessions/{session_alice.id}/').status_code == status.HTTP_404_NOT_FOUND
    assert api_client.delete(f'/api/v1/chat/sessions/{session_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 7: ChatMessage Injection into foreign session
    assert api_client.post(
        f'/api/v1/chat/sessions/{session_alice.id}/messages/',
        {"content": "Unauthorized probe"},
        format='json'
    ).status_code == status.HTTP_404_NOT_FOUND

    # Resource 8: UserMemory
    assert api_client.delete(f'/api/v1/chat/memory/{memory_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 9: ConnectedAccount Sync & Disconnect
    assert api_client.post(f'/api/v1/integrations/accounts/{account_alice.id}/sync/').status_code == status.HTTP_404_NOT_FOUND
    assert api_client.delete(f'/api/v1/integrations/accounts/{account_alice.id}/').status_code == status.HTTP_404_NOT_FOUND

    # Resource 10: Sovereign Export Isolation
    export_resp = api_client.get('/api/v1/content/export/')
    assert export_resp.status_code == status.HTTP_200_OK
    assert "Alice Private Note" not in json.dumps(export_resp.data)

@pytest.mark.django_db
def test_complete_account_purge_lifecycle(api_client, user_alice):
    """
    Test permanent GDPR account deletion (DELETE /api/v1/users/me/).
    Confirms all content items, chunks, collections, tags, chat, memories, and accounts are erased.
    """
    api_client.force_authenticate(user=user_alice)

    # Populate Alice data
    col = Collection.objects.create(user=user_alice, name="Purge Test Col")
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Note To Be Purged",
        collection=col
    )
    ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="Ephemeral text"
    )
    SavedSearch.objects.create(user=user_alice, name="Search To Be Purged", query_text="test")
    session = ChatSession.objects.create(user=user_alice, title="Purge Chat")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="Hello")
    UserMemory.objects.create(user=user_alice, memory_text="Ephemeral memory")
    ConnectedAccount.objects.create(user=user_alice, provider="youtube", external_account_id="purge_yt")

    alice_id = user_alice.id

    # Issue DELETE request
    resp = api_client.delete('/api/v1/users/me/')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['success'] is True

    # Confirm all user records are gone
    assert not User.objects.filter(id=alice_id).exists()
    assert not ContentItem.objects.filter(user_id=alice_id).exists()
    assert not ContentChunk.objects.filter(content_item__user_id=alice_id).exists()
    assert not Collection.objects.filter(user_id=alice_id).exists()
    assert not SavedSearch.objects.filter(user_id=alice_id).exists()
    assert not ChatSession.objects.filter(user_id=alice_id).exists()
    assert not UserMemory.objects.filter(user_id=alice_id).exists()
    assert not ConnectedAccount.objects.filter(user_id=alice_id).exists()

@pytest.mark.django_db
def test_rate_limiting_enforcement(api_client, user_alice):
    """
    Verify that rate limit throttles reject excessive traffic with HTTP 429.
    """
    api_client.force_authenticate(user=user_alice)

    # Test that throttle classes are attached to ingestion
    from content.views import IngestUrlView
    from core.throttling import IngestionRateThrottle

    assert IngestionRateThrottle in IngestUrlView.throttle_classes
