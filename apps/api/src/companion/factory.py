from __future__ import annotations

from dataclasses import dataclass

from companion.chat import ChatEngine
from companion.config import Settings
from companion.embeddings import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    MultilingualE5Provider,
)
from companion.memory import (
    CandidateExtractor,
    DeterministicMemoryExtractor,
    LLMContradictionJudge,
    MemoryExtractor,
    MemoryResolver,
    Retriever,
)
from companion.persona.checker import PersonaConsistencyChecker
from companion.persona.loader import load_persona
from companion.providers import FakeLLMProvider, LLMProvider, XAIResponsesProvider
from companion.request_control import LocalRequestGuard, RedisRequestGuard, RequestGuard
from companion.storage import Database, PostgresMemoryStore, SqlAlchemyMemoryStore


@dataclass
class AppServices:
    database: Database
    store: SqlAlchemyMemoryStore
    chat: ChatEngine
    request_guard: RequestGuard


def build_services(settings: Settings) -> AppServices:
    database = Database(settings.database_url)
    if settings.app_env not in {"staging", "production"}:
        database.create_all()
    store = (
        PostgresMemoryStore(database)
        if database.engine.dialect.name == "postgresql"
        else SqlAlchemyMemoryStore(database)
    )
    persona = load_persona()

    provider: LLMProvider
    extractor: CandidateExtractor
    if settings.llm_provider == "xai":
        provider = XAIResponsesProvider(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            model=settings.xai_chat_model,
            extraction_model=settings.xai_extraction_model,
        )
        extractor = MemoryExtractor(provider)
        judge = LLMContradictionJudge(provider)
    elif settings.llm_provider == "fake":
        provider = FakeLLMProvider()
        extractor = DeterministicMemoryExtractor()
        judge = None
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    embedding_provider: EmbeddingProvider
    if settings.embedding_provider == "multilingual-e5":
        embedding_provider = MultilingualE5Provider()
    elif settings.embedding_provider == "hash":
        embedding_provider = HashEmbeddingProvider()
    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")

    resolver = MemoryResolver(store, contradiction_judge=judge)
    retriever = Retriever(store, embedding_provider)
    persona_checker = PersonaConsistencyChecker(
        provider=provider,
        persona=persona,
        store=store,
    )
    chat = ChatEngine(
        store=store,
        provider=provider,
        extractor=extractor,
        resolver=resolver,
        retriever=retriever,
        embedding_provider=embedding_provider,
        persona=persona,
        persona_checker=persona_checker,
    )
    request_guard: RequestGuard
    if settings.redis_url:
        request_guard = RedisRequestGuard(
            url=settings.redis_url,
            per_minute=settings.chat_rate_limit_per_minute,
            per_day=settings.chat_rate_limit_per_day,
        )
    else:
        request_guard = LocalRequestGuard(
            per_minute=settings.chat_rate_limit_per_minute,
            per_day=settings.chat_rate_limit_per_day,
        )
    return AppServices(
        database=database,
        store=store,
        chat=chat,
        request_guard=request_guard,
    )
