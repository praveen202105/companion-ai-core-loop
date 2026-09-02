from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from companion.config import get_settings
from companion.domain import MemoryStatus
from companion.evaluation import run_evaluation, run_live_evaluation
from companion.factory import AppServices, build_services
from companion.persona.loader import load_persona
from companion.providers import GroqResponsesProvider
from companion.storage import Database, PostgresMemoryStore, SqlAlchemyMemoryStore

app = typer.Typer(help="Mira companion CLI")
memory_app = typer.Typer(help="Inspect durable memories and their audit history")
app.add_typer(memory_app, name="memory")
SESSION_FILE = Path("data/current-session")


def services() -> AppServices:
    return build_services(get_settings())


def current_session(service: AppServices, requested: str | None = None) -> UUID:
    if requested is not None:
        session_id = UUID(requested)
        if not service.store.session_exists(session_id):
            raise typer.BadParameter(f"Session {session_id} does not exist")
        return session_id
    if SESSION_FILE.exists():
        session_id = UUID(SESSION_FILE.read_text(encoding="utf-8").strip())
        if service.store.session_exists(session_id):
            return session_id
    session_id = service.store.create_session(persona_version=load_persona().version)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(str(session_id), encoding="utf-8")
    typer.echo(f"Created session: {session_id}")
    return session_id


@app.command()
def chat(
    message: str | None = typer.Option(None, "--message", "-m"),
    session: str | None = typer.Option(None, "--session"),
) -> None:
    """Send one message or start an interactive companion session."""
    service = services()
    try:
        session_id = current_session(service, session)
        if message is not None:
            result = asyncio.run(
                service.chat.turn(session_id=session_id, message=message)
            )
            typer.echo(f"Mira: {result.response}")
            return
        typer.echo("Commands: /memories, /history, /explain, /reset, /quit")
        while True:
            text = typer.prompt("You")
            if text == "/quit":
                return
            if text == "/memories":
                _print_memories(service, session_id)
                continue
            if text == "/history":
                _print_history(service, session_id)
                continue
            if text == "/explain":
                _print_explain(service, session_id)
                continue
            if text == "/reset":
                service.store.delete_session(session_id)
                typer.echo("Session permanently deleted.")
                return
            result = asyncio.run(service.chat.turn(session_id=session_id, message=text))
            typer.echo(f"Mira: {result.response}")
    finally:
        service.database.dispose()


@memory_app.command("list")
def memory_list(session: str | None = typer.Option(None, "--session")) -> None:
    """List active memories."""
    service = services()
    try:
        _print_memories(service, current_session(service, session))
    finally:
        service.database.dispose()


@memory_app.command()
def history(session: str | None = typer.Option(None, "--session")) -> None:
    """Show append-only memory decisions."""
    service = services()
    try:
        _print_history(service, current_session(service, session))
    finally:
        service.database.dispose()


@app.command()
def explain_last_turn(session: str | None = typer.Option(None, "--session")) -> None:
    """Show observable extraction and retrieval decisions, never hidden reasoning."""
    service = services()
    try:
        _print_explain(service, current_session(service, session))
    finally:
        service.database.dispose()


@app.command()
def reset(session: str | None = typer.Option(None, "--session")) -> None:
    """Permanently delete a session and all of its data."""
    service = services()
    try:
        session_id = current_session(service, session)
        if service.store.delete_session(session_id):
            typer.echo(f"Deleted session {session_id}")
    finally:
        service.database.dispose()


@app.command()
def demo() -> None:
    """Run a deterministic persistence and contradiction demonstration."""
    service = services()
    try:
        session_id = service.store.create_session(persona_version=load_persona().version)
        turns = (
            "My name is Praveen",
            "I live in Pune",
            "I moved to Bengaluru",
            "Where do I live?",
        )
        typer.echo(f"Demo session: {session_id}")
        for text in turns:
            result = asyncio.run(service.chat.turn(session_id=session_id, message=text))
            typer.echo(f"You: {text}\nMira: {result.response}")
        _print_explain(service, session_id)
    finally:
        service.database.dispose()


