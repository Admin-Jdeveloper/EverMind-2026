"""
Evermind — Object Storage Service (AWS S3 & MinIO).

Supports two operating modes:
1. Development: Local MinIO S3 object storage on Docker bridge network.
2. Production: Amazon S3 (e.g. bucket 'evermind2026' in region 'ap-south-1')
   with restricted IAM credentials and time-limited pre-signed download URLs.

Enforces multi-tenant path isolation and directory traversal sanitization.
"""

import os
import re
import uuid
import logging
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger('content.storage')


class StorageServiceError(Exception):
    """Base exception for object storage operations."""
    pass

class StorageAuthenticationError(StorageServiceError):
    """Raised when S3 credentials or signature validation fails."""
    pass

class StorageUploadError(StorageServiceError):
    """Raised when an object upload to storage fails."""
    pass


def get_active_bucket_name() -> str:
    """Return the configured bucket name based on the active storage provider."""
    provider = getattr(settings, 'STORAGE_PROVIDER', 'minio').lower()
    if provider == 's3':
        return getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'evermind2026')
    return getattr(settings, 'MINIO_BUCKET_NAME', 'mediacompile-uploads')


def get_s3_client():
    """
    Create a configured boto3 S3 client.
    - When STORAGE_PROVIDER is 's3': connects to AWS S3 using IAM credentials & region.
    - When STORAGE_PROVIDER is 'minio': connects to local/Docker MinIO endpoint.
    """
    provider = getattr(settings, 'STORAGE_PROVIDER', 'minio').lower()

    if provider == 's3':
        region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
        client_kwargs = {
            'service_name': 's3',
            'region_name': region,
            'config': Config(signature_version='s3v4', region_name=region),
        }
        aws_access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', '').strip()
        aws_secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', '').strip()
        if aws_access_key and aws_secret_key:
            client_kwargs['aws_access_key_id'] = aws_access_key
            client_kwargs['aws_secret_access_key'] = aws_secret_key

        endpoint_override = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_override and endpoint_override.strip():
            client_kwargs['endpoint_url'] = endpoint_override.strip()

        return boto3.client(**client_kwargs)

    # Local / Docker MinIO
    scheme = "https" if getattr(settings, 'MINIO_USE_SSL', False) else "http"
    endpoint_url = f"{scheme}://{settings.MINIO_ENDPOINT}"
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )


def ensure_bucket_exists():
    """
    Verify that the configured storage bucket is reachable.
    Creates local MinIO bucket if missing; verifies AWS S3 bucket without requiring admin create rights.
    Under least-privilege IAM policies, head_bucket 403 (Forbidden) is non-fatal.
    """
    provider = getattr(settings, 'STORAGE_PROVIDER', 'minio').lower()
    client = get_s3_client()
    bucket_name = get_active_bucket_name()

    try:
        client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        error_code = str(e.response.get('Error', {}).get('Code', ''))
        if provider == 'minio' or error_code in ('404', 'NoSuchBucket'):
            try:
                client.create_bucket(Bucket=bucket_name)
                logger.info(f"Created storage bucket '{bucket_name}'.")
            except Exception as create_err:
                logger.warning(f"Notice: Failed to create bucket '{bucket_name}': {create_err}")
        elif error_code in ('403', 'AccessDenied'):
            # Least-privilege IAM policy may permit s3:PutObject without s3:ListBucket / head_bucket
            logger.info(f"Bucket head check returned {error_code} for '{bucket_name}'; proceeding under least-privilege policy.")
        else:
            logger.warning(f"Notice: Storage bucket '{bucket_name}' head check returned {error_code}: {e}")
    except Exception as e:
        logger.warning(f"Notice: Storage check for bucket '{bucket_name}' failed: {e}")


def build_storage_key(user_id: str, filename: str) -> str:
    """
    Generate a sanitized, collision-resistant storage key scoped to the user ID.
    Enforces directory traversal safety and strict multi-tenant path isolation.
    """
    safe_base = os.path.basename(filename).strip()
    safe_base = re.sub(r'[^a-zA-Z0-9_.-]', '_', safe_base) or 'document'
    unique_prefix = uuid.uuid4().hex[:12]
    return f"users/{user_id}/files/{unique_prefix}_{safe_base}"


def upload_file_bytes(user_id: str, file_bytes: bytes, filename: str, content_type: str = 'application/octet-stream') -> str:
    """
    Upload raw file bytes into the user's isolated storage prefix.
    Sanitizes filename and uses unique prefix to prevent path traversal and object collisions.
    Returns the storage key: users/{user_id}/files/{safe_prefix}_{basename}.
    Raises StorageServiceError on failure without leaking credentials or signatures.
    """
    provider = getattr(settings, 'STORAGE_PROVIDER', 'minio').lower()
    if provider == 'minio':
        ensure_bucket_exists()

    client = get_s3_client()
    bucket_name = get_active_bucket_name()
    file_key = build_storage_key(user_id, filename)

    try:
        client.put_object(
            Bucket=bucket_name,
            Key=file_key,
            Body=file_bytes,
            ContentType=content_type,
            Metadata={
                'owner_uuid': str(user_id),
                'filename': os.path.basename(filename)
            }
        )
        return file_key
    except ClientError as exc:
        error_code = exc.response.get('Error', {}).get('Code', 'Unknown')
        logger.error(
            f"[S3_CLIENT_ERROR] Failed uploading '{filename}' to bucket '{bucket_name}': "
            f"Code={error_code}"
        )
        if error_code in ('SignatureDoesNotMatch', 'InvalidAccessKeyId', 'AuthFailure'):
            raise StorageAuthenticationError("Storage authentication failed: invalid credentials or signature mismatch.") from None
        if error_code in ('AccessDenied', '403'):
            raise StorageUploadError(f"Access denied writing to storage bucket '{bucket_name}'.") from None
        if error_code in ('NoSuchBucket', '404'):
            raise StorageUploadError(f"Configured storage bucket '{bucket_name}' does not exist.") from None
        raise StorageUploadError(f"Storage upload failed ({error_code}).") from None
    except Exception as exc:
        logger.error(f"[S3_UPLOAD_ERROR] Unexpected error uploading '{filename}' to bucket '{bucket_name}': {type(exc).__name__}")
        raise StorageUploadError("Storage service temporarily unavailable.") from None


def download_file_bytes(file_key: str) -> bytes:
    """Download raw bytes of an object from storage."""
    client = get_s3_client()
    bucket_name = get_active_bucket_name()
    response = client.get_object(Bucket=bucket_name, Key=file_key)
    return response['Body'].read()


def generate_presigned_download_url(file_key: str, expires_in_seconds: int = 3600) -> str:
    """Generate a time-limited pre-signed download URL for the object."""
    client = get_s3_client()
    bucket_name = get_active_bucket_name()
    return client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket_name,
            'Key': file_key
        },
        ExpiresIn=expires_in_seconds
    )


def delete_file(file_key: str) -> bool:
    """Delete an object from storage."""
    client = get_s3_client()
    bucket_name = get_active_bucket_name()
    try:
        client.delete_object(Bucket=bucket_name, Key=file_key)
        return True
    except Exception as e:
        logger.warning(f"Failed to delete storage object '{file_key}' from '{bucket_name}': {e}")
        return False
