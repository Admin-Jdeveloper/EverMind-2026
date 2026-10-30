"""
MediaCompile — Celery Ingestion Tasks.
Source of Truth: MediaCompile-prompt.md (Section 14: Processing Pipeline)

Processes URLs, uploaded documents (PDF, TXT, MD), and notes asynchronously.
Executes on the Windows host using Celery with the -P solo pool.
"""

import logging
from celery import shared_task
from django.db import transaction
from .models import ContentItem, ContentChunk
from .security import safe_fetch_url, SSRFProtectionError
from .storage import download_file_bytes
from .services import (
    extract_text_from_html,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_pptx,
    extract_text_from_xlsx,
    extract_text_from_csv,
    extract_text_from_txt,
    chunk_text
)

from .youtube import (
    is_youtube_url,
    extract_youtube_video_id,
    normalize_youtube_url,
    fetch_youtube_metadata,
    fetch_youtube_transcript,
    chunk_youtube_transcript
)
from .facts import compute_sha256, index_item_facts

logger = logging.getLogger(__name__)


def process_youtube_content_internal(task_instance, item: ContentItem):
    """
    Dedicated ingestion path for YouTube videos, shorts, and live streams.
    Extracts metadata via oEmbed and subtitles/transcripts via youtube-transcript-api.
    Embeds timestamped chunks in pgvector.
    Supports metadata-only fallback if transcripts are unavailable.
    """
    item.ingestion_status = ContentItem.STATUS_EXTRACTING
    item.save(update_fields=['ingestion_status'])

    video_id = extract_youtube_video_id(item.source_url)
    if not video_id:
        raise ValueError(f"Could not extract a valid YouTube video ID from {item.source_url}")

    canonical_url = normalize_youtube_url(item.source_url)
    item.source_url = canonical_url
    item.content_type = ContentItem.TYPE_VIDEO

    # 1. Fetch metadata
    yt_meta = fetch_youtube_metadata(video_id, canonical_url)
    if yt_meta.get('title') and (not item.title or item.title.startswith('http') or item.title.startswith('Pending') or item.title == 'Untitled Content'):
        item.title = yt_meta['title'][:512]
    if not item.summary and yt_meta.get('description'):
        item.summary = yt_meta['description'][:1000]

    item.metadata.update(yt_meta)
    item.save(update_fields=['title', 'summary', 'source_url', 'content_type', 'metadata', 'ingestion_status'])

    # 2. Fetch transcript cues
    cues, transcript_error = fetch_youtube_transcript(video_id)

    if cues:
        # Transcript available: chunk with timestamps
        item.ingestion_status = ContentItem.STATUS_CHUNKING
        item.save(update_fields=['ingestion_status'])

        chunks = chunk_youtube_transcript(cues, video_id, canonical_url)
        all_transcript_text = "\n\n".join([c['text'] for c in chunks])
        item.raw_text = all_transcript_text
        item.metadata['has_transcript'] = True
        item.metadata['transcript_cue_count'] = len(cues)
        item.error_message = ''
    else:
        # Section 7.4: Metadata-only ingestion when transcript cannot be obtained
        logger.info(f"[YouTube] Video {video_id} has no accessible transcript: {transcript_error}")
        fallback_text = (
            f"Title: {item.title}\n"
            f"Channel: {yt_meta.get('channel_name', 'Unknown')}\n\n"
            f"Description:\n{item.summary or 'No description provided.'}"
        )
        item.raw_text = fallback_text
        item.metadata['has_transcript'] = False
        item.metadata['metadata_only'] = True
        item.error_message = f"Video transcript unavailable ({transcript_error or 'No captions'}). Indexed video metadata and description."

        chunks = chunk_text(fallback_text)
        for c in chunks:
            c['metadata'].update({
                'video_id': video_id,
                'source_url': canonical_url,
                'platform': 'youtube',
                'is_metadata_only': True
            })

    if not chunks:
        raise ValueError("Could not extract any indexable content or metadata from YouTube video.")

    # 3. Generate embeddings
    item.ingestion_status = ContentItem.STATUS_EMBEDDING
    item.save(update_fields=['ingestion_status', 'raw_text', 'metadata', 'error_message'])

    from .embeddings import get_embedding_provider
    provider = get_embedding_provider()
    texts = [c['text'] for c in chunks]
    embeddings = provider.embed_batch(texts)

    chunk_objs = []
    for c, vec in zip(chunks, embeddings):
        meta = c.get('metadata', {})
        meta['char_length'] = c.get('char_length', len(c['text']))
        meta['embedding_model'] = provider.model_name
        meta['embedding_dimension'] = provider.dimension
        chunk_objs.append(
            ContentChunk(
                content_item=item,
                chunk_index=c['chunk_index'],
                text=c['text'],
                start_offset=c['start_offset'],
                end_offset=c['end_offset'],
                embedding=vec,
                metadata=meta,
                content_hash=compute_sha256(c['text']),
                version=item.version
            )
        )

    # 4. Atomic vector and fact indexing
    item.ingestion_status = ContentItem.STATUS_INDEXING
    item.content_hash = compute_sha256(item.raw_text)
    item.save(update_fields=['ingestion_status', 'content_hash'])

    with transaction.atomic():
        item.chunks.all().delete()
        ContentChunk.objects.bulk_create(chunk_objs)
        index_item_facts(item, chunk_objs)

        item.ingestion_status = ContentItem.STATUS_PARTIAL if item.metadata.get('metadata_only') else ContentItem.STATUS_COMPLETED
        item.metadata['chunk_count'] = len(chunk_objs)
        item.save(update_fields=['title', 'summary', 'raw_text', 'ingestion_status', 'content_hash', 'metadata', 'error_message'])

    logger.info(
        f"[DIAGNOSTIC] YouTube Ingestion Completed: item_id={item.id}, video_id={video_id}, "
        f"has_transcript={item.metadata.get('has_transcript')}, chunks={len(chunk_objs)}"
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=5, ignore_result=True)
def process_url_content(self, content_item_id: str, allow_test_local: bool = False):
    """
    Fetch URL content safely through SSRF protection or specialized YouTube pipeline.
    """
    try:
        item = ContentItem.objects.get(id=content_item_id)
    except ContentItem.DoesNotExist as exc:
        if getattr(self, 'request', None) and getattr(self.request, 'retries', 0) < getattr(self, 'max_retries', 3):
            raise self.retry(exc=exc, countdown=1)
        logger.warning(f"ContentItem {content_item_id} not found.")
        return

    item.ingestion_status = ContentItem.STATUS_PROCESSING
    item.save(update_fields=['ingestion_status'])

    try:
        # Route YouTube URLs to dedicated YouTube ingestion workflow
        if is_youtube_url(item.source_url):
            return process_youtube_content_internal(self, item)

        item.ingestion_status = ContentItem.STATUS_EXTRACTING
        item.save(update_fields=['ingestion_status'])

        status_code, content_type, body = safe_fetch_url(
            item.source_url,
            allow_test_local=allow_test_local
        )

        title, normalized_text, page_metadata = extract_text_from_html(body)
        
        # Save extracted title if not custom-specified by user
        if not item.title and title:
            item.title = title[:512]

        if not item.summary and page_metadata.get('description'):
            item.summary = page_metadata['description']

        item.metadata.update(page_metadata)
        item.raw_text = normalized_text

        # Validate minimum text content quality
        clean_text = (normalized_text or '').strip()
        if len(clean_text) < 40:
            raise ValueError(
                f"Extracted page content is too short ({len(clean_text)} chars) to be indexed. "
                "The target page may be empty, require JavaScript rendering, or block scraping."
            )

        # Check for bot-block / access-denied keywords in extracted text
        block_keywords = ['access denied', '403 forbidden', 'cloudflare ray id', 'please enable cookies', 'enable javascript to continue']
        clean_lower = clean_text[:400].lower()
        if any(kw in clean_lower for kw in block_keywords) and len(clean_text) < 400:
            raise ValueError(
                "Target server blocked content indexing (Access Denied / Bot Detection). "
                "The webpage cannot be indexed."
            )

        item.ingestion_status = ContentItem.STATUS_CHUNKING
        item.save(update_fields=['ingestion_status'])

        chunks = chunk_text(normalized_text)
        if not chunks:
            raise ValueError("No readable text chunks could be produced from document content.")

        item.ingestion_status = ContentItem.STATUS_EMBEDDING
        item.save(update_fields=['ingestion_status'])

        from .embeddings import get_embedding_provider
        provider = get_embedding_provider()
        texts = [c['text'] for c in chunks]
        embeddings = provider.embed_batch(texts)

        chunk_objs = []
        for c, vec in zip(chunks, embeddings):
            meta = c.get('metadata', {})
            meta['char_length'] = c.get('char_length', len(c['text']))
            meta['embedding_model'] = provider.model_name
            meta['embedding_dimension'] = provider.dimension
            chunk_objs.append(
                ContentChunk(
                    content_item=item,
                    chunk_index=c['chunk_index'],
                    text=c['text'],
                    start_offset=c['start_offset'],
                    end_offset=c['end_offset'],
                    embedding=vec,
                    metadata=meta,
                    content_hash=compute_sha256(c['text']),
                    version=item.version
                )
            )

        item.ingestion_status = ContentItem.STATUS_INDEXING
        item.content_hash = compute_sha256(item.raw_text)
        item.save(update_fields=['ingestion_status', 'content_hash'])

        with transaction.atomic():
            item.chunks.all().delete()
            ContentChunk.objects.bulk_create(chunk_objs)
            index_item_facts(item, chunk_objs)

            item.ingestion_status = ContentItem.STATUS_COMPLETED
            item.error_message = ''
            item.metadata['chunk_count'] = len(chunk_objs)
            item.save(update_fields=['title', 'summary', 'raw_text', 'ingestion_status', 'content_hash', 'error_message', 'metadata'])

        logger.info(
            f"[DIAGNOSTIC] URL Ingestion Completed: item_id={item.id}, user_id={item.user_id}, "
            f"chunks={len(chunk_objs)}, dims={provider.dimension}, model={provider.model_name}"
        )

    except SSRFProtectionError as e:
        logger.error(f"[DIAGNOSTIC] SSRF violation on {item.source_url}: {e}")
        item.ingestion_status = ContentItem.STATUS_FAILED
        item.error_message = f"SSRF Security Violation: {str(e)}"
        item.save(update_fields=['ingestion_status', 'error_message'])
    except Exception as e:
        logger.exception(f"[DIAGNOSTIC] Error processing URL {item.source_url}: {e}")
        item.ingestion_status = ContentItem.STATUS_FAILED
        item.error_message = f"Processing failed: {str(e)}"
        item.save(update_fields=['ingestion_status', 'error_message'])
        if getattr(self, 'request', None) and getattr(self.request, 'id', None) and not getattr(self.request, 'called_directly', False):
            try:
                self.retry(exc=e)
            except self.MaxRetriesExceededError:
                pass

