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

        # 3. MinIO S3 Storage Check
        try:
            from content.storage import get_s3_client
            from django.conf import settings
            s3 = get_s3_client()
            s3.head_bucket(Bucket=settings.MINIO_BUCKET_NAME)
            health_status["checks"]["storage"] = "ok"
        except Exception:
            health_status["checks"]["storage"] = "error"
            is_healthy = False

        if not is_healthy:
            health_status["status"] = "unhealthy"
            return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(health_status, status=status.HTTP_200_OK)
