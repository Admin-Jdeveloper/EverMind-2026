# MediaCompile

MediaCompile is a personal content library and retrieval-augmented generation (RAG) system. It ingests web pages, notes, documents (PDF, DOCX, XLSX, PPTX, TXT), and video transcripts into a single workspace, indexes them using hybrid search (lexical search + vector embeddings), and provides an AI chat assistant grounded strictly in your saved material with cited sources.

---

## Features

- **Multi-Source Ingestion**: Ingests URLs, direct notes, document uploads, and YouTube transcripts with automated text extraction and chunking.
- **Hybrid Retrieval**: Combines PostgreSQL full-text search with pgvector semantic similarity via Reciprocal Rank Fusion (RRF).
- **Grounded AI Chat**: Answers queries using retrieved library context, citing specific documents, pages, and chunks.
- **Data Isolation**: Strict per-user multi-tenant separation across all database queries, vectors, and object storage.
- **Chrome Extension**: Manifest V3 extension for clipping web content directly to your personal library.

---

## Tech Stack

- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, Auth.js
- **Backend API**: Django, Django REST Framework, Celery
- **Database & Storage**: PostgreSQL 16 with pgvector, Redis 7, MinIO (S3-compatible object storage)
- **Embeddings & LLM**: Local sentence transformers (`all-MiniLM-L6-v2`) via ONNX Runtime / Groq API (`openai/gpt-oss-120b`)

---

## Quickstart

### Prerequisites
- Git
- Node.js (>= 20)
- Python (>= 3.11)
- Docker Desktop

### 1. Environment Setup
```powershell
Copy-Item .env.example .env
```

### 2. Start Infrastructure
```powershell
docker compose up -d
```

### 3. Backend Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements.txt
python apps/api/manage.py migrate
```

### 4. Run Services
```powershell
# Django API (Port 8000)
.\.venv\Scripts\python.exe apps/api/manage.py runserver 127.0.0.1:8000

# Celery Worker
.\.venv\Scripts\python.exe -m celery --workdir apps/api -A config worker -l INFO -P solo

# Next.js Web App (Port 3000)
npm install
npm run dev
```

### 5. Service Endpoints
- **Web UI**: `http://localhost:3000`
- **REST API**: `http://127.0.0.1:8000/api/v1/`
- **Health Check**: `http://127.0.0.1:8000/api/v1/health/`
- **MinIO Console**: `http://127.0.0.1:9001` (`minioadmin` / `minioadmin`)

---

## Tests

```powershell
# Backend pytest suite
.\.venv\Scripts\python.exe -m pytest apps/api/tests/ -q

# Frontend lint & build
npm run lint
npm run build
```
