from companion.domain import MemoryCandidate, MemoryOwner, MemoryType
from companion.memory import MemoryExtraction, MemoryExtractor
from companion.providers.fake import FakeLLMProvider


async def test_extractor_returns_only_memory_worthy_candidates() -> None:
    provider = FakeLLMProvider()
    provider.register_structured(
        MemoryExtraction,
        MemoryExtraction(
            candidates=[
                MemoryCandidate(
                    owner=MemoryOwner.USER,
                    memory_type=MemoryType.PREFERENCE,
                    subject="user",
                    predicate="favorite drink",
                    value="masala chai",
                    normalized_text="User ko masala chai pasand hai.",
                    confidence=0.98,
                    importance=0.7,
                ),
                MemoryCandidate(
                    should_store=False,
                    owner=MemoryOwner.USER,
                    memory_type=MemoryType.EVENT,
                    subject="user",
                    predicate="said greeting",
                    value="hello",
                    normalized_text="The user said hello.",
                    confidence=1,
                    importance=0,
                ),
            ]
        ),
    )

    candidates = await MemoryExtractor(provider).extract("Hello, chai bana raha hoon")

    assert len(candidates) == 1
    assert candidates[0].value == "masala chai"


async def test_empty_extraction_is_valid_for_small_talk() -> None:
    provider = FakeLLMProvider()

    assert await MemoryExtractor(provider).extract("Hey!") == []
