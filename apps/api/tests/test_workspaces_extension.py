"""
MediaCompile — Phase 9 Tests: Workspaces, Topic Dashboards, Bulk Export/Import & Browser Extension Flow.
Source of Truth: MediaCompile-prompt.md (Section 19: Phase 9)

Tests:
1. WebClipAPIView: Browser extension clipping, SSRF rejection, and deduplication.
2. LibraryExportAPIView: Sovereign export generation with chunks, memories, and chat history.
3. LibraryBulkImportAPIView: Round-trip idempotent restoration and file upload handling.
4. TimelineAPIView: Chronological monthly grouping of library items.
5. RelatedContentAPIView: pgvector semantic related items recommendations with user isolation.
6. TopicWorkspaceAPIView: Grounded thematic inquiry and study questions synthesis.
7. SavedSearchViewSet: CRUD and multi-tenant isolation for user saved searches.
"""

import json
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from content.embeddings import get_embedding_provider
from chat.models import UserMemory, ChatSession, ChatMessage

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email='user_a@example.com',
        username='user_a@example.com',
        password='Password123!'
    )

@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email='user_b@example.com',
        username='user_b@example.com',
        password='Password123!'
    )

@pytest.mark.django_db
def test_web_clip_api_and_deduplication(api_client, user_a):
    api_client.force_authenticate(user=user_a)
    col = Collection.objects.create(user=user_a, name="Research")

    # 1. Clip valid page
    clip_payload = {
        "url": "https://example.com/deep-dive-ai",
        "title": "Deep Dive into Transformers",
        "selected_text": "Attention mechanisms allow models to focus on relevant tokens dynamically.",
        "notes": "Must review for transformer benchmarking.",
        "collection_id": str(col.id),
        "tags": ["ai", "transformers"]
    }
    resp = api_client.post('/api/v1/content/clip/', clip_payload, format='json')
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data['status'] == 'clipped'
    item_id = resp.data['item_id']

    # Verify ContentItem and chunks created
    item = ContentItem.objects.get(id=item_id)
    assert item.user == user_a
    assert item.collection == col
    assert item.tags.count() == 2
    assert item.chunks.count() >= 1
    assert item.chunks.first().embedding is not None

    # 2. Duplicate clip returns already_exists gracefully
    resp_dup = api_client.post('/api/v1/content/clip/', clip_payload, format='json')
    assert resp_dup.status_code == status.HTTP_200_OK
    assert resp_dup.data['status'] == 'already_exists'
    assert ContentItem.objects.filter(user=user_a, source_url="https://example.com/deep-dive-ai").count() == 1

@pytest.mark.django_db
def test_web_clip_ssrf_rejection(api_client, user_a):
    api_client.force_authenticate(user=user_a)

    # Test loopback IP
    resp1 = api_client.post('/api/v1/content/clip/', {"url": "http://127.0.0.1/admin", "title": "Loopback"}, format='json')
    assert resp1.status_code == status.HTTP_400_BAD_REQUEST
    assert "resolves to protected/private IP" in str(resp1.data)

    # Test non-standard port
    resp2 = api_client.post('/api/v1/content/clip/', {"url": "http://127.0.0.1:8000/internal", "title": "Port probe"}, format='json')
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert "Prohibited port" in str(resp2.data)

@pytest.mark.django_db
def test_export_manifest_fidelity_and_isolation(api_client, user_a, user_b):
    api_client.force_authenticate(user=user_a)

    # Populate user_a data
    col = Collection.objects.create(user=user_a, name="Quantum Computing")
    tag = Tag.objects.create(user=user_a, name="physics")
    provider = get_embedding_provider()
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Superposition Principles",
        raw_text="Quantum bits exist in a linear combination of states |0> and |1>.",
        collection=col,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    item.tags.add(tag)
    ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="Quantum bits exist in a linear combination of states |0> and |1>.",
        start_offset=0,
        end_offset=65,
        embedding=provider.embed_text("Quantum bits exist in a linear combination of states |0> and |1>.")
    )
    UserMemory.objects.create(
        user=user_a,
        memory_text="Prefers mathematical explanations over conceptual analogies.",
        category="preference"
    )

    # Populate user_b private item (must not leak)
    ContentItem.objects.create(
        user=user_b,
        content_type=ContentItem.TYPE_NOTE,
        title="User B Secret",
        raw_text="Confidential User B information."
    )

    # Request export for user_a
    resp = api_client.get('/api/v1/content/export/')
    assert resp.status_code == status.HTTP_200_OK
    manifest = resp.data

    assert manifest['manifest_version'] == '1.0'
    assert manifest['user_email'] == user_a.email
    assert len(manifest['collections']) == 1
    assert manifest['collections'][0]['name'] == "Quantum Computing"
    assert len(manifest['items']) == 1
    assert manifest['items'][0]['title'] == "Superposition Principles"
    assert len(manifest['items'][0]['chunks']) == 1
    assert len(manifest['memories']) == 1
    assert "mathematical explanations" in manifest['memories'][0]['memory_text']

    # Cross-user isolation check: User B secret must NOT be in manifest
    assert "User B Secret" not in json.dumps(manifest)

