"""
Regression and Evidence Sufficiency Test Suite for MediaCompile RAG AI.
Covers:
1. 'How do I use React.js?' with an empty library returns a useful answer.
2. 'What is Redis?' with an empty library returns a useful answer.
3. 'What did my notes say about React.js?' with no matching note reports missing saved evidence.
4. A saved React.js note is retrieved and cited when present.
5. A current-information question invokes working web research.
6. Browser-search results are processed before the final answer is returned.
7. An API or retrieval infrastructure failure is not mislabeled as missing evidence.
8. Citation validation does not reject general-knowledge answers for lacking library citations.
9. Follow-up questions retain their conversation context.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn
from chat.llm import UNSURE_FALLBACK_PHRASE, MockLLMProvider
from chat.web_search import evaluate_library_coverage, ExternalWebSearchProvider, WebSearchResult
from chat.citations import validate_citations
from content.models import ContentItem, ContentChunk
from content.search import RetrievalInfrastructureError

User = get_user_model()


@pytest.fixture
def test_user(db):
    user, _ = User.objects.get_or_create(
        email="test_evidence_user@example.com",
        defaults={"username": "test_evidence_user"}
    )
    return user


@pytest.fixture
def chat_session(test_user):
    return ChatSession.objects.create(user=test_user, title="Evidence Evaluation Session")


@pytest.mark.django_db
def test_1_how_do_i_use_react_empty_library(chat_session, test_user):
    """
    Scenario 1: 'How do I use React.js?' with an empty library returns a useful answer
    and does NOT return 'I cannot find sufficient evidence in your saved content'.
    """
    user_msg, asst_msg = generate_chat_turn(
        session=chat_session,
        user_question="How do I use React.js?"
    )

    assert asst_msg.metadata.get("answer_source") == "general_knowledge"
    assert asst_msg.metadata.get("library_coverage_case") == "D"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "react" in asst_msg.content.lower()
    assert len(asst_msg.content) > 100
    assert len(asst_msg.citations) == 0


@pytest.mark.django_db
def test_2_what_is_redis_empty_library(chat_session, test_user):
    """
    Scenario 2: 'What is Redis?' with an empty library returns a useful answer
    and does NOT return 'I cannot find sufficient evidence in your saved content'.
    """
    user_msg, asst_msg = generate_chat_turn(
        session=chat_session,
        user_question="What is Redis?"
    )

    assert asst_msg.metadata.get("answer_source") == "general_knowledge"
    assert asst_msg.metadata.get("library_coverage_case") == "D"
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert "redis" in asst_msg.content.lower()
    assert "in-memory" in asst_msg.content.lower() or "database" in asst_msg.content.lower()
    assert len(asst_msg.citations) == 0


@pytest.mark.django_db
def test_3_explicit_saved_notes_missing_reports_missing_evidence(chat_session, test_user):
    """
    Scenario 3: 'What did my notes say about React.js?' with no matching note reports
    missing saved evidence honestly instead of inventing general knowledge.
    """
    user_msg, asst_msg = generate_chat_turn(
        session=chat_session,
        user_question="What did my notes say about React.js?"
    )

    assert asst_msg.metadata.get("answer_source") == "explicit_saved_missing"
    assert UNSURE_FALLBACK_PHRASE in asst_msg.content or "could not find" in asst_msg.content.lower()
    assert len(asst_msg.citations) == 0


@pytest.mark.django_db
def test_4_saved_react_note_retrieved_and_cited_when_present(chat_session, test_user):
    """
    Scenario 4: A saved React.js note is retrieved and cited when present.
    """
    item = ContentItem.objects.create(
        user=test_user,
        title="React.js Architecture Notes",
        content_type=ContentItem.TYPE_NOTE,
        ingestion_status=ContentItem.STATUS_COMPLETED,
        raw_text="React is a declarative component library. Components manage state using hooks like useState."
    )
    chunk = ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text="React is a declarative component library. Components manage state using hooks like useState and render JSX efficiently.",
        start_offset=0,
        end_offset=125
    )

    user_msg, asst_msg = generate_chat_turn(
        session=chat_session,
        user_question="How do I use React.js?"
    )

    assert asst_msg.metadata.get("answer_source") in ("saved_library", "saved_library_plus_web")
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert len(asst_msg.citations) >= 1
    assert any(c.get("item_title") == "React.js Architecture Notes" for c in asst_msg.citations)
    assert "[Source 1]" in asst_msg.content or "React.js Architecture Notes" in asst_msg.content


@pytest.mark.django_db
def test_5_current_information_invokes_web_research(chat_session, test_user):
    """
    Scenario 5: A current-information question invokes working web research and cites external web sources.
    """
    user_msg, asst_msg = generate_chat_turn(
        session=chat_session,
        user_question="What is the latest React.js version?"
    )

    assert asst_msg.metadata.get("web_search_invoked") is True
    assert asst_msg.metadata.get("answer_source") in ("web_research", "saved_library_plus_web")
    assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
    assert len(asst_msg.citations) >= 1
    assert any(c.get("is_web") is True or c.get("content_type") == "web_search" for c in asst_msg.citations)
    assert "[Source 1]" in asst_msg.content or "19.3" in asst_msg.content


@pytest.mark.django_db
def test_6_browser_search_results_processed_before_final_answer(chat_session, test_user):
    """
    Scenario 6: Web search results are processed and formatted before final answer is synthesized.
    """
    mock_results = [
        WebSearchResult(
            title="React 19 Official Documentation",
            url="https://react.dev/releases/19",
            snippet="React 19 brings Actions, Server Components, and asset loading improvements."
        )
    ]
    with patch.object(ExternalWebSearchProvider, "search", return_value=mock_results) as mock_search:
        user_msg, asst_msg = generate_chat_turn(
            session=chat_session,
            user_question="What are the latest features in React 19?"
        )
        assert mock_search.called
        assert asst_msg.metadata.get("web_search_invoked") is True
        assert len(asst_msg.citations) >= 1
        web_cite = [c for c in asst_msg.citations if c.get("is_web")][0]
        assert web_cite["source_url"] == "https://react.dev/releases/19"
        assert web_cite["item_title"] == "React 19 Official Documentation"


@pytest.mark.django_db
def test_7_retrieval_infrastructure_failure_not_mislabeled_as_missing_evidence(chat_session, test_user):
    """
    Scenario 7: An API or retrieval infrastructure failure is not mislabeled as missing evidence.
    """
    with patch("chat.services.retrieve_grounding_context", side_effect=RetrievalInfrastructureError("Database connection timed out")):
        user_msg, asst_msg = generate_chat_turn(
            session=chat_session,
            user_question="How do I use React.js?"
        )

        assert asst_msg.metadata.get("answer_source") == "retrieval_error"
        assert asst_msg.metadata.get("retrieval_error") is True
        assert UNSURE_FALLBACK_PHRASE not in asst_msg.content
        assert "technical issue" in asst_msg.content.lower() or "unavailable" in asst_msg.content.lower()


@pytest.mark.django_db
def test_8_citation_validation_does_not_reject_general_knowledge(test_user):
    """
    Scenario 8: Citation validation does not reject general-knowledge answers for lacking library citations.
    """
    general_answer = (
        "## What is React.js?\n\n"
        "React.js is a front-end JavaScript library for creating declarative, reusable user interfaces."
    )
    validation = validate_citations(
        assistant_text=general_answer,
        candidate_citations=[],
        user=test_user,
        answer_source="general_knowledge"
    )

    assert validation.is_valid is True
    assert validation.citation_precision == 1.0
    assert validation.provenance_valid is True
    assert len(validation.validated_citations) == 0


@pytest.mark.django_db
def test_9_followup_questions_retain_conversation_context(chat_session, test_user):
    """
    Scenario 9: Follow-up questions retain their conversation context and coreference resolution.
    """
    # Turn 1
    u1, a1 = generate_chat_turn(session=chat_session, user_question="What is Redis?")
    assert "redis" in a1.content.lower()

    # Turn 2: Follow-up using anaphora/pronoun 'it'
    u2, a2 = generate_chat_turn(session=chat_session, user_question="How does it handle persistence?")
    assert UNSURE_FALLBACK_PHRASE not in a2.content
    assert a2.metadata.get("answer_source") == "general_knowledge"
    # Ensure session contains all 4 messages in proper chronological order
    all_msgs = list(chat_session.messages.order_by("created_at"))
    assert len(all_msgs) == 4
    assert all_msgs[0].content == "What is Redis?"
    assert all_msgs[2].content == "How does it handle persistence?"
