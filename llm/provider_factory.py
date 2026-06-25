"""Provider Factory.

Instantiates the appropriate LLMProvider based on configuration.

New: if the environment variable ``LLM_PROVIDER_CHAIN`` is set (a
comma-separated list, e.g. ``"gemini,groq,openrouter"``), a
:class:`~llm.provider_chain.ProviderChain` wrapping each named provider is
returned instead of a single provider.  This is fully additive — existing
single-provider behaviour via ``LLM_PROVIDER`` is preserved when
``LLM_PROVIDER_CHAIN`` is not set.
"""

from __future__ import annotations

import os
from llm.base import LLMProvider, LLMProviderError


def _make_single_provider(provider_name: str) -> LLMProvider:
    """Instantiate a single named LLMProvider.

    This is a package-level helper used by both :func:`get_provider` and
    :class:`~llm.provider_chain.ProviderChain`.

    Parameters
    ----------
    provider_name : str
        The provider to instantiate (e.g. ``'gemini'``, ``'groq'``).

    Returns
    -------
    LLMProvider
    """
    name = provider_name.lower().strip()
    if name == "gemini":
        from llm.gemini_provider import GeminiProvider
        return GeminiProvider()
    from llm.universal_provider import UniversalProvider
    return UniversalProvider(provider_name=name)


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """Instantiate and return the configured LLMProvider.

    Resolution order
    ----------------
    1. If ``LLM_PROVIDER_CHAIN`` is set in the environment, return a
       :class:`~llm.provider_chain.ProviderChain` over the listed providers.
    2. Otherwise, read ``LLM_PROVIDER`` (or the explicit *provider_name*
       argument) and return a single provider.  Defaults to ``'gemini'``.

    Parameters
    ----------
    provider_name : str | None, optional
        Explicit provider name to instantiate.  Ignored when
        ``LLM_PROVIDER_CHAIN`` is set.

    Returns
    -------
    LLMProvider
        The instantiated provider or chain.

    Raises
    ------
    ValueError
        If an unknown provider name is requested.
    """
    # ── Chain mode ────────────────────────────────────────────────────────────
    chain_env = os.environ.get("LLM_PROVIDER_CHAIN", "").strip()
    if chain_env:
        from llm.provider_chain import ProviderChain
        names = [n.strip() for n in chain_env.split(",") if n.strip()]
        if names:
            return ProviderChain(names)

    # ── Single-provider mode (unchanged) ─────────────────────────────────────
    if provider_name is None:
        provider_name = os.environ.get("LLM_PROVIDER", "gemini").lower()
    return _make_single_provider(provider_name)
