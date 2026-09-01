from types import SimpleNamespace
from typing import Any, cast

from openai import AsyncOpenAI
from pydantic import BaseModel

from companion.providers.xai import XAIResponsesProvider


class StructuredAnswer(BaseModel):
    answer: str


class FakeResponses:
    def __init__(self) -> None:
        self.create_kwargs: dict[str, Any] = {}
        self.parse_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.create_kwargs = kwargs
        return SimpleNamespace(
            output_text="A grounded response",
            usage=SimpleNamespace(input_tokens=11, output_tokens=4),
        )

    async def parse(self, **kwargs: Any) -> Any:
        self.parse_kwargs = kwargs
        return SimpleNamespace(
            output_parsed=StructuredAnswer(answer="chai"),
            usage=SimpleNamespace(input_tokens=7, output_tokens=2),
        )


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


async def test_xai_provider_uses_responses_api_and_pydantic_schema() -> None:
    client = FakeClient()
    provider = XAIResponsesProvider(
        api_key=None,
        model="grok-4.3",
        extraction_model="grok-4.3",
        client=cast(AsyncOpenAI, client),
    )

    generated = await provider.generate(
        system="Be Mira",
        messages=[{"role": "user", "content": "Hi"}],
    )
    structured = await provider.extract_structured(
        system="Extract",
        text="I like chai",
        schema=StructuredAnswer,
    )

    assert generated == "A grounded response"
    assert structured == StructuredAnswer(answer="chai")
    assert client.responses.create_kwargs["model"] == "grok-4.3"
    assert client.responses.create_kwargs["store"] is False
    assert client.responses.parse_kwargs["text_format"] is StructuredAnswer
    assert provider.usage_snapshot()["input_tokens"] == 18


def test_xai_provider_requires_an_api_key_without_injected_client() -> None:
    try:
        XAIResponsesProvider(api_key=None)
    except ValueError as error:
        assert "XAI_API_KEY" in str(error)
    else:
        raise AssertionError("Missing API key should fail during startup")
