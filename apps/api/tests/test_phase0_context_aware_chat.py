"""
MediaCompile — Phase 0 Acceptance Test Gate: Context-Aware Chatbot Foundation
Source of Truth: MediaCompile Autonomous RAG Engineering Master Prompt (Phase 0)

Verifies:
1. Direct factual questions.
2. Single-turn follow-ups (anaphora / entity resolution).
3. Multi-turn chains of follow-up questions.
4. References to earlier numbered points ("Explain the second point").
5. References to previous answers ("Expand the previous answer", "Why does it happen?").
6. Page-specific questions ("What does page 14 say?").
7. Ambiguous references (state scope / defensible resolution).
8. Questions involving multiple documents (comparison scope).
9. Questions without sufficient evidence (uncertainty fallback).
10. Missing or unavailable history handling.
11. Persistence and isolation between conversations.
12. Correct citation-to-source mapping.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk
from content.embeddings import get_embedding_provider
from chat.models import ChatSession, ChatMessage
from chat.services import (
    retrieve_grounding_context,
    build_system_prompt,
    generate_chat_turn
)
from chat.query_planner import (
    build_query_plan,
    extract_page_locator,
    extract_numbered_points_from_text,
    extract_salient_entities
)
from chat.llm import UNSURE_FALLBACK_PHRASE

User = get_user_model()


@pytest.fixture
def p0_users(db):
    user_a = User.objects.create_user(
        email="p0.alice@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Phase0"
    )
    user_b = User.objects.create_user(
        email="p0.bob@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Phase0"
    )
    return user_a, user_b


@pytest.fixture
def p0_fixtures(db, p0_users):
    user_a, user_b = p0_users
    provider = get_embedding_provider()

    # Document 1: Multi-page System Architecture Manual (PDF)
    doc_1 = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Distributed Database Internals",
        raw_text="Full text manual of distributed database architecture.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    # Page 3 Chunk: Raft Consensus
    chunk_p3 = ContentChunk.objects.create(
        content_item=doc_1,
        chunk_index=0,
        text="Page 3 explains that Raft consensus uses randomized election timeouts between 150ms and 300ms to elect a stable leader.",
        start_offset=0,
        end_offset=120,
        metadata={"page_number": 3},
        embedding=provider.embed_text("Raft consensus uses randomized election timeouts between 150ms and 300ms to elect a stable leader.")
    )
    # Page 14 Chunk: MVCC Locking Protocol
    chunk_p14 = ContentChunk.objects.create(
        content_item=doc_1,
        chunk_index=1,
        text="On page 14, the storage engine specifies that MVCC uses optimistic lock-free read transactions with snapshot isolation.",
        start_offset=121,
        end_offset=245,
        metadata={"page_number": 14},
        embedding=provider.embed_text("MVCC uses optimistic lock-free read transactions with snapshot isolation on page 14.")
    )

    # Document 2: Research Note on Paxos
    doc_2 = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Paxos Algorithm Comparative Study",
        raw_text="Multi-Paxos maintains a single master to achieve consensus within two network round trips.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    chunk_paxos = ContentChunk.objects.create(
        content_item=doc_2,
        chunk_index=0,
        text="Multi-Paxos maintains a single master to achieve consensus within two network round trips, whereas Raft simplifies state machine transitions.",
        start_offset=0,
        end_offset=145,
        metadata={"page_number": 1},
        embedding=provider.embed_text("Multi-Paxos maintains a single master to achieve consensus within two network round trips.")
    )

    # User B Knowledge Item (Tenant Isolation)
    doc_b = ContentItem.objects.create(
        user=user_b,
        content_type=ContentItem.TYPE_NOTE,
        title="Bob Secret Blueprint",
        raw_text="Confidential project code is Project-Chimera-77.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=doc_b,
        chunk_index=0,
        text="Confidential project code is Project-Chimera-77.",
        embedding=provider.embed_text("Confidential project code is Project-Chimera-77.")
    )

    return {
        "user_a": user_a,
        "user_b": user_b,
        "doc_1": doc_1,
        "doc_2": doc_2,
        "chunk_p3": chunk_p3,
        "chunk_p14": chunk_p14,
        "chunk_paxos": chunk_paxos,
    }


@pytest.mark.django_db
def test_p0_01_direct_factual_question(p0_fixtures):
    """Criterion 1: Direct factual questions return grounded context and accurate citation metadata."""
    user = p0_fixtures["user_a"]
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="What is the election timeout range in Raft?"
    )

    assert "NO_RELEVANT_CONTENT" != context_str
    assert len(citations) >= 1
    assert any("150ms and 300ms" in c["excerpt"] for c in citations)
    # Verify card locator and page metadata preserved
    first_cite = citations[0]
    assert first_cite["item_title"] == "Distributed Database Internals"
    assert first_cite["page_number"] == 3


@pytest.mark.django_db
def test_p0_02_single_turn_followup(p0_fixtures):
    """Criterion 2: Single-turn follow-up with pronouns resolves entity and retrieves relevant evidence."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Raft Consensus Session")

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_USER,
        content="Tell me about Raft consensus timeouts."
    )
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="Raft uses randomized election timeouts between 150ms and 300ms to avoid split votes."
    )

    # Follow-up with pronoun reference
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="Why does it use randomized values?",
        session=session
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1
    assert any("split votes" in c["excerpt"] or "election timeouts" in c["excerpt"] for c in citations)


