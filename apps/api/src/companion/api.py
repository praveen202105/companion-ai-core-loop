from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

import orjson
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from companion.api_models import (
    ChatRequest,
    HealthResponse,
    MemoriesResponse,
    MessagesResponse,
    SessionResponse,
)
from companion.config import Settings, get_settings
from companion.domain import MemoryStatus
from companion.factory import AppServices, build_services
from companion.persona.loader import load_persona


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if not hasattr(application.state, "services"):
            application.state.services = build_services(configured)
        yield
        services: AppServices = application.state.services
        services.database.dispose()

    application = FastAPI(
        title="Companion AI API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Internal-API-Key"],
    )
    register_routes(application)
    return application


def register_routes(application: FastAPI) -> None:
    @application.post(
        "/v1/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_internal_key)],
    )
    async def create_session(request: Request) -> SessionResponse:
        services = get_services(request)
        settings = get_api_settings(request)
        session_id = services.store.create_session(
            persona_version=load_persona().version,
            retention_days=settings.session_retention_days,
        )
        session = services.store.get_session(session_id)
        assert session is not None
        return SessionResponse(session=session)

    @application.post(
        "/v1/chat",
        dependencies=[Depends(require_internal_key)],
        response_class=StreamingResponse,
    )
    async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
        services = get_services(request)
        if not services.store.session_exists(payload.session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        async def events() -> AsyncIterator[bytes]:
            try:
                result = await services.chat.turn(
                    session_id=payload.session_id,
                    request_id=payload.request_id,
                    message=payload.message,
                )
                for resolution in result.resolutions:
                    yield sse_event("memory.update", resolution.model_dump(mode="json"))
                yield sse_event(
                    "retrieval.trace",
                    result.retrieval.trace.model_dump(mode="json"),
                )
                for delta in chunk_text(result.response):
                    yield sse_event("message.delta", {"delta": delta})
                yield sse_event(
                    "message.completed",
                    result.assistant_message.model_dump(mode="json"),
                )
            except Exception:
                yield sse_event(
                    "error",
                    {
                        "code": "turn_failed",
                        "message": "The turn could not be completed. Please retry.",
                        "retryable": True,
                    },
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get(
        "/v1/sessions/{session_id}/messages",
        response_model=MessagesResponse,
        dependencies=[Depends(require_internal_key)],
    )
    async def messages(session_id: UUID, request: Request) -> MessagesResponse:
        services = require_session(request, session_id)
        return MessagesResponse(messages=services.store.list_messages(session_id))

    @application.get(
        "/v1/sessions/{session_id}/memories",
        response_model=MemoriesResponse,
        dependencies=[Depends(require_internal_key)],
    )
    async def memories(
        session_id: UUID,
        request: Request,
        memory_status: Annotated[
            MemoryStatus,
            Query(alias="status"),
        ] = MemoryStatus.ACTIVE,
    ) -> MemoriesResponse:
        services = require_session(request, session_id)
        return MemoriesResponse(
            status=memory_status,
            memories=services.store.list_memories(session_id, status=memory_status),
            events=services.store.memory_history(session_id),
        )

    @application.delete(
        "/v1/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_internal_key)],
    )
    async def delete_session(session_id: UUID, request: Request) -> Response:
        services = require_session(request, session_id)
        services.store.delete_session(session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/health/live", response_model=HealthResponse)
    async def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/health/ready", response_model=HealthResponse)
    async def ready(request: Request) -> HealthResponse | JSONResponse:
        services = get_services(request)
        checks: dict[str, Any] = {}
        try:
            with services.database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "failed"
        settings = get_api_settings(request)
        if settings.llm_provider == "xai" and not settings.xai_api_key:
            checks["configuration"] = "missing_xai_api_key"
        else:
            checks["configuration"] = "ok"
        ready_status = "ok" if all(value == "ok" for value in checks.values()) else "not_ready"
        if ready_status != "ok":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=HealthResponse(status=ready_status, checks=checks).model_dump(),
            )
        return HealthResponse(status=ready_status, checks=checks)


def get_services(request: Request) -> AppServices:
    return request.app.state.services


def get_api_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_session(request: Request, session_id: UUID) -> AppServices:
    services = get_services(request)
    if not services.store.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return services


async def require_internal_key(
    request: Request,
    internal_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
) -> None:
    expected = get_api_settings(request).internal_api_key
    if internal_key is None or not hmac.compare_digest(internal_key, expected):
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def sse_event(event: str, payload: Any) -> bytes:
    serialized = orjson.dumps(payload).decode("utf-8")
    return f"event: {event}\ndata: {serialized}\n\n".encode()


def chunk_text(value: str, size: int = 24) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]


app = create_app()
