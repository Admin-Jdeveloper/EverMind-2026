"""
MediaCompile — Content Views and Ingestion API Endpoints.
Source of Truth: MediaCompile-prompt.md (Section 14: Processing Pipeline & Endpoints)

Enforces:
1. Strict server-side authorization: all querysets filtered by request.user.
2. Ingestion pipeline triggering (URL, Note, Document upload).
3. SSRF prevention and MinIO storage integration.
"""

import uuid
import logging
from rest_framework import viewsets, status, filters
from rest_framework.views import APIView

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django.db import transaction
from .models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from .youtube import is_youtube_url, normalize_youtube_url
from .serializers import (
    CollectionSerializer,
    TagSerializer,
    ContentItemSerializer,
    ContentItemDetailSerializer,
    UrlIngestSerializer,
    NoteIngestSerializer,
    DocumentUploadSerializer,
    SavedSearchSerializer,
    WebClipSerializer
)
from .storage import upload_file_bytes, generate_presigned_download_url, delete_file
from .tasks import process_url_content, process_document_content, process_note_content
from core.throttling import IngestionRateThrottle, SearchRateThrottle, ExportImportRateThrottle

class CollectionViewSet(viewsets.ModelViewSet):
    serializer_class = CollectionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Collection.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='add-item')
    def add_item(self, request, pk=None):
        """Add any supported content item (document, link, note) to collection."""
        collection = self.get_object()
        item_id = request.data.get('item_id') or request.data.get('content_id')
        if not item_id:
            return Response({'error': 'item_id or content_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        item = ContentItem.objects.filter(id=item_id, user=request.user).first()
        if not item:
            return Response({'error': 'Content item not found.'}, status=status.HTTP_404_NOT_FOUND)

        item.collection = collection
        item.save(update_fields=['collection'])
        return Response({
            'success': True,
            'collection_id': str(collection.id),
            'item_id': str(item.id),
            'item_count': collection.items.count()
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remove-item')
    def remove_item(self, request, pk=None):
        """Remove content membership from collection without deleting original item, file, chunks, or embeddings."""
        collection = self.get_object()
        item_id = request.data.get('item_id') or request.data.get('content_id')
        if not item_id:
            return Response({'error': 'item_id or content_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        item = ContentItem.objects.filter(id=item_id, user=request.user, collection=collection).first()
        if not item:
            return Response({'error': 'Content item not found in this collection.'}, status=status.HTTP_404_NOT_FOUND)

        item.collection = None
        item.save(update_fields=['collection'])
        return Response({
            'success': True,
            'collection_id': str(collection.id),
            'item_id': str(item.id),
            'item_count': collection.items.count()
        }, status=status.HTTP_200_OK)

class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ContentItemViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'summary', 'raw_text']
    ordering_fields = ['created_at', 'updated_at', 'title']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ContentItemDetailSerializer
        return ContentItemSerializer

    def get_queryset(self):
        qs = ContentItem.objects.filter(user=self.request.user).select_related('collection').prefetch_related('tags', 'chunks')
        
        # Filtering parameters
        content_type = self.request.query_params.get('content_type')
        if content_type:
            qs = qs.filter(content_type=content_type)

        collection_id = self.request.query_params.get('collection')
        if collection_id:
            qs = qs.filter(collection_id=collection_id)

        tag_name = self.request.query_params.get('tag')
        if tag_name:
            qs = qs.filter(tags__name=tag_name)

        ingestion_status = self.request.query_params.get('status')
        if ingestion_status:
            qs = qs.filter(ingestion_status=ingestion_status)

        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        item_id = str(instance.id)
        with transaction.atomic():
            chunk_count = instance.chunks.count()
            instance.chunks.all().delete()
            if hasattr(instance, 'facts'):
                instance.facts.all().delete()
            if instance.file_key:
                try:
                    delete_file(instance.file_key)
                except Exception as e:
                    logger.warning(f"Could not delete MinIO file {instance.file_key}: {e}")
            instance.delete()
            logger.info(f"[DELETION] ContentItem {item_id} and {chunk_count} associated chunks completely purged.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        with transaction.atomic():
            # 1. Explicitly purge associated chunks and embeddings
            chunk_count = instance.chunks.count()
            instance.chunks.all().delete()

            # 2. If object has an associated file in MinIO, remove it safely
            if instance.file_key:
                try:
                    delete_file(instance.file_key)
                except Exception as e:
                    logger.warning(f"Could not delete MinIO file {instance.file_key}: {e}")

            # 3. Delete parent content item
            item_id = str(instance.id)
            instance.delete()
            logger.info(f"[DELETION] ContentItem {item_id} and {chunk_count} associated chunks completely purged.")

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Bulk delete multiple content items belonging strictly to authenticated user."""
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response(
                {'error': 'A list of item IDs is required in the "ids" field.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        items = ContentItem.objects.filter(user=request.user, id__in=ids)
        deleted_count = 0
        for item in items:
            if item.file_key:
                try:
                    delete_file(item.file_key)
                except Exception as e:
                    logger.warning(f"Could not delete MinIO file {item.file_key}: {e}")
            item.delete()
            deleted_count += 1

        return Response(
            {'success': True, 'deleted_count': deleted_count},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Generate a short-lived signed MinIO download URL for document items."""
        item = self.get_object()
        if not item.file_key:
            return Response(
                {'error': 'No file binary is associated with this item.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        url = generate_presigned_download_url(item.file_key)
        return Response({'download_url': url, 'filename': item.metadata.get('filename')})

    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        """Retry a failed or pending content extraction and embedding job."""
        item = self.get_object()
        item.ingestion_status = ContentItem.STATUS_PENDING
        item.error_message = ''
        item.save(update_fields=['ingestion_status', 'error_message'])

        sync_mode = request.headers.get('X-Sync-Ingestion') == 'true'

        if item.content_type in (ContentItem.TYPE_URL, ContentItem.TYPE_VIDEO):
            if sync_mode:
                process_url_content(str(item.id), allow_test_local=True)
                item.refresh_from_db()
            else:
                transaction.on_commit(lambda: process_url_content.delay(str(item.id)))
        elif item.content_type == ContentItem.TYPE_DOCUMENT:
            if sync_mode:
                process_document_content(str(item.id))
                item.refresh_from_db()
            else:
                transaction.on_commit(lambda: process_document_content.delay(str(item.id)))
        elif item.content_type == ContentItem.TYPE_NOTE:
            if sync_mode:
                process_note_content(str(item.id))
                item.refresh_from_db()
            else:
                transaction.on_commit(lambda: process_note_content.delay(str(item.id)))

        return Response(
            ContentItemSerializer(item).data,
            status=status.HTTP_200_OK if sync_mode else status.HTTP_202_ACCEPTED
        )

class IngestUrlView(APIView):
    """POST /api/v1/content/urls/"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [IngestionRateThrottle]

    def post(self, request):
        serializer = UrlIngestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        url = data['url']
        title = data.get('title', '')
        collection_id = data.get('collection_id')
        tags = data.get('tags', [])

        is_yt = is_youtube_url(url)
        if is_yt:
            url = normalize_youtube_url(url)

        collection = None
        if collection_id:
            collection = Collection.objects.filter(id=collection_id, user=request.user).first()
            if not collection:
                return Response({'error': 'Collection not found or unauthorized.'}, status=status.HTTP_404_NOT_FOUND)

        # Handle duplicate submissions idempotently
        existing = ContentItem.objects.filter(user=request.user, source_url=url).first()
        if existing:
            item = existing
            if title:
                item.title = title
            if collection:
                item.collection = collection
            if is_yt:
                item.content_type = ContentItem.TYPE_VIDEO
            item.ingestion_status = ContentItem.STATUS_PENDING
            item.error_message = ''
            item.save(update_fields=['title', 'collection', 'content_type', 'ingestion_status', 'error_message'])
        else:
            item = ContentItem.objects.create(
                user=request.user,
                content_type=ContentItem.TYPE_VIDEO if is_yt else ContentItem.TYPE_URL,
                source_url=url,
                title=title,
                collection=collection,
                ingestion_status=ContentItem.STATUS_PENDING
            )

        for tag_name in tags:
            tag, _ = Tag.objects.get_or_create(user=request.user, name=tag_name.strip())
            item.tags.add(tag)

        # Trigger Celery asynchronous ingestion task
        sync_mode = request.headers.get('X-Sync-Ingestion') == 'true'
        if sync_mode:
            process_url_content(str(item.id), allow_test_local=True)
            item.refresh_from_db()
        else:
            transaction.on_commit(lambda: process_url_content.delay(str(item.id)))

        return Response(ContentItemSerializer(item).data, status=status.HTTP_202_ACCEPTED if not sync_mode else status.HTTP_201_CREATED)

class IngestNoteView(APIView):
    """POST /api/v1/content/notes/"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [IngestionRateThrottle]

    def post(self, request):
        serializer = NoteIngestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        content = data['content']
        title = (data.get('title') or '').strip()

        # Auto-derive title if left empty by user
        if not title:
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), '')
            title = first_line[:60] if first_line else "Untitled Note"

        collection_id = data.get('collection_id')
        tags = data.get('tags', [])

        collection = None
        if collection_id:
            collection = Collection.objects.filter(id=collection_id, user=request.user).first()
            if not collection:
                return Response({'error': 'Collection not found or unauthorized.'}, status=status.HTTP_404_NOT_FOUND)

        # Check for duplicate note content for this user
        existing_note = ContentItem.objects.filter(
            user=request.user,
            content_type=ContentItem.TYPE_NOTE,
            raw_text=content
        ).first()
        if existing_note:
            if title and existing_note.title != title:
                existing_note.title = title
            if collection:
                existing_note.collection = collection
            existing_note.save(update_fields=['title', 'collection'])
            return Response(ContentItemSerializer(existing_note).data, status=status.HTTP_200_OK)

        item = ContentItem.objects.create(
            user=request.user,
            content_type=ContentItem.TYPE_NOTE,
            title=title,
            raw_text=content,
            collection=collection,
            ingestion_status=ContentItem.STATUS_PENDING
        )

        for tag_name in tags:
            tag, _ = Tag.objects.get_or_create(user=request.user, name=tag_name.strip())
            item.tags.add(tag)

        # Execute note chunking immediately
        process_note_content(str(item.id))
        item.refresh_from_db()

        return Response(ContentItemSerializer(item).data, status=status.HTTP_201_CREATED)

class UploadDocumentView(APIView):
    """POST /api/v1/content/files/"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [IngestionRateThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        file_obj = data['file']
        title = data.get('title') or file_obj.name
        collection_id = data.get('collection_id')
        tags = data.get('tags', [])

        collection = None
        if collection_id:
            collection = Collection.objects.filter(id=collection_id, user=request.user).first()
            if not collection:
                return Response({'error': 'Collection not found or unauthorized.'}, status=status.HTTP_404_NOT_FOUND)

        # Read file bytes and upload to MinIO S3
        file_bytes = file_obj.read()
        file_key = upload_file_bytes(
            user_id=str(request.user.id),
            file_bytes=file_bytes,
            filename=file_obj.name,
            content_type=file_obj.content_type
        )

        meta = {
            'filename': file_obj.name,
            'file_size': len(file_bytes),
            'content_type': file_obj.content_type
        }
        detected_fmt = getattr(file_obj, '_detected_format', None)
        if detected_fmt:
            meta['detected_format'] = detected_fmt

        item = ContentItem.objects.create(
            user=request.user,
            content_type=ContentItem.TYPE_DOCUMENT,
            title=title,
            file_key=file_key,
            collection=collection,
            ingestion_status=ContentItem.STATUS_PENDING,
            metadata=meta
        )

        for tag_name in tags:
            tag, _ = Tag.objects.get_or_create(user=request.user, name=tag_name.strip())
            item.tags.add(tag)

        sync_mode = request.headers.get('X-Sync-Ingestion') == 'true'
        if sync_mode:
            process_document_content(str(item.id))
            item.refresh_from_db()
        else:
            transaction.on_commit(lambda: process_document_content.delay(str(item.id)))

        return Response(ContentItemSerializer(item).data, status=status.HTTP_202_ACCEPTED if not sync_mode else status.HTTP_201_CREATED)


class ReembedAPIView(APIView):
    """Trigger re-embedding for all user chunks (e.g. after embedding model change)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .tasks import reembed_user_content
        reembed_user_content(str(request.user.id))
        return Response({
            "status": "queued",
            "message": "Re-embedding pipeline triggered for user library."
        }, status=status.HTTP_202_ACCEPTED)

class SavedSearchViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for User-Saved Searches.
    Enforces strict user isolation.
    """
    serializer_class = SavedSearchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedSearch.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class WebClipAPIView(APIView):
    """
    Browser Extension Clipping Endpoint.
    Saves current tab URL, title, selected snippet, notes, tags, and collection.
    Validates URL safety against SSRF and deduplicates.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [IngestionRateThrottle]

    def post(self, request):
        serializer = WebClipSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        url = data['url']
        title = data.get('title') or url
        selected_text = data.get('selected_text', '').strip()
        notes = data.get('notes', '').strip()
        collection_id = data.get('collection_id')
        tags = data.get('tags', [])

        collection = None
        if collection_id:
            try:
                collection = Collection.objects.get(id=collection_id, user=request.user)
            except Collection.DoesNotExist:
                return Response({'error': 'Collection not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check deduplication
        existing_item = ContentItem.objects.filter(user=request.user, source_url=url).first()
        if existing_item:
            if notes:
                existing_item.metadata['extension_notes'] = notes
                existing_item.save(update_fields=['metadata'])
            if tags:
                tag_objs = [Tag.objects.get_or_create(user=request.user, name=t.strip())[0] for t in tags if t.strip()]
                existing_item.tags.add(*tag_objs)
            return Response({
                "status": "already_exists",
                "message": "URL already saved in your library.",
                "item_id": str(existing_item.id),
                "title": existing_item.title
            }, status=status.HTTP_200_OK)

        raw_content = selected_text
        if notes:
            raw_content = f"{selected_text}\n\nNotes:\n{notes}".strip() if selected_text else notes

        item = ContentItem.objects.create(
            user=request.user,
            content_type=ContentItem.TYPE_URL,
            source_url=url,
            title=title,
            raw_text=raw_content,
            collection=collection,
            metadata={"clipped_by": "browser_extension", "notes": notes},
            ingestion_status=ContentItem.STATUS_COMPLETED if selected_text else ContentItem.STATUS_PENDING
        )

        if tags:
            tag_objs = [Tag.objects.get_or_create(user=request.user, name=t.strip())[0] for t in tags if t.strip()]
            item.tags.set(tag_objs)

        if selected_text:
            from .services import chunk_text
            from .embeddings import get_embedding_provider
            provider = get_embedding_provider()
            chunks = chunk_text(raw_content, chunk_size=500, chunk_overlap=50)
            for idx, c in enumerate(chunks):
                emb = provider.embed_text(c["text"])
                ContentChunk.objects.create(
                    content_item=item,
                    chunk_index=idx,
                    text=c["text"],
                    start_offset=c["start_offset"],
                    end_offset=c["end_offset"],
                    embedding=emb
                )
        else:
            process_url_content.delay(str(item.id))

        return Response({
            "status": "clipped",
            "message": "Page successfully clipped to library.",
            "item_id": str(item.id),
            "title": item.title
        }, status=status.HTTP_201_CREATED)

class LibraryExportAPIView(APIView):
    """
    Sovereign User Library Export Endpoint.
    Returns complete archive of user's items, collections, tags, chunks, memories, and chat history.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExportImportRateThrottle]

    def get(self, request):
        from .export_import import export_user_library
        manifest = export_user_library(request.user)
        return Response(manifest, status=status.HTTP_200_OK)

    def post(self, request):
        from .export_import import export_user_library
        manifest = export_user_library(request.user)
        return Response(manifest, status=status.HTTP_200_OK)

class LibraryBulkImportAPIView(APIView):
    """
    Idempotent Bulk Import & Restore Endpoint.
    Accepts JSON manifest either directly in payload or via uploaded file.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExportImportRateThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        from .export_import import import_user_library
        import json

        manifest_data = None
        if 'file' in request.FILES:
            try:
                uploaded = request.FILES['file']
                content = uploaded.read().decode('utf-8')
                manifest_data = json.loads(content)
            except Exception as e:
                return Response({"error": f"Invalid manifest file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        elif 'manifest' in request.data:
            manifest_data = request.data['manifest']
        elif isinstance(request.data, dict) and 'items' in request.data:
            manifest_data = request.data
        else:
            return Response({"error": "No valid export manifest provided."}, status=status.HTTP_400_BAD_REQUEST)

        stats = import_user_library(request.user, manifest_data)
        return Response(stats, status=status.HTTP_200_OK)
