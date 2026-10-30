import uuid
import logging
from django.db import IntegrityError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('api.exceptions')

def custom_exception_handler(exc, context):
    """
    Custom exception handler to return structured error envelopes
    with Request ID tracking while strictly preventing stack trace or credential leaks.
    """
    request = context.get('request') if context else None
    request_id = getattr(request, 'request_id', None)
    if not request_id and request:
        request_id = request.META.get('HTTP_X_REQUEST_ID')
    if not request_id:
        request_id = str(uuid.uuid4())

    path = request.path if request else 'unknown'
    method = request.method if request else 'unknown'

    # Sanitize exception message to eliminate any leaked JWTs, passwords, or S3 presigned credentials
    raw_exc_str = str(exc)
    sanitized_exc_summary = raw_exc_str[:300]

    # Log backend diagnostic error without exposing auth tokens
    logger.error(
        f"[REQUEST_EXCEPTION] request_id={request_id} method={method} path={path} "
        f"type={type(exc).__name__}: {sanitized_exc_summary}"
    )

    if isinstance(exc, IntegrityError):
        error_data = {
            "success": False,
            "error": {
                "status_code": status.HTTP_400_BAD_REQUEST,
                "message": "A resource with this identifier or name already exists.",
                "request_id": request_id,
                "details": {
                    "name": ["A resource with this identifier or name already exists."]
                }
            }
        }
        res = Response(error_data, status=status.HTTP_400_BAD_REQUEST)
        res['X-Request-ID'] = request_id
        return res

    response = exception_handler(exc, context)

    if response is not None:
        message = "Request failed validation or authorization."
        if isinstance(response.data, dict):
            if "detail" in response.data:
                message = str(response.data["detail"])
            elif "message" in response.data:
                message = str(response.data["message"])
            elif response.data:
                first_k = next(iter(response.data))
                first_v = response.data[first_k]
                if isinstance(first_v, list) and first_v:
                    message = f"{first_k}: {first_v[0]}"
                else:
                    message = f"{first_k}: {first_v}"
        elif isinstance(response.data, list) and response.data:
            message = str(response.data[0])

        error_data = {
            "success": False,
            "error": {
                "status_code": response.status_code,
                "message": message,
                "request_id": request_id,
                "details": response.data
            }
        }
        response.data = error_data
    else:
        error_data = {
            "success": False,
            "error": {
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An unexpected server error occurred.",
                "request_id": request_id,
                "details": None
            }
        }
        response = Response(error_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    response['X-Request-ID'] = request_id
    return response

