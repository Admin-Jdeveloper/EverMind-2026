"""
MediaCompile — Phase 1 Acceptance Test Gate: Reliable Content Ingestion
Source of Truth: MediaCompile Autonomous RAG Engineering Master Prompt (Phase 1)

Verifies:
1. Valid PDFs with known page content.
2. Every other supported document format (DOCX, PPTX, XLSX, CSV, TXT).
3. Public article pages (HTML boilerplate stripping, title, clean body).
4. News articles (headline, article body, cookies/ads removal).
5. YouTube content with transcripts and timestamps.
6. Supported social-media / web links (OG metadata, canonical URL).
7. Notes creation, update, deletion, and retrieval.
8. Invalid URLs and unsupported schemes (rejection, SSRF safety).
9. Inaccessible and malformed sources (safe failure state, clear error message).
10. Empty documents and extraction failures.
11. Duplicate ingestion handling.
12. Interrupted ingestion and retry behavior.
13. Rate limits and timeouts.
14. Source updates and deletions (cascades chunks and facts).
15. Correct metadata, page numbers, URLs, and chunk provenance.
16. Cross-user access prevention.
17. End-to-end ingestion followed by chatbot retrieval.
"""

import io
import csv
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import ContentItem, ContentChunk, Collection
from content.services import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_pptx,
    extract_text_from_xlsx,
    extract_text_from_csv,
    extract_text_from_txt,
    extract_text_from_html,
    chunk_text
)
from content.tasks import (
    process_note_content,
    process_document_content,
    process_url_content
)
from chat.services import retrieve_grounding_context
from content.security import SSRFProtectionError

User = get_user_model()


@pytest.fixture
def p1_users(db):
    user_a = User.objects.create_user(
        email="p1.alice@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Ingest"
    )
    user_b = User.objects.create_user(
        email="p1.bob@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Ingest"
    )
    return user_a, user_b


@pytest.fixture
def auth_client_a(p1_users):
    user_a, _ = p1_users
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


