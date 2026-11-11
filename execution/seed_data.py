#!/usr/bin/env python3
"""
MediaCompile — Seed Data Generator.
Source of Truth: MediaCompile-prompt.md (Section 21: Phase 11 — Seed Data & Testing)

Populates a deterministic, comprehensive demo environment:
- Demo User: demo@mediacompile.io
- Collections: Distributed Systems, AI & Transformers, Database Engineering
- ContentItems: Notes, URLs, and Documents with pre-computed vector chunks & embeddings
- User Memories: Research preferences and learning profiles
- Chat Sessions: Grounded conversations with verifiable citations
- Saved Searches: Pre-configured search filters
"""

import sys
import os

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
sys.path.insert(0, API_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from content.models import Collection, Tag, ContentItem, ContentChunk, SavedSearch
from content.embeddings import get_embedding_provider
from chat.models import ChatSession, ChatMessage, UserMemory, UserPreference

User = get_user_model()

def seed_demo_library():
    print("===> Seeding MediaCompile Demo Library...")

    # 1. Create or retrieve demo user
    demo_email = "demo@mediacompile.io"
    user, created = User.objects.get_or_create(
        email=demo_email,
        defaults={
            "username": demo_email,
            "name": "Demo User",
            "is_active": True
        }
    )
    user.set_password("Password123!")
    user.save()
    print(f"[{'CREATED' if created else 'EXISTS'}] Demo user: {user.email}")

    # 2. Collections
    col_dist, _ = Collection.objects.get_or_create(
        user=user,
        name="Distributed Systems",
        defaults={"description": "Consensus, replication, and fault tolerance"}
    )
    col_ai, _ = Collection.objects.get_or_create(
        user=user,
        name="AI & Transformers",
        defaults={"description": "Transformer architectures, RAG, and vector search"}
    )
    col_db, _ = Collection.objects.get_or_create(
        user=user,
        name="Database Engineering",
        defaults={"description": "PostgreSQL indexing, transaction models, and pgvector"}
    )

    # 3. Tags
    tags = {}
    tag_names = ["consensus", "raft", "paxos", "transformers", "pgvector", "storage", "rag"]
    for tname in tag_names:
        tag, _ = Tag.objects.get_or_create(user=user, name=tname)
        tags[tname] = tag

    provider = get_embedding_provider()

    # 4. Content Items & Vector Chunks
    items_data = [
        {
            "title": "In Search of an Understandable Consensus Algorithm (Raft)",
            "content_type": ContentItem.TYPE_URL,
            "source_url": "https://raft.github.io/raft.pdf",
            "collection": col_dist,
            "tags": ["consensus", "raft", "storage"],
            "raw_text": (
                "Raft is a consensus algorithm for managing a replicated log. It produces a result equivalent to Paxos, "
                "and it is as efficient as Paxos, but its structure is different: Raft separates key elements of consensus, "
                "such as leader election, log replication, and safety, to enhance understandability. In Raft, a leader is "
                "first elected, then given complete responsibility for managing the replicated log."
            )
        },
        {
            "title": "Attention Is All You Need (Transformer Architecture)",
            "content_type": ContentItem.TYPE_URL,
            "source_url": "https://arxiv.org/abs/1706.03762",
            "collection": col_ai,
            "tags": ["transformers", "rag"],
            "raw_text": (
                "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. "
                "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, "
                "dispensing with recurrence and convolutions entirely. Experiments show these models to be superior in quality "
                "while being more parallelizable and requiring significantly less training time."
            )
        },
        {
            "title": "PostgreSQL pgvector HNSW Indexing Architecture",
            "content_type": ContentItem.TYPE_NOTE,
            "source_url": "",
            "collection": col_db,
            "tags": ["pgvector", "storage"],
            "raw_text": (
                "pgvector implements vector similarity search inside PostgreSQL. The HNSW (Hierarchical Navigable Small World) "
                "index constructs a multi-layer graph for fast approximate nearest neighbor (ANN) retrieval with cosine distance. "
                "Key tuning parameters include m (max outgoing connections per node, default 16) and ef_construction (search size "
                "during index build, default 64). Increasing ef_construction improves query recall at the cost of build time."
            )
        }
    ]

    for data in items_data:
        item, it_created = ContentItem.objects.get_or_create(
            user=user,
            title=data["title"],
            defaults={
                "content_type": data["content_type"],
                "source_url": data["source_url"],
                "collection": data["collection"],
                "raw_text": data["raw_text"],
                "ingestion_status": ContentItem.STATUS_COMPLETED
            }
        )
        if it_created:
            for tname in data["tags"]:
                item.tags.add(tags[tname])

            # Generate chunk & embedding
            emb = provider.embed_text(data["raw_text"])
            ContentChunk.objects.create(
                content_item=item,
                chunk_index=0,
                text=data["raw_text"],
                start_offset=0,
                end_offset=len(data["raw_text"]),
                embedding=emb
            )
            print(f"[CREATED] Item & Chunk: {item.title}")

    # 5. User Memories & Preferences
    UserPreference.objects.get_or_create(
        user=user,
        defaults={"personalization_enabled": True}
    )
    UserMemory.objects.get_or_create(
        user=user,
        memory_text="Prefers rigorous architectural explanations and algorithmic comparisons.",
        defaults={"category": "learning", "is_explicit": True, "is_active": True}
    )

    # 6. Saved Search
    SavedSearch.objects.get_or_create(
        user=user,
        name="Consensus & Replication",
        defaults={
            "query_text": "consensus raft paxos replicated log",
            "filters": {"tag": "consensus"}
        }
    )

    # 7. Demo Chat Session
    session, s_created = ChatSession.objects.get_or_create(
        user=user,
        title="Distributed Consensus Exploration",
        defaults={}
    )
    if s_created:
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content="How does Raft simplify consensus compared to Paxos?"
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=(
                "Raft simplifies consensus primarily by decomposing the problem into discrete, independent subproblems: "
                "leader election, log replication, and safety [Source 1]. By establishing a strong, elected leader that "
                "unidirectionally replicates log entries to follower nodes, Raft removes the state machine symmetry that makes Paxos complex."
            ),
            citations=[
                {
                    "source_number": 1,
                    "title": "In Search of an Understandable Consensus Algorithm (Raft)",
                    "chunk_id": "chunk-demo-raft-0",
                    "source_url": "https://raft.github.io/raft.pdf",
                    "text_excerpt": "Raft separates key elements of consensus, such as leader election, log replication, and safety, to enhance understandability."
                }
            ]
        )
        print(f"[CREATED] Demo Chat Session with citations: {session.title}")

    print("===> Seeding completed successfully.")

if __name__ == '__main__':
    seed_demo_library()
