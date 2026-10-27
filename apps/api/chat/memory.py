"""
MediaCompile — User Memory & Personalization Management Service.
Source of Truth: MediaCompile-prompt.md (Section 17: Personalization and User-Controlled Memory)

Features:
1. User Memory Sovereignty: Add, list, edit, disable, and delete memories.
2. AI Safety / Sensitive Trait Rejection: Enforces strict guardrails against inferring
   or retaining sensitive categories (health, religion, politics, biometric, financial credentials).
3. Personalization Opt-Out: Respects user master toggle (personalization_enabled).
4. Topic Summary Generation: Synthesizes knowledge topics with supporting item links.
"""

import re
import logging
from typing import List, Dict, Any, Tuple
from django.core.exceptions import ValidationError

from content.models import ContentItem
from .models import UserMemory, UserPreference

logger = logging.getLogger(__name__)

# Sensitive personal data categories prohibited from memory retention
PROHIBITED_SENSITIVE_PATTERNS = [
    r"\b(medical|diagnosis|diagnosed|disease|illness|prescription|prescribed|medication|surgery|symptom|cancer|asthma|diabetes|allergy|allergies|hiv|aids)\b",
    r"\b(religion|religious|christianity|christian|baptist|catholic|protestant|islam|muslim|judaism|jewish|hinduism|buddhism|atheist|church|mosque|synagogue)\b",
    r"\b(politic|political|politics|republican|democrat|democratic|socialist|conservative|liberal|marxist|election|vote|voted|voting|campaign)\b",
    r"\b(sexual orientation|sexuality|homosexual|heterosexual|bisexual|transgender|queer)\b",
    r"\b(ssn|social security|credit card|cvv|bank account|routing number|password|secret key)\b"
]

class SensitiveMemoryError(ValidationError):
    """Raised when memory content contains prohibited sensitive personal traits."""
    pass

def validate_memory_safety(text: str, category: str = "general"):
    """
    Validate that memory text and category do not retain sensitive personal traits
    (health, religion, politics, sexuality, biometric, or sensitive financial data).
    """
    category_lower = category.lower().strip()
    if category_lower in ("health", "medical", "religion", "politics", "political", "sexuality", "biometrics"):
        raise SensitiveMemoryError(
            f"Category '{category}' is prohibited. Personalization memory strictly forbids "
            "retaining sensitive traits (health, religion, politics, sexuality, biometrics)."
        )

    text_lower = text.lower()
    for pattern in PROHIBITED_SENSITIVE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            prohibited_term = match.group(0)
            raise SensitiveMemoryError(
                f"Memory content contains prohibited sensitive topic ('{prohibited_term}'). "
                "Personalization memory strictly forbids retaining health, religious, political, "
                "or confidential financial attributes."
            )

def get_user_preference(user) -> UserPreference:
    """Retrieve or create default privacy preferences for user."""
    pref, _ = UserPreference.objects.get_or_create(user=user)
    return pref

def get_active_user_memories(user) -> List[str]:
    """
    Retrieve active memories formatted for prompt injection, strictly respecting
    the user's personalization_enabled master toggle.
    """
    pref = get_user_preference(user)
    if not pref.personalization_enabled:
        return []

    memories = UserMemory.objects.filter(user=user, is_active=True).order_by('-created_at')[:8]
    formatted = []
    for m in memories:
        kind = "explicit preference" if m.is_explicit else "consented inference"
        formatted.append(f"- [{kind}] {m.memory_text}")
    return formatted

def generate_topic_summaries(user) -> List[Dict[str, Any]]:
    """
    Generate knowledge topic summaries derived from the user's saved items
    with direct provenance links to supporting documents.
    """
    items = ContentItem.objects.filter(user=user, ingestion_status=ContentItem.STATUS_COMPLETED).select_related('collection').prefetch_related('tags')[:30]

    topics_by_collection: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        col_name = item.collection.name if item.collection else "Unfiled Library"
        if col_name not in topics_by_collection:
            topics_by_collection[col_name] = []

        topics_by_collection[col_name].append({
            "id": str(item.id),
            "title": item.title or "Untitled Item",
            "content_type": item.content_type,
            "source_url": item.source_url,
            "created_at": item.created_at.isoformat()
        })

    topic_summaries = []
    for col_name, supporting_items in topics_by_collection.items():
        topic_summaries.append({
            "topic": col_name,
            "item_count": len(supporting_items),
            "summary": f"Aggregated knowledge repository for {col_name} containing {len(supporting_items)} saved references.",
            "supporting_items": supporting_items
        })

    return topic_summaries
