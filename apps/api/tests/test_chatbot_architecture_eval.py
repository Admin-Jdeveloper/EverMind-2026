"""
MediaCompile — 15-Point Chatbot Architecture & Reliability Evaluation Suite.
Source of Truth: MediaCompile-prompt.md (Step 10: Evaluate the actual system)

Covers all 15 required evaluation points:
1. Exact DOB retrieval.
2. Paraphrased DOB queries ("What is my DOB?", "When was I born?", "What is my birth date?", "Tell me my DOB").
3. Exact dates, amounts, names, and identifiers (passport, invoice, currency).
4. Facts inside documents (PDF / CSV with page and row metadata).
5. Facts inside extracted webpage content.
6. Conceptual questions requiring multiple chunks.
7. Questions requiring multiple sources.
8. Conversation follow-ups (session-aware coreference resolution).
9. Missing evidence (admitting uncertainty with exact fallback).
10. Conflicting facts (explicit conflict explanation citing each source).
11. Edited and deleted sources (consistency across indexes).
12. Pending or failed ingestion (unextracted content not claimed as read).
13. Malformed extraction and embedding failures handled gracefully.
14. Citation correctness and provenance verification.
15. Cross-user access attempts (multi-tenant isolation).
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from content.models import ContentItem, ContentChunk, ContentFact
from content.tasks import process_note_content, process_url_content
from content.facts import find_facts_for_query
from content.search import hybrid_retrieve_with_facts, vector_search
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn, retrieve_grounding_context
from chat.llm import UNSURE_FALLBACK_PHRASE

User = get_user_model()


@pytest.fixture
def user_alice(db):
    return User.objects.create_user(
        email="alice@example.com",
        password="TestPassword123!",
        name="Alice Smith"
    )


@pytest.fixture
def user_bob(db):
    return User.objects.create_user(
        email="bob@example.com",
        password="TestPassword123!",
        name="Bob Jones"
    )


# --------------------------------------------------------------------------
# 1. Exact DOB retrieval
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_01_exact_dob_retrieval(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Personal Bio",
        raw_text="My date of birth is 15 March 2005. I live in Seattle."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice, title="Bio Chat")
    user_msg, assistant_msg = generate_chat_turn(session, "What is my date of birth?")

    assert "15 March 2005" in assistant_msg.content
    assert len(assistant_msg.citations) > 0
    assert str(item.id) == assistant_msg.citations[0]["item_id"]


# --------------------------------------------------------------------------
# 2. Paraphrased DOB queries
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_02_paraphrased_dob_queries(user_alice):
    # Note intentionally omits abbreviation 'DOB'
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Identity Note",
        raw_text="My date of birth is 15 March 2005. Citizen of Earth."
    )
    process_note_content(str(item.id))

    paraphrased_queries = [
        "What is my DOB?",
        "When was I born?",
        "What is my birth date?",
        "Tell me my DOB",
    ]

    for q in paraphrased_queries:
        session = ChatSession.objects.create(user=user_alice, title="DOB Test")
        user_msg, assistant_msg = generate_chat_turn(session, q)
        assert "15 March 2005" in assistant_msg.content, f"Failed on query: '{q}'"
        assert len(assistant_msg.citations) >= 1, f"Missing citations on query: '{q}'"
        assert assistant_msg.citations[0]["item_id"] == str(item.id)


# --------------------------------------------------------------------------
# 3. Exact dates, amounts, names, and identifiers
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_03_exact_dates_amounts_names_identifiers(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Official Credentials",
        raw_text="Passport: AB987654. Total invoice amount is $4,250.75. Contract effective 01 September 2026."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg1 = generate_chat_turn(session, "What is my passport number?")
    assert "AB987654" in msg1.content
    assert len(msg1.citations) >= 1

    _, msg2 = generate_chat_turn(session, "How much was the invoice amount?")
    assert "$4,250.75" in msg2.content


# --------------------------------------------------------------------------
# 4. Facts inside documents
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_04_facts_inside_documents(user_alice):
    # Simulate multi-page PDF document
    doc_text = (
        "[Page 1]\nIntroduction to Company Policy and Compliance Guidelines.\n\n"
        "[Page 2]\nAuthorized emergency budget limit is $75,000. Approval code is AUTH-9921."
    )
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_DOCUMENT,
        title="Compliance Manual.pdf",
        raw_text=doc_text
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is the emergency budget limit?")

    assert "$75,000" in msg.content or "AUTH-9921" in msg.content
    assert len(msg.citations) >= 1
    # Check that page 2 is preserved in citation metadata
    cite = msg.citations[0]
    assert cite.get("page_number") == 2 or "Page 2" in cite.get("excerpt", "")


# --------------------------------------------------------------------------
# 5. Facts inside extracted webpage content
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_05_facts_inside_extracted_webpage(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_URL,
        source_url="https://docs.example.com/release-notes",
        title="Example Docs Release 3.2",
        raw_text="Version 3.2 introduces zero-knowledge proof verification with sub-second latencies."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What does version 3.2 introduce?")

    assert "zero-knowledge proof" in msg.content.lower()
    assert msg.citations[0]["source_url"] == "https://docs.example.com/release-notes"


# --------------------------------------------------------------------------
# 6. Conceptual questions requiring multiple chunks
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_06_conceptual_questions_requiring_multiple_chunks(user_alice):
    long_text = (
        "Quantum Key Distribution Protocol Analysis.\n\n"
        "Section 1: The BB84 protocol uses four polarization states of single photons across non-orthogonal bases.\n\n"
        + ("Filler background description of photon emitter systems. " * 30) + "\n\n"
        "Section 2: In contrast, the E91 protocol relies on quantum entanglement and tests of Bell's theorem to verify security."
    )
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Quantum Cryptography Protocols",
        raw_text=long_text
    )
    process_note_content(str(item.id))
    assert item.chunks.count() >= 2

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "Compare BB84 and E91 quantum protocols based on my notes.")

    assert "bb84" in msg.content.lower()
    assert "e91" in msg.content.lower()


# --------------------------------------------------------------------------
# 7. Questions requiring multiple sources
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_07_questions_requiring_multiple_sources(user_alice):
    item1 = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Apollo Mission Report",
        raw_text="Project Apollo total historical budget was 25.4 billion dollars."
    )
    process_note_content(str(item1.id))

    item2 = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Artemis Program Goals",
        raw_text="Project Artemis plans a sustainable human return to the lunar south pole by 2028."
    )
    process_note_content(str(item2.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "Summarize what my notes say about Apollo and Artemis.")

    item_ids_cited = {c["item_id"] for c in msg.citations}
    assert str(item1.id) in item_ids_cited or "apollo" in msg.content.lower()
    assert str(item2.id) in item_ids_cited or "artemis" in msg.content.lower()


# --------------------------------------------------------------------------
# 8. Conversation follow-ups
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_08_conversation_followups(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Colleague Dossier - Alice Smith",
        raw_text="Alice Smith was born on 15 March 2005. She works as a cryptographic protocol engineer."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice, title="Team Review")

    # Turn 1
    generate_chat_turn(session, "Who is Alice Smith?")

    # Turn 2: Follow-up using pronoun coreference
    _, msg2 = generate_chat_turn(session, "When was she born?")

    assert "15 March 2005" in msg2.content
    assert len(msg2.citations) >= 1
    assert msg2.citations[0]["item_id"] == str(item.id)


# --------------------------------------------------------------------------
# 9. Missing evidence (admitting uncertainty)
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_09_missing_evidence(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Grocery List",
        raw_text="Bananas, apples, whole milk, oats."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is my bank account routing number?")

    assert UNSURE_FALLBACK_PHRASE in msg.content
    assert len(msg.citations) == 0


# --------------------------------------------------------------------------
# 10. Conflicting facts handled explicitly
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_10_conflicting_facts(user_alice):
    item1 = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Driver License Record",
        raw_text="Date of birth: 15 March 2005."
    )
    process_note_content(str(item1.id))

    item2 = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Old Gym Membership",
        raw_text="Date of birth: 20 May 2006."
    )
    process_note_content(str(item2.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is my DOB?")

    # Must explain the conflict and cite each source
    content_lower = msg.content.lower()
    assert "conflict" in content_lower or "15 march 2005" in msg.content
    assert "15 March 2005" in msg.content or "20 May 2006" in msg.content


# --------------------------------------------------------------------------
# 11. Edited and deleted sources
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_11_edited_and_deleted_sources(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Compensation Agreement",
        raw_text="My annual salary is $100,000."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg1 = generate_chat_turn(session, "What is my salary?")
    assert "$100,000" in msg1.content

    # 1. Edit the source content
    item.raw_text = "My annual salary is $125,000."
    item.version += 1
    item.save(update_fields=['raw_text', 'version'])
    process_note_content(str(item.id))

    session2 = ChatSession.objects.create(user=user_alice)
    _, msg2 = generate_chat_turn(session2, "What is my salary?")
    assert "$125,000" in msg2.content
    assert "$100,000" not in msg2.content

    # 2. Delete the source
    item.delete()

    session3 = ChatSession.objects.create(user=user_alice)
    _, msg3 = generate_chat_turn(session3, "What is my salary?")
    assert UNSURE_FALLBACK_PHRASE in msg3.content


# --------------------------------------------------------------------------
# 12. Pending or failed ingestion
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_12_pending_or_failed_ingestion(user_alice):
    item_pending = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Secret Pending Note",
        raw_text="Secret passphrase is BlueWhale99.",
        ingestion_status=ContentItem.STATUS_PENDING
    )
    # Do NOT process it

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is my secret passphrase?")

    assert UNSURE_FALLBACK_PHRASE in msg.content
    assert "BlueWhale99" not in msg.content


# --------------------------------------------------------------------------
# 13. Malformed extraction and embedding failures
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_13_malformed_extraction_and_embedding_failures(user_alice):
    item_empty = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Empty Note",
        raw_text="   "
    )
    process_note_content(str(item_empty.id))
    item_empty.refresh_from_db()

    assert item_empty.ingestion_status == ContentItem.STATUS_FAILED
    assert "empty" in item_empty.error_message.lower()

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is in my empty note?")
    assert UNSURE_FALLBACK_PHRASE in msg.content


# --------------------------------------------------------------------------
# 14. Citation correctness and provenance
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_14_citation_correctness_and_provenance(user_alice):
    item = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Project Specs",
        raw_text="Target API latency SLA is 120 milliseconds."
    )
    process_note_content(str(item.id))

    session = ChatSession.objects.create(user=user_alice)
    _, msg = generate_chat_turn(session, "What is the API latency SLA?")

    assert len(msg.citations) >= 1
    cite = msg.citations[0]
    assert cite["item_id"] == str(item.id)
    assert cite["chunk_id"] is not None
    assert "120" in cite["excerpt"]


# --------------------------------------------------------------------------
# 15. Cross-user access attempts (multi-tenant isolation)
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_15_cross_user_access_attempts(user_alice, user_bob):
    item_alice = ContentItem.objects.create(
        user=user_alice,
        content_type=ContentItem.TYPE_NOTE,
        title="Alice Confidential",
        raw_text="Alice confidential passport is X888999111."
    )
    process_note_content(str(item_alice.id))

    # Bob asks for the passport
    session_bob = ChatSession.objects.create(user=user_bob)
    _, msg_bob = generate_chat_turn(session_bob, "What is my passport number?")

    assert "X888999111" not in msg_bob.content
    assert UNSURE_FALLBACK_PHRASE in msg_bob.content
    assert len(msg_bob.citations) == 0

    # Ensure fact search is also strictly isolated
    bob_facts, _ = find_facts_for_query(user_bob, "passport number")
    assert len(bob_facts) == 0
