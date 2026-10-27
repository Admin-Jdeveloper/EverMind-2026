import pytest
from content.security import validate_safe_url, SSRFProtectionError, is_ip_safe

def test_safe_public_urls_accepted():
    """Verify standard public URLs pass SSRF validation."""
    assert validate_safe_url("https://example.com") == "https://example.com"
    assert validate_safe_url("http://example.com/path/to/page") == "http://example.com/path/to/page"
    assert validate_safe_url("https://arxiv.org/abs/2312.001") == "https://arxiv.org/abs/2312.001"

def test_loopback_rejected():
    """Verify loopback addresses are strictly rejected."""
    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://127.0.0.1:8080/admin")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://localhost/secret")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://127.0.0.2")

def test_private_subnets_rejected():
    """Verify RFC 1918 private subnets are blocked."""
    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://10.0.0.1/internal")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://192.168.1.100")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://172.16.0.5:80")

def test_cloud_metadata_rejected():
    """Verify AWS/GCP/Azure link-local metadata endpoints are blocked."""
    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://metadata.google.internal/computeMetadata/v1/")

def test_prohibited_schemes_rejected():
    """Verify non-HTTP schemes are rejected."""
    with pytest.raises(SSRFProtectionError):
        validate_safe_url("file:///etc/passwd")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("ftp://example.com/resource")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("gopher://127.0.0.1:11211/")

def test_prohibited_ports_rejected():
    """Verify non-web ports (SSH, MySQL, Redis) are blocked."""
    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://example.com:22/")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://example.com:3306/")

    with pytest.raises(SSRFProtectionError):
        validate_safe_url("http://example.com:6379/")

def test_ip_safe_helper():
    """Test unit validation of IP address categories."""
    assert is_ip_safe("93.184.216.34") is True      # example.com
    assert is_ip_safe("8.8.8.8") is True             # Google DNS
    assert is_ip_safe("127.0.0.1") is False          # Loopback
    assert is_ip_safe("10.0.0.1") is False           # Private class A
    assert is_ip_safe("172.16.0.1") is False         # Private class B
    assert is_ip_safe("192.168.0.1") is False        # Private class C
    assert is_ip_safe("169.254.169.254") is False    # Link-local metadata
    assert is_ip_safe("224.0.0.1") is False          # Multicast
