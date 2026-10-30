import time
import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()

def generate_test_token(sub="authjs_sub_12345", email="testuser@mediacompile.io", name="Test User",
                        secret=None, issuer=None, audience=None, exp_delta=60, image=None):
    """Helper to generate JWT tokens for Identity Bridge testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
        "image": image or "",
        "iss": issuer if issuer is not None else settings.INTERNAL_API_ISSUER,
        "aud": audience if audience is not None else settings.INTERNAL_API_AUDIENCE,
        "iat": now,
        "exp": now + exp_delta
    }
    return jwt.encode(payload, secret if secret is not None else settings.INTERNAL_API_SECRET, algorithm="HS256")

@pytest.mark.django_db
def test_identity_bridge_valid_token_provisions_and_authenticates():
    """Verify a valid signed JWT from Next.js successfully provisions user and authenticates."""
    client = APIClient()
    token = generate_test_token(sub="authjs_user_999", email="newuser@mediacompile.io", name="New User")
    
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data["success"] is True
    assert response.data["data"]["email"] == "newuser@mediacompile.io"
    assert response.data["data"]["authjs_id"] == "authjs_user_999"
    assert response.data["data"]["name"] == "New User"
    
    # Confirm user persisted in PostgreSQL
    db_user = User.objects.filter(authjs_id="authjs_user_999").first()
    assert db_user is not None
    assert db_user.email == "newuser@mediacompile.io"

@pytest.mark.django_db
def test_identity_bridge_links_existing_user_by_email():
    """Verify that an existing user created prior is linked to the incoming Auth.js subject."""
    existing = User.objects.create_user(email="preexisting@mediacompile.io", password="PreExistingPassword123!")
    assert existing.authjs_id is None

    client = APIClient()
    token = generate_test_token(sub="authjs_linked_888", email="preexisting@mediacompile.io")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")

    assert response.status_code == status.HTTP_200_OK
    existing.refresh_from_db()
    assert existing.authjs_id == "authjs_linked_888"

@pytest.mark.django_db
def test_identity_bridge_expired_token_rejected():
    """Verify expired token returns 401 Unauthorized."""
    client = APIClient()
    token = generate_test_token(exp_delta=-10) # Expired 10 seconds ago
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in str(response.data).lower()

@pytest.mark.django_db
def test_identity_bridge_invalid_signature_rejected():
    """Verify token signed with wrong secret is rejected."""
    client = APIClient()
    token = generate_test_token(secret="wrong-secret-key-that-does-not-match")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "signature" in str(response.data).lower()

@pytest.mark.django_db
def test_identity_bridge_invalid_issuer_rejected():
    """Verify token with invalid issuer claim is rejected."""
    client = APIClient()
    token = generate_test_token(issuer="unauthorized-issuer")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "issuer" in str(response.data).lower()

@pytest.mark.django_db
def test_identity_bridge_invalid_audience_rejected():
    """Verify token with invalid audience claim is rejected."""
    client = APIClient()
    token = generate_test_token(audience="wrong-audience")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "audience" in str(response.data).lower()

@pytest.mark.django_db
def test_unauthenticated_request_rejected():
    """Verify request with no Authorization header returns 401."""
    client = APIClient()
    response = client.get("/api/v1/users/me/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_disabled_user_rejected():
    """Verify inactive user cannot authenticate."""
    disabled_user = User.objects.create_user(
        email="disabled@mediacompile.io",
        authjs_id="disabled_sub_000",
        is_active=False
    )
    client = APIClient()
    token = generate_test_token(sub="disabled_sub_000", email="disabled@mediacompile.io")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/users/me/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_google_oauth_data_sync_and_resource_isolation():
    """Verify Google OAuth user profile syncs avatar/name and uniquely isolates chats and items."""
    from chat.models import ChatSession
    from content.models import ContentItem

    client = APIClient()
    google_avatar = "https://lh3.googleusercontent.com/a/ACg8ocL_test_avatar_url"
    google_token = generate_test_token(
        sub="google_oauth_1092837465",
        email="alex.google@example.com",
        name="Alex GoogleUser",
        image=google_avatar
    )

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {google_token}")
    me_res = client.get("/api/v1/users/me/")
    assert me_res.status_code == status.HTTP_200_OK
    assert me_res.data["data"]["email"] == "alex.google@example.com"
    assert me_res.data["data"]["authjs_id"] == "google_oauth_1092837465"
    assert me_res.data["data"]["image"] == google_avatar
    assert me_res.data["data"]["name"] == "Alex GoogleUser"

    google_user = User.objects.get(email="alex.google@example.com")
    assert google_user.image == google_avatar
    assert google_user.email_verified is True

    # Create a chat session and a content item for this Google user
    session = ChatSession.objects.create(user=google_user, title="Alex Private Google Chat")
    item = ContentItem.objects.create(user=google_user, title="Alex Private Google Doc", content_type="document")

    # Verify Google user can access their own session and items
    sessions_res = client.get("/api/v1/chat/sessions/")
    assert sessions_res.status_code == status.HTTP_200_OK
    raw_sessions = sessions_res.data.get("results", sessions_res.data if isinstance(sessions_res.data, list) else [])
    session_ids = [str(s["id"]) for s in raw_sessions]
    assert str(session.id) in session_ids

    items_res = client.get("/api/v1/content/items/")
    assert items_res.status_code == status.HTTP_200_OK
    raw_items = items_res.data.get("results", items_res.data if isinstance(items_res.data, list) else [])
    item_ids = [str(i["id"]) for i in raw_items]
    assert str(item.id) in item_ids

    # Switch to User B (different identity)
    user_b_token = generate_test_token(
        sub="other_user_sub_555",
        email="user_b@example.com",
        name="User B"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_b_token}")

    # User B must NOT see Alex's chat session or content item
    b_sessions_res = client.get("/api/v1/chat/sessions/")
    assert b_sessions_res.status_code == status.HTTP_200_OK
    raw_b_sessions = b_sessions_res.data.get("results", b_sessions_res.data if isinstance(b_sessions_res.data, list) else [])
    b_session_ids = [str(s["id"]) for s in raw_b_sessions]
    assert str(session.id) not in b_session_ids

    b_items_res = client.get("/api/v1/content/items/")
    assert b_items_res.status_code == status.HTTP_200_OK
    raw_b_items = b_items_res.data.get("results", b_items_res.data if isinstance(b_items_res.data, list) else [])
    b_item_ids = [str(i["id"]) for i in raw_b_items]
    assert str(item.id) not in b_item_ids

    # User B attempting direct access to Alex's chat session must be 404
    direct_res = client.get(f"/api/v1/chat/sessions/{session.id}/")
    assert direct_res.status_code == status.HTTP_404_NOT_FOUND

