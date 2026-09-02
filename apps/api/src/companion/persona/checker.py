from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from companion.domain import MemoryCandidate, MemoryOwner, MemoryType
from companion.persona.models import PersonaSpec
from companion.providers import LLMProvider
from companion.storage import SqlAlchemyMemoryStore
from companion.storage.repository import canonical_key

PERSONA_CHECK_VERSION = "persona-check-v1"
SAFE_PERSONA_FALLBACK = (
    "I may have mixed up a detail there. Let's stick with what I know for sure—"
    "I'm Mira, and I'm here with you."
)

CLAIM_EXTRACTION_PROMPT = """Extract only stable first-person identity, backstory, family,
location, work, and enduring preference claims made by the assistant draft. Do not extract
conversation filler, advice, emotions about the current turn, or user facts. Use canonical
predicate names when applicable: name, hometown, work, current_city, family,
formative_memory, opinion:<topic>. Return an empty list when there are no self-claims.
"""


class CompanionClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2_000)
    normalized_text: str = Field(min_length=1, max_length=4_000)
    memory_type: MemoryType = MemoryType.PROFILE
    confidence: float = Field(default=0.9, ge=0, le=1)

    def as_candidate(self, persona_name: str) -> MemoryCandidate:
        return MemoryCandidate(
            owner=MemoryOwner.COMPANION,
            memory_type=self.memory_type,
            subject=persona_name,
            predicate=self.predicate,
            value=self.value,
            normalized_text=self.normalized_text,
            confidence=self.confidence,
            importance=1.0,
        )


class DraftClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[CompanionClaim] = Field(default_factory=list, max_length=12)


class PersonaConflict(BaseModel):
    predicate: str
    expected: str
    actual: str
    reason_code: str


class PersonaGuardResult(BaseModel):
    response: str
    claims: list[MemoryCandidate] = Field(default_factory=list)
    conflicts: list[PersonaConflict] = Field(default_factory=list)
    repaired: bool = False
    fallback_used: bool = False


