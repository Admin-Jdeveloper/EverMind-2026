"""
MediaCompile — Content Serializers.
Source of Truth: MediaCompile-prompt.md (Section 14: Serializers)
"""

from rest_framework import serializers
from .models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from .security import validate_safe_url, SSRFProtectionError

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'created_at']
        read_only_fields = ['id', 'created_at']

class CollectionSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = Collection
        fields = ['id', 'user', 'name', 'description', 'is_private', 'item_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=Collection.objects.all(),
                fields=['user', 'name'],
                message="A collection with this name already exists."
            )
        ]

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Collection name cannot be empty.")
        return cleaned

class ContentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentChunk
        fields = ['id', 'chunk_index', 'text', 'start_offset', 'end_offset', 'metadata', 'content_hash', 'version', 'created_at']
        read_only_fields = ['id', 'content_hash', 'version', 'created_at']

class ContentItemSerializer(serializers.ModelSerializer):
    collection_name = serializers.CharField(source='collection.name', read_only=True)
    tags_list = serializers.SlugRelatedField(many=True, slug_field='name', source='tags', read_only=True)
    chunk_count = serializers.SerializerMethodField()

    def get_chunk_count(self, obj):
        # 1. Use pre-annotated count from queryset if present (0 additional queries)
        if hasattr(obj, 'annotated_chunk_count'):
            return obj.annotated_chunk_count
        # 2. Use stored metadata count if present (0 additional queries)
        if isinstance(obj.metadata, dict) and 'chunk_count' in obj.metadata:
            return obj.metadata['chunk_count']
        # 3. Fallback to count query only if not annotated
        return obj.chunks.count()

    class Meta:
        model = ContentItem
        fields = [
            'id', 'title', 'source_url', 'content_type', 'summary', 'raw_text',
            'ingestion_status', 'error_message', 'collection', 'collection_name',
            'tags_list', 'tags', 'chunk_count', 'metadata', 'content_hash', 'version',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'ingestion_status', 'error_message', 'content_hash', 'version', 'created_at', 'updated_at']

    def validate_collection(self, value):
        if value and hasattr(self, 'context') and 'request' in self.context:
            request = self.context['request']
            if request.user.is_authenticated and value.user != request.user:
                raise serializers.ValidationError("Cannot assign item to a collection you do not own.")
        return value

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        old_raw_text = instance.raw_text
        new_raw_text = validated_data.get('raw_text', None)

        instance = super().update(instance, validated_data)

        if tags_data is not None:
            instance.tags.clear()
            for tag_name in tags_data:
                tag_str = tag_name.strip()
                if tag_str:
                    tag, _ = Tag.objects.get_or_create(user=instance.user, name=tag_str)
                    instance.tags.add(tag)

        # If a Note's text was updated, automatically re-chunk and re-embed
        if new_raw_text is not None and instance.content_type == ContentItem.TYPE_NOTE and new_raw_text != old_raw_text:
            instance.version += 1
            instance.save(update_fields=['version'])
            from .tasks import process_note_content
            from django.db import transaction
            
            # If in test or sync request, execute immediately; otherwise dispatch via transaction commit
            is_sync = False
            if hasattr(self, 'context') and 'request' in self.context:
                is_sync = self.context['request'].headers.get('X-Sync-Ingestion') == 'true'
            
            if is_sync:
                process_note_content(str(instance.id))
            else:
                try:
                    transaction.on_commit(lambda: process_note_content.delay(str(instance.id)))
                except Exception:
                    process_note_content(str(instance.id))

        return instance

class ContentItemDetailSerializer(ContentItemSerializer):
    chunks = ContentChunkSerializer(many=True, read_only=True)

    class Meta(ContentItemSerializer.Meta):
        fields = ContentItemSerializer.Meta.fields + ['chunks']

class UrlIngestSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048, required=True)
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)

    def validate_url(self, value):
        try:
            # Enforce pre-validation check
            validate_safe_url(value)
            return value
        except SSRFProtectionError as e:
            raise serializers.ValidationError(str(e))

class NoteIngestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    content = serializers.CharField(required=True)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)

class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)

    ALLOWED_EXTENSIONS = (
        '.pdf', '.docx', '.pptx', '.xlsx', '.csv', '.txt', '.md', '.markdown'
    )
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    DISALLOWED_EXTENSIONS = (
        '.exe', '.dll', '.so', '.dylib', '.bat', '.cmd', '.sh', '.bin',
        '.msi', '.vbs', '.js', '.jar', '.com', '.scr', '.pif', '.py', '.php'
    )

    def validate_file(self, value):
        filename = value.name.lower()
        if value.size == 0:
            raise serializers.ValidationError("File is empty (0 bytes).")
        if value.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"File size exceeds {self.MAX_FILE_SIZE // (1024 * 1024)} MB limit."
            )

        if any(filename.endswith(ext) for ext in self.DISALLOWED_EXTENSIONS):
            raise serializers.ValidationError(f"Unsupported file type: Executables and scripts are not permitted.")

        # Content/Magic Header Validation
        try:
            value.seek(0)
            header = value.read(1024)
            value.seek(0)
        except Exception:
            header = b''

        # Security check: reject executable binaries by magic bytes
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise serializers.ValidationError("Executable binaries are not permitted.")

        matched_ext = any(filename.endswith(ext) for ext in self.ALLOWED_EXTENSIONS)
        
        # Safe format detection fallback if extension is missing or atypical (not an executable)
        if not matched_ext:
            if b'%PDF-' in header:
                value._detected_format = 'pdf'
            elif header.startswith(b'PK\x03\x04'):
                value._detected_format = 'docx'
            elif b'.' not in filename and b'\x00' not in header:
                # Extensionless text-like content
                value._detected_format = 'txt'
            else:
                raise serializers.ValidationError(
                    f"Unsupported file type. Supported formats: {', '.join(self.ALLOWED_EXTENSIONS)}."
                )

        if filename.endswith('.pdf') and b'%PDF-' not in header:
            raise serializers.ValidationError("Invalid PDF file: Missing %PDF- signature.")
        elif any(filename.endswith(ext) for ext in ('.docx', '.pptx', '.xlsx')) and not header.startswith(b'PK\x03\x04'):
            raise serializers.ValidationError("Invalid Office document: File is not a valid zip archive.")

        return value

class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'name', 'query_text', 'filters', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class WebClipSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048, required=True)
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    selected_text = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)

    def validate_url(self, value):
        try:
            validate_safe_url(value)
            return value
        except SSRFProtectionError as e:
            raise serializers.ValidationError(str(e))
