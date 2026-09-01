from pydantic import BaseModel

from companion.providers.fake import FakeLLMProvider


class EmptyResult(BaseModel):
    pass


async def test_fake_provider_is_deterministic() -> None:
    provider = FakeLLMProvider("A steady response")

    result = await provider.generate(system="persona", messages=[])
    structured = await provider.extract_structured(
        system="extract",
        text="hello",
        schema=EmptyResult,
    )

    assert result == "A steady response"
    assert structured == EmptyResult()
    assert provider.usage_snapshot()["calls"] == 2
