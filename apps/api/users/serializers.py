from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for authenticated user profile."""
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'name',
            'image',
            'authjs_id',
            'email_verified',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'email', 'authjs_id', 'created_at', 'updated_at']
