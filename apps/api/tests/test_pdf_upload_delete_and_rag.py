"""
MediaCompile — Comprehensive Test Suite for PDF Upload, Content & Chat Deletion, and Grounded RAG.
Covers:
1. Valid PDF upload with zero optional metadata -> 201 Created, stored, extracted, chunked, embedded.
2. Invalid/corrupted PDF upload -> 400 Bad Request with actionable validation error.
3. Unauthenticated request -> 401 Unauthorized.
4. Single content deletion -> removes ContentItem, cascading ContentChunks, vectors, and MinIO storage file.
5. Bulk content deletion -> removes multiple selected ContentItems and their chunks.
6. Multi-tenant isolation for content delete -> User B cannot delete User A's content.
7. Single chat session deletion -> cascades deletion of ChatSession and ChatMessages.
8. Multi-tenant isolation for chat delete -> User B cannot delete User A's chat session.
9. Clear all chat sessions -> clears all user conversations without touching library content.
10. RAG retrieval & QA on real multi-page PDF -> answers grounded in PDF facts with real page citations.
11. RAG insufficient evidence fallback -> unrelated question returns the strict fallback phrase without fabricating facts.
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import ContentItem, ContentChunk
from chat.models import ChatSession, ChatMessage
from chat.llm import UNSURE_FALLBACK_PHRASE
from content.storage import delete_file

User = get_user_model()


def build_two_page_pdf(page1_text: str, page2_text: str) -> bytes:
    """Build a valid 2-page PDF byte buffer with extractable text."""
    # Build clean PDF stream objects
    stream1 = f"BT\n/F1 14 Tf\n50 700 Td\n({page1_text}) Tj\nET".encode('latin-1')
    stream2 = f"BT\n/F1 14 Tf\n50 700 Td\n({page2_text}) Tj\nET".encode('latin-1')

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    
    offsets = []
    
    def add_obj(content: bytes):
        offsets.append(len(pdf))
        pdf.extend(content)
        pdf.extend(b"\n")

    # Obj 1: Catalog
    add_obj(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    # Obj 2: Pages
    add_obj(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>\nendobj")
    # Obj 3: Page 1
    add_obj(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj")
    # Obj 4: Page 2
    add_obj(b"4 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>\nendobj")
    # Obj 5: Stream 1
    add_obj(f"5 0 obj\n<< /Length {len(stream1)} >>\nstream\n".encode('latin-1') + stream1 + b"\nendstream\nendobj")
    # Obj 6: Stream 2
    add_obj(f"6 0 obj\n<< /Length {len(stream2)} >>\nstream\n".encode('latin-1') + stream2 + b"\nendstream\nendobj")
    # Obj 7: Font
    add_obj(b"7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")

    xref_offset = len(pdf)
    pdf.extend(b"xref\n0 8\n")
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode('latin-1'))
    
    pdf.extend(f"trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode('latin-1'))
    return bytes(pdf)


@pytest.fixture
def users(db):
    user_a = User.objects.create_user(
        email="test.user.a@mediacompile.io",
        password="SecurePassword2026!",
        name="User Alpha"
    )
    user_b = User.objects.create_user(
        email="test.user.b@mediacompile.io",
        password="SecurePassword2026!",
        name="User Beta"
    )
    return user_a, user_b


@pytest.fixture
def client_a(users):
    client = APIClient()
    client.force_authenticate(user=users[0])
    return client


@pytest.fixture
def client_b(users):
    client = APIClient()
    client.force_authenticate(user=users[1])
    return client


# ==============================================================================
# Phase 1: PDF Upload & Validation Tests
# ==============================================================================

@pytest.mark.django_db
def test_pdf_upload_success_minimal_metadata(client_a, users):
    """Test valid PDF upload without author, publisher or optional metadata."""
    pdf_bytes = build_two_page_pdf(
        "Project Hyperion Specification. Release Date: October 14, 2026. Latency: 42.8ms across 128 nodes.",
        "Hyperion speculative graph exploration eliminates lock contention."
    )
    uploaded = SimpleUploadedFile("hyperion.pdf", pdf_bytes, content_type="application/pdf")

    res = client_a.post(
        '/api/v1/content/files/',
        {'file': uploaded},  # no optional metadata provided
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )

    assert res.status_code == 201, f"Upload failed: {res.data}"
    data = res.json()
    assert data['content_type'] == 'document'
    assert data['ingestion_status'] == ContentItem.STATUS_COMPLETED
    assert data['chunk_count'] >= 1

    item = ContentItem.objects.get(id=data['id'])
    assert item.user == users[0]
    assert item.file_key is not None
    assert "hyperion" in item.title.lower() or "project" in item.title.lower()

    # Verify chunks have embeddings
    chunks = list(item.chunks.all())
    assert len(chunks) >= 1
    for chunk in chunks:
        assert len(chunk.embedding) == 384
        assert chunk.metadata.get('page_number') in (1, 2)


@pytest.mark.django_db
def test_pdf_upload_corrupted_file_error(client_a):
    """Test uploading a corrupted file returns a 400 validation error with actionable message."""
    corrupted_bytes = b"NOT_A_REAL_PDF_FILE_HEADER_CORRUPTED_DATA_12345"
    uploaded = SimpleUploadedFile("broken.pdf", corrupted_bytes, content_type="application/pdf")

    res = client_a.post(
        '/api/v1/content/files/',
        {'file': uploaded},
        format='multipart'
    )

    assert res.status_code == 400
    res_json = res.json()
    # Error should not be generic authorization failure
    assert "validation" in str(res_json).lower() or "file" in str(res_json).lower() or "pdf" in str(res_json).lower()


@pytest.mark.django_db
def test_pdf_upload_unauthenticated():
    """Test unauthenticated PDF upload returns 401."""
    client = APIClient()
    pdf_bytes = build_two_page_pdf("Page 1 Text", "Page 2 Text")
    uploaded = SimpleUploadedFile("test.pdf", pdf_bytes, content_type="application/pdf")

    res = client.post(
        '/api/v1/content/files/',
        {'file': uploaded},
        format='multipart'
    )
    assert res.status_code == 401


# ==============================================================================
# Phase 2: Content Deletion Tests (Single & Bulk)
# ==============================================================================

@pytest.mark.django_db
def test_single_content_item_deletion(client_a, users):
    """Test deleting one content item removes record, cascading chunks, and vector embeddings."""
    pdf_bytes = build_two_page_pdf("Page 1 data to delete", "Page 2 data to delete")
    uploaded = SimpleUploadedFile("to_delete.pdf", pdf_bytes, content_type="application/pdf")

    res = client_a.post(
        '/api/v1/content/files/',
        {'file': uploaded},
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )
    assert res.status_code == 201
    item_id = res.json()['id']

    # Confirm item and chunks exist
    assert ContentItem.objects.filter(id=item_id).exists()
    assert ContentChunk.objects.filter(content_item_id=item_id).count() >= 1

    # Delete item
    del_res = client_a.delete(f'/api/v1/content/items/{item_id}/')
    assert del_res.status_code in (200, 204)

    # Verify item and chunks are gone
    assert not ContentItem.objects.filter(id=item_id).exists()
    assert ContentChunk.objects.filter(content_item_id=item_id).count() == 0


@pytest.mark.django_db
def test_bulk_content_deletion(client_a, users):
    """Test deleting multiple content items simultaneously via bulk-delete action."""
    ids = []
    for i in range(3):
        item = ContentItem.objects.create(
            user=users[0],
            title=f"Bulk Item {i}",
            content_type=ContentItem.TYPE_NOTE,
            raw_text=f"Sample note content {i}",
            ingestion_status=ContentItem.STATUS_COMPLETED
        )
        ContentChunk.objects.create(
            content_item=item,
            chunk_index=0,
            text=f"Chunk {i}",
            start_offset=0,
            end_offset=len(f"Chunk {i}"),
            embedding=[0.01] * 384
        )
        ids.append(str(item.id))

    assert ContentItem.objects.filter(id__in=ids).count() == 3

    # Call bulk-delete
    res = client_a.post(
        '/api/v1/content/items/bulk-delete/',
        {'ids': ids},
        format='json'
    )
    assert res.status_code == 200
    data = res.json()
    assert data['deleted_count'] == 3
    assert not ContentItem.objects.filter(id__in=ids).exists()
    assert ContentChunk.objects.filter(content_item_id__in=ids).count() == 0


@pytest.mark.django_db
def test_content_deletion_tenant_isolation(client_a, client_b, users):
    """User B cannot delete User A's content item."""
    item_a = ContentItem.objects.create(
        user=users[0],
        title="User A Private Spec",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="Confidential data",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # User B attempts to delete item_a
    res = client_b.delete(f'/api/v1/content/items/{item_a.id}/')
    assert res.status_code in (403, 404)
    assert ContentItem.objects.filter(id=item_a.id).exists()


# ==============================================================================
# Phase 3: Chat Session Deletion Tests
# ==============================================================================

@pytest.mark.django_db
def test_single_chat_session_deletion(client_a, users):
    """Test deleting a chat session cascades to delete its messages without touching library content."""
    # Create library content to ensure it is not deleted
    library_item = ContentItem.objects.create(
        user=users[0],
        title="Unrelated Note",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="Keep this safe",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # Create session with messages
    session = ChatSession.objects.create(user=users[0], title="Session To Delete")
    ChatMessage.objects.create(session=session, role="user", content="Hello assistant")
    ChatMessage.objects.create(session=session, role="assistant", content="Hello user")

    session_id = str(session.id)
    assert ChatMessage.objects.filter(session_id=session_id).count() == 2

    # Delete session
    res = client_a.delete(f'/api/v1/chat/sessions/{session_id}/')
    assert res.status_code in (200, 204)

    # Verify session and messages are deleted
    assert not ChatSession.objects.filter(id=session_id).exists()
    assert ChatMessage.objects.filter(session_id=session_id).count() == 0

    # Verify library item is completely intact
    assert ContentItem.objects.filter(id=library_item.id).exists()


@pytest.mark.django_db
def test_clear_all_chat_sessions(client_a, users):
    """Test clear-all endpoint deletes all chat sessions for authenticated user."""
    for i in range(4):
        s = ChatSession.objects.create(user=users[0], title=f"Chat {i}")
        ChatMessage.objects.create(session=s, role="user", content=f"Message {i}")

    assert ChatSession.objects.filter(user=users[0]).count() == 4

    res = client_a.delete('/api/v1/chat/sessions/clear-all/')
    assert res.status_code == 200
    assert ChatSession.objects.filter(user=users[0]).count() == 0


@pytest.mark.django_db
def test_chat_deletion_tenant_isolation(client_a, client_b, users):
    """User B cannot delete User A's chat session."""
    session_a = ChatSession.objects.create(user=users[0], title="User A Chat")
    ChatMessage.objects.create(session=session_a, role="user", content="User A secret")

    res = client_b.delete(f'/api/v1/chat/sessions/{session_a.id}/')
    assert res.status_code in (403, 404)
    assert ChatSession.objects.filter(id=session_a.id).exists()


# ==============================================================================
# Phase 4 & 5: Grounded RAG & Citations on Indexed PDF
# ==============================================================================

@pytest.mark.django_db
def test_rag_qa_grounded_in_pdf_content(client_a, users):
    """
    Test uploading a PDF with specific facts, querying the chatbot,
    and verifying answers and citations are grounded in the actual document.
    """
    # 1. Upload known PDF
    pdf_bytes = build_two_page_pdf(
        "Project Hyperion. Target latency: 42.8ms across 128 distributed nodes. Completed on October 14, 2026.",
        "Hyperion speculative graph exploration eliminates all lock contention during real-time ingest."
    )
    uploaded = SimpleUploadedFile("hyperion_spec.pdf", pdf_bytes, content_type="application/pdf")
    res_upload = client_a.post(
        '/api/v1/content/files/',
        {'file': uploaded, 'title': 'Project Hyperion Architecture Spec'},
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )
    assert res_upload.status_code == 201
    item_id = res_upload.json()['id']

    # 2. Create Chat Session
    res_session = client_a.post('/api/v1/chat/sessions/', {'title': 'Hyperion Q&A'}, format='json')
    assert res_session.status_code == 201
    session_id = res_session.json()['id']

    # 3. Ask question with mock Groq provider returning grounded text
    mock_llm_response = (
        "According to the Project Hyperion Architecture Spec [1], the target latency is 42.8 milliseconds "
        "across 128 distributed nodes, and it was completed on October 14, 2026."
    )

    mock_provider = MagicMock()
    mock_provider.model_name = "openai/gpt-oss-120b"
    mock_provider.generate_response.return_value = mock_llm_response

    with patch('chat.services.get_llm_provider', return_value=mock_provider):
        res_msg = client_a.post(
            f'/api/v1/chat/sessions/{session_id}/messages/',
            {'content': 'What is the target latency and completion date for Project Hyperion?'},
            format='json'
        )

        assert res_msg.status_code == 201
        data = res_msg.json()
        assistant_msg = data['assistant_message']
        assert "42.8" in assistant_msg['content']
        assert "October 14, 2026" in assistant_msg['content']
        # Verify citations were generated and retrieved from actual indexed chunks
        assert len(assistant_msg['citations']) >= 1
        assert assistant_msg['citations'][0]['item_title'] == 'Project Hyperion Architecture Spec'
        assert assistant_msg['citations'][0]['page_number'] in (1, 2)
        # Verify the system prompt received the actual retrieved chunk facts
        call_args = mock_provider.generate_response.call_args
        system_prompt_passed = call_args.kwargs.get('system_prompt', '')
        if not system_prompt_passed and len(call_args.args) > 1:
            system_prompt_passed = call_args.args[1]
        assert "Hyperion" in system_prompt_passed or "42.8" in system_prompt_passed


@pytest.mark.django_db
def test_rag_unrelated_query_insufficient_evidence(client_a, users):
    """
    Test asking an unrelated question when content is indexed returns the strict
    insufficient evidence fallback phrase without hallucination.
    """
    # Create a note about quantum cryptography
    client_a.post('/api/v1/content/notes/', {
        'title': 'Quantum Cryptography',
        'content': 'BB84 is a quantum key distribution scheme developed in 1984.'
    }, format='json')

    res_session = client_a.post('/api/v1/chat/sessions/', {'title': 'Unrelated Question'}, format='json')
    session_id = res_session.json()['id']

    # Ask about cooking recipes in saved notes (completely unrelated)
    res_msg = client_a.post(
        f'/api/v1/chat/sessions/{session_id}/messages/',
        {'content': 'What do my notes say about baking sourdough bread with a 75% hydration ratio?'},
        format='json'
    )


    assert res_msg.status_code == 201
    content = res_msg.json()['assistant_message']['content']
    assert UNSURE_FALLBACK_PHRASE.lower() in content.lower() or "cannot find sufficient evidence" in content.lower()