@pytest.mark.django_db
def test_p0_03_multi_turn_chains_of_followups(p0_fixtures):
    """Criterion 3: Multi-turn chains maintain coherent entity tracking across multiple questions."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Consensus Exploration")

    # Turn 1
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="Explain Raft consensus.")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="Raft elects a stable leader.")

    # Turn 2
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="What about election timeouts?")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="They are between 150ms and 300ms.")

    # Turn 3: Chain follow-up
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="What happens if that timeout expires?",
        session=session
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1


@pytest.mark.django_db
def test_p0_04_references_to_earlier_numbered_points(p0_fixtures):
    """Criterion 4: User requests 'Explain the second point' -> resolves exact text of point 2 from assistant."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Numbered Points Session")

    assistant_msg = (
        "Here are the two core mechanisms:\n"
        "1. Raft consensus election timeouts: randomized between 150ms and 300ms.\n"
        "2. MVCC snapshot isolation: lock-free read transactions from storage engine."
    )
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="Summarize the core mechanisms.")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_msg)

    # User asks specifically for point 2
    plan = build_query_plan(
        user_query="Explain the second point.",
        session=session
    )

    assert "MVCC snapshot isolation" in plan.standalone_query
    context_str, citations = retrieve_grounding_context(
        user=user,
        question="Explain the second point.",
        session=session
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    # Should retrieve MVCC snapshot isolation (Page 14)
    assert any("MVCC" in c["excerpt"] or c.get("page_number") == 14 for c in citations)


@pytest.mark.django_db
def test_p0_05_references_to_previous_answers(p0_fixtures):
    """Criterion 5: 'Expand the previous answer' resolves to prior topic and retrieves deeper context."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Deep Dive Session")

    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="What is MVCC?")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="MVCC uses optimistic lock-free read transactions.")

    plan = build_query_plan(
        user_query="Expand the previous answer.",
        session=session
    )

    assert "MVCC" in plan.standalone_query or "optimistic" in plan.standalone_query


@pytest.mark.django_db
def test_p0_06_page_specific_questions(p0_fixtures):
    """Criterion 6: 'What does page 14 say?' binds target_page=14 and retrieves page 14 evidence."""
    user = p0_fixtures["user_a"]

    # Verify locator extraction
    pg, clean_q = extract_page_locator("What does page 14 say about locking?")
    assert pg == 14
    assert "locking" in clean_q

    context_str, citations = retrieve_grounding_context(
        user=user,
        question="What does page 14 say about locking?"
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    assert len(citations) >= 1
    # Top citation MUST be page 14
    assert citations[0]["page_number"] == 14
    assert "MVCC" in (citations[0].get("text") or citations[0]["excerpt"])


@pytest.mark.django_db
def test_p0_07_ambiguous_references(p0_fixtures):
    """Criterion 7: Ambiguous queries like 'Why?' or 'What about that?' use prior turn context defensively."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Ambiguity Test")

    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="Tell me about Raft election timeouts.")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="Raft uses timeouts between 150ms and 300ms.")

    plan = build_query_plan(
        user_query="Why?",
        session=session
    )

    # Standalone query should enrich with Raft / timeouts
    assert any(term in plan.standalone_query.lower() for term in ["raft", "election", "timeouts"])


