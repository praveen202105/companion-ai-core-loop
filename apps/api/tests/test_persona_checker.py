from pydantic import BaseModel

from companion.domain import MemoryOwner, MemoryStatus
from companion.persona import (
    CompanionClaim,
    DraftClaims,
    PersonaConsistencyChecker,
    load_persona,
)
from companion.persona.checker import SAFE_PERSONA_FALLBACK
from companion.providers.base import SchemaT
from companion.providers.fake import FakeLLMProvider
from companion.storage import SqlAlchemyMemoryStore


class SequencedClaimsProvider(FakeLLMProvider):
    def __init__(self, results: list[DraftClaims], repair: str) -> None:
        super().__init__(repair)
        self.results = results

    async def extract_structured(
        self,
        *,
        system: str,
        text: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        del system, text
        result: BaseModel = self.results.pop(0)
        return schema.model_validate(result.model_dump())


def city_claim(value: str) -> CompanionClaim:
    return CompanionClaim(
        predicate="current_city",
        value=value,
        normalized_text=f"Mira lives in {value}.",
    )


async def test_checker_repairs_one_persona_conflict(store: SqlAlchemyMemoryStore) -> None:
    provider = SequencedClaimsProvider(
        [
            DraftClaims(claims=[city_claim("Mumbai")]),
            DraftClaims(claims=[city_claim("Bengaluru")]),
        ],
        repair="I live in Bengaluru.",
    )
    checker = PersonaConsistencyChecker(
        provider=provider,
        persona=load_persona(),
        store=store,
    )
    session_id = store.create_session(persona_version="1.0.0")

    result = await checker.guard(session_id=session_id, draft="I live in Mumbai.")

    assert result.response == "I live in Bengaluru."
    assert result.repaired
    assert not result.fallback_used
    assert result.claims[0].owner == MemoryOwner.COMPANION


async def test_checker_uses_safe_fallback_after_failed_repair(
    store: SqlAlchemyMemoryStore,
) -> None:
    provider = SequencedClaimsProvider(
        [
            DraftClaims(claims=[city_claim("Mumbai")]),
            DraftClaims(claims=[city_claim("Mumbai")]),
        ],
        repair="I still live in Mumbai.",
    )
    checker = PersonaConsistencyChecker(
        provider=provider,
        persona=load_persona(),
        store=store,
    )
    session_id = store.create_session(persona_version="1.0.0")

    result = await checker.guard(session_id=session_id, draft="I live in Mumbai.")

    assert result.response == SAFE_PERSONA_FALLBACK
    assert result.fallback_used
    assert result.claims == []


async def test_chat_persists_consistent_companion_claim(
    store: SqlAlchemyMemoryStore,
) -> None:
    from companion.chat import ChatEngine
    from companion.embeddings import HashEmbeddingProvider
    from companion.memory import MemoryExtractor, MemoryResolver, Retriever

    provider = FakeLLMProvider("I live in Bengaluru.")
    provider.register_structured(DraftClaims, DraftClaims(claims=[city_claim("Bengaluru")]))
    persona = load_persona()
    embeddings = HashEmbeddingProvider()
    checker = PersonaConsistencyChecker(provider=provider, persona=persona, store=store)
    chat = ChatEngine(
        store=store,
        provider=provider,
        extractor=MemoryExtractor(provider),
        resolver=MemoryResolver(store),
        retriever=Retriever(store, embeddings),
        embedding_provider=embeddings,
        persona=persona,
        persona_checker=checker,
    )
    session_id = store.create_session(persona_version="1.0.0")

    await chat.turn(session_id=session_id, message="Where are you based?")

    companion_memories = [
        memory
        for memory in store.list_memories(session_id, status=MemoryStatus.ACTIVE)
        if memory.owner == MemoryOwner.COMPANION
    ]
    assert companion_memories[0].value == "Bengaluru"
