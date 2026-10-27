import uuid
from django.db import models
from django.conf import settings

class ChatSession(models.Model):
    """User-owned conversation session for grounded RAG chat."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, default="New Conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.email} - {self.title}"

class ChatMessage(models.Model):
    """Individual message in a chat session."""
    
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_SYSTEM = 'system'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_SYSTEM, 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    
    # Structured citations pointing to ContentChunk and ContentItem UUIDs
    citations = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}..."

class UserMemory(models.Model):
    """
    Explicit or consented preference / memory item.
    Full user control: can be inspected, edited, disabled, or deleted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memories')
    memory_text = models.TextField()
    category = models.CharField(max_length=64, default="general")
    is_explicit = models.BooleanField(default=True, help_text="True if user explicitly typed it; False if inferred with consent")
    is_active = models.BooleanField(default=True, help_text="Can be toggled off without deleting")
    provenance = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} memory: {self.memory_text[:30]}..."

class UserPreference(models.Model):
    """User privacy preferences controlling AI personalization and memory retention."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_preference')
    personalization_enabled = models.BooleanField(default=True, help_text="Master toggle to enable/disable AI memory in prompts")
    allow_inferred_memories = models.BooleanField(default=True, help_text="Consent to allow automated memory inference from chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} (Personalization: {self.personalization_enabled})"