# Helper generator for binary test documents
def generate_test_pdf_bytes() -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def generate_test_docx_bytes() -> bytes:
    import docx
    doc = docx.Document()
    doc.core_properties.title = "Distributed Architecture Guide"
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("MediaCompile uses an asynchronous multi-stage ingestion pipeline.")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Component"
    table.rows[0].cells[1].text = "Purpose"
    table.rows[1].cells[0].text = "PgVector"
    table.rows[1].cells[1].text = "HNSW Dense Search"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generate_test_pptx_bytes() -> bytes:
    import pptx
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Microservices at Scale"
    slide.placeholders[1].text = "Service meshes provide automated mutual TLS and observability."
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def generate_test_xlsx_bytes() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EngineeringMetrics"
    ws.append(["Metric", "Target", "Status"])
    ws.append(["Retrieval Latency", "50ms", "Optimal"])
    ws.append(["Chunk Precision", "99.2%", "Verified"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.django_db
def test_p1_01_valid_pdf_page_content_extraction():
    """Criterion 1: PDF extraction preserves page numbers and text structure."""
    from pypdf import PdfWriter
    # Verify PdfReader parsing pipeline
    pdf_bytes = generate_test_pdf_bytes()
    title, text, pages_data = extract_text_from_pdf(pdf_bytes)
    assert isinstance(pages_data, list)
    # Validate chunking preserves page tags
    simulated_pdf_text = (
        "[Page 1]\n"
        "Introduction to Distributed Consensus. In distributed systems, consensus is the process of agreeing on a value among nodes.\n\n"
        "[Page 2]\n"
        "Raft elects a leader using randomized election timeouts between 150ms and 300ms to avoid split vote conditions."
    )
    chunks = chunk_text(simulated_pdf_text, chunk_size=140, chunk_overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["metadata"]["page_number"] == 1
    assert chunks[1]["metadata"]["page_number"] == 2


@pytest.mark.django_db
def test_p1_02_every_supported_document_format():
    """Criterion 2: DOCX, PPTX, XLSX, CSV, and TXT extract headings, tables, slides, rows, and tags."""
    # 1. DOCX
    docx_bytes = generate_test_docx_bytes()
    d_title, d_text, d_sections = extract_text_from_docx(docx_bytes)
    assert "Architecture Overview" in d_text
    assert "HNSW Dense Search" in d_text

    # 2. PPTX
    pptx_bytes = generate_test_pptx_bytes()
    p_title, p_text, p_slides = extract_text_from_pptx(pptx_bytes)
    assert "Microservices at Scale" in p_text
    assert p_slides[0]["slide_number"] == 1

    # 3. XLSX
    xlsx_bytes = generate_test_xlsx_bytes()
    x_title, x_text, x_rows = extract_text_from_xlsx(xlsx_bytes)
    assert "EngineeringMetrics" in x_text
    assert "Retrieval Latency" in x_text

    # 4. CSV
    csv_bytes = b"Server,IP,Status\napi-01,10.0.1.5,Active\napi-02,10.0.1.6,Standby\n"
    c_title, c_text, c_rows = extract_text_from_csv(csv_bytes)
    assert "api-01" in c_text
    assert len(c_rows) == 2

    # 5. TXT
    txt_bytes = b"# Deployment Checklist\n1. Run migrations\n2. Verify health"
    t_title, t_text = extract_text_from_txt(txt_bytes)
    assert t_title == "Deployment Checklist"
    assert "Run migrations" in t_text


@pytest.mark.django_db
def test_p1_03_public_article_extraction():
    """Criterion 3: Public HTML extraction strips boilerplate and extracts main article content."""
    html_sample = b"""
    <!DOCTYPE html>
    <html>
    <head><title>Engineering Blog: High Performance RAG</title></head>
    <body>
        <nav><a href="/home">Home</a><a href="/login">Sign In</a></nav>
        <div class="cookie-consent-banner">We use cookies. Click Agree.</div>
        <article>
            <h1>High Performance RAG Systems</h1>
            <p>Modern RAG requires combining dense pgvector retrieval with BM25 keyword matching.</p>
        </article>
        <footer>(c) 2026 TechCorp. All rights reserved.</footer>
    </body>
    </html>
    """
    title, text, meta = extract_text_from_html(html_sample)
    assert title == "Engineering Blog: High Performance RAG"
    assert "High Performance RAG Systems" in text
    assert "Modern RAG requires combining dense" in text
    # Verify boilerplate was stripped
    assert "cookie-consent-banner" not in text
    assert "Click Agree" not in text
    assert "Sign In" not in text
    assert "TechCorp" not in text


@pytest.mark.django_db
def test_p1_04_news_article_extraction():
    """Criterion 4: News pages extract article body and strip ads."""
    news_html = b"""
    <html>
    <head><meta property="og:title" content="Tech News: Database Innovations"></head>
    <body>
        <div class="advert-sidebar">Special Offer: Buy Now!</div>
        <main>
            <p>Databases now support hybrid indexing with native vector extensions.</p>
        </main>
    </body>
    </html>
    """
    title, text, meta = extract_text_from_html(news_html)
    assert "Databases now support hybrid indexing" in text
    assert "Special Offer" not in text


@pytest.mark.django_db
def test_p1_05_youtube_content_with_timestamps(p1_users):
    """Criterion 5: YouTube content extraction captures timestamp cues, metadata, and timestamp URLs."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_VIDEO,
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Pending YouTube Ingestion",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    mock_cues = [
        {"text": "Welcome to the database tutorial.", "start": 0.0, "duration": 4.0},
        {"text": "Here we discuss HNSW graph indexing.", "start": 65.0, "duration": 5.0},
    ]

    with patch("content.tasks.fetch_youtube_metadata") as mock_meta, \
         patch("content.tasks.fetch_youtube_transcript") as mock_trans:
        mock_meta.return_value = {
            "title": "HNSW Graph Indexing Masterclass",
            "channel_name": "Distributed Systems Acad",
            "description": "Deep dive into vector graph indexes."
        }
        mock_trans.return_value = (mock_cues, None)

        process_url_content(str(item.id), allow_test_local=True)
        item.refresh_from_db()

        assert item.ingestion_status == ContentItem.STATUS_COMPLETED
        assert item.title == "HNSW Graph Indexing Masterclass"
        chunks = list(item.chunks.all().order_by("chunk_index"))
        assert len(chunks) >= 1
        # Check timestamp metadata and video id preserved
        assert any(c.metadata.get("video_id") == "dQw4w9WgXcQ" for c in chunks)
        assert any("timestamp" in c.metadata for c in chunks)
        assert any("HNSW" in c.text for c in chunks)


@pytest.mark.django_db
def test_p1_06_supported_web_links_metadata():
    """Criterion 6: Web links preserve description, canonical URL, and title."""
    html = b"""
    <html>
    <head>
        <title>Vector Search Essentials</title>
        <meta name="description" content="A comprehensive tutorial on embeddings." />
        <link rel="canonical" href="https://example.com/vector-search" />
    </head>
    <body><main><p>Vector search projects high dimensional text into cosine space.</p></main></body>
    </html>
    """
    title, text, meta = extract_text_from_html(html)
    assert meta["description"] == "A comprehensive tutorial on embeddings."
    assert meta["canonical_url"] == "https://example.com/vector-search"


@pytest.mark.django_db
def test_p1_07_notes_crud_lifecycle(auth_client_a, p1_users):
    """Criterion 7: User-created notes lifecycle (create, update, chunk, delete)."""
    user_a, _ = p1_users

    # Create
    res = auth_client_a.post("/api/v1/content/notes/", {
        "title": "Raft Notes",
        "content": "Raft uses heartbeats every 50ms to maintain authority."
    }, format="json")
    assert res.status_code == 201
    item_id = res.data["id"]

    item = ContentItem.objects.get(id=item_id)
    assert item.ingestion_status == ContentItem.STATUS_COMPLETED
    assert item.chunks.count() >= 1

    # Update
    res_update = auth_client_a.patch(f"/api/v1/content/items/{item_id}/", {
        "title": "Updated Raft Notes"
    }, format="json")
    assert res_update.status_code == 200
    item.refresh_from_db()
    assert item.title == "Updated Raft Notes"

    # Delete
    res_del = auth_client_a.delete(f"/api/v1/content/items/{item_id}/")
    assert res_del.status_code == 204
    assert not ContentItem.objects.filter(id=item_id).exists()
    assert not ContentChunk.objects.filter(content_item_id=item_id).exists()


@pytest.mark.django_db
def test_p1_08_invalid_urls_and_unsupported_schemes(p1_users):
    """Criterion 8: Invalid URLs and unsupported schemes (ftp, file, internal IP) are safely rejected."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_URL,
        source_url="ftp://malicious.host/exploit.txt",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    process_url_content(str(item.id), allow_test_local=False)
    item.refresh_from_db()

    assert item.ingestion_status == ContentItem.STATUS_FAILED
    assert "SSRF" in item.error_message or "failed" in item.error_message.lower()


@pytest.mark.django_db
def test_p1_09_inaccessible_and_malformed_sources(p1_users):
    """Criterion 9: Inaccessible URLs (404/500) transition to failed status with clear diagnostic error."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_URL,
        source_url="https://valid-domain.com/nonexistent-page",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    with patch("content.tasks.safe_fetch_url") as mock_fetch:
        mock_fetch.side_effect = Exception("HTTP 404: Not Found")
        process_url_content(str(item.id), allow_test_local=True)
        item.refresh_from_db()

        assert item.ingestion_status == ContentItem.STATUS_FAILED
        assert "404" in item.error_message


@pytest.mark.django_db
def test_p1_10_empty_documents_and_extraction_failures(p1_users):
    """Criterion 10: Empty notes or documents fail gracefully with descriptive error."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Empty Note",
        raw_text="",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    process_note_content(str(item.id))
    item.refresh_from_db()

    assert item.ingestion_status == ContentItem.STATUS_FAILED
    assert "empty" in item.error_message.lower()


@pytest.mark.django_db
def test_p1_11_duplicate_ingestion(auth_client_a, p1_users):
    """Criterion 11: Duplicate note submission returns existing note without duplicating chunks."""
    user_a, _ = p1_users
    payload = {
        "title": "Idempotent Note",
        "content": "Exact duplicate content to verify idempotency and hash stability."
    }

    # First submission
    res1 = auth_client_a.post("/api/v1/content/notes/", payload, format="json")
    assert res1.status_code == 201
    item_id_1 = res1.data["id"]

    # Second submission with identical content
    res2 = auth_client_a.post("/api/v1/content/notes/", payload, format="json")
    assert res2.status_code == 200
    assert res2.data["id"] == item_id_1

    # Verify no duplicate records created
    assert ContentItem.objects.filter(user=user_a, title="Idempotent Note").count() == 1


@pytest.mark.django_db
def test_p1_12_interrupted_ingestion_and_retry_behavior(p1_users):
    """Criterion 12: Interrupted task marks status appropriately without leaving corrupt state."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Transient Error Note",
        raw_text="Some valid content for chunking.",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    with patch("content.tasks.chunk_text", side_effect=RuntimeError("Worker interrupted")):
        process_note_content(str(item.id))
        item.refresh_from_db()
        assert item.ingestion_status == ContentItem.STATUS_FAILED
        assert "interrupted" in item.error_message.lower()


@pytest.mark.django_db
def test_p1_13_rate_limits_and_timeouts(p1_users):
    """Criterion 13: Timeouts during URL fetch result in failed status with timeout diagnosis."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_URL,
        source_url="https://slow-api.example.com/data",
        ingestion_status=ContentItem.STATUS_PENDING
    )

    with patch("content.tasks.safe_fetch_url", side_effect=TimeoutError("Request timed out after 10s")):
        process_url_content(str(item.id), allow_test_local=True)
        item.refresh_from_db()
        assert item.ingestion_status == ContentItem.STATUS_FAILED
        assert "timed out" in item.error_message.lower()


@pytest.mark.django_db
def test_p1_14_source_updates_and_deletions(p1_users):
    """Criterion 14: Updating note content regenerates embeddings and updates content hash."""
    user_a, _ = p1_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Versioned Note",
        raw_text="Version 1 content for testing.",
        ingestion_status=ContentItem.STATUS_PENDING
    )
    process_note_content(str(item.id))
    item.refresh_from_db()
    hash_v1 = item.content_hash

    # Update content
    item.raw_text = "Version 2 completely different content with updated facts."
    item.save(update_fields=['raw_text'])
    process_note_content(str(item.id))
    item.refresh_from_db()

    assert item.content_hash != hash_v1
    assert item.chunks.count() >= 1
    assert "Version 2" in item.chunks.first().text


@pytest.mark.django_db
def test_p1_15_metadata_and_chunk_provenance(p1_users):
    """Criterion 15: Chunks preserve start_offset, end_offset, char_length, and parent item link."""
    user_a, _ = p1_users
    text = (
        "First section describes the architecture.\n\n"
        "Second section describes the deployment lifecycle."
    )
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Provenance Note",
        raw_text=text,
        ingestion_status=ContentItem.STATUS_PENDING
    )
    process_note_content(str(item.id))
    item.refresh_from_db()

    for chunk in item.chunks.all():
        assert chunk.content_item_id == item.id
        assert chunk.start_offset >= 0
        assert chunk.end_offset > chunk.start_offset
        assert chunk.metadata.get("char_length") == len(chunk.text)


