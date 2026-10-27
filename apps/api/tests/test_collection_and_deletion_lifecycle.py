"""
MediaCompile — Collection Management, Delete Flows, and Data Integrity Test Suite.
Validates:
1. Rename collection successfully: updates name in-place, preserves stable UUID primary key.
2. Content relationship preservation: all content items attached to the collection remain attached after rename.
3. Duplicate name prevention: attempting to rename to an existing collection name returns HTTP 400 (not 500), does not mutate collection or create duplicates.
4. Empty name validation: whitespace or empty string rename returns HTTP 400.
5. Same-name rename: renaming to the collection's current name succeeds without validation error.
6. Multi-tenant isolation: users cannot view, rename, or delete collections belonging to other tenants.
7. Collection deletion semantics: deleting a collection unlinks content items (sets collection to NULL) without deleting the content items or their embeddings.
8. Chat session deletion: deleting a chat session cascades to its messages while leaving other conversations intact.
"""

import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from content.models import Collection, ContentItem
from chat.models import ChatSession, ChatMessage

User = get_user_model()


@pytest.fixture
def auth_users(db):
    user_a = User.objects.create_user(
        email="alice.test@mediacompile.io",
        password="SecurePassword2026!",
        name="Alice Tester"
    )
    user_b = User.objects.create_user(
        email="bob.test@mediacompile.io",
        password="SecurePassword2026!",
        name="Bob Tester"
    )
    return user_a, user_b


@pytest.fixture
def client_a(auth_users):
    client = APIClient()
    client.force_authenticate(user=auth_users[0])
    return client


@pytest.fixture
def client_b(auth_users):
    client = APIClient()
    client.force_authenticate(user=auth_users[1])
    return client


# ------------------------------------------------------------------------------
# 1. Collection Rename: Success, Stable ID, Content Relationship Preservation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_rename_collection_success_and_preserves_relationships(client_a, auth_users):
    user_a = auth_users[0]
    
    # Create collection
    col = Collection.objects.create(
        user=user_a,
        name="Machine Learning Research",
        description="Papers on Transformers and RAG"
    )
    original_id = col.id

    # Attach two content items
    item1 = ContentItem.objects.create(
        user=user_a,
        collection=col,
        title="Attention Is All You Need",
        content_type=ContentItem.TYPE_DOCUMENT,
        raw_text="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks."
    )
    item2 = ContentItem.objects.create(
        user=user_a,
        collection=col,
        title="Retrieval-Augmented Generation",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="RAG models combine pre-trained parametric and non-parametric memory for language generation."
    )

    # Perform rename via PATCH
    rename_payload = {
        "name": "Advanced AI & LLM Research",
        "description": "Updated description for AI papers"
    }
    res = client_a.patch(f"/api/v1/content/collections/{original_id}/", rename_payload, format="json")
    
    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.data}"
    data = res.data
    assert data["id"] == str(original_id), "Collection ID must remain strictly unchanged!"
    assert data["name"] == "Advanced AI & LLM Research"
    assert data["description"] == "Updated description for AI papers"

    # Verify database state
    col.refresh_from_db()
    assert col.id == original_id, "Database primary key must be unchanged!"
    assert col.name == "Advanced AI & LLM Research"

    # Verify content items are still associated with this collection
    item1.refresh_from_db()
    item2.refresh_from_db()
    assert item1.collection_id == original_id, "Item 1 must remain linked to the renamed collection!"
    assert item2.collection_id == original_id, "Item 2 must remain linked to the renamed collection!"
    assert col.items.count() == 2, "Collection items count must be preserved!"

    # Verify no new collection was created
    assert Collection.objects.filter(user=user_a).count() == 1


# ------------------------------------------------------------------------------
# 2. Duplicate Name Prevention: Returns 400, No 500, No Replacement Created
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_rename_collection_duplicate_name_fails_gracefully(client_a, auth_users):
    user_a = auth_users[0]
    
    col1 = Collection.objects.create(user=user_a, name="Quantum Computing")
    col2 = Collection.objects.create(user=user_a, name="Quantum Information")
    col1_id = col1.id
    col2_id = col2.id

    # Attempt to rename col2 to col1's name (Quantum Computing)
    res = client_a.patch(f"/api/v1/content/collections/{col2_id}/", {
        "name": "Quantum Computing"
    }, format="json")

    assert res.status_code == 400, f"Expected 400 Bad Request, got {res.status_code}: {res.data}"
    assert res.data["success"] is False
    assert "error" in res.data
    # Details or message should indicate unique constraint error
    err_msg = res.data["error"]["message"].lower()
    assert "already exists" in err_msg or "unique" in err_msg

    # Verify col2 name was not changed and no new collection was created
    col2.refresh_from_db()
    assert col2.name == "Quantum Information"
    assert Collection.objects.filter(user=user_a).count() == 2


