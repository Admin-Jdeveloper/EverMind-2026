"""
MediaCompile — Hybrid Search & Retrieval Engine with Structured Fact Fusion.
Source of Truth: MediaCompile-prompt.md (Step 4: Hybrid Retrieval, Step 5: Structured Facts)

Features:
1. Multi-Tenant Isolation: Strictly user-scoped (content_item__user=user).
2. Lexical / Keyword Search: Full-text keyword search across ContentChunk & ContentItem with query expansion.
3. Vector / Semantic Search: pgvector CosineDistance on ContentChunk embeddings (all-MiniLM-L6-v2 384-dim).
4. True Reciprocal Rank Fusion (RRF): Combines structured fact matches, lexical rank, and vector rank.
   RRF score = FactBonus + 1.0/(60 + lex_rank) + 1.0/(60 + vec_rank).
5. Query Understanding & Expansion: Bridges acronyms and synonyms (e.g., DOB <-> date of birth <-> born).
6. Conflict Transparency: Surfaces conflicting values across sources when disagreements exist.
7. Provenance Preservation: Returns chunk text, character offsets, chunk index, parent item metadata.
"""

import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from django.db import DatabaseError
from django.db.models import Q, F
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from pgvector.django import CosineDistance

from .models import ContentItem, ContentChunk
from .embeddings import get_embedding_provider, EmbeddingError
from .facts import find_facts_for_query, SYNONYM_ATTRIBUTE_MAP

logger = logging.getLogger(__name__)


class RetrievalInfrastructureError(Exception):
    """Raised when library retrieval fails due to database, embedding, or indexing infrastructure failure."""
    pass


STOP_WORDS = {
    "the", "is", "at", "which", "on", "in", "a", "an", "and", "or", "of", "to", "for",
    "with", "as", "by", "from", "it", "this", "that", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "what", "who", "where", "when", "why",
    "how", "all", "any", "both", "each", "few", "more", "most", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
    "about", "into", "through", "during", "before", "after", "above", "below", "my", "your",
    "tell", "me", "discuss", "explain", "describe", "according", "saved", "notes", "library"
}


def expand_query_terms(query_text: str) -> List[str]:
    """
    Expand query with synonym phrases and acronym expansions.
    For example:
    - 'DOB' -> ['date of birth', 'born', 'birth date', 'birthday']
    - 'born' -> ['date of birth', 'dob', 'birthday']
    - 'passport' -> ['passport number']
    - 'ssn' -> ['social security']
    - 'salary' -> ['compensation', 'pay']
    """
    q_lower = query_text.lower()
    expansions = []

    if "dob" in q_lower or "d.o.b" in q_lower:
        expansions.extend(["date of birth", "born", "birth date", "birthday"])
    elif "born" in q_lower or "birthday" in q_lower:
        expansions.extend(["date of birth", "dob", "birth date"])

    if "ssn" in q_lower:
        expansions.append("social security")
    if "passport" in q_lower:
        expansions.append("passport number")
    if "salary" in q_lower:
        expansions.extend(["compensation", "pay", "wage"])
    if "phone" in q_lower:
        expansions.extend(["telephone", "mobile", "cell"])
    if "invoice" in q_lower:
        expansions.extend(["amount", "total", "invoice number"])
    if "database" in q_lower or "databases" in q_lower or "db" in q_lower:
        expansions.extend(["database", "databases", "db", "postgresql", "postgres", "mongodb", "mongo", "sql", "nosql"])

    # Technical Framework & Library Aliasing (.js vs bare name)
    import re
    for token in re.findall(r'\b[a-zA-Z0-9_\.-]+\b', q_lower):
        clean_tok = token.strip(".,?!:;\"'()[]{}")
        if clean_tok.endswith(".js") and len(clean_tok) > 3:
            base = clean_tok[:-3]
            expansions.extend([base, f"{base}.js"])
        elif clean_tok in ("react", "node", "vue", "next", "nuxt", "express", "angular", "ember", "svelte"):
            expansions.extend([clean_tok, f"{clean_tok}.js"])

    # Resume & Skills lexical bridging
    if any(k in q_lower for k in ("resume", "cv", "skill", "skills", "experience", "background")):
        expansions.extend(["resume", "cv", "skills", "skill", "experience", "technologies", "proficiencies"])

    return expansions


