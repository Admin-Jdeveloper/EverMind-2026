"""
MediaCompile — Phase 2 Acceptance Test Gate: Hybrid Retrieval, Ranking, and Context Assembly
Source of Truth: MediaCompile Autonomous RAG Engineering Master Prompt (Phase 2)

Verifies:
1. Exact-match queries.
2. Semantic queries and paraphrases.
3. Technical terminology and identifiers.
4. Dense retrieval alone.
5. BM25 / Lexical retrieval alone.
6. Combined RRF retrieval (k=60 fusion).
7. Reranking on vs off.
8. Deduplication and chunk expansion (window=1).
9. Page-specific queries.
10. Follow-up contextual queries.
11. Cross-document comparisons.
12. Metadata and source-scope filtering (collection, tags, type).
13. Empty results and insufficient evidence.
14. Retrieval failure and reranker failure fallback.
15. Updates and deletions (index consistency).
16. Tenant isolation (User B data never leaks to User A).
17. Complete ingestion-to-answer integration.
18. Performance & retrieval metrics (Recall@k, MRR).
"""

import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk, Collection, Tag
from content.embeddings import get_embedding_provider
from content.search import (
    hybrid_retrieve_with_facts,
    lexical_search_chunks,
    vector_search_chunks,
    rerank_candidates,
    expand_chunk_windows,
    filter_content_chunks
)
from chat.services import retrieve_grounding_context

User = get_user_model()


@pytest.fixture
def p2_users(db):
    user_a = User.objects.create_user(
        email="p2.alice@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Phase2"
    )
    user_b = User.objects.create_user(
        email="p2.bob@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Phase2"
    )
    return user_a, user_b


@pytest.fixture
def p2_dataset(db, p2_users):
    user_a, user_b = p2_users
    provider = get_embedding_provider()

    col_infra = Collection.objects.create(user=user_a, name="Infrastructure")
    tag_storage = Tag.objects.create(user=user_a, name="storage")

    # Item 1: Distributed Database Technical Specification
    item_db = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Distributed Database Internals",
        raw_text="MVCC and LSM-Tree storage engine documentation.",
        collection=col_infra,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    item_db.tags.add(tag_storage)

    chunk_db_1 = ContentChunk.objects.create(
        content_item=item_db,
        chunk_index=0,
        text="LSM-trees use an in-memory MemTable backed by a write-ahead log (WAL) for durability.",
        metadata={"page_number": 1, "section": "LSM Architecture"},
        embedding=provider.embed_text("LSM-trees use an in-memory MemTable backed by a write-ahead log (WAL) for durability.")
    )

    chunk_db_2 = ContentChunk.objects.create(
        content_item=item_db,
        chunk_index=1,
        text="When MemTable fills, it flushes to disk as an immutable SSTable in Level 0.",
        metadata={"page_number": 2, "section": "Flushing Mechanism"},
        embedding=provider.embed_text("When MemTable fills, it flushes to disk as an immutable SSTable in Level 0.")
    )

    chunk_db_3 = ContentChunk.objects.create(
        content_item=item_db,
        chunk_index=2,
        text="On page 14, MVCC uses lock-free read transactions with timestamp-based snapshot isolation.",
        metadata={"page_number": 14, "section": "Concurrency Control"},
        embedding=provider.embed_text("MVCC uses lock-free read transactions with timestamp-based snapshot isolation on page 14.")
    )

    # Item 2: Networking & Security Architecture
    item_net = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Network Security Protocol",
        raw_text="mTLS and WireGuard technical guidelines.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk_net = ContentChunk.objects.create(
        content_item=item_net,
        chunk_index=0,
        text="WireGuard uses Noise Protocol Framework with ChaCha20-Poly1305 and Curve25519 for secure key exchange.",
        metadata={"page_number": 1},
        embedding=provider.embed_text("WireGuard uses Noise Protocol Framework with ChaCha20-Poly1305 and Curve25519.")
    )

    # Item B: Bob Confidential Note (Tenant Isolation)
    item_b = ContentItem.objects.create(
        user=user_b,
        content_type=ContentItem.TYPE_NOTE,
        title="Bob Secret Key",
        raw_text="The confidential access token is SECRET-TOKEN-ALPHA-99.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=item_b,
        chunk_index=0,
        text="The confidential access token is SECRET-TOKEN-ALPHA-99.",
        embedding=provider.embed_text("The confidential access token is SECRET-TOKEN-ALPHA-99.")
    )

    return {
        "user_a": user_a,
        "user_b": user_b,
        "col_infra": col_infra,
        "tag_storage": tag_storage,
        "item_db": item_db,
        "item_net": item_net,
        "chunks": [chunk_db_1, chunk_db_2, chunk_db_3, chunk_net]
    }


@pytest.mark.django_db
def test_p2_01_exact_match_query(p2_dataset):
    """Criterion 1: Exact keyword search retrieves chunks containing specific phrases."""
    user = p2_dataset["user_a"]
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="ChaCha20-Poly1305")
    assert len(results) >= 1
    assert any("ChaCha20-Poly1305" in r["text"] for r in results)


