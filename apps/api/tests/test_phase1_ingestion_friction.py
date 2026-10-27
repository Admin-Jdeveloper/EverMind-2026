"""
MediaCompile — Phase 1: Upload Friction & Ingestion Simplification Test Suite.
Source of Truth: Phase 1 Specifications & MediaCompile-prompt.md

Validates:
1. Every supported document format (PDF, DOCX, PPTX, XLSX, CSV, TXT, MD) uploads and ingests.
2. Missing metadata is permitted without failing (note title auto-derived, doc title from filename, URL title from HTML).
3. Public article URLs from different domains are accepted without manual allowlist registration.
4. Failed URL extractions preserve original item and URL, marked failed, and can be retried via POST /items/{id}/retry/.
5. Oversized files (> 15MB) are rejected with clear error.
6. Malformed files (spoofed extension with invalid header) are rejected with clear validation error.
7. Duplicate URL submissions are handled idempotently.
8. Multi-tenant user isolation is strictly enforced.
"""

import io
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import ContentItem, ContentChunk
from content.security import SSRFProtectionError

User = get_user_model()

@pytest.fixture
def phase1_users(db):
    user_a = User.objects.create_user(
        email="alice.phase1@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Phase1"
    )
    user_b = User.objects.create_user(
        email="bob.phase1@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Phase1"
    )
    return user_a, user_b

