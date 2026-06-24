"""Provider Factory.

Instantiates the appropriate LLMProvider based on configuration.
"""

from __future__ import annotations

import os
from llm.base import LLMProvider, LLMProviderError


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """Instantiate and return the configured LLMProvider.

    Reads LLM_PROVIDER from environment if provider_name is not specified.
    Defaults to 'gemini'.

    Parameters
    ----------
    provider_name : str | None, optional
        Explicit provider name to instantiate (e.g. 'gemini', 'groq').

    Returns
    -------
    LLMProvider
        The instantiated LLMProvider object.

    Raises
    ------
    ValueError
        If an unknown provider name is requested.
    """
    if provider_name is None:
        provider_name = os.environ.get("LLM_PROVIDER", "gemini").lower()

    if provider_name == "gemini":
        from llm.gemini_provider import GeminiProvider
        return GeminiProvider()
    # Future providers (groq, openrouter, openai) will be added here
    raise ValueError(f"Unknown LLM provider: {provider_name}")
