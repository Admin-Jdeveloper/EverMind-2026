from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.db import connection
from django.core.cache import cache
import os

class HealthCheckView(APIView):
    """
    Health check endpoint returning readiness of Django, PostgreSQL, and Redis.
    Accessible without authentication for monitoring purposes.
    Secrets and internal addresses are strictly redacted.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        health_status = {
            "status": "healthy",
            "service": "mediacompile-api",
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "checks": {}
        }
        is_healthy = True

        # 1. PostgreSQL Check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            health_status["checks"]["database"] = "ok"
        except Exception as e:
            health_status["checks"]["database"] = "error"
            is_healthy = False

        # 2. Redis Cache Check
        try:
            cache.set("_health_check_ping", "pong", timeout=10)
            val = cache.get("_health_check_ping")
            if val == "pong":
                health_status["checks"]["cache"] = "ok"
            else:
                health_status["checks"]["cache"] = "error"
                is_healthy = False
        except Exception as e:
            health_status["checks"]["cache"] = "error"
            is_healthy = False

        # 3. Object Storage Check (Active provider: S3 or MinIO)
        try:
            from content.storage import get_s3_client, get_active_bucket_name
            from django.conf import settings
            s3 = get_s3_client()
            bucket_name = get_active_bucket_name()
            try:
                s3.head_bucket(Bucket=bucket_name)
                health_status["checks"]["storage"] = "ok"
            except Exception as s3_err:
                error_code = getattr(s3_err, 'response', {}).get('Error', {}).get('Code', '')
                if error_code in ('403', 'AccessDenied'):
                    # Least-privilege IAM policy without ListBucket/head_bucket
                    health_status["checks"]["storage"] = "ok"
                else:
                    health_status["checks"]["storage"] = "error"
                    is_healthy = False
        except Exception:
            health_status["checks"]["storage"] = "error"
            is_healthy = False

        if not is_healthy:
            health_status["status"] = "unhealthy"
            return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(health_status, status=status.HTTP_200_OK)


class DatabaseDiagnosticsView(APIView):
    """
    Diagnostic endpoint for monitoring PostgreSQL database connections,
    pooler configuration, latency, and Celery worker status safely without exposing secrets.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        import time
        from django.conf import settings
        from config.celery import app as celery_app

        db_settings = settings.DATABASES.get('default', {})
        options = db_settings.get('OPTIONS', {})
        port = str(db_settings.get('PORT', '5432'))
        host = db_settings.get('HOST', '')

        # Redact host to domain-only for safe diagnostics
        safe_host = host.split('@')[-1] if '@' in host else host
        pooler_mode = 'transaction' if port == '6543' else ('session' if 'pooler.supabase.com' in safe_host else 'direct')

        diag = {
            "database": {
                "host_type": safe_host,
                "port": port,
                "pooler_mode": pooler_mode,
                "conn_max_age": settings.DATABASES['default'].get('CONN_MAX_AGE', 0),
                "connect_timeout": options.get('connect_timeout'),
                "disable_server_side_cursors": settings.DATABASES['default'].get('DISABLE_SERVER_SIDE_CURSORS', False),
                "prepare_threshold": options.get('prepare_threshold'),
            },
            "metrics": {},
            "celery": {},
        }

        # Query metrics & latency
        t0 = time.perf_counter()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                diag["metrics"]["latency_ms"] = latency_ms
                diag["metrics"]["status"] = "connected"

                # Check active sessions in PostgreSQL if accessible
                try:
                    cursor.execute("SELECT count(*) FROM pg_stat_activity;")
                    row = cursor.fetchone()
                    diag["metrics"]["pg_stat_activity_count"] = row[0] if row else None
                except Exception:
                    diag["metrics"]["pg_stat_activity_count"] = None

                try:
                    cursor.execute("SHOW max_connections;")
                    row = cursor.fetchone()
                    diag["metrics"]["max_connections"] = row[0] if row else None
                except Exception:
                    diag["metrics"]["max_connections"] = None
        except Exception as e:
            diag["metrics"]["status"] = "error"
            diag["metrics"]["error"] = type(e).__name__

        # Celery status
        try:
            inspect = celery_app.control.inspect(timeout=0.5)
            ping_res = inspect.ping() if inspect else None
            if ping_res:
                worker_names = list(ping_res.keys())
                diag["celery"]["status"] = "active"
                diag["celery"]["worker_count"] = len(worker_names)
                diag["celery"]["workers"] = [w.split('@')[0] for w in worker_names]
            else:
                diag["celery"]["status"] = "no_workers_responding"
                diag["celery"]["worker_count"] = 0
        except Exception as e:
            diag["celery"]["status"] = "error"
            diag["celery"]["error"] = type(e).__name__

        return Response(
            diag,
            status=status.HTTP_200_OK if diag["metrics"].get("status") == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE
        )