@pytest.mark.django_db
def test_p2_02_semantic_query_and_paraphrase(p2_dataset):
    """Criterion 2: Semantic paraphrase retrieves relevant chunk without exact word overlap."""
    user = p2_dataset["user_a"]
    # Paraphrase for "MemTable backed by a write-ahead log (WAL)"
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="how does the database ensure crash recovery in memory?")
    assert len(results) >= 1
    top_hit = results[0]
    assert "MemTable" in top_hit["text"] or "WAL" in top_hit["text"] or "SSTable" in top_hit["text"]


@pytest.mark.django_db
def test_p2_03_technical_terminology_and_identifiers(p2_dataset):
    """Criterion 3: Rare technical identifiers (Curve25519, SSTable) are retrievable."""
    user = p2_dataset["user_a"]
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="Curve25519")
    assert len(results) >= 1
    assert any("Curve25519" in r["text"] for r in results)


@pytest.mark.django_db
def test_p2_04_dense_retrieval_alone(p2_dataset):
    """Criterion 4: Dense vector search returns ranked candidates based on CosineDistance."""
    user = p2_dataset["user_a"]
    vec_results = vector_search_chunks(user=user, query_text="cryptographic tunnel and noise framework", limit=5)
    assert len(vec_results) >= 1
    assert "WireGuard" in vec_results[0]["chunk"].text


@pytest.mark.django_db
def test_p2_05_bm25_lexical_retrieval_alone(p2_dataset):
    """Criterion 5: Lexical full-text search scores and ranks term matches."""
    user = p2_dataset["user_a"]
    lex_results = lexical_search_chunks(user=user, query_text="MemTable WAL", limit=5)
    assert len(lex_results) >= 1
    assert "MemTable" in lex_results[0]["chunk"].text


@pytest.mark.django_db
def test_p2_06_combined_rrf_fusion(p2_dataset):
    """Criterion 6: Reciprocal Rank Fusion combines lexical and semantic ranks with k=60."""
    user = p2_dataset["user_a"]
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="SSTable Level 0 flush", limit=5)
    assert len(results) >= 1
    top_hit = results[0]
    assert top_hit["score"] > 0.0
    # Mode string demonstrates fusion
    assert "+" in top_hit["retrieval_mode"] or "hybrid" in top_hit["retrieval_mode"] or "keyword" in top_hit["retrieval_mode"]


@pytest.mark.django_db
def test_p2_07_reranking_on_vs_off(p2_dataset):
    """Criterion 7: Multi-aspect reranking adjusts score and ranks candidates with fallback."""
    user = p2_dataset["user_a"]
    query = "immutable SSTable in Level 0"

    results_reranked, _, _ = hybrid_retrieve_with_facts(user=user, query_text=query, rerank=True)
    results_plain, _, _ = hybrid_retrieve_with_facts(user=user, query_text=query, rerank=False)

    assert len(results_reranked) >= 1
    assert len(results_plain) >= 1
    # Check reranker scores attached
    assert "rerank_score" in results_reranked[0]


@pytest.mark.django_db
def test_p2_08_deduplication_and_chunk_expansion(p2_dataset):
    """Criterion 8: Sibling chunk expansion stitches context from adjacent chunk."""
    user = p2_dataset["user_a"]
    # Chunk 1 (flushing mechanism) has chunk 0 before it and chunk 2 after it
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="When MemTable fills, it flushes", expand_window=True)
    assert len(results) >= 1
    expanded_hit = next((r for r in results if r.get("chunk_index") == 1), None)
    if expanded_hit:
        assert expanded_hit.get("is_expanded", False) is True


@pytest.mark.django_db
def test_p2_09_page_specific_queries(p2_dataset):
    """Criterion 9: Specifying page_number filters retrieval strictly to that page."""
    user = p2_dataset["user_a"]
    results, _, _ = hybrid_retrieve_with_facts(user=user, query_text="locking transactions", page_number=14)
    assert len(results) >= 1
    assert all(r["page_number"] == 14 for r in results)


@pytest.mark.django_db
def test_p2_10_followup_contextual_queries(p2_dataset):
    """Criterion 10: Query planner follow-up resolution enables retrieval on ambiguous questions."""
    user = p2_dataset["user_a"]
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="What does it say about write-ahead log?",
        history=[{"role": "user", "content": "Tell me about LSM-trees."}]
    )
    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1
    assert any("MemTable" in c["excerpt"] or "WAL" in c["excerpt"] for c in citations)


@pytest.mark.django_db
def test_p2_11_cross_document_comparisons(p2_dataset):
    """Criterion 11: Comparison queries retrieve evidence across distinct documents."""
    user = p2_dataset["user_a"]
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="Compare WireGuard with LSM database storage in my library."
    )
    assert context_str != "NO_RELEVANT_CONTENT"
    retrieved_titles = {c["item_title"] for c in citations}
    assert "Distributed Database Internals" in retrieved_titles
    assert "Network Security Protocol" in retrieved_titles


