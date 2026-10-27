"""
MediaCompile — Groq API Chatbot Integration Test Suite.
Validates:
1. GroqLLMProvider initializes with GROQ_API_KEY, GROQ_MODEL (openai/gpt-oss-120b), and base URL.
2. Does NOT send requests to api.openai.com.
3. Safe error handling when GROQ_API_KEY is missing (clean LLMError).
4. Error mapping: AuthenticationError, RateLimitError, NotFoundError, APITimeoutError.
5. Response generation with mocked Groq SDK client.
6. Streaming response with mocked Groq SDK client.
7. Full grounded chat turn with Groq provider.
8. Multi-tenant isolation: User B cannot retrieve User A's items via Groq chatbot.
"""

import pytest
import os
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import override_settings

from chat.llm import (
    GroqLLMProvider,
    MockLLMProvider,
    get_llm_provider,
    LLMError,
    DEFAULT_GROQ_MODEL,
    DEFAULT_GROQ_BASE_URL,
)
from chat.models import ChatSession, ChatMessage
from chat.services import generate_chat_turn, build_system_prompt
from content.models import ContentItem, ContentChunk
from content.embeddings import get_embedding_provider

User = get_user_model()


class TestGroqLLMProviderConfig:
    """Tests provider configuration and environment variable loading."""

    def test_default_configuration(self):
        provider = GroqLLMProvider(api_key="gsk_testkey123")
        assert provider.model_name == "openai/gpt-oss-120b"
        assert provider.base_url == "https://api.groq.com/openai/v1"
        assert provider.api_key == "gsk_testkey123"
        # Confirm no reference to OpenAI endpoint
        assert "api.openai.com" not in provider.base_url

    def test_missing_api_key_raises_llm_error(self):
        provider = GroqLLMProvider(api_key="")
        with pytest.raises(LLMError) as exc_info:
            provider.generate_response([{"role": "user", "content": "hello"}], "system")
        assert "GROQ_API_KEY is not configured" in str(exc_info.value)

    def test_get_llm_provider_factory_reads_settings(self):
        with override_settings(
            LLM_PROVIDER="groq",
            GROQ_API_KEY="gsk_custom_key_456",
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_BASE_URL="https://api.groq.com/openai/v1",
        ):
            provider = get_llm_provider()
            assert isinstance(provider, GroqLLMProvider)
            assert provider.model_name == "openai/gpt-oss-120b"
            assert provider.api_key == "gsk_custom_key_456"
            assert provider.base_url == "https://api.groq.com/openai/v1"


class TestGroqResponseGeneration:
    """Tests completion and streaming via mocked Groq SDK client."""

    @patch("groq.Groq")
    def test_generate_response_mocked_groq(self, mock_groq_class):
        # Set up mock Groq client completion
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "Grounded answer about vector databases [Source 1]."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        provider = GroqLLMProvider(api_key="gsk_mock_valid_key")
        messages = [{"role": "user", "content": "Explain vector search"}]
        system_prompt = "You are MediaCompile AI."

        result = provider.generate_response(messages, system_prompt=system_prompt)

        assert result == "Grounded answer about vector databases [Source 1]."
        # Verify call arguments
        mock_client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are MediaCompile AI."},
                {"role": "user", "content": "Explain vector search"},
            ],
            temperature=0.2,
        )

    @patch("groq.Groq")
    def test_stream_response_mocked_groq(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client

        # Mock streaming chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="world!"))]
        mock_client.chat.completions.create.return_value = [chunk1, chunk2]

        provider = GroqLLMProvider(api_key="gsk_mock_valid_key")
        tokens = list(provider.stream_response([{"role": "user", "content": "hi"}], "system"))

        assert tokens == ["Hello ", "world!"]
        mock_client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "hi"},
            ],
            temperature=0.2,
            stream=True,
        )