@shared_task(bind=True, max_retries=3, default_retry_delay=5, ignore_result=True)
def process_document_content(self, content_item_id: str):
    """
    Download uploaded file from MinIO, extract text (PDF/DOCX/PPTX/XLSX/CSV/TXT/MD), and generate chunks.
    """
    try:
        item = ContentItem.objects.get(id=content_item_id)
    except ContentItem.DoesNotExist as exc:
        if getattr(self, 'request', None) and getattr(self.request, 'retries', 0) < getattr(self, 'max_retries', 3):
            raise self.retry(exc=exc, countdown=1)
        logger.warning(f"ContentItem {content_item_id} not found.")
        return

    item.ingestion_status = ContentItem.STATUS_PROCESSING
    item.save(update_fields=['ingestion_status'])

    try:
        item.ingestion_status = ContentItem.STATUS_EXTRACTING
        item.save(update_fields=['ingestion_status'])

        file_bytes = download_file_bytes(item.file_key)
        filename = item.metadata.get('filename', '').lower()
        detected_format = item.metadata.get('detected_format', '').lower()

        # Format detection with extension and magic header fallback
        if filename.endswith('.pdf') or detected_format == 'pdf' or b'%PDF-' in file_bytes[:1024]:
            title, text, _ = extract_text_from_pdf(file_bytes)
        elif filename.endswith('.docx') or detected_format == 'docx':
            title, text, _ = extract_text_from_docx(file_bytes)
        elif filename.endswith('.pptx') or detected_format == 'pptx':
            title, text, _ = extract_text_from_pptx(file_bytes)
        elif filename.endswith('.xlsx') or detected_format == 'xlsx':
            title, text, _ = extract_text_from_xlsx(file_bytes)
        elif filename.endswith('.csv') or detected_format == 'csv':
            title, text, _ = extract_text_from_csv(file_bytes)
        else:
            title, text = extract_text_from_txt(file_bytes)

        if not item.title and title:
            item.title = title[:512]

        item.raw_text = text

        clean_text = (text or '').strip()
        if len(clean_text) < 10:
            if filename.endswith('.pdf') or detected_format == 'pdf' or b'%PDF-' in file_bytes[:1024]:
                logger.warning(f"[PDF] Scanned PDF or empty text in {item.file_key}")
                item.ingestion_status = ContentItem.STATUS_FAILED
                item.error_message = (
                    "This PDF appears to be a scanned document or image without embedded text. "
                    "OCR is required to extract and index scanned documents."
                )
                item.metadata['needs_ocr'] = True
                item.metadata['text_length'] = len(clean_text)
                item.save(update_fields=['ingestion_status', 'error_message', 'metadata'])
                return
            raise ValueError("Extracted document content is empty or contains no extractable text.")

        item.ingestion_status = ContentItem.STATUS_CHUNKING
        item.save(update_fields=['ingestion_status', 'title', 'raw_text'])

        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("No text chunks could be extracted from this document.")

        item.ingestion_status = ContentItem.STATUS_EMBEDDING
        item.save(update_fields=['ingestion_status'])

        from .embeddings import get_embedding_provider
        provider = get_embedding_provider()
        texts = [c['text'] for c in chunks]
        embeddings = provider.embed_batch(texts)

        chunk_objs = []
        for c, vec in zip(chunks, embeddings):
            meta = c.get('metadata', {})
            meta['char_length'] = c.get('char_length', len(c['text']))
            meta['embedding_model'] = provider.model_name
            meta['embedding_dimension'] = provider.dimension
            chunk_objs.append(
                ContentChunk(
                    content_item=item,
                    chunk_index=c['chunk_index'],
                    text=c['text'],
                    start_offset=c['start_offset'],
                    end_offset=c['end_offset'],
                    embedding=vec,
                    metadata=meta,
                    content_hash=compute_sha256(c['text']),
                    version=item.version
                )
            )

        item.ingestion_status = ContentItem.STATUS_INDEXING
        item.content_hash = compute_sha256(item.raw_text)
        item.save(update_fields=['ingestion_status', 'content_hash'])

        with transaction.atomic():
            item.chunks.all().delete()
            ContentChunk.objects.bulk_create(chunk_objs)
            index_item_facts(item, chunk_objs)

            item.ingestion_status = ContentItem.STATUS_COMPLETED
            item.error_message = ''
            item.metadata['chunk_count'] = len(chunk_objs)
            item.save(update_fields=['title', 'raw_text', 'ingestion_status', 'content_hash', 'error_message', 'metadata'])

        logger.info(
            f"[DIAGNOSTIC] Document Ingestion Completed: item_id={item.id}, user_id={item.user_id}, "
            f"chunks={len(chunk_objs)}, dims={provider.dimension}, model={provider.model_name}"
        )

    except Exception as e:
        logger.exception(f"[DIAGNOSTIC] Error processing document {item.file_key}: {e}")
        item.ingestion_status = ContentItem.STATUS_FAILED
        item.error_message = f"Document processing failed: {str(e)}"
        item.save(update_fields=['ingestion_status', 'error_message'])
        if getattr(self, 'request', None) and getattr(self.request, 'id', None) and not getattr(self.request, 'called_directly', False):
            if not isinstance(e, (ValueError, TypeError)):
                try:
                    self.retry(exc=e)
                except self.MaxRetriesExceededError:
                    pass

