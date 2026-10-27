"""
MediaCompile — Phase 4: Chatbot and RAG Retrieval Repair Test Suite.
Source of Truth: MediaCompile-prompt.md (Phase 4: Chatbot and RAG Retrieval Repair)

Validates:
1. Distinctive Public Article Test:
   - Ingests a distinctive article on a niche historical/scientific discovery.
   - Verifies the chatbot answers factual questions uniquely contained in the article.
   - Verifies answer attributes the exact saved article with structured citations.
2. Multi-Page / Structural Section Citations:
   - Ingests multi-page / multi-section document with distinct factual assertions per page.
   - Verifies chatbot questions cite the exact matching page_number, section, and item ID.
3. Multi-Turn Context Retention:
   - Turn 1 establishes subject; Turn 2 asks follow-up with pronouns.
   - Verifies session retains multi-turn context and retrieves grounded evidence.
4. Strict Multi-Tenant Isolation:
   - User A and User B cannot retrieve, cross-cite, or query each other's documents or sessions.
5. Resolution of False Uncertainty:
   - When evidence exists, grounded answer is generated with citations (no false uncertainty).
   - When no evidence exists in library, graceful uncertainty fallback is returned.
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from content.models import ContentItem, ContentChunk
from content.embeddings import get_embedding_provider
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn, retrieve_grounding_context
from chat.llm import UNSURE_FALLBACK_PHRASE

User = get_user_model()


@pytest.fixture
def rag_users(db):
    user_a = User.objects.create_user(
        email="alice.rag@mediacompile.io",
        password="SecurePassword2026!",
        name="Alice RAG"
    )
    user_b = User.objects.create_user(
        email="bob.rag@mediacompile.io",
        password="SecurePassword2026!",
        name="Bob RAG"
    )
    return user_a, user_b


@pytest.fixture
def auth_client_a(rag_users):
    client = APIClient()
    client.force_authenticate(user=rag_users[0])
    return client


@pytest.fixture
def auth_client_b(rag_users):
    client = APIClient()
    client.force_authenticate(user=rag_users[1])
    return client


# ------------------------------------------------------------------------------
# 1. Distinctive Public Article Test
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_distinctive_public_article_rag_flow(auth_client_a, rag_users):
    """
    Distinctive Public Article Test:
    1. Save a distinctive public article with niche historical facts.
    2. Ask a factual question uniquely contained in that article.
    3. Verify chatbot answers accurately and cites the saved article.
    """
    user_a = rag_users[0]
    provider = get_embedding_provider()

    article_text = (
        "In 1965, radio astronomers Arno Penzias and Robert Wilson discovered the Cosmic Microwave "
        "Background radiation using the Holmdel Horn Antenna located at Bell Telephone Laboratories "
        "in Holmdel Township, New Jersey. The excess antenna temperature of 3.5 Kelvin was isotropic "
        "and unpolarized, providing foundational empirical evidence for the Big Bang cosmological model. "
        "Penzias and Wilson were awarded the 1978 Nobel Prize in Physics for this landmark discovery."
    )

    # Ingest distinctive article via API
    res_ingest = auth_client_a.post('/api/v1/content/notes/', {
        'title': 'Discovery of Cosmic Microwave Background Radiation',
        'content': article_text,
        'tags': ['astronomy', 'cosmology', 'nobel-prize']
    }, format='json')
    assert res_ingest.status_code == 201
    item_id = res_ingest.json()['id']

    # Create chat session
    res_session = auth_client_a.post('/api/v1/chat/sessions/', {'title': 'Cosmology Inquiries'}, format='json')
    assert res_session.status_code == 201
    session_id = res_session.json()['id']

    # Ask factual question whose answer is uniquely contained in the saved article
    question = "Who discovered the Cosmic Microwave Background radiation in 1965 and at what facility?"
    res_chat = auth_client_a.post(f'/api/v1/chat/sessions/{session_id}/messages/', {
        'content': question
    }, format='json')
    assert res_chat.status_code == 201

    data = res_chat.json()
    assistant_msg = data['assistant_message']

    # Must NOT respond with false uncertainty
    assert UNSURE_FALLBACK_PHRASE not in assistant_msg['content']

    # Must contain key facts and cite source
    content = assistant_msg['content']
    assert "[Source 1]" in content or "Source" in content
    assert "Penzias" in content or "Wilson" in content or "Holmdel" in content

    # Verify structured citations
    citations = assistant_msg['citations']
    assert len(citations) >= 1
    primary_cite = citations[0]
    assert primary_cite['item_id'] == item_id
    assert primary_cite['item_title'] == 'Discovery of Cosmic Microwave Background Radiation'
    assert "Cosmic Microwave Background" in primary_cite['excerpt']


# ------------------------------------------------------------------------------
# 2. Multi-Page Document Page/Section Citations Test
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_multipage_document_specific_page_citations(auth_client_a, rag_users):
    """
    Multi-Page Document Test:
    1. Ingest multi-page document with distinct facts across pages.
    2. Ask question about a specific page's content.
    3. Verify citations reference the correct page number and section.
    """
    user_a = rag_users[0]
    provider = get_embedding_provider()

    doc_text = (
        "[Page 1]\n"
        "Introduction to Operating System Scheduling. Preemptive algorithms include Round Robin and Multi-Level Feedback Queues.\n\n"
        "[Page 2]\n"
        "Memory Management Architecture. Virtual memory utilizes translation lookaside buffers (TLB) to accelerate page address resolution.\n\n"
        "[Page 3]\n"
        "Storage Subsystems and RAID. RAID 6 utilizes dual distributed parity across multiple disk drives to withstand dual-disk simultaneous failure."
    )

    item = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Operating Systems Principles Course",
        raw_text=doc_text,
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    from content.services import chunk_text
    chunks = chunk_text(doc_text, chunk_size=200, chunk_overlap=30)
    for c in chunks:
        meta = c.get('metadata', {})
        meta['embedding_dimension'] = 384
        ContentChunk.objects.create(
            content_item=item,
            chunk_index=c['chunk_index'],
            text=c['text'],
            start_offset=c['start_offset'],
            end_offset=c['end_offset'],
            embedding=provider.embed_text(c['text']),
            metadata=meta
        )

    # Ask about Page 3 topic: RAID 6 dual parity
    session = ChatSession.objects.create(user=user_a, title="OS Coursework")
    res = auth_client_a.post(f'/api/v1/chat/sessions/{session.id}/messages/', {
        'content': "How does RAID 6 withstand simultaneous disk failure?"
    }, format='json')

    assert res.status_code == 201
    assistant_msg = res.json()['assistant_message']
    assert UNSURE_FALLBACK_PHRASE not in assistant_msg['content']

    # Verify citation links to Page 3
    citations = assistant_msg['citations']
    assert len(citations) >= 1
    raid_cite = next((c for c in citations if "RAID" in c.get('excerpt', '')), citations[0])
    assert raid_cite['item_id'] == str(item.id)
    assert raid_cite.get('page_number') == 3


# ------------------------------------------------------------------------------
# 3. Multi-Turn Conversation Retention
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_multiturn_conversation_retention(auth_client_a, rag_users):
    """
    Multi-Turn Test:
    Turn 1: User asks initial question on a saved topic.
    Turn 2: User asks follow-up with pronouns ('How does it work?').
    Verifies session-aware contextual retrieval accurately grounds the follow-up.
    """
    user_a = rag_users[0]
    provider = get_embedding_provider()

    ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Spanner Global Database",
        raw_text=(
            "Google Spanner uses TrueTime API with GPS receivers and atomic clocks to achieve "
            "globally synchronized commit timestamps without centralized timestamp oracles."
        ),
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    # Generate chunks
    item = ContentItem.objects.get(user=user_a, title="Spanner Global Database")
    ContentChunk.objects.create(
        content_item=item,
        chunk_index=0,
        text=item.raw_text,
        start_offset=0,
        end_offset=len(item.raw_text),
        embedding=provider.embed_text(item.raw_text),
        metadata={'char_length': len(item.raw_text), 'embedding_dimension': 384}
    )

    # Session creation
    session = ChatSession.objects.create(user=user_a, title="Spanner Database")

    # Turn 1
    res1 = auth_client_a.post(f'/api/v1/chat/sessions/{session.id}/messages/', {
        'content': "What is Google Spanner?"
    }, format='json')
    assert res1.status_code == 201
    assert UNSURE_FALLBACK_PHRASE not in res1.json()['assistant_message']['content']

    # Turn 2: Follow-up with pronoun ('How does it synchronize timestamps?')
    res2 = auth_client_a.post(f'/api/v1/chat/sessions/{session.id}/messages/', {
        'content': "How does it synchronize timestamps?"
    }, format='json')
    assert res2.status_code == 201
    data2 = res2.json()

    # Must retain multi-turn context and ground response in Spanner TrueTime
    content2 = data2['assistant_message']['content']
    assert UNSURE_FALLBACK_PHRASE not in content2
    assert "TrueTime" in content2 or "atomic" in content2 or "GPS" in content2 or "Source" in content2
    assert len(data2['assistant_message']['citations']) >= 1


# ------------------------------------------------------------------------------
# 4. Strict Multi-Tenant Isolation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_multitenant_chat_isolation(auth_client_a, auth_client_b, rag_users):
    """
    Tenant Isolation Test:
    User A has confidential data.
    User B queries about User A's data.
    Verifies User B NEVER retrieves User A's content and receives honest uncertainty response.
    """
    user_a, user_b = rag_users
    provider = get_embedding_provider()

    # User A private note
    item_a = ContentItem.objects.create(
        user=user_a,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Confidential Patent",
        raw_text="The confidential patent code is PHI-7721-SUPERCONDUCTOR.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentChunk.objects.create(
        content_item=item_a,
        chunk_index=0,
        text=item_a.raw_text,
        start_offset=0,
        end_offset=len(item_a.raw_text),
        embedding=provider.embed_text(item_a.raw_text)
    )

    # User B asks about Alice's secret patent code
    session_b = ChatSession.objects.create(user=user_b, title="Bob Inquiries")
    res_b = auth_client_b.post(f'/api/v1/chat/sessions/{session_b.id}/messages/', {
        'content': "What is the confidential patent code for the superconductor?"
    }, format='json')
    assert res_b.status_code == 201

    data_b = res_b.json()
    assistant_msg_b = data_b['assistant_message']

    # User B must NOT retrieve User A's secret
    assert "PHI-7721" not in assistant_msg_b['content']
    assert UNSURE_FALLBACK_PHRASE in assistant_msg_b['content']
    assert len(assistant_msg_b['citations']) == 0

    # User B cannot access User A's session endpoint (HTTP 404)
    session_a = ChatSession.objects.create(user=user_a, title="Alice Secret Session")
    res_cross = auth_client_b.get(f'/api/v1/chat/sessions/{session_a.id}/')
    assert res_cross.status_code == 404


# ------------------------------------------------------------------------------
# 5. True Uncertainty When Evidence is Absent
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_true_uncertainty_when_evidence_absent(auth_client_a, rag_users):
    """
    Verifies that asking about ungrounded external facts returns the honest
    uncertainty fallback rather than fabricating or hallucinating information.
    """
    user_a = rag_users[0]
    session = ChatSession.objects.create(user=user_a, title="Random Question")

    # Ask about a topic completely absent from user library
    res = auth_client_a.post(f'/api/v1/chat/sessions/{session.id}/messages/', {
        'content': "What is the population of ancient Carthage in 250 BC according to my saved notes?"
    }, format='json')
    assert res.status_code == 201

    data = res.json()
    assert UNSURE_FALLBACK_PHRASE in data['assistant_message']['content']
    assert len(data['assistant_message']['citations']) == 0
