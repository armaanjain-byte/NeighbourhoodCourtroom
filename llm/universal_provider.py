"""Universal LLM Provider Implementation.

Dynamically supports any AI provider (OpenRouter, Groq, OpenAI, Anthropic,
DeepSeek, Together, vLLM, Ollama, etc.) via REST HTTP requests to standard
OpenAI Chat Completions or Anthropic endpoints.
"""

from __future__ import annotations

import os
import json
import logging
import urllib.request
import urllib.error
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

logger = logging.getLogger(__name__)


class UniversalProvider(LLMProvider):
    """Universal LLMProvider supporting any OpenAI-compatible or Anthropic endpoint."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name.lower()
        self.api_key = self._discover_api_key()
        self.base_url, self.default_model = self._configure_endpoint()

    def _discover_api_key(self) -> str:
        """Discover the API key from environment variables."""
        env_keys = [
            f"{self.provider_name.upper()}_API_KEY",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
        ]
        for k in env_keys:
            val = os.environ.get(k)
            if val:
                return val.strip().strip('"').strip("'")

        # Search for any variable containing the provider name and API_KEY
        for k, val in os.environ.items():
            if self.provider_name.upper() in k and "KEY" in k:
                return val.strip().strip('"').strip("'")

        raise LLMAuthError(
            f"API key not found for provider '{self.provider_name}'. "
            f"Please set {self.provider_name.upper()}_API_KEY or LLM_API_KEY."
        )

    def _configure_endpoint(self) -> tuple[str, str]:
        """Configure the base URL and default model for known providers."""
        custom_url = os.environ.get("LLM_BASE_URL")
        custom_model = os.environ.get("LLM_MODEL")

        if self.provider_name == "openrouter":
            url = custom_url or "https://openrouter.ai/api/v1/chat/completions"
            model = custom_model or "meta-llama/llama-3.3-70b-instruct"
        elif self.provider_name == "groq":
            url = custom_url or "https://api.groq.com/openai/v1/chat/completions"
            model = custom_model or "llama3-70b-8192"
        elif self.provider_name == "openai":
            url = custom_url or "https://api.openai.com/v1/chat/completions"
            model = custom_model or "gpt-4o"
        elif self.provider_name == "anthropic":
            url = custom_url or "https://api.anthropic.com/v1/messages"
            model = custom_model or "claude-3-7-sonnet-20250219"
        else:
            url = custom_url or f"https://api.{self.provider_name}.com/v1/chat/completions"
            model = custom_model or "default-model"

        return url, model

    def _normalize_schema(self, schema: Any) -> Any:
        """Recursively normalize Gemini uppercase types to standard JSON Schema lowercase types."""
        if isinstance(schema, dict):
            new_schema = {}
            for k, v in schema.items():
                if k == "type" and isinstance(v, str):
                    new_schema[k] = v.lower()
                else:
                    new_schema[k] = self._normalize_schema(v)
            return new_schema
        elif isinstance(schema, list):
            return [self._normalize_schema(item) for item in schema]
        return schema

    def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send HTTP POST request with retry wrapping and proper error mapping."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.provider_name == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
            if "Authorization" in headers:
                del headers["Authorization"]
        elif self.provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/armaanjain-byte/NeighbourhoodCourtroom"
            headers["X-Title"] = "NeighbourhoodCourtroom"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=headers, method="POST")

        def _call() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(req, timeout=30.0) as response:
                    resp_body = response.read().decode("utf-8")
                    return json.loads(resp_body)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                if e.code in (401, 403):
                    raise LLMAuthError(f"Authentication failed ({e.code}): {err_body}") from e
                elif e.code == 429:
                    raise LLMRateLimitError(f"Rate limit exceeded (429): {err_body}") from e
                elif 500 <= e.code < 600:
                    raise LLMTransientError(f"Server error ({e.code}): {err_body}") from e
                raise LLMProviderError(f"HTTP Error {e.code}: {err_body}") from e
            except urllib.error.URLError as e:
                raise LLMTransientError(f"Network connection error: {e}") from e

        result = execute_with_retry(_call)
        increment_call_count()
        return result

    def generate_text(self, system_instruction: str, user_prompt: str) -> str:
        if self.provider_name == "anthropic":
            payload = {
                "model": self.default_model,
                "system": system_instruction,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": 4096,
            }
            resp = self._make_request(payload)
            content = resp.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "").strip()
            return str(resp).strip()
        else:
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": user_prompt})
            payload = {
                "model": self.default_model,
                "messages": messages,
            }
            resp = self._make_request(payload)
            choices = resp.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""

    def generate_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        tool_declarations: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Any] | None = None,
        required_keys: set[str] | None = None,
    ) -> dict:
        messages = []
        if system_instruction:
            if self.provider_name != "anthropic":
                messages.append({"role": "system", "content": system_instruction})

        messages.append({"role": "user", "content": user_prompt})

        # Format tools for OpenAI/OpenRouter/Groq schema
        tools = []
        if tool_declarations:
            for td in tool_declarations:
                norm_td = self._normalize_schema(td)
                tools.append({
                    "type": "function",
                    "function": norm_td,
                })

        tool_results_list = []
        turn_limit = 5
        final_text = ""
        payload: dict[str, Any] = {}

        for _ in range(turn_limit):
            payload = {
                "model": self.default_model,
                "messages": messages,
            }
            if self.provider_name == "anthropic":
                payload["system"] = system_instruction
                payload["max_tokens"] = 4096
                if tool_declarations:
                    payload["tools"] = [self._normalize_schema(td) for td in tool_declarations]
            else:
                if tools:
                    payload["tools"] = tools

            resp = self._make_request(payload)

            if self.provider_name == "anthropic":
                stop_reason = resp.get("stop_reason")
                content = resp.get("content", [])

                txt_part = next((p for p in content if p.get("type") == "text"), None)
                if txt_part:
                    final_text = txt_part.get("text", "")

                if stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": content})
                    tool_uses = [p for p in content if p.get("type") == "tool_use"]

                    tool_resp_content = []
                    for tu in tool_uses:
                        t_name = tu.get("name")
                        t_args = tu.get("input", {})
                        try:
                            if tool_executor:
                                res = tool_executor(t_name, t_args)
                            else:
                                res = {"error": f"No tool executor provided for {t_name}"}
                            if not isinstance(res, dict):
                                res = {"result": res}
                        except Exception as e:
                            res = {"error": str(e)}

                        tool_results_list.append({"name": t_name, "args": t_args, "result": res})
                        tool_resp_content.append({
                            "type": "tool_result",
                            "tool_use_id": tu.get("id"),
                            "content": json.dumps(res)
                        })

                    messages.append({"role": "user", "content": tool_resp_content})
                    continue
                else:
                    break
            else:
                choice = resp.get("choices", [{}])[0]
                msg = choice.get("message", {})
                finish_reason = choice.get("finish_reason")

                if msg.get("content"):
                    final_text = msg.get("content")

                tool_calls = msg.get("tool_calls")
                if tool_calls or finish_reason == "tool_calls":
                    assistant_msg = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
                    messages.append(assistant_msg)

                    for tc in tool_calls or []:
                        fn = tc.get("function", {})
                        t_name = fn.get("name")
                        try:
                            t_args = json.loads(fn.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            t_args = {}

                        try:
                            if tool_executor:
                                res = tool_executor(t_name, t_args)
                            else:
                                res = {"error": f"No tool executor provided for {t_name}"}
                            if not isinstance(res, dict):
                                res = {"result": res}
                        except Exception as e:
                            res = {"error": str(e)}

                        tool_results_list.append({"name": t_name, "args": t_args, "result": res})
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": t_name,
                            "content": json.dumps(res),
                        })
                    continue
                else:
                    break
        else:
            raise LLMProviderError("Turn limit exceeded. Agent got stuck in a function calling loop.")

        def _parse_and_validate(resp_text: str) -> dict:
            raw = resp_text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise LLMInvalidResponseError("Parsed JSON is not a dictionary")
                if required_keys and not required_keys.issubset(data.keys()):
                    missing = required_keys - data.keys()
                    raise LLMInvalidResponseError(f"LLM response missing keys: {missing}")
                data["text"] = resp_text.strip()
                data["tool_results"] = tool_results_list
                return data
            except json.JSONDecodeError as e:
                raise LLMInvalidResponseError(f"Failed to parse JSON response: {e}")

        try:
            data = _parse_and_validate(final_text)
        except LLMInvalidResponseError as e:
            logger.warning(f"Invalid JSON or missing keys encountered: {e}. Nudging model once in same chat.")
            nudge_msg = (
                "Your previous response was invalid or missing required keys. "
                "Please return ONLY valid JSON matching the exact schema requested, with no markdown fences."
            )
            if self.provider_name == "anthropic":
                messages.append({"role": "user", "content": nudge_msg})
                payload["messages"] = messages
                resp = self._make_request(payload)
                content = resp.get("content", [])
                txt_part = next((p for p in content if p.get("type") == "text"), None)
                if txt_part:
                    final_text = txt_part.get("text", "")
            else:
                messages.append({"role": "user", "content": nudge_msg})
                payload["messages"] = messages
                if "tools" in payload:
                    del payload["tools"]
                resp = self._make_request(payload)
                choice = resp.get("choices", [{}])[0]
                final_text = choice.get("message", {}).get("content", "")

            try:
                data = _parse_and_validate(final_text)
            except LLMInvalidResponseError as e2:
                logger.error(f"LLMInvalidResponseError: Second attempt failed after nudge: {e2}")
                raise LLMInvalidResponseError(f"Failed to produce valid JSON after nudge: {e2}") from e2

        return data