@shared_task(bind=True, max_retries=3, default_retry_delay=5, ignore_result=True)
def process_note_content(self, content_item_id: str):
    """
    Chunk and index a user-created plain text note.
    """
    try:
        item = ContentItem.objects.get(id=content_item_id)
    except ContentItem.DoesNotExist as exc:
        if getattr(self, 'request', None) and getattr(self.request, 'retries', 0) < getattr(self, 'max_retries', 3):
            raise self.retry(exc=exc, countdown=1)
        return

    item.ingestion_status = ContentItem.STATUS_PROCESSING
    item.save(update_fields=['ingestion_status'])

    try:
        clean_text = (item.raw_text or '').strip()
        if not clean_text:
            raise ValueError("Note content is empty.")

        item.ingestion_status = ContentItem.STATUS_CHUNKING
        item.save(update_fields=['ingestion_status'])

        chunks = chunk_text(item.raw_text)
        if not chunks:
            raise ValueError("No text chunks generated for note.")

        item.ingestion_status = ContentItem.STATUS_EMBEDDING
        item.save(update_fields=['ingestion_status'])

        from .embeddings import get_embedding_provider
        provider = get_embedding_provider()
        texts = [c['text'] for c in chunks]
        embeddings = provider.embed_batch(texts)

        chunk_objs = []
        for c, vec in zip(chunks, embeddings):
            meta = c.get('metadata', {})
            meta['char_length'] = c.get('char_length', len(c['text']))
            meta['embedding_model'] = provider.model_name
            meta['embedding_dimension'] = provider.dimension
            chunk_objs.append(
                ContentChunk(
                    content_item=item,
                    chunk_index=c['chunk_index'],
                    text=c['text'],
                    start_offset=c['start_offset'],
                    end_offset=c['end_offset'],
                    embedding=vec,
                    metadata=meta,
                    content_hash=compute_sha256(c['text']),
                    version=item.version
                )
            )

        item.ingestion_status = ContentItem.STATUS_INDEXING
        item.content_hash = compute_sha256(item.raw_text)
        item.save(update_fields=['ingestion_status', 'content_hash'])

        with transaction.atomic():
            item.chunks.all().delete()
            ContentChunk.objects.bulk_create(chunk_objs)
            index_item_facts(item, chunk_objs)

            item.ingestion_status = ContentItem.STATUS_COMPLETED
            item.error_message = ''
            item.metadata['chunk_count'] = len(chunk_objs)
            item.save(update_fields=['ingestion_status', 'content_hash', 'error_message', 'metadata'])

        logger.info(
            f"[DIAGNOSTIC] Note Ingestion Completed: item_id={item.id}, user_id={item.user_id}, "
            f"chunks={len(chunk_objs)}, dims={provider.dimension}, model={provider.model_name}"
        )
    except Exception as e:
        logger.exception(f"[DIAGNOSTIC] Error processing note {item.id}: {e}")
        item.ingestion_status = ContentItem.STATUS_FAILED
        item.error_message = f"Note processing failed: {str(e)}"
        item.save(update_fields=['ingestion_status', 'error_message'])
        if getattr(self, 'request', None) and getattr(self.request, 'id', None) and not getattr(self.request, 'called_directly', False):
            try:
                self.retry(exc=e)
            except self.MaxRetriesExceededError:
                pass

