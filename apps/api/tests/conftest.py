from collections.abc import Iterator
from pathlib import Path

import pytest

from companion.storage import Database, SqlAlchemyMemoryStore


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'companion.db'}")
    db.create_all()
    yield db
    db.dispose()


@pytest.fixture
def store(database: Database) -> SqlAlchemyMemoryStore:
    return SqlAlchemyMemoryStore(database)
