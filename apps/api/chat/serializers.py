"""
MediaCompile — Chat Serializers.
Source of Truth: MediaCompile-prompt.md (Section 16: Phase 6 — Grounded AI Chat)
"""

from rest_framework import serializers
from .models import ChatSession, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    """Serializer for individual chat message with structured citations."""
    class Meta:
        model = ChatMessage
        fields = [
            'id',
            'role',
            'content',
            'citations',
            'metadata',
            'created_at'
        ]
        read_only_fields = ['id', 'role', 'citations', 'metadata', 'created_at']

class ChatSessionSerializer(serializers.ModelSerializer):
    """Summary serializer for chat sessions."""
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'title',
            'message_count',
            'last_message',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_message_count(self, obj) -> int:
        return obj.messages.count()

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        if last:
            return {
                "id": str(last.id),
                "role": last.role,
                "content": last.content[:60] + ("..." if len(last.content) > 60 else ""),
                "created_at": last.created_at.isoformat()
            }
        return None

class ChatSessionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for chat session including full message thread."""
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'title',
            'messages',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'messages', 'created_at', 'updated_at']

class SendMessageSerializer(serializers.Serializer):
    """Input serializer for posting a user question into a chat session."""
    content = serializers.CharField(max_length=4096, required=True, allow_blank=False)

class UserMemorySerializer(serializers.ModelSerializer):
    """Serializer for user memory items with safety checks."""
    class Meta:
        from .models import UserMemory
        model = UserMemory
        fields = [
            'id',
            'memory_text',
            'category',
            'is_explicit',
            'is_active',
            'provenance',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        from .memory import validate_memory_safety, SensitiveMemoryError
        memory_text = attrs.get('memory_text', getattr(self.instance, 'memory_text', ''))
        category = attrs.get('category', getattr(self.instance, 'category', 'general'))
        try:
            validate_memory_safety(memory_text, category)
        except SensitiveMemoryError as exc:
            raise serializers.ValidationError({"memory_text": str(exc)})
        return attrs

class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for user AI personalization and privacy settings."""
    class Meta:
        from .models import UserPreference
        model = UserPreference
        fields = [
            'personalization_enabled',
            'allow_inferred_memories',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