def filter_content_chunks(
    queryset,
    user,
    content_type: Optional[str] = None,
    collection_id: Optional[str] = None,
    item_ids: Optional[List[Any]] = None,
    page_number: Optional[int] = None,
    tags: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    **kwargs
):
    qs = queryset.filter(
        content_item__user=user,
        content_item__ingestion_status__in=[ContentItem.STATUS_COMPLETED, ContentItem.STATUS_PARTIAL]
    )

    if item_ids:
        clean_uuids = []
        for iid in item_ids:
            try:
                clean_uuids.append(uuid.UUID(str(iid)))
            except (ValueError, TypeError):
                pass
        if clean_uuids:
            qs = qs.filter(content_item_id__in=clean_uuids)

    if page_number is not None:
        qs = qs.filter(metadata__page_number=int(page_number))

    if content_type:
        qs = qs.filter(content_item__content_type=content_type)

    if collection_id:
        try:
            col_uuid = uuid.UUID(str(collection_id))
            qs = qs.filter(content_item__collection_id=col_uuid)
        except (ValueError, TypeError):
            pass

    if tags:
        qs = qs.filter(content_item__tags__name__in=tags).distinct()

    if date_from:
        try:
            df = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            qs = qs.filter(content_item__created_at__gte=df)
        except Exception:
            pass

    if date_to:
        try:
            dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            qs = qs.filter(content_item__created_at__lte=dt)
        except Exception:
            pass

    return qs


