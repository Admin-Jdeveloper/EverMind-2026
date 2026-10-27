"""
MediaCompile — Phase 8: Social and External Integrations Test Suite.
Source of Truth: MediaCompile-prompt.md (Section 18: Social and External Integrations)

Validates:
1. Token Encryption & Redaction: Credentials encrypted with Fernet at rest, never leaked in API output.
2. Browser Bookmark Connector: Netscape HTML and JSON import with SSRF rejection and deduplication.
3. YouTube Connector: OAuth sync, metadata normalization, deduplication, Takeout export import, token expiry.
4. Reddit Connector: OAuth sync, subreddit tagging, deduplication, CSV/JSON export import, token expiry.
5. Multi-Tenant Isolation: User B cannot view, sync, or disconnect User A's connected accounts (returns 404).
6. Disconnect & Revocation: Revokes access, purges encrypted tokens, blocks subsequent sync attempts.
7. Catalogue & Policy Guidance: GET /api/v1/integrations/ documents active connectors and optional platform policies.
"""

import io
import json
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from content.models import ContentItem, ContentChunk
from integrations.models import ConnectedAccount
from integrations.crypto import encrypt_credentials, decrypt_credentials, redact_credentials
from integrations.connectors.registry import get_connector, list_supported_connectors

User = get_user_model()

@pytest.fixture
def integration_users(db):
    user_a = User.objects.create_user(
        email="alice.integrations@mediacompile.io",
        password="ValidPassword123!",
        name="Alice Integrations"
    )
    user_b = User.objects.create_user(
        email="bob.integrations@mediacompile.io",
        password="ValidPassword123!",
        name="Bob Integrations"
    )
    return user_a, user_b

@pytest.fixture
def auth_client_a(integration_users):
    user_a, _ = integration_users
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client

@pytest.fixture
def auth_client_b(integration_users):
    _, user_b = integration_users
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client

# =========================================================================
# 1. Token Encryption at Rest & Log Redaction
# =========================================================================

def test_token_encryption_roundtrip():
    """Verify credentials dictionary is symmetrically encrypted and decrypted."""
    creds = {
        "access_token": "ya29.a0AfH6SMB_secret_access_token_12345",
        "refresh_token": "1//04_refresh_token_secret_67890",
        "token_type": "Bearer",
        "expires_in": 3600
    }
    encrypted = encrypt_credentials(creds)
    assert isinstance(encrypted, str)
    assert len(encrypted) > 0
    assert "ya29" not in encrypted
    assert "secret" not in encrypted

    decrypted = decrypt_credentials(encrypted)
    assert decrypted["access_token"] == creds["access_token"]
    assert decrypted["refresh_token"] == creds["refresh_token"]
    assert decrypted["expires_in"] == 3600

def test_token_redaction():
    """Verify redact_credentials masks sensitive keys."""
    raw = {
        "access_token": "ya29.secret_token_12345",
        "refresh_token": "1//secret_refresh",
        "username": "alice_dev",
        "scope": "read"
    }
    redacted = redact_credentials(raw)
    assert redacted["username"] == "alice_dev"
    assert redacted["scope"] == "read"
    assert redacted["access_token"].startswith("ya29")
    assert redacted["access_token"].endswith("2345")
    assert "..." in redacted["access_token"]

@pytest.mark.django_db
def test_connected_account_token_secrecy(auth_client_a, integration_users):
    """Verify serialized ConnectedAccount never exposes encrypted_credentials."""
    user_a, _ = integration_users
    acc = ConnectedAccount.objects.create(
        user=user_a,
        provider="youtube",
        external_account_id="yt_channel_123",
        account_name="Alice YouTube Channel"
    )
    acc.set_credentials({"access_token": "super_secret_token", "refresh_token": "super_secret_refresh"})
    acc.save()

    res = auth_client_a.get(f"/api/v1/integrations/accounts/{acc.id}/")
    assert res.status_code == 200
    data = res.json()
    assert "encrypted_credentials" not in data
    assert "super_secret_token" not in str(data)

# =========================================================================
# 2. Browser Bookmarks Connector (Netscape HTML & JSON)
# =========================================================================

