import pytest
from unittest.mock import patch, MagicMock
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from users.models import User
from content.models import ContentItem, ContentChunk
from content.youtube import (
    extract_video_id,
    normalize_youtube_url,
    fetch_youtube_metadata,
    fetch_youtube_transcript,
    chunk_youtube_transcript,
    format_timestamp,
)
from content.tasks import process_url_content
from chat.services import retrieve_grounding_context, build_system_prompt

@pytest.fixture
def auth_user():
    return User.objects.create_user(
        email="yt.tester@mediacompile.io",
        password="TestPassword2026!",
        authjs_id="authjs_yt_test_999"
    )

def test_extract_video_id_and_normalize():
    """Verify regex patterns for all supported YouTube URL formats."""
    # Standard watch URL
    url1 = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(url1) == "dQw4w9WgXcQ"
    assert normalize_youtube_url(url1) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # With tracking parameters
    url2 = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&t=45s&si=abc123"
    assert extract_video_id(url2) == "dQw4w9WgXcQ"
    assert normalize_youtube_url(url2) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # Short youtu.be URL
    url3 = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url3) == "dQw4w9WgXcQ"
    assert normalize_youtube_url(url3) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # Shorts URL
    url4 = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
    assert extract_video_id(url4) == "dQw4w9WgXcQ"
    assert normalize_youtube_url(url4) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # Live URL
    url5 = "https://www.youtube.com/live/dQw4w9WgXcQ"
    assert extract_video_id(url5) == "dQw4w9WgXcQ"
    assert normalize_youtube_url(url5) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # Non-YouTube URL
    url_other = "https://example.com/article"
    assert extract_video_id(url_other) is None
    assert normalize_youtube_url(url_other) is None

def test_format_timestamp():
    """Verify second-to-timestamp string conversion."""
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3665) == "01:01:05"

def test_chunk_youtube_transcript():
    """Verify transcript snippets are grouped into timestamped chunks with URLs."""
    video_id = "test_vid_123"
    snippets = [
        {"text": "Welcome to the deep learning tutorial.", "start": 0.0, "duration": 3.0},
        {"text": "In this section we cover gradient descent.", "start": 3.5, "duration": 4.0},
        {"text": "Backpropagation computes analytical gradients.", "start": 8.0, "duration": 5.0},
        {"text": "We adjust weights using the learning rate parameter.", "start": 13.5, "duration": 4.5},
    ]

    chunks = chunk_youtube_transcript(snippets, video_id, f"https://www.youtube.com/watch?v={video_id}", target_chunk_chars=50)
    assert len(chunks) >= 1

    first_chunk = chunks[0]
    assert "start_time" in first_chunk["metadata"]
    assert "end_time" in first_chunk["metadata"]
    assert "timestamp" in first_chunk["metadata"]
    assert "timestamp_url" in first_chunk["metadata"]
    assert first_chunk["metadata"]["timestamp"] == "00:00"
    assert "https://www.youtube.com/watch?v=test_vid_123&t=0s" in first_chunk["metadata"]["timestamp_url"]

@pytest.mark.django_db
def test_youtube_ingestion_with_transcript(auth_user):
    """Verify complete processing task for YouTube URL with transcript."""
    item = ContentItem.objects.create(
        user=auth_user,
        content_type=ContentItem.TYPE_URL,
        source_url="https://www.youtube.com/watch?v=mock_video_success",
        title="Pending YouTube Ingestion",
        ingestion_status=ContentItem.STATUS_PENDING,
    )

    mock_snippets = [
        {"text": "The transformer architecture replaces recurrent layers with self-attention.", "start": 10.0, "duration": 5.0},
        {"text": "Multi-head attention allows the model to attend to information at different positions.", "start": 15.5, "duration": 6.0},
    ]

    mock_metadata = {
        "title": "Attention Is All You Need Video",
        "author": "DeepLearning AI",
        "description": "Video lecture on transformers.",
    }

    mock_provider = MagicMock()
    mock_provider.embed_batch.return_value = [[0.05] * 384, [0.06] * 384]
    mock_provider.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_provider.dimension = 384

    with patch("content.tasks.fetch_youtube_metadata", return_value=mock_metadata):
        with patch("content.tasks.fetch_youtube_transcript", return_value=(mock_snippets, None)):
            with patch("content.embeddings.get_embedding_provider", return_value=mock_provider):
                # Run the task directly
                process_url_content(str(item.id))

    item.refresh_from_db()
    assert item.ingestion_status == ContentItem.STATUS_COMPLETED
    assert item.content_type == ContentItem.TYPE_VIDEO
    assert item.title == "Attention Is All You Need Video"
    assert item.metadata.get("author") == "DeepLearning AI"

    chunks = item.chunks.all().order_by("chunk_index")
    assert chunks.count() >= 1
    c1 = chunks.first()
    assert c1.metadata is not None
    assert "timestamp" in c1.metadata
    assert c1.metadata["timestamp"] == "00:10"
    assert "t=10s" in c1.metadata["timestamp_url"]