def lexical_search_chunks(
    user,
    query_text: str,
    limit: int = 50,
    **filters
) -> List[Dict[str, Any]]:
    """
    Perform full-text keyword search across content chunks and parent items.
    Incorporates query expansion to bridge acronyms (e.g. DOB <-> date of birth).
    """
    if not query_text or not query_text.strip():
        return []

    clean_query = query_text.strip()
    base_qs = filter_content_chunks(ContentChunk.objects.all(), user, **filters)

    raw_tokens = [w.strip(".,?!:;\"'()[]{}") for w in clean_query.lower().split()]
    words = []
    for w in raw_tokens:
        if len(w) >= 3 and w not in STOP_WORDS:
            if w not in words:
                words.append(w)
            if "." in w:
                for sub in w.split("."):
                    if len(sub) >= 3 and sub not in STOP_WORDS and sub not in words:
                        words.append(sub)
    if not words:
        words = [w for w in raw_tokens if len(w) >= 2] or [clean_query.lower()]

    expanded_phrases = expand_query_terms(clean_query)

    # Match chunks containing query terms or expanded phrases across text, title, summary, or tags
    q_filter = Q()
    for w in words:
        q_filter |= (
            Q(text__icontains=w) |
            Q(content_item__title__icontains=w) |
            Q(content_item__summary__icontains=w) |
            Q(content_item__tags__name__iexact=w)
        )

    for p in expanded_phrases:
        q_filter |= (
            Q(text__icontains=p) |
            Q(content_item__title__icontains=p)
        )

    try:
        matching_chunks = list(
            base_qs.filter(q_filter)
            .select_related('content_item', 'content_item__collection')
            .prefetch_related('content_item__tags')
            .distinct()[:limit]
        )
    except DatabaseError as e:
        logger.error(f"[DIAGNOSTIC] Database error during lexical search: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Database error during lexical retrieval: {e}") from e

    # Score and rank matching chunks by term occurrence density
    scored_chunks = []
    clean_lower = clean_query.lower()
    for chunk in matching_chunks:
        text_lower = (chunk.text + " " + (chunk.content_item.title or "")).lower()
        match_count = sum(1 for w in words if w.lower() in text_lower)
        exact_bonus = 2 if clean_lower in text_lower else 0
        phrase_bonus = sum(2 for p in expanded_phrases if p in text_lower)
        relevance = match_count + exact_bonus + phrase_bonus
        scored_chunks.append((relevance, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    results = []
    for rank_idx, (relevance, chunk) in enumerate(scored_chunks, start=1):
        results.append({
            "chunk": chunk,
            "lexical_rank": rank_idx,
            "lexical_score": round(1.0 / (rank_idx + 1), 4)
        })

    logger.info(
        f"[DIAGNOSTIC] Lexical search: user={user.id}, query='{query_text[:50]}', "
        f"matches_found={len(results)}"
    )
    return results


def vector_search_chunks(
    user,
    query_text: str,
    limit: int = 50,
    min_similarity: float = 0.30,
    **filters
) -> List[Dict[str, Any]]:
    """
    Perform semantic vector similarity search via pgvector CosineDistance.
    """
    if not query_text or not query_text.strip():
        return []

    try:
        provider = get_embedding_provider()
        query_vector = provider.embed_text(query_text.strip())
    except EmbeddingError as e:
        logger.error(f"[DIAGNOSTIC] Embedding service failure: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Embedding service failure: {e}") from e
    except Exception as e:
        logger.error(f"[DIAGNOSTIC] Unexpected embedding provider failure: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Embedding service failure: {e}") from e

    try:
        base_qs = filter_content_chunks(
            ContentChunk.objects.filter(embedding__isnull=False),
            user,
            **filters
        )

        chunks_with_distance = list(
            base_qs.annotate(distance=CosineDistance('embedding', query_vector))
            .order_by('distance')
            .select_related('content_item', 'content_item__collection')
            .prefetch_related('content_item__tags')[:limit]
        )
    except DatabaseError as e:
        logger.error(f"[DIAGNOSTIC] Database error during vector search: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Database error during vector retrieval: {e}") from e


    results = []
    rank_idx = 1
    for chunk in chunks_with_distance:
        similarity = max(0.0, round(1.0 - float(chunk.distance), 4))
        if similarity >= min_similarity:
            results.append({
                "chunk": chunk,
                "vector_rank": rank_idx,
                "similarity": similarity
            })
            rank_idx += 1

    top_sim = results[0]["similarity"] if results else "N/A"
    top_chunk_id = str(results[0]["chunk"].id) if results else "None"
    logger.info(
        f"[DIAGNOSTIC] Vector search: user={user.id}, query='{query_text[:50]}', "
        f"candidates={len(chunks_with_distance)}, min_similarity={min_similarity}, "
        f"returned={len(results)}, top_similarity={top_sim}, top_chunk_id={top_chunk_id}"
    )

    return results


def hybrid_retrieve_with_facts(
    user,
    query_text: str,
    limit: int = 20,
    min_similarity: float = 0.30,
    expand_window: bool = True,
    rerank: bool = True,
    **filters
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Multi-stage hybrid retrieval engine:
    1. Structured Fact Matching: Resolves exact attributes (DOB, dates, amounts, IDs).
    2. Reciprocal Rank Fusion: Merges lexical full-text and semantic pgvector ranks.
    3. Conflict Detection: Identifies disagreeing values across distinct sources.
    
    Returns:
    (formatted_chunks, matching_facts, conflict_report)
    """
    clean_query = query_text.strip() if query_text else ""

    if not clean_query:
        base_qs = filter_content_chunks(ContentChunk.objects.all(), user, **filters)
        recent_chunks = (
            base_qs.select_related('content_item', 'content_item__collection')
            .prefetch_related('content_item__tags')
            .order_by('-created_at')[:limit]
        )
        results = [format_chunk_result(c, score=1.0, mode="recent") for c in recent_chunks]
        return results, [], None

    # Step 1: Structured Fact Search
    try:
        facts_list, conflict_report = find_facts_for_query(user, clean_query)
    except DatabaseError as e:
        logger.error(f"[DIAGNOSTIC] Database error during fact search: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Database error during fact retrieval: {e}") from e

    # Step 2: Lexical & Vector Search
    lex_results = lexical_search_chunks(user, clean_query, limit=limit * 2, **filters)
    vec_results = vector_search_chunks(user, clean_query, limit=limit * 2, min_similarity=min_similarity, **filters)

    # Step 3: Reciprocal Rank Fusion (RRF) with Structured Fact Boost
    # Constant k = 60
    K_RRF = 60.0
    chunk_data_map: Dict[str, Dict[str, Any]] = {}

    # Map lexical ranks
    for item in lex_results:
        chunk = item["chunk"]
        cid = str(chunk.id)
        rank = item["lexical_rank"]
        chunk_data_map.setdefault(cid, {
            "chunk": chunk,
            "lex_rank": rank,
            "vec_rank": None,
            "similarity": 0.0,
            "fact_match": None,
            "score": 0.0,
            "modes": []
        })
        chunk_data_map[cid]["lex_rank"] = rank
        chunk_data_map[cid]["score"] += 1.0 / (K_RRF + rank)
        chunk_data_map[cid]["modes"].append("keyword")

    # Map vector ranks
    for item in vec_results:
        chunk = item["chunk"]
        cid = str(chunk.id)
        rank = item["vector_rank"]
        sim = item.get("similarity", 0.0)
        chunk_data_map.setdefault(cid, {
            "chunk": chunk,
            "lex_rank": None,
            "vec_rank": rank,
            "similarity": sim,
            "fact_match": None,
            "score": 0.0,
            "modes": []
        })
        chunk_data_map[cid]["vec_rank"] = rank
        chunk_data_map[cid]["similarity"] = sim
        chunk_data_map[cid]["score"] += 1.0 / (K_RRF + rank)
        if "semantic" not in chunk_data_map[cid]["modes"]:
            chunk_data_map[cid]["modes"].append("semantic")

    # Step 2.5: Exact Title & Filename Matcher Boost
    try:
        exact_items = exact_item_title_search(user, clean_query)
        for e_item in exact_items:
            if e_item.ingestion_status in (ContentItem.STATUS_COMPLETED, ContentItem.STATUS_PARTIAL):
                e_chunks = list(
                    ContentChunk.objects.filter(content_item=e_item)
                    .select_related('content_item', 'content_item__collection')
                    .prefetch_related('content_item__tags')[:3]
                )
                for c_obj in e_chunks:
                    cid = str(c_obj.id)
                    chunk_data_map.setdefault(cid, {
                        "chunk": c_obj,
                        "lex_rank": 1,
                        "vec_rank": None,
                        "similarity": 1.0,
                        "fact_match": None,
                        "score": 0.0,
                        "modes": []
                    })
                    chunk_data_map[cid]["score"] += 2.0
                    if "exact_title" not in chunk_data_map[cid]["modes"]:
                        chunk_data_map[cid]["modes"].insert(0, "exact_title")
    except Exception as e:
        logger.warning(f"[DIAGNOSTIC] Error during exact title boost: {e}")

    # Map structured fact boosts
    for fact in facts_list:
        chunk_id = fact.get("chunk_id")
        item_id = fact.get("item_id")

        if chunk_id and chunk_id in chunk_data_map:
            chunk_data_map[chunk_id]["score"] += 1.0  # Massive boost for verified exact-fact match
            chunk_data_map[chunk_id]["fact_match"] = fact
            if "fact" not in chunk_data_map[chunk_id]["modes"]:
                chunk_data_map[chunk_id]["modes"].insert(0, "fact")
        elif chunk_id:
            # Chunk exists in fact index but wasn't in top lexical/vector
            try:
                c_obj = ContentChunk.objects.select_related('content_item', 'content_item__collection').prefetch_related('content_item__tags').get(id=chunk_id)
                chunk_data_map[chunk_id] = {
                    "chunk": c_obj,
                    "lex_rank": None,
                    "vec_rank": None,
                    "similarity": 1.0,
                    "fact_match": fact,
                    "score": 1.5,
                    "modes": ["fact"]
                }
            except ContentChunk.DoesNotExist:
                pass
        elif item_id:
            # Fact was attached to item without specific chunk -> pull item's first chunk
            first_chunk = ContentChunk.objects.filter(content_item_id=item_id).select_related('content_item', 'content_item__collection').prefetch_related('content_item__tags').first()
            if first_chunk:
                fc_id = str(first_chunk.id)
                chunk_data_map.setdefault(fc_id, {
                    "chunk": first_chunk,
                    "lex_rank": None,
                    "vec_rank": None,
                    "similarity": 1.0,
                    "fact_match": fact,
                    "score": 1.5,
                    "modes": ["fact"]
                })
                chunk_data_map[fc_id]["score"] += 1.0
                chunk_data_map[fc_id]["fact_match"] = fact

    # Filter out entries that have neither keyword match nor fact match and low vector similarity
    meaningful_entries = []
    for entry in chunk_data_map.values():
        if entry.get("fact_match"):
            meaningful_entries.append(entry)
        elif entry.get("lex_rank") is not None:
            meaningful_entries.append(entry)
        elif entry.get("similarity", 0.0) >= min_similarity:
            meaningful_entries.append(entry)

    # Sort candidates by combined fusion score descending
    sorted_entries = sorted(meaningful_entries, key=lambda x: x["score"], reverse=True)
    top_entries = sorted_entries[:limit]


    # If strict page filtering produced 0 results, fall back to broader search
    if not sorted_entries and filters.get("page_number") is not None:
        relaxed_filters = dict(filters)
        relaxed_filters.pop("page_number", None)
        logger.info(f"[DIAGNOSTIC] Page-specific search returned 0 matches, relaxing page filter for query: '{clean_query[:50]}'")
        return hybrid_retrieve_with_facts(
            user=user,
            query_text=query_text,
            limit=limit,
            min_similarity=min_similarity,
            expand_window=expand_window,
            **relaxed_filters
        )

    formatted_results = []
    for entry in top_entries:
        mode_str = "+".join(entry["modes"]) if entry["modes"] else "hybrid"
        res = format_chunk_result(
            chunk=entry["chunk"],
            score=round(entry["score"], 4),
            mode=mode_str,
            lexical_rank=entry["lex_rank"],
            vector_rank=entry["vec_rank"]
        )
        if entry["fact_match"]:
            res["fact_match"] = entry["fact_match"]
        formatted_results.append(res)

    # Optional Sibling Chunk Window Expansion
    if expand_window and formatted_results:
        formatted_results = expand_chunk_windows(formatted_results, window=1)

    # Optional Multi-Aspect Candidate Reranking
    if rerank and formatted_results and clean_query:
        formatted_results = rerank_candidates(clean_query, formatted_results, enabled=True)

    logger.info(
        f"[DIAGNOSTIC] Hybrid RRF search: user={user.id}, query='{clean_query[:50]}', "
        f"facts_found={len(facts_list)}, conflict={bool(conflict_report)}, "
        f"lex_hits={len(lex_results)}, vec_hits={len(vec_results)}, returned={len(formatted_results)}"
    )

    return formatted_results, facts_list, conflict_report


def rerank_candidates(
    query_text: str,
    candidates: List[Dict[str, Any]],
    enabled: bool = True
) -> List[Dict[str, Any]]:
    """
    Rerank candidate chunks using lexical-semantic term cross-matching.
    Scores candidates by query term density, exact phrase matching, and fact bonuses.
    Falls back gracefully to input candidate order if reranker fails or is disabled.
    """
    if not enabled or not candidates or not query_text:
        return candidates

    try:
        q_tokens = [w.lower().strip(".,?!:;\"'()") for w in query_text.split() if len(w) >= 3]
        clean_q = query_text.strip().lower()

        reranked = []
        for rank_pos, cand in enumerate(candidates):
            text = cand.get("text", "").lower()
            title = cand.get("item", {}).get("title", "").lower()
            combined = f"{title} {text}"

            # 1. Exact phrase boost
            exact_match_score = 0.5 if clean_q in combined else 0.0

            # 2. Token overlap ratio
            token_matches = sum(1 for tok in q_tokens if tok in combined)
            token_ratio = (token_matches / max(1, len(q_tokens))) * 0.3

            # 3. Existing RRF score contribution
            base_rrf = cand.get("score", 0.0)

            # 4. Fact match bonus
            fact_bonus = 0.5 if cand.get("fact_match") else 0.0

            rerank_score = round(base_rrf + exact_match_score + token_ratio + fact_bonus, 4)
            cand_copy = dict(cand)
            cand_copy["rerank_score"] = rerank_score
            cand_copy["original_rank"] = rank_pos + 1
            reranked.append(cand_copy)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked
    except Exception as e:
        logger.warning(f"Reranker failed, falling back to RRF order: {e}")
        return candidates


def expand_chunk_windows(chunks: List[Dict[str, Any]], window: int = 1) -> List[Dict[str, Any]]:
    """
    Expand chunk context by stitching sibling chunks (C_{i-1}, C_{i+1}) from the same document.
    Ensures sentences that cross chunk boundaries are not truncated.
    """
    if not chunks or window <= 0:
        return chunks

    expanded = []
    for hit in chunks:
        chunk_idx = hit.get("chunk_index")
        item_id = hit.get("item", {}).get("id")
        original_text = hit.get("text", "")

        if chunk_idx is not None and item_id:
            try:
                prev_text = ContentChunk.objects.filter(
                    content_item_id=item_id,
                    chunk_index=chunk_idx - 1
                ).values_list('text', flat=True).first() if chunk_idx > 0 else None

                next_text = ContentChunk.objects.filter(
                    content_item_id=item_id,
                    chunk_index=chunk_idx + 1
                ).values_list('text', flat=True).first()

                combined_parts = []
                if prev_text:
                    prev_sentences = [s.strip() for s in prev_text.strip().split(". ") if s.strip()]
                    if prev_sentences:
                        combined_parts.append(prev_sentences[-1])
                combined_parts.append(original_text)
                if next_text:
                    next_sentences = [s.strip() for s in next_text.strip().split(". ") if s.strip()]
                    if next_sentences:
                        combined_parts.append(next_sentences[0])

                hit_copy = dict(hit)
                if len(combined_parts) > 1:
                    hit_copy["text"] = " ".join(combined_parts)
                    hit_copy["is_expanded"] = True
                expanded.append(hit_copy)
                continue
            except Exception as e:
                logger.debug(f"Window expansion skipped for chunk: {e}")

        expanded.append(hit)

    return expanded


def vector_search(
    user,
    query_text: str,
    limit: int = 20,
    min_similarity: float = 0.05,
    **filters
) -> List[Dict[str, Any]]:
    """
    Standard hybrid search entrypoint for backward compatibility.
    Invokes true hybrid RRF retrieval with structured fact integration.
    """
    results, _, _ = hybrid_retrieve_with_facts(
        user=user,
        query_text=query_text,
        limit=limit,
        min_similarity=min_similarity,
        **filters
    )
    return results


# Backward compatibility alias
hybrid_search = vector_search


def format_chunk_result(
    chunk: ContentChunk,
    score: float,
    mode: str,
    lexical_rank: Optional[int] = None,
    vector_rank: Optional[int] = None
) -> Dict[str, Any]:
    """Format ContentChunk and parent ContentItem into client API response structure."""
    item = chunk.content_item
    collection_data = None
    if item.collection:
        collection_data = {
            "id": str(item.collection.id),
            "name": item.collection.name
        }

    tags_data = [
        {"id": str(t.id), "name": t.name, "color": t.color}
        for t in item.tags.all()
    ]

    chunk_meta = chunk.metadata or {}
    return {
        "chunk_id": str(chunk.id),
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "score": score,
        "retrieval_mode": mode,
        "lexical_rank": lexical_rank,
        "vector_rank": vector_rank,
        "metadata": chunk_meta,
        "page_number": chunk_meta.get("page_number"),
        "slide_number": chunk_meta.get("slide_number"),
        "sheet_name": chunk_meta.get("sheet_name"),
        "item": {
            "id": str(item.id),
            "title": item.title,
            "content_type": item.content_type,
            "source_url": item.source_url,
            "summary": item.summary,
            "ingestion_status": item.ingestion_status,
            "content_hash": getattr(item, 'content_hash', ''),
            "version": getattr(item, 'version', 1),
            "collection": collection_data,
            "tags": tags_data,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat()
        }
    }


def get_authoritative_library_stats(user) -> Dict[str, Any]:
    """
    Authoritative database query for user's saved items, counts, and collections.
    Strictly scoped to authenticated user (ContentItem.objects.filter(user=user)).
    Counts represent canonical saved ContentItem records (not chunks, embeddings, or jobs).
    Raises RetrievalInfrastructureError on database failure so errors are never converted to false zero.
    """
    try:
        from django.db.models import Count
        from .models import Collection

        items_qs = ContentItem.objects.filter(user=user)
        total_count = items_qs.count()

        # Counts by content_type
        type_counts = {
            ContentItem.TYPE_DOCUMENT: items_qs.filter(content_type=ContentItem.TYPE_DOCUMENT).count(),
            ContentItem.TYPE_NOTE: items_qs.filter(content_type=ContentItem.TYPE_NOTE).count(),
            ContentItem.TYPE_URL: items_qs.filter(content_type=ContentItem.TYPE_URL).count(),
            ContentItem.TYPE_VIDEO: items_qs.filter(content_type=ContentItem.TYPE_VIDEO).count(),
        }

        # Counts by ingestion_status
        status_counts = {
            ContentItem.STATUS_COMPLETED: items_qs.filter(ingestion_status=ContentItem.STATUS_COMPLETED).count(),
            ContentItem.STATUS_PENDING: items_qs.filter(ingestion_status=ContentItem.STATUS_PENDING).count(),
            ContentItem.STATUS_PROCESSING: items_qs.filter(
                ingestion_status__in=[
                    ContentItem.STATUS_PROCESSING,
                    ContentItem.STATUS_EXTRACTING,
                    ContentItem.STATUS_CHUNKING,
                    ContentItem.STATUS_EMBEDDING,
                    ContentItem.STATUS_INDEXING
                ]
            ).count(),
            ContentItem.STATUS_PARTIAL: items_qs.filter(ingestion_status=ContentItem.STATUS_PARTIAL).count(),
            ContentItem.STATUS_FAILED: items_qs.filter(ingestion_status=ContentItem.STATUS_FAILED).count(),
        }

        # User's collections with item counts
        collections_data = []
        user_collections = Collection.objects.filter(user=user).annotate(item_count=Count('items')).order_by('name')
        for col in user_collections:
            collections_data.append({
                "id": str(col.id),
                "name": col.name,
                "item_count": col.item_count
            })

        # Recent items manifest for context grounding
        recent_items = list(
            items_qs.select_related('collection').order_by('-created_at')[:20]
        )
        items_summary = []
        for it in recent_items:
            items_summary.append({
                "id": str(it.id),
                "title": it.title or it.source_url or "Untitled Note",
                "content_type": it.content_type,
                "status": it.ingestion_status,
                "collection": it.collection.name if it.collection else None,
                "created_at": it.created_at.isoformat(),
                "error_message": it.error_message
            })

        return {
            "total_count": total_count,
            "counts_by_type": type_counts,
            "counts_by_status": status_counts,
            "collections": collections_data,
            "items_summary": items_summary
        }
    except DatabaseError as e:
        logger.error(f"[DIAGNOSTIC] Database error while retrieving library stats for user {user.id}: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Database error while querying saved library stats: {e}") from e
    except Exception as e:
        logger.error(f"[DIAGNOSTIC] Unexpected error while retrieving library stats for user {user.id}: {e}", exc_info=True)
        raise RetrievalInfrastructureError(f"Failed to query saved library stats: {e}") from e


def exact_item_title_search(user, query_text: str) -> List[ContentItem]:
    """
    Search for user's ContentItem records matching exact or partial title, filename, or source_url.
    Strictly scoped to user.
    Handles exact title match, case-insensitive substring, and extension-stripped filename matching.
    """
    if not query_text or not query_text.strip():
        return []

    clean_q = query_text.strip()
    clean_lower = clean_q.lower()

    # Strip quotes if user quoted a document name
    quoted_match = re.search(r'["\']([^"\']+)["\']', clean_q)
    target_terms = [clean_q]
    if quoted_match:
        target_terms.insert(0, quoted_match.group(1).strip())

    # Detect file extensions (e.g. .pdf, .docx, .txt, .csv, .xlsx, .pptx)
    ext_match = re.search(r'([a-zA-Z0-9_\-\s]+\.(?:pdf|docx|txt|xlsx|pptx|csv|md))', clean_q, re.IGNORECASE)
    if ext_match:
        target_terms.insert(0, ext_match.group(1).strip())

    matches = []
    seen_ids = set()

    for term in target_terms:
        if len(term) < 2:
            continue
        # Exact title or URL match
        exact_qs = ContentItem.objects.filter(
            Q(user=user) & (Q(title__iexact=term) | Q(source_url__iexact=term))
        ).select_related('collection').prefetch_related('tags')
        for item in exact_qs:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                matches.append(item)

        # Substring title match
        if len(term) >= 3:
            sub_qs = ContentItem.objects.filter(
                Q(user=user) & (Q(title__icontains=term) | Q(source_url__icontains=term))
            ).select_related('collection').prefetch_related('tags')[:5]
            for item in sub_qs:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    matches.append(item)

    return matches

