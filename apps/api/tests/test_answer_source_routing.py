"""
MediaCompile — Comprehensive Regression Tests for Answer-Source Routing & RAG Failure Fixes.
Source of Truth: Section 5 (Regression Tests 1-10)

Tests:
1. "What is Redis?" with an empty library — must produce a useful general answer.
2. "What did my notes say about Redis?" with no matching note — must not fabricate a note.
3. A Redis note exists — the chatbot retrieves and cites it.
4. "Latest Redis version?" — library retrieval occurs before web search.
5. A follow-up question references a previously discussed document.
6. A page-specific question retrieves the correct page when page metadata exists.
7. Database or embedding failure is not reported as an ordinary empty search.
8. Groq/API rate-limit and error failure is handled gracefully.
9. Citation validation rejects unsupported source references.
10. User A's saved content is never returned to User B.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.db import DatabaseError

from content.models import ContentItem, ContentChunk
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn
from chat.llm import UNSURE_FALLBACK_PHRASE, MockLLMProvider
from chat.citations import validate_citations
from content.search import RetrievalInfrastructureError
from content.embeddings import EmbeddingError

User = get_user_model()


@pytest.fixture
def auth_user():
    return User.objects.create_user(
        email=f"tester_{uuid.uuid4().hex[:6]}@example.com",
        password="TestPassword123!"
    )


@pytest.fixture
def other_user():
    return User.objects.create_user(
        email=f"other_{uuid.uuid4().hex[:6]}@example.com",
        password="TestPassword123!"
    )


def create_indexed_chunk(user, title, text, page_number=None):
    from content.embeddings import get_embedding_provider
    provider = get_embedding_provider()
    item = ContentItem.objects.create(
        user=user,
        title=title,
        content_type=ContentItem.TYPE_NOTE,
        raw_text=text,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    meta = {}
    if page_number is not None:
        meta["page_number"] = page_number
    emb = provider.embed_text(text)
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text=text,
        start_offset=0,
        end_offset=len(text),
        metadata=meta,
        embedding=emb
    )
    return item, chunk



# ==============================================================================
# Scenario 1: "What is Redis?" with an empty library — must produce a useful general answer.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_1_general_question_empty_library(auth_user):
    """General knowledge question with 0 chunks must return factual LLM answer, not fallback phrase."""
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is Redis?")

    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "redis" in asst_msg.content.lower()
    assert "data structure store" in asst_msg.content.lower() or "cache" in asst_msg.content.lower() or "in-memory" in asst_msg.content.lower()
    assert asst_msg.metadata["answer_source"] == "general_knowledge"
    assert len(asst_msg.citations) == 0


# ==============================================================================
# Scenario 2: "What did my notes say about Redis?" with no matching note — must not fabricate a note.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_2_explicit_notes_query_no_matching_note(auth_user):
    """Explicit saved content question without matching notes admits uncertainty and must not fabricate citations."""
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What did my notes say about Redis?")

    assert UNSURE_FALLBACK_PHRASE in asst_msg.content
    assert len(asst_msg.citations) == 0
    assert asst_msg.metadata["answer_source"] == "explicit_saved_missing"


# ==============================================================================
# Scenario 3: A Redis note exists — the chatbot retrieves and cites it.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_3_redis_note_exists_retrieves_and_cites(auth_user):
    """When a note discussing Redis exists, chatbot grounds answer on it and includes source citation."""
    note_text = "Redis Configuration: Redis is deployed as an in-memory session cache running on port 6379 with persistence enabled."
    create_indexed_chunk(auth_user, "Redis Setup Notes", note_text)

    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What did my notes say about Redis?")

    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "6379" in asst_msg.content or "redis configuration" in asst_msg.content.lower() or "cache" in asst_msg.content.lower()
    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["item_title"] == "Redis Setup Notes"
    assert asst_msg.metadata["answer_source"] == "saved_library"


# ==============================================================================
# Scenario 4: "Latest Redis version?" — library retrieval occurs before web search.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_4_latest_version_library_first_order(auth_user):
    """Current information questions check saved library retrieval before executing external web research."""
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is the latest Redis version?")

    tool_calls = asst_msg.metadata.get("tool_calls", [])
    assert "saved_library_retrieval" in tool_calls
    # Library retrieval must be executed before web research
    lib_idx = tool_calls.index("saved_library_retrieval")
    if "external_web_search" in tool_calls:
        web_idx = tool_calls.index("external_web_search")
        assert lib_idx < web_idx
    assert asst_msg.metadata["answer_source"] in ("web_research", "saved_library_plus_web")


# ==============================================================================
# Scenario 5: A follow-up question references a previously discussed document.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_5_followup_question_resolves_context(auth_user):
    """Follow-up question ('Explain the second point') inherits previous document context and citations."""
    doc_text = "Distributed Architecture Points: 1. Raft consensus for leader election. 2. MVCC locking for concurrent transactions."
    item, _ = create_indexed_chunk(auth_user, "System Architecture Doc", doc_text)

    session = ChatSession.objects.create(user=auth_user)
    # Turn 1
    generate_chat_turn(session, "What does my document say about distributed architecture?")
    # Turn 2: Follow-up referencing second point
    _, asst_turn2 = generate_chat_turn(session, "Explain the second point in my notes")

    assert "mvcc" in asst_turn2.content.lower() or "locking" in asst_turn2.content.lower() or len(asst_turn2.citations) >= 1
    if asst_turn2.citations:
        assert asst_turn2.citations[0]["item_id"] == str(item.id)


# ==============================================================================
# Scenario 6: A page-specific question retrieves the correct page when metadata exists.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_6_page_specific_retrieval(auth_user):
    """Page locator ('page 14') targets page 14 chunk and cites the page."""
    p14_text = "Page 14: Deadlock detection algorithm with wait-for-graph cycle analysis."
    create_indexed_chunk(auth_user, "Database Engineering Guide", p14_text, page_number=14)

    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What does page 14 in my guide say about deadlock?")

    assert "deadlock" in asst_msg.content.lower()
    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["page_number"] == 14


# ==============================================================================
# Scenario 7: Database or embedding failure is not reported as an ordinary empty search.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_7_retrieval_infrastructure_failure_surfaced_honestly(auth_user):
    """Database or embedding failure returns a controlled technical error, not 'No evidence found'."""
    session = ChatSession.objects.create(user=auth_user)

    with patch("chat.services.retrieve_grounding_context", side_effect=RetrievalInfrastructureError("Postgres connection timeout")):
        _, asst_msg = generate_chat_turn(session, "What did my notes say about Redis?")

    # Must NOT report "I cannot find sufficient evidence in your saved content"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "technical issue" in asst_msg.content.lower() or "service unavailable" in asst_msg.content.lower()
    assert asst_msg.metadata.get("retrieval_error") is True
    assert asst_msg.metadata.get("answer_source") == "retrieval_error"


# ==============================================================================
# Scenario 8: Groq/API failure & rate-limit handling is handled gracefully.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_8_groq_api_failure_fallback_handling(auth_user):
    """Groq provider error gracefully returns user-friendly notice without crashing."""
    from chat.llm import LLMError
    note_text = "Comparison analysis between Redis and Memcached architectures."
    create_indexed_chunk(auth_user, "Cache Comparison", note_text)

    session = ChatSession.objects.create(user=auth_user)

    with patch("chat.services.get_llm_provider") as mock_get_provider:
        failing_groq = MagicMock()
        failing_groq.model_name = "openai/gpt-oss-120b"
        failing_groq.generate_response.side_effect = LLMError("Groq rate limit exceeded. Please wait a moment and try again.")
        mock_get_provider.return_value = failing_groq

        _, asst_msg = generate_chat_turn(session, "Compare Redis and Memcached in my notes")

        assert asst_msg.metadata["provider_fallback"] is True
        assert "rate limit exceeded" in asst_msg.metadata["fallback_reason"].lower()
        assert "high demand" in asst_msg.content.lower() or "rate limit" in asst_msg.content.lower()


# ==============================================================================
# Scenario 9: Citation validation rejects unsupported source references.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_9_citation_validation_rejects_unsupported_sources(auth_user):
    """Unsupported or hallucinated source citations ([Source 99]) are stripped."""
    candidate_citations = [{
        "source_index": 1,
        "chunk_id": str(uuid.uuid4()),
        "item_id": str(uuid.uuid4()),
        "item_title": "Real Source",
        "text": "Real content text",
        "score": 0.9
    }]
    # Assistant hallucinates [Source 99]
    hallucinated_text = "Redis operates in-memory [Source 99]."
    val = validate_citations(hallucinated_text, candidate_citations, auth_user)

    assert 99 in val.hallucinated_indices
    assert len(val.validated_citations) == 0


# ==============================================================================
# Scenario 10: User A's saved content is never returned to User B.
# ==============================================================================
@pytest.mark.django_db
def test_scenario_10_cross_tenant_isolation_enforced(auth_user, other_user):
    """User B asking about User A's saved notes cannot retrieve or cite User A's data."""
    secret_text = "Confidential financial statement: Q3 profit is $4,500,000 for User A."
    create_indexed_chunk(auth_user, "User A Secret Finances", secret_text)

    session_b = ChatSession.objects.create(user=other_user)
    _, asst_msg_b = generate_chat_turn(session_b, "What did my notes say about Q3 profit?")

    # User B must not see User A's content
    assert "4,500,000" not in asst_msg_b.content
    assert len(asst_msg_b.citations) == 0
    assert asst_msg_b.metadata["answer_source"] == "explicit_saved_missing"
    assert UNSURE_FALLBACK_PHRASE in asst_msg_b.content
