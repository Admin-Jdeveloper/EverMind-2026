"""
MediaCompile — Conversational Query Planner and Reference Resolver.
Source of Truth: Chatbot_architecture_recall.md (Section 1: Steps 3-5, Section 2: Sequences A-E)

Responsibilities:
1. Classifies user query: Standalone vs Follow-Up (Ordinal reference, Page locator, Anaphora, Expansion, Comparison, Ambiguous).
2. Resolves ordinal references (e.g. "Explain the second point") to exact text of preceding assistant points.
3. Resolves spatial locators (e.g. "What does page 14 say about locking?") to page filters and target focus queries.
4. Resolves anaphoric pronouns ("it", "they", "she", "he", "this", "that") using recent conversational history.
5. Resolves multi-document comparative scope (e.g. "Compare it with the other document").
6. Emits structured QueryPlan for downstream hybrid retrieval, chunk filtering, and context assembly.
"""

import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ORDINAL_WORD_MAP = {
    "first": 1, "1st": 1, "one": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
    "fifth": 5, "5th": 5, "five": 5,
    "sixth": 6, "6th": 6, "six": 6,
    "seventh": 7, "7th": 7, "seven": 7,
    "eighth": 8, "8th": 8, "eight": 8,
    "ninth": 9, "9th": 9, "nine": 9,
    "tenth": 10, "10th": 10, "ten": 10,
    "last": -1, "final": -1,
}

PRONOUNS = {
    "it", "its", "they", "them", "their", "theirs",
    "she", "her", "hers", "he", "him", "his",
    "this", "that", "these", "those"
}

GENERIC_WORDS = {
    "source", "media", "compile", "page", "slide", "based", "according",
    "hello", "hi", "hey", "please", "thank", "thanks", "tell", "explain",
    "describe", "summary", "summarize", "document", "article", "note", "paper",
    "deep", "dive", "session", "exploration", "test", "ambiguity", "numbered"
}


def extract_salient_entities(history: List[Dict[str, str]], session_title: str = "") -> List[str]:
    """Extract key entity and topic nouns from recent conversation history."""
    entities = []

    # Check last user and assistant turns FIRST (most authoritative)
    for turn in reversed(history[-4:]):
        content = turn.get("content", "")
        # Find capitalized words or acronyms (e.g. "Raft", "MVCC", "TCP", "Kafka", "Paxos")
        matches = re.findall(r'\b[A-Z][a-zA-Z0-9_-]{1,}\b', content)
        for m in matches:
            if m.lower() not in GENERIC_WORDS and m not in entities:
                entities.append(m)

    # Check session title only as fallback if no entities found in conversation
    if not entities and session_title and session_title.lower() not in ("new conversation", "new chat", "untitled"):
        for word in session_title.split():
            clean = word.strip(".,?!:;\"'()")
            if len(clean) >= 3 and clean.lower() not in GENERIC_WORDS:
                if clean not in entities:
                    entities.append(clean)

    return entities


@dataclass
class QueryPlan:
    """Structured retrieval and routing plan for a conversational turn."""
    original_query: str
    standalone_queries: List[str] = field(default_factory=list)
    is_follow_up: bool = False
    follow_up_type: str = "STANDALONE"  # STANDALONE, ORDINAL_POINT, PAGE_PINNED, EXPANSION, ANAPHORA, COMPARISON, AMBIGUOUS
    requires_retrieval: bool = True
    scope_mode: str = "global"  # single_item, collection, global, comparison
    target_page: Optional[int] = None
    target_item_ids: Optional[List[str]] = None
    focus_query: Optional[str] = None
    clarification_needed: bool = False
    extracted_point_text: Optional[str] = None
    inherited_citations: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def standalone_query(self) -> str:
        return self.standalone_queries[0] if self.standalone_queries else self.original_query

    @property
    def search_queries(self) -> List[str]:
        return self.standalone_queries if self.standalone_queries else [self.original_query]

    def get_primary_search_query(self) -> str:
        if self.standalone_queries:
            return self.standalone_queries[0]
        return self.original_query