def _dispatch_embedding_task(chunk_ids: list):
    """Helper to dispatch embedding generation asynchronously with synchronous fallback."""
    if not chunk_ids:
        return
    try:
        generate_chunk_embeddings.delay(chunk_ids)
    except Exception:
        try:
            generate_chunk_embeddings(chunk_ids)
        except Exception as e:
            logger.warning(f"Could not generate embeddings synchronously: {e}")

@shared_task(bind=True, max_retries=3, default_retry_delay=5, ignore_result=True)
def generate_chunk_embeddings(self, chunk_ids: list):
    """
    Generate and store vector embeddings for the specified ContentChunks.
    Supports asynchronous execution with bounded retries and backoff.
    """
    import uuid
    from .embeddings import get_embedding_provider
    try:
        valid_uuids = []
        for cid in chunk_ids:
            try:
                valid_uuids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                pass

        if not valid_uuids:
            return

        provider = get_embedding_provider()
        chunks = list(ContentChunk.objects.filter(id__in=valid_uuids))
        if not chunks:
            return

        texts = [c.text for c in chunks]
        embeddings = provider.embed_batch(texts)

        with transaction.atomic():
            for chunk, vec in zip(chunks, embeddings):
                chunk.embedding = vec
                chunk.metadata['embedding_model'] = provider.model_name
                chunk.metadata['embedding_dimension'] = provider.dimension
                chunk.save(update_fields=['embedding', 'metadata'])

        logger.info(
            f"[DIAGNOSTIC] Embeddings generated for {len(chunks)} chunks: "
            f"dims={provider.dimension}, model={provider.model_name}"
        )
    except Exception as e:
        logger.exception(f"[DIAGNOSTIC] Failed to generate chunk embeddings: {e}")
        try:
            self.retry(exc=e)
        except (self.MaxRetriesExceededError, AttributeError):
            logger.error(f"[DIAGNOSTIC] Exceeded max retries generating embeddings for chunks: {chunk_ids}")

@shared_task(ignore_result=True)
def reembed_user_content(user_id: str):
    """
    Re-generate embeddings for all chunks belonging to a specific user (e.g. after model upgrade).
    """
    chunk_ids = list(ContentChunk.objects.filter(content_item__user_id=user_id).values_list('id', flat=True))
    for i in range(0, len(chunk_ids), 50):
        batch = [str(cid) for cid in chunk_ids[i:i+50]]
        _dispatch_embedding_task(batch)
