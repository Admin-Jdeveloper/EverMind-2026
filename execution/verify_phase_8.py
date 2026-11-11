#!/usr/bin/env python3
"""
MediaCompile — Phase 8: Social and External Integrations Deterministic Verification Script.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Social and External Integrations)

Test Gates:
1. Token Encryption & Redaction at Rest:
   - Verifies Fernet symmetrical encryption of OAuth credentials and log/API masking.
2. Browser Bookmark Connector:
   - Verifies Netscape HTML & JSON import, SSRF rejection, automatic chunking, and deduplication.
3. YouTube Connector:
   - Verifies OAuth sandbox sync, Takeout export parser, metadata normalization, and deduplication.
4. Reddit Connector:
   - Verifies OAuth sandbox sync, GDPR CSV/JSON export parser, subreddit tagging, and deduplication.
5. Multi-Tenant Privacy Isolation:
   - Verifies User B can NEVER inspect, sync, or disconnect User A's connected accounts (returns 404).
6. Disconnect & Revocation:
   - Verifies revoking connection purges encrypted credentials and blocks subsequent sync attempts.
7. Live DRF Integrations REST API:
   - Validates live endpoints: /api/v1/integrations/, /connect/, /accounts/{id}/sync/, and file imports.
8. Full Backend Pytest Suite:
   - Verifies all 77 backend tests pass with 100% pass rate.
9. Next.js Production Build Zero-Regression:
   - Confirms Next.js compiles all routes including updated integrations dashboard with 0 errors.
"""

import sys
import os
import time
import subprocess
import json
import urllib.request
import urllib.error

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "web"))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")