@pytest.mark.django_db
def test_bookmark_html_import(integration_users):
    """Verify Netscape HTML bookmark import parses URLs, creates chunks, and deduplicates."""
    user_a, _ = integration_users
    connector = get_connector("bookmarks")
    assert connector is not None

    html_payload = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
    <META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
    <TITLE>Bookmarks</TITLE>
    <H1>Bookmarks</H1>
    <DL><p>
        <DT><H3 ADD_DATE="1600000000">Distributed Systems</H3>
        <DL><p>
            <DT><A HREF="https://raft.github.io/" ADD_DATE="1600000001">Raft Consensus Algorithm</A>
            <DT><A HREF="https://lamport.azurewebsites.net/pubs/paxos-simple.pdf" ADD_DATE="1600000002">Paxos Made Simple</A>
            <DT><A HREF="http://127.0.0.1:8000/internal" ADD_DATE="1600000003">SSRF Attack Link</A>
        </DL><p>
    </DL><p>
    """

    result = connector.import_export_data(user_a, html_payload)
    assert result.success is True
    assert result.items_synced == 2  # Raft + Paxos (127.0.0.1 SSRF link rejected)
    assert result.items_skipped == 1  # SSRF link skipped

    # Verify items created
    raft_item = ContentItem.objects.get(user=user_a, source_url="https://raft.github.io/")
    assert raft_item.title == "Raft Consensus Algorithm"
    assert raft_item.chunks.count() >= 1

    # Re-import identical content: should be skipped (deduplication)
    re_result = connector.import_export_data(user_a, html_payload)
    assert re_result.success is True
    assert re_result.items_synced == 0
    assert re_result.items_skipped == 3

@pytest.mark.django_db
def test_bookmark_json_import(integration_users):
    """Verify JSON bookmark tree import."""
    user_a, _ = integration_users
    connector = get_connector("bookmarks")

    json_payload = json.dumps([
        {"title": "PostgreSQL Documentation", "url": "https://www.postgresql.org/docs/"},
        {"title": "pgvector GitHub", "url": "https://github.com/pgvector/pgvector"}
    ])

    result = connector.import_export_data(user_a, json_payload)
    assert result.success is True
    assert result.items_synced == 2
    assert ContentItem.objects.filter(user=user_a, source_url="https://www.postgresql.org/docs/").exists()

# =========================================================================
# 3. YouTube Connector (OAuth Sync & Takeout Export)
# =========================================================================

@pytest.mark.django_db
def test_youtube_connector_sync_and_deduplication(integration_users):
    """Verify YouTube connector syncs videos, normalizes metadata, and deduplicates."""
    user_a, _ = integration_users
    connector = get_connector("youtube")

    # 1. Test connection with sandbox mock token
    assert connector.test_connection({"access_token": "mock_youtube_token"}) is True
    assert connector.test_connection({"access_token": "mock_expired_token"}) is False

    # 2. Sync content
    res = connector.sync_content(user_a, credentials={"access_token": "mock_youtube_token"}, limit=10)
    assert res.success is True
    assert res.items_synced == 2

    # Check created ContentItem
    yt_item = ContentItem.objects.filter(user=user_a, metadata__platform="youtube").first()
    assert yt_item is not None
    assert yt_item.metadata.get("platform") == "youtube"
    assert yt_item.chunks.count() >= 1

    # 3. Deduplication check on second sync
    re_res = connector.sync_content(user_a, credentials={"access_token": "mock_youtube_token"}, limit=10)
    assert re_res.success is True
    assert re_res.items_synced == 0
    assert re_res.items_skipped == 2

@pytest.mark.django_db
def test_youtube_token_expiry_handling(integration_users):
    """Verify expired token returns error status."""
    user_a, _ = integration_users
    connector = get_connector("youtube")
    res = connector.sync_content(user_a, credentials={"access_token": "mock_expired_token"})
    assert res.success is False
    assert res.details.get("status") == "expired"

@pytest.mark.django_db
def test_youtube_takeout_export_import(integration_users):
    """Verify Google Takeout YouTube playlist JSON import."""
    user_a, _ = integration_users
    connector = get_connector("youtube")

    takeout_json = json.dumps([
        {
            "id": "takeout_vid_1",
            "title": "Next.js 16 App Router Tutorial",
            "channel": "Vercel",
            "url": "https://www.youtube.com/watch?v=takeout_vid_1",
            "description": "Learn the new features of Next.js 16 Turbopack and React 19."
        }
    ])
    result = connector.import_export_data(user_a, takeout_json)
    assert result.success is True
    assert result.items_synced == 1
    assert ContentItem.objects.filter(user=user_a, source_url="https://www.youtube.com/watch?v=takeout_vid_1").exists()

# =========================================================================
# 4. Reddit Connector (OAuth Sync & CSV/JSON Export)
# =========================================================================

@pytest.mark.django_db
def test_reddit_connector_sync_and_deduplication(integration_users):
    """Verify Reddit connector syncs saved posts, parses subreddits, and deduplicates."""
    user_a, _ = integration_users
    connector = get_connector("reddit")

    assert connector.test_connection({"access_token": "mock_reddit_token"}) is True
    assert connector.test_connection({"access_token": "mock_expired_token"}) is False

    res = connector.sync_content(user_a, credentials={"access_token": "mock_reddit_token", "username": "alice_dev"})
    assert res.success is True
    assert res.items_synced == 2

    # Check created ContentItem
    reddit_item = ContentItem.objects.filter(user=user_a, metadata__platform="reddit").first()
    assert reddit_item is not None
    assert "r/" in reddit_item.raw_text
    assert reddit_item.chunks.count() >= 1

    # Re-sync deduplication
    re_res = connector.sync_content(user_a, credentials={"access_token": "mock_reddit_token", "username": "alice_dev"})
    assert re_res.success is True
    assert re_res.items_synced == 0
    assert re_res.items_skipped == 2

@pytest.mark.django_db
def test_reddit_csv_export_import(integration_users):
    """Verify Reddit GDPR CSV export import."""
    user_a, _ = integration_users
    connector = get_connector("reddit")

    csv_data = "id,title,subreddit,author,permalink,selftext\n" \
               "t3_csv1,PostgreSQL Indexing Guide,PostgreSQL,dba_pro,https://reddit.com/r/PostgreSQL/comments/csv1/guide,Comprehensive indexing advice.\n"

    result = connector.import_export_data(user_a, csv_data)
    assert result.success is True
    assert result.items_synced == 1
    assert ContentItem.objects.filter(user=user_a, source_url="https://reddit.com/r/PostgreSQL/comments/csv1/guide").exists()

# =========================================================================
# 5. REST API Endpoints & Multi-Tenant Isolation
# =========================================================================

@pytest.mark.django_db
def test_connect_account_api(auth_client_a):
    """Test connecting an account via POST /api/v1/integrations/connect/."""
    payload = {
        "provider": "youtube",
        "external_account_id": "yt_channel_alice_api",
        "account_name": "Alice Channel",
        "credentials": {
            "access_token": "mock_youtube_token"
        }
    }
    res = auth_client_a.post("/api/v1/integrations/connect/", payload, format="json")
    assert res.status_code == 201
    data = res.json()
    assert data["provider"] == "youtube"
    assert data["account_name"] == "Alice Channel"
    assert data["status"] == "active"
    assert "encrypted_credentials" not in data

@pytest.mark.django_db
def test_multi_tenant_connected_account_isolation(auth_client_a, auth_client_b, integration_users):
    """Verify User B cannot view, sync, or disconnect User A's connected account."""
    user_a, _ = integration_users
    acc_a = ConnectedAccount.objects.create(
        user=user_a,
        provider="youtube",
        external_account_id="yt_channel_isolated",
        account_name="Alice Isolated Channel"
    )
    acc_a.set_credentials({"access_token": "mock_youtube_token"})
    acc_a.save()

    # User B list: User A's account omitted
    res = auth_client_b.get("/api/v1/integrations/accounts/")
    assert res.status_code == 200
    results = res.json() if isinstance(res.json(), list) else res.json().get("results", [])
    assert all(a["id"] != str(acc_a.id) for a in results)

    # User B retrieve direct -> 404
    res = auth_client_b.get(f"/api/v1/integrations/accounts/{acc_a.id}/")
    assert res.status_code == 404

    # User B sync -> 404
    res = auth_client_b.post(f"/api/v1/integrations/accounts/{acc_a.id}/sync/")
    assert res.status_code == 404

    # User B disconnect -> 404
    res = auth_client_b.post(f"/api/v1/integrations/accounts/{acc_a.id}/disconnect/")
    assert res.status_code == 404

