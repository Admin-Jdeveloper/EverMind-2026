"""
MediaCompile — Chat Views and RAG API Endpoints.
Source of Truth: MediaCompile-prompt.md (Section 16: Phase 6 — Grounded AI Chat)

Enforces:
1. Multi-Tenant Session Isolation: All sessions filtered by request.user (cross-user access returns 404).
2. Grounded Message Generation: POST /api/v1/chat/sessions/{id}/messages/ invokes RAG pipeline.
3. Structured Citations: Returns grounded answers accompanied by verified citation metadata.
4. Server-Sent Events (SSE) Streaming: GET /api/v1/chat/sessions/{id}/stream/?query=...
"""

import json
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse, Http404

from .models import ChatSession, ChatMessage, UserMemory, UserPreference
from .serializers import (
    ChatSessionSerializer,
    ChatSessionDetailSerializer,
    ChatMessageSerializer,
    SendMessageSerializer,
    UserMemorySerializer,
    UserPreferenceSerializer
)
from .services import (
    generate_chat_turn,
    retrieve_grounding_context,
    build_system_prompt,
    clean_llm_response,
    compact_conversation_history,
    generate_suggested_followups
)
from .memory import (
    get_user_preference,
    get_active_user_memories,
    generate_topic_summaries
)
from .llm import get_llm_provider, UNSURE_FALLBACK_PHRASE
from core.throttling import ChatRateThrottle

