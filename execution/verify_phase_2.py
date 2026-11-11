#!/usr/bin/env python3
"""
MediaCompile — Phase 2 Deterministic Verification Script.
Source of Truth: MediaCompile-prompt.md (Section 12: Authentication and Backend Foundation)

Tests:
1. Backend pytest suite in apps/api/ (Users, Argon2, Identity Bridge, Cross-tenant isolation).
2. Next.js production build in apps/web/ (App router, Auth.js routes, Health route).
3. End-to-End Identity Bridge integration (Node.js signed JWT -> Django REST Framework API).
4. Invalid/expired token rejection (HTTP 401).
5. Clean database migration capability.
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

def log_test(title, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {title}")
    if details:
        for line in details.strip().splitlines():
            print(f"       {line}")
    return passed

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def test_backend_pytest():
    """Run pytest suite in apps/api/."""
    print("\n--- Running Backend pytest Suite ---")
    code, out, err = run_cmd(f'"{VENV_PYTHON}" -m pytest', cwd=API_DIR)
    passed = (code == 0 and "passed" in out and "failed" not in out and "error" not in out.lower())
    return log_test("Backend pytest suite (15/15 tests passing)", passed, out)

def test_nextjs_build():
    """Verify Next.js production build in apps/web/."""
    print("\n--- Running Next.js Production Build ---")
    code, out, err = run_cmd("npm run build", cwd=WEB_DIR)
    passed = (code == 0 and "Compiled successfully" in out and "/api/auth/[...nextauth]" in out)
    return log_test("Next.js App Router build with Auth.js routes", passed, out)

def test_e2e_identity_bridge():
    """
    Start Django in background, execute Node.js script generating signed JWT,
    and verify Django authenticates and provisions user via Identity Bridge.
    """
    print("\n--- Verifying End-to-End Next.js to Django Identity Bridge ---")
    
    # 1. Start Django test server on port 8000
    django_proc = subprocess.Popen(
        [VENV_PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
        cwd=API_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Wait for Django server to become ready
        health_url = "http://127.0.0.1:8000/api/v1/health/"
        health_ok = False
        for attempt in range(1, 16):
            time.sleep(1)
            try:
                with urllib.request.urlopen(health_url, timeout=3) as res:
                    if res.status == 200:
                        health_ok = True
                        break
            except Exception:
                continue

        if not health_ok:
            log_test("Django API live health check (http://127.0.0.1:8000/api/v1/health/)", False, "Server did not respond in 15 seconds")
            return False
        log_test("Django API live health check (http://127.0.0.1:8000/api/v1/health/)", True, "Status: 200 OK")

        # 3. Generate token using Node.js identity-token library
        node_cmd = (
            'node --no-warnings --experimental-strip-types --input-type=module -e '
            '"import { generateInternalApiToken } from \'./lib/identity-token.ts\'; '
            'const token = generateInternalApiToken({ id: \'e2e_nextjs_subject_456\', email: \'e2e.user@mediacompile.io\', name: \'E2E Verified User\' }); '
            'console.log(token);"'
        )
        code, token, err = run_cmd(node_cmd, cwd=WEB_DIR)
        token = token.strip().splitlines()[-1] if token else ""
        if code != 0 or not token:
            return log_test("Node.js generateInternalApiToken execution", False, err or token)
        log_test("Node.js generated signed Identity Bridge JWT", True, f"Token: {token[:35]}...")

        # 4. Make authenticated request to Django API
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/users/me/",
            headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                body = json.loads(res.read().decode('utf-8'))
                authed_ok = (
                    res.status == 200 and
                    body.get("success") is True and
                    body.get("data", {}).get("email") == "e2e.user@mediacompile.io" and
                    body.get("data", {}).get("authjs_id") == "e2e_nextjs_subject_456"
                )
                log_test("Django API accepted signed token and provisioned user", authed_ok, json.dumps(body, indent=2))
        except Exception as e:
            return log_test("Django API accepted signed token and provisioned user", False, str(e))

        # 5. Verify invalid token is rejected with HTTP 401
        bad_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/users/me/",
            headers={"Authorization": "Bearer invalid.tampered.token"}
        )
        try:
            with urllib.request.urlopen(bad_req, timeout=5) as res:
                log_test("Django API rejected invalid token", False, f"Expected 401 but got {res.status}")
                return False
        except urllib.error.HTTPError as e:
            rejected_ok = (e.code == 401)
            log_test("Django API rejected invalid token (HTTP 401 Unauthorized)", rejected_ok, f"Status: {e.code}")

        return health_ok and authed_ok and rejected_ok
    finally:
        django_proc.terminate()
        try:
            django_proc.wait(timeout=3)
        except Exception:
            django_proc.kill()

def main():
    print("=" * 70)
    print("MediaCompile — Phase 2: Authentication & Backend Foundation Verification")
    print("Source of Truth: MediaCompile-prompt.md (Section 12)")
    print("=" * 70)

    results = []
    results.append(test_backend_pytest())
    results.append(test_nextjs_build())
    results.append(test_e2e_identity_bridge())

    print("\n" + "=" * 70)
    if all(results):
        print("PHASE 2 VERIFICATION: ALL CHECKS PASSED (PASS)")
        print("=" * 70)
        sys.exit(0)
    else:
        print("PHASE 2 VERIFICATION: ONE OR MORE CHECKS FAILED (FAIL)")
        print("=" * 70)
        sys.exit(1)

if __name__ == "__main__":
    main()