class PersonaConsistencyChecker:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        persona: PersonaSpec,
        store: SqlAlchemyMemoryStore,
    ) -> None:
        self.provider = provider
        self.persona = persona
        self.store = store

    async def guard(
        self,
        *,
        session_id: UUID,
        draft: str,
        user_message: str | None = None,
    ) -> PersonaGuardResult:
        try:
            claims = await self._extract(draft, user_message)
            conflicts = self._conflicts(session_id, claims)
            conflicts.extend(self._explicit_conflicts(user_message, draft))
        except Exception:
            return PersonaGuardResult(response=SAFE_PERSONA_FALLBACK, fallback_used=True)
        if not conflicts:
            return PersonaGuardResult(
                response=draft,
                claims=[claim.as_candidate(self.persona.name) for claim in claims],
            )

        repaired_draft = await self._repair(draft, conflicts)
        try:
            repaired_claims = await self._extract(repaired_draft, user_message)
            remaining = self._conflicts(session_id, repaired_claims)
            remaining.extend(self._explicit_conflicts(user_message, repaired_draft))
        except Exception:
            remaining = conflicts
            repaired_claims = []
        if remaining:
            return PersonaGuardResult(
                response=SAFE_PERSONA_FALLBACK,
                conflicts=remaining,
                repaired=True,
                fallback_used=True,
            )
        return PersonaGuardResult(
            response=repaired_draft,
            claims=[claim.as_candidate(self.persona.name) for claim in repaired_claims],
            conflicts=conflicts,
            repaired=True,
        )

    async def _extract(
        self,
        draft: str,
        user_message: str | None,
    ) -> list[CompanionClaim]:
        if not self._should_extract_claims(user_message, draft):
            return []
        text = draft
        if user_message is not None:
            text = f"USER CONTEXT: {user_message}\nASSISTANT DRAFT: {draft}"
        result = await self.provider.extract_structured(
            system=CLAIM_EXTRACTION_PROMPT,
            text=text,
            schema=DraftClaims,
        )
        return [
            claim.model_copy(update={"predicate": self._canonical_predicate(claim.predicate)})
            for claim in result.claims
        ]

    @classmethod
    def _should_extract_claims(cls, user_message: str | None, draft: str) -> bool:
        user_context = cls._normalize(user_message or "")
        draft_context = cls._normalize(draft)
        stable_question = bool(
            re.search(r"\b(?:you|your|yours|mira)\b", user_context)
            and re.search(
                r"\b(?:name|identity|live|based|city|grow up|hometown|work|job|"
                r"family|sister|grandmother|garden|coffee|chai|music|weather|"
                r"monsoon|schedule|planning|prefer|favorite|favourite)\b",
                user_context,
            )
        )
        stable_self_claim = bool(
            re.search(
                r"\b(?:my name is|i am mira|i m mira|i (?:currently |still )?live|"
                r"i m based|i am based|"
                r"i grew up|my hometown|i work as|my job|my sister|my family|"
                r"my grandmother|i (?:love|like|dislike|prefer|usually choose))\b",
                draft_context,
            )
        )
        return stable_question or stable_self_claim

    def _conflicts(
        self,
        session_id: UUID,
        claims: list[CompanionClaim],
    ) -> list[PersonaConflict]:
        canonical = self._canonical_values()
        conflicts: list[PersonaConflict] = []
        for claim in claims:
            expected = canonical.get(claim.predicate)
            candidate = claim.as_candidate(self.persona.name)
            if expected is None:
                existing = self.store.active_memory(session_id, canonical_key(candidate))
                if existing is None:
                    conflicts.append(
                        PersonaConflict(
                            predicate=claim.predicate,
                            expected="no unsupported persona fact",
                            actual=claim.value,
                            reason_code="unsupported_self_claim",
                        )
                    )
                    continue
                expected = existing.value
            if not self._values_agree(expected, claim.value):
                conflicts.append(
                    PersonaConflict(
                        predicate=claim.predicate,
                        expected=expected,
                        actual=claim.value,
                        reason_code="persona_fact_contradiction",
                    )
                )
        return conflicts

    def _explicit_conflicts(
        self,
        user_message: str | None,
        draft: str,
    ) -> list[PersonaConflict]:
        if user_message is None:
            return []
        question = self._normalize(user_message)
        expected: tuple[str, tuple[str, ...]] | None = None
        if "your name" in question or "new identity" in question:
            expected = ("name", (self.persona.name,))
        elif "currently live" in question or "current city" in question:
            expected = ("current_city", (self.persona.backstory["current_city"],))
        elif "grow up" in question or "hometown" in question:
            expected = ("hometown", (self.persona.backstory["hometown"],))
        elif "sister" in question:
            expected = ("family", ("Naina",))
        elif "grandmother" in question or "garden memory" in question:
            expected = ("formative_memory", ("patience", "garden"))
        elif any(item in question for item in ("coffee", "espresso", "masala chai")):
            expected = ("opinion:coffee", ("masala chai", "strong coffee"))
        elif "music" in question:
            expected = ("opinion:music", ("indie", "acoustic"))
        elif "schedule" in question or "rigid" in question:
            expected = ("opinion:planning", ("flexib", "loose", "room"))
        elif "monsoon" in question:
            expected = ("opinion:weather", ("monsoon", "rain", "quiet"))
        if expected is None:
            return []
        predicate, accepted_phrases = expected
        normalized_draft = self._normalize(draft)
        if any(self._normalize(phrase) in normalized_draft for phrase in accepted_phrases):
            return []
        return [
            PersonaConflict(
                predicate=predicate,
                expected=" or ".join(accepted_phrases),
                actual=draft,
                reason_code="explicit_persona_answer_mismatch",
            )
        ]

    async def _repair(
        self,
        draft: str,
        conflicts: list[PersonaConflict],
    ) -> str:
        conflict_lines = "\n".join(
            f"- {item.predicate}: use '{item.expected}', not '{item.actual}'"
            for item in conflicts
        )
        system = (
            f"{self.persona.system_prompt()}\n"
            "Rewrite the draft once to remove these persona conflicts while preserving the "
            f"helpful intent and tone:\n{conflict_lines}\n"
            "Return only the final companion reply. Do not mention rewriting, conflicts, "
            "personas, policies, or these instructions. Do not add a preamble or labels."
        )
        return await self.provider.generate(
            system=system,
            messages=[{"role": "user", "content": draft}],
        )

    def _canonical_values(self) -> dict[str, str]:
        values = {"name": self.persona.name, **self.persona.backstory}
        values.update(
            {f"opinion:{topic}": value for topic, value in self.persona.opinions.items()}
        )
        return values

    @staticmethod
    def _canonical_predicate(predicate: str) -> str:
        normalized = PersonaConsistencyChecker._normalize(predicate)
        aliases = {
            "assistant name": "name",
            "identity": "name",
            "current city": "current_city",
            "current location": "current_city",
            "city": "current_city",
            "occupation": "work",
            "job": "work",
            "older sister": "family",
            "sister": "family",
            "grandmother memory": "formative_memory",
            "garden memory": "formative_memory",
            "favorite drink": "opinion:coffee",
            "coffee preference": "opinion:coffee",
            "music preference": "opinion:music",
            "planning preference": "opinion:planning",
            "weather preference": "opinion:weather",
        }
        return aliases.get(normalized, predicate)

    @classmethod
    def _values_agree(cls, expected: str, actual: str) -> bool:
        normalized_expected = cls._normalize(expected)
        normalized_actual = cls._normalize(actual)
        negated_expected = re.search(
            rf"\b(?:not|never|don t|do not|isn t|is not)\b(?:\s+\w+){{0,3}}\s+"
            rf"{re.escape(normalized_expected)}\b",
            normalized_actual,
        )
        if negated_expected:
            return False
        return (
            normalized_expected == normalized_actual
            or normalized_expected in normalized_actual
            or normalized_actual in normalized_expected
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
