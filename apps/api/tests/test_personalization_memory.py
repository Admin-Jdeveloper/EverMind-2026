"""
MediaCompile — Phase 7: Personalization and User-Controlled Memory Test Suite.
Source of Truth: MediaCompile-prompt.md (Section 17: Phase 7 — Personalization and User-Controlled Memory)

Validates:
1. Memory Sovereignty (CRUD): Create, list, edit, toggle active status, and delete memory items.
2. Sensitive Trait Rejection (Safety Guardrails): Prohibits storing health, religion, politics, or financial credentials.
3. Multi-Tenant Isolation: User B cannot inspect, edit, toggle, or delete User A's memory items (returns 404).
4. Personalization Opt-Out: When personalization_enabled=False, memories are excluded from prompts completely.
5. Inactive Memory Filtering: Inactive memories (is_active=False) are never injected into prompts.
6. Deletion Persistence: Permanently deleted memories never appear in subsequent prompts or retrievals.
7. Preferences API: GET and PATCH /api/v1/chat/preferences/ controls personalization toggles.
8. Topic Summaries: GET /api/v1/chat/topics/ synthesizes library topics with verifiable item provenance.
9. Grounded Turn Integration: Active memories shape formatting while preserving grounded document citations.
"""

import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk, Collection
from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference
from chat.memory import (
    validate_memory_safety,
    SensitiveMemoryError,
    get_user_preference,
    get_active_user_memories,
    generate_topic_summaries
)
from chat.services import build_system_prompt, generate_chat_turn

User = get_user_model()

@pytest.fixture
def memory_users(db):
    user_a = User.objects.create_user(
        email="alice.pref@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Preferences"
    )
    user_b = User.objects.create_user(
        email="bob.pref@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Preferences"
    )
    return user_a, user_b

@pytest.fixture
def auth_client_a(memory_users):
    user_a, _ = memory_users
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client

@pytest.fixture
def auth_client_b(memory_users):
    _, user_b = memory_users
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client

# =========================================================================
# 1. Sensitive Trait Rejection Guardrails (AI Safety)
# =========================================================================

def test_sensitive_category_rejected():
    """Verify sensitive categories (health, religion, politics) raise validation errors."""
    with pytest.raises(SensitiveMemoryError) as exc_info:
        validate_memory_safety("User likes organic vegetables", category="health")
    assert "Category 'health' is prohibited" in str(exc_info.value)

    with pytest.raises(SensitiveMemoryError) as exc_info:
        validate_memory_safety("Attends services weekly", category="religion")
    assert "Category 'religion' is prohibited" in str(exc_info.value)

    with pytest.raises(SensitiveMemoryError) as exc_info:
        validate_memory_safety("Active campaign volunteer", category="politics")
    assert "Category 'politics' is prohibited" in str(exc_info.value)

def test_sensitive_text_content_rejected():
    """Verify prohibited terms within memory text raise validation errors."""
    prohibited_samples = [
        "User was diagnosed with cancer in 2024",
        "Practicing devout christianity and attends church",
        "Voted for republican candidates in recent election",
        "Confidential bank account routing number 123456789"
    ]
    for sample in prohibited_samples:
        with pytest.raises(SensitiveMemoryError) as exc_info:
            validate_memory_safety(sample, category="general")
        assert "prohibited sensitive topic" in str(exc_info.value)

def test_safe_content_accepted():
    """Verify standard preferences, styles, and workflows pass validation without error."""
    safe_samples = [
        ("Prefers responses in bulleted markdown format", "style"),
        ("Uses Python 3.14 and Next.js 16 for full-stack engineering", "technical"),
        ("Wants concise answers with big-O algorithmic complexity", "general"),
        ("Working on distributed consensus protocols and vector databases", "technical")
    ]
    for text, category in safe_samples:
        # Should execute cleanly without raising SensitiveMemoryError
        validate_memory_safety(text, category=category)

# =========================================================================
# 2. Memory CRUD REST API & Isolation
# =========================================================================

