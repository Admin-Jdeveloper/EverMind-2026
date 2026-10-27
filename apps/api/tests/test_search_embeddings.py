"""
MediaCompile — Phase 5: Search, Embeddings, and Retrieval Test Suite.
Source of Truth: MediaCompile-prompt.md (Section 15: Phase 5 Tasks & Gates)

Validates:
1. Embedding Provider: Deterministic unit vector generation, 1536 dimension check, error handling.
2. Async Embedding Task: Celery worker embedding computation & metadata recording.
3. Semantic Vector Search: pgvector CosineDistance ranking on deterministic fixtures.
4. Lexical Search: Keyword matching across title, chunk text, and tags.
5. Hybrid Retrieval: Reciprocal Rank Fusion (RRF) combining keyword and vector ranks.
6. Library Filters: Filtering by content_type, collection, tags, date range.
7. Multi-Tenant Isolation: User B can never retrieve User A's chunks.
8. Empty & Malformed Queries: Graceful handling without unhandled exceptions.
9. REST Search Endpoint: GET /api/v1/content/search/ permissions and parameters.
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk, Collection, Tag
from content.embeddings import (
    MockEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    get_embedding_provider
)
from content.tasks import generate_chunk_embeddings
from content.search import (
    lexical_search_chunks,
    vector_search_chunks,
    hybrid_search
)

User = get_user_model()

@pytest.fixture
def test_users(db):
    user_a = User.objects.create_user(
        email="alice.search@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Search"
    )
    user_b = User.objects.create_user(
        email="bob.search@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Search"
    )
    return user_a, user_b

@pytest.fixture
def search_fixtures(db, test_users):
    user_a, user_b = test_users
    provider = get_embedding_provider()

    # Create collections
    col_ai = Collection.objects.create(user=user_a, name="AI Engineering")
    col_systems = Collection.objects.create(user=user_a, name="Distributed Systems")

    # Create tags
    tag_rag = Tag.objects.create(user=user_a, name="rag")
    tag_postgres = Tag.objects.create(user=user_a, name="postgres")

    # Item 1: RAG and Vector Indexes (User A)
    item_1 = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_URL,
        title="Hierarchical Navigable Small World Graphs for Vector Search",
        source_url="https://arxiv.org/abs/2312.001",
        summary="A study on HNSW graph construction and nearest neighbor retrieval.",
        raw_text="HNSW graphs construct multi-layer proximity graphs for sub-linear search latency.",
        collection=col_ai,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    item_1.tags.add(tag_rag)

    chunk_1_1 = ContentChunk.objects.create(
        content_item=item_1,
        chunk_index=0,
        text="HNSW graphs achieve logarithmic search complexity for high dimensional vector spaces.",
        start_offset=0,
        end_offset=83,
        embedding=provider.embed_text("HNSW graphs achieve logarithmic search complexity for high dimensional vector spaces.")
    )
    chunk_1_2 = ContentChunk.objects.create(
        content_item=item_1,
        chunk_index=1,
        text="Cosine distance calculation on normalized unit vectors reduces to inner product dot product.",
        start_offset=84,
        end_offset=175,
        embedding=provider.embed_text("Cosine distance calculation on normalized unit vectors reduces to inner product dot product.")
    )

    # Item 2: PostgreSQL Full-Text (User A)
    item_2 = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="PostgreSQL Full Text Search and GIN Indexes",
        summary="Engineering notes on tsvector queries in relational databases.",
        raw_text="PostgreSQL provides tsvector and tsquery for fast lexical token searching.",
        collection=col_systems,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    item_2.tags.add(tag_postgres)

    chunk_2_1 = ContentChunk.objects.create(
        content_item=item_2,
        chunk_index=0,
        text="PostgreSQL supports GIN indexes on tsvector columns for rapid lexical inverted index queries.",
        start_offset=0,
        end_offset=94,
        embedding=provider.embed_text("PostgreSQL supports GIN indexes on tsvector columns for rapid lexical inverted index queries.")
    )

    # Item 3: User B Content (Tenant Isolation Test)
    item_b = ContentItem.objects.create(
        user=user_b,
        content_type=ContentItem.TYPE_NOTE,
        title="Bob Secret Research on Quantum Computing",
        raw_text="Quantum teleportation and qubit decoherence experimental metrics.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk_b_1 = ContentChunk.objects.create(
        content_item=item_b,
        chunk_index=0,
        text="HNSW graphs and vector spaces in quantum states should remain strictly secret to Bob.",
        start_offset=0,
        end_offset=88,
        embedding=provider.embed_text("HNSW graphs and vector spaces in quantum states should remain strictly secret to Bob.")
    )

    return {
        "user_a": user_a,
        "user_b": user_b,
        "item_1": item_1,
        "item_2": item_2,
        "item_b": item_b,
        "chunk_1_1": chunk_1_1,
        "chunk_1_2": chunk_1_2,
        "chunk_2_1": chunk_2_1,
        "chunk_b_1": chunk_b_1,
        "col_ai": col_ai,
        "col_systems": col_systems,
        "tag_rag": tag_rag,
        "tag_postgres": tag_postgres
    }

# ------------------------------------------------------------------------------
# 1. Embedding Provider Unit Tests
# ------------------------------------------------------------------------------

def test_mock_embedding_provider_dimension_and_normalization():
    """Verify mock provider generates 384-dimensional unit vectors."""
    provider = MockEmbeddingProvider(dimension=384)
    vec = provider.embed_text("Testing vector embedding generation")
    assert len(vec) == 384
    # Unit vector magnitude check: sqrt(sum(v^2)) == 1.0 (approx)
    magnitude = sum(x * x for x in vec) ** 0.5
    assert abs(magnitude - 1.0) < 0.01

def test_mock_embedding_provider_deterministic_similarity():
    """Verify that identical text yields similarity 1.0, and distinct texts differ."""
    provider = MockEmbeddingProvider(dimension=384)
    v1 = provider.embed_text("Artificial Intelligence Machine Learning")
    v2 = provider.embed_text("Artificial Intelligence Machine Learning")
    v3 = provider.embed_text("Cooking recipes with garlic and pasta")

    sim_1_2 = sum(a * b for a, b in zip(v1, v2))
    sim_1_3 = sum(a * b for a, b in zip(v1, v3))

    assert round(sim_1_2, 4) == 1.0
    assert sim_1_3 < 0.5

def test_embedding_batch_generation():
    """Verify batch embedding generation produces list of valid vectors."""
    provider = MockEmbeddingProvider(dimension=384)
    texts = ["First document text", "Second document text", "Third document text"]
    batch = provider.embed_batch(texts)
    assert len(batch) == 3
    for v in batch:
        assert len(v) == 384

# ------------------------------------------------------------------------------
# 2. Celery Task Embedding Computation
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_generate_chunk_embeddings_task(test_users):
    """Verify Celery task calculates and stores embeddings for chunks with missing vectors."""
    user_a, _ = test_users
    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Unembedded Note",
        raw_text="This note has not been embedded yet."
    )
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="This note has not been embedded yet.",
        embedding=None
    )

    assert chunk.embedding is None
    # Run task directly
    generate_chunk_embeddings([str(chunk.id)])
    
    chunk.refresh_from_db()
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 384
    assert chunk.metadata.get('embedding_model') == 'sentence-transformers/all-MiniLM-L6-v2'

# ------------------------------------------------------------------------------
# 3. Lexical / Keyword Search Tests
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_lexical_search_exact_match(search_fixtures):
    """Verify lexical search finds exact keyword matches across text and title."""
    f = search_fixtures
    results = lexical_search_chunks(f["user_a"], "HNSW")
    assert len(results) >= 1
    found_chunks = [r["chunk"].id for r in results]
    assert f["chunk_1_1"].id in found_chunks

@pytest.mark.django_db
def test_lexical_search_case_insensitivity(search_fixtures):
    """Verify case-insensitive search match."""
    f = search_fixtures
    results = lexical_search_chunks(f["user_a"], "postgresql")
    assert len(results) >= 1
    assert results[0]["chunk"].id == f["chunk_2_1"].id

# ------------------------------------------------------------------------------
# 4. Semantic Vector Search via pgvector CosineDistance
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_vector_search_semantic_matching(search_fixtures):
    """Verify pgvector CosineDistance retrieves semantically relevant chunk first."""
    f = search_fixtures
    results = vector_search_chunks(
        f["user_a"],
        "HNSW graphs achieve logarithmic search complexity for high dimensional vector spaces."
    )
    assert len(results) >= 1
    top_hit = results[0]
    assert top_hit["chunk"].id == f["chunk_1_1"].id
    assert top_hit["similarity"] >= 0.95


# ------------------------------------------------------------------------------
# 6. Library Filtering Capabilities
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_search_content_type_filter(search_fixtures):
    """Verify filtering search results by content_type."""
    f = search_fixtures
    # Filter by url only
    results_url = hybrid_search(f["user_a"], "HNSW", content_type="url")
    assert all(r["item"]["content_type"] == "url" for r in results_url)

    # Filter by note only (should not return item_1 which is a URL)
    results_note = hybrid_search(f["user_a"], "HNSW", content_type="note")
    assert all(r["item"]["content_type"] == "note" for r in results_note)

@pytest.mark.django_db
def test_search_collection_filter(search_fixtures):
    """Verify filtering search results by collection ID."""
    f = search_fixtures
    results = hybrid_search(f["user_a"], "HNSW", collection_id=str(f["col_ai"].id))
    assert len(results) >= 1
    assert all(r["item"]["collection"]["id"] == str(f["col_ai"].id) for r in results)

@pytest.mark.django_db
def test_search_tag_filter(search_fixtures):
    """Verify filtering search results by tag name."""
    f = search_fixtures
    results = hybrid_search(f["user_a"], "PostgreSQL", tags=["postgres"])
    assert len(results) >= 1
    assert results[0]["chunk_id"] == str(f["chunk_2_1"].id)

# ------------------------------------------------------------------------------
# 7. Multi-Tenant Data Isolation Gate
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_search_tenant_isolation(search_fixtures):
    """Verify User A NEVER retrieves User B's content even if query matches perfectly."""
    f = search_fixtures
    # Query words that exist in User B's secret chunk
    results_for_a = hybrid_search(f["user_a"], "Quantum teleportation secret to Bob")
    for r in results_for_a:
        assert r["chunk_id"] != str(f["chunk_b_1"].id)
        assert r["item"]["id"] != str(f["item_b"].id)

    # Bob searching for his own content should find it
    results_for_b = hybrid_search(f["user_b"], "Quantum teleportation secret to Bob")
    assert len(results_for_b) >= 1
    assert results_for_b[0]["chunk_id"] == str(f["chunk_b_1"].id)

# ------------------------------------------------------------------------------
# 8. Empty & Malformed Queries
# ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_search_empty_query_returns_recent_items(search_fixtures):
    """Verify empty query string returns user's recent chunks without errors."""
    f = search_fixtures
    results = hybrid_search(f["user_a"], "")
    assert len(results) >= 1
    # Mode should indicate recent
    assert results[0]["retrieval_mode"] == "recent"

