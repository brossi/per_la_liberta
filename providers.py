"""Model provider abstraction for multi-witness translation.

Each provider wraps an LLM API client and normalises the interface to:
    provider.translate(text, title, system_prompt, edgren_context) → TranslationResult

Supported providers:
    - AnthropicProvider  (Claude Sonnet / Opus)
    - GeminiProvider     (Gemini Pro / Flash)
    - OpenAIProvider     (GPT-4o, optional — requires `openai` extra)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranslationResult:
    """Normalised output from any translation provider."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    elapsed: float          # wall-clock seconds
    stop_reason: str        # provider-native stop reason string


def _build_user_content(text: str, title: str, edgren_context: str | None) -> str:
    """Assemble the user message shared across all providers."""
    content = f"Translate the following chapter ({title}):\n\n{text}"
    if edgren_context:
        content += (
            "\n\n---\n"
            "Period-appropriate definitions from the Edgren Italian-English "
            "Dictionary (1901). Use these to inform your word choices. Prefer "
            "period meanings over modern ones where they differ:\n\n"
            + edgren_context
        )
    return content


# ── Protocol ─────────────────────────────────────────────────────────


@runtime_checkable
class TranslationProvider(Protocol):
    """Common interface every model provider must satisfy."""

    name: str

    def translate(
        self,
        text: str,
        title: str,
        system_prompt: str,
        edgren_context: str | None = None,
    ) -> TranslationResult: ...


# ── Anthropic ────────────────────────────────────────────────────────


class AnthropicProvider:
    """Claude (Sonnet / Opus) via the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        thinking_budget: int = 4096,
        timeout: float = 300.0,
    ) -> None:
        import anthropic

        self.name = f"claude ({model.split('-')[1]})"
        self._model = model
        self._thinking_budget = thinking_budget
        self._retryable = (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        )
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("No Anthropic API key. Set ANTHROPIC_API_KEY or pass api_key.")
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout)

    def translate(
        self,
        text: str,
        title: str,
        system_prompt: str,
        edgren_context: str | None = None,
    ) -> TranslationResult:
        from utils import retry_api_call

        user_content = _build_user_content(text, title, edgren_context)

        kwargs = {
            "model": self._model,
            "max_tokens": 128_000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "thinking": {
                "type": "enabled",
                "budget_tokens": self._thinking_budget,
            },
        }

        t0 = time.monotonic()

        def _call():
            return self._client.messages.create(**kwargs)

        response = retry_api_call(_call, retryable_exceptions=self._retryable)
        elapsed = time.monotonic() - t0

        translated = next(b.text for b in response.content if b.type == "text")
        return TranslationResult(
            text=translated,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            elapsed=elapsed,
            stop_reason=response.stop_reason,
        )


# ── Gemini ───────────────────────────────────────────────────────────


class GeminiProvider:
    """Gemini Pro / Flash via the Google GenAI SDK."""

    # Map friendly names to model IDs — keep in sync with ocr.py
    MODELS = {
        "gemini-pro": "gemini-2.5-pro",
        "gemini-flash": "gemini-2.5-flash",
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-pro",
    ) -> None:
        from google import genai

        self.name = f"gemini ({model.split('-')[1]})"
        self._model_id = self.MODELS.get(model, model)

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("No Gemini API key. Set GEMINI_API_KEY or pass api_key.")
        self._client = genai.Client(api_key=key)

        # Gemini SDK exception types for retry
        try:
            from google.api_core.exceptions import (
                ResourceExhausted,
                ServiceUnavailable,
                InternalServerError,
                TooManyRequests,
            )
            self._retryable = (ResourceExhausted, ServiceUnavailable,
                               InternalServerError, TooManyRequests)
        except ImportError:
            # Fallback — retry on any RuntimeError from the SDK
            self._retryable = (RuntimeError,)

    def translate(
        self,
        text: str,
        title: str,
        system_prompt: str,
        edgren_context: str | None = None,
    ) -> TranslationResult:
        from google.genai import types
        from utils import retry_api_call

        user_content = _build_user_content(text, title, edgren_context)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=65_536,
        )

        t0 = time.monotonic()

        def _call():
            return self._client.models.generate_content(
                model=self._model_id,
                contents=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_content)],
                ),
                config=config,
            )

        response = retry_api_call(_call, retryable_exceptions=self._retryable)
        elapsed = time.monotonic() - t0

        # Extract token counts from usage metadata (may not be present on all models)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        # Gemini stop reason
        candidate = response.candidates[0] if response.candidates else None
        stop_reason = str(candidate.finish_reason) if candidate else "unknown"

        return TranslationResult(
            text=response.text.strip(),
            model=self._model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            elapsed=elapsed,
            stop_reason=stop_reason,
        )


# ── OpenAI ───────────────────────────────────────────────────────────


class OpenAIProvider:
    """GPT-4o via the OpenAI Chat Completions API.

    Requires the `openai` package (install via: uv sync --extra multi-translate).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
    ) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the openai package. "
                "Install with: uv sync --extra multi-translate"
            )

        self.name = f"gpt ({model})"
        self._model = model
        self._retryable = (
            openai.RateLimitError,
            openai.InternalServerError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        )

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("No OpenAI API key. Set OPENAI_API_KEY or pass api_key.")
        self._client = openai.OpenAI(api_key=key)

    def translate(
        self,
        text: str,
        title: str,
        system_prompt: str,
        edgren_context: str | None = None,
    ) -> TranslationResult:
        from utils import retry_api_call

        user_content = _build_user_content(text, title, edgren_context)

        t0 = time.monotonic()

        def _call():
            return self._client.chat.completions.create(
                model=self._model,
                max_tokens=16_384,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )

        response = retry_api_call(_call, retryable_exceptions=self._retryable)
        elapsed = time.monotonic() - t0

        choice = response.choices[0]
        return TranslationResult(
            text=choice.message.content.strip(),
            model=self._model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            elapsed=elapsed,
            stop_reason=choice.finish_reason,
        )


# ── Factory ──────────────────────────────────────────────────────────

# Canonical names used in --draft-models CLI arg
PROVIDER_ALIASES = {
    "claude": "anthropic",
    "sonnet": "anthropic",
    "gemini": "gemini-pro",
    "gemini-pro": "gemini-pro",
    "gemini-flash": "gemini-flash",
    "gpt": "openai",
    "gpt-4o": "openai",
}


def create_provider(
    name: str,
    *,
    anthropic_api_key: str | None = None,
    gemini_api_key: str | None = None,
    openai_api_key: str | None = None,
    thinking_budget: int = 4096,
) -> TranslationProvider:
    """Instantiate a translation provider by canonical name."""
    canonical = PROVIDER_ALIASES.get(name, name)

    if canonical == "anthropic":
        return AnthropicProvider(api_key=anthropic_api_key, thinking_budget=thinking_budget)
    elif canonical in ("gemini-pro", "gemini-flash"):
        return GeminiProvider(api_key=gemini_api_key, model=canonical)
    elif canonical == "openai":
        return OpenAIProvider(api_key=openai_api_key)
    else:
        raise ValueError(
            f"Unknown provider: {name!r}. "
            f"Valid names: {', '.join(sorted(PROVIDER_ALIASES))}"
        )
