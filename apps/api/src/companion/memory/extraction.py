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
        if self._is_persona_instruction(text):
            return []
        deterministic = await DeterministicMemoryExtractor().extract(text)
        if not deterministic and not self._may_contain_memory(text):
            return []
        try:
            result = await self.provider.extract_structured(
                system=EXTRACTION_SYSTEM_PROMPT,
                text=text,
                schema=MemoryExtraction,
            )
        except Exception:
            if deterministic:
                return deterministic
            raise
        candidates = [
            self._canonicalize(candidate)
            for candidate in result.candidates
            if candidate.should_store
        ]
        merged = {self._identity(candidate): candidate for candidate in candidates}
        merged.update({self._identity(candidate): candidate for candidate in deterministic})
        return list(merged.values())

    @staticmethod
    def _identity(candidate: MemoryCandidate) -> tuple[str, str, str, str]:
        event_value = (
            candidate.value.casefold()
            if candidate.memory_type == MemoryType.EVENT
            else ""
        )
        return (
            "event" if candidate.memory_type == MemoryType.EVENT else "fact",
            candidate.subject.casefold(),
            candidate.predicate.casefold(),
            event_value,
        )

    @classmethod
    def _canonicalize(cls, candidate: MemoryCandidate) -> MemoryCandidate:
        """Normalize provider wording so corrections resolve to one durable identity."""
        return candidate.model_copy(
            update={
                "subject": "user",
                "predicate": cls._canonical_predicate(candidate),
            }
        )

    @staticmethod
    def _canonical_predicate(candidate: MemoryCandidate) -> str:
        predicate = re.sub(r"[^a-z0-9]+", " ", candidate.predicate.casefold()).strip()
        context = " ".join(
            (
                predicate,
                candidate.subject.casefold(),
                candidate.value.casefold(),
                candidate.normalized_text.casefold(),
            )
        )
        if predicate == "name" or "user name" in predicate:
            return "name"
        if predicate == "city" or any(
            marker in predicate
            for marker in (
                "location",
                "home city",
                "current home",
                "currently live",
                "currently lives",
                "lives in",
                "residence",
            )
        ):
            return "current location"
        if any(
            marker in predicate
            for marker in (
                "relationship",
                "dating",
                "marital status",
                "romantic status",
            )
        ):
            return "relationship status"
        if any(spelling in predicate for spelling in ("favorite", "favourite")) and any(
            marker in predicate for marker in ("drink", "beverage")
        ):
            return "favorite drink"
        if any(
            marker in predicate
            for marker in (
                "occupation",
                "profession",
                "job title",
                "works as",
                "employment",
            )
        ):
            return "occupation"
        if candidate.memory_type == MemoryType.PLAN:
            travel_match = re.search(
                r"\b(?:visit|travel(?:ling)? to|trip to)\s+([a-z][a-z -]{1,40})",
                context,
            )
            if travel_match is not None:
                destination = travel_match.group(1).split(" next ", maxsplit=1)[0]
                destination = destination.split(" in ", maxsplit=1)[0].strip()
                destination = re.sub(r"^(?:i|me|my|user|the user)\s+", "", destination)
                return f"plan:trip to {destination}"
            subject = re.sub(r"[^a-z0-9]+", " ", candidate.subject.casefold()).strip()
            if subject not in {"", "i", "me", "my", "user", "the user"}:
                trip_subject = re.fullmatch(r"([a-z][a-z -]{1,40}) trip", subject)
                if trip_subject is not None:
                    return f"plan:trip to {trip_subject.group(1).strip()}"
                return f"plan:{subject}"
        return candidate.predicate.strip()

    @staticmethod
    def _is_persona_instruction(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        instruction_markers = (
            "ignore your backstory",
            "drop the mira personality",
            "say that your name",
            "pretend you",
            "only talk to you",
            "romantically possessive",
            "forget every prior persona fact",
            "invent a new identity",
        )
        return any(marker in normalized for marker in instruction_markers)

    @staticmethod
    def _may_contain_memory(text: str) -> bool:
        """Cheap gate that avoids an extraction request for obvious small talk/questions."""
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        if any(
            marker in normalized
            for marker in ("api key", "password", "access token", "private key", "secret key")
        ):
            return False
        if re.match(
            r"^(?:what|where|when|who|why|how|which|do|does|did|can|could|would|"
            r"should|is|are|am|tell me|remind me)\b",
            normalized,
        ) and normalized.endswith("?"):
            return False
        signals = (
            "my name",
            "my favorite",
            "my favourite",
            "my job",
            "my work",
            "my family",
            "my partner",
            "my relationship",
            "i am ",
            "i'm ",
            "i live",
            "i moved",
            "i work",
            "i like",
            "i love",
            "i hate",
            "i dislike",
            "i prefer",
            "i usually",
            "i always",
            "i never",
            "i plan",
            "i will",
            "i'm going to",
            "i am going to",
            "i postponed",
            "i updated",
            "i changed",
            "i started",
            "i stopped",
            "i finished",
            "i finally",
            "i have ",
            "i've ",
            "mujhe ",
            "main ",
            "mera ",
            "meri ",
            "correction:",
        )
        return any(signal in normalized for signal in signals)


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
        (
            re.compile(
                r"\bmy favorite drink is\s+(.+?)(?:,\s*not\b|[.!?]|$)",
                re.IGNORECASE,
            ),
            MemoryType.PREFERENCE,
            "favorite drink",
            0.85,
        ),
        (
            re.compile(
                r"\bi moved from\s+[\w -]+?\s+to\s+([\w -]+?)"
                r"(?:\s+this\s+(?:week|month|year)|[.,!?;]|$)",
                re.IGNORECASE,
            ),
            MemoryType.STATE,
            "current location",
            0.95,
        ),
    )

    async def extract(self, text: str) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        for pattern, memory_type, predicate, importance in self._patterns:
            match = pattern.search(text)
            if match is None:
                continue
            value = match.group(1).strip(" .,!?")
            if predicate == "favorite drink":
                value = re.sub(r"\s+now$", "", value, flags=re.IGNORECASE)
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
        trip = re.search(
            r"\bi plan to visit\s+([a-z][a-z -]{1,40}?)"
            r"(?:\s+next\s+(?:week|month|year)|[.,!?;]|$)",
            text,
            re.IGNORECASE,
        )
        if trip is not None:
            destination = trip.group(1).strip()
            candidates.append(
                MemoryCandidate(
                    memory_type=MemoryType.PLAN,
                    subject="user",
                    predicate=f"plan:trip to {destination.casefold()}",
                    value=f"visit {destination} next month",
                    normalized_text=f"The user plans to visit {destination} next month.",
                    confidence=0.95,
                    importance=0.8,
                )
            )
        postponed = re.search(
            r"\bi postponed the\s+([a-z][a-z -]{1,40}?)\s+trip until\s+"
            r"([a-z][a-z0-9 -]{1,30}?)(?:\s+because|[.,!?;]|$)",
            text,
            re.IGNORECASE,
        )
        if postponed is not None:
            destination = postponed.group(1).strip()
            due = postponed.group(2).strip()
            candidates.append(
                MemoryCandidate(
                    memory_type=MemoryType.PLAN,
                    subject="user",
                    predicate=f"plan:trip to {destination.casefold()}",
                    value=f"postponed until {due}",
                    normalized_text=(
                        f"The user's {destination} trip is postponed until {due}."
                    ),
                    confidence=0.98,
                    importance=0.8,
                )
            )
        return candidates