def extract_numbered_points_from_text(text: str) -> List[str]:
    """
    Extract discrete numbered or bulleted points from assistant response.
    Supports formats:
    - 1. Point text...
    - Point 1: Point text...
    - 1) Point text...
    - - Point text...
    """
    if not text:
        return []

    points = []
    lines = text.splitlines()

    # Pattern 1: Numbered list "1. ...", "1) ...", "Point 1: ...", "Claim 1: ..."
    numbered_regex = re.compile(
        r'^(?:(?:\d+[\.\)]|\bpoint\s+\d+:?|\bclaim\s+\d+:?|\bfinding\s+\d+:?))\s*(.+)',
        re.IGNORECASE
    )

    current_point = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_point:
                points.append(" ".join(current_point))
                current_point = []
            continue

        match = numbered_regex.match(stripped)
        if match:
            if current_point:
                points.append(" ".join(current_point))
                current_point = []
            content = match.group(1).strip()
            # Clean leading bolding like **Title:**
            clean_content = re.sub(r'^\*\*[^*]+\*\*[:\-]?\s*', '', content)
            current_point.append(clean_content or content)
        elif current_point and not stripped.startswith('#'):
            current_point.append(stripped)

    if current_point:
        points.append(" ".join(current_point))

    # If no numbered list found, fall back to markdown bullets
    if not points:
        bullet_regex = re.compile(r'^[-*•]\s+(.+)')
        for line in lines:
            stripped = line.strip()
            match = bullet_regex.match(stripped)
            if match:
                content = match.group(1).strip()
                clean_content = re.sub(r'^\*\*[^*]+\*\*[:\-]?\s*', '', content)
                points.append(clean_content or content)

    return points


