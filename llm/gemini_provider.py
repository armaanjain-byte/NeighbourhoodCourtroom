"""Google Gemini LLM Provider Implementation.

Implements the LLMProvider interface using direct REST API calls via requests,
incorporating production-grade retry logic, request timeouts, daily budget tracking,
and JSON validation nudging.
"""

from __future__ import annotations

import os
import json
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
    import requests
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

logger = logging.getLogger(__name__)


class GeminiRestResponse:
    """Encapsulates a Gemini REST API response to maintain compatibility with existing attributes."""

    def __init__(self, raw_data: dict) -> None:
        self.raw_data = raw_data

    @property
    def text(self) -> str:
        try:
            parts = self.raw_data.get("candidates", [])[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts if "text" in p)
        except Exception:
            return ""

    @property
    def function_calls(self) -> list[Any]:
        class FuncCall:
            def __init__(self, name: str, args: dict) -> None:
                self.name = name
                self.args = args

        try:
            parts = self.raw_data.get("candidates", [])[0].get("content", {}).get("parts", [])
            calls = []
            for p in parts:
                if "functionCall" in p:
                    fc = p["functionCall"]
                    calls.append(FuncCall(fc.get("name", ""), fc.get("args", {})))
            return calls
        except Exception:
            return []


class GeminiRestChat:
    """Maintains conversation history and provides send_message functionality via Gemini REST API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        system_instruction: str | None = None,
        tools: list[dict] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        self.system_instruction = system_instruction
        self.tools = tools
        self.contents: list[dict] = []

    def send_message(self, content_parts: str | list[dict]) -> GeminiRestResponse:
        if isinstance(content_parts, str):
            new_content = {"role": "user", "parts": [{"text": content_parts}]}
        else:
            role = "user"
            if any("functionResponse" in p for p in content_parts):
                role = "tool"
            new_content = {"role": role, "parts": content_parts}

        self.contents.append(new_content)

        payload: dict[str, Any] = {
            "contents": self.contents
        }
        if self.system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": self.system_instruction}]}
        if self.tools:
            payload["tools"] = self.tools

        response = requests.post(self.url, json=payload, timeout=15.0)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError(
                f"{response.status_code} Error: {response.text}", response=response
            )

        resp_json = response.json()
        try:
            model_content = resp_json.get("candidates", [])[0].get("content")
            if model_content:
                self.contents.append(model_content)
        except Exception:
            pass

        return GeminiRestResponse(resp_json)


class GeminiProvider(LLMProvider):
    """LLMProvider implementation for Google Gemini using direct REST API calls via requests."""

    def generate_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        tool_declarations: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Any] | None = None,
        required_keys: set[str] | None = None,
    ) -> dict:
        if not HAS_GEMINI:
            raise LLMProviderError("requests package is not installed")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMAuthError("Gemini not configured")

        try:
            tools = [{"function_declarations": tool_declarations}] if tool_declarations else None
            chat = GeminiRestChat(
                api_key=api_key,
                model="gemini-2.5-flash",
                system_instruction=system_instruction,
                tools=tools,
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

                        part_dicts.append({
                            "functionResponse": {
                                "name": name,
                                "response": result
                            }
                        })

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
                if not response.text or not response.text.strip():
                    raise LLMInvalidResponseError("Empty response received from Gemini")
                data = _parse_and_validate(response.text)
            except LLMInvalidResponseError as e:
                if not response.text or not response.text.strip():
                    logger.warning(f"Empty response encountered: {e}. Skipping nudge and making a SECOND fresh API call.")
                    fresh_chat = GeminiRestChat(
                        api_key=api_key,
                        model="gemini-2.5-flash",
                        system_instruction=system_instruction,
                    )
                    fresh_prompt = "Respond with valid JSON only.\n" + user_prompt
                    resp2 = execute_with_retry(fresh_chat.send_message, fresh_prompt)
                    if not resp2.text or not resp2.text.strip():
                        logger.error("Second fresh API call also returned empty response. Falling back immediately.")
                        raise LLMInvalidResponseError("Second fresh API call returned empty response")
                    try:
                        data = _parse_and_validate(resp2.text)
                    except LLMInvalidResponseError as e2:
                        logger.error(f"LLMInvalidResponseError: Second fresh API call failed to produce valid JSON: {e2}")
                        raise LLMInvalidResponseError(f"Failed to produce valid JSON on fresh retry: {e2}") from e2
                else:
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
            if "API key" in error_msg or "400" in error_msg or "401" in error_msg or "403" in error_msg or "APIError" in err_type or "Auth" in err_type:
                raise LLMAuthError(f"Invalid or missing Gemini API key: {e}") from e
            if "50" in error_msg or "Transient" in err_type or "Unavailable" in err_type or "Internal" in err_type or "Timeout" in err_type or "Connection" in err_type:
                raise LLMTransientError(f"Transient error occurred: {e}") from e
            raise LLMProviderError(f"Gemini execution failed: {e}") from e

    def generate_text(self, system_instruction: str, user_prompt: str) -> str:
        if not HAS_GEMINI:
            raise LLMProviderError("requests package is not installed")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMAuthError("Gemini API key not found")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}]
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        def _make_request():
            resp = requests.post(url, json=payload, timeout=15.0)
            if resp.status_code != 200:
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error: {resp.text}", response=resp
                )
            return resp.json()

        try:
            data = execute_with_retry(_make_request)
            try:
                text = data.get("candidates", [])[0].get("content", {}).get("parts", [])[0].get("text", "")
                if not text or not text.strip():
                    raise LLMInvalidResponseError("Empty response received from Gemini")
            except (IndexError, KeyError, TypeError) as e:
                raise LLMInvalidResponseError(f"Malformed response structure: {e}") from e

            increment_call_count()
            return text.strip()
        except Exception as e:
            if isinstance(e, (LLMProviderError, LLMRateLimitError, LLMAuthError, LLMTransientError, LLMInvalidResponseError)):
                raise e
            error_msg = str(e)
            err_type = type(e).__name__
            if "429" in error_msg or "ResourceExhausted" in err_type:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
            if "API key" in error_msg or "400" in error_msg or "401" in error_msg or "403" in error_msg or "APIError" in err_type or "Auth" in err_type:
                raise LLMAuthError(f"Invalid or missing Gemini API key: {e}") from e
            if "50" in error_msg or "Transient" in err_type or "Unavailable" in err_type or "Internal" in err_type or "Timeout" in err_type or "Connection" in err_type:
                raise LLMTransientError(f"Transient error occurred: {e}") from e
            raise LLMProviderError(f"Gemini execution failed: {e}") from e