@pytest.mark.django_db
def test_sync_and_disconnect_api(auth_client_a, integration_users):
    """Test live sync action and disconnect action via REST API."""
    user_a, _ = integration_users
    acc = ConnectedAccount.objects.create(
        user=user_a,
        provider="youtube",
        external_account_id="yt_channel_sync_test",
        account_name="Alice Sync Channel"
    )
    acc.set_credentials({"access_token": "mock_youtube_token"})
    acc.save()

    # 1. Trigger sync
    sync_res = auth_client_a.post(f"/api/v1/integrations/accounts/{acc.id}/sync/")
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["status"] == "success"
    assert sync_data["items_synced"] == 2

    # 2. Disconnect
    disc_res = auth_client_a.post(f"/api/v1/integrations/accounts/{acc.id}/disconnect/")
    assert disc_res.status_code == 200
    assert disc_res.json()["status"] == "revoked"

    acc.refresh_from_db()
    assert acc.status == ConnectedAccount.STATUS_REVOKED
    assert acc.encrypted_credentials == ""

    # 3. Attempting to sync after disconnect returns 400
    after_sync = auth_client_a.post(f"/api/v1/integrations/accounts/{acc.id}/sync/")
    assert after_sync.status_code == 400

@pytest.mark.django_db
def test_catalogue_api(auth_client_a):
    """Test catalogue endpoint returns active connectors and optional platform policies."""
    res = auth_client_a.get("/api/v1/integrations/")
    assert res.status_code == 200
    data = res.json()
    assert "integrations" in data
    ids = [i["id"] for i in data["integrations"]]
    assert "bookmarks" in ids
    assert "youtube" in ids
    assert "reddit" in ids
    assert "x" in ids
    assert "instagram" in ids
    assert "linkedin" in ids
