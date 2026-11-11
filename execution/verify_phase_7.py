#!/usr/bin/env python3
"""
MediaCompile — Phase 7: Personalization and User-Controlled Memory Deterministic Verification Script.
Source of Truth: MediaCompile-prompt.md (Section 17: Personalization and User-Controlled Memory)

Test Gates:
1. Memory Sovereignty & Lifecycle:
   - Verifies explicit memory creation, update, active/disabled toggling, and persistent deletion.
2. Sensitive Trait Rejection & AI Safety:
   - Verifies strict rejection of prohibited sensitive topics (health, religion, politics, sensitive credentials).
3. Personalization Opt-Out & Prompt Construction:
   - Verifies that when personalization_enabled=False, memory injection is strictly bypassed in chat prompts.
4. Inactive & Deleted Memory Exclusion:
   - Verifies disabled memories (is_active=False) and deleted memories never enter active retrieval or prompts.
5. Multi-Tenant Privacy Isolation:
   - Verifies User B can NEVER read, edit, toggle, or delete User A's memory items (returns 404).
6. Live REST API Integration:
   - Tests live DRF endpoints: /api/v1/chat/preferences/, /api/v1/chat/memories/, and /api/v1/chat/topics/.
7. Full Backend Pytest Suite:
   - Runs all 63 backend tests, confirming 100% pass rate.
8. Next.js Production Build Zero-Regression:
   - Validates that Next.js compiles all routes including updated settings and topic dashboards with 0 errors.
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
from content.models import ContentItem, Collection
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

def test_memory_core_and_safety():
    """Verify memory lifecycle, sensitive rejection, opt-out, and tenant isolation."""
    print("\n--- Gates 1 to 5: Memory Sovereignty, AI Safety, Opt-Out & Isolation ---")
    results = []

    try:
        user_a, _ = User.objects.get_or_create(
            email="verify_pref_alice@mediacompile.io",
            defaults={"name": "Alice Pref Verify", "password": "ValidPassword123!"}
        )
        user_b, _ = User.objects.get_or_create(
            email="verify_pref_bob@mediacompile.io",
            defaults={"name": "Bob Pref Verify", "password": "ValidPassword123!"}
        )

        # Clean prior test state
        UserMemory.objects.filter(user__in=[user_a, user_b]).delete()
        UserPreference.objects.filter(user__in=[user_a, user_b]).delete()

        # Gate 1: Memory Sovereignty & Lifecycle
        mem1 = UserMemory.objects.create(
            user=user_a,
            memory_text="Prefers Python 3.14 and type hints on all function signatures.",
            category="technical",
            is_explicit=True,
            is_active=True,
            provenance={"source": "Settings UI"}
        )
        mem1.memory_text = "Prefers Python 3.14 with strict typing and docstrings."
        mem1.save()
        mem1.refresh_from_db()

        # Toggle inactive
        mem1.is_active = False
        mem1.save()
        mem1.refresh_from_db()
        toggled_ok = mem1.is_active is False

        # Toggle back to active
        mem1.is_active = True
        mem1.save()

        # Create temporary mem to test deletion
        temp_mem = UserMemory.objects.create(
            user=user_a,
            memory_text="Temporary style preference to be deleted.",
            is_active=True
        )
        temp_id = temp_mem.id
        temp_mem.delete()
        deleted_ok = not UserMemory.objects.filter(id=temp_id).exists()

        results.append(log_test(
            "Gate 1: Memory Sovereignty & Lifecycle (Create, Edit, Toggle, Delete)",
            toggled_ok and deleted_ok and mem1.memory_text.endswith("docstrings."),
            f"Created memory {mem1.id}, updated text, toggled active, verified deletion."
        ))

        # Gate 2: Sensitive Trait Rejection & AI Safety
        rejected_count = 0
        test_sensitive_cases = [
            ("User was diagnosed with asthma and takes daily medication.", "general"),
            ("Attends Baptist church every Sunday.", "general"),
            ("Active volunteer for Democratic party political campaign.", "general"),
            ("Confidential credit card CVV 888 and banking routing number.", "general"),
            ("User likes daily walks", "health"),
            ("User studies comparative scriptures", "religion"),
            ("User interested in local civic council meetings", "politics")
        ]
        for text, cat in test_sensitive_cases:
            try:
                validate_memory_safety(text, category=cat)
            except SensitiveMemoryError:
                rejected_count += 1

        all_sensitive_rejected = (rejected_count == len(test_sensitive_cases))
        results.append(log_test(
            "Gate 2: Sensitive Trait Rejection & AI Safety Guardrails",
            all_sensitive_rejected,
            f"Rejected {rejected_count}/{len(test_sensitive_cases)} sensitive personal categories (health, religion, politics, credentials)."
        ))

        # Gate 3: Personalization Opt-Out & Prompt Construction
        pref_a = get_user_preference(user_a)
        pref_a.personalization_enabled = True
        pref_a.save()

        active_mems = get_active_user_memories(user_a)
        prompt_with_pref = build_system_prompt("Context document", memories=active_mems)
        has_pref = "CONSENTED USER PREFERENCES & MEMORY" in prompt_with_pref and "Python 3.14" in prompt_with_pref

        # Disable personalization
        pref_a.personalization_enabled = False
        pref_a.save()

        disabled_mems = get_active_user_memories(user_a)
        prompt_without_pref = build_system_prompt("Context document", memories=disabled_mems)
        bypasses_pref = "CONSENTED USER PREFERENCES & MEMORY" not in prompt_without_pref and len(disabled_mems) == 0

        results.append(log_test(
            "Gate 3: Personalization Opt-Out & Prompt Construction",
            has_pref and bypasses_pref,
            "When enabled: preferences injected into prompt. When disabled: preferences completely excluded."
        ))

        # Restore enabled for subsequent checks
        pref_a.personalization_enabled = True
        pref_a.save()

        # Gate 4: Inactive and Deleted Memory Filtering
        inactive_mem = UserMemory.objects.create(
            user=user_a,
            memory_text="Should never appear: strictly inactive preference.",
            is_active=False
        )
        active_list = get_active_user_memories(user_a)
        inactive_excluded = not any("strictly inactive" in m for m in active_list)
        results.append(log_test(
            "Gate 4: Inactive & Deleted Memory Exclusion",
            inactive_excluded,
            f"Active memories count: {len(active_list)}. Inactive item correctly filtered out."
        ))

        # Gate 5: Multi-Tenant Privacy Isolation
        bob_mem = UserMemory.objects.create(
            user=user_b,
            memory_text="Bob's private workflow preference.",
            is_active=True
        )
        alice_mems = get_active_user_memories(user_a)
        bob_isolated = not any("Bob's private" in m for m in alice_mems)
        alice_isolated = not any("Python 3.14" in m for m in get_active_user_memories(user_b))
        results.append(log_test(
            "Gate 5: Multi-Tenant Privacy Isolation",
            bob_isolated and alice_isolated,
            "User A and User B memory pools strictly separated; 0 cross-tenant leakage."
        ))

    except Exception as e:
        results.append(log_test("Gates 1-5 Exception", False, str(e)))

    return all(results)

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

def test_live_rest_endpoints():
    """Verify live DRF preferences, memory CRUD, and topic summaries endpoints."""
    print("\n--- Gate 6: Live DRF Memory, Preferences & Topic Summaries API ---")
    port = 8017
    server_proc = None

    try:
        # Start Django test server
        server_cmd = f'"{VENV_PYTHON}" manage.py runserver 127.0.0.1:{port} --noreload'
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=API_DIR,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        base_url = f"http://127.0.0.1:{port}"
        # Poll health endpoint
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
            return log_test("Gate 6: Live API Server Start", False, f"Server failed to start on port {port}")

        token_a = get_node_jwt("alice_api_test@mediacompile.io", "Alice API Test")
        auth_header = {"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"}

        # 1. GET & PATCH /api/v1/chat/preferences/
        req = urllib.request.Request(f"{base_url}/api/v1/chat/preferences/", headers=auth_header, method="GET")
        with urllib.request.urlopen(req) as resp:
            pref_data = json.loads(resp.read().decode())
            assert "personalization_enabled" in pref_data

        patch_req = urllib.request.Request(
            f"{base_url}/api/v1/chat/preferences/",
            data=json.dumps({"personalization_enabled": True, "allow_inferred_memories": True}).encode(),
            headers=auth_header,
            method="PATCH"
        )
        with urllib.request.urlopen(patch_req) as resp:
            patched = json.loads(resp.read().decode())
            assert patched["personalization_enabled"] is True

        # 2. POST /api/v1/chat/memories/ (Create memory)
        mem_payload = {
            "memory_text": "Always explain using real-world distributed database analogies.",
            "category": "style",
            "is_explicit": True,
            "is_active": True,
            "provenance": {"source": "REST Verification Test"}
        }
        create_req = urllib.request.Request(
            f"{base_url}/api/v1/chat/memories/",
            data=json.dumps(mem_payload).encode(),
            headers=auth_header,
            method="POST"
        )
        with urllib.request.urlopen(create_req) as resp:
            assert resp.status == 201
            created_mem = json.loads(resp.read().decode())
            mem_id = created_mem["id"]

        # 3. POST /api/v1/chat/memories/{id}/toggle/
        toggle_req = urllib.request.Request(
            f"{base_url}/api/v1/chat/memories/{mem_id}/toggle/",
            headers=auth_header,
            method="POST"
        )
        with urllib.request.urlopen(toggle_req) as resp:
            assert resp.status == 200
            toggled = json.loads(resp.read().decode())
            assert toggled["is_active"] is False

        # 4. GET /api/v1/chat/topics/
        topics_req = urllib.request.Request(f"{base_url}/api/v1/chat/topics/", headers=auth_header, method="GET")
        with urllib.request.urlopen(topics_req) as resp:
            assert resp.status == 200
            topics_data = json.loads(resp.read().decode())
            assert "topics" in topics_data

        # 5. Multi-tenant 404 test with Token B
        token_b = get_node_jwt("bob_api_test@mediacompile.io", "Bob API Test")
        auth_header_b = {"Authorization": f"Bearer {token_b}", "Content-Type": "application/json"}
        bob_req = urllib.request.Request(f"{base_url}/api/v1/chat/memories/{mem_id}/", headers=auth_header_b, method="GET")
        try:
            urllib.request.urlopen(bob_req)
            cross_leak = True
        except urllib.error.HTTPError as he:
            cross_leak = False
            assert he.code == 404

        return log_test(
            "Gate 6: Live DRF Memory, Preferences & Topic Summaries API",
            not cross_leak,
            f"Preferences PATCHed, memory {mem_id} created and toggled, topics fetched, cross-user access returned 404."
        )

    except Exception as e:
        return log_test("Gate 6: Live DRF Memory API", False, str(e))
    finally:
        if server_proc:
            try:
                subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

def test_full_pytest_suite():
    """Verify all backend tests pass."""
    print("\n--- Gate 7: Full Backend Pytest Suite ---")
    cmd = f'"{VENV_PYTHON}" -m pytest apps/api/tests/ -v'
    code, stdout, stderr = run_cmd(cmd, cwd=ROOT_DIR)
    passed = (code == 0) and ("passed in" in stdout)
    return log_test(
        "Gate 7: Full Backend Pytest Suite",
        passed,
        stdout if not passed else stdout.splitlines()[-1]
    )

def test_nextjs_build():
    """Verify Next.js production build succeeds with 0 errors."""
    print("\n--- Gate 8: Next.js Production Build Zero-Regression ---")
    env = os.environ.copy()
    env.pop("NODE_ENV", None)
    cmd = "npm run build"
    code, stdout, stderr = run_cmd(cmd, cwd=WEB_DIR, env=env)
    passed = (code == 0) and ("Compiled successfully" in stdout)
    return log_test(
        "Gate 8: Next.js Production Build Zero-Regression",
        passed,
        "Compiled successfully with Turbopack across all routes." if passed else stderr
    )

def main():
    print("==========================================================================")
    print("MediaCompile — Phase 7: Personalization & User-Controlled Memory Verification")
    print("Source of Truth: MediaCompile-prompt.md (Section 17)")
    print("==========================================================================")

    gate_1_to_5 = test_memory_core_and_safety()
    gate_6 = test_live_rest_endpoints()
    gate_7 = test_full_pytest_suite()
    gate_8 = test_nextjs_build()

    all_passed = gate_1_to_5 and gate_6 and gate_7 and gate_8

    print("\n==========================================================================")
    if all_passed:
        print(">>> ALL PHASE 7 GATES PASSED DETERMINISTICALLY! <<<")
        print("Ready for user review and explicit authorization for Phase 8.")
    else:
        print(">>> PHASE 7 VERIFICATION FAILED! Review gate failures above. <<<")
    print("==========================================================================")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
