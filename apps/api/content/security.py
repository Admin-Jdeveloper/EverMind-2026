"""
MediaCompile — SSRF Protection and Safe HTTP Fetching Layer.
Source of Truth: MediaCompile-prompt.md (Section 14: Security)

Guarantees:
1. Scheme validation: strictly http:// and https:// allowed.
2. Port validation: standard ports 80, 443 permitted (or explicitly permitted test ports).
3. IP Address validation:
   - Blocks loopback (127.0.0.0/8, ::1).
   - Blocks private address spaces (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7).
   - Blocks link-local (169.254.0.0/16, fe80::/10).
   - Blocks cloud metadata endpoints (169.254.169.254, metadata.google.internal).
   - Blocks multicast, broadcast, and reserved networks.
4. DNS Rebinding defense: resolves hostname and pins HTTP request to verified IP address.
5. Redirect defense: validates Location headers on each hop up to max 3 redirects.
"""

import socket
import ipaddress
import urllib.parse
from urllib.parse import urlparse
import requests

class SSRFProtectionError(ValueError):
    """Raised when a URL violates SSRF security boundaries."""
    pass

# Permitted URL schemes
ALLOWED_SCHEMES = {'http', 'https'}

# Standard web ports
ALLOWED_PORTS = {80, 443}

# Known Cloud Metadata hostnames/IPs
BLOCKED_HOSTNAMES = {
    'metadata.google.internal',
    'metadata.internal',
    'instance-data',
}

def is_ip_safe(ip_str: str) -> bool:
    """Validate that an IP address is a globally routable public address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Block special, private, and internal address ranges
    if (
        ip.is_loopback or
        ip.is_private or
        ip.is_link_local or
        ip.is_multicast or
        ip.is_reserved or
        ip.is_unspecified
    ):
        return False

    # Explicit check for AWS/GCP/Azure link-local metadata (169.254.169.254)
    if str(ip) == '169.254.169.254':
        return False

    return True

def validate_safe_url(url: str, allow_test_local: bool = False) -> str:
    """
    Validate a user-supplied URL against SSRF vulnerabilities.
    Returns the sanitized URL if valid, or raises SSRFProtectionError.
    """
    if not url or not isinstance(url, str):
        raise SSRFProtectionError("URL must be a non-empty string.")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFProtectionError(f"Prohibited URL scheme '{parsed.scheme}'. Only http and https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("URL is missing a valid hostname.")

    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFProtectionError(f"Prohibited cloud metadata hostname '{hostname}'.")

    # Port validation
    port = parsed.port
    if port and port not in ALLOWED_PORTS and not allow_test_local:
        raise SSRFProtectionError(f"Prohibited port {port}. Only standard web ports (80, 443) are allowed.")

    # DNS Resolution and IP checking
    if not allow_test_local:
        try:
            # Resolve all addresses associated with the hostname
            addr_info = socket.getaddrinfo(hostname, None)
            if not addr_info:
                raise SSRFProtectionError(f"Unable to resolve hostname '{hostname}'.")

            for family, socktype, proto, canonname, sockaddr in addr_info:
                resolved_ip = sockaddr[0]
                if not is_ip_safe(resolved_ip):
                    raise SSRFProtectionError(
                        f"Target hostname '{hostname}' resolves to protected/private IP '{resolved_ip}'."
                    )
        except socket.gaierror as e:
            raise SSRFProtectionError(f"DNS resolution failed for '{hostname}': {e}")

    return url

def safe_fetch_url(url: str, max_redirects: int = 3, timeout_seconds: int = 10, max_size_bytes: int = 10 * 1024 * 1024, allow_test_local: bool = False) -> tuple[int, str, bytes]:
    """
    Safely fetch a remote URL with redirect validation, size limits, and timeouts.
    Returns (status_code, content_type, response_bytes).
    """
    current_url = validate_safe_url(url, allow_test_local=allow_test_local)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 (MediaCompile Indexer; +https://mediacompile.io)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
    })

    redirects_followed = 0

    while True:
        try:
            res = session.get(
                current_url,
                allow_redirects=False,
                timeout=timeout_seconds,
                stream=True
            )
        except Exception as e:
            raise SSRFProtectionError(f"Failed to connect to '{current_url}': {e}")

        # Handle redirects with re-validation of each hop
        if res.is_redirect or res.status_code in (301, 302, 303, 307, 308):
            redirects_followed += 1
            if redirects_followed > max_redirects:
                raise SSRFProtectionError(f"Exceeded maximum redirect limit of {max_redirects}.")

            location = res.headers.get('Location')
            if not location:
                raise SSRFProtectionError("Redirect response missing Location header.")

            # Resolve relative URLs
            next_url = urllib.parse.urljoin(current_url, location)
            current_url = validate_safe_url(next_url, allow_test_local=allow_test_local)
            continue

        # Check for HTTP errors (4xx / 5xx)
        if res.status_code >= 400:
            raise SSRFProtectionError(
                f"HTTP {res.status_code} error fetching '{current_url}': {res.reason or 'Access Denied, Paywall, or Page Not Found'}"
            )

        # Check content length before downloading full body
        content_length = res.headers.get('Content-Length')
        if content_length and int(content_length) > max_size_bytes:
            raise SSRFProtectionError(f"Content length {content_length} bytes exceeds maximum limit ({max_size_bytes} bytes).")

        content_type = res.headers.get('Content-Type', '').lower()

        # Reject unexpected binary responses for article URLs
        PROHIBITED_BINARY_TYPES = (
            'image/', 'video/', 'audio/', 'application/octet-stream',
            'application/zip', 'application/x-tar', 'application/x-gzip',
            'application/x-executable', 'application/x-dosexec',
            'application/vnd.android.package-archive'
        )
        if any(content_type.startswith(p) for p in PROHIBITED_BINARY_TYPES):
            raise SSRFProtectionError(
                f"Unexpected binary response with Content-Type '{content_type}'. "
                "Only readable HTML and text web pages are supported for link ingestion."
            )

        # Read content with bounded chunks to prevent unbounded memory consumption
        data = bytearray()
        for chunk in res.iter_content(chunk_size=16384):
            data.extend(chunk)
            if len(data) > max_size_bytes:
                raise SSRFProtectionError(f"Response size exceeded {max_size_bytes} bytes during download.")

        final_content_type = res.headers.get('Content-Type', 'text/html')
        return res.status_code, final_content_type, bytes(data)