# ------------------------------------------------------------------------------
# 3. Empty or Whitespace Name Validation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_rename_collection_empty_name_rejected(client_a, auth_users):
    user_a = auth_users[0]
    col = Collection.objects.create(user=user_a, name="Original Name")

    res = client_a.patch(f"/api/v1/content/collections/{col.id}/", {
        "name": "   "
    }, format="json")

    assert res.status_code == 400
    assert res.data["success"] is False

    col.refresh_from_db()
    assert col.name == "Original Name"


# ------------------------------------------------------------------------------
# 4. Same-Name Rename Succeeds
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_rename_collection_same_name_succeeds(client_a, auth_users):
    user_a = auth_users[0]
    col = Collection.objects.create(user=user_a, name="Static Analysis", description="Initial")

    res = client_a.patch(f"/api/v1/content/collections/{col.id}/", {
        "name": "Static Analysis",
        "description": "Updated Description"
    }, format="json")

    assert res.status_code == 200
    assert res.data["description"] == "Updated Description"
    col.refresh_from_db()
    assert col.description == "Updated Description"


# ------------------------------------------------------------------------------
# 5. Multi-Tenant Collection Isolation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_cross_tenant_collection_rename_and_delete_forbidden(client_b, auth_users):
    user_a = auth_users[0]
    col_a = Collection.objects.create(user=user_a, name="Alice Secret Notes")

    # Bob attempts to rename Alice's collection
    res_rename = client_b.patch(f"/api/v1/content/collections/{col_a.id}/", {
        "name": "Bob Infiltration"
    }, format="json")
    assert res_rename.status_code == 404, "User B should not find or modify User A's collection"

    # Bob attempts to delete Alice's collection
    res_delete = client_b.delete(f"/api/v1/content/collections/{col_a.id}/")
    assert res_delete.status_code == 404, "User B should not delete User A's collection"

    # Alice's collection remains intact
    col_a.refresh_from_db()
    assert col_a.name == "Alice Secret Notes"


# ------------------------------------------------------------------------------
# 6. Collection Deletion: Unlinks Items Without Deleting Original Content
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_collection_deletion_preserves_content_items(client_a, auth_users):
    user_a = auth_users[0]
    col = Collection.objects.create(user=user_a, name="Temporary Collection")
    col_id = col.id

    item = ContentItem.objects.create(
        user=user_a,
        collection=col,
        title="Saved Article",
        content_type=ContentItem.TYPE_URL,
        source_url="https://example.com/saved-article"
    )

    res = client_a.delete(f"/api/v1/content/collections/{col_id}/")
    assert res.status_code == 204

    # Collection is deleted
    assert not Collection.objects.filter(id=col_id).exists()

    # Child item is preserved with collection = None (SET_NULL semantics)
    item.refresh_from_db()
    assert item.collection is None
    assert ContentItem.objects.filter(id=item.id).exists()


# ------------------------------------------------------------------------------
# 7. Chat Deletion: Deletes Session and Messages, Preserves Other Sessions
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_chat_deletion_and_isolation(client_a, auth_users):
    user_a = auth_users[0]

    # Create two chat sessions
    sess1 = ChatSession.objects.create(user=user_a, title="Conversation 1")
    ChatMessage.objects.create(session=sess1, role="user", content="Hello in sess 1")
    ChatMessage.objects.create(session=sess1, role="assistant", content="Response 1")

    sess2 = ChatSession.objects.create(user=user_a, title="Conversation 2")
    ChatMessage.objects.create(session=sess2, role="user", content="Hello in sess 2")

    # Delete session 1
    res = client_a.delete(f"/api/v1/chat/sessions/{sess1.id}/")
    assert res.status_code == 204

    # Verify session 1 and its messages are deleted
    assert not ChatSession.objects.filter(id=sess1.id).exists()
    assert ChatMessage.objects.filter(session_id=sess1.id).count() == 0

    # Verify session 2 remains completely intact
    assert ChatSession.objects.filter(id=sess2.id).exists()
    assert ChatMessage.objects.filter(session_id=sess2.id).count() == 1
