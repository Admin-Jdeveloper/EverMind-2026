import pytest
from django.contrib.auth import get_user_model
from content.models import Collection, ContentItem
from chat.models import ChatSession

User = get_user_model()

@pytest.mark.django_db
def test_cross_tenant_content_isolation():
    """Verify that User B cannot query or access User A's private collections or items."""
    user_a = User.objects.create_user(email="alice@mediacompile.io", password="AlicePassword123!")
    user_b = User.objects.create_user(email="bob@mediacompile.io", password="BobPassword123!")

    # User A creates a collection and content item
    col_a = Collection.objects.create(user=user_a, name="Alice AI Research")
    item_a = ContentItem.objects.create(
        user=user_a,
        collection=col_a,
        title="Distributed Systems Paper",
        source_url="https://example.com/paper.pdf"
    )

    # User B queries their own collections and items
    bob_collections = Collection.objects.filter(user=user_b)
    bob_items = ContentItem.objects.filter(user=user_b)

    assert col_a not in bob_collections
    assert item_a not in bob_items
    assert bob_collections.count() == 0
    assert bob_items.count() == 0

@pytest.mark.django_db
def test_cross_tenant_chat_isolation():
    """Verify that User B cannot query or access User A's chat sessions."""
    user_a = User.objects.create_user(email="alice_chat@mediacompile.io", password="AlicePassword123!")
    user_b = User.objects.create_user(email="bob_chat@mediacompile.io", password="BobPassword123!")

    session_a = ChatSession.objects.create(user=user_a, title="Alice's Private Session")

    bob_sessions = ChatSession.objects.filter(user=user_b)
    assert session_a not in bob_sessions
    assert bob_sessions.count() == 0
