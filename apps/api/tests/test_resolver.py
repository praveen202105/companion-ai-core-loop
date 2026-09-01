from datetime import UTC, datetime

from companion.domain import (
    MemoryAction,
    MemoryCandidate,
    MemoryStatus,
    MemoryType,
)
from companion.memory.resolver import (
    ContradictionDecision,
    LLMContradictionJudge,
    MemoryResolver,
)
from companion.providers.fake import FakeLLMProvider
from companion.storage import SqlAlchemyMemoryStore
from companion.storage.repository import canonical_key


def fact(
    value: str,
    *,
    memory_type: MemoryType = MemoryType.STATE,
    predicate: str = "relationship status",
    valid_from: datetime | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        memory_type=memory_type,
        subject="user",
        predicate=predicate,
        value=value,
        normalized_text=f"The user's {predicate} is {value}.",
        confidence=0.96,
        importance=0.8,
        valid_from=valid_from,
    )


async def test_changed_current_state_supersedes_old_memory(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    resolver = MemoryResolver(store)

    first = await resolver.resolve(session_id=session_id, candidate=fact("dating"))
    second = await resolver.resolve(session_id=session_id, candidate=fact("single"))

    assert first.action == MemoryAction.ADD
    assert second.action == MemoryAction.SUPERSEDE
    memories = store.list_memories(session_id)
    assert [item.status for item in memories] == [
        MemoryStatus.SUPERSEDED,
        MemoryStatus.ACTIVE,
    ]
    active = store.active_memory(session_id, canonical_key(fact("single")))
    assert active is not None and second.memory is not None
    assert active.id == second.memory.id
    assert active.value == "single"


async def test_same_value_refreshes_in_place(store: SqlAlchemyMemoryStore) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    resolver = MemoryResolver(store)

    original = await resolver.resolve(session_id=session_id, candidate=fact("Pune"))
    refreshed = await resolver.resolve(session_id=session_id, candidate=fact("pune"))

    assert refreshed.action == MemoryAction.UPDATE
    assert refreshed.reason_code == "same_value_refresh"
    assert refreshed.memory is not None
    assert original.memory is not None
    assert refreshed.memory.id == original.memory.id


async def test_preference_correction_updates_with_audit_event(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    resolver = MemoryResolver(store)
    tea = fact(
        "tea",
        memory_type=MemoryType.PREFERENCE,
        predicate="favorite drink",
    )
    coffee = fact(
        "coffee",
        memory_type=MemoryType.PREFERENCE,
        predicate="favorite drink",
    )

    first = await resolver.resolve(session_id=session_id, candidate=tea)
    corrected = await resolver.resolve(session_id=session_id, candidate=coffee)

    assert corrected.action == MemoryAction.UPDATE
    assert first.memory is not None and corrected.memory is not None
    assert first.memory.id == corrected.memory.id
    history = store.memory_history(session_id, canonical_key(coffee))
    assert history[-1].previous_snapshot is not None
    assert history[-1].previous_snapshot["value"] == "tea"


async def test_distinct_historical_events_coexist(store: SqlAlchemyMemoryStore) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    resolver = MemoryResolver(store)
    first_trip = fact(
        "visited Jaipur",
        memory_type=MemoryType.EVENT,
        predicate="travel",
        valid_from=datetime(2026, 1, 4, tzinfo=UTC),
    )
    second_trip = fact(
        "visited Kochi",
        memory_type=MemoryType.EVENT,
        predicate="travel",
        valid_from=datetime(2026, 7, 8, tzinfo=UTC),
    )

    await resolver.resolve(session_id=session_id, candidate=first_trip)
    await resolver.resolve(session_id=session_id, candidate=second_trip)

    memories = store.list_memories(session_id, status=MemoryStatus.ACTIVE)
    assert len(memories) == 2
    assert canonical_key(first_trip) != canonical_key(second_trip)


async def test_ambiguous_correction_can_use_structured_contradiction_decision(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider()
    provider.register_structured(
        ContradictionDecision,
        ContradictionDecision(
            action=MemoryAction.IGNORE,
            reason_code="candidate_is_quoted_not_asserted",
        ),
    )
    resolver = MemoryResolver(
        store,
        contradiction_judge=LLMContradictionJudge(provider),
    )
    session_id = store.create_session(persona_version="1.0.0")
    original = fact(
        "tea",
        memory_type=MemoryType.PREFERENCE,
        predicate="favorite drink",
    )
    quoted = fact(
        "coffee",
        memory_type=MemoryType.PREFERENCE,
        predicate="favorite drink",
    )

    await resolver.resolve(session_id=session_id, candidate=original)
    resolution = await resolver.resolve(session_id=session_id, candidate=quoted)

    assert resolution.action == MemoryAction.IGNORE
    active = store.active_memory(session_id, canonical_key(original))
    assert active is not None and active.value == "tea"
