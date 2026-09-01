from companion.storage.database import Database
from companion.storage.repository import SqlAlchemyMemoryStore


class PostgresMemoryStore(SqlAlchemyMemoryStore):
    """PostgreSQL/pgvector adapter preserving the SQLAlchemy store contract."""

    def __init__(self, database: Database) -> None:
        if database.engine.dialect.name != "postgresql":
            raise ValueError("PostgresMemoryStore requires a PostgreSQL database")
        super().__init__(database)
