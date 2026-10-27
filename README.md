# MediaCompile

MediaCompile is a secure digital content library and personalized AI retrieval-augmented generation (RAG) platform. It aggregates permitted social media posts, URLs, notes, and documents into a private, indexed repository and provides an AI assistant grounded strictly in your own saved content.

---

## Architecture Overview

MediaCompile follows a hybrid local architecture:
- **Docker Compose**: Used **only** for external infrastructure:
  - **PostgreSQL 16 with pgvector** (`127.0.0.1:5432`)
  - **Redis 7** (`127.0.0.1:6379`)
  - **MinIO S3 Storage** (`127.0.0.1:9000` API, `127.0.0.1:9001` Console)
- **Windows Host**: All application components run directly on Windows:
  - **Next.js App Router** (Frontend with Auth.js)
  - **Django REST Framework** (Authoritative API backend)
  - **Celery Worker** (Asynchronous background worker with `-P solo`)
  - **Tests & Migrations**

Detailed architecture documentation is available in [docs/architecture.md](docs/architecture.md).  
The phased delivery roadmap is available in [docs/phase-plan.md](docs/phase-plan.md).  
The infrastructure operations manual is available in [docs/infrastructure.md](docs/infrastructure.md).

---

## Quickstart (Windows PowerShell)

### Prerequisites
- **Git** (>= 2.40)
- **Node.js** (>= 20.x, tested on v22.23.3)
- **Python** (>= 3.11, tested on 3.14.3)
- **Docker Desktop** (with Docker Compose v2+)

### Step 1: Configure Environment
```powershell
Copy-Item .env.example .env
```

### Step 2: Start Infrastructure
```powershell
docker compose up -d
```

### Step 3: Verify Infrastructure
```powershell
python execution/verify_phase_1.py
```

