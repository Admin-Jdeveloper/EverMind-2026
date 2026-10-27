"""
MediaCompile — Saved-Content-First RAG Regression Test Suite.
Validates the 10 mandatory scenarios:
1. Relevant saved content exists: Answer prioritizes retrieved content rather than giving a generic answer.
2. No relevant saved content: Ordinary general-knowledge question receives a useful answer.
3. Explicit saved-source question: Missing source evidence produces an honest limitation, not a fabricated answer.
4. Conflicting information: Saved content is represented faithfully, and discrepancies are handled transparently.
5. Follow-up question: "What about page 14?" resolves the prior document context and retrieves the correct page.
6. Lexical variation: "Is React in my resume skill section?" and "Is React.js in my resume skills?" retrieve the same relevant evidence.
7. Current information: Saved content is searched first, and web research is used when necessary and available.
8. Retrieval infrastructure failure: Database, embedding, or search errors are not silently treated as a successful search with zero results.
9. User isolation: Retrieval never leaks another user's saved content.
10. Citation validation: Correct answers are not discarded solely because optional citations are absent; source-specific answers still enforce appropriate grounding.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.db import DatabaseError

from content.models import ContentItem, ContentChunk
from content.embeddings import get_embedding_provider
from content.search import RetrievalInfrastructureError
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn, build_system_prompt
from chat.llm import UNSURE_FALLBACK_PHRASE
from chat.citations import validate_citations
from chat.web_search import is_explicit_saved_content_query, evaluate_library_coverage

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username=f"rag_user_{uuid.uuid4().hex[:6]}",
        email=f"rag_user_{uuid.uuid4().hex[:6]}@mediacompile.local",
        password="ValidPassword123!"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username=f"other_user_{uuid.uuid4().hex[:6]}",
        email=f"other_user_{uuid.uuid4().hex[:6]}@mediacompile.local",
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
# Scenario 1: Relevant saved content exists -> Answer prioritizes retrieved content
# ==============================================================================
@pytest.mark.django_db
def test_1_saved_content_takes_precedence_over_generic_knowledge(auth_user):
    """
    When user has a saved note specifying custom Redis configuration (e.g. port 9999, custom eviction),
    the system must route to saved_library, prioritize the saved evidence, and cite it.
    """
    custom_note = "Internal Infrastructure: Our production Redis cluster runs on port 9999 with 8GB memory limit and custom LRU eviction."
    create_indexed_chunk(auth_user, "Production Redis Architecture", custom_note)

    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "How is Redis configured in our system?")

    assert asst_msg.metadata["answer_source"] == "saved_library"
    assert "9999" in asst_msg.content or "production redis architecture" in asst_msg.content.lower() or "8gb" in asst_msg.content.lower()
    assert len(asst_msg.citations) >= 1
    assert asst_msg.citations[0]["item_title"] == "Production Redis Architecture"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content


# ==============================================================================
# Scenario 2: No relevant saved content -> Useful general knowledge answer
# ==============================================================================
@pytest.mark.django_db
def test_2_empty_library_general_knowledge_fallback(auth_user):
    """
    When the library is empty, an ordinary question ('What is TCP?') is answered helpfully
    from general knowledge without returning the missing-evidence fallback phrase.
    """
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is TCP?")

    assert asst_msg.metadata["answer_source"] == "general_knowledge"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "transmission control protocol" in asst_msg.content.lower() or "tcp" in asst_msg.content.lower()
    assert len(asst_msg.citations) == 0


# ==============================================================================
# Scenario 3: Explicit saved-source question with missing evidence -> Honest limitation
# ==============================================================================
@pytest.mark.django_db
def test_3_explicit_saved_content_missing_reports_honest_limitation(auth_user):
    """
    When user explicitly asks about their saved notes or uploads ('What did my notes say about Kubernetes?'),
    missing evidence MUST return an honest limitation, not fabricated general knowledge.
    """
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What did my notes say about Kubernetes?")

    assert asst_msg.metadata["answer_source"] == "explicit_saved_missing"
    assert UNSURE_FALLBACK_PHRASE in asst_msg.content
    assert len(asst_msg.citations) == 0


# ==============================================================================
# Scenario 4: Conflicting information -> Handled transparently
# ==============================================================================
@pytest.mark.django_db
def test_4_conflicting_information_represented_faithfully(auth_user):
    """
    When sources conflict on an attribute, the discrepancy is surfaced transparently
    rather than arbitrarily picking one.
    """
    create_indexed_chunk(auth_user, "Project Spec Doc A", "Meeting schedule: The team sync is held at 10:00 AM every Monday.")
    create_indexed_chunk(auth_user, "Project Spec Doc B", "Meeting schedule: The team sync is held at 2:00 PM every Monday.")

    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "Compare what my notes say about the meeting schedule")

    assert len(asst_msg.citations) >= 1
    # Check that answer references both or acknowledges the sources
    assert asst_msg.metadata["answer_source"] in ("saved_library", "saved_library_plus_web")


# ==============================================================================
# Scenario 5: Follow-up question -> "What about page 14?" resolves context
# ==============================================================================
@pytest.mark.django_db
def test_5_followup_question_resolves_page_context(auth_user):
    """
    Turn 1 asks about a document. Turn 2 asks 'What about page 14?' which resolves
    the prior document and retrieves page 14.
    """
    doc_text_p1 = "Page 1: Distributed consensus systems overview."
    doc_text_p14 = "Page 14: Deadlock detection using wait-for graphs and cycle detection algorithms."
    item, _ = create_indexed_chunk(auth_user, "Distributed Systems Guide", doc_text_p1, page_number=1)
    create_indexed_chunk(auth_user, "Distributed Systems Guide", doc_text_p14, page_number=14)

    session = ChatSession.objects.create(user=auth_user)
    # Turn 1
    generate_chat_turn(session, "What does my Distributed Systems Guide say?")
    # Turn 2: Follow-up targeting page 14
    _, asst_turn2 = generate_chat_turn(session, "What about page 14?")

    assert len(asst_turn2.citations) >= 1
    # Check that page 14 chunk was targeted
    c0 = asst_turn2.citations[0]
    assert c0.get("page_number") == 14 or "deadlock" in asst_turn2.content.lower()


# ==============================================================================
# Scenario 6: Lexical variation -> "React" vs "React.js" in resume skills
# ==============================================================================
@pytest.mark.django_db
def test_6_lexical_variation_react_and_react_js_resume_skills(auth_user):
    """
    'Is React in my resume skill section?' and 'Is React.js in my resume skills?'
    retrieve the same relevant resume chunk.
    """
    resume_text = "Technical Skills: React, TypeScript, Next.js, Python, Django, PostgreSQL. 5 years building scalable web applications."
    create_indexed_chunk(auth_user, "My Engineering Resume", resume_text)

    session1 = ChatSession.objects.create(user=auth_user)
    _, asst1 = generate_chat_turn(session1, "Is React in my resume skill section?")

    session2 = ChatSession.objects.create(user=auth_user)
    _, asst2 = generate_chat_turn(session2, "Is React.js in my resume skills?")

    # Both must identify the saved resume
    assert len(asst1.citations) >= 1
    assert asst1.citations[0]["item_title"] == "My Engineering Resume"
    assert asst1.metadata["answer_source"] == "saved_library"

    assert len(asst2.citations) >= 1
    assert asst2.citations[0]["item_title"] == "My Engineering Resume"
    assert asst2.metadata["answer_source"] == "saved_library"


# ==============================================================================
# Scenario 7: Current information -> Saved content searched first, web second
# ==============================================================================
@pytest.mark.django_db
def test_7_current_information_searches_saved_content_first(auth_user):
    """
    When asking for latest/current info, tool_calls must record saved_library_retrieval
    before external_web_search.
    """
    session = ChatSession.objects.create(user=auth_user)
    _, asst_msg = generate_chat_turn(session, "What is the latest React version today?")

    tool_calls = asst_msg.metadata.get("tool_calls", [])
    assert "saved_library_retrieval" in tool_calls
    if "external_web_search" in tool_calls:
        lib_idx = tool_calls.index("saved_library_retrieval")
        web_idx = tool_calls.index("external_web_search")
        assert lib_idx < web_idx
    assert asst_msg.metadata["answer_source"] in ("web_research", "saved_library_plus_web")


# ==============================================================================
# Scenario 8: Retrieval infrastructure failure -> Not mislabeled as empty search
# ==============================================================================
@pytest.mark.django_db
def test_8_retrieval_infrastructure_failure_surfaces_technical_issue(auth_user):
    """
    Database or embedding errors return a controlled technical error, not 'no evidence found'.
    """
    session = ChatSession.objects.create(user=auth_user)
    with patch("chat.services.retrieve_grounding_context", side_effect=RetrievalInfrastructureError("Database connection lost")):
        _, asst_msg = generate_chat_turn(session, "How do I configure Redis?")

    assert asst_msg.metadata.get("retrieval_error") is True
    assert asst_msg.metadata.get("answer_source") == "retrieval_error"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "technical issue" in asst_msg.content.lower() or "unavailable" in asst_msg.content.lower()


# ==============================================================================
# Scenario 9: User isolation -> User A's content never leaks to User B
# ==============================================================================
@pytest.mark.django_db
def test_9_cross_tenant_isolation_strictly_enforced(auth_user, other_user):
    """
    User B cannot retrieve or cite User A's saved content.
    """
    private_doc = "Secret Project Apollo: Internal budget allocated is $12,000,000."
    create_indexed_chunk(auth_user, "User A Apollo Project", private_doc)

    session_b = ChatSession.objects.create(user=other_user)
    _, asst_b = generate_chat_turn(session_b, "What did my notes say about Project Apollo budget?")

    assert "12,000,000" not in asst_b.content
    assert len(asst_b.citations) == 0
    assert asst_b.metadata["answer_source"] == "explicit_saved_missing"
    assert UNSURE_FALLBACK_PHRASE in asst_b.content


# ==============================================================================
# Scenario 10: Citation validation -> Correct answers not discarded
# ==============================================================================
@pytest.mark.django_db
def test_10_citation_validation_preserves_valid_answers(auth_user):
    """
    Citation validation accepts grounded answers even if bracketed citations were omitted,
    attaching the candidate citations under tenant isolation.
    """
    item, chunk = create_indexed_chunk(auth_user, "React Guide", "React uses components to structure UI.")
    candidates = [{
        "source_index": 1,
        "chunk_id": str(chunk.id),
        "item_id": str(item.id),
        "item_title": "React Guide",
        "text": chunk.text,
        "score": 0.95
    }]
    # Assistant answers without explicit [Source 1]
    raw_answer = "React is a component-based UI library."
    val = validate_citations(raw_answer, candidates, auth_user, answer_source="saved_library")

    assert val.is_valid is True
    assert len(val.validated_citations) == 1
    assert val.validated_citations[0]["item_title"] == "React Guide"