# ------------------------------------------------------------------------------
# 1. Missing Metadata & Zero-Friction Notes
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_note_ingestion_without_title_auto_derives(phase1_users):
    """Verify users can save notes without title; title is auto-derived from content."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    res = client.post('/api/v1/content/notes/', data={
        "content": "First line becomes the title\nSecond line contains detailed explanation."
    }, format="json")

    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "First line becomes the title"
    assert data["content_type"] == "note"
    assert data["ingestion_status"] == ContentItem.STATUS_COMPLETED
    assert ContentChunk.objects.filter(content_item_id=data["id"]).count() >= 1

# ------------------------------------------------------------------------------
# 2. Every Supported Document Format
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_all_supported_document_formats_upload(phase1_users, monkeypatch):
    """Verify PDF, DOCX, PPTX, XLSX, CSV, TXT, MD are accepted without friction."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    # Mock MinIO storage and text extractors
    monkeypatch.setattr("content.views.upload_file_bytes", lambda **kw: f"mock-key-{kw['filename']}")

    # Formats with their valid minimal magic bytes
    formats = [
        ("report.pdf", b"%PDF-1.4 sample pdf content stream", "application/pdf"),
        ("document.docx", b"PK\x03\x04\x14\x00\x00\x00word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("slides.pptx", b"PK\x03\x04\x14\x00\x00\x00ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("data.xlsx", b"PK\x03\x04\x14\x00\x00\x00xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("sheet.csv", b"col1,col2\nval1,val2\n", "text/csv"),
        ("notes.txt", b"Plain text note without title", "text/plain"),
        ("readme.md", b"# Markdown Header\nSome body text", "text/markdown"),
    ]

    for filename, content, mime in formats:
        file_obj = SimpleUploadedFile(filename, content, content_type=mime)
        res = client.post('/api/v1/content/files/', data={
            "file": file_obj
        }, format="multipart")

        assert res.status_code in (201, 202), f"Failed for format {filename}: {res.data}"
        assert res.json()["title"] == filename

# ------------------------------------------------------------------------------
# 3. Public URLs from Different Domains (No Domain Whitelist)
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_public_urls_different_domains_accepted(phase1_users, monkeypatch):
    """Verify arbitrary public domains (arxiv.org, github.com, wikipedia.org) are accepted."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    # Mock safe_fetch_url to avoid live outbound networks during tests
    def mock_fetch(url, *args, **kwargs):
        domain = url.split("//")[1].split("/")[0]
        html = f"<html><head><title>Article from {domain}</title></head><body><p>Substantive article content from {domain} with enough characters to pass validation.</p></body></html>"
        return 200, "text/html", html.encode("utf-8")

    monkeypatch.setattr("content.tasks.safe_fetch_url", mock_fetch)

    test_urls = [
        "https://arxiv.org/abs/2301.00001",
        "https://en.wikipedia.org/wiki/Distributed_computing",
        "https://github.com/blog/2026-tech-update",
        "https://news.ycombinator.com/item?id=12345",
    ]

    for test_url in test_urls:
        res = client.post(
            '/api/v1/content/urls/',
            data={"url": test_url},
            format="json",
            HTTP_X_SYNC_INGESTION="true"
        )
        assert res.status_code == 201, f"Failed for {test_url}: {res.data}"
        assert res.json()["ingestion_status"] == ContentItem.STATUS_COMPLETED
        assert "arxiv.org" in res.json()["title"] or "wikipedia" in res.json()["title"] or "github" in res.json()["title"] or "ycombinator" in res.json()["title"]

# ------------------------------------------------------------------------------
# 4. Duplicate URL Submissions Handled Idempotently
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_duplicate_url_submission_reuses_item(phase1_users, monkeypatch):
    """Verify submitting the same URL updates and re-queues without duplicating library records."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    def mock_fetch(url, *args, **kwargs):
        return 200, "text/html", b"<html><title>Sample Title</title><body><p>This is a complete and substantive article text that has more than fifty characters to pass all extraction thresholds.</p></body></html>"

    monkeypatch.setattr("content.tasks.safe_fetch_url", mock_fetch)

    url = "https://example.com/unique-article"
    res1 = client.post('/api/v1/content/urls/', data={"url": url}, format="json", HTTP_X_SYNC_INGESTION="true")
    assert res1.status_code == 201
    item_id_1 = res1.json()["id"]

    # Submit exact same URL again with updated title
    res2 = client.post('/api/v1/content/urls/', data={"url": url, "title": "Updated Custom Title"}, format="json", HTTP_X_SYNC_INGESTION="true")
    assert res2.status_code == 201
    item_id_2 = res2.json()["id"]

    assert item_id_1 == item_id_2
    assert ContentItem.objects.filter(user=user_a, source_url=url).count() == 1

# ------------------------------------------------------------------------------
# 5. Failed Extraction Preserves Record & Enables Retry
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_failed_url_extraction_preserves_item_and_can_retry(phase1_users, monkeypatch):
    """Verify failed URLs are marked failed, preserved in DB, and retryable."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    # 1. Fail fetch
    def failing_fetch(url, *args, **kwargs):
        raise SSRFProtectionError("HTTP 404 error fetching 'https://example.com/not-found': Not Found")

    monkeypatch.setattr("content.tasks.safe_fetch_url", failing_fetch)

    res = client.post(
        '/api/v1/content/urls/',
        data={"url": "https://example.com/not-found"},
        format="json",
        HTTP_X_SYNC_INGESTION="true"
    )
    assert res.status_code == 201
    item_id = res.json()["id"]
    item = ContentItem.objects.get(id=item_id)
    assert item.ingestion_status == ContentItem.STATUS_FAILED
    assert "HTTP 404 error" in item.error_message

    # 2. Now simulate site becomes available and call retry endpoint
    def success_fetch(url, *args, **kwargs):
        return 200, "text/html", b"<html><title>Recovered Page</title><body><p>This is a recovered article text with enough characters to pass all extraction validations.</p></body></html>"

    monkeypatch.setattr("content.tasks.safe_fetch_url", success_fetch)

    retry_res = client.post(f'/api/v1/content/items/{item_id}/retry/', HTTP_X_SYNC_INGESTION="true")
    assert retry_res.status_code == 200
    item.refresh_from_db()
    assert item.ingestion_status == ContentItem.STATUS_COMPLETED
    assert item.error_message == ""
    assert item.chunks.count() >= 1

# ------------------------------------------------------------------------------
# 6. Oversized and Malformed Files Rejected with Clear Errors
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_oversized_file_rejected(phase1_users):
    """Verify files exceeding 15MB are rejected with clear error."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    # 16 MB dummy file
    big_data = b"0" * (16 * 1024 * 1024)
    file_obj = SimpleUploadedFile("big.txt", big_data, content_type="text/plain")

    res = client.post('/api/v1/content/files/', data={"file": file_obj}, format="multipart")
    assert res.status_code == 400
    assert "exceeds" in str(res.data)

@pytest.mark.django_db
def test_malformed_spoofed_pdf_rejected(phase1_users):
    """Verify spoofed PDF without %PDF- header is rejected with clear error."""
    user_a, _ = phase1_users
    client = APIClient()
    client.force_authenticate(user=user_a)

    fake_pdf = SimpleUploadedFile("fake.pdf", b"NOT_A_REAL_PDF_STREAM", content_type="application/pdf")
    res = client.post('/api/v1/content/files/', data={"file": fake_pdf}, format="multipart")
    assert res.status_code == 400
    assert "Missing %PDF- signature" in str(res.data)

# ------------------------------------------------------------------------------
# 7. User Isolation on Retry & Library Management
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_b_cannot_retry_or_view_user_a_items(phase1_users):
    """Verify User B receives 404 when attempting to access User A's content item."""
    user_a, user_b = phase1_users
    client_b = APIClient()
    client_b.force_authenticate(user=user_b)

    item_a = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Private Secrets",
        raw_text="Confidential data",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # Attempt to retrieve
    res = client_b.get(f'/api/v1/content/items/{item_a.id}/')
    assert res.status_code == 404

    # Attempt to retry
    retry_res = client_b.post(f'/api/v1/content/items/{item_a.id}/retry/')
    assert retry_res.status_code == 404
