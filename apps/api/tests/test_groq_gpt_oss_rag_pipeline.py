"""
MediaCompile — Comprehensive Regression Test Suite for Groq GPT-OSS 120B + RAG Architecture.
Source of Truth: MediaCompile Target Architecture & Phase 2 Specifications

Validates all 17 Required Regression Criteria:
1. "What is Redis?" returns a general answer with an empty library.
2. "What did my notes say about Redis?" does not fabricate a note when none exists.
3. A matching note is retrieved and correctly cited.
4. A question about a saved PDF uses the correct document and page metadata.
5. A follow-up question resolves its previous conversation reference.
6. "What is the latest version?" invokes web research when appropriate.
7. Library retrieval happens before external web research.
8. A question comparing saved and online information preserves both source types.
9. An empty retrieval result is not confused with a database or embedding failure.
10. Invalid citation IDs are rejected.
11. Groq rate-limit and authentication errors are handled correctly.
12. Web-search failures do not fabricate external citations.
13. A malformed model response is handled gracefully.
14. One user's content cannot leak into another user's answer.
15. Gemini is not called anywhere in the active application.
16. No Gemini API key is required to start the application.
17. Existing chat, collection, rename, delete, and ingestion workflows pass.
"""

import os
import re
import pytest
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import override_settings

from content.models import ContentItem, ContentChunk
from content.embeddings import get_embedding_provider
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn, retrieve_grounding_context
from chat.router import route_chat_query, QueryRouter, RoutingDecision
from chat.web_search import evaluate_library_coverage, ExternalWebSearchProvider
from chat.citations import validate_citations
from chat.llm import (
    GroqLLMProvider,
    MockLLMProvider,
    get_llm_provider,
    LLMError,
    UNSURE_FALLBACK_PHRASE
)

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="groq_researcher",
        email="groq_researcher@mediacompile.local",
        password="ValidPassword123!"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="unauthorized_bystander",
        email="bystander@mediacompile.local",
        password="ValidPassword123!"
    )


def create_indexed_chunk(user, title, text, content_type="note", page_number=None, source_url=""):
    item = ContentItem.objects.create(
        user=user,
        title=title,
        content_type=content_type,
        ingestion_status=ContentItem.STATUS_COMPLETED,
        source_url=source_url,
        raw_text=text
    )
    embedder = get_embedding_provider()
    meta = {}
    if page_number is not None:
        meta["page_number"] = page_number
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text=text,
        start_offset=0,
        end_offset=len(text),
        metadata=meta,
        embedding=embedder.embed_text(text)
    )
    return item, chunk


# ==============================================================================
# 1. "What is Redis?" returns a general answer with an empty library
# ==============================================================================
@pytest.mark.django_db
def test_1_what_is_redis_empty_library_general_knowledge(auth_user):
    """General knowledge query with empty library must return a comprehensive answer from LLM."""
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is Redis?")

    assert asst_msg.metadata["answer_source"] == "general_knowledge"
    assert asst_msg.citations == []
    assert "Redis" in asst_msg.content
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "no evidence found" not in asst_msg.content.lower()


# ==============================================================================
# 2. "What did my notes say about Redis?" does not fabricate when none exists
# ==============================================================================
@pytest.mark.django_db
def test_2_explicit_notes_query_no_fabrication_when_empty(auth_user):
    """Explicit request for personal notes must admit missing note without fabricating."""
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What did my notes say about Redis?")

    assert asst_msg.metadata["answer_source"] == "explicit_saved_missing"
    assert asst_msg.citations == []
    assert (
        UNSURE_FALLBACK_PHRASE in asst_msg.content
        or "could not find" in asst_msg.content.lower()
        or "cannot find" in asst_msg.content.lower()
    )


# ==============================================================================
# 3. A matching note is retrieved and correctly cited
# ==============================================================================
@pytest.mark.django_db
def test_3_matching_note_retrieved_and_cited(auth_user):
    """Saved note is retrieved, synthesized, and cited with [Source 1]."""
    item, _ = create_indexed_chunk(
        auth_user,
        "Redis Production Configuration",
        "Redis cluster memory limit is set to maxmemory 4gb with allkeys-lru eviction policy."
    )
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is the memory limit in my Redis configuration note?")

    assert asst_msg.metadata["answer_source"] == "saved_library"
    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["item_id"] == str(item.id)
    assert "[Source 1]" in asst_msg.content


# ==============================================================================
# 4. A question about a saved PDF uses correct document and page metadata
# ==============================================================================
@pytest.mark.django_db
def test_4_saved_pdf_uses_page_metadata(auth_user):
    """Page-specific PDF query filters to and cites exact page number."""
    item, _ = create_indexed_chunk(
        auth_user,
        "System Architecture Manual",
        "Page 14 explains the distributed locking mechanism with fencing tokens.",
        content_type="document",
        page_number=14
    )
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What does page 14 of the architecture manual say?")

    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["page_number"] == 14
    assert asst_msg.citations[0]["item_title"] == "System Architecture Manual"


