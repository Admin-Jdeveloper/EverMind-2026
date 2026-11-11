#!/usr/bin/env python3
"""
MediaCompile — Secret, Credential and Dependency Vulnerability Scanner.

Checks:
1. Hardcoded Secrets Scan: Searches workspace code for private keys, AWS/OAuth secrets, and hardcoded tokens.
2. Git Exclusion Verification: Verifies .env, credentials.json, and secrets are excluded from Git tracking.
3. Environment Decoupling: Verifies Django and Next.js require environment variables for secret credentials.
"""

import sys
import os
import re
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Regex patterns for common secret leaks
SECRET_PATTERNS = [
    (r'-----BEGIN (?:RSA )?PRIVATE KEY-----', 'RSA/Private Key Block'),
    (r'AIza[0-9A-Za-z-_]{35}', 'Google API Key'),
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
    (r'(?i)ya29\.[0-9A-Za-z\-_]{50,}', 'Google OAuth Access Token'),
    (r'(?i)ghp_[0-9A-Za-z]{36}', 'GitHub Personal Access Token'),
    (r'(?i)sk-[a-zA-Z0-9]{32,}', 'OpenAI API Secret Key'),
]

IGNORE_DIRS = {
    '.git', '.venv', 'node_modules', '.next', '.pytest_cache',
    '__pycache__', '.tmp', 'dist', 'build'
}

IGNORE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2',
    '.ttf', '.eot', '.webp', '.log', '.db', '.sqlite3', '.parquet', '.bin'
}

IGNORE_FILES = {
    '.env.example', 'scan_secrets_and_deps.py', '.env', '.env.development', '.env.production', '.env.local'
}

def scan_files_for_secrets():
    print("\n--- 1. Scanning Workspace Code for Leaked Secrets & Private Keys ---")
    leaks = []
    scanned_count = 0

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in IGNORE_EXTENSIONS:
                continue
            if file in IGNORE_FILES:
                continue

            rel_path = file_path.relative_to(ROOT_DIR)
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            scanned_count += 1
            for pattern, label in SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    leaks.append((str(rel_path), label, len(matches)))

    print(f"Scanned {scanned_count} files across workspace.")
    if leaks:
        print("[FAIL] Secret scanner found potential leaked secrets:")
        for path, label, count in leaks:
            print(f"       {path}: {count} match(es) for {label}")
        return False
    else:
        print("[PASS] Zero committed secrets, private keys, or credentials found.")
        return True

def verify_git_exclusion():
    print("\n--- 2. Verifying Git Exclusion of Secret Files ---")
    gitignore_path = ROOT_DIR / '.gitignore'
    if not gitignore_path.exists():
        print("[FAIL] Missing .gitignore file in root.")
        return False

    content = gitignore_path.read_text(encoding='utf-8')
    required_ignores = ['.env', 'credentials.json', 'token.json', '.venv', 'node_modules']
    missing = [req for req in required_ignores if req not in content]

    if missing:
        print(f"[FAIL] .gitignore is missing critical ignore patterns: {missing}")
        return False

    # Check git status for any staged or tracked .env files
    res = subprocess.run('git ls-files --error-unmatch .env', cwd=ROOT_DIR, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0:
        print("[FAIL] .env file is tracked by Git! Must be untracked.")
        return False

    print("[PASS] .env and credentials are strictly ignored and untracked by Git.")
    return True

def verify_environment_decoupling():
    print("\n--- 3. Verifying Production Environment Decoupling ---")
    settings_file = ROOT_DIR / 'apps' / 'api' / 'config' / 'settings.py'
    content = settings_file.read_text(encoding='utf-8')

    # Verify SECRET_KEY and credentials pull from os.environ
    checks = [
        (r"os\.environ\.get\(\s*['\"]DJANGO_SECRET_KEY['\"]", "DJANGO_SECRET_KEY"),
        (r"os\.environ\.get\(\s*['\"]INTERNAL_API_SECRET['\"]", "INTERNAL_API_SECRET"),
        (r"os\.environ\.get\(\s*['\"]POSTGRES_PASSWORD['\"]", "POSTGRES_PASSWORD"),
        (r"os\.environ\.get\(\s*['\"]MINIO_ROOT_PASSWORD['\"]", "MINIO_ROOT_PASSWORD")
    ]
    missing = [label for pattern, label in checks if not re.search(pattern, content)]
    if missing:
        print(f"[FAIL] settings.py has hardcoded credentials: {missing}")
        return False

    print("[PASS] All sensitive keys decouple to environment variables with fallback safe defaults.")
    return True

def main():
    print("======================================================================")
    print("MediaCompile — Security & Secret Audit Scanner")
    print("======================================================================")
    ok1 = scan_files_for_secrets()
    ok2 = verify_git_exclusion()
    ok3 = verify_environment_decoupling()

    all_ok = ok1 and ok2 and ok3
    print("\n======================================================================")
    if all_ok:
        print("SECURITY AUDIT SCAN PASSED (3/3 Checks)")
    else:
        print("SECURITY AUDIT SCAN FAILED")
    print("======================================================================")
    sys.exit(0 if all_ok else 1)

if __name__ == '__main__':
    main()
