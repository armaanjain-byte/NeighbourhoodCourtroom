"""Tests for LLM Abstraction Layer (llm/ package).

Covers:
    - Provider factory selection logic (default, explicit, unknown)
    - GeminiProvider successful structured & text generation
    - Exception mapping (RateLimit, Auth, Transient, InvalidResponse)
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMAuthError,
    LLMTransientError,
    LLMInvalidResponseError,
)
from llm.provider_factory import get_provider
from llm.gemini_provider import GeminiProvider


class TestProviderFactory:
    def test_get_provider_default(self) -> None:
        """By default, or with LLM_PROVIDER=gemini, get_provider should return GeminiProvider."""
        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini"}):
            provider = get_provider()
            assert isinstance(provider, GeminiProvider)

    def test_get_provider_explicit(self) -> None:
        """Passing 'gemini' explicitly should return GeminiProvider."""
        provider = get_provider("gemini")
        assert isinstance(provider, GeminiProvider)

    def test_get_provider_unknown(self) -> None:
        """Requesting an unknown provider must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM provider: unknown_ai"):
            get_provider("unknown_ai")


class TestGeminiProvider:
    @patch("llm.gemini_provider.genai.Client")
    def test_generate_text_success(self, mock_client_cls) -> None:
        """Test successful text generation."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()
            result = provider.generate_text("System", "Prompt")
            assert result == "Hello world"

    def test_missing_api_key(self) -> None:
        """Missing API key must raise LLMAuthError."""
        with patch.dict("os.environ", {}, clear=True):
            provider = GeminiProvider()
            with pytest.raises(LLMAuthError, match="Gemini API key not found"):
                provider.generate_text("System", "Prompt")
            with pytest.raises(LLMAuthError, match="Gemini not configured"):
                provider.generate_structured("System", "Prompt")

    @patch("llm.gemini_provider.genai.Client")
    def test_generate_structured_success(self, mock_client_cls) -> None:
        """Test successful structured generation with JSON parsing."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        mock_response = MagicMock()
        mock_response.function_calls = []
        mock_response.text = '{"score": 95.0, "verdict": "accept"}'
        mock_chat.send_message.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()
            data = provider.generate_structured("System", "Prompt")
            assert data["score"] == 95.0
            assert data["verdict"] == "accept"
            assert data["text"] == '{"score": 95.0, "verdict": "accept"}'

    @patch("llm.gemini_provider.genai.Client")
    def test_generate_structured_invalid_json(self, mock_client_cls) -> None:
        """Unparseable JSON must raise LLMInvalidResponseError."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        mock_response = MagicMock()
        mock_response.function_calls = []
        mock_response.text = 'invalid json'
        mock_chat.send_message.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()
            with pytest.raises(LLMInvalidResponseError, match="Failed to parse JSON response"):
                provider.generate_structured("System", "Prompt")

    @patch("llm.gemini_provider.genai.Client")
    def test_exception_mapping(self, mock_client_cls) -> None:
        """Test SDK exceptions are mapped to the common exception hierarchy."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()

            # Rate limit (429)
            mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted")
            with pytest.raises(LLMRateLimitError):
                provider.generate_text("System", "Prompt")

            # Auth error (403)
            mock_client.models.generate_content.side_effect = Exception("403 Forbidden: API key invalid")
            with pytest.raises(LLMAuthError):
                provider.generate_text("System", "Prompt")

            # Transient server error (503)
            mock_client.models.generate_content.side_effect = Exception("503 Service Unavailable")
            with pytest.raises(LLMTransientError):
                provider.generate_text("System", "Prompt")

            # Generic error
            mock_client.models.generate_content.side_effect = Exception("Some unknown error")
            with pytest.raises(LLMProviderError):
                provider.generate_text("System", "Prompt")
