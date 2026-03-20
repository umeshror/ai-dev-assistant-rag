"""
app/engines/llm.py
──────────────────────────────────────────────────────────────────────────────
LLM client wrapper for OpenAI Chat Completions.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Thin, async wrapper around the OpenAI Chat Completions API.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=httpx.Timeout(
                timeout=settings.llm_timeout_seconds,
                connect=10.0,
            ),
        )

    async def analyze(
        self, messages: List[ChatCompletionMessageParam]
    ) -> Dict[str, Any]:
        """Send messages to the LLM and return the parsed JSON response."""
        raw_content = await self._call_with_retry(messages)
        return self._parse_json_response(raw_content)

    async def _call_with_retry(
        self, messages: List[ChatCompletionMessageParam]
    ) -> str:
        """Execute the chat completion call, retrying on transient errors."""

        @retry(
            retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
            stop=stop_after_attempt(self._settings.llm_max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=16),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _inner() -> str:
            try:
                response = await self._client.chat.completions.create(
                    model=self._settings.chat_model,
                    messages=messages,
                    temperature=self._settings.llm_temperature,
                    max_tokens=self._settings.llm_max_tokens,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, APIConnectionError):
                raise
            except APIError as exc:
                logger.error("Non-retryable OpenAI API error: status=%s msg=%s", exc.status_code, exc.message)
                raise LLMError(f"LLM API error (status {exc.status_code}): {exc.message}") from exc
            except Exception as exc:
                logger.error("Unexpected error during LLM call: %s", exc)
                raise LLMError(f"Unexpected LLM error: {exc}") from exc

        try:
            return await _inner()
        except (RateLimitError, APIConnectionError) as exc:
            logger.error("LLM call failed after exhaustive retries: %s", exc)
            raise LLMError(f"LLM unavailable after {self._settings.llm_max_retries} retries.") from exc

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        """Parse and validate the raw LLM string response as JSON."""
        if not raw or not raw.strip():
            raise LLMError("LLM returned an empty response.")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM output is not valid JSON: %s", exc)
            raise LLMError("LLM returned malformed JSON.") from exc

        if not isinstance(parsed, dict):
            raise LLMError(f"Expected JSON object from LLM, got {type(parsed).__name__}.")

        return parsed