@pytest.mark.django_db
def test_create_memory_via_api(auth_client_a):
    """Test user can add an explicit memory item via REST endpoint."""
    payload = {
        "memory_text": "Prefers code snippets written in TypeScript with strict typing.",
        "category": "technical",
        "is_explicit": True,
        "is_active": True,
        "provenance": {"source": "User settings"}
    }
    res = auth_client_a.post("/api/v1/chat/memories/", payload, format="json")
    assert res.status_code == 201
    data = res.json()
    assert data["memory_text"] == payload["memory_text"]
    assert data["category"] == "technical"
    assert data["is_active"] is True
    assert data["is_explicit"] is True

@pytest.mark.django_db
def test_sensitive_memory_rejected_via_api(auth_client_a):
    """Test REST API rejects sensitive memory creation with 400 Bad Request."""
    payload = {
        "memory_text": "User was prescribed antibiotics for severe illness.",
        "category": "general"
    }
    res = auth_client_a.post("/api/v1/chat/memories/", payload, format="json")
    assert res.status_code == 400
    data = res.json()
    details = data.get("error", {}).get("details", data)
    assert "memory_text" in details

@pytest.mark.django_db
def test_multi_tenant_memory_isolation(auth_client_a, auth_client_b, memory_users):
    """Verify User B cannot view, edit, toggle, or delete User A's memory."""
    user_a, _ = memory_users
    mem_a = UserMemory.objects.create(
        user=user_a,
        memory_text="Alice's private technical preference.",
        category="technical",
        is_active=True
    )

    # 1. User B lists memories: User A's memory not visible
    res = auth_client_b.get("/api/v1/chat/memories/")
    assert res.status_code == 200
    results = res.json() if isinstance(res.json(), list) else res.json().get("results", [])
    assert all(m["id"] != str(mem_a.id) for m in results)

    # 2. User B tries to retrieve User A's memory directly -> 404
    res = auth_client_b.get(f"/api/v1/chat/memories/{mem_a.id}/")
    assert res.status_code == 404

    # 3. User B tries to toggle User A's memory -> 404
    res = auth_client_b.post(f"/api/v1/chat/memories/{mem_a.id}/toggle/")
    assert res.status_code == 404

    # 4. User B tries to delete User A's memory -> 404
    res = auth_client_b.delete(f"/api/v1/chat/memories/{mem_a.id}/")
    assert res.status_code == 404

    # Confirm User A's memory was not deleted
    assert UserMemory.objects.filter(id=mem_a.id).exists()

@pytest.mark.django_db
def test_toggle_and_delete_memory(auth_client_a, memory_users):
    """Test toggling is_active and deleting a memory."""
    user_a, _ = memory_users
    mem = UserMemory.objects.create(
        user=user_a,
        memory_text="Always explain using analogies.",
        is_active=True
    )

    # Toggle to False
    res = auth_client_a.post(f"/api/v1/chat/memories/{mem.id}/toggle/")
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    mem.refresh_from_db()
    assert mem.is_active is False

    # Delete
    del_res = auth_client_a.delete(f"/api/v1/chat/memories/{mem.id}/")
    assert del_res.status_code == 204
    assert not UserMemory.objects.filter(id=mem.id).exists()

# =========================================================================
# 3. Opt-Out and Prompt Construction Enforcement
# =========================================================================

@pytest.mark.django_db
def test_personalization_opt_out_prompt_behavior(memory_users):
    """Verify that when personalization_enabled=False, memories are excluded from prompt."""
    user_a, _ = memory_users
    UserMemory.objects.create(
        user=user_a,
        memory_text="Always format equations in LaTeX.",
        is_active=True
    )

    pref = get_user_preference(user_a)
    pref.personalization_enabled = True
    pref.save()

    active_mems = get_active_user_memories(user_a)
    assert len(active_mems) == 1
    assert "Always format equations in LaTeX." in active_mems[0]

    prompt = build_system_prompt("Context excerpt", memories=active_mems)
    assert "CONSENTED USER PREFERENCES & MEMORY" in prompt
    assert "Always format equations in LaTeX." in prompt

    # Now disable personalization
    pref.personalization_enabled = False
    pref.save()

    active_mems_disabled = get_active_user_memories(user_a)
    assert active_mems_disabled == []

    prompt_disabled = build_system_prompt("Context excerpt", memories=active_mems_disabled)
    assert "CONSENTED USER PREFERENCES & MEMORY" not in prompt_disabled
    assert "Always format equations in LaTeX." not in prompt_disabled

