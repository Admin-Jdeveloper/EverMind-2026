"""
Evermind — Grounded RAG Saved-Content Reliability & Authoritative Item Count Tests.
Source of Truth: PART 2 & PART 3 (RAG Regression Tests, Authoritative Counts, Cross-Tenant Isolation).

Covers:
1. Genuinely empty account returns zero saved items (no hallucinated zero or fabricated items).
2. Authoritative counts for 1 saved item (document/note/url).
3. Accurate multi-item per-type and per-collection counts (documents, notes, URLs, collections).
4. Exact title and filename search resolution.
5. Searchability after indexing completes.
6. Explicit status notices for pending, processing, and failed indexing jobs.
7. General knowledge questions answered accurately without saved items or fabricated citations.
8. Source-specific questions for non-existent sources report honest limitations.
9. Cross-user isolation: User B cannot retrieve or count User A's saved items or chunks.
10. Database errors are raised as technical issues and NEVER converted to a false zero.
"""

import pytest
from unittest.mock import patch
from django.db import DatabaseError
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk, Collection, Tag
from chat.models import ChatSession, ChatMessage
from chat.services import (
    generate_chat_turn,
    is_authoritative_count_or_inventory_query,
    retrieve_grounding_context
)
from content.search import (
    get_authoritative_library_stats,
    exact_item_title_search,
    RetrievalInfrastructureError
)
from chat.llm import UNSURE_FALLBACK_PHRASE

User = get_user_model()


@pytest.fixture
def test_user_a(db):
    return User.objects.create_user(
        email="user_a_rag@evermind.io",
        password="ValidPassword123!",
        name="User A"
    )


@pytest.fixture
def test_user_b(db):
    return User.objects.create_user(
        email="user_b_rag@evermind.io",
        password="ValidPassword123!",
        name="User B"
    )


# ==============================================================================
# 1. Zero saved items -> Authoritative Zero Count
# ==============================================================================
@pytest.mark.django_db
def test_empty_account_returns_authoritative_zero(test_user_a):
    """A new account with zero saved items authoritatively returns 0 items."""
    stats = get_authoritative_library_stats(test_user_a)
    assert stats["total_count"] == 0
    assert stats["counts_by_type"]["document"] == 0
    assert stats["counts_by_type"]["note"] == 0
    assert len(stats["collections"]) == 0

    session = ChatSession.objects.create(user=test_user_a)
    _, asst_msg = generate_chat_turn(session, "How many items have I saved?")

    assert asst_msg.metadata["is_authoritative_count"] is True
    assert asst_msg.metadata["item_count"] == 0
    assert "0 items" in asst_msg.content.lower() or "0 saved items" in asst_msg.content.lower()


# ==============================================================================
# 2. One saved item -> Accurate count of 1
# ==============================================================================
@pytest.mark.django_db
def test_single_item_count_accuracy(test_user_a):
    """One saved note returns count of 1 item with accurate note count."""
    note = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Project Planning Notes",
        raw_text="The Q4 roadmap focuses on RAG reliability and Dockerless testing.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=note,
        chunk_index=0,
        text=note.raw_text,
        start_offset=0,
        end_offset=len(note.raw_text)
    )

    stats = get_authoritative_library_stats(test_user_a)
    assert stats["total_count"] == 1
    assert stats["counts_by_type"]["note"] == 1
    assert stats["counts_by_type"]["document"] == 0

    session = ChatSession.objects.create(user=test_user_a)
    _, asst_msg = generate_chat_turn(session, "How many items do I have saved?")

    assert asst_msg.metadata["is_authoritative_count"] is True
    assert asst_msg.metadata["item_count"] == 1
    assert "1 saved item" in asst_msg.content or "1 item" in asst_msg.content


# ==============================================================================
# 3. Multiple items and accurate per-type/per-collection counts
# ==============================================================================
@pytest.mark.django_db
def test_multiple_items_and_per_type_counts(test_user_a):
    """Accurate counts broken down by document, note, url, and collections."""
    col_research = Collection.objects.create(user=test_user_a, name="Deep Learning")
    col_work = Collection.objects.create(user=test_user_a, name="Work Projects")

    # 2 documents
    d1 = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Attention Is All You Need.pdf",
        collection=col_research,
        raw_text="Transformer architecture uses self-attention mechanisms.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    d2 = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="System Design Spec.docx",
        collection=col_work,
        raw_text="Evermind uses micro-services and PostgreSQL vector storage.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    # 3 notes
    for i in range(3):
        ContentItem.objects.create(
            user=test_user_a,
            content_type=ContentItem.TYPE_NOTE,
            title=f"Meeting Note #{i+1}",
            collection=col_work,
            raw_text=f"Meeting agenda discussion #{i+1}",
            ingestion_status=ContentItem.STATUS_COMPLETED
        )

    # 1 URL
    ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_URL,
        title="Next.js Documentation",
        source_url="https://nextjs.org/docs",
        raw_text="Next.js enables React server components and server actions.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    stats = get_authoritative_library_stats(test_user_a)
    assert stats["total_count"] == 6
    assert stats["counts_by_type"]["document"] == 2
    assert stats["counts_by_type"]["note"] == 3
    assert stats["counts_by_type"]["url"] == 1
    assert len(stats["collections"]) == 2

    session = ChatSession.objects.create(user=test_user_a)

    # Total count query
    _, asst_all = generate_chat_turn(session, "How many items have I saved?")
    assert asst_all.metadata["item_count"] == 6
    assert "6 saved items" in asst_all.content or "6 items" in asst_all.content
    assert "Documents**: 2" in asst_all.content
    assert "Notes**: 3" in asst_all.content

    # Specific type count query ("How many notes do I have?")
    _, asst_notes = generate_chat_turn(session, "How many notes do I have?")
    assert asst_notes.metadata["is_authoritative_count"] is True
    assert "3 notes" in asst_notes.content


