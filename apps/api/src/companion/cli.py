from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import typer

from companion.config import get_settings
from companion.domain import MemoryStatus
from companion.factory import AppServices, build_services
from companion.persona.loader import load_persona

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
def eval_command() -> None:
    """Evaluation suite entry point; scenarios are added in the assessment release phase."""
    typer.echo("Evaluation scenarios are not installed yet.")


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
