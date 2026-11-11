import os
from django.core.cache import cache
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """
    Health check endpoint returning readiness of Django, PostgreSQL, Redis, and object storage.
    Accessible without authentication for infrastructure monitoring.
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

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            health_status["checks"]["database"] = "ok"
        except Exception:
            health_status["checks"]["database"] = "error"
            is_healthy = False

        try:
            cache.set("_health_check_ping", "pong", timeout=10)
            val = cache.get("_health_check_ping")
            if val == "pong":
                health_status["checks"]["cache"] = "ok"
            else:
                health_status["checks"]["cache"] = "error"
                is_healthy = False
        except Exception:
            health_status["checks"]["cache"] = "error"
            is_healthy = False

        try:
            from content.storage import get_s3_client, get_active_bucket_name
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
