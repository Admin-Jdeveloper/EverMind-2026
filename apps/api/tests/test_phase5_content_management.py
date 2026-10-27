"""
MediaCompile — Phase 5: Content Management Test Suite.
Source of Truth: MediaCompile-prompt.md (Phase 5: Content Management Implementation)

Validates:
1. View item details: title, type, status, source URL / file info, chunk count, raw text preview, chunks list.
2. Edit item metadata: PATCH /api/v1/content/items/{id}/ updating title, collection, and tags.
3. Retry ingestion: POST /api/v1/content/items/{id}/retry/ re-runs extraction and embedding, clearing errors.
4. Download document: GET /api/v1/content/items/{id}/download/ generates signed MinIO download URL.
5. Delete item: DELETE /api/v1/content/items/{id}/ cleanly cascades to all ContentChunks and vector embeddings.
6. Multi-tenant authorization: Users can only view, edit, download, retry, and delete their own items (cross-user access returns 404).
"""

import io
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import ContentItem, ContentChunk, Collection, Tag
from content.embeddings import get_embedding_provider

User = get_user_model()


@pytest.fixture
def mgmt_users(db):
    user_a = User.objects.create_user(
        email="alice.mgmt@mediacompile.io",
        password="SecurePassword2026!",
        name="Alice Mgmt"
    )
    user_b = User.objects.create_user(
        email="bob.mgmt@mediacompile.io",
        password="SecurePassword2026!",
        name="Bob Mgmt"
    )
    return user_a, user_b


@pytest.fixture
def client_a(mgmt_users):
    client = APIClient()
    client.force_authenticate(user=mgmt_users[0])
    return client


@pytest.fixture
def client_b(mgmt_users):
    client = APIClient()
    client.force_authenticate(user=mgmt_users[1])
    return client


# ------------------------------------------------------------------------------
# 1. View Item Details and Extracted Text Preview
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_view_item_details_and_chunks(client_a, mgmt_users):
    """Verify GET /api/v1/content/items/{id}/ returns full item metadata, raw text, and chunks."""
    user_a = mgmt_users[0]
    provider = get_embedding_provider()

    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Distributed Consensus Architecture",
        raw_text="Raft consensus uses randomized election timeouts to establish leader leases.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text=item.raw_text,
        start_offset=0,
        end_offset=len(item.raw_text),
        embedding=provider.embed_text(item.raw_text),
        metadata={'char_length': len(item.raw_text), 'heading': 'Consensus'}
    )

    res = client_a.get(f'/api/v1/content/items/{item.id}/')
    assert res.status_code == 200
    data = res.json()

    assert data['id'] == str(item.id)
    assert data['title'] == "Distributed Consensus Architecture"
    assert data['content_type'] == "note"
    assert data['ingestion_status'] == "completed"
    assert data['raw_text'] == item.raw_text
    assert data['chunk_count'] == 1
    assert len(data['chunks']) == 1

    chunk_data = data['chunks'][0]
    assert chunk_data['chunk_index'] == 0
    assert chunk_data['text'] == item.raw_text
    assert chunk_data['metadata']['heading'] == 'Consensus'


# ------------------------------------------------------------------------------
# 2. Edit Item Metadata (Title, Collection, Tags)
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_edit_item_metadata(client_a, mgmt_users):
    """Verify PATCH /api/v1/content/items/{id}/ updates title, collection, and tags."""
    user_a = mgmt_users[0]
    collection_1 = Collection.objects.create(user=user_a, name="Distributed Systems")
    collection_2 = Collection.objects.create(user=user_a, name="Database Internals")

    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Original Title",
        collection=collection_1,
        raw_text="Note content for metadata editing test.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    tag_initial = Tag.objects.create(user=user_a, name="initial-tag")
    item.tags.add(tag_initial)

    # Update title, collection, and tags via PATCH
    res = client_a.patch(f'/api/v1/content/items/{item.id}/', {
        'title': 'Updated Title: Raft & Paxos',
        'collection': str(collection_2.id),
        'tags': ['consensus', 'fault-tolerance', 'algorithms']
    }, format='json')

    assert res.status_code == 200
    data = res.json()
    assert data['title'] == 'Updated Title: Raft & Paxos'
    assert data['collection'] == str(collection_2.id)
    assert 'consensus' in data['tags_list']
    assert 'fault-tolerance' in data['tags_list']
    assert 'initial-tag' not in data['tags_list']

    # Verify persistence in database
    item.refresh_from_db()
    assert item.title == 'Updated Title: Raft & Paxos'
    assert item.collection == collection_2
    tag_names = list(item.tags.values_list('name', flat=True))
    assert 'consensus' in tag_names
    assert 'initial-tag' not in tag_names


