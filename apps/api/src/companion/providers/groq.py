from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

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
        reasoning_effort: Literal["low", "medium", "high"] = "low",
        max_output_tokens: int = 1_200,
        extraction_max_output_tokens: int = 3_000,
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
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.extraction_max_output_tokens = extraction_max_output_tokens
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0

    async def generate(self, *, system: str, messages: list[dict[str, str]]) -> str:
        if not self.model.startswith("openai/gpt-oss-"):
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=cast(
                    Any,
                    [{"role": "system", "content": system}, *messages],
                ),
                max_completion_tokens=self.max_output_tokens,
                temperature=0.7,
            )
            self._capture_usage(completion)
            content = completion.choices[0].message.content
            if not content:
                raise RuntimeError("Groq returned no output text")
            return content
        response_api = await self.client.responses.create(
            model=self.model,
            instructions=system,
            input=cast(Any, messages),
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        self._capture_usage(response_api)
        if not response_api.output_text:
            raise RuntimeError("Groq returned no output text")
        return response_api.output_text

    async def extract_structured(
        self,
        *,
        system: str,
        text: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        if not self.extraction_model.startswith("openai/gpt-oss-"):
            schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            completion = await self.client.chat.completions.create(
                model=self.extraction_model,
                messages=cast(
                    Any,
                    [
                        {
                            "role": "system",
                            "content": (
                                f"{system}\nReturn only a JSON object matching this schema: "
                                f"{schema_json}"
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                ),
                response_format={"type": "json_object"},
                max_completion_tokens=self.extraction_max_output_tokens,
                temperature=0.1,
            )
            self._capture_usage(completion)
            content = completion.choices[0].message.content
            if not content:
                raise RuntimeError("Groq returned no structured output")
            return schema.model_validate_json(content)
        response = await self.client.responses.parse(
            model=self.extraction_model,
            instructions=system,
            input=text,
            text_format=schema,
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=self.extraction_max_output_tokens,
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
        if not self.model.startswith("openai/gpt-oss-"):
            llama_stream = await self.client.chat.completions.create(
                model=self.model,
                messages=cast(
                    Any,
                    [{"role": "system", "content": system}, *messages],
                ),
                max_completion_tokens=self.max_output_tokens,
                temperature=0.7,
                stream=True,
                stream_options={"include_usage": True},
            )
            final_chunk: Any = None
            async for chunk in llama_stream:
                final_chunk = chunk
                content = chunk.choices[0].delta.content if chunk.choices else None
                if content:
                    yield content
            if final_chunk is not None:
                self._capture_usage(final_chunk)
            return
        response_stream = self.client.responses.stream(
            model=self.model,
            instructions=system,
            input=cast(Any, messages),
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        async with response_stream as stream:
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
            self._input_tokens += int(
                getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))
            )
            self._output_tokens += int(
                getattr(
                    usage,
                    "output_tokens",
                    getattr(usage, "completion_tokens", 0),
                )
            )
