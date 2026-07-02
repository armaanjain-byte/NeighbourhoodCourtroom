"""Tests for ProviderChain and failover behaviour."""

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
from llm.provider_chain import ProviderChain
from llm.provider_factory import get_provider


def test_provider_chain_initialization() -> None:
    """Test ProviderChain initializes with valid provider names."""
    chain = ProviderChain(["gemini", "groq"])
    assert chain._provider_names == ["gemini", "groq"]
    
    with pytest.raises(ValueError):
        ProviderChain([])


@patch("llm.provider_chain.ProviderChain._get_provider")
def test_provider_chain_immediate_failover_ratelimit(mock_get_provider) -> None:
    """Test immediate failover on LLMRateLimitError."""
    mock_p1 = MagicMock(spec=LLMProvider)
    mock_p1.generate_structured.side_effect = LLMRateLimitError("Quota exceeded")
    
    mock_p2 = MagicMock(spec=LLMProvider)
    mock_p2.generate_structured.return_value = {"score": 85.0}
    
    # Return mock_p1 for first call, mock_p2 for second call
    mock_get_provider.side_effect = [mock_p1, mock_p2]
    
    chain = ProviderChain(["gemini", "groq"])
    res = chain.generate_structured("system", "user")
    
    assert res == {"score": 85.0}
    assert mock_p1.generate_structured.call_count == 1
    assert mock_p2.generate_structured.call_count == 1


@patch("llm.provider_chain.ProviderChain._get_provider")
def test_provider_chain_immediate_failover_auth(mock_get_provider) -> None:
    """Test immediate failover on LLMAuthError."""
    mock_p1 = MagicMock(spec=LLMProvider)
    mock_p1.generate_text.side_effect = LLMAuthError("Invalid key")
    
    mock_p2 = MagicMock(spec=LLMProvider)
    mock_p2.generate_text.return_value = "Success text"
    
    mock_get_provider.side_effect = [mock_p1, mock_p2]
    
    chain = ProviderChain(["gemini", "groq"])
    res = chain.generate_text("system", "user")
    
    assert res == "Success text"
    assert mock_p1.generate_text.call_count == 1
    assert mock_p2.generate_text.call_count == 1


@patch("llm.provider_chain.ProviderChain._get_provider")
def test_provider_chain_all_exhausted(mock_get_provider) -> None:
    """Test LLMProviderError raised when all providers fail."""
    mock_p1 = MagicMock(spec=LLMProvider)
    mock_p1.generate_structured.side_effect = LLMRateLimitError("Quota p1")
    
    mock_p2 = MagicMock(spec=LLMProvider)
    mock_p2.generate_structured.side_effect = LLMTransientError("Transient p2")
    
    mock_get_provider.side_effect = [mock_p1, mock_p2]
    
    chain = ProviderChain(["gemini", "groq"])
    with pytest.raises(LLMProviderError) as exc_info:
        chain.generate_structured("system", "user")
        
    assert "All providers in chain exhausted" in str(exc_info.value)
    assert "gemini:LLMRateLimitError" in str(exc_info.value)
    assert "groq:LLMTransientError" in str(exc_info.value)


@patch.dict("os.environ", {"LLM_PROVIDER_CHAIN": "gemini, groq , openrouter"})
def test_provider_factory_chain_env() -> None:
    """Test get_provider returns ProviderChain when LLM_PROVIDER_CHAIN is set."""
    provider = get_provider()
    assert isinstance(provider, ProviderChain)
    assert provider._provider_names == ["gemini", "groq", "openrouter"]
