"""Google Gemini LLM Provider Implementation.

Implements the LLMProvider interface using the google-genai SDK,
incorporating production-grade retry logic, request timeouts, daily budget tracking,
and JSON validation nudging.
"""

from __future__ import annotations

import os
import json
import time
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
from llm.retry import execute_with_retry
from llm.budget import increment_call_count

try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """LLMProvider implementation for Google Gemini using google-genai."""

    def generate_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        tool_declarations: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Any] | None = None,
        required_keys: set[str] | None = None,
    ) -> dict:
        if not HAS_GEMINI:
            raise LLMProviderError("google-genai package is not installed")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMAuthError("Gemini not configured")

        try:
            # Set request timeout (30s) on every individual API call
            client = genai.Client(api_key=api_key, http_options={"timeout": 30.0})
            tools = [{"function_declarations": tool_declarations}] if tool_declarations else None
            chat = client.chats.create(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools,
                )
            )

            def _send(msg):
                return execute_with_retry(chat.send_message, msg)

            response = _send(user_prompt)

            tool_results_list = []
            turn_limit = 5
            for _ in range(turn_limit):
                if response.function_calls:
                    part_dicts = []
                    for function_call in response.function_calls:
                        name = function_call.name
                        args = {k: v for k, v in function_call.args.items()}
                        try:
                            if tool_executor:
                                result = tool_executor(name, args)
                            else:
                                result = {"error": f"No tool executor provided for {name}"}
                            if not isinstance(result, dict):
                                result = {"result": result}
                        except Exception as e:
                            result = {"error": str(e)}

                        tool_results_list.append({"name": name, "args": args, "result": result})

                        part_dicts.append(
                            types.Part.from_function_response(
                                name=name,
                                response=result
                            )
                        )

                    response = _send(part_dicts)
                else:
                    break
            else:
                raise LLMProviderError("Turn limit exceeded. Agent got stuck in a function calling loop.")

            def _parse_and_validate(resp_text):
                raw = resp_text.strip()
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise LLMInvalidResponseError("Parsed JSON is not a dictionary")
                    if required_keys and not required_keys.issubset(data.keys()):
                        missing = required_keys - data.keys()
                        raise LLMInvalidResponseError(f"LLM response missing keys: {missing}")
                    data["text"] = raw
                    data["tool_results"] = tool_results_list
                    return data
                except json.JSONDecodeError as e:
                    raise LLMInvalidResponseError(f"Failed to parse JSON response: {e}")

            try:
                data = _parse_and_validate(response.text)
            except LLMInvalidResponseError as e:
                logger.warning(f"Invalid JSON or missing keys encountered: {e}. Nudging model once in same chat.")
                nudge_msg = (
                    "Your previous response was invalid or missing required keys. "
                    "Please return ONLY valid JSON matching the exact schema requested, with no markdown fences."
                )
                response = _send(nudge_msg)
                try:
                    data = _parse_and_validate(response.text)
                except LLMInvalidResponseError as e2:
                    logger.error(f"LLMInvalidResponseError: Second attempt failed after nudge: {e2}")
                    raise LLMInvalidResponseError(f"Failed to produce valid JSON after nudge: {e2}") from e2

            increment_call_count()
            return data

        except Exception as e:
            if isinstance(e, (LLMProviderError, LLMRateLimitError, LLMAuthError, LLMTransientError, LLMInvalidResponseError)):
                raise e
            error_msg = str(e)
            err_type = type(e).__name__
            if "429" in error_msg or "ResourceExhausted" in err_type:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
            if "API key" in error_msg or "400" in error_msg or "403" in error_msg or "APIError" in err_type or "Auth" in err_type:
                raise LLMAuthError(f"Invalid or missing Gemini API key: {e}") from e
            if "50" in error_msg or "Transient" in err_type or "Unavailable" in err_type or "Internal" in err_type:
                raise LLMTransientError(f"Transient error occurred: {e}") from e
            raise LLMProviderError(f"Gemini execution failed: {e}") from e

    def generate_text(self, system_instruction: str, user_prompt: str) -> str:
        if not HAS_GEMINI:
            raise LLMProviderError("google-genai package is not installed")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMAuthError("Gemini API key not found")

        try:
            client = genai.Client(api_key=api_key, http_options={"timeout": 30.0})
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
            ) if system_instruction else None

            response = execute_with_retry(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=config
            )
            increment_call_count()
            return response.text.strip()
        except Exception as e:
            if isinstance(e, (LLMProviderError, LLMRateLimitError, LLMAuthError, LLMTransientError, LLMInvalidResponseError)):
                raise e
            error_msg = str(e)
            err_type = type(e).__name__
            if "429" in error_msg or "ResourceExhausted" in err_type:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
            if "API key" in error_msg or "400" in error_msg or "403" in error_msg or "APIError" in err_type or "Auth" in err_type:
                raise LLMAuthError(f"Invalid or missing Gemini API key: {e}") from e
            if "50" in error_msg or "Transient" in err_type or "Unavailable" in err_type or "Internal" in err_type:
                raise LLMTransientError(f"Transient error occurred: {e}") from e
            raise LLMProviderError(f"Gemini execution failed: {e}") from e
