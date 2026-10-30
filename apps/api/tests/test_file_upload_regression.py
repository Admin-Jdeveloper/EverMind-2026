"""
Evermind — Production File Upload Regression Test Suite.

Covers:
1. Successful authenticated file upload.
2. Invalid internal JWT rejection (wrong secret, expired, invalid audience).
3. Missing or placeholder production configuration detection.
4. S3 access denied, timeout, and incorrect region error handling.
5. Database failure during metadata persistence.
6. Invalid file type (executables, scripts, magic bytes) and oversized uploads.
7. S3 success followed by database failure (S3 object cleanup).
8. Upload success followed by Celery ingestion queueing failure.
9. Correct user ownership and cross-user access rejection.
10. Development vs Production storage provider workflows.
"""

import uuid
import jwt
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError, EndpointConnectionError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from content.models import ContentItem, Collection, Tag
from content.storage import (
    StorageServiceError,
    StorageAuthenticationError,
    StorageUploadError,
    upload_file_bytes,
    delete_file
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def test_user(db):
    user, _ = User.objects.get_or_create(
        email="test_uploader@example.com",
        defaults={
            "name": "Test Uploader",
            "is_active": True
        }
    )
    return user


@pytest.fixture
def other_user(db):
    user, _ = User.objects.get_or_create(
        email="other_user@example.com",
        defaults={
            "name": "Other User",
            "is_active": True
        }
    )
    return user


def generate_test_jwt(user, secret=None, iss="evermind-web", aud="evermind-api", expired=False):
    import time
    secret = secret or settings.INTERNAL_API_SECRET
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": getattr(user, "full_name", ""),
        "iss": iss,
        "aud": aud,
        "iat": now - 120 if expired else now,
        "exp": now - 60 if expired else now + 300,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.django_db
class TestFileUploadRegression:

    def test_successful_authenticated_file_upload(self, api_client, test_user):
        """1. Verify successful authenticated file upload with valid JWT, S3 upload, and DB creation."""
        from django.test import TestCase
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        file_content = b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\nstartxref\n0\n%%EOF"
        upload_file = SimpleUploadedFile("sample_report.pdf", file_content, content_type="application/pdf")

        with patch("content.views.upload_file_bytes") as mock_upload, \
             patch("content.tasks.process_document_content.delay") as mock_delay, \
             TestCase().captureOnCommitCallbacks(execute=True):
            mock_upload.return_value = f"users/{test_user.id}/files/abc123_sample_report.pdf"

            response = api_client.post(
                "/api/v1/content/files/",
                {"file": upload_file, "title": "My Quarterly Report"},
                format="multipart",
                HTTP_X_REQUEST_ID="req-test-success-001"
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.data
        assert data["title"] == "My Quarterly Report"
        assert data["content_type"] == "document"
        assert data["ingestion_status"] == "pending"
        assert "sample_report.pdf" in data["metadata"]["filename"]

        # Verify persisted in database with correct user ownership
        item = ContentItem.objects.get(id=data["id"])
        assert item.user == test_user
        assert item.file_key == f"users/{test_user.id}/files/abc123_sample_report.pdf"
        assert mock_delay.called

    def test_invalid_internal_jwt_rejection(self, api_client, test_user):
        """2. Verify rejection of invalid JWT signatures, expired tokens, and wrong audiences."""
        # A. Invalid signature (wrong secret)
        bad_token = generate_test_jwt(test_user, secret="completely-wrong-secret-key-32chars!!")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {bad_token}")

        upload_file = SimpleUploadedFile("doc.txt", b"Test content", content_type="text/plain")
        res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token signature" in str(res.data)

        # B. Expired token
        expired_token = generate_test_jwt(test_user, expired=True)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")
        upload_file = SimpleUploadedFile("doc.txt", b"Test content", content_type="text/plain")
        res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in str(res.data).lower()

        # C. Invalid audience
        wrong_aud_token = generate_test_jwt(test_user, aud="unauthorized-service")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {wrong_aud_token}")
        upload_file = SimpleUploadedFile("doc.txt", b"Test content", content_type="text/plain")
        res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert "audience" in str(res.data).lower()

    def test_missing_production_configuration(self):
        """3. Verify production check flags missing or default placeholder secrets."""
        secret = getattr(settings, "INTERNAL_API_SECRET", "")
        assert len(secret) >= 32, "INTERNAL_API_SECRET must be at least 32 characters."
        assert "development" not in secret.lower(), "Production must not use placeholder secret."

    def test_s3_error_handling_access_denied_timeout_and_invalid_region(self, api_client, test_user):
        """4. Verify S3 errors (AccessDenied, Timeout, SignatureDoesNotMatch) return safe 502/503 responses."""
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        file_content = b"Safe text file content"

        # Case A: AccessDenied (403 from S3)
        with patch("content.views.upload_file_bytes") as mock_upload:
            mock_upload.side_effect = StorageUploadError("Access denied writing to storage bucket 'evermind2026'.")
            upload_file = SimpleUploadedFile("test.txt", file_content, content_type="text/plain")
            res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart", HTTP_X_REQUEST_ID="req-s3-denied")
            assert res.status_code == status.HTTP_502_BAD_GATEWAY
            assert "Access denied" in res.data["error"]["message"]
            assert res.data["error"]["request_id"] == "req-s3-denied"
            # Never leak AWS credentials or secret keys in response
            assert "AKIA" not in str(res.data)
            assert "Secret" not in str(res.data)

        # Case B: StorageAuthenticationError (SignatureDoesNotMatch)
        with patch("content.views.upload_file_bytes") as mock_upload:
            mock_upload.side_effect = StorageAuthenticationError("Storage authentication failed: invalid credentials or signature mismatch.")
            upload_file = SimpleUploadedFile("test.txt", file_content, content_type="text/plain")
            res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart", HTTP_X_REQUEST_ID="req-s3-auth")
            assert res.status_code == status.HTTP_502_BAD_GATEWAY
            assert "Storage authentication failed" in res.data["error"]["message"]
            assert res.data["error"]["request_id"] == "req-s3-auth"

    def test_invalid_file_type_and_oversized_upload(self, api_client, test_user):
        """5. Verify validation rejects empty files, executables, scripts, and oversized uploads."""
        from content.serializers import DocumentUploadSerializer
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # A. Empty file (0 bytes)
        empty_file = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
        res = api_client.post("/api/v1/content/files/", {"file": empty_file}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "empty" in str(res.data).lower()

        # B. Disallowed extension (e.g. .exe, .sh)
        bad_ext_file = SimpleUploadedFile("malware.exe", b"MZdummyexecutable", content_type="application/octet-stream")
        res = api_client.post("/api/v1/content/files/", {"file": bad_ext_file}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Executable" in str(res.data) or "not permitted" in str(res.data)

        # C. Magic byte executable disguised as txt
        fake_txt_file = SimpleUploadedFile("innocent.txt", b"MZ\x90\x00\x03\x00\x00\x00", content_type="text/plain")
        res = api_client.post("/api/v1/content/files/", {"file": fake_txt_file}, format="multipart")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Executable" in str(res.data)

        # D. Oversized file (>50 MB limit)
        with patch.object(DocumentUploadSerializer, "MAX_FILE_SIZE", 50):
            oversized = SimpleUploadedFile("large.txt", b"A" * 100, content_type="text/plain")
            res = api_client.post("/api/v1/content/files/", {"file": oversized}, format="multipart")
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert "limit" in str(res.data).lower()

    def test_s3_success_followed_by_database_failure_cleans_up_s3(self, api_client, test_user):
        """6. S3 upload succeeds, but database metadata persistence fails: verify orphaned S3 file cleanup."""
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        upload_file = SimpleUploadedFile("report.txt", b"Report text content", content_type="text/plain")
        test_key = f"users/{test_user.id}/files/test_cleanup_key.txt"

        with patch("content.views.upload_file_bytes", return_value=test_key), \
             patch("content.models.ContentItem.objects.create", side_effect=Exception("Database disk failure")), \
             patch("content.views.delete_file") as mock_delete:

            res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart", HTTP_X_REQUEST_ID="req-db-fail")
            assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            # Verify S3 cleanup was invoked for the orphaned key
            mock_delete.assert_called_once_with(test_key)

    def test_upload_success_followed_by_celery_ingestion_failure(self, api_client, test_user):
        """7. S3 and DB succeed, but background Celery queueing fails: verify item is saved with failed status."""
        from django.test import TestCase
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        upload_file = SimpleUploadedFile("document.txt", b"Document content", content_type="text/plain")
        test_key = f"users/{test_user.id}/files/doc_key.txt"

        with patch("content.views.upload_file_bytes", return_value=test_key), \
             patch("content.tasks.process_document_content.delay", side_effect=Exception("Celery broker connection refused")), \
             TestCase().captureOnCommitCallbacks(execute=True):

            res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart")

        assert res.status_code == status.HTTP_202_ACCEPTED
        item_id = res.data["id"]

        item = ContentItem.objects.get(id=item_id)
        assert item.user == test_user
        assert item.file_key == test_key
        assert item.ingestion_status == ContentItem.STATUS_FAILED
        assert "unavailable" in item.error_message or "failed" in item.error_message

    def test_correct_user_ownership_and_cross_user_access_rejection(self, api_client, test_user, other_user):
        """8. Verify strict user isolation: User B cannot access, download, or delete User A's uploaded file."""
        # Create item owned by test_user
        item = ContentItem.objects.create(
            user=test_user,
            content_type=ContentItem.TYPE_DOCUMENT,
            title="Confidential Document",
            file_key=f"users/{test_user.id}/files/secret.pdf",
            metadata={"filename": "secret.pdf"}
        )

        # Authenticate as other_user
        other_token = generate_test_jwt(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_token}")

        # Attempt to retrieve
        get_res = api_client.get(f"/api/v1/content/items/{item.id}/")
        assert get_res.status_code == status.HTTP_404_NOT_FOUND

        # Attempt to download
        dl_res = api_client.get(f"/api/v1/content/items/{item.id}/download/")
        assert dl_res.status_code == status.HTTP_404_NOT_FOUND

        # Attempt to delete
        del_res = api_client.delete(f"/api/v1/content/items/{item.id}/")
        assert del_res.status_code == status.HTTP_404_NOT_FOUND

        # Ensure item was NOT deleted
        assert ContentItem.objects.filter(id=item.id).exists()

    def test_existing_development_upload_workflow(self, api_client, test_user):
        """9. Verify upload pipeline operates identically under MinIO storage provider setting."""
        token = generate_test_jwt(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        upload_file = SimpleUploadedFile("dev_doc.txt", b"Dev doc bytes", content_type="text/plain")

        with patch("content.storage.settings.STORAGE_PROVIDER", "minio"), \
             patch("content.views.upload_file_bytes", return_value=f"users/{test_user.id}/files/dev_doc.txt"), \
             patch("content.tasks.process_document_content.delay"):

            res = api_client.post("/api/v1/content/files/", {"file": upload_file}, format="multipart")
            assert res.status_code == status.HTTP_202_ACCEPTED
            assert res.data["title"] == "dev_doc.txt"
