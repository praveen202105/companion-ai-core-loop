from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from companion.domain import MemoryCandidate
from companion.providers import LLMProvider

EXTRACTION_PROMPT_VERSION = "memory-extraction-v1"
EXTRACTION_SYSTEM_PROMPT = """You extract durable memories from one user message.
Return only facts explicitly stated or unambiguously corrected by the user.

Store:
- stable profile facts and relationships
- preferences and dislikes
- current states such as location, work, health, or relationship state
- concrete plans with dates or meaningful future intent
- meaningful life events

Do not store greetings, filler, generic opinions, assistant guesses, secrets such as
passwords/API keys, or disposable small talk. Use one candidate per fact. Keep subject and
predicate stable across corrections so the same fact gets the same canonical key. Mark
non-memory content with no candidates rather than inventing a fact. Preserve the user's
language in normalized_text when useful, including Hinglish.
"""


class MemoryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[MemoryCandidate] = Field(default_factory=list, max_length=12)


class MemoryExtractor:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def extract(self, text: str) -> list[MemoryCandidate]:
        result = await self.provider.extract_structured(
            system=EXTRACTION_SYSTEM_PROMPT,
            text=text,
            schema=MemoryExtraction,
        )
        return [candidate for candidate in result.candidates if candidate.should_store]
