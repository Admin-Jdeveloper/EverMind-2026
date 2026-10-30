"""
MediaCompile — Security Headers and Request Audit Middleware.
Source of Truth: MediaCompile-prompt.md (Section 20: Phase 10 — Security & Privacy)

Implements:
1. Strict Security Headers: nosniff, DENY frame-ancestors, CSP, Referrer-Policy, Permissions-Policy.
2. Structured Redacted Request Logging: Logs incoming requests without exposing tokens or credentials.
"""

import time
import logging

logger = logging.getLogger('mediacompile.security')

class SecurityHeadersMiddleware:
    """
    Applies defense-in-depth HTTP security headers to all incoming responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # OWASP Security Headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), payment=()'
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Resource-Policy'] = 'same-site'

        # Content Security Policy (allows local Next.js client and API communication)
        if 'Content-Security-Policy' not in response:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https: blob:; "
                "connect-src 'self' http://localhost:3000 http://127.0.0.1:3000 http://localhost:8000 http://127.0.0.1:8000; "
                "frame-ancestors 'none'; "
                "object-src 'none';"
            )
            response['Content-Security-Policy'] = csp

        return response

import uuid

class RequestAuditLoggingMiddleware:
    """
    Logs API requests with duration, user context, and Request ID, guaranteeing sensitive token redaction.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id

        start_time = time.time()
        response = self.get_response(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Propagate X-Request-ID in response headers
        response['X-Request-ID'] = request_id

        user_id = str(request.user.id) if getattr(request, 'user', None) and request.user.is_authenticated else 'anonymous'
        path = request.path

        # Do not log health checks to keep logs clean
        if not path.startswith('/api/v1/health'):
            logger.info(
                f"[AUDIT] request_id={request_id} {request.method} {path} -> HTTP {response.status_code} "
                f"({duration_ms}ms) user={user_id} ip={self.get_client_ip(request)}"
            )

        return response

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '127.0.0.1')
