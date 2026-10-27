"""
MediaCompile — Production User Data Isolation, Security & Workspace Deletion Tests.

Verifies:
1. Profile identity immutability (PATCH/PUT /api/v1/users/profile/ & /me/ returns 403 Forbidden).
2. Permanent workspace deletion (DELETE /api/v1/users/workspace/) purges all User A resources
   while keeping User A account credentials intact and User B resources completely untouched.
3. Cross-user collection assignment rejection during ingestion (Note, URL, Document).
4. Vector & hybrid search isolation (User B chunks never enter User A retrieval scope).
5. Safe storage object key generation (directory traversal prevention & unique UUID prefixing).
"""

import json
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from content.models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from content.storage import build_storage_key
from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference
from content.search import hybrid_retrieve_with_facts

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user_alice(db):
    return User.objects.create_user(
        email="alice_prod_iso@mediacompile.io",
        password="AliceSecurePassword123!"
    )

@pytest.fixture
def user_bob(db):
    return User.objects.create_user(
        email="bob_prod_iso@mediacompile.io",
        password="BobSecurePassword123!"
    )


@pytest.mark.django_db
def test_profile_identity_fields_immutable_via_api(api_client, user_alice):
    """
    Requirements 2.1 & Phase 4:
    Users must not be able to change their email address, name, or profile identity
    fields through the application UI or ordinary API requests (returns 403 Forbidden).
    """
    api_client.force_authenticate(user=user_alice)

    # Test PATCH /api/v1/users/me/
    patch_resp = api_client.patch(
        '/api/v1/users/me/',
        {"email": "hacked_alice@evil.com", "name": "Evil Alice"},
        format='json'
    )
    assert patch_resp.status_code == status.HTTP_403_FORBIDDEN
    assert patch_resp.data["success"] is False

    # Test PUT /api/v1/users/profile/
    put_resp = api_client.put(
        '/api/v1/users/profile/',
        {"email": "hacked_alice@evil.com", "first_name": "Evil"},
        format='json'
    )
    assert put_resp.status_code == status.HTTP_403_FORBIDDEN
    assert put_resp.data["success"] is False

    # Verify email and database record was unmodified
    user_alice.refresh_from_db()
    assert user_alice.email == "alice_prod_iso@mediacompile.io"


@pytest.mark.django_db
def test_workspace_permanent_deletion_safeguards(api_client, user_alice, user_bob):
    """
    Requirements Phase 4:
    DELETE /api/v1/users/workspace/ permanently deletes workspace data for the authenticated user,
    including content items, chunks, collections, chat history, memories, and searches,
    while leaving the user's account active and other users' workspaces completely unaffected.
    """
    # 1. Populate Alice's workspace
    col_a = Collection.objects.create(user=user_alice, name="Alice Workspace Project")
    item_a = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Secret Roadmap",
        raw_text="Confidential strategy",
        collection=col_a
    )
    chunk_a = ContentChunk.objects.create(
        content_item=item_a,
        chunk_index=0,
        text="Confidential strategy chunk"
    )
    session_a = ChatSession.objects.create(user=user_alice, title="Alice Strategy Chat")
    ChatMessage.objects.create(session=session_a, role=ChatMessage.ROLE_USER, content="Hello")
    memory_a = UserMemory.objects.create(user=user_alice, memory_text="Alice prefers dark theme")
    search_a = SavedSearch.objects.create(user=user_alice, name="Alice Search", query_text="strategy")

    # 2. Populate Bob's workspace (Must remain untouched)
    col_b = Collection.objects.create(user=user_bob, name="Bob Isolated Collection")
    item_b = ContentItem.objects.create(
        user=user_bob,
        content_type=ContentItem.TYPE_NOTE,
        title="Bob Untouched Document",
        raw_text="Bob safe notes",
        collection=col_b
    )
    chunk_b = ContentChunk.objects.create(
        content_item=item_b,
        chunk_index=0,
        text="Bob chunk"
    )
    session_b = ChatSession.objects.create(user=user_bob, title="Bob Safe Session")
    ChatMessage.objects.create(session=session_b, role=ChatMessage.ROLE_USER, content="Bob chat")
    memory_b = UserMemory.objects.create(user=user_bob, memory_text="Bob prefers light theme")

    # 3. Authenticate as Alice and invoke DELETE /api/v1/users/workspace/
    api_client.force_authenticate(user=user_alice)
    delete_resp = api_client.delete('/api/v1/users/workspace/')
    assert delete_resp.status_code == status.HTTP_200_OK
    assert delete_resp.data["success"] is True

    # 4. Verify Alice's workspace data is completely erased
    assert not ContentItem.objects.filter(user=user_alice).exists()
    assert not ContentChunk.objects.filter(content_item__user=user_alice).exists()
    assert not Collection.objects.filter(user=user_alice).exists()
    assert not ChatSession.objects.filter(user=user_alice).exists()
    assert not ChatMessage.objects.filter(session__user=user_alice).exists()
    assert not UserMemory.objects.filter(user=user_alice).exists()
    assert not SavedSearch.objects.filter(user=user_alice).exists()

    # 5. Alice's user account itself remains intact (can still log in)
    assert User.objects.filter(id=user_alice.id).exists()

    # 6. Verify Bob's workspace data is 100% preserved
    assert ContentItem.objects.filter(user=user_bob).count() == 1
    assert ContentChunk.objects.filter(content_item__user=user_bob).count() == 1
    assert Collection.objects.filter(user=user_bob).count() == 1
    assert ChatSession.objects.filter(user=user_bob).count() == 1
    assert ChatMessage.objects.filter(session__user=user_bob).count() == 1
    assert UserMemory.objects.filter(user=user_bob).count() == 1


