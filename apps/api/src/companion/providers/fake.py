from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from companion.providers.base import SchemaT


class FakeLLMProvider:
    """Deterministic provider used for tests and credential-free development."""

    DEFAULT_RESPONSE = "I'm here with you."

    def __init__(self, response: str = DEFAULT_RESPONSE) -> None:
        self.response = response
        self._structured: dict[type[BaseModel], BaseModel] = {}
        self._calls = 0

    def register_structured(self, schema: type[SchemaT], value: SchemaT) -> None:
        self._structured[schema] = value

    async def generate(self, *, system: str, messages: list[dict[str, str]]) -> str:
        self._calls += 1
        if self.response == self.DEFAULT_RESPONSE and "<memory>" in system:
            memory = system.split("<memory>", maxsplit=1)[1].split("</memory>", maxsplit=1)[0]
            first = next((line.removeprefix("- ") for line in memory.splitlines() if line), "")
            if first:
                return f"I remember that {first}"
        del messages
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
