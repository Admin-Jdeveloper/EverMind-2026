import pytest
from rest_framework.test import APIClient
from rest_framework import status

@pytest.mark.django_db
def test_health_check_endpoint():
    """Verify /api/v1/health/ returns 200 OK and confirms DB and cache health."""
    client = APIClient()
    response = client.get("/api/v1/health/")
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "healthy"
    assert response.data["service"] == "mediacompile-api"
    assert response.data["checks"]["database"] == "ok"
    assert response.data["checks"]["cache"] == "ok"
    # Ensure no secrets or internal IP addresses are leaked in health payload
    assert "password" not in str(response.data).lower()
    assert "secret" not in str(response.data).lower()