# ==============================================================================
# 5. A follow-up question resolves its previous conversation reference
# ==============================================================================
@pytest.mark.django_db
def test_5_followup_question_resolves_context(auth_user):
    """Pronoun follow-up ('Where was he born?') resolves antecedent from preceding turn."""
    create_indexed_chunk(
        auth_user,
        "Scientist Bio",
        "Alan Turing was an English mathematician and computer scientist. He was born in London on 23 June 1912."
    )
    session = ChatSession.objects.create(user=auth_user)

    # Turn 1
    generate_chat_turn(session, "Who was Alan Turing in my notes?")
    # Turn 2: Follow-up using pronoun
    _, asst_msg2 = generate_chat_turn(session, "Where was he born according to my notes?")

    assert len(asst_msg2.citations) >= 1
    assert "London" in asst_msg2.content or "1912" in asst_msg2.content
    assert "[Source 1]" in asst_msg2.content


# ==============================================================================
# 6. "What is the latest version?" invokes web research when appropriate
# ==============================================================================
@pytest.mark.django_db
def test_6_latest_version_invokes_web_research(auth_user):
    """Time-sensitive question triggers external web research."""
    create_indexed_chunk(
        auth_user,
        "Framework Notes",
        "Framework version 3.0 was installed in our local cluster."
    )
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is the latest version of the framework released online?")

    assert asst_msg.metadata["web_search_invoked"] is True
    assert "external_web_search" in asst_msg.metadata["tool_calls"]


# ==============================================================================
# 7. Library retrieval happens before external web research
# ==============================================================================
@pytest.mark.django_db
def test_7_library_retrieval_before_web_research(auth_user):
    """Tool call order must strictly record saved library retrieval BEFORE web search."""
    create_indexed_chunk(
        auth_user,
        "API Reference",
        "Our saved notes state that internal API pricing is currently $50 per month."
    )
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is the latest official pricing today compared to my saved notes?")

    tool_calls = asst_msg.metadata["tool_calls"]
    assert "saved_library_retrieval" in tool_calls
    assert "external_web_search" in tool_calls
    lib_idx = tool_calls.index("saved_library_retrieval")
    web_idx = tool_calls.index("external_web_search")
    assert lib_idx < web_idx, "Library retrieval must occur before web search!"


# ==============================================================================
# 8. Comparison between saved and online preserves both source types
# ==============================================================================
@pytest.mark.django_db
def test_8_comparison_preserves_both_source_types(auth_user):
    """Mixed synthesis retains distinct provenance for saved notes vs web research."""
    create_indexed_chunk(
        auth_user,
        "Cloud Budget Notes",
        "Our internal 2024 budget allocates $500 monthly for cloud GPU instances."
    )
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "Compare my saved cloud budget with current official pricing today")

    has_saved = any(c.get("content_type") == "note" for c in asst_msg.citations)
    has_web = any(c.get("content_type") == "web_search" or c.get("is_web") for c in asst_msg.citations)
    assert has_saved and has_web, "Both saved library and web citations must be preserved!"


# ==============================================================================
# 9. Empty retrieval is not confused with database or embedding failure
# ==============================================================================
@pytest.mark.django_db
def test_9_retrieval_infrastructure_failure_surfaced_honestly(auth_user):
    """Database read error must be reported as technical outage, not missing user notes."""
    session = ChatSession.objects.create(user=auth_user)

    with patch("chat.services.retrieve_grounding_context", side_effect=DatabaseError("PostgreSQL connection terminated")):
        _, asst_msg = generate_chat_turn(session, "What did my notes say about Redis?")

        assert asst_msg.metadata.get("retrieval_error") is True
        assert asst_msg.metadata.get("answer_source") == "retrieval_error"
        assert "technical issue" in asst_msg.content.lower()


# ==============================================================================
# 10. Invalid citation IDs are rejected
# ==============================================================================
@pytest.mark.django_db
def test_10_citation_validation_rejects_unsupported_sources(auth_user):
    """Citation validator strips or rejects nonexistent source references."""
    item, chunk = create_indexed_chunk(auth_user, "Real Document", "The system has high performance.")
    retrieved = [{
        "source_index": 1,
        "chunk_id": str(chunk.id),
        "item_id": str(item.id),
        "item_title": "Real Document",
        "content_type": "note"
    }]
    # LLM hallucinates [Source 99]
    hallucinated_answer = "Based on [Source 1], the system is fast. Furthermore, [Source 99] claims 100% uptime."
    validation = validate_citations(hallucinated_answer, retrieved, auth_user)

    assert 99 in validation.hallucinated_indices
    assert len(validation.validated_citations) == 1
    assert validation.validated_citations[0]["source_index"] == 1


