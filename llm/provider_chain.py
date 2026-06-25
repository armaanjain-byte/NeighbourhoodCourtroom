"""Provider Failover Chain.

Wraps an ordered list of LLMProvider instances and tries each in sequence,
applying provider-specific failover rules so the system survives any single
provider quota exhaustion, auth failure, or outage transparently.

Failover rules
--------------
- LLMRateLimitError  -> immediate failover (no retry on exhausted provider)
- LLMAuthError       -> immediate failover (bad key should not block the chain)
- LLMTransientError  -> provider own retry already ran; failover if still failing
- LLMInvalidResponse -> provider own nudge already ran; failover if still failing
- LLMProviderError   -> immediate failover

If ALL providers fail, a single consolidated LLMProviderError is raised
containing a per-provider failure summary.  This is caught by base_agent.py
existing fallback-to-deterministic path.

Raw exception text (JSON blobs, stack traces, etc.) is intentionally kept out
of the raised exception message -- only provider name and error TYPE are
surfaced.  Full detail is logged at DEBUG level for developer inspection.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMAuthError,
    LLMTransientError,
    LLMInvalidResponseError,
)

logger = logging.getLogger(__name__)

# Errors that warrant IMMEDIATE failover (no point retrying the same provider)
_IMMEDIATE_FAILOVER = (LLMRateLimitError, LLMAuthError)

# Errors where provider retry/nudge logic already ran before we see it
_AFTER_RETRY_FAILOVER = (LLMTransientError, LLMInvalidResponseError, LLMProviderError)


class ProviderChain(LLMProvider):
    """Ordered failover chain over multiple LLMProvider instances.

    Parameters
    ----------
    provider_names : list[str]
        Ordered list of provider names to try
        (e.g. ["gemini", "groq", "openrouter"]).
        Each provider is instantiated lazily on first use.
    """

    def __init__(self, provider_names: list[str]) -> None:
        if not provider_names:
            raise ValueError("ProviderChain requires at least one provider name.")
        self._provider_names = provider_names
        self._providers: dict[str, LLMProvider] = {}

    def _get_provider(self, name: str) -> LLMProvider:
        """Lazily instantiate a provider by name."""
        if name not in self._providers:
            from llm.provider_factory import _make_single_provider
            self._providers[name] = _make_single_provider(name)
        return self._providers[name]

    def _try_each(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Try method_name on each provider in order, applying failover rules.

        Parameters
        ----------
        method_name : str
            Name of the LLMProvider method to call.
        *args, **kwargs
            Arguments forwarded to the method.

        Returns
        -------
        Any
            The result from the first provider that succeeds.

        Raises
        ------
        LLMProviderError
            If all providers in the chain fail.
        """
        total = len(self._provider_names)
        failures: list[str] = []

        for idx, name in enumerate(self._provider_names, start=1):
            logger.info("[CHAIN] Trying provider %d/%d: %s", idx, total, name)
            try:
                provider = self._get_provider(name)
                method = getattr(provider, method_name)
                result = method(*args, **kwargs)
                logger.info("[CHAIN] Provider %s succeeded.", name)
                return result

            except _IMMEDIATE_FAILOVER as exc:
                err_type = type(exc).__name__
                short_msg = str(exc)[:120]
                logger.warning(
                    "[CHAIN] Provider %s: %s -- immediate failover. msg=%s",
                    name, err_type, short_msg,
                )
                logger.debug("[CHAIN] Provider %s full error: %s", name, exc)
                if isinstance(exc, LLMAuthError):
                    logger.warning(
                        "[CHAIN] LLMAuthError from provider '%s' -- this likely "
                        "indicates a missing or invalid API key. Check configuration.",
                        name,
                    )
                failures.append(f"{name}:{err_type}")

            except (LLMTransientError, LLMInvalidResponseError, LLMProviderError) as exc:
                err_type = type(exc).__name__
                short_msg = str(exc)[:120]
                logger.warning(
                    "[CHAIN] Provider %s: %s (after own retries) -- failing over. msg=%s",
                    name, err_type, short_msg,
                )
                logger.debug("[CHAIN] Provider %s full error: %s", name, exc)
                failures.append(f"{name}:{err_type}")

            except Exception as exc:
                err_type = type(exc).__name__
                logger.warning(
                    "[CHAIN] Provider %s: unexpected %s -- failing over.",
                    name, err_type,
                )
                logger.debug("[CHAIN] Provider %s unexpected error: %s", name, exc)
                failures.append(f"{name}:{err_type}")

        # All providers exhausted
        summary = ", ".join(failures)
        logger.error("[CHAIN] All %d providers exhausted. Failures: %s", total, summary)
        raise LLMProviderError(
            f"All providers in chain exhausted ({summary}). "
            "Deterministic fallback will be used."
        )

    # ---- LLMProvider interface ----------------------------------------------

    def generate_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        tool_declarations: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Any] | None = None,
        required_keys: set[str] | None = None,
    ) -> dict:
        """Try each provider in order for a structured response."""
        return self._try_each(
            "generate_structured",
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            tool_declarations=tool_declarations,
            tool_executor=tool_executor,
            required_keys=required_keys,
        )

    def generate_text(self, system_instruction: str, user_prompt: str) -> str:
        """Try each provider in order for a plain text response."""
        return self._try_each(
            "generate_text",
            system_instruction=system_instruction,
            user_prompt=user_prompt,
        )