@pytest.mark.django_db
def test_inactive_and_deleted_memories_excluded(memory_users):
    """Ensure inactive or deleted memories are never included in prompts."""
    user_a, _ = memory_users
    mem1 = UserMemory.objects.create(
        user=user_a,
        memory_text="Active item.",
        is_active=True
    )
    mem2 = UserMemory.objects.create(
        user=user_a,
        memory_text="Disabled item.",
        is_active=False
    )

    mems = get_active_user_memories(user_a)
    assert any("Active item." in m for m in mems)
    assert not any("Disabled item." in m for m in mems)

    # Delete mem1
    mem1.delete()
    mems_after = get_active_user_memories(user_a)
    assert len(mems_after) == 0

# =========================================================================
# 4. Preferences API
# =========================================================================

@pytest.mark.django_db
def test_user_preferences_api(auth_client_a):
    """Test getting and updating user personalization preferences."""
    # 1. GET preferences
    res = auth_client_a.get("/api/v1/chat/preferences/")
    assert res.status_code == 200
    data = res.json()
    assert "personalization_enabled" in data
    assert "allow_inferred_memories" in data

    # 2. PATCH preferences to disable personalization
    patch_res = auth_client_a.patch("/api/v1/chat/preferences/", {
        "personalization_enabled": False,
        "allow_inferred_memories": False
    }, format="json")
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["personalization_enabled"] is False
    assert updated["allow_inferred_memories"] is False

# =========================================================================
# 5. Topic Summaries API & Grounded Provenance
# =========================================================================

@pytest.mark.django_db
def test_topic_summaries_api(auth_client_a, memory_users):
    """Test generating topic summaries derived from saved content with provenance."""
    user_a, _ = memory_users

    col = Collection.objects.create(user=user_a, name="Distributed Systems")
    ContentItem.objects.create(
        user=user_a,
        collection=col,
        title="Raft Protocol Overview",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="Raft consensus algorithm details.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ContentItem.objects.create(
        user=user_a,
        collection=col,
        title="Paxos Made Simple",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="Classic Paxos consensus paper notes.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    res = auth_client_a.get("/api/v1/chat/topics/")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 1
    topics = data["topics"]
    found = next((t for t in topics if t["topic"] == "Distributed Systems"), None)
    assert found is not None
    assert found["item_count"] == 2
    assert len(found["supporting_items"]) == 2
    assert any(item["title"] == "Raft Protocol Overview" for item in found["supporting_items"])

# =========================================================================
# 6. End-to-End Chat Turn with Memory
# =========================================================================

@pytest.mark.django_db
def test_chat_turn_incorporates_memory(memory_users):
    """Verify chat turn executes with personalization active without corrupting grounding."""
    user_a, _ = memory_users
    UserMemory.objects.create(
        user=user_a,
        memory_text="Always provide concise, authoritative technical summaries.",
        is_active=True
    )
    # Saved content
    ContentItem.objects.create(
        user=user_a,
        title="PostgreSQL 16 Performance",
        raw_text="PostgreSQL 16 introduces enhanced query parallelism and reduced buffer lock contention.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )

    session = ChatSession.objects.create(user=user_a, title="PG16 Tuning")
    user_msg, assistant_msg = generate_chat_turn(session, "What does PostgreSQL 16 introduce?")

    assert user_msg.content == "What does PostgreSQL 16 introduce?"
    assert assistant_msg.content is not None
    assert len(assistant_msg.content) > 0