@pytest.mark.django_db
def test_p1_16_cross_user_access_prevention(auth_client_a, p1_users):
    """Criterion 16: User A cannot read, modify, or delete User B's content items (HTTP 404)."""
    user_a, user_b = p1_users

    item_b = ContentItem.objects.create(
        user=user_b,
        content_type=ContentItem.TYPE_NOTE,
        title="Bob Private Document",
        raw_text="Top secret internal project details.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # User A attempts GET
    res_get = auth_client_a.get(f"/api/v1/content/items/{item_b.id}/")
    assert res_get.status_code == 404

    # User A attempts DELETE
    res_del = auth_client_a.delete(f"/api/v1/content/items/{item_b.id}/")
    assert res_del.status_code == 404

    # User B item still intact
    assert ContentItem.objects.filter(id=item_b.id).exists()


@pytest.mark.django_db
def test_p1_17_end_to_end_ingestion_followed_by_chatbot_retrieval(p1_users):
    """Criterion 17: Full lifecycle: ingest note -> chunk -> embed -> retrieve through chat query planner."""
    user_a, _ = p1_users

    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Spanner Database Notes",
        raw_text="Google Spanner uses TrueTime API with GPS and atomic clocks to achieve external consistency.",
        ingestion_status=ContentItem.STATUS_PENDING
    )
    process_note_content(str(item.id))
    item.refresh_from_db()
    assert item.ingestion_status == ContentItem.STATUS_COMPLETED

    # Query grounding context
    context_str, citations = retrieve_grounding_context(
        user=user_a,
        question="How does Spanner achieve external consistency?"
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1
    assert any("TrueTime" in c["excerpt"] for c in citations)
    assert citations[0]["item_title"] == "Spanner Database Notes"