@pytest.mark.django_db
def test_p0_08_questions_involving_multiple_documents(p0_fixtures):
    """Criterion 8: Cross-document comparison queries ('Compare Raft with Paxos') sets comparison scope."""
    user = p0_fixtures["user_a"]

    plan = build_query_plan(
        user_query="Compare Raft with Paxos in my documents."
    )

    assert plan.scope_mode == "comparison"
    assert len(plan.search_queries) >= 2

    context_str, citations = retrieve_grounding_context(
        user=user,
        question="Compare Raft with Paxos in my documents."
    )

    assert context_str != "NO_RELEVANT_CONTENT"
    retrieved_titles = {c["item_title"] for c in citations}
    # Should include both documents
    assert "Distributed Database Internals" in retrieved_titles
    assert "Paxos Algorithm Comparative Study" in retrieved_titles


@pytest.mark.django_db
def test_p0_09_questions_without_sufficient_evidence(p0_fixtures):
    """Criterion 9: Questions with no evidence in the library return uncertainty fallback without hallucinations."""
    user = p0_fixtures["user_a"]
    session = ChatSession.objects.create(user=user, title="Uncertainty Session")

    with patch("chat.services.get_llm_provider") as mock_provider:
        mock_instance = MagicMock()
        mock_instance.model_name = "groq/openai/gpt-oss-120b"
        mock_instance.generate_response.return_value = UNSURE_FALLBACK_PHRASE
        mock_provider.return_value = mock_instance

        user_msg, assistant_msg = generate_chat_turn(
            session=session,
            user_question="What is the internal recipe for Coca-Cola zero?"
        )

        assert UNSURE_FALLBACK_PHRASE in assistant_msg.content
        # Hallucinated citations must NOT be persisted when unsure
        assert len(assistant_msg.citations) == 0


@pytest.mark.django_db
def test_p0_10_missing_or_unavailable_history(p0_fixtures):
    """Criterion 10: Gracefully handles None session, empty history, or truncated message objects."""
    user = p0_fixtures["user_a"]

    # No session
    plan = build_query_plan(user_query="What is Raft consensus?", session=None, history=None)
    assert plan.standalone_query == "What is Raft consensus?"

    # Empty history list
    plan2 = build_query_plan(user_query="What is Raft consensus?", session=None, history=[])
    assert plan2.standalone_query == "What is Raft consensus?"

    # Session with 0 messages
    empty_session = ChatSession.objects.create(user=user, title="Empty Session")
    plan3 = build_query_plan(user_query="What is Raft consensus?", session=empty_session)
    assert plan3.standalone_query == "What is Raft consensus?"


@pytest.mark.django_db
def test_p0_11_persistence_and_isolation_between_conversations(p0_fixtures):
    """Criterion 11: Cross-user and cross-session isolation; User A cannot retrieve User B's content."""
    user_a = p0_fixtures["user_a"]
    user_b = p0_fixtures["user_b"]

    session_a = ChatSession.objects.create(user=user_a, title="Session A")
    session_b = ChatSession.objects.create(user=user_b, title="Session B")

    # User A searches for Bob's secret project
    context_str, citations = retrieve_grounding_context(
        user=user_a,
        question="What is Project-Chimera-77?",
        session=session_a
    )

    # Bob's secret content MUST NEVER appear in Alice's context
    assert "Project-Chimera-77" not in context_str
    assert not any("Chimera" in c["excerpt"] for c in citations)


@pytest.mark.django_db
def test_p0_12_correct_citation_to_source_mapping(p0_fixtures):
    """Criterion 12: Every citation maps to real ContentChunk UUID, ContentItem UUID, page number, and offsets."""
    user = p0_fixtures["user_a"]

    context_str, citations = retrieve_grounding_context(
        user=user,
        question="What does page 14 describe?"
    )

    assert len(citations) >= 1
    top_citation = citations[0]

    # Verify chunk and item existence in database
    chunk = ContentChunk.objects.get(id=top_citation["chunk_id"])
    item = ContentItem.objects.get(id=top_citation["item_id"])

    assert chunk.content_item_id == item.id
    assert top_citation["page_number"] == 14
    assert top_citation["item_title"] == "Distributed Database Internals"
    assert top_citation["start_offset"] == chunk.start_offset
    assert top_citation["end_offset"] == chunk.end_offset