@pytest.mark.django_db
def test_youtube_metadata_only_fallback(auth_user):
    """Verify Section 7.4 fallback when video has no accessible captions/transcripts."""
    item = ContentItem.objects.create(
        user=auth_user,
        content_type=ContentItem.TYPE_URL,
        source_url="https://www.youtube.com/watch?v=no_captions_video",
        title="Pending Video",
        ingestion_status=ContentItem.STATUS_PENDING,
    )

    mock_metadata = {
        "title": "Podcast Without Captions",
        "author": "Audio Only Creator",
        "description": "Episode discussing high performance computing.",
    }

    mock_provider = MagicMock()
    mock_provider.embed_batch.return_value = [[0.05] * 384]
    mock_provider.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_provider.dimension = 384

    # Simulate captions disabled / no transcript available
    with patch("content.tasks.fetch_youtube_metadata", return_value=mock_metadata):
        with patch("content.tasks.fetch_youtube_transcript", return_value=(None, "No captions found")):
            with patch("content.embeddings.get_embedding_provider", return_value=mock_provider):
                process_url_content(str(item.id))

    item.refresh_from_db()
    # Must be marked PARTIAL, preserving metadata without crashing or fabricating transcripts
    assert item.ingestion_status == ContentItem.STATUS_PARTIAL
    assert item.content_type == ContentItem.TYPE_VIDEO
    assert item.title == "Podcast Without Captions"
    assert "transcript unavailable" in item.error_message.lower()

@pytest.mark.django_db
def test_chat_retrieval_with_youtube_citations(auth_user):
    """Verify RAG retrieval context and citation payloads preserve YouTube timestamps."""
    item = ContentItem.objects.create(
        user=auth_user,
        content_type=ContentItem.TYPE_VIDEO,
        source_url="https://www.youtube.com/watch?v=test_rag_vid",
        title="Vector Databases in Production",
        ingestion_status=ContentItem.STATUS_COMPLETED,
    )

    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="HNSW graphs construct hierarchical proximity graphs for approximate nearest neighbor search.",
        start_offset=0,
        end_offset=95,
        embedding=[0.01] * 384,
        metadata={
            "timestamp": "02:15",
            "timestamp_seconds": 135.0,
            "timestamp_url": "https://www.youtube.com/watch?v=test_rag_vid&t=135s",
            "source_type": "youtube_transcript",
        }
    )


    with patch("chat.services.vector_search") as mock_search:
        mock_search.return_value = [
            {
                "chunk_id": str(chunk.id),
                "text": chunk.text,
                "item": {
                    "id": str(item.id),
                    "title": item.title,
                    "source_url": item.source_url,
                },
                "chunk_index": 0,
                "score": 0.88,
                "metadata": chunk.metadata,
                "retrieval_mode": "hybrid",
            }
        ]

        context_text, citations = retrieve_grounding_context(user=auth_user, question="How does HNSW work?")

    assert len(citations) == 1
    cit = citations[0]
    assert cit["item_title"] == "Vector Databases in Production"
    assert cit["timestamp"] == "02:15"
    assert cit["timestamp_seconds"] == 135.0
    assert "t=135s" in cit["timestamp_url"]
    assert "Timestamp 02:15" in context_text
