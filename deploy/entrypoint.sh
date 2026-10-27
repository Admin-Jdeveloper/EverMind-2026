#!/usr/bin/env bash
# ==============================================================================
# MediaCompile Production Entrypoint Script
# Handles database readiness checks, migrations, and static asset collection
# ==============================================================================

set -o errexit
set -o pipefail
set -o nounset

echo "[entrypoint] Starting MediaCompile API container initialization..."

# ------------------------------------------------------------------------------
# 1. Database Readiness Check
# ------------------------------------------------------------------------------
DATABASE_HOST="${POSTGRES_HOST:-db}"
DATABASE_PORT="${POSTGRES_PORT:-5432}"
DATABASE_WAIT_TIMEOUT="${DATABASE_WAIT_TIMEOUT:-60}"

echo "[entrypoint] Waiting for database at ${DATABASE_HOST}:${DATABASE_PORT} (timeout: ${DATABASE_WAIT_TIMEOUT}s)..."

count=0
until python -c "
import sys, socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('${DATABASE_HOST}', int('${DATABASE_PORT}')))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" > /dev/null 2>&1; do
    count=$((count + 1))
    if [ "$count" -ge "$DATABASE_WAIT_TIMEOUT" ]; then
        echo "[entrypoint] ERROR: Database connection timed out after ${DATABASE_WAIT_TIMEOUT} seconds."
        exit 1
    fi
    echo "[entrypoint] Waiting for database connection... ($count/${DATABASE_WAIT_TIMEOUT})"
    sleep 1
done

echo "[entrypoint] Database TCP socket is reachable. Validating Django ORM connection..."
python manage.py check --database default > /dev/null 2>&1 || {
    echo "[entrypoint] WARNING: Django ORM check failed. Retrying in 3s..."
    sleep 3
    python manage.py check --database default
}
echo "[entrypoint] Database connection verified successfully."

# ------------------------------------------------------------------------------
# 2. Database Migrations (Run if enabled)
# ------------------------------------------------------------------------------
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "[entrypoint] Executing database migrations..."
    python manage.py migrate --noinput
    echo "[entrypoint] Migrations completed successfully."
else
    echo "[entrypoint] Skipping database migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

# ------------------------------------------------------------------------------
# 3. Static Assets Collection (Run if enabled)
# ------------------------------------------------------------------------------
COLLECT_STATIC="${COLLECT_STATIC:-true}"
if [ "$COLLECT_STATIC" = "true" ] || [ "$COLLECT_STATIC" = "1" ]; then
    echo "[entrypoint] Collecting static assets..."
    python manage.py collectstatic --noinput
    echo "[entrypoint] Static assets collected successfully."
else
    echo "[entrypoint] Skipping static asset collection (COLLECT_STATIC=${COLLECT_STATIC})."
fi

# ------------------------------------------------------------------------------
# 4. Execute Main Process
# ------------------------------------------------------------------------------
echo "[entrypoint] Launching main application process: $@"
exec "$@"
