from sqlalchemy.dialects import postgresql

from companion.config import Settings
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
