import time
import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()

def generate_test_token(sub="authjs_sub_12345", email="testuser@mediacompile.io", name="Test User",
                        secret=None, issuer=None, audience=None, exp_delta=60):
    """Helper to generate JWT tokens for Identity Bridge testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
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
