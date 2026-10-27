import pytest
import io
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from users.models import User
from content.models import ContentItem, ContentChunk, Collection, Tag
from content.services import chunk_text, extract_text_from_html, extract_text_from_txt

@pytest.fixture
def auth_user():
    return User.objects.create_user(
        email="ingest.tester@mediacompile.io",
        password="TestPassword2026!",
        authjs_id="authjs_ingest_test_123"
    )

@pytest.fixture
def auth_client(auth_user):
    client = APIClient()
    client.force_authenticate(user=auth_user)
    return client

@pytest.mark.django_db
def test_chunking_engine():
    """Verify text chunker splits text with correct character offsets and ordering."""
    sample_text = (
        "Distributed consensus algorithms ensure that multiple nodes agree on a shared state. " * 15 +
        "\n\n" +
        "Raft achieves consensus via leader election and log replication. " * 10
    )
    
    chunks = chunk_text(sample_text, chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1

    for idx, c in enumerate(chunks):
        assert c['chunk_index'] == idx
        assert c['char_length'] > 0
        assert c['start_offset'] >= 0
        assert c['end_offset'] <= len(sample_text.strip())
        assert sample_text.strip()[c['start_offset']:c['end_offset']].strip() == c['text']

@pytest.mark.django_db
def test_html_extraction_boilerplate_removal():
    """Verify HTML extractor cleans scripts, navs, and styles while preserving core body."""
    html = b"""
    <html>
      <head><title>Vector DB Guide</title><style>body { color: red; }</style></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <article>
          <h1>Vector Indexing</h1>
          <p>HNSW graphs provide logarithmic lookup complexity.</p>
        </article>
        <footer>Copyright 2026</footer>
        <script>alert("evil");</script>
      </body>
    </html>
    """
    title, text, metadata = extract_text_from_html(html)
    assert title == "Vector DB Guide"
    assert "HNSW graphs provide logarithmic lookup complexity." in text
    assert "Home" not in text
    assert "alert" not in text
    assert "Copyright" not in text
    assert isinstance(metadata, dict)

@pytest.mark.django_db
def test_ingest_plain_note_endpoint(auth_client, auth_user):
    """Verify note ingestion creates ContentItem, chunks, and returns HTTP 201."""
    res = auth_client.post('/api/v1/content/notes/', {
        'title': 'Raft Election Safety',
        'content': 'At most one leader can be elected in a given term. Raft guarantees this using election timeouts.',
        'tags': ['consensus', 'distributed-systems']
    }, format='json')

    assert res.status_code == 201
    data = res.json()
    assert data['title'] == 'Raft Election Safety'
    assert data['content_type'] == 'note'
    assert data['ingestion_status'] == 'completed'
    assert data['chunk_count'] >= 1
    assert 'consensus' in data['tags_list']

    item = ContentItem.objects.get(id=data['id'])
    assert item.user == auth_user
    assert item.chunks.count() >= 1

@pytest.mark.django_db
def test_ingest_url_ssrf_rejection(auth_client):
    """Verify URL ingestion endpoint blocks private/loopback URLs before processing."""
    # 1. Test standard port loopback (resolves to private/loopback IP)
    res_loopback = auth_client.post('/api/v1/content/urls/', {
        'url': 'http://127.0.0.1/internal-api',
        'title': 'Loopback Attack'
    }, format='json')
    assert res_loopback.status_code == 400
    assert 'url' in res_loopback.json()
    assert 'resolves to protected/private IP' in str(res_loopback.json()['url'])

    # 2. Test prohibited internal port
    res_port = auth_client.post('/api/v1/content/urls/', {
        'url': 'http://127.0.0.1:8000/internal-api',
        'title': 'Port Attack'
    }, format='json')
    assert res_port.status_code == 400
    assert 'Prohibited port' in str(res_port.json()['url'])

@pytest.mark.django_db
def test_upload_document_endpoint_with_minio(auth_client, auth_user):
    """Verify uploading a document stores in MinIO, extracts text, and creates chunks."""
    file_content = b"This is a field report on vector databases in production. Embeddings allow semantic retrieval."
    uploaded = SimpleUploadedFile(
        "vector_report.txt",
        file_content,
        content_type="text/plain"
    )

    res = auth_client.post(
        '/api/v1/content/files/',
        {'file': uploaded, 'title': 'Vector Report 2026'},
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )

    assert res.status_code == 201
    data = res.json()
    assert data['title'] == 'Vector Report 2026'
    assert data['content_type'] == 'document'
    assert data['ingestion_status'] == 'completed'

    item = ContentItem.objects.get(id=data['id'])
    assert item.file_key.startswith(f"users/{auth_user.id}/files/")
    assert item.chunks.count() >= 1

    # Verify download presigned URL endpoint
    dl_res = auth_client.get(f'/api/v1/content/items/{item.id}/download/')
    assert dl_res.status_code == 200
    assert 'download_url' in dl_res.json()
    assert 'http://' in dl_res.json()['download_url']

@pytest.mark.django_db
def test_upload_disallowed_file_extension(auth_client):
    """Verify dangerous executable extensions are rejected."""
    uploaded = SimpleUploadedFile("script.exe", b"binarycontent", content_type="application/x-msdownload")
    res = auth_client.post('/api/v1/content/files/', {'file': uploaded}, format='multipart')
    assert res.status_code == 400
    assert 'Unsupported file type' in str(res.json())

# ------------------------------------------------------------------------------
# Multi-Format Ingestion Tests (PDF, DOCX, PPTX, XLSX, CSV, TXT, MD)
# ------------------------------------------------------------------------------

def test_extract_text_from_docx():
    """Verify DOCX extractor extracts headings, paragraphs, and tables."""
    import docx
    from content.services import extract_text_from_docx

    doc = docx.Document()
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("MediaCompile uses pgvector for semantic retrieval.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Component"
    table.cell(0, 1).text = "Technology"
    table.cell(1, 0).text = "VectorDB"
    table.cell(1, 1).text = "PostgreSQL"

    buf = io.BytesIO()
    doc.save(buf)
    title, text, sections_data = extract_text_from_docx(buf.getvalue())

    assert title == "Architecture Overview"
    assert "MediaCompile uses pgvector for semantic retrieval." in text
    assert "Component: VectorDB | Technology: PostgreSQL" in text
    assert len(sections_data) >= 1


def test_extract_text_from_pptx():
    """Verify PPTX extractor extracts slide numbers, titles, and body shapes."""
    import pptx
    from content.services import extract_text_from_pptx

    prs = pptx.Presentation()
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "Distributed Consensus"
    body1 = slide1.shapes.placeholders[1]
    body1.text = "Raft uses randomized election timeouts."

    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "Vector Search Pipeline"
    body2 = slide2.shapes.placeholders[1]
    body2.text = "Embeddings are indexed using HNSW."

    buf = io.BytesIO()
    prs.save(buf)
    title, text, slides_data = extract_text_from_pptx(buf.getvalue())

    assert title == "Distributed Consensus"
    assert "[Slide 1: Distributed Consensus]" in text
    assert "Raft uses randomized election timeouts." in text
    assert "[Slide 2: Vector Search Pipeline]" in text
    assert "Embeddings are indexed using HNSW." in text
    assert len(slides_data) == 2
    assert slides_data[0]['slide_number'] == 1
    assert slides_data[1]['slide_number'] == 2


def test_extract_text_from_xlsx():
    """Verify XLSX extractor extracts sheet names, headers, and row relationships."""
    import openpyxl
    from content.services import extract_text_from_xlsx

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Revenue"
    ws1.append(["Quarter", "MRR", "Churn"])
    ws1.append(["Q1", "$50,000", "2.1%"])
    ws1.append(["Q2", "$65,000", "1.8%"])

    ws2 = wb.create_sheet(title="Costs")
    ws2.append(["Category", "Amount"])
    ws2.append(["Servers", "$3,500"])

    buf = io.BytesIO()
    wb.save(buf)
    title, text, rows_data = extract_text_from_xlsx(buf.getvalue())

    assert "Revenue" in title
    assert "[Sheet: Revenue | Row 2] Quarter: Q1 | MRR: $50,000 | Churn: 2.1%" in text
    assert "[Sheet: Revenue | Row 3] Quarter: Q2 | MRR: $65,000 | Churn: 1.8%" in text
    assert "[Sheet: Costs | Row 2] Category: Servers | Amount: $3,500" in text
    assert len(rows_data) == 3


def test_extract_text_from_csv():
    """Verify CSV extractor maps headers to cell values."""
    from content.services import extract_text_from_csv

    csv_data = b"City,Country,Population\nTokyo,Japan,37000000\nParis,France,2161000\n"
    title, text, rows_data = extract_text_from_csv(csv_data)

    assert "City: Tokyo | Country: Japan | Population: 37000000" in text
    assert "City: Paris | Country: France | Population: 2161000" in text
    assert len(rows_data) == 2


def test_extract_text_from_txt_and_md():
    """Verify TXT and Markdown multi-encoding extraction."""
    from content.services import extract_text_from_txt

    md_content = b"# System Architecture\n\nHigh performance semantic search using pgvector."
    title, text = extract_text_from_txt(md_content)
    assert title == "System Architecture"
    assert "High performance semantic search using pgvector." in text


def test_chunking_metadata_preservation():
    """Verify sliding-window chunker preserves structural metadata for citations."""
    sample_annotated_text = (
        "[Page 1]\n"
        "Introduction to Database Systems. Relational and vector models.\n\n"
        "[Page 2]\n"
        "Distributed consensus mechanisms guarantee linearizability across replicas.\n\n"
        "[Slide 3: Query Processing]\n"
        "Vector similarity is computed via cosine distance over normalized embeddings."
    )
    chunks = chunk_text(sample_annotated_text, chunk_size=200, chunk_overlap=30)
    assert len(chunks) >= 2

    # Verify that metadata tags are detected and populated
    has_page_meta = any(c.get('metadata', {}).get('page_number') is not None for c in chunks)
    has_slide_meta = any(c.get('metadata', {}).get('slide_number') is not None for c in chunks)
    assert has_page_meta
    assert has_slide_meta


@pytest.mark.django_db
def test_upload_empty_document_rejected(auth_client):
    """Verify uploading an empty 0-byte file is rejected."""
    empty_file = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
    res = auth_client.post('/api/v1/content/files/', {'file': empty_file}, format='multipart')
    assert res.status_code == 400
    assert "empty" in str(res.json()).lower()


@pytest.mark.django_db
def test_upload_magic_bytes_spoofing_rejected(auth_client):
    """Verify spoofed files (e.g. text file renamed to .pdf) fail magic byte checks."""
    fake_pdf = SimpleUploadedFile("document.pdf", b"Not a real PDF header", content_type="application/pdf")
    res = auth_client.post('/api/v1/content/files/', {'file': fake_pdf}, format='multipart')
    assert res.status_code == 400
    assert "invalid pdf" in str(res.json()).lower()


def test_ssrf_rejects_binary_content_types():
    """Verify safe_fetch_url rejects binary responses (images, videos, executables) for web links."""
    from content.security import safe_fetch_url, SSRFProtectionError
    from unittest.mock import patch, MagicMock

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.headers = {'Content-Type': 'application/octet-stream'}

    with patch('requests.Session.get', return_value=mock_resp):
        with pytest.raises(SSRFProtectionError) as exc_info:
            safe_fetch_url("http://example.com/binary.dat", allow_test_local=True)
        assert "Unexpected binary response" in str(exc_info.value)


@pytest.mark.django_db
def test_content_item_deletion_cascades_chunks(auth_client, auth_user):
    """Verify deleting a ContentItem cascades and cleans up all associated ContentChunks."""
    item = ContentItem.objects.create(
        user=auth_user,
        content_type=ContentItem.TYPE_NOTE,
        title="Temporary Note to Delete",
        raw_text="This note will be deleted to test chunk cleanup.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="This note will be deleted to test chunk cleanup.",
        embedding=[0.05] * 384
    )
    chunk_id = chunk.id
    assert ContentChunk.objects.filter(id=chunk_id).exists()

    # Delete via API
    del_res = auth_client.delete(f'/api/v1/content/items/{item.id}/')
    assert del_res.status_code == 204

    # Verify both item and its chunks are removed
    assert not ContentItem.objects.filter(id=item.id).exists()
    assert not ContentChunk.objects.filter(id=chunk_id).exists()

