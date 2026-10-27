from django.db import IntegrityError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """
    Custom exception handler to return structured error envelopes
    and prevent leaking stack traces or internal secrets.
    """
    if isinstance(exc, IntegrityError):
        error_data = {
            "success": False,
            "error": {
                "status_code": status.HTTP_400_BAD_REQUEST,
                "message": "A collection with this name already exists.",
                "details": {
                    "name": ["A collection with this name already exists."]
                }
            }
        }
        return Response(error_data, status=status.HTTP_400_BAD_REQUEST)

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
                "details": None
            }
        }
        response = Response(error_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response

