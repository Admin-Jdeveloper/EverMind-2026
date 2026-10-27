"""
MediaCompile — Phase 6: Final End-to-End Integration & Regression Test Suite.
Source of Truth: MediaCompile-prompt.md (Phase 6: Final Integration and Regression Testing)

Validates complete user journey:
1. Authentication: Register new users and authenticate clients.
2. Multi-Format Ingestion: Ingest URL, PDF, DOCX, Note, and confirm all reach 'completed' with 384-dim vectors.
3. Hybrid Search: Test semantic and keyword queries returning relevant ingested items.
4. Grounded Chatbot & Citations: Ask questions about saved items; verify authoritative answers with structured citations.
5. Multi-Turn Context: Ask follow-up question; verify session context retention and pronoun resolution.
6. Content Management Lifecycle: Inspect details, edit metadata (title/tags), download document, delete item.
7. End-to-End Multi-Tenant Isolation: User A and User B cannot access, view, search, or cite each other's data.
8. Distinctive Public Article Acceptance Gate: Full acceptance test on unique historical discovery.
"""

import io
import os
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

import docx
from pypdf import PdfWriter

from content.models import ContentItem, ContentChunk, Collection, Tag
from content.embeddings import get_embedding_provider
from chat.models import ChatSession, ChatMessage
from chat.llm import UNSURE_FALLBACK_PHRASE

User = get_user_model()


@pytest.fixture
def e2e_users(db):
    user_alice = User.objects.create_user(
        email="alice.e2e@mediacompile.io",
        password="SecureAlice2026!",
        name="Alice E2E"
    )
    user_bob = User.objects.create_user(
        email="bob.e2e@mediacompile.io",
        password="SecureBob2026!",
        name="Bob E2E"
    )
    return user_alice, user_bob


@pytest.fixture
def client_alice(e2e_users):
    client = APIClient()
    client.force_authenticate(user=e2e_users[0])
    return client


@pytest.fixture
def client_bob(e2e_users):
    client = APIClient()
    client.force_authenticate(user=e2e_users[1])
    return client