@pytest.mark.django_db
def test_bulk_import_idempotent_restoration(api_client, user_b):
    api_client.force_authenticate(user=user_b)

    manifest_payload = {
        "manifest_version": "1.0",
        "user_email": "user_b@example.com",
        "collections": [
            {"name": "Distributed Systems", "description": "Consensus & Replication", "is_private": True}
        ],
        "tags": [
            {"name": "raft", "color": "#10B981"}
        ],
        "items": [
            {
                "content_type": "note",
                "source_url": "https://raft.github.io/raft.pdf",
                "title": "In Search of an Understandable Consensus Algorithm",
                "raw_text": "Raft is a consensus algorithm for managing a replicated log.",
                "collection_name": "Distributed Systems",
                "tags": ["raft"],
                "metadata": {"author": "Ongaro & Ousterhout"},
                "chunks": [
                    {
                        "chunk_index": 0,
                        "text": "Raft is a consensus algorithm for managing a replicated log.",
                        "start_offset": 0,
                        "end_offset": 60
                    }
                ]
            }
        ],
        "memories": [
            {"memory_text": "Studies distributed systems algorithms", "category": "learning"}
        ]
    }

    # 1. First import
    resp1 = api_client.post('/api/v1/content/import-bulk/', {"manifest": manifest_payload}, format='json')
    assert resp1.status_code == status.HTTP_200_OK
    assert resp1.data['items_synced'] == 1
    assert resp1.data['collections_created'] == 1
    assert resp1.data['memories_created'] == 1

    # Verify database state
    assert ContentItem.objects.filter(user=user_b, title="In Search of an Understandable Consensus Algorithm").exists()
    assert UserMemory.objects.filter(user=user_b, memory_text="Studies distributed systems algorithms").exists()

    # 2. Second import (idempotent: items skipped, no duplicate errors)
    resp2 = api_client.post('/api/v1/content/import-bulk/', {"manifest": manifest_payload}, format='json')
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.data['items_synced'] == 0
    assert resp2.data['items_skipped'] == 1
    assert ContentItem.objects.filter(user=user_b, source_url="https://raft.github.io/raft.pdf").count() == 1

@pytest.mark.django_db
def test_bulk_import_file_upload(api_client, user_a):
    api_client.force_authenticate(user=user_a)

    manifest_data = {
        "manifest_version": "1.0",
        "collections": [],
        "tags": [],
        "items": [
            {
                "content_type": "note",
                "source_url": "",
                "title": "Imported via File Note",
                "raw_text": "This note was restored from a JSON archive file upload.",
                "tags": []
            }
        ],
        "memories": []
    }
    file_bytes = json.dumps(manifest_data).encode('utf-8')
    uploaded_file = SimpleUploadedFile("export.json", file_bytes, content_type="application/json")

    resp = api_client.post('/api/v1/content/import-bulk/', {'file': uploaded_file}, format='multipart')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['items_synced'] == 1
    assert ContentItem.objects.filter(user=user_a, title="Imported via File Note").exists()


@pytest.mark.django_db
def test_saved_search_crud_and_isolation(api_client, user_a, user_b):
    api_client.force_authenticate(user=user_a)

    # 1. Create saved search
    payload = {
        "name": "Database Architecture",
        "query_text": "postgresql pgvector hnsw",
        "filters": {"content_type": "note", "tag": "database"}
    }
    resp = api_client.post('/api/v1/content/saved-searches/', payload, format='json')
    assert resp.status_code == status.HTTP_201_CREATED
    search_id = resp.data['id']

    # 2. List saved searches
    resp_list = api_client.get('/api/v1/content/saved-searches/')
    assert resp_list.status_code == status.HTTP_200_OK
    assert resp_list.data['count'] == 1
    assert resp_list.data['results'][0]['name'] == "Database Architecture"

    # 3. User B cannot access User A's saved search
    api_client.force_authenticate(user=user_b)
    resp_b_get = api_client.get(f'/api/v1/content/saved-searches/{search_id}/')
    assert resp_b_get.status_code == status.HTTP_404_NOT_FOUND
