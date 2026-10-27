import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher

User = get_user_model()

@pytest.mark.django_db
def test_create_user_with_email_and_uuid():
    """Verify user creation with UUID primary key and normalized email."""
    user = User.objects.create_user(
        email="TEST@MediaCompile.io",
        password="SecurePassword123!"
    )
    assert user.id is not None
    assert str(user.id) != ""
    assert user.email == "test@mediacompile.io"
    assert user.check_password("SecurePassword123!")
    assert not user.check_password("WrongPassword")
    assert user.is_active is True
    assert user.is_staff is False

@pytest.mark.django_db
def test_argon2_password_hasher_used():
    """Verify password hashing algorithm adheres to Argon2 requirement."""
    user = User.objects.create_user(
        email="argon2user@mediacompile.io",
        password="Argon2Password#2026"
    )
    hasher = identify_hasher(user.password)
    assert hasher.algorithm == "argon2"

@pytest.mark.django_db
def test_create_superuser():
    """Verify superuser creation."""
    admin = User.objects.create_superuser(
        email="admin@mediacompile.io",
        password="SuperAdminPassword123!"
    )
    assert admin.is_staff is True
    assert admin.is_superuser is True

@pytest.mark.django_db
def test_create_user_without_email_fails():
    """Verify user creation without email raises ValueError."""
    with pytest.raises(ValueError):
        User.objects.create_user(email="")