### Step 4: Access Services
- **MinIO Console**: [http://127.0.0.1:9001](http://127.0.0.1:9001) (Credentials: `minioadmin` / `minioadmin`)
- **MinIO S3 API**: [http://127.0.0.1:9000](http://127.0.0.1:9000)
- **PostgreSQL 16**: `127.0.0.1:5432`, DB: `mediacompile`, User: `postgres`, Pass: `postgres`
- **Redis 7**: `127.0.0.1:6379`

---

## Current Status

- **Phase 0 (Repository Audit & Plan)**: **PASS**
- **Phase 1 (Local Infrastructure with Docker)**: **PASS**
- **Phase 2 (Authentication & Backend Foundation)**: **PASS**
- **Phase 3 (Frontend Application Shell)**: **PASS**
- **Phase 4 (Content Ingestion & Personal Library)**: **PASS**
- **Phase 5 (Search, Embeddings & Vector Retrieval)**: **PASS**
- **Phase 6 (Grounded AI Chat & Citations)**: **PASS**
- **Phase 7 (Personalization & User-Controlled Memory)**: **PASS**
- **Phase 8 (Social and External Integrations)**: **PASS**
- **Phase 9 (Workspaces, Timeline, Sovereign Backup & Browser Extension)**: **PASS**
- **Phase 10 (Security Hardening, Audit & Reliability)**: **PASS**
- **Phase 11 (Quality, CI/CD & Release Readiness)**: **PASS**
- **Phase 12 (Production Deployment Strategy)**: **PASS** (100% Master Plan Complete)

### Step 5: Verify Authentication & Backend Foundation
```powershell
python execution/verify_phase_2.py
```
- Tests backend pytest suite (15/15 tests passing across User models, Argon2id hashing, Identity Bridge, and cross-tenant data isolation).
- Tests Next.js production build (`npm run build`) with App Router and Auth.js routes.
- Tests end-to-end Identity Bridge authentication handoff from Node.js signed JWT to Django REST Framework API.

### Step 6: Verify Frontend Application Shell
```powershell
python execution/verify_phase_3.py
```
- Tests Next.js 16 production build compilation across all 10 application routes with Turbopack.
- Tests live HTTP runtime responses and DOM content assertions across `/`, `/login`, `/register`, `/dashboard`, `/library`, `/search`, `/chat`, `/collections`, `/integrations`, and `/settings`.
- Tests zero regression across the backend test suite (15/15 tests passing).

### Step 7: Verify Content Ingestion & Personal Library
```powershell
python execution/verify_phase_4.py
```
- Tests SSRF defense boundary (rejection of loopback, RFC 1918 private subnets, cloud metadata endpoints, prohibited schemes, and non-whitelisted ports).
- Tests text extraction and sliding-window chunking engine with offset tracking (`start_offset`, `end_offset`).
- Tests MinIO S3 object storage integration (user-scoped byte-level upload, download, and pre-signed URL generation).
- Tests live DRF ingestion endpoints (`/api/v1/content/notes/`, `/urls/`, `/files/`) with automatic chunking and strict cross-tenant isolation enforcement (HTTP 404 on foreign items).
- Tests full backend pytest suite (29/29 tests passing with 100% pass rate).
- Tests Next.js App Router zero-regression production build.

### Step 8: Verify Search, Embeddings & Vector Retrieval
```powershell
python execution/verify_phase_5.py
```
- Tests provider-neutral embedding interface with 1536-dimensional unit vectors and deterministic cosine similarity.
- Tests pgvector HNSW indexing and `CosineDistance` nearest-neighbor semantic search directly on PostgreSQL.
- Tests PostgreSQL multi-term lexical token and full-text search across titles, summaries, chunk text, and tags.
- Tests hybrid retrieval with Reciprocal Rank Fusion (RRF $k=60$) combining lexical and vector ranking signals.
- Tests strict multi-tenant isolation (foreign user content never leaked or retrievable).
- Tests live DRF Search REST API (`GET /api/v1/content/search/?q=...&mode=hybrid`) with Identity Bridge authentication and HTTP 401 unauthenticated protection.
- Tests full backend pytest suite (44/44 tests passing with 100% pass rate).
- Tests Next.js App Router production build with enhanced `/search` interface.

### Step 9: Verify Grounded AI Chat (RAG) & Citations
```powershell
python execution/verify_phase_6.py
```
- Tests grounded RAG response generation with authoritative `[Source N]` bracketed citations.
- Tests structured citation mapping linking every claim to ContentChunk UUIDs and character offsets `[start_offset:end_offset]`.
- Tests explicit uncertainty fallback: queries lacking library evidence reliably trigger admission of insufficient facts without hallucinating.
- Tests AI safety and prompt injection defense: untrusted document text is treated strictly as inert reference data and cannot override system policy.
- Tests multi-tenant isolation and session privacy: User B cannot access or post to User A's session (HTTP 404), and foreign secrets never enter the retrieval context.
- Tests live DRF Chat API (`POST /api/v1/chat/sessions/{id}/messages/`) and Server-Sent Events (SSE) streaming (`GET /api/v1/chat/sessions/{id}/stream/`).
- Tests full backend pytest suite (51/51 tests passing with 100% pass rate).
- Tests Next.js App Router production build with enhanced `/chat` interface.

### Step 10: Verify Personalization & User-Controlled Memory
```powershell
python execution/verify_phase_7.py
```
- Tests user memory sovereignty: create, update, toggle active status, and permanently delete explicit preferences (`UserMemory`).
- Tests sensitive trait rejection (AI safety): rejects sensitive categories and keywords relating to health, religion, politics, sexuality, and financial credentials.
- Tests personalization opt-out: verifies that toggling `personalization_enabled=False` completely bypasses memory injection in grounded prompts and live chat.
- Tests inactive and deleted memory exclusion: verifies inactive (`is_active=False`) and deleted memory items never leak into prompts.
- Tests multi-tenant privacy isolation: verifies complete separation between distinct users with 404 enforcement on unauthorized access.
- Tests live DRF endpoints (`GET`/`PATCH /api/v1/chat/preferences/`, CRUD `/api/v1/chat/memories/`, `GET /api/v1/chat/topics/`).
- Tests full backend pytest suite (63/63 tests passing with 100% pass rate).
- Tests Next.js App Router production build with enhanced `/settings` memory management and topic summary dashboards.

### Step 11: Verify Social & External Integrations
```powershell
python execution/verify_phase_8.py
```
- Tests OAuth token encryption at rest using Fernet symmetrical encryption (`ConnectedAccount`, `crypto.py`) and log/API credential masking.
- Tests browser bookmarks import: Netscape HTML and JSON export parsing with SSRF defense (blocking internal IPs/loopback) and deduplication.
- Tests YouTube connector: OAuth read capability (`youtube.readonly`), metadata normalization (channel, tags, published date), Google Takeout export parser, and token expiry handling.
- Tests Reddit connector: OAuth read integration (`identity,read,history`), subreddit tagging, and GDPR CSV/JSON export parser.
- Tests Celery background synchronization worker task (`sync_account_task`).
- Tests multi-tenant privacy isolation (User B cannot view, sync, or disconnect User A's connected account, returning HTTP 404).
- Tests live DRF Integrations API (`GET /api/v1/integrations/`, `POST .../connect/`, `POST .../sync/`, `POST .../disconnect/`, and file imports).
- Tests full backend pytest suite (77/77 tests passing with 100% pass rate).
- Tests Next.js App Router production build with enhanced `/integrations` dashboard, connect modals, and archive uploaders.

### Step 12: Verify Workspaces, Timeline, Sovereign Backup & Browser Extension
```powershell
python execution/verify_phase_9.py
```
- Tests browser extension web clip endpoint (`POST /api/v1/content/clip/`) with SSRF defense and deduplication.
- Tests sovereign library export (`export_user_library`) generating full JSON archives with complete multi-tenant privacy.
- Tests idempotent bulk restoration (`import_user_library`) and file upload parsing.
- Tests chronological library timeline grouping (`get_user_timeline`) and pgvector cosine distance related content recommendations.
- Tests grounded topic workspace inquiry question generation.
- Tests SavedSearch model CRUD and tenant isolation.
- Tests Chrome Manifest V3 extension compliance, minimal permissions (`activeTab`, `storage`), and popup assets.
- Tests full backend pytest suite (86/86 tests passing with 100% pass rate).
- Tests Next.js production build compiling all 15 routes including `/workspace` with Turbopack.

### Step 13: Verify Security Hardening, Audit & Reliability
```powershell
python execution/verify_phase_10.py
```
- Tests OWASP security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy`).
- Tests complete 10-resource multi-tenant authorization matrix (User B strictly denied access to User A's items, chunks, collections, tags, searches, chat, messages, memories, preferences, and connected accounts).
- Tests permanent GDPR account erasure (`DELETE /api/v1/users/me/`) with full cascading deletion.
- Tests scoped rate limiting throttles protecting search (180/m), ingestion (120/m), chat (60/m), export/import (20/m).
- Tests security audit event logging with token/credential redaction.
- Tests secret scanner (`scan_secrets_and_deps.py`) across 195 workspace files with 0 committed secrets or untracked `.env` files.
- Tests multi-service health monitoring (`/api/v1/health/`) testing PostgreSQL, Redis, and MinIO storage.
- Tests full backend pytest suite (92/92 tests passing with 100% pass rate).
- Tests Next.js production build compiling all 15 routes cleanly.

### Step 14: Verify Quality, CI/CD & Release Readiness
```powershell
python execution/verify_phase_11.py
```
- Tests CI/CD workflow configuration (`.github/workflows/ci.yml`) validating backend pytest, secret scan, and Turbopack build across service containers.
- Tests architecture & engineering documentation completeness (all 8 core documentation guides present and detailed).
- Tests automated secret & credential audit scan across workspace code with 0 leaks.
- Tests deterministic seed data generator (`execution/seed_data.py`) populating clean demo library.
- Tests full backend pytest suite (92/92 tests passing with 100% pass rate).
- Tests Next.js App Router production build compiling all 15 routes cleanly.
- Emits release-readiness report confirming system is ready for Phase 12 production deployment.

### Step 15: Verify Production Deployment Strategy
```powershell
python execution/verify_phase_12.py
```
- Tests multi-stage Dockerfiles (`deploy/Dockerfile.api` and `deploy/Dockerfile.web`) with non-root least-privilege security and healthcheck probes.
- Tests production Docker Compose stack (`deploy/docker-compose.prod.yml`) orchestrating Nginx reverse proxy, Web, API, Celery worker, Celery beat, PostgreSQL 16 + pgvector, Redis 7, and MinIO storage with DMZ network isolation and resource limits.
- Tests production Nginx reverse proxy configuration (`deploy/nginx/nginx.conf`) enforcing TLS 1.3, HTTP/2, HSTS, CSP, and unbuffered SSE chat streaming.
- Tests production entrypoint script (`deploy/entrypoint.sh`) validating database connectivity retry loops, automated migrations, and static collection.
- Tests production environment template (`deploy/.env.production.example`) covering all 12 security categories.
- Tests architectural deployment runbook (`docs/deployment.md`) detailing hosting options, zero-downtime rolling restart sequences, daily encrypted backups, and rollback procedures.
- Tests automated database backup and restore drill simulation verifying database dump integrity and pgvector extension.
- Tests full backend pytest suite (92/92 tests passing with 100% pass rate).
- Tests Next.js 16 frontend build (15/15 routes cleanly compiled with Turbopack).

