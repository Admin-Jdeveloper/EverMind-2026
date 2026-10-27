import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class CustomUserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for auth."""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = email.lower().strip()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """
    Custom user model for MediaCompile.
    Uses UUID as the primary key and maps to Auth.js identity via authjs_id.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authjs_id = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(unique=True, db_index=True)
    email_verified = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True)
    image = models.URLField(max_length=1024, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email
