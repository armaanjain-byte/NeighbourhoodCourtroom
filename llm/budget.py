"""Daily Budget Tracker for LLM API calls.

Provides lightweight in-memory tracking of daily API usage.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Module-level counter for in-memory daily budget tracking.
# Note: This is a best-effort client-side estimate, not authoritative.
# The real limit is enforced server-side by the LLM provider.
_DAILY_CALL_COUNT = 0


def get_daily_budget() -> int:
    """Retrieve the configured daily budget from environment."""
    return int(os.environ.get("LLM_DAILY_BUDGET", 200))


def is_budget_exhausted() -> bool:
    """Check if the daily budget has been reached or exceeded."""
    budget = get_daily_budget()
    exhausted = _DAILY_CALL_COUNT >= budget
    if exhausted:
        logger.warning(
            f"LLM daily budget estimated to be exhausted ({_DAILY_CALL_COUNT}/{budget} calls). "
            "Skipping API call."
        )
    return exhausted


def increment_call_count() -> None:
    """Increment the daily call count after a successful API call."""
    global _DAILY_CALL_COUNT
    _DAILY_CALL_COUNT += 1
    logger.info(f"LLM call successful. Daily call count incremented to {_DAILY_CALL_COUNT}/{get_daily_budget()}.")


def reset_call_count() -> None:
    """Reset call count (useful for testing)."""
    global _DAILY_CALL_COUNT
    _DAILY_CALL_COUNT = 0
