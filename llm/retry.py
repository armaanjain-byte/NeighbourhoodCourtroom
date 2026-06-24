"""Retry Utility for LLM API Calls.

Provides production-grade exponential backoff with jitter, distinguishing between
short-lived rate limits (RPM), daily quota exhaustion (RPD), auth errors,
and transient network/server failures.
"""

import time
import random
import logging
from typing import Callable, Any

from llm.base import (
    LLMProviderError,
    LLMRateLimitError,
    LLMAuthError,
    LLMTransientError,
    LLMInvalidResponseError,
)

logger = logging.getLogger(__name__)


def execute_with_retry(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute an API call with exponential backoff and jitter, distinguishing error types.

    1. 429 with RESOURCE_EXHAUSTED + per-minute framing -> retry with backoff (max 4 retries, base 2s).
    2. 429 with daily/RPD framing -> do NOT retry, raise LLMRateLimitError immediately.
    3. 401/403/API key -> raise LLMAuthError immediately, never retry.
    4. 5xx / connection errors / timeouts -> retry with backoff (max 3 retries, base 1s).
    """
    attempt_rate_limit = 0
    attempt_transient = 0
    max_rate_limit = 4
    max_transient = 3

    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            err_type = type(e).__name__

            # Check Auth errors first
            if any(k in error_msg for k in ["401", "403", "API key"]) or any(k in err_type for k in ["Auth", "Forbidden"]):
                logger.error(f"LLMAuthError encountered: {e}. Raising immediately without retries.")
                if isinstance(e, LLMAuthError):
                    raise e
                raise LLMAuthError(f"Invalid or missing API key: {e}") from e

            # Check Rate Limit (429 / ResourceExhausted)
            if "429" in error_msg or "ResourceExhausted" in err_type or "QuotaExceeded" in err_type:
                # Check for daily quota exhaustion
                if any(k in error_msg.lower() for k in ["daily", "rpd", "quota exceeded", "per day"]):
                    logger.error(
                        f"LLMRateLimitError (Daily Quota Exhausted) encountered: {e}. "
                        "Raising immediately without retries."
                    )
                    raise LLMRateLimitError(f"Daily quota likely exhausted: {e}") from e

                # Otherwise, assume per-minute / RPM framing
                if attempt_rate_limit >= max_rate_limit:
                    logger.error(
                        f"LLMRateLimitError: Max retries ({max_rate_limit}) exhausted for rate limit error: {e}"
                    )
                    raise LLMRateLimitError(f"Rate limit exceeded after {max_rate_limit} retries: {e}") from e

                attempt_rate_limit += 1
                # Base delay 2s, doubling each retry, capped at 60s
                delay = min(60.0, 2.0 * (2 ** (attempt_rate_limit - 1)))
                # Random jitter (±20%)
                jitter = delay * 0.2 * (random.random() * 2 - 1)
                sleep_time = delay + jitter
                logger.warning(
                    f"Rate limit encountered (attempt {attempt_rate_limit}/{max_rate_limit}). "
                    f"Sleeping for {sleep_time:.2f}s before retry. Error: {e}"
                )
                time.sleep(sleep_time)
                continue

            # Check Transient / 5xx / Connection / Timeouts
            if any(k in error_msg for k in ["50", "timeout", "connection", "transient"]) or any(k in err_type for k in ["Transient", "Timeout", "Connection", "Unavailable", "Internal"]):
                if attempt_transient >= max_transient:
                    logger.error(
                        f"LLMTransientError: Max retries ({max_transient}) exhausted for transient error: {e}"
                    )
                    raise LLMTransientError(f"Transient error persisted after {max_transient} retries: {e}") from e

                attempt_transient += 1
                # Base delay 1s, doubling each retry, capped at 60s
                delay = min(60.0, 1.0 * (2 ** (attempt_transient - 1)))
                jitter = delay * 0.2 * (random.random() * 2 - 1)
                sleep_time = delay + jitter
                logger.warning(
                    f"Transient error encountered (attempt {attempt_transient}/{max_transient}). "
                    f"Sleeping for {sleep_time:.2f}s before retry. Error: {e}"
                )
                time.sleep(sleep_time)
                continue

            # Generic error
            if isinstance(e, (LLMProviderError, LLMRateLimitError, LLMAuthError, LLMTransientError, LLMInvalidResponseError)):
                raise e
            logger.error(f"Unexpected LLMProviderError encountered: {e}")
            raise LLMProviderError(f"LLM execution failed: {e}") from e