# ------------------------------------------------------------------------------
# 3. Retry Failed Item Ingestion
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_retry_failed_item_ingestion(client_a, mgmt_users):
    """Verify POST /api/v1/content/items/{id}/retry/ re-runs extraction and embedding."""
    user_a = mgmt_users[0]
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Retry Test Note",
        raw_text="This note was previously marked failed due to temporary network error.",
        ingestion_status=ContentItem.STATUS_FAILED,
        error_message="Simulated temporary processing error"
    )

    # Verify initial failure state
    assert item.chunks.count() == 0
    assert item.ingestion_status == ContentItem.STATUS_FAILED

    # Trigger retry with synchronous header
    res = client_a.post(
        f'/api/v1/content/items/{item.id}/retry/',
        HTTP_X_SYNC_INGESTION='true'
    )
    assert res.status_code == 200

    item.refresh_from_db()
    assert item.ingestion_status == ContentItem.STATUS_COMPLETED
    assert item.error_message == ''
    assert item.chunks.count() >= 1

    # Verify embeddings were generated
    chunk = item.chunks.first()
    assert len(chunk.embedding) == 384


# ------------------------------------------------------------------------------
# 4. Download Uploaded Document via Presigned URL
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_download_document_presigned_url(client_a, mgmt_users):
    """Verify GET /api/v1/content/items/{id}/download/ returns signed MinIO URL."""
    uploaded = SimpleUploadedFile(
        "report.txt",
        b"Production deployment report content for vector database.",
        content_type="text/plain"
    )
    upload_res = client_a.post(
        '/api/v1/content/files/',
        {'file': uploaded, 'title': 'Production Report'},
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )
    assert upload_res.status_code == 201
    item_id = upload_res.json()['id']

    # Request presigned download URL
    dl_res = client_a.get(f'/api/v1/content/items/{item_id}/download/')
    assert dl_res.status_code == 200
    data = dl_res.json()
    assert 'download_url' in data
    assert 'http' in data['download_url']
    assert 'report.txt' in data.get('filename', '')

    # Non-document items without file_key return 400 Bad Request
    note_res = client_a.post('/api/v1/content/notes/', {'content': 'Plain text note without file'}, format='json')
    note_id = note_res.json()['id']
    note_dl = client_a.get(f'/api/v1/content/items/{note_id}/download/')
    assert note_dl.status_code == 400


# ------------------------------------------------------------------------------
# 5. Delete Item Cascades to Chunks and Vector Embeddings
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_delete_item_cascades_chunks_and_embeddings(client_a, mgmt_users):
    """Verify DELETE /api/v1/content/items/{id}/ deletes item and all pgvector chunks."""
    user_a = mgmt_users[0]
    provider = get_embedding_provider()

    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Deletable Item",
        raw_text="This item will be deleted.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk_1 = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="Chunk 1",
        embedding=provider.embed_text("Chunk 1")
    )
    chunk_2 = ContentChunk.objects.create(
        content_item=item,
        chunk_index=1,
        text="Chunk 2",
        embedding=provider.embed_text("Chunk 2")
    )

    c1_id = chunk_1.id
    c2_id = chunk_2.id
    assert ContentChunk.objects.filter(id__in=[c1_id, c2_id]).count() == 2

    # Delete item via API
    del_res = client_a.delete(f'/api/v1/content/items/{item.id}/')
    assert del_res.status_code == 204

    # Verify ContentItem and associated ContentChunks are completely deleted
    assert not ContentItem.objects.filter(id=item.id).exists()
    assert not ContentChunk.objects.filter(id__in=[c1_id, c2_id]).exists()


# ------------------------------------------------------------------------------
# 6. Multi-Tenant Authorization Isolation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_multitenant_content_management_isolation(client_a, client_b, mgmt_users):
    """Verify User B cannot view, edit, download, retry, or delete User A's items."""
    user_a, user_b = mgmt_users

    item_a = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Confidential Item",
        raw_text="Alice confidential content.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # 1. User B cannot view User A's item (404)
    res_view = client_b.get(f'/api/v1/content/items/{item_a.id}/')
    assert res_view.status_code == 404

    # 2. User B cannot edit User A's item (404)
    res_edit = client_b.patch(f'/api/v1/content/items/{item_a.id}/', {'title': 'Hacked Title'})
    assert res_edit.status_code == 404

    # 3. User B cannot retry User A's item (404)
    res_retry = client_b.post(f'/api/v1/content/items/{item_a.id}/retry/')
    assert res_retry.status_code == 404

    # 4. User B cannot download User A's item (404)
    res_dl = client_b.get(f'/api/v1/content/items/{item_a.id}/download/')
    assert res_dl.status_code == 404

    # 5. User B cannot delete User A's item (404)
    res_del = client_b.delete(f'/api/v1/content/items/{item_a.id}/')
    assert res_del.status_code == 404

    # Confirm item_a is completely untouched
    item_a.refresh_from_db()
    assert item_a.title == "Alice Confidential Item"
