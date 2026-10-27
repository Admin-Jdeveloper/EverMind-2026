"""
MediaCompile — Library Export and Bulk Import Service.
Source of Truth: MediaCompile-prompt.md (Section 19: Phase 9 — Export correctness & import round-trips)

Enforces:
1. Strict User Isolation: Exports only the authenticated user's private items, memories, and chat history.
2. Complete Fidelity: Serializes collections, tags, content items, vector chunks, offsets, and metadata.
3. Round-Trip Idempotency: Restores library data without creating duplicate records.
"""

import json
import logging
from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from .models import ContentItem, ContentChunk, Collection, Tag
from .services import chunk_text
from .embeddings import get_embedding_provider
from chat.models import UserMemory, ChatSession, ChatMessage

logger = logging.getLogger(__name__)

def export_user_library(user) -> Dict[str, Any]:
    """Generate a complete, sovereign export manifest of the user's library."""
    # 1. Collections
    collections = []
    for col in Collection.objects.filter(user=user):
        collections.append({
            "id": str(col.id),
            "name": col.name,
            "description": col.description,
            "is_private": col.is_private,
        })

    # 2. Tags
    tags = []
    for tag in Tag.objects.filter(user=user):
        tags.append({
            "id": str(tag.id),
            "name": tag.name,
            "color": tag.color,
        })

    # 3. Content Items & Vector Chunks
    items = []
    for item in ContentItem.objects.filter(user=user).select_related('collection').prefetch_related('tags', 'chunks'):
        chunks_data = []
        for ch in item.chunks.all():
            chunks_data.append({
                "chunk_index": ch.chunk_index,
                "text": ch.text,
                "start_offset": ch.start_offset,
                "end_offset": ch.end_offset,
            })

        items.append({
            "id": str(item.id),
            "content_type": item.content_type,
            "source_url": item.source_url,
            "title": item.title,
            "raw_text": item.raw_text,
            "collection_name": item.collection.name if item.collection else None,
            "tags": [t.name for t in item.tags.all()],
            "metadata": item.metadata,
            "chunks": chunks_data,
            "created_at": item.created_at.isoformat(),
        })

    # 4. User Memories
    memories = []
    for m in UserMemory.objects.filter(user=user):
        memories.append({
            "id": str(m.id),
            "memory_text": m.memory_text,
            "category": m.category,
            "is_explicit": m.is_explicit,
            "is_active": m.is_active,
            "provenance": m.provenance,
            "created_at": m.created_at.isoformat(),
        })

    # 5. Chat Sessions
    chat_sessions = []
    for session in ChatSession.objects.filter(user=user).prefetch_related('messages'):
        msgs = []
        for msg in session.messages.all():
            msgs.append({
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations,
                "created_at": msg.created_at.isoformat(),
            })
        chat_sessions.append({
            "id": str(session.id),
            "title": session.title,
            "messages": msgs,
            "created_at": session.created_at.isoformat(),
        })

    return {
        "manifest_version": "1.0",
        "exported_at": timezone.now().isoformat(),
        "user_email": user.email,
        "collections": collections,
        "tags": tags,
        "items": items,
        "memories": memories,
        "chat_sessions": chat_sessions,
        "total_items": len(items),
    }

def import_user_library(user, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Idempotently restore user library items, collections, tags, and memories from export manifest."""
    provider = get_embedding_provider()
    collections_created = 0
    tags_created = 0
    items_synced = 0
    items_skipped = 0
    memories_created = 0

    with transaction.atomic():
        # 1. Restore Collections
        col_map = {}
        for col_data in manifest.get("collections", []):
            name = col_data.get("name", "").strip()
            if not name:
                continue
            col, created = Collection.objects.get_or_create(
                user=user,
                name=name,
                defaults={
                    "description": col_data.get("description", ""),
                    "is_private": col_data.get("is_private", True),
                }
            )
            col_map[name] = col
            if created:
                collections_created += 1

        # 2. Restore Tags
        tag_map = {}
        for tag_data in manifest.get("tags", []):
            name = tag_data.get("name", "").strip()
            if not name:
                continue
            tag, created = Tag.objects.get_or_create(
                user=user,
                name=name,
                defaults={"color": tag_data.get("color", "#3B82F6")}
            )
            tag_map[name] = tag
            if created:
                tags_created += 1

        # 3. Restore Content Items
        for it_data in manifest.get("items", []):
            url = it_data.get("source_url", "").strip()
            title = it_data.get("title", "").strip() or "Untitled Item"
            raw_text = it_data.get("raw_text", "")
            content_type = it_data.get("content_type", ContentItem.TYPE_NOTE)

            # Deduplication
            if url and ContentItem.objects.filter(user=user, source_url=url).exists():
                items_skipped += 1
                continue
            if not url and ContentItem.objects.filter(user=user, title=title, raw_text=raw_text).exists():
                items_skipped += 1
                continue

            col_name = it_data.get("collection_name")
            collection = col_map.get(col_name) if col_name else None

            item = ContentItem.objects.create(
                user=user,
                content_type=content_type,
                source_url=url,
                title=title,
                raw_text=raw_text,
                collection=collection,
                metadata=it_data.get("metadata", {}),
                ingestion_status=ContentItem.STATUS_COMPLETED
            )

            # Assign tags
            item_tags = [tag_map[tn] for tn in it_data.get("tags", []) if tn in tag_map]
            if item_tags:
                item.tags.set(item_tags)

            # Restore or generate chunks
            manifest_chunks = it_data.get("chunks", [])
            if manifest_chunks:
                for ch in manifest_chunks:
                    emb = provider.embed_text(ch["text"])
                    ContentChunk.objects.create(
                        content_item=item,
                        chunk_index=ch["chunk_index"],
                        text=ch["text"],
                        start_offset=ch.get("start_offset", 0),
                        end_offset=ch.get("end_offset", len(ch["text"])),
                        embedding=emb
                    )
            else:
                chunks = chunk_text(raw_text, chunk_size=500, chunk_overlap=50)
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

            items_synced += 1

        # 4. Restore Memories
        for mem_data in manifest.get("memories", []):
            text = mem_data.get("memory_text", "").strip()
            if not text:
                continue
            if UserMemory.objects.filter(user=user, memory_text=text).exists():
                continue
            UserMemory.objects.create(
                user=user,
                memory_text=text,
                category=mem_data.get("category", "general"),
                is_explicit=mem_data.get("is_explicit", True),
                is_active=mem_data.get("is_active", True),
                provenance=mem_data.get("provenance", {"source": "Imported archive"})
            )
            memories_created += 1

    return {
        "success": True,
        "collections_created": collections_created,
        "tags_created": tags_created,
        "items_synced": items_synced,
        "items_skipped": items_skipped,
        "memories_created": memories_created,
    }
