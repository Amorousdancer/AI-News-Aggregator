"""LLM client wrapper with retry, fallback chain, and cost tracking.

Fallback chain: Claude Sonnet 4 → Claude Haiku 4 → GPT-4o-mini → error.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog
from anthropic import APIError, APITimeoutError, AsyncAnthropic, RateLimitError
from anthropic.types import Message as AnthropicMessage
from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI

from src.analyzer.cost_tracker import CostTracker
from src.config import settings

logger = structlog.get_logger(__name__)

# Primary models in priority order (fallback chain)
FALLBACK_CHAIN = [
    # (provider, model_name, requires_api_key)
    ("anthropic", settings.anthropic_model_primary, "anthropic_api_key"),
]


@dataclass
class LLMResponse:
    """Successful LLM response with metadata."""

    content: str
    model_name: str
    model_provider: str
    input_tokens: int
    output_tokens: int
    is_cached_input: bool = False
    duration_ms: float = 0.0


class LLMClient:
    """Async LLM client with multi-provider fallback and cost tracking."""

    def __init__(self, cost_tracker: CostTracker | None = None):
        self.cost_tracker = cost_tracker or CostTracker(
            daily_budget_usd=settings.daily_cost_limit_usd,
        )
        self._anthropic: AsyncAnthropic | None = None
        self._openai: AsyncOpenAI | None = None

    @property
    def anthropic(self) -> AsyncAnthropic:
        if self._anthropic is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            self._anthropic = AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
            )
        return self._anthropic

    @property
    def openai(self) -> AsyncOpenAI:
        if self._openai is None:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            self._openai = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        return self._openai

    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 16384,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Send a prompt through the fallback chain and return the response.

        Tries each model in the fallback chain. On failure, proceeds to the next.
        Raises RuntimeError if all models fail.
        """
        if self.cost_tracker.is_over_budget():
            raise RuntimeError(
                f"Daily cost limit (${self.cost_tracker.daily_budget_usd:.2f}) exceeded"
            )

        last_error = None

        for provider, model, api_key_attr in FALLBACK_CHAIN:
            # Check if this provider's API key is configured
            if not getattr(settings, api_key_attr, None):
                logger.debug("Skipping provider — no API key", provider=provider, model=model)
                continue

            try:
                if provider == "anthropic":
                    result = await self._call_anthropic(
                        model, system_prompt, user_message, temperature, max_tokens, max_retries
                    )
                else:
                    result = await self._call_openai(
                        model, system_prompt, user_message, temperature, max_tokens, max_retries
                    )

                # Record cost
                self.cost_tracker.record_call(
                    model_name=result.model_name,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    is_cached_input=result.is_cached_input,
                )

                return result

            except (APIError, APITimeoutError, RateLimitError, OpenAIAPIError) as exc:
                logger.warning(
                    "LLM call failed, trying fallback",
                    provider=provider,
                    model=model,
                    error=str(exc),
                )
                last_error = exc
                await asyncio.sleep(1)  # Brief pause before fallback
                continue

            except Exception as exc:
                logger.error(
                    "Unexpected LLM error",
                    provider=provider,
                    model=model,
                    error=str(exc),
                )
                last_error = exc
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def generate_report(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a daily report using the best available model (no fallback on quality)."""
        # Reports use only the primary model
        if settings.anthropic_api_key:
            result = await self._call_anthropic(
                settings.anthropic_model_primary,
                system_prompt,
                user_message,
                temperature,
                max_tokens,
                max_retries=2,
            )
        else:
            raise RuntimeError("No LLM API key configured for report generation")

        self.cost_tracker.record_call(
            model_name=result.model_name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            is_cached_input=result.is_cached_input,
        )

        return result

    async def _call_anthropic(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
        max_retries: int,
    ) -> LLMResponse:
        """Call Anthropic Claude API with retries."""
        import time
        start = time.monotonic()

        for attempt in range(max_retries):
            try:
                # System prompt is cached automatically by Anthropic
                message: AnthropicMessage = await self.anthropic.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"} if attempt == 0 else None,
                        }
                    ],
                    messages=[{"role": "user", "content": user_message}],
                )

                duration_ms = (time.monotonic() - start) * 1000
                input_tokens = message.usage.input_tokens
                output_tokens = message.usage.output_tokens

                # Check if cache was hit (Anthropic reports cache hits separately)
                cached_tokens = getattr(message.usage, "cache_read_input_tokens", 0) or 0
                is_cached = cached_tokens > 0

                # Extract text content (handle both Claude and MiMo response formats)
                content = ""
                logger.debug("Response blocks", block_types=[b.type for b in message.content])
                for block in message.content:
                    if block.type == "text":
                        content += block.text
                        logger.debug("Found text block", text_length=len(block.text))
                    elif block.type == "thinking":
                        # MiMo returns thinking blocks - log for debugging
                        thinking_text = getattr(block, "thinking", "")
                        logger.debug("MiMo thinking block", thinking_length=len(thinking_text))
                # If no text block found, check for thinking blocks (MiMo)
                if not content:
                    logger.warning("No text block found in response, checking thinking blocks")
                    for block in message.content:
                        if block.type == "thinking":
                            thinking_text = getattr(block, "thinking", "")
                            # Try to extract JSON from thinking text
                            if "{" in thinking_text and "}" in thinking_text:
                                start = thinking_text.find("{")
                                end = thinking_text.rfind("}") + 1
                                content = thinking_text[start:end]
                                logger.debug(
                                    "Extracted JSON from thinking block",
                                    content_length=len(content),
                                )
                                break

                return LLMResponse(
                    content=content,
                    model_name=model,
                    model_provider="anthropic",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    is_cached_input=is_cached,
                    duration_ms=duration_ms,
                )

            except (APITimeoutError, RateLimitError):
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                    logger.info("Retrying Anthropic call", attempt=attempt + 1, wait=wait)
                    await asyncio.sleep(wait)
                    continue
                raise
            except APIError as exc:
                # Non-retryable errors (400, 401, etc.)
                if exc.status_code and 400 <= exc.status_code < 500 and exc.status_code != 429:
                    raise
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 2
                    await asyncio.sleep(wait)
                    continue
                raise

        raise RuntimeError(f"Anthropic call failed after {max_retries} retries")

    async def _call_openai(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
        max_retries: int,
    ) -> LLMResponse:
        """Call OpenAI API with retries."""
        import time
        start = time.monotonic()

        for attempt in range(max_retries):
            try:
                response = await self.openai.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                duration_ms = (time.monotonic() - start) * 1000
                content = response.choices[0].message.content or ""

                return LLMResponse(
                    content=content,
                    model_name=model,
                    model_provider="openai",
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    is_cached_input=False,  # OpenAI doesn't expose cache info in v1
                    duration_ms=duration_ms,
                )

            except OpenAIAPIError:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 2
                    logger.info("Retrying OpenAI call", attempt=attempt + 1, wait=wait)
                    await asyncio.sleep(wait)
                    continue
                raise

        raise RuntimeError(f"OpenAI call failed after {max_retries} retries")