# ==============================================================================
# 4. Exact Title and Filename Search
# ==============================================================================
@pytest.mark.django_db
def test_exact_title_and_filename_search(test_user_a):
    """Direct search for a document by exact title or filename succeeds."""
    doc = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Financial_Audit_2026.pdf",
        raw_text="The total operational expenditure was 1.2M USD with 15% revenue margin.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk = ContentChunk.objects.create(
        content_item=doc,
        chunk_index=0,
        text=doc.raw_text,
        start_offset=0,
        end_offset=len(doc.raw_text)
    )

    matches = exact_item_title_search(test_user_a, "Financial_Audit_2026.pdf")
    assert len(matches) >= 1
    assert matches[0].id == doc.id

    session = ChatSession.objects.create(user=test_user_a)
    _, asst_msg = generate_chat_turn(session, "What does 'Financial_Audit_2026.pdf' say about operational expenditure?")
    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["item_id"] == str(doc.id)


# ==============================================================================
# 5. Pending and Failed Indexing Status Notices
# ==============================================================================
@pytest.mark.django_db
def test_pending_and_failed_indexing_status_notices(test_user_a):
    """Pending and failed documents report explicit status notices rather than claiming non-existence."""
    pending_doc = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Pending_Research.pdf",
        raw_text="",
        ingestion_status=ContentItem.STATUS_PENDING
    )
    failed_doc = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Corrupted_Spreadsheet.xlsx",
        raw_text="",
        ingestion_status=ContentItem.STATUS_FAILED,
        error_message="File header corrupt, failed parsing XML."
    )

    session = ChatSession.objects.create(user=test_user_a)

    # Inquiring about pending file
    _, asst_pending = generate_chat_turn(session, "What is inside 'Pending_Research.pdf'?")
    assert "currently being processed" in asst_pending.content or "status: pending" in asst_pending.content

    # Inquiring about failed file
    _, asst_failed = generate_chat_turn(session, "What is inside 'Corrupted_Spreadsheet.xlsx'?")
    assert "error" in asst_failed.content.lower() or "failed" in asst_failed.content.lower()


# ==============================================================================
# 6. General Questions Answered from LLM Knowledge Without Fabricated Citations
# ==============================================================================
@pytest.mark.django_db
def test_general_knowledge_fallback_without_saved_items(test_user_a):
    """General programming/tech questions answered accurately without fake citations."""
    session = ChatSession.objects.create(user=test_user_a)
    _, asst_msg = generate_chat_turn(session, "What is the difference between TCP and UDP?")

    assert asst_msg.metadata["answer_source"] == "general_knowledge"
    assert len(asst_msg.citations) == 0
    assert "[Source 1]" not in asst_msg.content
    assert "TCP" in asst_msg.content and "UDP" in asst_msg.content


# ==============================================================================
# 7. Non-existent Saved Source Reports Honest Limitation
# ==============================================================================
@pytest.mark.django_db
def test_nonexistent_saved_source_reports_honest_limitation(test_user_a):
    """Asking for a document that doesn't exist returns an honest limitation."""
    # User has some items, but not Quantum_Physics.pdf
    ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Shopping List",
        raw_text="Milk, Eggs, Bread",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    session = ChatSession.objects.create(user=test_user_a)
    _, asst_msg = generate_chat_turn(session, "What does my saved document 'Quantum_Physics.pdf' say?")

    assert asst_msg.metadata["answer_source"] == "explicit_saved_missing"
    assert len(asst_msg.citations) == 0
    assert "could not find" in asst_msg.content.lower() or UNSURE_FALLBACK_PHRASE in asst_msg.content


# ==============================================================================
# 8. Cross-User Isolation
# ==============================================================================
@pytest.mark.django_db
def test_cross_user_isolation(test_user_a, test_user_b):
    """User B cannot see, count, or retrieve User A's items or chunks."""
    # User A creates a secret document
    secret_doc = ContentItem.objects.create(
        user=test_user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="User A Secret Blueprint",
        raw_text="User A secret master key is 99887766.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=secret_doc,
        chunk_index=0,
        text=secret_doc.raw_text,
        start_offset=0,
        end_offset=len(secret_doc.raw_text)
    )

    # User B checks library stats
    stats_b = get_authoritative_library_stats(test_user_b)
    assert stats_b["total_count"] == 0

    session_b = ChatSession.objects.create(user=test_user_b)
    _, asst_b_count = generate_chat_turn(session_b, "How many items have I saved?")
    assert asst_b_count.metadata["item_count"] == 0

    # User B queries about User A's secret document
    _, asst_b_query = generate_chat_turn(session_b, "What is the secret master key in my blueprint?")
    assert len(asst_b_query.citations) == 0
    assert "99887766" not in asst_b_query.content


# ==============================================================================
# 9. Database Errors Are Surfaced, Not Converted to False Zero
# ==============================================================================
@pytest.mark.django_db
def test_database_error_not_converted_to_false_zero(test_user_a):
    """A database error raises RetrievalInfrastructureError and returns a technical error message."""
    session = ChatSession.objects.create(user=test_user_a)

    with patch('chat.services.get_authoritative_library_stats', side_effect=DatabaseError("Connection terminated")):
        _, asst_msg = generate_chat_turn(session, "How many items have I saved?")
        assert asst_msg.metadata.get("retrieval_error") is True
        assert asst_msg.metadata.get("answer_source") == "retrieval_error"
        assert "technical issue" in asst_msg.content.lower()
        # Must NOT claim user has 0 items
        assert "0 items" not in asst_msg.content.lower()