@app.command("eval")
def eval_command(
    output: Annotated[
        Path,
        typer.Option("--output", help="Path for the numeric evaluation report"),
    ] = Path("evals/results/latest.json"),
) -> None:
    """Run deterministic memory and persona evaluation scenarios."""
    report = asyncio.run(run_evaluation(output_path=output))
    typer.echo(report.metrics.model_dump_json(indent=2))
    if report.failures:
        raise typer.Exit(code=1)


@app.command("eval-live")
def eval_live_command(
    output: Annotated[
        Path,
        typer.Option("--output", help="Path for the real-provider evaluation report"),
    ] = Path("evals/results/groq-live-v1.json"),
    checkpoint: Annotated[
        Path,
        typer.Option("--checkpoint", help="Ignored resumable live-eval checkpoint"),
    ] = Path("data/groq-live-v1.checkpoint.json"),
) -> None:
    """Run the 52-turn Groq memory, persona, and tone evaluation."""
    settings = get_settings()
    if not settings.groq_api_key:
        raise typer.BadParameter("GROQ_API_KEY is required")
    chat_provider = GroqResponsesProvider(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model=settings.groq_chat_model,
        extraction_model=settings.groq_extraction_model,
        max_output_tokens=300,
        extraction_max_output_tokens=800,
    )
    judge_provider = GroqResponsesProvider(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model=settings.groq_judge_model,
        extraction_model=settings.groq_judge_model,
        max_output_tokens=500,
        extraction_max_output_tokens=1_200,
    )
    report = asyncio.run(
        run_live_evaluation(
            chat_provider=chat_provider,
            judge_provider=judge_provider,
            output_path=output,
            checkpoint_path=checkpoint,
            progress=lambda turn, total: typer.echo(f"Live eval turn {turn}/{total}"),
            judge_progress=lambda batch, total: typer.echo(
                f"Live eval judge batch {batch}/{total}"
            ),
            turn_delay_seconds=30,
            judge_delay_seconds=60,
        )
    )
    typer.echo(report.metrics.model_dump_json(indent=2))
    if not all(report.acceptance.values()):
        raise typer.Exit(code=1)


@app.command()
def cleanup() -> None:
    """Permanently remove sessions whose retention window has expired."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise typer.BadParameter("DATABASE_URL is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    database = Database(database_url)
    store = (
        PostgresMemoryStore(database)
        if database.engine.dialect.name == "postgresql"
        else SqlAlchemyMemoryStore(database)
    )
    try:
        removed = store.cleanup_expired_sessions()
        typer.echo(f"Deleted {removed} expired session(s).")
    finally:
        database.dispose()


def _print_memories(service: AppServices, session_id: UUID) -> None:
    memories = service.store.list_memories(session_id, status=MemoryStatus.ACTIVE)
    if not memories:
        typer.echo("No active memories.")
    for item in memories:
        typer.echo(f"{item.canonical_key}: {item.value} ({item.memory_type.value})")


def _print_history(service: AppServices, session_id: UUID) -> None:
    events = service.store.memory_history(session_id)
    if not events:
        typer.echo("No memory events.")
    for event in events:
        typer.echo(f"{event.action.value}: {event.canonical_key or '-'} [{event.reason_code}]")


def _print_explain(service: AppServices, session_id: UUID) -> None:
    trace = service.store.latest_retrieval(session_id)
    if trace is None:
        typer.echo("No retrieval trace yet.")
        return
    typer.echo(
        f"Retrieval {trace.algorithm_version}: {trace.candidate_count} candidates; "
        f"degraded={trace.degraded_mode or 'no'}"
    )
    for selected in trace.selected:
        typer.echo(
            f"selected {selected['canonical_key']} score={selected['score']} "
            f"factors={selected['factors']}"
        )
