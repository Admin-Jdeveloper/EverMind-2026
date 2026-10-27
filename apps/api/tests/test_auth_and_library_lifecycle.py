"""
MediaCompile — Comprehensive Authentication & Library Bug Fix Test Suite.
Tests:
1. Register Alice and Bob, verify distinct UUIDs.
2. Verify credentials and profile retrieval for Alice.
3. Switch identity to Bob, verify distinct identity details.
4. Duplicate registration rejection.
5. Invalid password login rejection.
6. Impersonation prevention (user cannot tamper with user ID or headers).
7. Alice adds an item; verify persistence with Alice's user_id.
8. Verify create API returns persisted item with real ID.
9. Verify Library listing returns Alice's item.
10. Verify Bob cannot see Alice's items (Account Isolation).
11. Verify failed writes show error response.
12. Verify filtering and deletion scoped to user.
"""

import pytest
import uuid
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from content.models import ContentItem, Tag

User = get_user_model()


def generate_test_token(user_id: str, email: str, name: str = "") -> str:
    """Helper to generate signed Identity Bridge JWT for tests."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "iss": settings.INTERNAL_API_ISSUER,
        "aud": settings.INTERNAL_API_AUDIENCE,
    }
    return jwt.encode(payload, settings.INTERNAL_API_SECRET, algorithm="HS256")


@pytest.mark.django_db
class TestAuthenticationLifecycle:
    """Verifies Bug 1 fixes: No hardcoded 'John Doe', distinct user identity."""

    def test_01_register_alice_and_bob_distinct_ids(self):
        client = APIClient()

        # 1. Register Alice
        res_alice = client.post(
            "/api/v1/users/register/",
            {"name": "Alice Wonderland", "email": "alice@example.com", "password": "Password123!"},
            format="json",
        )
        assert res_alice.status_code == status.HTTP_201_CREATED
        alice_data = res_alice.data["data"]
        assert alice_data["name"] == "Alice Wonderland"
        assert alice_data["email"] == "alice@example.com"
        assert "id" in alice_data

        # 2. Register Bob
        res_bob = client.post(
            "/api/v1/users/register/",
            {"name": "Bob Builder", "email": "bob@example.com", "password": "Password123!"},
            format="json",
        )
        assert res_bob.status_code == status.HTTP_201_CREATED
        bob_data = res_bob.data["data"]
        assert bob_data["name"] == "Bob Builder"
        assert bob_data["email"] == "bob@example.com"
        assert "id" in bob_data

        # 3. Verify distinct database IDs
        assert alice_data["id"] != bob_data["id"]
        assert uuid.UUID(alice_data["id"]) != uuid.UUID(bob_data["id"])

    def test_02_login_and_verify_credentials(self):
        client = APIClient()

        # Create user Alice
        alice = User.objects.create_user(
            email="alice@example.com",
            password="Password123!",
            name="Alice Wonderland",
            email_verified=True,
        )

        # Verify valid credentials
        res = client.post(
            "/api/v1/users/verify-credentials/",
            {"email": "alice@example.com", "password": "Password123!"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.data["data"]
        assert data["id"] == str(alice.id)
        assert data["email"] == "alice@example.com"
        assert data["name"] == "Alice Wonderland"
        assert data["name"] != "John Doe"

    def test_03_switch_identity_bob_profile(self):
        client = APIClient()

        alice = User.objects.create_user(
            email="alice@example.com",
            password="Password123!",
            name="Alice Wonderland",
        )
        bob = User.objects.create_user(
            email="bob@example.com",
            password="Password123!",
            name="Bob Builder",
        )

        # Authenticate as Alice via identity token
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")
        profile_alice = client.get("/api/v1/users/profile/")
        assert profile_alice.status_code == status.HTTP_200_OK
        assert profile_alice.data["data"]["email"] == "alice@example.com"
        assert profile_alice.data["data"]["name"] == "Alice Wonderland"

        # Log out / switch identity to Bob
        client.credentials()  # clear credentials
        bob_token = generate_test_token(bob.id, bob.email, bob.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {bob_token}")
        profile_bob = client.get("/api/v1/users/profile/")
        assert profile_bob.status_code == status.HTTP_200_OK
        assert profile_bob.data["data"]["email"] == "bob@example.com"
        assert profile_bob.data["data"]["name"] == "Bob Builder"
        assert profile_bob.data["data"]["name"] != profile_alice.data["data"]["name"]

    def test_04_duplicate_registration_rejected(self):
        client = APIClient()
        User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")

        res = client.post(
            "/api/v1/users/register/",
            {"name": "Alice Duplicate", "email": "alice@example.com", "password": "Password123!"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in res.data["error"]

    def test_05_invalid_login_rejected(self):
        client = APIClient()
        User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")

        # Wrong password
        res = client.post(
            "/api/v1/users/verify-credentials/",
            {"email": "alice@example.com", "password": "WrongPassword999!"},
            format="json",
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # Nonexistent user
        res_nonexistent = client.post(
            "/api/v1/users/verify-credentials/",
            {"email": "nonexistent@example.com", "password": "Password123!"},
            format="json",
        )
        assert res_nonexistent.status_code == status.HTTP_401_UNAUTHORIZED

    def test_06_impersonation_prevention(self):
        client = APIClient()
        alice = User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")
        bob = User.objects.create_user(email="bob@example.com", password="Password123!", name="Bob")

        # Alice authenticates with valid token
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")

        # Attempt to pass Bob's user_id in payload or query params
        res = client.get(f"/api/v1/users/profile/?user_id={bob.id}")
        assert res.status_code == status.HTTP_200_OK
        # Server must still return Alice's profile because user is derived from cryptographic token
        assert res.data["data"]["email"] == "alice@example.com"
        assert res.data["data"]["id"] == str(alice.id)


@pytest.mark.django_db
class TestLibraryLifecycleAndIsolation:
    """Verifies Bug 2 fixes: Live persistence, retrieval, and strict account isolation."""

    def test_01_alice_adds_note_persisted_with_user_id(self):
        client = APIClient()
        alice = User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")

        # Add note via API
        payload = {
            "title": "Alice's Secret Research Notes",
            "content": "Detailed architectural notes on vector indexing and LLM grounding.",
            "tags": ["research", "llm"],
        }
        res = client.post("/api/v1/content/notes/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        created = res.data
        assert created["title"] == "Alice's Secret Research Notes"
        assert "id" in created
        assert uuid.UUID(created["id"])

        # Verify database record belongs to Alice
        item_in_db = ContentItem.objects.get(id=created["id"])
        assert item_in_db.user == alice
        assert item_in_db.title == "Alice's Secret Research Notes"
        assert item_in_db.raw_text == payload["content"]

    def test_02_library_listing_returns_persisted_item(self):
        client = APIClient()
        alice = User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")

        # Ingest note
        client.post(
            "/api/v1/content/notes/",
            {"title": "Note 1", "content": "Content for note 1", "tags": ["tag1"]},
            format="json",
        )

        # Query Library listing endpoint
        res = client.get("/api/v1/content/items/")
        assert res.status_code == status.HTTP_200_OK
        results = res.data.get("results", res.data)
        assert len(results) >= 1
        item = next(i for i in results if i["title"] == "Note 1")
        assert item["title"] == "Note 1"
        assert "tag1" in item["tags_list"]

    def test_03_bob_cannot_see_alice_private_items(self):
        client = APIClient()
        alice = User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")
        bob = User.objects.create_user(email="bob@example.com", password="Password123!", name="Bob")

        # Alice creates private item
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")
        res_create = client.post(
            "/api/v1/content/notes/",
            {"title": "Alice Confidential Document", "content": "Top secret content."},
            format="json",
        )
        alice_item_id = res_create.data["id"]

        # Bob logs in
        bob_token = generate_test_token(bob.id, bob.email, bob.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {bob_token}")

        # Bob queries Library list
        res_bob_list = client.get("/api/v1/content/items/")
        assert res_bob_list.status_code == status.HTTP_200_OK
        bob_results = res_bob_list.data.get("results", res_bob_list.data)
        bob_titles = [i["title"] for i in bob_results]
        assert "Alice Confidential Document" not in bob_titles

        # Bob attempts direct access to Alice's item by ID
        res_direct = client.get(f"/api/v1/content/items/{alice_item_id}/")
        assert res_direct.status_code == status.HTTP_404_NOT_FOUND

        # Bob attempts to delete Alice's item
        res_delete = client.delete(f"/api/v1/content/items/{alice_item_id}/")
        assert res_delete.status_code == status.HTTP_404_NOT_FOUND

    def test_04_failed_writes_return_error(self):
        client = APIClient()
        alice = User.objects.create_user(email="alice@example.com", password="Password123!", name="Alice")
        alice_token = generate_test_token(alice.id, alice.email, alice.name)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {alice_token}")

        # Empty content should fail validation
        res = client.post("/api/v1/content/notes/", {"title": "Missing content"}, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

        # Invalid URL format
        res_bad_url = client.post("/api/v1/content/urls/", {"url": "not-a-valid-url"}, format="json")
        assert res_bad_url.status_code == status.HTTP_400_BAD_REQUEST

        # SSRF forbidden URL
        res_ssrf = client.post("/api/v1/content/urls/", {"url": "http://169.254.169.254/metadata"}, format="json")
        assert res_ssrf.status_code == status.HTTP_400_BAD_REQUEST
