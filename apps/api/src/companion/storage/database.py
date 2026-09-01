from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from companion.storage.models import Base


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self._ensure_sqlite_directory(url)
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(url, echo=echo, connect_args=connect_args)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def _ensure_sqlite_directory(url: str) -> None:
        parsed = make_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in {None, ":memory:"}:
            database_path = parsed.database
            assert database_path is not None
            Path(database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            self._create_sqlite_fts()

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    def _create_sqlite_fts(self) -> None:
        statements = (
            """CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                memory_id UNINDEXED,
                session_id UNINDEXED,
                normalized_text,
                tokenize='unicode61 remove_diacritics 2'
            )""",
            """CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON memories
            WHEN new.status = 'active' BEGIN
                INSERT INTO memory_fts(memory_id, session_id, normalized_text)
                VALUES (new.id, new.session_id, new.normalized_text);
            END""",
            """CREATE TRIGGER IF NOT EXISTS memory_fts_delete AFTER DELETE ON memories BEGIN
                DELETE FROM memory_fts WHERE memory_id = old.id;
            END""",
            """CREATE TRIGGER IF NOT EXISTS memory_fts_update AFTER UPDATE ON memories BEGIN
                DELETE FROM memory_fts WHERE memory_id = old.id;
                INSERT INTO memory_fts(memory_id, session_id, normalized_text)
                SELECT new.id, new.session_id, new.normalized_text
                WHERE new.status = 'active';
            END""",
        )
        with self.engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)