class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for user chat sessions.
    Strictly user-isolated.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        return ChatSessionSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        from django.db import transaction
        import logging
        logger = logging.getLogger(__name__)
        instance = self.get_object()
        session_id = str(instance.id)
        with transaction.atomic():
            instance.messages.all().delete()
            instance.delete()
        logger.info(f"[DELETION] ChatSession {session_id} and all messages deleted.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'], url_path='clear-all')
    def clear_all(self, request):
        """Delete all chat sessions and their associated messages for authenticated user."""
        count, _ = ChatSession.objects.filter(user=request.user).delete()
        return Response({'success': True, 'deleted_count': count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='messages')
    def send_message(self, request, pk=None):
        """
        Send a user question to the session, execute grounded retrieval,
        and generate an authoritative assistant answer with citations.
        Supports scope switching via request.data['context_pins'].
        """
        session = self.get_object()
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_question = serializer.validated_data['content']
        context_pins = request.data.get('context_pins')
        from .llm import LLMError
        try:
            user_msg, assistant_msg = generate_chat_turn(
                session=session,
                user_question=user_question,
                context_pins=context_pins
            )
        except LLMError as e:
            return Response(
                {"error": str(e), "code": "LLM_PROVIDER_ERROR"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        return Response({
            "user_message": ChatMessageSerializer(user_msg).data,
            "assistant_message": ChatMessageSerializer(assistant_msg).data,
            "session": ChatSessionSerializer(session).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='stream')
    def stream_message(self, request, pk=None):
        """
        Stream grounded assistant response as Server-Sent Events (text/event-stream).
        Emits candidate metadata, incremental tokens, and final completion with citations.
        """
        session = self.get_object()
        user_question = request.query_params.get('query', '').strip()
        if not user_question:
            return Response({"error": "Query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Save user message
        user_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=user_question
        )

        all_past_messages = list(session.messages.exclude(id=user_msg.id).order_by('created_at'))
        conv_summary, history = compact_conversation_history(all_past_messages, max_recent=6)

        # 2. Retrieve grounded context from saved library
        from content.search import RetrievalInfrastructureError
        from django.db import DatabaseError
        from content.embeddings import EmbeddingError
        import re

        try:
            context_str, citations, facts_list, conflict_report = retrieve_grounding_context(
                request.user,
                user_question,
                limit=5,
                session=session,
                history=history,
                return_extended=True
            )
        except (RetrievalInfrastructureError, DatabaseError, EmbeddingError) as e:
            logger.exception(f"[STREAMING RETRIEVAL ERROR] user={request.user.id}: {e}")
            error_content = (
                "I encountered a technical issue retrieving data from your saved library "
                "(database or embedding service unavailable). Please try again later."
            )
            asst_msg = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_ASSISTANT,
                content=error_content,
                citations=[],
                metadata={
                    "retrieval_error": True,
                    "error_detail": str(e),
                    "answer_source": "retrieval_error",
                    "streaming": True
                }
            )
            def err_stream():
                yield f"event: error\ndata: {json.dumps({'error': error_content, 'message_id': str(asst_msg.id)})}\n\n"
            return StreamingHttpResponse(err_stream(), content_type='text/event-stream')

        tool_calls = ["saved_library_retrieval"]

        # 3. Library-First, Web-Second Evaluation
        from .web_search import evaluate_library_coverage, ExternalWebSearchProvider, is_explicit_saved_content_query
        is_explicit_saved = is_explicit_saved_content_query(user_question)
        coverage = evaluate_library_coverage(
            user_query=user_question,
            retrieved_citations=citations,
            retrieved_facts=facts_list,
            has_conflict=bool(conflict_report)
        )

        # 4. Handle Case: Explicit saved-content query with missing saved evidence
        if coverage.answer_source == "explicit_saved_missing":
            if re.search(r'\b(pdf|doc|document)\b', user_question.lower()):
                fallback_content = "I could not find the specified document or relevant evidence in your saved library to answer this question."
            else:
                fallback_content = UNSURE_FALLBACK_PHRASE

            asst_msg = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_ASSISTANT,
                content=fallback_content,
                citations=[],
                metadata={
                    "model": "rule_based_fallback",
                    "tool_calls": tool_calls,
                    "answer_source": "explicit_saved_missing",
                    "streaming": True
                }
            )
            def fallback_stream():
                yield f"event: metadata\ndata: {json.dumps({'citations': [], 'session_id': str(session.id), 'router_decision': 'none', 'is_complex': False})}\n\n"
                for word in fallback_content.split(" "):
                    yield f"event: token\ndata: {json.dumps({'token': word + ' '})}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': 'completed', 'message_id': str(asst_msg.id), 'session_id': str(session.id), 'suggested_followups': []})}\n\n"
            return StreamingHttpResponse(fallback_stream(), content_type='text/event-stream')

        web_results = []
        if coverage.needs_web_search:
            tool_calls.append("external_web_search")
            web_results = ExternalWebSearchProvider().search(coverage.web_query)
            if web_results:
                web_lines = [f"\n--- EXTERNAL WEB RESEARCH RESULTS (CASE {coverage.case}) ---"]
                next_idx = len(citations) + 1
                for wr in web_results:
                    web_lines.append(f"[Source {next_idx}] External Web: {wr.title} ({wr.url}):\n{wr.snippet}\n")
                    citations.append({
                        "source_index": next_idx,
                        "chunk_id": f"web_{next_idx}",
                        "item_id": f"web_ext_{next_idx}",
                        "item_title": wr.title,
                        "content_type": "web_search",
                        "source_url": wr.url,
                        "page_number": None,
                        "timestamp": None,
                        "text": wr.snippet,
                        "excerpt": wr.snippet[:240],
                        "score": 0.5,
                        "is_web": True,
                        "platform": "web_search"
                    })
                    next_idx += 1
                if context_str == "NO_RELEVANT_CONTENT":
                    context_str = "\n".join(web_lines)
                else:
                    context_str += "\n\n" + "\n".join(web_lines)

        memories = get_active_user_memories(request.user)
        system_prompt = build_system_prompt(
            context_str,
            memories=memories,
            conversation_summary=conv_summary,
            answer_source=coverage.answer_source,
            is_explicit_saved=is_explicit_saved
        )

        history_for_llm = list(history)
        history_for_llm.append({"role": "user", "content": user_question})

        from .router import route_chat_query
        decision = route_chat_query(
            user_query=user_question,
            retrieved_citations=citations,
            has_conflict=bool(conflict_report),
            has_web_results=bool(web_results),
            exact_facts=facts_list
        )

        provider = get_llm_provider(decision.provider, decision.model_name)

        import time
        from .citations import validate_citations
        t0 = time.time()

        def event_stream():
            collected_chunks = []
            ttft_ms = None
            gen_start = time.time()

            stream_citations = [] if coverage.answer_source == "general_knowledge" else citations
            # First send metadata event with candidate citations
            yield f"event: metadata\ndata: {json.dumps({'citations': stream_citations, 'session_id': str(session.id), 'router_decision': decision.provider, 'is_complex': decision.is_complex, 'answer_source': coverage.answer_source})}\n\n"

            try:
                for token in provider.stream_response(history_for_llm, system_prompt):
                    if ttft_ms is None:
                        ttft_ms = round((time.time() - gen_start) * 1000, 2)
                    collected_chunks.append(token)
                    yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            except Exception as e:
                logger.exception(f"Streaming token generation failed: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                return

            # Finalize message persistence with rigorous citation validation
            full_response = clean_llm_response("".join(collected_chunks))
            validation = validate_citations(full_response, citations, request.user, answer_source=coverage.answer_source)
            citations_to_persist = validation.validated_citations
            val_prec = validation.citation_precision
            prov_ok = validation.provenance_valid

            suggested_followups = generate_suggested_followups(
                user_question=user_question,
                assistant_content=full_response,
                citations=citations_to_persist
            )

            total_ms = round((time.time() - t0) * 1000, 2)
            meta = {
                "model": provider.model_name,
                "tool_calls": tool_calls,
                "router_decision": decision.provider,
                "router_reason": decision.reason,
                "is_complex": decision.is_complex,
                "library_coverage_case": coverage.case,
                "answer_source": coverage.answer_source,
                "web_search_invoked": coverage.needs_web_search,
                "citation_count": len(citations_to_persist),
                "citation_precision": val_prec,
                "provenance_valid": prov_ok,
                "time_to_first_token_ms": ttft_ms or 0.0,
                "total_latency_ms": total_ms,
                "streaming": True,
                "suggested_followups": suggested_followups,
                "conversation_compacted": bool(conv_summary)
            }

            asst_msg = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_ASSISTANT,
                content=full_response,
                citations=citations_to_persist,
                metadata=meta
            )
            yield f"event: done\ndata: {json.dumps({'status': 'completed', 'message_id': str(asst_msg.id), 'session_id': str(session.id), 'suggested_followups': suggested_followups})}\n\n"


        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class UserMemoryViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for personal AI memories.
    Strictly user-isolated and gated with sensitive trait rejection.
    """
    serializer_class = UserMemorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserMemory.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='toggle')
    def toggle_active(self, request, pk=None):
        """Toggle active status of a memory item without deleting it."""
        memory = self.get_object()
        memory.is_active = not memory.is_active
        memory.save(update_fields=['is_active', 'updated_at'])
        return Response(UserMemorySerializer(memory).data, status=status.HTTP_200_OK)


class UserPreferenceView(APIView):
    """
    Get and update user personalization settings (master toggle & automated memory consent).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pref = get_user_preference(request.user)
        return Response(UserPreferenceSerializer(pref).data)

    def patch(self, request):
        pref = get_user_preference(request.user)
        serializer = UserPreferenceSerializer(pref, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class TopicSummariesView(APIView):
    """
    Generate knowledge topic summaries derived from user's saved items with direct provenance links.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summaries = generate_topic_summaries(request.user)
        return Response({
            "count": len(summaries),
            "topics": summaries
        }, status=status.HTTP_200_OK)
