from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from companion.api import create_app
from companion.config import Settings
from companion.factory import build_services


@pytest.fixture
async def api_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        internal_api_key="test-internal-key",
        llm_provider="fake",
        embedding_provider="hash",
    )
    application = create_app(settings)
    services = build_services(settings)
    application.state.services = services
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    services.database.dispose()


def auth() -> dict[str, str]:
    return {"X-Internal-API-Key": "test-internal-key"}


async def test_internal_endpoints_require_api_key(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/v1/sessions")

    assert response.status_code == 401


async def test_session_chat_inspection_and_permanent_reset(
    api_client: httpx.AsyncClient,
) -> None:
    created = await api_client.post("/v1/sessions", headers=auth())
    session_id = created.json()["session"]["id"]

    chat = await api_client.post(
        "/v1/chat",
        headers=auth(),
        json={
            "session_id": session_id,
            "request_id": "request-api-001",
            "message": "I live in Pune",
        },
    )

    assert chat.status_code == 200
    assert chat.headers["content-type"].startswith("text/event-stream")
    assert "event: memory.update" in chat.text
    assert "event: retrieval.trace" in chat.text
    assert "event: message.delta" in chat.text
    assert "event: message.completed" in chat.text

    messages = await api_client.get(
        f"/v1/sessions/{session_id}/messages",
        headers=auth(),
    )
    memories = await api_client.get(
        f"/v1/sessions/{session_id}/memories?status=active",
        headers=auth(),
    )
    assert len(messages.json()["messages"]) == 2
    assert memories.json()["memories"][0]["value"] == "Pune"

    deleted = await api_client.delete(f"/v1/sessions/{session_id}", headers=auth())
    missing = await api_client.get(
        f"/v1/sessions/{session_id}/messages",
        headers=auth(),
    )
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_health_checks_do_not_call_model(api_client: httpx.AsyncClient) -> None:
    live = await api_client.get("/health/live")
    ready = await api_client.get("/health/ready")

    assert live.json() == {"status": "ok", "checks": {}}
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"