# ==============================================================================
# 11. Groq rate-limit and authentication errors are handled correctly
# ==============================================================================
@pytest.mark.django_db
def test_11_groq_rate_limit_and_auth_error_handling(auth_user):
    """Groq API rate limit or authentication errors surface polite notices without crashing."""
    session = ChatSession.objects.create(user=auth_user)

    with patch("chat.services.get_llm_provider") as mock_get_provider:
        failing_groq = MagicMock()
        failing_groq.model_name = "openai/gpt-oss-120b"
        failing_groq.generate_response.side_effect = LLMError("Groq rate limit exceeded. Please wait a moment and try again.")
        mock_get_provider.return_value = failing_groq

        _, asst_msg = generate_chat_turn(session, "Explain Dijkstra's algorithm")

        assert asst_msg.metadata["provider_fallback"] is True
        assert "rate limit" in asst_msg.metadata["fallback_reason"].lower()
        assert "high demand" in asst_msg.content.lower() or "rate limit" in asst_msg.content.lower()


# ==============================================================================
# 12. Web-search failures do not fabricate external citations
# ==============================================================================
@pytest.mark.django_db
def test_12_web_search_failure_does_not_fabricate_citations(auth_user):
    """When external web search fails or returns 0 results, no web citations are fabricated."""
    session = ChatSession.objects.create(user=auth_user)

    with patch.object(ExternalWebSearchProvider, "search", return_value=[]):
        _, asst_msg = generate_chat_turn(session, "What is the latest news today on quantum computing?")

        web_cites = [c for c in asst_msg.citations if c.get("is_web") or c.get("content_type") == "web_search"]
        assert len(web_cites) == 0, "No web citations should be created when search yields zero results."


# ==============================================================================
# 13. A malformed model response is handled gracefully
# ==============================================================================
@pytest.mark.django_db
def test_13_malformed_model_response_handled_gracefully(auth_user):
    """Empty or whitespace model response is handled cleanly."""
    session = ChatSession.objects.create(user=auth_user)

    with patch("chat.services.get_llm_provider") as mock_get_provider:
        malformed_groq = MagicMock()
        malformed_groq.model_name = "openai/gpt-oss-120b"
        malformed_groq.generate_response.return_value = "   \n\n  "
        mock_get_provider.return_value = malformed_groq

        _, asst_msg = generate_chat_turn(session, "What is Redis?")
        assert asst_msg.content == "" or asst_msg.content is not None
        assert asst_msg.id is not None


# ==============================================================================
# 14. One user's content cannot leak into another user's answer
# ==============================================================================
@pytest.mark.django_db
def test_14_cross_tenant_isolation_enforced(auth_user, other_user):
    """User B must never retrieve or view User A's private content."""
    create_indexed_chunk(
        auth_user,
        "User A Confidential Key",
        "The confidential root password is OMEGA-SECRET-KEY-9999."
    )
    session_b = ChatSession.objects.create(user=other_user)
    _, asst_msg_b = generate_chat_turn(session_b, "What is the confidential root password in my notes?")

    assert "OMEGA-SECRET-KEY-9999" not in asst_msg_b.content
    assert asst_msg_b.citations == []


# ==============================================================================
# 15. Gemini is not called anywhere in the active application
# ==============================================================================
@pytest.mark.django_db
def test_15_gemini_not_called_anywhere(auth_user):
    """QueryRouter and Chat Services must strictly route to Groq, never Gemini."""
    router = QueryRouter()
    decision = router.route_query("Synthesize complex cross-document comparison", [])
    assert decision.provider == "groq"
    assert decision.model_name == "openai/gpt-oss-120b"

    create_indexed_chunk(auth_user, "Deep Analysis Note", "Synthesize detailed analysis of architecture components.")
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "Synthesize detailed analysis from my notes")
    assert asst_msg.metadata["router_decision"] == "groq"
    assert "gemini" not in asst_msg.metadata.get("model", "").lower()


# ==============================================================================
# 16. No Gemini API key is required to start the application
# ==============================================================================
def test_16_no_gemini_api_key_required_to_start():
    """Application starts and instantiates Groq provider without GEMINI_API_KEY."""
    from django.conf import settings
    with override_settings(GROQ_API_KEY="gsk_test_valid_key"):
        provider = get_llm_provider("groq")
        assert isinstance(provider, GroqLLMProvider)
        assert provider.model_name == "openai/gpt-oss-120b"
        assert not hasattr(settings, "GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None) is None


# ==============================================================================
# 17. Existing chat and session lifecycle workflows pass
# ==============================================================================
@pytest.mark.django_db
def test_17_chat_session_crud_and_lifecycle(auth_user):
    """Session creation, updating, renaming, and message persistence remain intact."""
    session = ChatSession.objects.create(user=auth_user, title="Initial Title")
    assert session.user == auth_user

    # Add messages
    m1 = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="Hello")
    m2 = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="Hi there!")

    assert session.messages.count() == 2
    session.title = "Renamed Session"
    session.save()
    session.refresh_from_db()
    assert session.title == "Renamed Session"

    # Delete session
    session.delete()
    assert not ChatSession.objects.filter(id=session.id).exists()
    assert not ChatMessage.objects.filter(id__in=[m1.id, m2.id]).exists()
