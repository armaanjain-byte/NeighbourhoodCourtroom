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

    def test_get_provider_universal(self) -> None:
        """Requesting any non-gemini provider returns UniversalProvider."""
        from llm.universal_provider import UniversalProvider
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake_key"}):
            provider = get_provider("openrouter")
            assert isinstance(provider, UniversalProvider)
            assert provider.provider_name == "openrouter"


class TestGeminiProvider:
    @patch("requests.post")
    def test_generate_text_success(self, mock_post) -> None:
        """Test successful text generation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello world"}]}}]
        }
        mock_post.return_value = mock_response

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

    @patch("requests.post")
    def test_generate_structured_success(self, mock_post) -> None:
        """Test successful structured generation with JSON parsing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"score": 95.0, "verdict": "accept"}'}]}}]
        }
        mock_post.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()
            data = provider.generate_structured("System", "Prompt")
            assert data["score"] == 95.0
            assert data["verdict"] == "accept"
            assert data["text"] == '{"score": 95.0, "verdict": "accept"}'

    @patch("requests.post")
    def test_generate_structured_invalid_json(self, mock_post) -> None:
        """Unparseable JSON must raise LLMInvalidResponseError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "invalid json"}]}}]
        }
        mock_post.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()
            with pytest.raises(LLMInvalidResponseError, match="Failed to parse JSON response"):
                provider.generate_structured("System", "Prompt")

    @patch("requests.post")
    def test_exception_mapping(self, mock_post) -> None:
        """Test SDK exceptions are mapped to the common exception hierarchy."""
        import requests
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            provider = GeminiProvider()

            # Rate limit (429)
            mock_post.side_effect = requests.exceptions.HTTPError("429 ResourceExhausted")
            with pytest.raises(LLMRateLimitError):
                provider.generate_text("System", "Prompt")

            # Auth error (403)
            mock_post.side_effect = requests.exceptions.HTTPError("403 Forbidden: API key invalid")
            with pytest.raises(LLMAuthError):
                provider.generate_text("System", "Prompt")

            # Transient server error (503)
            mock_post.side_effect = requests.exceptions.HTTPError("503 Service Unavailable")
            with pytest.raises(LLMTransientError):
                provider.generate_text("System", "Prompt")

            # Generic error
            mock_post.side_effect = Exception("Some unknown error")
            with pytest.raises(LLMProviderError):
                provider.generate_text("System", "Prompt")


class TestUniversalProvider:
    @patch("urllib.request.urlopen")
    def test_generate_text_success(self, mock_urlopen) -> None:
        """Test successful text generation via REST."""
        from llm.universal_provider import UniversalProvider
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "Hello REST world"}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake_key"}):
            provider = UniversalProvider("openrouter")
            result = provider.generate_text("System", "Prompt")
            assert result == "Hello REST world"

    @patch("urllib.request.urlopen")
    def test_generate_structured_success(self, mock_urlopen) -> None:
        """Test successful structured generation via REST."""
        from llm.universal_provider import UniversalProvider
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "{\\"score\\": 95.0, \\"verdict\\": \\"accept\\"}"}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict("os.environ", {"GROQ_API_KEY": "fake_key"}):
            provider = UniversalProvider("groq")
            data = provider.generate_structured("System", "Prompt")
            assert data["score"] == 95.0
            assert data["verdict"] == "accept"

    def test_missing_api_key(self) -> None:
        """Missing API key must raise LLMAuthError."""
        from llm.universal_provider import UniversalProvider
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LLMAuthError, match="API key not found for provider 'openrouter'"):
                UniversalProvider("openrouter")

    @patch("urllib.request.urlopen")
    def test_anthropic_text_success(self, mock_urlopen) -> None:
        """Test successful text generation for Anthropic format."""
        from llm.universal_provider import UniversalProvider
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"content": [{"type": "text", "text": "Hello Anthropic"}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake_key"}):
            provider = UniversalProvider("anthropic")
            result = provider.generate_text("System", "Prompt")
            assert result == "Hello Anthropic"
