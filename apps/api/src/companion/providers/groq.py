from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from openai import AsyncOpenAI

from companion.providers.base import SchemaT


class GroqResponsesProvider:
    """Groq provider implemented against its OpenAI-compatible Responses API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "openai/gpt-oss-120b",
        extraction_model: str = "openai/gpt-oss-20b",
        timeout_seconds: float = 45,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if client is None and not api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        self.client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=2,
            timeout=httpx.Timeout(timeout_seconds, connect=10),
        )
        self.model = model
        self.extraction_model = extraction_model
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0

    async def generate(self, *, system: str, messages: list[dict[str, str]]) -> str:
        response = await self.client.responses.create(
            model=self.model,
            instructions=system,
            input=cast(Any, messages),
            store=False,
        )
        self._capture_usage(response)
        if not response.output_text:
            raise RuntimeError("Groq returned no output text")
        return response.output_text

    async def extract_structured(
        self,
        *,
        system: str,
        text: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        response = await self.client.responses.parse(
            model=self.extraction_model,
            instructions=system,
            input=text,
            text_format=schema,
            store=False,
        )
        self._capture_usage(response)
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("Groq returned no structured output")
        return parsed

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        manager = self.client.responses.stream(
            model=self.model,
            instructions=system,
            input=cast(Any, messages),
            store=False,
        )
        async with manager as stream:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield event.delta
            response = await stream.get_final_response()
        self._capture_usage(response)

    def usage_snapshot(self) -> dict[str, Any]:
        return {
            "calls": self._calls,
            "provider": "groq",
            "model": self.model,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
        }

    def _capture_usage(self, response: Any) -> None:
        self._calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._input_tokens += int(getattr(usage, "input_tokens", 0))
            self._output_tokens += int(getattr(usage, "output_tokens", 0))
