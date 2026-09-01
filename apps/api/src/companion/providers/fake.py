from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from companion.providers.base import SchemaT


class FakeLLMProvider:
    """Deterministic provider used for tests and credential-free development."""

    def __init__(self, response: str = "I'm here with you.") -> None:
        self.response = response
        self._structured: dict[type[BaseModel], BaseModel] = {}
        self._calls = 0

    def register_structured(self, schema: type[SchemaT], value: SchemaT) -> None:
        self._structured[schema] = value

    async def generate(self, *, system: str, messages: list[dict[str, str]]) -> str:
        del system, messages
        self._calls += 1
        return self.response

    async def extract_structured(
        self,
        *,
        system: str,
        text: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        del system, text
        self._calls += 1
        value = self._structured.get(schema)
        if value is None:
            return schema.model_validate({})
        return schema.model_validate(value.model_dump())

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        response = await self.generate(system=system, messages=messages)
        for token in response.split(" "):
            yield f"{token} "

    def usage_snapshot(self) -> dict[str, Any]:
        return {"calls": self._calls, "provider": "fake"}
