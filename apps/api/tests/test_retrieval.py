from datetime import UTC, datetime, timedelta

from companion.domain import MemoryCandidate, MemoryStatus, MemoryType
from companion.embeddings import HashEmbeddingProvider
from companion.memory import MemoryResolver, Retriever
from companion.storage import SqlAlchemyMemoryStore


def memory(
    value: str,
    *,
    predicate: str,
    memory_type: MemoryType = MemoryType.PREFERENCE,
    valid_from: datetime | None = None,
    importance: float = 0.7,
) -> MemoryCandidate:
    return MemoryCandidate(
        memory_type=memory_type,
        subject="user",
        predicate=predicate,
        value=value,
        normalized_text=f"The user {predicate} {value}.",
        confidence=0.95,
        importance=importance,
        valid_from=valid_from,
    )


async def add_embedded(
    store: SqlAlchemyMemoryStore,
    session_id: object,
    candidate: MemoryCandidate,
    embeddings: HashEmbeddingProvider,
) -> None:
    from uuid import UUID

    await MemoryResolver(store).resolve(
        session_id=UUID(str(session_id)),
        candidate=candidate,
        embedding=embeddings.embed_one(candidate.normalized_text),
    )


async def test_hybrid_retrieval_finds_hinglish_preference_and_limits_context(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    embeddings = HashEmbeddingProvider()
    await add_embedded(
        store,
        session_id,
        memory("masala chai", predicate="likes to drink"),
        embeddings,
    )
    for index in range(8):
        await add_embedded(
            store,
            session_id,
            memory(f"topic {index}", predicate=f"mentioned distractor {index}"),
            embeddings,
        )

    result = Retriever(store, embeddings).retrieve(
        "Mujhe kaunsi chai pasand hai?",
        session_id,
    )

    assert len(result.memories) <= 6
    assert result.memories[0].memory.value == "masala chai"
    assert result.trace.selected[0]["factors"]["lexical_rank"] == 1


async def test_superseded_memory_never_leaks_into_retrieval(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    embeddings = HashEmbeddingProvider()
    resolver = MemoryResolver(store)
    pune = memory("Pune", predicate="current location", memory_type=MemoryType.STATE)
    delhi = memory("Delhi", predicate="current location", memory_type=MemoryType.STATE)
    await resolver.resolve(
        session_id=session_id,
        candidate=pune,
        embedding=embeddings.embed_one(pune.normalized_text),
    )
    await resolver.resolve(
        session_id=session_id,
        candidate=delhi,
        embedding=embeddings.embed_one(delhi.normalized_text),
    )

    result = Retriever(store, embeddings).retrieve("Where do I live?", session_id)

    assert {item.memory.value for item in result.memories} == {"Delhi"}
    assert store.list_memories(session_id, status=MemoryStatus.SUPERSEDED)[0].value == "Pune"


async def test_current_state_decays_faster_than_profile_fact(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    embeddings = HashEmbeddingProvider()
    old = datetime.now(UTC) - timedelta(days=60)
    profile = memory(
        "Praveen",
        predicate="name",
        memory_type=MemoryType.PROFILE,
        valid_from=old,
    )
    state = memory(
        "busy",
        predicate="current state",
        memory_type=MemoryType.STATE,
        valid_from=old,
    )
    await add_embedded(store, session_id, profile, embeddings)
    await add_embedded(store, session_id, state, embeddings)

    result = Retriever(store, embeddings).retrieve("user information", session_id)
    by_value = {item.memory.value: item for item in result.memories}

    assert by_value["Praveen"].factors["freshness"] > by_value["busy"].factors["freshness"]