def extract_page_locator(question: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Detect explicit spatial locator like 'page 14', 'p. 14', 'page 4'.
    Returns (page_number, stripped_query).
    """
    # Regex for "page 14", "page 4", "p. 14", "p.14", "slide 3"
    match = re.search(r'\b(?:page|p\.)\s*(\d+)\b', question, re.IGNORECASE)
    if match:
        page_num = int(match.group(1))
        # Remove "what does page 14 say about" -> "about locking" -> "locking"
        stripped = re.sub(r'\b(?:what\s+does\s+)?(?:page|p\.)\s*\d+\s*(?:say\s+about|say|contain|state|mention|have)?\b', '', question, flags=re.IGNORECASE)
        stripped = re.sub(r'\s+', ' ', stripped).strip()
        return page_num, stripped or None

    return None, None


def extract_salient_entities(history: List[Dict[str, str]], session_title: str = "") -> List[str]:
    """Extract key entity and topic nouns from recent conversation history."""
    entities = []

    # Check session title first if meaningful
    if session_title and session_title.lower() not in ("new conversation", "new chat", "untitled"):
        for word in session_title.split():
            clean = word.strip(".,?!:;\"'()")
            if len(clean) >= 3 and clean.lower() not in GENERIC_WORDS:
                if clean not in entities:
                    entities.append(clean)

    # Check last user and assistant turns
    for turn in reversed(history[-4:]):
        content = turn.get("content", "")
        # Find capitalized words or acronyms (e.g. "Raft", "TCP", "Kafka", "Sinclair")
        matches = re.findall(r'\b[A-Z][a-zA-Z0-9_-]{1,}\b', content)
        for m in matches:
            if m.lower() not in GENERIC_WORDS and m not in entities:
                entities.append(m)

    return entities


def build_query_plan(
    question: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    session: Any = None,
    context_pins: Optional[List[Dict[str, Any]]] = None,
    user_query: Optional[str] = None
) -> QueryPlan:
    """
    Analyze the incoming user question against conversational history and active pins.
    Emits a fully resolved, actionable QueryPlan.
    """
    raw = user_query if user_query is not None else (question or "")
    clean_q = raw.strip()
    q_lower = clean_q.lower()

    if history is None and session and hasattr(session, 'messages'):
        history = []
        for m in reversed(list(session.messages.order_by('-created_at')[:6])):
            history.append({"role": m.role, "content": m.content})
    else:
        history = history or []

    # Inherit citations from previous assistant turn if available
    inherited_citations = []
    if session and hasattr(session, 'messages'):
        last_asst = session.messages.filter(role='assistant').order_by('-created_at').first()
        if last_asst and last_asst.citations:
            inherited_citations = list(last_asst.citations)

    # Inherit item_ids from context pins or citations
    explicit_pinned_ids = []
    if context_pins:
        if isinstance(context_pins, dict):
            raw_ids = (
                context_pins.get("target_item_ids") or
                context_pins.get("item_ids") or
                context_pins.get("cards") or
                context_pins.get("card_id") or
                context_pins.get("id")
            )
            if raw_ids:
                if isinstance(raw_ids, list):
                    for item in raw_ids:
                        if isinstance(item, dict) and item.get("id"):
                            explicit_pinned_ids.append(str(item["id"]))
                        elif isinstance(item, (str, int, uuid.UUID)):
                            explicit_pinned_ids.append(str(item))
                elif isinstance(raw_ids, (str, int, uuid.UUID)):
                    explicit_pinned_ids.append(str(raw_ids))
        elif isinstance(context_pins, list):
            for p in context_pins:
                if isinstance(p, dict) and p.get("id"):
                    explicit_pinned_ids.append(str(p["id"]))
                elif isinstance(p, (str, int, uuid.UUID)):
                    explicit_pinned_ids.append(str(p))

    pinned_item_ids = list(explicit_pinned_ids)
    if not pinned_item_ids and inherited_citations:
        for c in inherited_citations:
            cid = c.get("item_id")
            if cid and str(cid) not in pinned_item_ids:
                pinned_item_ids.append(str(cid))

    session_title = getattr(session, 'title', '') if session else ''

    # Pre-extract Page Locators and Comparison Triggers (universal across turns)
    page_num, focus_q = extract_page_locator(clean_q)
    if page_num is not None:
        salient_entities = extract_salient_entities(history, session_title=session_title)
        primary_entity = salient_entities[0] if salient_entities else ""
        standalone = []
        if focus_q and primary_entity:
            standalone.append(f"{primary_entity} {focus_q} page {page_num}")
            standalone.append(f"{focus_q} page {page_num}")
        elif focus_q:
            standalone.append(f"{focus_q} page {page_num}")
        elif primary_entity:
            standalone.append(f"{primary_entity} page {page_num}")
        else:
            standalone.append(f"page {page_num}")
        standalone.append(clean_q)

        return QueryPlan(
            original_query=clean_q,
            standalone_queries=standalone,
            is_follow_up=bool(history),
            follow_up_type="PAGE_PINNED",
            requires_retrieval=True,
            scope_mode="single_item" if pinned_item_ids else "global",
            target_page=page_num,
            target_item_ids=pinned_item_ids or None,
            focus_query=focus_q or f"page {page_num}",
            inherited_citations=inherited_citations
        )

    # Cross-Document Comparison (universal across turns)
    comp_triggers = ["compare", "versus", "vs", "which one", "difference between", "both documents"]
    if any(t in q_lower for t in comp_triggers):
        salient_entities = extract_salient_entities(history, session_title=session_title)
        primary_entity = salient_entities[0] if salient_entities else ""
        standalone = [clean_q]
        # Extract sub-entities from comparison query (e.g. "Compare Raft with Paxos")
        comp_matches = re.findall(r'\b[A-Z][a-zA-Z0-9_-]{1,}\b', clean_q)
        for cm in comp_matches:
            if cm.lower() not in GENERIC_WORDS and cm not in standalone:
                standalone.append(cm)
        if primary_entity and primary_entity.lower() not in q_lower:
            standalone.insert(0, f"{primary_entity} {clean_q}")

        return QueryPlan(
            original_query=clean_q,
            standalone_queries=standalone,
            is_follow_up=bool(history),
            follow_up_type="COMPARISON",
            requires_retrieval=True,
            scope_mode="comparison",
            target_item_ids=pinned_item_ids or None,
            inherited_citations=inherited_citations
        )

    # Empty history fallback -> standard standalone query
    if not history:
        return QueryPlan(
            original_query=clean_q,
            standalone_queries=[clean_q],
            is_follow_up=False,
            follow_up_type="STANDALONE",
            requires_retrieval=True,
            scope_mode="single_item" if len(pinned_item_ids) == 1 else "global",
            target_page=None,
            target_item_ids=pinned_item_ids or None,
            focus_query=None,
            inherited_citations=inherited_citations
        )

    last_assistant_msg = ""
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            last_assistant_msg = turn.get("content", "")
            break

    salient_entities = extract_salient_entities(history, session_title=session_title)
    primary_entity = salient_entities[0] if salient_entities else ""

    # Case 2: Ordinal Point Reference (e.g. "Explain the second point", "Elaborate on point 3", "What about the 1st finding?")
    ordinal_match = re.search(
        r'\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|last|final)\s+(?:point|claim|item|finding|reason|step|argument|recommendation)\b',
        q_lower
    )
    if not ordinal_match:
        # Also match "point 2", "point 3", "step 1"
        num_point_match = re.search(r'\b(?:point|step|claim|item)\s+(\d+)\b', q_lower)
        if num_point_match:
            ordinal_idx = int(num_point_match.group(1))
        else:
            ordinal_idx = None
    else:
        word = ordinal_match.group(1).lower()
        ordinal_idx = ORDINAL_WORD_MAP.get(word)

    if ordinal_idx is not None and last_assistant_msg:
        extracted_points = extract_numbered_points_from_text(last_assistant_msg)
        target_point_text = None
        if extracted_points:
            if ordinal_idx == -1:
                target_point_text = extracted_points[-1]
            elif 1 <= ordinal_idx <= len(extracted_points):
                target_point_text = extracted_points[ordinal_idx - 1]

        if target_point_text:
            # Formulate targeted standalone query
            point_summary = target_point_text[:120].strip()
            standalone = []
            if primary_entity:
                standalone.append(f"{primary_entity} {point_summary}")
            standalone.append(point_summary)
            standalone.append(clean_q)

            return QueryPlan(
                original_query=clean_q,
                standalone_queries=standalone,
                is_follow_up=True,
                follow_up_type="ORDINAL_POINT",
                requires_retrieval=True,
                scope_mode="single_item" if len(pinned_item_ids) == 1 else "global",
                target_item_ids=pinned_item_ids or None,
                focus_query=point_summary[:60],
                extracted_point_text=target_point_text,
                inherited_citations=inherited_citations
            )

    # Case 4: Previous Answer Expansion / Why / Example
    expansion_triggers = [
        "expand", "elaborate", "tell me more", "explain that", "why does it",
        "why is that", "give an example", "explain the example", "what about that",
        "show an example", "can you give an example", "how come"
    ]
    is_expansion = any(t in q_lower for t in expansion_triggers) or q_lower in ("why?", "why", "how?", "how", "what about it?", "expand", "more")
    if is_expansion:
        standalone = []
        if last_assistant_msg:
            # Extract first sentence or key concept of last assistant message
            first_sentence = last_assistant_msg.strip().split(".")[0][:80]
            if first_sentence:
                standalone.append(f"{first_sentence} {clean_q}")
        if primary_entity:
            standalone.append(f"{primary_entity} {clean_q}")
        standalone.append(clean_q)

        return QueryPlan(
            original_query=clean_q,
            standalone_queries=standalone,
            is_follow_up=True,
            follow_up_type="EXPANSION",
            requires_retrieval=True,
            scope_mode="single_item" if len(pinned_item_ids) == 1 else "global",
            target_item_ids=pinned_item_ids or None,
            inherited_citations=inherited_citations
        )

    # Case 5: Pronoun Anaphora Resolution (e.g. "How does it handle replication?", "When was she born?")
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', q_lower))
    has_pronoun = bool(tokens & PRONOUNS)

    if has_pronoun or len(clean_q.split()) <= 4:
        standalone = []
        if primary_entity and primary_entity.lower() not in q_lower:
            # Replace pronouns or prefix with primary entity
            enriched = f"{primary_entity} {clean_q}"
            standalone.append(enriched)
        standalone.append(clean_q)

        return QueryPlan(
            original_query=clean_q,
            standalone_queries=standalone,
            is_follow_up=True,
            follow_up_type="ANAPHORA",
            requires_retrieval=True,
            scope_mode="single_item" if len(pinned_item_ids) == 1 else "global",
            target_item_ids=pinned_item_ids or None,
            inherited_citations=inherited_citations
        )

    # Case 6: Standard Standalone or Complex Multi-word Query
    return QueryPlan(
        original_query=clean_q,
        standalone_queries=[clean_q],
        is_follow_up=False,
        follow_up_type="STANDALONE",
        requires_retrieval=True,
        scope_mode="single_item" if len(explicit_pinned_ids) == 1 else "global",
        target_item_ids=explicit_pinned_ids or None,
        inherited_citations=inherited_citations
    )