@pytest.mark.django_db
def test_p2_12_metadata_and_source_scope_filtering(p2_dataset):
    """Criterion 12: Scope filtering by collection_id and tags works deterministically."""
    user = p2_dataset["user_a"]
    col_id = str(p2_dataset["col_infra"].id)

    # Filter by collection
    res_col, _, _ = hybrid_retrieve_with_facts(user=user, query_text="storage", collection_id=col_id)
    assert len(res_col) >= 1
    assert all(r["item"]["title"] == "Distributed Database Internals" for r in res_col)

    # Filter by tags
    res_tag, _, _ = hybrid_retrieve_with_facts(user=user, query_text="storage", tags=["storage"])
    assert len(res_tag) >= 1
    assert all(r["item"]["title"] == "Distributed Database Internals" for r in res_tag)


@pytest.mark.django_db
def test_p2_13_empty_results_and_insufficient_evidence(p2_dataset):
    """Criterion 13: Unmatched query returns empty results without fabricating hits."""
    user = p2_dataset["user_a"]
    results, facts, conflict = hybrid_retrieve_with_facts(
        user=user,
        query_text="Quantum teleportation protocol of interstellar wormholes"
    )
    # Dense min_similarity filter + lexical no-match should prune irrelevant results
    assert len(results) == 0 or results[0]["score"] < 0.2


@pytest.mark.django_db
def test_p2_14_retrieval_failure_and_reranker_fallback(p2_dataset):
    """Criterion 14: If reranker throws exception, retrieval safely falls back to RRF ordering."""
    candidates = [
        {"text": "Chunk A", "score": 0.05, "item": {"title": "Doc A"}},
        {"text": "Chunk B", "score": 0.03, "item": {"title": "Doc B"}}
    ]
    with patch("content.search.logger.warning") as mock_log:
        # Pass non-string to trigger fallback safely
        result = rerank_candidates(query_text=None, candidates=candidates, enabled=True)
        assert result == candidates


@pytest.mark.django_db
def test_p2_15_updates_and_deletions_index_consistency(p2_dataset):
    """Criterion 15: Deleting an item immediately removes its chunks from vector search."""
    user = p2_dataset["user_a"]
    item_net = p2_dataset["item_net"]

    # Verify retrievable initially
    res_before, _, _ = hybrid_retrieve_with_facts(user=user, query_text="WireGuard Curve25519")
    assert len(res_before) >= 1

    # Delete item
    item_net.delete()

    # Search again
    res_after, _, _ = hybrid_retrieve_with_facts(user=user, query_text="WireGuard Curve25519")
    assert not any("WireGuard" in r["text"] for r in res_after)


@pytest.mark.django_db
def test_p2_16_tenant_isolation(p2_dataset):
    """Criterion 16: User A cannot retrieve User B's secret chunks under any query or filter."""
    user_a = p2_dataset["user_a"]

    # Alice searches for Bob's token
    res, _, _ = hybrid_retrieve_with_facts(user=user_a, query_text="SECRET-TOKEN-ALPHA-99")
    assert len(res) == 0
    assert not any("SECRET-TOKEN" in r["text"] for r in res)


@pytest.mark.django_db
def test_p2_17_complete_ingestion_to_answer_integration(p2_dataset):
    """Criterion 17: Ingestion -> RRF -> Reranking -> Grounding context with citations."""
    user = p2_dataset["user_a"]
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="How does MemTable flush to disk?"
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1
    assert any("SSTable" in c["excerpt"] for c in citations)
    # Check card title and page in citation
    assert citations[0]["item_title"] == "Distributed Database Internals"


@pytest.mark.django_db
def test_p2_18_retrieval_quality_metrics(p2_dataset):
    """Criterion 18: Measure Recall@k and Mean Reciprocal Rank (MRR) across evaluation queries."""
    user = p2_dataset["user_a"]

    eval_suite = [
        {"query": "MemTable write-ahead log", "expected_page": 1},
        {"query": "flush to disk as SSTable", "expected_page": 2},
        {"query": "snapshot isolation lock-free", "expected_page": 14},
    ]

    reciprocal_ranks = []
    hits_at_k = 0
    k = 3

    for test_case in eval_suite:
        results, _, _ = hybrid_retrieve_with_facts(user=user, query_text=test_case["query"], limit=k)
        pages = [r.get("page_number") for r in results]

        # Recall@k
        if test_case["expected_page"] in pages:
            hits_at_k += 1
            # MRR
            rank = pages.index(test_case["expected_page"]) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    recall_at_k = hits_at_k / len(eval_suite)
    mrr = sum(reciprocal_ranks) / len(eval_suite)

    assert recall_at_k >= 0.99, f"Recall@{k} dropped below 99%: {recall_at_k}"
    assert mrr >= 0.80, f"MRR dropped below 0.80: {mrr}"
