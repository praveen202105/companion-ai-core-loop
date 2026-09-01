import os
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from companion.config import Settings
from companion.domain import MemoryCandidate, MemoryType
from companion.embeddings import HashEmbeddingProvider
from companion.storage import Database, PostgresMemoryStore
from companion.storage.models import EmbeddingVector


def test_railway_postgres_url_uses_psycopg3_driver() -> None:
    settings = Settings(database_url="postgresql://user:pass@host:5432/companion")

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_embedding_type_is_native_vector_on_postgres() -> None:
    data_type = EmbeddingVector().dialect_impl(postgresql.dialect())

    assert "VECTOR(384)" in data_type.impl.compile(dialect=postgresql.dialect())


def test_postgres_store_rejects_accidental_sqlite_configuration() -> None:
    database = Database("sqlite:///:memory:")
    try:
        try:
            PostgresMemoryStore(database)
        except ValueError as error:
            assert "PostgreSQL" in str(error)
        else:
            raise AssertionError("Postgres adapter accepted SQLite")
    finally:
        database.dispose()


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="PostgreSQL integration URL not set")
def test_postgres_pgvector_store_contract() -> None:
    database = Database(os.environ["TEST_POSTGRES_URL"])
    store = PostgresMemoryStore(database)
    session_id = store.create_session(persona_version="1.0.0")
    unique = uuid4().hex
    candidate = MemoryCandidate(
        memory_type=MemoryType.PREFERENCE,
        subject="user",
        predicate=f"ci snack {unique}",
        value="roasted makhana",
        normalized_text=f"The user likes roasted makhana {unique}.",
        confidence=1,
        importance=0.8,
    )
    embeddings = HashEmbeddingProvider()
    try:
        stored = store.add_memory(
            session_id=session_id,
            candidate=candidate,
            embedding=embeddings.embed_one(candidate.normalized_text),
        )

        assert store.vector_extension_available()
        assert store.search_lexical(
            session_id=session_id,
            query="roasted makhana",
        )[0].id == stored.id
        assert store.search_vector(
            session_id=session_id,
            query_embedding=embeddings.embed_one("makhana snack"),
        )[0].id == stored.id
    finally:
        store.delete_session(session_id)
        database.dispose()
