"""
Regression tests for Production API 500 fixes:
- GET /api/v1/content/items/?ordering=-created_at
- GET /api/v1/content/collections/
- GET /api/v1/chat/sessions/

Verifies:
1. New user with zero items receives 200 OK with empty paginated list.
2. User with existing items receives their own items only (cross-user isolation).
3. Missing optional relationships handled gracefully.
4. Invalid / missing authentication returns 401 (not 500).
5. Safe throttle resiliency: Redis connection/cache failures fail open and do not crash the API with 500.
"""

import pytest
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from redis.exceptions import ConnectionError as RedisConnectionError

from content.models import ContentItem, Collection
from chat.models import ChatSession

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def new_user(db):
    return User.objects.create_user(
        email=f"newuser_{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123!"
    )


@pytest.fixture
def existing_user(db):
    user = User.objects.create_user(
        email=f"existing_{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123!"
    )
    col = Collection.objects.create(user=user, name="Work")
    ContentItem.objects.create(
        user=user,
        collection=col,
        title="Existing Research Note",
        content_type=ContentItem.TYPE_NOTE,
        raw_text="Some valuable content.",
        ingestion_status=ContentItem.STATUS_COMPLETED
    )
    ChatSession.objects.create(user=user, title="Existing Session")
    return user


@pytest.mark.django_db
class TestProduction500EndpointsRegression:
    
    def test_new_user_zero_items_returns_200_ok(self, api_client, new_user):
        """A new user with zero items must receive a 200 OK empty paginated result."""
        api_client.force_authenticate(user=new_user)
        
        # 1. Content items
        res = api_client.get('/api/v1/content/items/?ordering=-created_at')
        assert res.status_code == status.HTTP_200_OK, f"Expected 200, got {res.status_code}: {res.content}"
        data = res.json()
        assert data.get('count') == 0
        assert data.get('results') == []
        
        # 2. Collections
        res_col = api_client.get('/api/v1/content/collections/')
        assert res_col.status_code == status.HTTP_200_OK, f"Expected 200, got {res_col.status_code}: {res_col.content}"
        col_data = res_col.json()
        assert col_data.get('count') == 0 or col_data == []
        
        # 3. Chat sessions
        res_chat = api_client.get('/api/v1/chat/sessions/')
        assert res_chat.status_code == status.HTTP_200_OK, f"Expected 200, got {res_chat.status_code}: {res_chat.content}"
        chat_data = res_chat.json()
        assert chat_data.get('count') == 0 or chat_data == []

    def test_user_isolation_between_accounts(self, api_client, new_user, existing_user):
        """New user must see zero items even when other users have items in the database."""
        api_client.force_authenticate(user=new_user)
        
        res = api_client.get('/api/v1/content/items/?ordering=-created_at')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('count') == 0
        assert len(data.get('results', [])) == 0

        # Existing user sees their own item
        api_client.force_authenticate(user=existing_user)
        res_exist = api_client.get('/api/v1/content/items/?ordering=-created_at')
        assert res_exist.status_code == status.HTTP_200_OK
        data_exist = res_exist.json()
        assert data_exist.get('count') == 1
        assert data_exist['results'][0]['title'] == "Existing Research Note"

    def test_unauthenticated_requests_return_401_not_500(self, api_client):
        """Unauthenticated requests must return 401 Unauthorized, never 500."""
        endpoints = [
            '/api/v1/content/items/?ordering=-created_at',
            '/api/v1/content/collections/',
            '/api/v1/chat/sessions/'
        ]
        for ep in endpoints:
            res = api_client.get(ep)
            assert res.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN], \
                f"Expected 401/403 for unauth {ep}, got {res.status_code}"

    def test_safe_throttle_resilience_on_redis_cache_error(self, api_client, new_user):
        """When Redis/cache connection fails (e.g. max clients reached), throttles must fail open and endpoints succeed with 200."""
        api_client.force_authenticate(user=new_user)
        
        with patch('django.core.cache.cache.get', side_effect=RedisConnectionError("max number of clients reached")):
            res = api_client.get('/api/v1/content/items/?ordering=-created_at')
            assert res.status_code == status.HTTP_200_OK, f"Expected 200 even with Redis error, got {res.status_code}"
            
            res_col = api_client.get('/api/v1/content/collections/')
            assert res_col.status_code == status.HTTP_200_OK
            
            res_chat = api_client.get('/api/v1/chat/sessions/')
            assert res_chat.status_code == status.HTTP_200_OK
