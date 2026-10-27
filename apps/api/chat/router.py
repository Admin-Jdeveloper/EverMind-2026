"""
MediaCompile — Conversational Query Router & Reasoning Classifier.
Source of Truth: MediaCompile Target Architecture (Groq GPT-OSS 120B as Single Provider)

Principles:
1. Groq GPT-OSS 120B (openai/gpt-oss-120b) is the sole LLM provider for all completion turns.
2. Deterministic rules evaluate query complexity, multi-source requirements, exact facts,
   and conflict status with zero extra model latency.
3. Provides structured classification (is_complex, reason, intent_category) to inform
   downstream context assembly, token budgets, and observability logs.
4. Safe, deterministic routing with full tenant isolation and zero external dependencies.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    provider: str        # 'groq'
    model_name: str      # 'openai/gpt-oss-120b'
    is_complex: bool
    reason: str
    intent_category: str = "standard_rag"


class QueryRouter:
    """
    Intelligent query router and complexity classifier for Groq GPT-OSS 120B.
    Analyzes user query and retrieved evidence to determine complexity, synthesis mode,
    and factual precision requirements.
    """
    def __init__(self):
        self.groq_model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")

    def route_query(
        self,
        user_query: str,
        retrieved_citations: List[Dict[str, Any]],
        has_conflict: bool = False,
        has_web_results: bool = False,
        exact_facts: Optional[List[Dict[str, Any]]] = None,
    ) -> RoutingDecision:
        """
        Evaluate query and retrieval context to classify complexity and reasoning mode.
        Provider is always Groq GPT-OSS 120B.
        """
        q_lower = user_query.strip().lower()
        groq_model = (
            getattr(settings, "GROQ_MODEL", None)
            or os.environ.get("GROQ_MODEL")
            or self.groq_model
        )

        # 1. Exact fact lookups (DOB, dates, passport, codes, currency)
        dob_terms = {"dob", "born", "birth", "birthday", "birthdate", "date of birth"}
        exact_fact_terms = {
            "what is my", "what was the date", "account number", "phone number",
            "email address", "budget limit", "code", "when was", "where was", "exact value"
        }
        user_words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', q_lower))

        if (user_words & dob_terms) or (exact_facts and len(exact_facts) > 0) or any(t in q_lower for t in exact_fact_terms):
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=False,
                reason="Routine exact factual lookup (DOB/date/code/identifier); served with exact fact precision.",
                intent_category="exact_fact"
            )

        # 2. Simple greetings and conversational courtesies
        greetings = {"hi", "hello", "hey", "good morning", "good evening", "thanks", "thank you", "who are you"}
        if len(q_lower.split()) <= 3 and any(g in q_lower for g in greetings):
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=False,
                reason="Conversational greeting or short courtesy.",
                intent_category="greeting"
            )

        # 3. Conflict resolution across contradictory evidence
        if has_conflict:
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=True,
                reason="Contradictory evidence detected across saved sources; requires explicit conflict synthesis.",
                intent_category="conflict_resolution"
            )

        # Count distinct saved content items in retrieved citations
        distinct_source_ids = set()
        for c in retrieved_citations:
            s_id = (
                c.get("item_id")
                or c.get("content_item_id")
                or c.get("source_id")
                or c.get("item_title")
                or c.get("title")
            )
            if s_id:
                distinct_source_ids.add(s_id)
        distinct_count = len(distinct_source_ids)

        # 4. Multi-source cross-document comparison
        comparison_keywords = {"compare", "versus", "vs", "contrast", "difference between", "differ", "pros and cons"}
        is_comparison = any(term in q_lower for term in comparison_keywords)
        if is_comparison and distinct_count >= 2:
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=True,
                reason=f"Cross-document comparative analysis across {distinct_count} distinct sources.",
                intent_category="cross_source_comparison"
            )

        # 5. Hybrid library + external web research synthesis
        if has_web_results and distinct_count >= 1:
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=True,
                reason="Multi-source synthesis reconciling saved library knowledge with live external web research.",
                intent_category="hybrid_research"
            )

        # 6. High-volume synthesis across 3 or more distinct sources
        if distinct_count >= 3:
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=True,
                reason=f"Multi-document synthesis across {distinct_count} distinct documents.",
                intent_category="multi_source_synthesis"
            )

        # 7. Deep analytical research report requests
        analytical_keywords = {
            "synthesize", "comprehensive analysis", "detailed report", "break down the implications",
            "deep dive", "cross-reference", "systematic evaluation", "in-depth breakdown"
        }
        if any(term in q_lower for term in analytical_keywords):
            return RoutingDecision(
                provider="groq",
                model_name=groq_model,
                is_complex=True,
                reason="Analytical query requesting comprehensive multi-part synthesis.",
                intent_category="deep_analysis"
            )

        # 8. Standard single-source explanation or general query
        return RoutingDecision(
            provider="groq",
            model_name=groq_model,
            is_complex=False,
            reason="Standard query served reliably by Groq GPT-OSS 120B.",
            intent_category="standard_rag"
        )


_default_router = QueryRouter()


def route_chat_query(
    user_query: str,
    retrieved_citations: List[Dict[str, Any]],
    has_conflict: bool = False,
    has_web_results: bool = False,
    exact_facts: Optional[List[Dict[str, Any]]] = None,
) -> RoutingDecision:
    """Convenience helper to route a query."""
    return _default_router.route_query(
        user_query=user_query,
        retrieved_citations=retrieved_citations,
        has_conflict=has_conflict,
        has_web_results=has_web_results,
        exact_facts=exact_facts,
    )
