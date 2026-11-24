import asyncio
import logging
import uuid
from typing import Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Raised when the upstream LLM provider fails after all retries."""


class LLMClient(Protocol):
    """Minimal interface for LLM providers to allow deterministic fakes in tests."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a text completion given system and user prompts."""
        ...


class OpenAILLMClient:
    """OpenAI SDK wrapper with request ID logging and exponential backoff."""

    def __init__(
        self,
        settings: Settings | None = None,
        base_delay: float = 1.0,
    ) -> None:
        self._settings = settings or get_settings()
        api_key = self._settings.openai_api_key.get_secret_value()
        if not api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._settings.openai_base_url,
            timeout=self._settings.llm_timeout,
            max_retries=0,
        )
        self._base_delay = base_delay

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI Chat Completions in JSON mode with retry/backoff."""
        request_id = str(uuid.uuid4())
        max_retries = self._settings.llm_max_retries

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "LLM request started | request_id=%s model=%s attempt=%d",
                    request_id,
                    self._settings.model_name,
                    attempt + 1,
                )
                response = await self._client.chat.completions.create(
                    model=self._settings.model_name,
                    temperature=self._settings.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content or ""
                logger.info(
                    "LLM request succeeded | request_id=%s attempt=%d",
                    request_id,
                    attempt + 1,
                )
                return content

            except (APITimeoutError, RateLimitError, APIConnectionError) as exc:
                if attempt >= max_retries:
                    logger.error(
                        "LLM request exhausted retries | request_id=%s error=%s",
                        request_id,
                        type(exc).__name__,
                    )
                    raise LLMServiceError(
                        f"LLM provider unavailable after {max_retries} retries."
                    ) from exc

                delay = self._base_delay * (2**attempt)
                logger.warning(
                    "Transient LLM error | request_id=%s error=%s delay=%.1fs",
                    request_id,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)

            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt < max_retries:
                    delay = self._base_delay * (2**attempt)
                    logger.warning(
                        "LLM server error %d | request_id=%s delay=%.1fs",
                        exc.status_code,
                        request_id,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "LLM API status error | request_id=%s status=%d",
                    request_id,
                    exc.status_code,
                )
                raise LLMServiceError(
                    f"LLM provider returned status {exc.status_code}."
                ) from exc

        raise LLMServiceError("Unexpected LLM retry loop termination.")