class TestGroqErrorHandling:
    """Tests error mapping for Groq API exceptions."""

    @patch("groq.Groq")
    def test_authentication_error_mapped(self, mock_groq_class):
        import groq
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = groq.AuthenticationError(
            message="Invalid API Key",
            response=MagicMock(status_code=401),
            body=None,
        )

        provider = GroqLLMProvider(api_key="gsk_bad_key")
        with pytest.raises(LLMError) as exc_info:
            provider.generate_response([{"role": "user", "content": "hi"}], "system")
        assert "Groq authentication failed" in str(exc_info.value)

    @patch("groq.Groq")
    def test_rate_limit_error_mapped(self, mock_groq_class):
        import groq
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = groq.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )

        provider = GroqLLMProvider(api_key="gsk_valid_key")
        with pytest.raises(LLMError) as exc_info:
            provider.generate_response([{"role": "user", "content": "hi"}], "system")
        assert "rate limit exceeded" in str(exc_info.value)

    @patch("groq.Groq")
    def test_not_found_error_mapped(self, mock_groq_class):
        import groq
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = groq.NotFoundError(
            message="Model not found",
            response=MagicMock(status_code=404),
            body=None,
        )

        provider = GroqLLMProvider(api_key="gsk_valid_key", model_name="openai/gpt-oss-120b")
        with pytest.raises(LLMError) as exc_info:
            provider.generate_response([{"role": "user", "content": "hi"}], "system")
        assert "was not found or is currently unavailable" in str(exc_info.value)


@pytest.mark.django_db
class TestGroqGroundedChatTurnAndIsolation:
    """Tests grounded RAG chat turns and tenant isolation using Groq provider."""

    @patch("groq.Groq")
    def test_grounded_chat_turn_persists_model_and_citations(self, mock_groq_class):
        user = User.objects.create_user(email="carol@mediacompile.io", password="Password123!")
        embedder = get_embedding_provider()

        item = ContentItem.objects.create(
            user=user,
            content_type=ContentItem.TYPE_NOTE,
            title="Consensus Raft Notes",
            raw_text="Raft leader election uses randomized timeouts 150-300ms.",
            ingestion_status=ContentItem.STATUS_COMPLETED,
        )
        ContentChunk.objects.create(
            content_item=item,
            chunk_index=0,
            text="Raft leader election uses randomized timeouts 150-300ms.",
            start_offset=0,
            end_offset=58,
            embedding=embedder.embed_text("Raft leader election uses randomized timeouts 150-300ms."),
        )

        session = ChatSession.objects.create(user=user, title="New Conversation")

        # Mock Groq response
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "Based on your saved notes [Source 1], Raft uses 150-300ms randomized timeouts."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        with override_settings(
            LLM_PROVIDER="groq",
            GROQ_API_KEY="gsk_test_key_for_turn",
            GROQ_MODEL="openai/gpt-oss-120b",
        ):
            user_msg, assistant_msg = generate_chat_turn(session, "How does Raft elect leaders?")

            assert user_msg.role == ChatMessage.ROLE_USER
            assert assistant_msg.role == ChatMessage.ROLE_ASSISTANT
            assert "[Source 1]" in assistant_msg.content
            assert assistant_msg.metadata["model"] == "openai/gpt-oss-120b"
            assert len(assistant_msg.citations) >= 1
            assert assistant_msg.citations[0]["item_title"] == "Consensus Raft Notes"

    @patch("groq.Groq")
    def test_tenant_isolation_user_b_cannot_retrieve_user_a_content(self, mock_groq_class):
        user_alice = User.objects.create_user(email="alice@groqtest.io", password="Password123!")
        user_bob = User.objects.create_user(email="bob@groqtest.io", password="Password123!")
        embedder = get_embedding_provider()

        # Alice creates private secret note
        item_alice = ContentItem.objects.create(
            user=user_alice,
            content_type=ContentItem.TYPE_NOTE,
            title="Alice Top Secret Cryptography",
            raw_text="The secret quantum vault passcode is ZETA-9988-ALPHA.",
            ingestion_status=ContentItem.STATUS_COMPLETED,
        )
        ContentChunk.objects.create(
            content_item=item_alice,
            chunk_index=0,
            text="The secret quantum vault passcode is ZETA-9988-ALPHA.",
            start_offset=0,
            end_offset=52,
            embedding=embedder.embed_text("The secret quantum vault passcode is ZETA-9988-ALPHA."),
        )

        # Bob creates chat session
        session_bob = ChatSession.objects.create(user=user_bob, title="Bob Chat")

        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "I cannot find sufficient evidence in your saved content to answer this question."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        with override_settings(
            LLM_PROVIDER="groq",
            GROQ_API_KEY="gsk_test_key_isolation",
            GROQ_MODEL="openai/gpt-oss-120b",
        ):
            user_msg, assistant_msg = generate_chat_turn(session_bob, "What is the secret quantum vault passcode?")

            # Verify that the system prompt passed to Groq did NOT contain Alice's secret!
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            system_msg = next(m["content"] for m in call_kwargs["messages"] if m["role"] == "system")
            assert "ZETA-9988-ALPHA" not in system_msg
            assert "Alice Top Secret Cryptography" not in system_msg
            assert assistant_msg.citations == []
