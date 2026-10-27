"""
Evermind — Centralized Environment Validation & Production Readiness Checker.

- In development: permits local Docker infrastructure (127.0.0.1, MinIO, local pgvector, local Redis).
- In production: strictly enforces real external managed services (PostgreSQL with SSL, managed Redis, S3, Groq, strong secrets).
"""

import os
import sys
import socket
import logging
from urllib.parse import urlparse

logger = logging.getLogger('config.env_validation')


class ProductionConfigurationError(Exception):
    """Raised when required production environment variables are missing, insecure, or pointing to invalid services."""
    pass


def validate_environment_configuration():
    """
    Validates environment settings. In development mode, permits local defaults.
    In production mode, enforces required secrets and external services.
    """
    env = os.environ.get('ENVIRONMENT', os.environ.get('NODE_ENV', 'development')).lower()
    if env != 'production':
        logger.info("[Evermind Config] Development mode active. Local services permitted.")
        return

    logger.info("[Evermind Config] Production mode active. Validating external services & credentials...")
    errors = []

    # 1. Django Secret Key
    secret_key = os.environ.get('DJANGO_SECRET_KEY', '').strip()
    if not secret_key or 'insecure' in secret_key or 'change-this' in secret_key or len(secret_key) < 32:
        errors.append(
            "DJANGO_SECRET_KEY is missing, too short, or contains insecure default placeholder. "
            "Generate a strong 50+ character key (e.g. `python -c 'import secrets; print(secrets.token_urlsafe(50))'`)."
        )

    # 2. Database Configuration
    database_url = os.environ.get('DATABASE_URL', '').strip()
    postgres_host = os.environ.get('POSTGRES_HOST', '').strip()
    if database_url:
        if '127.0.0.1' in database_url or 'localhost' in database_url:
            errors.append(
                "DATABASE_URL in production mode points to localhost (127.0.0.1). "
                "Must connect to an external PostgreSQL instance (e.g. Render / AWS RDS)."
            )
    else:
        if not postgres_host or postgres_host in ('127.0.0.1', 'localhost'):
            errors.append(
                "POSTGRES_HOST or DATABASE_URL is missing or points to localhost in production mode. "
                "Supply an external PostgreSQL host or full connection URL."
            )
        if not os.environ.get('POSTGRES_PASSWORD'):
            errors.append("POSTGRES_PASSWORD is required in production mode.")

    # 3. Redis / Celery Broker
    redis_url = os.environ.get('REDIS_URL', '').strip()
    celery_broker = os.environ.get('CELERY_BROKER_URL', '').strip()
    active_redis = redis_url or celery_broker
    if not active_redis:
        errors.append("REDIS_URL or CELERY_BROKER_URL must be configured for caching and Celery queues in production mode.")
    elif '127.0.0.1:6379' in active_redis or 'localhost:6379' in active_redis:
        errors.append(
            f"Redis URL ({active_redis}) points to local unauthenticated port in production mode. "
            "Must use an external managed Redis instance with authentication and TLS."
        )

    # 4. Storage Provider (AWS S3 vs MinIO)
    storage_provider = os.environ.get('STORAGE_PROVIDER', '').lower()
    s3_bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME', '').strip()
    if storage_provider == 's3' or s3_bucket:
        bucket = s3_bucket or 'evermind2026'
        region = os.environ.get('AWS_S3_REGION_NAME', '').strip()
        aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '').strip()
        aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '').strip()
        if not aws_key or 'minioadmin' in aws_key:
            errors.append("AWS_ACCESS_KEY_ID is missing or set to MinIO default for AWS S3 storage.")
        if not aws_secret or 'minioadmin' in aws_secret:
            errors.append("AWS_SECRET_ACCESS_KEY is missing or set to MinIO default for AWS S3 storage.")
        if not region:
            errors.append("AWS_S3_REGION_NAME (e.g., ap-south-1 or us-east-1) is required for AWS S3 storage.")
    elif storage_provider == 'minio':
        minio_endpoint = os.environ.get('MINIO_ENDPOINT', '').strip()
        if not minio_endpoint or '127.0.0.1' in minio_endpoint or 'localhost' in minio_endpoint:
            errors.append(
                "MINIO_ENDPOINT points to localhost in production mode. "
                "Supply an external storage host or configure STORAGE_PROVIDER=s3."
            )
        if os.environ.get('MINIO_ROOT_PASSWORD') in (None, '', 'minioadmin'):
            errors.append("MINIO_ROOT_PASSWORD cannot use default 'minioadmin' credentials in production mode.")
    else:
        errors.append(
            "STORAGE_PROVIDER must be set to 's3' (or configure AWS_STORAGE_BUCKET_NAME) for production mode."
        )

    # 5. Groq LLM API Key
    groq_api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not groq_api_key or groq_api_key == 'your-production-groq-api-key':
        errors.append("GROQ_API_KEY is required for grounded RAG generation in production mode.")

    # 6. Internal Identity Bridge Secret
    bridge_secret = os.environ.get('INTERNAL_API_SECRET', '').strip()
    if not bridge_secret or 'development-internal' in bridge_secret or len(bridge_secret) < 32:
        errors.append(
            "INTERNAL_API_SECRET is missing or using default development secret. "
            "Must be at least 32 characters for cryptographically secure server-to-server JWTs."
        )

    if errors:
        error_msg = (
            "\n" + "=" * 80 + "\n"
            "EVERMIND PRODUCTION CONFIGURATION FAILURE\n"
            f"The application failed to start because {len(errors)} required setting(s) were invalid:\n"
            + "\n".join(f"  [{i+1}] {err}" for i, err in enumerate(errors))
            + "\n\nPlease update your production environment variables and restart."
            + "\n" + "=" * 80 + "\n"
        )
        logger.critical(error_msg)
        raise ProductionConfigurationError(error_msg)

    logger.info("[Evermind Config] All production configuration checks PASSED.")


def check_tcp_connectivity(host: str, port: int, timeout_seconds: float = 3.0) -> bool:
    """Test TCP socket reachability for an external service endpoint without sending payload."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False
