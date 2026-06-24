"""Tests for LLM Retry Utility, Budget Tracking, and Fallback Routing.

Covers:
    - rate-limit-then-success (exponential backoff on 429 RPM)
    - daily-quota-no-retry (immediate LLMRateLimitError)
    - auth-error-no-retry (immediate LLMAuthError)
    - transient-error-retry (exponential backoff on 5xx)
    - malformed-json-one-retry-then-fallback (single nudge in chat, then fallback)
    - budget-exhausted-skips-call-entirely (skips API call entirely, triggers fallback)
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from llm.base import (
    LLMRateLimitError,
    LLMAuthError,
    LLMTransientError,
    LLMInvalidResponseError,
)
from llm.retry import execute_with_retry
from llm.gemini_provider import GeminiProvider
from llm.budget import reset_call_count
from agents.base_agent import BaseAgent
from models.proposal import Proposal
from models.agent_output import AgentOutput
from engine.state import create_initial_proposal
from services.gemini_explainer import generate_judge_brief


# Dummy concrete agent for testing fallback routing
class RetryMockAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "community"

    @property
    def personality_brief(self) -> str:
        return "Mock personality brief."

    @property
    def risk_tolerance(self) -> str:
        return "mock risk tolerance"

    def evaluate(self, proposal: Proposal, context: dict) -> AgentOutput:

        return AgentOutput(
            agent_name="community",
            score=85.0,
            verdict="modify",
            proposed_changes={"green_space_pct": 25.0},
            reasoning_and_evidence="Community fallback reasoning.",
        )


@pytest.fixture(autouse=True)
def clean_budget():
    reset_call_count()
    yield
    reset_call_count()


@patch("time.sleep")
class TestRetryUtility:
    def test_rate_limit_then_success(self, mock_sleep) -> None:
        """Test exponential backoff on 429 RPM error, succeeding on attempt 3."""
        mock_func = MagicMock()
        mock_func.side_effect = [
            Exception("429 ResourceExhausted: Too many requests per minute"),
            Exception("429 ResourceExhausted: Too many requests per minute"),
            "success_result",
        ]
        result = execute_with_retry(mock_func, "arg1", kw="val")
        assert result == "success_result"
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2

    def test_daily_quota_no_retry(self, mock_sleep) -> None:
        """Test that 429 with daily quota framing raises immediately without retry."""
        mock_func = MagicMock()
        mock_func.side_effect = Exception("429 Quota Exceeded: Daily limit reached")
        with pytest.raises(LLMRateLimitError, match="Daily quota likely exhausted"):
            execute_with_retry(mock_func)
        assert mock_func.call_count == 1
        assert mock_sleep.call_count == 0

    def test_auth_error_no_retry(self, mock_sleep) -> None:
        """Test that 403 Auth error raises immediately without retry."""
        mock_func = MagicMock()
        mock_func.side_effect = Exception("403 Forbidden: Invalid API key")
        with pytest.raises(LLMAuthError, match="Invalid or missing API key"):
            execute_with_retry(mock_func)
        assert mock_func.call_count == 1
        assert mock_sleep.call_count == 0

    def test_transient_error_retry(self, mock_sleep) -> None:
        """Test that 5xx transient error retries up to 3 times before raising."""
        mock_func = MagicMock()
        mock_func.side_effect = Exception("503 Service Unavailable: Server overloaded")
        with pytest.raises(LLMTransientError, match="Transient error persisted"):
            execute_with_retry(mock_func)
        assert mock_func.call_count == 4  # Initial + 3 retries
        assert mock_sleep.call_count == 3


class TestGeminiProviderAdvanced:
    @patch("llm.gemini_provider.genai.Client")
    def test_malformed_json_one_retry_then_fallback(self, mock_client_cls) -> None:
        """Test JSON decode failure triggers a single nudge in chat, then fallback."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        # Return invalid JSON on initial prompt AND on the nudge prompt
        mock_response_1 = MagicMock()
        mock_response_1.function_calls = []
        mock_response_1.text = "Here is some text but not JSON"

        mock_response_2 = MagicMock()
        mock_response_2.function_calls = []
        mock_response_2.text = "Still not valid JSON"

        mock_chat.send_message.side_effect = [mock_response_1, mock_response_2]

        agent = RetryMockAgent()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key", "LLM_PROVIDER": "gemini"}):
            proposal = create_initial_proposal("phoenix_az")
            opinion = agent.generate_opinion(proposal, {})

            # Must have attempted twice in chat (initial + nudge)
            assert mock_chat.send_message.call_count == 2
            # Must have cleanly routed to fallback
            assert opinion.score == 85.0
            assert opinion.recommendation == {"green_space_pct": 25.0}
            assert "deterministic fallback" in opinion.position
            assert "Invalid model response" in opinion.position

    @patch("llm.gemini_provider.genai.Client")
    def test_budget_exhausted_skips_call_entirely(self, mock_client_cls) -> None:
        """Test that when budget is exhausted, API calls are skipped entirely."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        agent = RetryMockAgent()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key", "LLM_DAILY_BUDGET": "5"}):
            import llm.budget
            llm.budget._DAILY_CALL_COUNT = 5  # Exhaust budget

            proposal = create_initial_proposal("phoenix_az")
            opinion = agent.generate_opinion(proposal, {})

            # Must NOT have called send_message
            assert mock_chat.send_message.call_count == 0
            # Must have cleanly routed to fallback
            assert opinion.score == 85.0
            assert opinion.recommendation == {"green_space_pct": 25.0}
            assert "Daily budget exhausted" in opinion.position

            # Test GeminiExplainer budget skip
            mock_session = MagicMock()
            mock_session.debate_rounds = []
            mock_session.override_history = []
            mock_session.current_proposal = proposal

            brief = generate_judge_brief(mock_session)
            assert brief == "Daily budget exhausted. Automated judge brief unavailable."
