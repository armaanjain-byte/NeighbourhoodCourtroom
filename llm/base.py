"""Abstract LLM Provider and Exception Hierarchy.

Defines the contract for all LLM providers (Gemini, Groq, OpenAI, etc.)
and a unified exception hierarchy.
"""

from __future__ import annotations

import abc
from typing import Any, Callable


# ── Exception Hierarchy ──────────────────────────────────────────────────────

class LLMProviderError(Exception):
    """Base exception for all LLM provider errors."""
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when an LLM provider rate limit (e.g. 429) is exceeded."""
    pass


class LLMAuthError(LLMProviderError):
    """Raised when authentication fails (missing/invalid API key)."""
    pass


class LLMTransientError(LLMProviderError):
    """Raised on temporary network or server errors (e.g. 5xx)."""
    pass


class LLMInvalidResponseError(LLMProviderError):
    """Raised when the model produces invalid or unparseable output (e.g. bad JSON)."""
    pass


# ── Abstract Base Class ──────────────────────────────────────────────────────

class LLMProvider(abc.ABC):
    """Abstract base class for provider-agnostic LLM integrations."""

    @abc.abstractmethod
    def generate_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        tool_declarations: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Any] | None = None,
        required_keys: set[str] | None = None,
    ) -> dict:
        """Generate a structured response, handling multi-turn tool calling loops internally.

        Parameters
        ----------
        system_instruction : str
            The system prompt / instructions for the model.
        user_prompt : str
            The initial user prompt.
        tool_declarations : list[dict] | None, optional
            List of tool/function declarations for the model to use.
        tool_executor : Callable[[str, dict], Any] | None, optional
            Callback function taking (tool_name, tool_args) and returning the tool result.

        Returns
        -------
        dict
            The parsed JSON response as a dictionary, including at minimum a 'text' field
            containing the raw model output string, and a 'tool_results' field containing
            a list of dictionaries of tool calls made during the session (e.g. [{"name": ..., "args": ..., "result": ...}]).

        Raises
        ------
        LLMProviderError
            If the generation fails or turn limit is exceeded.
        """
        pass  # pragma: no cover

    @abc.abstractmethod
    def generate_text(self, system_instruction: str, user_prompt: str) -> str:
        """Generate a simple one-shot text completion without tools.

        Parameters
        ----------
        system_instruction : str
            The system prompt / instructions for the model.
        user_prompt : str
            The user prompt.

        Returns
        -------
        str
            The resulting text string from the model.

        Raises
        ------
        LLMProviderError
            If the generation fails.
        """
        pass  # pragma: no cover
