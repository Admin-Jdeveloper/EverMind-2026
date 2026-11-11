# MediaCompile

MediaCompile is a secure digital content library and personalized AI retrieval-augmented generation (RAG) platform. It aggregates permitted social media posts, URLs, notes, and documents into a private, indexed repository and provides an AI assistant grounded in your saved content.

---

## Architecture Overview

MediaCompile supports both hybrid local development and full Docker Compose production deployments:

- **Infrastructure Services (`docker-compose.yml`)**:
  - **PostgreSQL 16 with pgvector** (`127.0.0.1:5432`)
  - **Redis 7** (`127.0.0.1:6379`)
  - **MinIO S3 Storage** (`127.0.0.1:9000` API, `127.0.0.1:9001` Console)
- **Application Services**:
  - **Next.js App Router (`apps/web`)**: Frontend UI and Auth.js session boundary
  - **Django REST Framework (`apps/api`)**: Authoritative API backend, hybrid search, and grounded RAG engine
  - **Celery Worker (`apps/api`)**: Asynchronous document, URL, and YouTube ingestion pipeline
  - **Browser Extension (`apps/extension`)**: Chrome Manifest V3 web clipper

Detailed documentation is available in:
- [docs/architecture.md](docs/architecture.md) — System architecture & trust boundaries
- [docs/infrastructure.md](docs/infrastructure.md) — Local infrastructure operations
- [docs/api-conventions.md](docs/api-conventions.md) — REST API conventions & endpoint catalog
- [docs/testing.md](docs/testing.md) — Automated test suites & verification
- [docs/runbook.md](docs/runbook.md) — Local development & operational runbook
- [docs/deployment.md](docs/deployment.md) — Production deployment & disaster recovery
- [docs/threat-model.md](docs/threat-model.md) — Security threat model & STRIDE analysis

---

## Quickstart (Windows PowerShell)

### Prerequisites
- **Git** (>= 2.40)
- **Node.js** (>= 20.x)
- **Python** (>= 3.11)
- **Docker Desktop** (with Docker Compose v2+)

### 1. Configure Environment
```powershell
Copy-Item .env.example .env
```

### 2. Start Infrastructure Services
```powershell
docker compose up -d
```

### 3. Set Up Backend & Run Migrations
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements.txt
python apps/api/manage.py migrate
```

### 4. Start Application Services
```powershell
# Start Django API (Port 8000)
.\.venv\Scripts\python.exe apps/api/manage.py runserver 127.0.0.1:8000

# Start Celery Worker (Windows solo pool)
.\.venv\Scripts\python.exe -m celery --workdir apps/api -A config worker -l INFO -P solo

# Start Next.js Web App (Port 3000)
npm install
npm run dev
```

### 5. Access Local Services
- **Web Application**: `http://localhost:3000`
- **Django REST API Health**: `http://127.0.0.1:8000/api/v1/health/`
- **MinIO Console**: `http://127.0.0.1:9001` (Default credentials: `minioadmin` / `minioadmin`)
- **PostgreSQL 16**: `127.0.0.1:5432` (`mediacompile`)
- **Redis 7**: `127.0.0.1:6379`

---

## Testing & Verification

```powershell
# Run Backend Test Suite
.\.venv\Scripts\python.exe -m pytest apps/api/tests/ -q

# Run Frontend Lint & Production Build
npm run lint
npm run build

# Run Security & Secret Audit Scanner
.\.venv\Scripts\python.exe execution/scan_secrets_and_deps.py
```
