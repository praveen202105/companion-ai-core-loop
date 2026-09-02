from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from companion.domain import (
    MemoryCandidate,
    MemoryOwner,
    MemoryStatus,
    MemoryType,
    MessageRole,
    utc_now,
)
from companion.storage import Database, SqlAlchemyMemoryStore
from companion.storage.repository import canonical_key


def candidate(value: str = "single") -> MemoryCandidate:
    return MemoryCandidate(
        owner=MemoryOwner.USER,
        memory_type=MemoryType.STATE,
        subject="user",
        predicate="relationship status",
        value=value,
        normalized_text=f"The user is currently {value}.",
        confidence=0.98,
        importance=0.9,
    )


def test_messages_and_memories_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "persistent.db"
    first_db = Database(f"sqlite:///{path}")
    first_db.create_all()
    first = SqlAlchemyMemoryStore(first_db)
    session_id = first.create_session(persona_version="1.0.0")
    message = first.append_message(
        session_id=session_id,
        role=MessageRole.USER,
        content="I am single now.",
    )
    first.add_memory(
        session_id=session_id,
        candidate=candidate(),
        source_message_id=message.id,
    )
    first_db.dispose()

    second_db = Database(f"sqlite:///{path}")
    second = SqlAlchemyMemoryStore(second_db)

    assert second.list_messages(session_id)[0].content == "I am single now."
    assert second.list_memories(session_id, status=MemoryStatus.ACTIVE)[0].value == "single"
    second_db.dispose()


def test_authenticated_user_gets_one_persistent_session(
    store: SqlAlchemyMemoryStore,
) -> None:
    first_user, first_session = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-1",
        persona_version="1.0.0",
    )
    second_user, second_session = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-1",
        persona_version="1.0.0",
    )
    other_user, other_session = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-2",
        persona_version="1.0.0",
    )

    assert first_user.id == second_user.id
    assert first_session.id == second_session.id
    assert first_session.expires_at is None
    assert first_session.user_id == first_user.id
    assert other_user.id != first_user.id
    assert other_session.id != first_session.id


def test_reset_only_replaces_authenticated_users_session(
    store: SqlAlchemyMemoryStore,
) -> None:
    _, first = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-1",
        persona_version="1.0.0",
    )
    _, other = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-2",
        persona_version="1.0.0",
    )
    store.append_message(session_id=first.id, role=MessageRole.USER, content="private")
    store.append_message(session_id=other.id, role=MessageRole.USER, content="other")

    _, replacement = store.reset_user_session(
        auth_provider="google",
        auth_subject="google-user-1",
        persona_version="1.0.0",
    )

    assert replacement.id != first.id
    assert store.get_session(first.id) is None
    assert store.list_messages(replacement.id) == []
    assert store.list_messages(other.id)[0].content == "other"


def test_cleanup_keeps_authenticated_sessions(store: SqlAlchemyMemoryStore) -> None:
    _, authenticated = store.get_or_create_user_session(
        auth_provider="google",
        auth_subject="google-user-1",
        persona_version="1.0.0",
    )
    anonymous = store.create_session(persona_version="1.0.0", retention_days=1)

    removed = store.cleanup_expired_sessions(now=utc_now() + timedelta(days=2))

    assert removed == 1
    assert store.get_session(anonymous) is None
    assert store.get_session(authenticated.id) is not None


def test_message_limit_returns_latest_messages_in_chronological_order(
    store: SqlAlchemyMemoryStore,
) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    for index in range(12):
        store.append_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=f"message {index}",
        )

    messages = store.list_messages(session_id, limit=8)

    assert [item.content for item in messages] == [
        f"message {index}" for index in range(4, 12)
    ]


def test_only_one_active_canonical_memory_is_allowed(store: SqlAlchemyMemoryStore) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    store.add_memory(session_id=session_id, candidate=candidate())

    with pytest.raises(IntegrityError):
        store.add_memory(session_id=session_id, candidate=candidate("dating"))


def test_supersession_preserves_audit_history(store: SqlAlchemyMemoryStore) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    old = store.add_memory(session_id=session_id, candidate=candidate("dating"))

    current = store.supersede_memory(
        old_memory_id=old.id,
        candidate=candidate("single"),
        source_message_id=None,
    )

    active = store.active_memory(session_id, canonical_key(candidate()))
    all_memories = store.list_memories(session_id)
    history = store.memory_history(session_id, canonical_key(candidate()))

    assert active is not None and active.id == current.id
    assert [memory.status for memory in all_memories] == [
        MemoryStatus.SUPERSEDED,
        MemoryStatus.ACTIVE,
    ]
    assert all_memories[0].superseded_by_id == current.id
    assert history[-1].reason_code == "changed_current_truth"


def test_delete_and_retention_cascade_session_data(store: SqlAlchemyMemoryStore) -> None:
    session_id = store.create_session(persona_version="1.0.0")
    store.append_message(session_id=session_id, role=MessageRole.USER, content="Remember me")
    store.add_memory(session_id=session_id, candidate=candidate())

    assert store.delete_session(session_id)
    assert store.list_messages(session_id) == []
    assert store.list_memories(session_id) == []

    expired_id = store.create_session(persona_version="1.0.0", retention_days=1)
    removed = store.cleanup_expired_sessions(now=utc_now() + timedelta(days=2))

    assert removed == 1
    assert not store.session_exists(expired_id)
