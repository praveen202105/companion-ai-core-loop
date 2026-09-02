from types import SimpleNamespace
from typing import Any, cast

from openai import AsyncOpenAI
from pydantic import BaseModel

from companion.providers.groq import GroqResponsesProvider


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


async def test_groq_provider_uses_responses_api_and_pydantic_schema() -> None:
    client = FakeClient()
    provider = GroqResponsesProvider(
        api_key=None,
        model="openai/gpt-oss-120b",
        extraction_model="openai/gpt-oss-20b",
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
    assert client.responses.create_kwargs["model"] == "openai/gpt-oss-120b"
    assert client.responses.create_kwargs["store"] is False
    assert client.responses.parse_kwargs["model"] == "openai/gpt-oss-20b"
    assert client.responses.parse_kwargs["text_format"] is StructuredAnswer
    assert provider.usage_snapshot() == {
        "calls": 2,
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "input_tokens": 18,
        "output_tokens": 6,
    }


def test_groq_provider_requires_an_api_key_without_injected_client() -> None:
    try:
        GroqResponsesProvider(api_key=None)
    except ValueError as error:
        assert "GROQ_API_KEY" in str(error)
    else:
        raise AssertionError("Missing API key should fail during startup")