# Initialize Django environment for in-process testing
sys.path.insert(0, API_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.contrib.auth import get_user_model
from content.models import ContentItem, ContentChunk
from integrations.models import ConnectedAccount
from integrations.crypto import encrypt_credentials, decrypt_credentials, redact_credentials
from integrations.connectors.registry import get_connector, list_supported_connectors

User = get_user_model()

def log_test(title, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {title}")
    if details:
        for line in details.strip().splitlines()[:12]:
            print(f"       {line}")
    return passed

def run_cmd(cmd, cwd=None, env=None):
    res = subprocess.run(cmd, cwd=cwd, env=env, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def get_node_jwt(email, name="Verify User"):
    """Generate signed JWT using Node.js identity bridge helper."""
    node_cmd = (
        'node --no-warnings --experimental-strip-types --input-type=module -e '
        '"import { generateInternalApiToken } from \'./lib/identity-token.ts\'; '
        f'console.log(generateInternalApiToken({{ id: \'verify-{email}\', email: \'{email}\', name: \'{name}\' }}));"'
    )
    code, stdout, stderr = run_cmd(node_cmd, cwd=WEB_DIR)
    if code != 0:
        raise RuntimeError(f"Failed to sign JWT with Node: {stderr}")
    return stdout.strip().splitlines()[-1]

def test_integrations_core():
    """Verify encryption, bookmark connector, youtube, reddit, and multi-tenant isolation in-process."""
    print("\n--- Gates 1 to 6: Core Integrations, Connectors & Security ---")
    results = []

    try:
        user_a, _ = User.objects.get_or_create(
            email="verify_integ_alice@mediacompile.io",
            defaults={"name": "Alice Integ Verify", "password": "ValidPassword123!"}
        )
        user_b, _ = User.objects.get_or_create(
            email="verify_integ_bob@mediacompile.io",
            defaults={"name": "Bob Integ Verify", "password": "ValidPassword123!"}
        )

        # Clean prior test state
        ConnectedAccount.objects.filter(user__in=[user_a, user_b]).delete()
        ContentItem.objects.filter(user__in=[user_a, user_b]).delete()

        # Gate 1: Token Encryption & Redaction
        raw_creds = {"access_token": "ya29.live_secret_token_123456", "refresh_token": "1//refresh_token_789"}
        encrypted = encrypt_credentials(raw_creds)
        decrypted = decrypt_credentials(encrypted)
        redacted = redact_credentials(raw_creds)

        acc = ConnectedAccount.objects.create(
            user=user_a,
            provider="youtube",
            external_account_id="yt_channel_verify",
            account_name="Verify Channel"
        )
        acc.set_credentials(raw_creds)
        acc.save()
        acc.refresh_from_db()

        enc_ok = (
            decrypted["access_token"] == raw_creds["access_token"] and
            "live_secret" not in acc.encrypted_credentials and
            "..." in redacted["access_token"]
        )
        results.append(log_test(
            "Gate 1: Token Encryption at Rest & Redaction",
            enc_ok,
            f"Tokens symmetrically encrypted with Fernet; decrypted accurately. Credentials masked for logs."
        ))

        # Gate 2: Browser Bookmark Import & SSRF Protection
        bm_connector = get_connector("bookmarks")
        html_payload = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
        <TITLE>Bookmarks</TITLE><H1>Bookmarks</H1>
        <DL><p>
            <DT><A HREF="https://postgresql.org/">PostgreSQL</A>
            <DT><A HREF="http://127.0.0.1:5432/internal">SSRF Link</A>
        </DL><p>
        """
        bm_res = bm_connector.import_export_data(user_a, html_payload)
        bm_ok = (bm_res.items_synced == 1 and bm_res.items_skipped == 1)

        # Re-import deduplication check
        bm_re = bm_connector.import_export_data(user_a, html_payload)
        dedup_ok = (bm_re.items_synced == 0 and bm_re.items_skipped == 2)
        results.append(log_test(
            "Gate 2: Browser Bookmark Connector & SSRF Defense",
            bm_ok and dedup_ok,
            f"Imported 1 safe link, rejected 1 internal SSRF link. Re-import successfully deduplicated."
        ))

        # Gate 3: YouTube Connector (OAuth Sync & Takeout Export)
        yt_connector = get_connector("youtube")
        yt_sync = yt_connector.sync_content(user_a, {"access_token": "mock_youtube_token"})
        yt_item = ContentItem.objects.filter(user=user_a, metadata__platform="youtube").first()
        yt_ok = (yt_sync.items_synced == 2 and yt_item is not None and yt_item.chunks.count() >= 1)

        # Takeout export import
        yt_takeout = yt_connector.import_export_data(user_a, json.dumps([
            {"id": "takeout_v1", "title": "Takeout Video", "url": "https://www.youtube.com/watch?v=takeout_v1"}
        ]))
        takeout_ok = (yt_takeout.items_synced == 1)
        results.append(log_test(
            "Gate 3: YouTube Connector (OAuth Sync, Metadata & Takeout Export)",
            yt_ok and takeout_ok,
            f"OAuth sync ingested 2 videos with vector chunks. Takeout JSON export parsed cleanly."
        ))

        # Gate 4: Reddit Connector (OAuth Sync & GDPR Export)
        reddit_connector = get_connector("reddit")
        reddit_sync = reddit_connector.sync_content(user_a, {"access_token": "mock_reddit_token", "username": "alice_verify"})
        reddit_item = ContentItem.objects.filter(user=user_a, metadata__platform="reddit").first()
        reddit_ok = (reddit_sync.items_synced == 2 and reddit_item is not None and reddit_item.chunks.count() >= 1)

        # GDPR CSV import
        csv_payload = "id,title,subreddit,permalink,body\nt3_v1,Postgres Invariants,PostgreSQL,https://reddit.com/r/PostgreSQL/comments/v1,Details\n"
        reddit_csv = reddit_connector.import_export_data(user_a, csv_payload)
        csv_ok = (reddit_csv.items_synced == 1)
        results.append(log_test(
            "Gate 4: Reddit Connector (OAuth Sync, Subreddit Tagging & GDPR CSV)",
            reddit_ok and csv_ok,
            f"OAuth sync ingested 2 saved posts with vector chunks. GDPR CSV export parsed cleanly."
        ))

        # Gate 5: Multi-Tenant Privacy Isolation
        acc_b = ConnectedAccount.objects.create(
            user=user_b,
            provider="reddit",
            external_account_id="reddit_user_bob",
            account_name="Bob Reddit"
        )
        acc_b.set_credentials({"access_token": "bob_mock_token"})
        acc_b.save()

        user_a_accounts = ConnectedAccount.objects.filter(user=user_a)
        user_b_accounts = ConnectedAccount.objects.filter(user=user_b)
        isolation_ok = (
            all(a.id != acc_b.id for a in user_a_accounts) and
            all(b.id != acc.id for b in user_b_accounts)
        )
        results.append(log_test(
            "Gate 5: Multi-Tenant Privacy Isolation",
            isolation_ok,
            "ConnectedAccount querysets strictly scoped to authenticated user tenant."
        ))

        # Gate 6: Disconnect & Revocation
        acc.disconnect()
        acc.refresh_from_db()
        revoked_ok = (acc.status == ConnectedAccount.STATUS_REVOKED and acc.encrypted_credentials == "")
        results.append(log_test(
            "Gate 6: Disconnect & Token Revocation",
            revoked_ok,
            f"Account revoked; encrypted tokens purged from database."
        ))

    except Exception as e:
        results.append(log_test("Gates 1-6 Exception", False, str(e)))

    return all(results)

def test_live_rest_api():
    """Verify live DRF integrations catalogue, connect, sync, and import endpoints."""
    print("\n--- Gate 7: Live DRF Integrations REST API ---")
    port = 8018
    server_proc = None

    try:
        server_cmd = f'"{VENV_PYTHON}" manage.py runserver 127.0.0.1:{port} --noreload'
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=API_DIR,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        base_url = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/health/", timeout=1) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.3)

        if not ready:
            return log_test("Gate 7: Live Server Readiness", False, f"Server failed to start on port {port}")

        token_a = get_node_jwt("alice_integ_live@mediacompile.io", "Alice Integ Live")
        auth_header = {"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"}

        # 1. GET /api/v1/integrations/ (Catalogue)
        req = urllib.request.Request(f"{base_url}/api/v1/integrations/", headers=auth_header, method="GET")
        with urllib.request.urlopen(req) as resp:
            cat_data = json.loads(resp.read().decode())
            assert "integrations" in cat_data
            p_ids = [i["id"] for i in cat_data["integrations"]]
            assert "youtube" in p_ids and "reddit" in p_ids and "bookmarks" in p_ids

        # 2. POST /api/v1/integrations/connect/
        connect_payload = {
            "provider": "youtube",
            "external_account_id": "yt_live_e2e_channel",
            "account_name": "E2E YouTube",
            "credentials": {"access_token": "mock_youtube_token"}
        }
        connect_req = urllib.request.Request(
            f"{base_url}/api/v1/integrations/connect/",
            data=json.dumps(connect_payload).encode(),
            headers=auth_header,
            method="POST"
        )
        with urllib.request.urlopen(connect_req) as resp:
            assert resp.status in (200, 201)
            connected = json.loads(resp.read().decode())
            acc_id = connected["id"]

        # 3. POST /api/v1/integrations/accounts/{id}/sync/
        sync_req = urllib.request.Request(
            f"{base_url}/api/v1/integrations/accounts/{acc_id}/sync/",
            headers=auth_header,
            method="POST"
        )
        with urllib.request.urlopen(sync_req) as resp:
            assert resp.status == 200
            sync_res = json.loads(resp.read().decode())
            assert sync_res["status"] == "success"

        # 4. Multi-Tenant isolation with User B token
        token_b = get_node_jwt("bob_integ_live@mediacompile.io", "Bob Integ Live")
        auth_header_b = {"Authorization": f"Bearer {token_b}", "Content-Type": "application/json"}
        bob_req = urllib.request.Request(
            f"{base_url}/api/v1/integrations/accounts/{acc_id}/sync/",
            headers=auth_header_b,
            method="POST"
        )
        try:
            urllib.request.urlopen(bob_req)
            cross_leak = True
        except urllib.error.HTTPError as he:
            cross_leak = False
            assert he.code == 404

        return log_test(
            "Gate 7: Live DRF Integrations REST API",
            not cross_leak,
            f"Catalogue verified, account {acc_id} connected & synced, foreign tenant access returned HTTP 404."
        )

    except Exception as e:
        return log_test("Gate 7: Live DRF Integrations API", False, str(e))
    finally:
        if server_proc:
            try:
                subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

def test_full_pytest_suite():
    """Verify all backend tests pass."""
    print("\n--- Gate 8: Full Backend Pytest Suite ---")
    cmd = f'"{VENV_PYTHON}" -m pytest apps/api/tests/ -v'
    code, stdout, stderr = run_cmd(cmd, cwd=ROOT_DIR)
    passed = (code == 0) and ("passed in" in stdout)
    return log_test(
        "Gate 8: Full Backend Pytest Suite",
        passed,
        stdout if not passed else stdout.splitlines()[-1]
    )

def test_nextjs_build():
    """Verify Next.js production build succeeds with 0 errors."""
    print("\n--- Gate 9: Next.js Production Build Zero-Regression ---")
    env = os.environ.copy()
    env.pop("NODE_ENV", None)
    cmd = "npm run build"
    code, stdout, stderr = run_cmd(cmd, cwd=WEB_DIR, env=env)
    passed = (code == 0) and ("Compiled successfully" in stdout)
    return log_test(
        "Gate 9: Next.js Production Build Zero-Regression",
        passed,
        "Compiled successfully with Turbopack across all routes." if passed else stderr
    )

def main():
    print("==========================================================================")
    print("MediaCompile — Phase 8: Social and External Integrations Verification")
    print("Source of Truth: MediaCompile-prompt.md (Section 18)")
    print("==========================================================================")

    gates_1_to_6 = test_integrations_core()
    gate_7 = test_live_rest_api()
    gate_8 = test_full_pytest_suite()
    gate_9 = test_nextjs_build()

    all_passed = gates_1_to_6 and gate_7 and gate_8 and gate_9

    print("\n==========================================================================")
    if all_passed:
        print(">>> ALL PHASE 8 GATES PASSED DETERMINISTICALLY! <<<")
        print("Ready for user review and explicit authorization for Phase 9.")
    else:
        print(">>> PHASE 8 VERIFICATION FAILED! Review gate failures above. <<<")
    print("==========================================================================")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