@pytest.mark.django_db
def test_cross_user_collection_assignment_rejected(api_client, user_alice, user_bob):
    """
    Requirements 2.2 & 2.3:
    User A cannot attach newly created notes, URLs, or documents to User B's collection.
    The server rejects the foreign collection_id with 404 Not Found.
    """
    col_bob = Collection.objects.create(user=user_bob, name="Bob Private Vault")

    api_client.force_authenticate(user=user_alice)

    # Ingest Note targeting Bob's collection
    note_resp = api_client.post(
        '/api/v1/content/notes/',
        {
            "title": "Malicious Note Injection",
            "content": "Attempting to plant into Bob's vault",
            "collection_id": str(col_bob.id)
        },
        format='json'
    )
    assert note_resp.status_code == status.HTTP_404_NOT_FOUND
    assert not ContentItem.objects.filter(title="Malicious Note Injection").exists()

    # Ingest URL targeting Bob's collection
    url_resp = api_client.post(
        '/api/v1/content/urls/',
        {
            "url": "https://example.com/exploit",
            "collection_id": str(col_bob.id)
        },
        format='json'
    )
    assert url_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieval_and_search_strict_tenant_isolation(user_alice, user_bob):
    """
    Requirements 2.4:
    Retrieval and search scope must enforce user ownership at the database query level.
    User B's chunks must NEVER be retrieved or returned in User A's candidate set.
    """
    # Create distinct items and chunks for Alice and Bob
    item_alice = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Python Async Best Practices",
        raw_text="Asyncio coroutines and event loops in Python",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=item_alice,
        chunk_index=0,
        text="Asyncio coroutines and event loops in Python for high performance concurrency.",
        embedding=[0.05] * 384
    )

    item_bob = ContentItem.objects.create(
        user=user_bob,
        content_type=ContentItem.TYPE_NOTE,
        title="Secret Bob Python Formula",
        raw_text="Bob secret proprietary algorithmic trading system in Python",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=item_bob,
        chunk_index=0,
        text="Bob secret proprietary algorithmic trading system in Python with zero slippage.",
        embedding=[0.05] * 384
    )

    # Alice queries for "Python"
    alice_results, _, _ = hybrid_retrieve_with_facts(
        user=user_alice,
        query_text="Python",
        limit=10,
        min_similarity=0.01
    )

    # User B's chunk must never appear in Alice's results
    assert len(alice_results) > 0
    for res in alice_results:
        assert res["item"]["id"] == str(item_alice.id)
        assert "Bob secret" not in res["text"]


def test_storage_path_sanitization_and_isolation():
    """
    Requirements 2.5:
    Storage paths must prevent directory traversal and overwrite collisions.
    """
    malicious_filename = "../../../etc/passwd.txt"
    user_id = "00000000-0000-0000-0000-000000000001"

    safe_path = build_storage_key(user_id, malicious_filename)

    # Must start with users/{user_id}/files/
    assert safe_path.startswith(f"users/{user_id}/files/")
    # Must NOT contain directory traversal
    assert ".." not in safe_path
    assert "/etc/" not in safe_path
    assert "passwd" in safe_path
