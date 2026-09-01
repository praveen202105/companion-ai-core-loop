from __future__ import annotations

import re
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from companion.domain import (
    MemoryAction,
    MemoryCandidate,
    MemoryType,
    StoredMemory,
)
from companion.providers import LLMProvider
from companion.storage import SqlAlchemyMemoryStore
from companion.storage.repository import canonical_key

CONTRADICTION_PROMPT_VERSION = "contradiction-v1"
CONTRADICTION_SYSTEM_PROMPT = """Compare an existing memory with a new candidate about the
same subject and predicate. Decide whether the candidate is a correction to update in place,
a changed current truth that must supersede the old record, or unsupported/noisy content to
ignore. Current location, relationship, work, health state, and dated plans normally supersede.
Preference/profile wording corrections normally update. Never reveal hidden reasoning; return
only the structured decision and a short machine-readable reason_code.
"""


class ContradictionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MemoryAction
    reason_code: str


class ResolutionResult(BaseModel):
    action: MemoryAction
    reason_code: str
    memory: StoredMemory | None = None


class ContradictionJudge(Protocol):
    async def decide(
        self, *, existing: StoredMemory, candidate: MemoryCandidate
    ) -> ContradictionDecision: ...


class LLMContradictionJudge:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def decide(
        self, *, existing: StoredMemory, candidate: MemoryCandidate
    ) -> ContradictionDecision:
        payload = (
            f"EXISTING: {existing.model_dump_json()}\n"
            f"CANDIDATE: {candidate.model_dump_json()}"
        )
        decision = await self.provider.extract_structured(
            system=CONTRADICTION_SYSTEM_PROMPT,
            text=payload,
            schema=ContradictionDecision,
        )
        allowed = {MemoryAction.UPDATE, MemoryAction.SUPERSEDE, MemoryAction.IGNORE}
        if decision.action not in allowed:
            raise ValueError(f"Unsupported contradiction action: {decision.action}")
        return decision


class MemoryResolver:
    def __init__(
        self,
        store: SqlAlchemyMemoryStore,
        *,
        contradiction_judge: ContradictionJudge | None = None,
    ) -> None:
        self.store = store
        self.contradiction_judge = contradiction_judge

    async def resolve(
        self,
        *,
        session_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None = None,
        embedding: list[float] | None = None,
    ) -> ResolutionResult:
        key = canonical_key(candidate)
        if not candidate.should_store:
            return self._ignore(
                session_id=session_id,
                candidate=candidate,
                source_message_id=source_message_id,
                key=key,
                reason_code="not_memory_worthy",
            )

        existing = self.store.active_memory(session_id, key)
        if existing is None:
            memory = self.store.add_memory(
                session_id=session_id,
                candidate=candidate,
                source_message_id=source_message_id,
                embedding=embedding,
            )
            return ResolutionResult(
                action=MemoryAction.ADD,
                reason_code="new_canonical_fact",
                memory=memory,
            )

        if self._normalized_value(existing.value) == self._normalized_value(candidate.value):
            memory = self.store.update_memory(
                memory_id=existing.id,
                candidate=candidate,
                source_message_id=source_message_id,
                reason_code="same_value_refresh",
                embedding=embedding or existing.embedding,
            )
            return ResolutionResult(
                action=MemoryAction.UPDATE,
                reason_code="same_value_refresh",
                memory=memory,
            )

        decision = await self._changed_value_decision(existing, candidate)
        if decision.action == MemoryAction.IGNORE:
            return self._ignore(
                session_id=session_id,
                candidate=candidate,
                source_message_id=source_message_id,
                key=key,
                reason_code=decision.reason_code,
                existing=existing,
            )
        if decision.action == MemoryAction.SUPERSEDE:
            memory = self.store.supersede_memory(
                old_memory_id=existing.id,
                candidate=candidate,
                source_message_id=source_message_id,
                embedding=embedding,
                reason_code=decision.reason_code,
            )
        else:
            memory = self.store.update_memory(
                memory_id=existing.id,
                candidate=candidate,
                source_message_id=source_message_id,
                reason_code=decision.reason_code,
                embedding=embedding,
            )
        return ResolutionResult(
            action=decision.action,
            reason_code=decision.reason_code,
            memory=memory,
        )

    async def _changed_value_decision(
        self,
        existing: StoredMemory,
        candidate: MemoryCandidate,
    ) -> ContradictionDecision:
        if candidate.memory_type in {MemoryType.STATE, MemoryType.PLAN}:
            return ContradictionDecision(
                action=MemoryAction.SUPERSEDE,
                reason_code="changed_current_truth",
            )
        if self._is_current_truth_predicate(candidate.predicate):
            return ContradictionDecision(
                action=MemoryAction.SUPERSEDE,
                reason_code="changed_current_truth",
            )
        if self.contradiction_judge is not None:
            return await self.contradiction_judge.decide(
                existing=existing,
                candidate=candidate,
            )
        return ContradictionDecision(
            action=MemoryAction.UPDATE,
            reason_code="corrected_stable_fact",
        )

    def _ignore(
        self,
        *,
        session_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None,
        key: str,
        reason_code: str,
        existing: StoredMemory | None = None,
    ) -> ResolutionResult:
        self.store.record_event(
            session_id=session_id,
            action=MemoryAction.IGNORE,
            reason_code=reason_code,
            memory_id=existing.id if existing else None,
            source_message_id=source_message_id,
            key=key,
            previous=existing.model_dump(mode="json") if existing else None,
            candidate=candidate.model_dump(mode="json"),
        )
        return ResolutionResult(action=MemoryAction.IGNORE, reason_code=reason_code)

    @staticmethod
    def _normalized_value(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    @staticmethod
    def _is_current_truth_predicate(predicate: str) -> bool:
        normalized = predicate.casefold()
        markers = (
            "current",
            "relationship",
            "location",
            "lives",
            "employer",
            "job",
            "health",
        )
        return any(marker in normalized for marker in markers)
