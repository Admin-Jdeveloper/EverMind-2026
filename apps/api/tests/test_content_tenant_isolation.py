import pytest
from rest_framework.test import APIClient
from users.models import User
from content.models import ContentItem, ContentChunk, Collection, Tag

@pytest.fixture
def user_a():
    return User.objects.create_user(
        email="alice@mediacompile.io",
        password="AlicePassword2026!",
        authjs_id="authjs_alice_1"
    )

@pytest.fixture
def user_b():
    return User.objects.create_user(
        email="bob@mediacompile.io",
        password="BobPassword2026!",
        authjs_id="authjs_bob_2"
    )

@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client

@pytest.fixture
def client_b(user_b):
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client

@pytest.mark.django_db
def test_user_b_cannot_access_user_a_content(client_a, client_b, user_a, user_b):
    """Verify strict tenant isolation across all content CRUD endpoints."""
    # Alice creates a collection and a private note
    col_a = Collection.objects.create(user=user_a, name="Alice Confidential")
    item_a = ContentItem.objects.create(
        user=user_a,
        title="Alice Secret Roadmap",
        content_type="note",
        raw_text="Top secret project data.",
        collection=col_a,
        file_key=f"users/{user_a.id}/files/secret.txt"
    )
    chunk_a = ContentChunk.objects.create(
        content_item=item_a,
        chunk_index=0,
        text="Top secret project data."
    )

    # 1. Bob cannot see Alice's item in item list
    res_list = client_b.get('/api/v1/content/items/')
    assert res_list.status_code == 200
    assert len(res_list.json().get('results', [])) == 0

    # 2. Bob cannot retrieve Alice's item detail by ID (returns 404)
    res_detail = client_b.get(f'/api/v1/content/items/{item_a.id}/')
    assert res_detail.status_code == 404

    # 3. Bob cannot modify Alice's item
    res_patch = client_b.patch(f'/api/v1/content/items/{item_a.id}/', {'title': 'Hacked Title'})
    assert res_patch.status_code == 404
    item_a.refresh_from_db()
    assert item_a.title == "Alice Secret Roadmap"

    # 4. Bob cannot delete Alice's item
    res_del = client_b.delete(f'/api/v1/content/items/{item_a.id}/')
    assert res_del.status_code == 404
    assert ContentItem.objects.filter(id=item_a.id).exists()

    # 5. Bob cannot download Alice's pre-signed file URL
    res_dl = client_b.get(f'/api/v1/content/items/{item_a.id}/download/')
    assert res_dl.status_code == 404

    # 6. Bob cannot view or modify Alice's collection
    res_col = client_b.get(f'/api/v1/content/collections/{col_a.id}/')
    assert res_col.status_code == 404
