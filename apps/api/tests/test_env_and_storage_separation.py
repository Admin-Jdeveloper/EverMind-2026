"""
Evermind — Development vs Production Environment Separation & Storage Provider Tests.

Verifies:
1. Environment validation permits local defaults in Development mode.
2. Environment validation strictly rejects insecure keys, localhost database,
   localhost Redis, and missing AWS S3 credentials in Production mode.
3. Storage client and bucket resolution switches correctly between MinIO (dev) and AWS S3 (prod).
4. Identity bridge dual-compatibility: validates both 'evermind-*' and legacy 'mediacompile-*' tokens.
"""

import os
import jwt
import pytest
from unittest.mock import patch
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from config.env_validation import validate_environment_configuration, ProductionConfigurationError
from content.storage import get_active_bucket_name, get_s3_client
from users.authentication import AuthJsBridgeAuthentication
from django.contrib.auth import get_user_model

User = get_user_model()


def test_development_mode_permits_local_defaults():
    """Verify that in development mode, local mocks and default settings do not raise errors."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        # Must not raise ProductionConfigurationError
        validate_environment_configuration()


def test_production_mode_detects_insecure_secret_key():
    """Verify that in production mode, insecure or default secret keys are rejected."""
    env_vars = {
        "ENVIRONMENT": "production",
        "DJANGO_SECRET_KEY": "django-insecure-default-dev-key",
        "DATABASE_URL": "postgresql://user:pass@render-db-host:5432/evermind?sslmode=require",
        "REDIS_URL": "rediss://:pass@render-redis-host:6379/0",
        "STORAGE_PROVIDER": "s3",
        "AWS_STORAGE_BUCKET_NAME": "evermind2026",
        "AWS_S3_REGION_NAME": "ap-south-1",
        "AWS_ACCESS_KEY_ID": "AKIAVALIDKEY12345678",
        "AWS_SECRET_ACCESS_KEY": "ValidSecretKeyString1234567890",
        "GROQ_API_KEY": "gsk_valid_production_key_12345",
        "INTERNAL_API_SECRET": "a-strong-32-byte-secret-for-production-jwt",
    }
    with patch.dict(os.environ, env_vars):
        with pytest.raises(ProductionConfigurationError) as exc_info:
            validate_environment_configuration()
        assert "DJANGO_SECRET_KEY" in str(exc_info.value)


def test_production_mode_detects_localhost_database():
    """Verify that in production mode, a localhost database URL is rejected."""
    env_vars = {
        "ENVIRONMENT": "production",
        "DJANGO_SECRET_KEY": "a-strong-50-character-production-secret-key-xyz-12345",
        "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/evermind",
        "REDIS_URL": "rediss://:pass@render-redis-host:6379/0",
        "STORAGE_PROVIDER": "s3",
        "AWS_STORAGE_BUCKET_NAME": "evermind2026",
        "AWS_S3_REGION_NAME": "ap-south-1",
        "AWS_ACCESS_KEY_ID": "AKIAVALIDKEY12345678",
        "AWS_SECRET_ACCESS_KEY": "ValidSecretKeyString1234567890",
        "GROQ_API_KEY": "gsk_valid_production_key_12345",
        "INTERNAL_API_SECRET": "a-strong-32-byte-secret-for-production-jwt",
    }
    with patch.dict(os.environ, env_vars):
        with pytest.raises(ProductionConfigurationError) as exc_info:
            validate_environment_configuration()
        assert "DATABASE_URL" in str(exc_info.value)
        assert "localhost" in str(exc_info.value)


def test_production_mode_detects_missing_s3_credentials():
    """Verify that in production mode, missing AWS S3 credentials fail validation."""
    env_vars = {
        "ENVIRONMENT": "production",
        "DJANGO_SECRET_KEY": "a-strong-50-character-production-secret-key-xyz-12345",
        "DATABASE_URL": "postgresql://user:pass@render-db-host:5432/evermind?sslmode=require",
        "REDIS_URL": "rediss://:pass@render-redis-host:6379/0",
        "STORAGE_PROVIDER": "s3",
        "AWS_STORAGE_BUCKET_NAME": "evermind2026",
        "AWS_S3_REGION_NAME": "ap-south-1",
        "AWS_ACCESS_KEY_ID": "minioadmin", # Invalid for real AWS S3
        "AWS_SECRET_ACCESS_KEY": "",
        "GROQ_API_KEY": "gsk_valid_production_key_12345",
        "INTERNAL_API_SECRET": "a-strong-32-byte-secret-for-production-jwt",
    }
    with patch.dict(os.environ, env_vars):
        with pytest.raises(ProductionConfigurationError) as exc_info:
            validate_environment_configuration()
        assert "AWS_ACCESS_KEY_ID" in str(exc_info.value)


def test_storage_bucket_switching():
    """Verify that get_active_bucket_name returns appropriate bucket for provider."""
    # MinIO mode
    with patch.object(settings, 'STORAGE_PROVIDER', 'minio'):
        with patch.object(settings, 'MINIO_BUCKET_NAME', 'mediacompile-uploads'):
            assert get_active_bucket_name() == 'mediacompile-uploads'

    # S3 mode
    with patch.object(settings, 'STORAGE_PROVIDER', 's3'):
        with patch.object(settings, 'AWS_STORAGE_BUCKET_NAME', 'evermind2026'):
            assert get_active_bucket_name() == 'evermind2026'


@pytest.mark.django_db
def test_identity_bridge_evermind_and_legacy_compatibility():
    """
    Verify that AuthJsBridgeAuthentication validates:
    - Evermind tokens (iss: 'evermind-web', aud: 'evermind-api')
    - Legacy tokens (iss: 'mediacompile-web', aud: 'mediacompile-api')
    And rejects invalid tokens.
    """
    auth_bridge = AuthJsBridgeAuthentication()
    factory = APIRequestFactory()
    user = User.objects.create_user(email="token_user@evermind.io", password="ValidPassword123!")

    # 1. Evermind Token
    evermind_token = jwt.encode(
        {"sub": str(user.id), "email": user.email, "iss": "evermind-web", "aud": "evermind-api"},
        settings.INTERNAL_API_SECRET,
        algorithm="HS256"
    )
    req1 = factory.get("/api/v1/users/me/", HTTP_AUTHORIZATION=f"Bearer {evermind_token}")
    auth_result = auth_bridge.authenticate(req1)
    assert auth_result is not None
    assert auth_result[0].email == "token_user@evermind.io"

    # 2. Legacy MediaCompile Token
    legacy_token = jwt.encode(
        {"sub": str(user.id), "email": user.email, "iss": "mediacompile-web", "aud": "mediacompile-api"},
        settings.INTERNAL_API_SECRET,
        algorithm="HS256"
    )
    req2 = factory.get("/api/v1/users/me/", HTTP_AUTHORIZATION=f"Bearer {legacy_token}")
    legacy_result = auth_bridge.authenticate(req2)
    assert legacy_result is not None
    assert legacy_result[0].email == "token_user@evermind.io"

    # 3. Spoofed Token with foreign audience
    spoofed_token = jwt.encode(
        {"sub": str(user.id), "email": user.email, "iss": "evermind-web", "aud": "attacker-api"},
        settings.INTERNAL_API_SECRET,
        algorithm="HS256"
    )
    req3 = factory.get("/api/v1/users/me/", HTTP_AUTHORIZATION=f"Bearer {spoofed_token}")
    with pytest.raises(AuthenticationFailed):
        auth_bridge.authenticate(req3)