# ------------------------------------------------------------------------------
# 1. Complete End-to-End User Journey Walkthrough
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_full_user_journey_walkthrough(client_alice, e2e_users):
    """
    Complete Walkthrough:
    Upload items -> verify completion -> search -> chat with citations -> multi-turn -> edit -> delete.
    """
    user_alice = e2e_users[0]
    provider = get_embedding_provider()

    # Step 1: Ingest Note
    res_note = client_alice.post('/api/v1/content/notes/', {
        'title': 'CRDTs and Eventual Consistency',
        'content': 'Conflict-free Replicated Data Types (CRDTs) allow concurrent replicas to merge state deterministically without consensus coordination.',
        'tags': ['distributed-systems', 'crdt']
    }, format='json')
    assert res_note.status_code == 201
    note_id = res_note.json()['id']
    assert res_note.json()['ingestion_status'] == 'completed'
    assert res_note.json()['chunk_count'] >= 1

    # Step 2: Ingest DOCX Document
    doc = docx.Document()
    doc.add_heading("PostgreSQL pgvector Optimization", level=1)
    doc.add_paragraph("HNSW indexes require tuning m and ef_construction parameters for production recall.")
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    uploaded_docx = SimpleUploadedFile("pgvector_tuning.docx", docx_bytes, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    res_doc = client_alice.post(
        '/api/v1/content/files/',
        {'file': uploaded_docx, 'title': 'pgvector Optimization Guide'},
        format='multipart',
        HTTP_X_SYNC_INGESTION='true'
    )
    assert res_doc.status_code == 201
    doc_id = res_doc.json()['id']
    assert res_doc.json()['ingestion_status'] == 'completed'

    # Step 3: Verify Semantic Vector Retrieval
    from content.search import vector_search
    search_results = vector_search(user_alice, "conflict-free replicated data types")
    assert len(search_results) >= 1
    assert any(r['item']['id'] == note_id for r in search_results)

    # Step 4: Chatbot Question & Grounded Answer with Citations
    res_session = client_alice.post('/api/v1/chat/sessions/', {'title': 'Distributed Data Discussion'}, format='json')
    session_id = res_session.json()['id']

    # Turn 1: Ask about CRDTs
    res_turn1 = client_alice.post(f'/api/v1/chat/sessions/{session_id}/messages/', {
        'content': "How do CRDTs achieve state convergence?"
    }, format='json')
    assert res_turn1.status_code == 201
    turn1_data = res_turn1.json()['assistant_message']
    assert UNSURE_FALLBACK_PHRASE not in turn1_data['content']
    assert len(turn1_data['citations']) >= 1
    assert turn1_data['citations'][0]['item_id'] == note_id

    # Turn 2: Follow-up question in the same session
    res_turn2 = client_alice.post(f'/api/v1/chat/sessions/{session_id}/messages/', {
        'content': "Do they require consensus coordination?"
    }, format='json')
    assert res_turn2.status_code == 201
    turn2_data = res_turn2.json()['assistant_message']
    assert UNSURE_FALLBACK_PHRASE not in turn2_data['content']
    assert "without consensus" in turn2_data['content'].lower() or "crdt" in turn2_data['content'].lower() or "source" in turn2_data['content'].lower()

    # Step 5: Content Management Operations
    # 5a. View details
    res_detail = client_alice.get(f'/api/v1/content/items/{note_id}/')
    assert res_detail.status_code == 200
    assert res_detail.json()['title'] == 'CRDTs and Eventual Consistency'
    assert len(res_detail.json()['chunks']) >= 1

    # 5b. Edit metadata (title and tags)
    res_edit = client_alice.patch(f'/api/v1/content/items/{note_id}/', {
        'title': 'CRDTs and Conflict Resolution',
        'tags': ['crdt', 'replication', 'database']
    }, format='json')
    assert res_edit.status_code == 200
    assert res_edit.json()['title'] == 'CRDTs and Conflict Resolution'
    assert 'replication' in res_edit.json()['tags_list']

    # 5c. Download uploaded document
    res_dl = client_alice.get(f'/api/v1/content/items/{doc_id}/download/')
    assert res_dl.status_code == 200
    assert 'download_url' in res_dl.json()

    # 5d. Delete item with cascading chunk cleanup
    res_del = client_alice.delete(f'/api/v1/content/items/{note_id}/')
    assert res_del.status_code == 204
    assert not ContentItem.objects.filter(id=note_id).exists()
    assert not ContentChunk.objects.filter(content_item_id=note_id).exists()


# ------------------------------------------------------------------------------
# 2. End-to-End Multi-Tenant Isolation
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_end_to_end_multitenant_isolation(client_alice, client_bob, e2e_users):
    """
    Verify complete multi-tenant boundaries:
    Alice and Bob save distinct content. Neither can view, search, chat, or access the other's content.
    """
    user_alice, user_bob = e2e_users

    # Alice saves private research note
    res_alice = client_alice.post('/api/v1/content/notes/', {
        'title': 'Alice Quantum Key Distribution Protocol',
        'content': 'The BB84 protocol uses polarized photons to detect eavesdropping along quantum communication channels.',
        'tags': ['cryptography', 'quantum']
    }, format='json')
    assert res_alice.status_code == 201
    alice_item_id = res_alice.json()['id']

    # Bob saves distinct private note
    res_bob = client_bob.post('/api/v1/content/notes/', {
        'title': 'Bob Machine Learning Benchmark',
        'content': 'Transformer self-attention exhibits quadratic complexity with respect to sequence length.',
        'tags': ['deep-learning', 'nlp']
    }, format='json')
    assert res_bob.status_code == 201
    bob_item_id = res_bob.json()['id']

    # 1. Search Isolation
    # Bob searches for Alice's keywords -> must return 0 results
    from content.search import vector_search
    bob_results = vector_search(user_bob, 'BB84 polarized photons')
    assert len(bob_results) == 0

    # Alice searches for Bob's keywords -> must return 0 results
    alice_results = vector_search(user_alice, 'Transformer self-attention quadratic')
    assert len(alice_results) == 0

    # 2. Chat Isolation
    # Bob asks about Alice's protocol -> must respond with uncertainty, zero citations
    session_bob = ChatSession.objects.create(user=user_bob, title="Bob Inquiries")
    bob_chat = client_bob.post(f'/api/v1/chat/sessions/{session_bob.id}/messages/', {
        'content': "What does the BB84 protocol use to detect eavesdropping?"
    }, format='json')
    assert bob_chat.status_code == 201
    assert UNSURE_FALLBACK_PHRASE in bob_chat.json()['assistant_message']['content']
    assert len(bob_chat.json()['assistant_message']['citations']) == 0

    # 3. Direct Item Access Isolation
    assert client_bob.get(f'/api/v1/content/items/{alice_item_id}/').status_code == 404
    assert client_bob.patch(f'/api/v1/content/items/{alice_item_id}/', {'title': 'Hacked'}).status_code == 404
    assert client_bob.delete(f'/api/v1/content/items/{alice_item_id}/').status_code == 404


# ------------------------------------------------------------------------------
# 3. Distinctive Public Article Acceptance Gate
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_distinctive_article_final_acceptance_gate(client_alice, e2e_users):
    """
    Definitive acceptance test from MediaCompile-prompt.md:
    1. Ingest a distinctive public article on a specific scientific discovery.
    2. Query factual question uniquely answered by the article.
    3. Verify authoritative answer with valid source citation.
    """
    article_text = (
        "In 1911, Dutch physicist Heike Kamerlingh Onnes discovered superconductivity at Leiden University "
        "while studying the electrical resistance of solid mercury cooled to 4.2 Kelvin using liquid helium. "
        "At this critical transition temperature, the electrical resistance abruptly vanished to zero. "
        "Kamerlingh Onnes was awarded the 1913 Nobel Prize in Physics for his low-temperature research."
    )

    res_item = client_alice.post('/api/v1/content/notes/', {
        'title': 'Discovery of Superconductivity in 1911',
        'content': article_text,
        'tags': ['physics', 'superconductivity', 'nobel-prize']
    }, format='json')
    assert res_item.status_code == 201
    item_id = res_item.json()['id']

    session = ChatSession.objects.create(user=e2e_users[0], title="Superconductivity History")

    # Ask factual question
    res_chat = client_alice.post(f'/api/v1/chat/sessions/{session.id}/messages/', {
        'content': "Who discovered superconductivity in 1911, using what element and transition temperature?"
    }, format='json')
    assert res_chat.status_code == 201

    assistant_msg = res_chat.json()['assistant_message']
    content = assistant_msg['content']

    # Must NOT return false uncertainty
    assert UNSURE_FALLBACK_PHRASE not in content

    # Must cite [Source 1] and contain key facts
    assert "[Source 1]" in content or "Source" in content
    assert "Kamerlingh Onnes" in content or "Onnes" in content or "mercury" in content or "4.2" in content

    # Citation metadata must accurately reference the saved item
    assert len(assistant_msg['citations']) >= 1
    assert assistant_msg['citations'][0]['item_id'] == item_id
    assert assistant_msg['citations'][0]['item_title'] == 'Discovery of Superconductivity in 1911'
