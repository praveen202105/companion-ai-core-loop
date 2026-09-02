from companion.chat import ChatEngine
from companion.domain import (
    MemoryAction,
    MemoryCandidate,
    MemoryOwner,
    MemoryType,
    MessageRole,
)
from companion.embeddings import HashEmbeddingProvider
from companion.memory import (
    CandidateExtractor,
    MemoryExtraction,
    MemoryExtractor,
    MemoryResolver,
    Retriever,
)
from companion.persona.checker import PersonaConsistencyChecker
from companion.persona.loader import load_persona
from companion.providers.fake import FakeLLMProvider
from companion.storage import SqlAlchemyMemoryStore


def candidate(value: str = "Pune") -> MemoryCandidate:
    return MemoryCandidate(
        owner=MemoryOwner.USER,
        memory_type=MemoryType.STATE,
        subject="user",
        predicate="current location",
        value=value,
        normalized_text=f"The user currently lives in {value}.",
        confidence=0.98,
        importance=0.85,
    )


def engine(
    store: SqlAlchemyMemoryStore,
    provider: FakeLLMProvider,
    extractor: CandidateExtractor | None = None,
) -> ChatEngine:
    embeddings = HashEmbeddingProvider()
    return ChatEngine(
        store=store,
        provider=provider,
        extractor=extractor or MemoryExtractor(provider),
        resolver=MemoryResolver(store),
        retriever=Retriever(store, embeddings),
        embedding_provider=embeddings,
        persona=load_persona(),
    )


def guarded_engine(
    store: SqlAlchemyMemoryStore,
    provider: FakeLLMProvider,
) -> ChatEngine:
    embeddings = HashEmbeddingProvider()
    persona = load_persona()
    return ChatEngine(
        store=store,
        provider=provider,
        extractor=MemoryExtractor(provider),
        resolver=MemoryResolver(store),
        retriever=Retriever(store, embeddings),
        embedding_provider=embeddings,
        persona=persona,
        persona_checker=PersonaConsistencyChecker(
            provider=provider,
            persona=persona,
            store=store,
        ),
    )


async def test_turn_persists_extracts_retrieves_and_responds(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider("Pune sounds familiar.")
    provider.register_structured(
        MemoryExtraction,
        MemoryExtraction(candidates=[candidate()]),
    )
    chat = engine(store, provider)
    session_id = store.create_session(persona_version="1.0.0")

    result = await chat.turn(
        session_id=session_id,
        message="I live in Pune",
        request_id="request-1",
    )

    assert result.response == "Pune sounds familiar."
    assert result.resolutions[0].action == MemoryAction.ADD
    assert result.retrieval.memories[0].memory.value == "Pune"
    assert [message.role for message in store.list_messages(session_id)] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]


class BrokenExtractor:
    async def extract(self, text: str) -> list[MemoryCandidate]:
        del text
        raise RuntimeError("model unavailable")


async def test_extraction_failure_still_allows_response(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider("Still here.")
    chat = engine(store, provider, extractor=BrokenExtractor())
    session_id = store.create_session(persona_version="1.0.0")

    result = await chat.turn(session_id=session_id, message="Hello")

    assert result.response == "Still here."
    assert store.memory_history(session_id)[0].action == MemoryAction.EXTRACTION_FAILED


async def test_retry_resumes_after_user_message_was_already_persisted(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider("Recovered response")
    chat = engine(store, provider)
    session_id = store.create_session(persona_version="1.0.0")
    store.append_message(
        session_id=session_id,
        role=MessageRole.USER,
        content="Please retry",
        request_id="retry-request-01",
    )

    result = await chat.turn(
        session_id=session_id,
        message="Please retry",
        request_id="retry-request-01",
    )

    assert result.response == "Recovered response"
    assert len(store.list_messages(session_id)) == 2


async def test_small_talk_uses_one_generation_call(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider("That sounds like a pleasantly quiet evening.")
    chat = guarded_engine(store, provider)
    session_id = store.create_session(persona_version="1.0.0")

    await chat.turn(session_id=session_id, message="The evening is quiet today.")

    assert provider.usage_snapshot()["calls"] == 1


async def test_memory_worthy_turn_uses_at_most_two_calls(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = FakeLLMProvider()
    chat = guarded_engine(store, provider)
    session_id = store.create_session(persona_version="1.0.0")

    await chat.turn(session_id=session_id, message="I live in Pune.")

    assert provider.usage_snapshot()["calls"] == 2
