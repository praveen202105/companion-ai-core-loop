from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from companion.domain import MemoryCandidate, MemoryType
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


class CandidateExtractor(Protocol):
    async def extract(self, text: str) -> list[MemoryCandidate]: ...


class DeterministicMemoryExtractor:
    """Small credential-free extractor for local demos; production uses structured output."""

    _patterns: tuple[tuple[re.Pattern[str], MemoryType, str, float], ...] = (
        (
            re.compile(r"\bmy name is\s+([\w -]{2,80})", re.IGNORECASE),
            MemoryType.PROFILE,
            "name",
            0.9,
        ),
        (
            re.compile(r"\b(?:i live in|i moved to|currently in)\s+([\w -]{2,80})", re.IGNORECASE),
            MemoryType.STATE,
            "current location",
            0.9,
        ),
        (
            re.compile(r"\b(?:i like|i love|mujhe)\s+([\w -]{2,100})", re.IGNORECASE),
            MemoryType.PREFERENCE,
            "likes",
            0.7,
        ),
        (
            re.compile(r"\bi am\s+(single|dating|married|engaged)\b", re.IGNORECASE),
            MemoryType.STATE,
            "relationship status",
            0.9,
        ),
    )

    async def extract(self, text: str) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        for pattern, memory_type, predicate, importance in self._patterns:
            match = pattern.search(text)
            if match is None:
                continue
            value = match.group(1).strip(" .,!?")
            candidates.append(
                MemoryCandidate(
                    memory_type=memory_type,
                    subject="user",
                    predicate=predicate,
                    value=value,
                    normalized_text=f"The user's {predicate} is {value}.",
                    confidence=0.9,
                    importance=importance,
                )
            )
        return candidates
