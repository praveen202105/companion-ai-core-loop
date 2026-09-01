from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from companion.persona import load_persona


def test_mira_persona_is_versioned_and_complete() -> None:
    persona = load_persona()

    assert persona.name == "Mira"
    assert persona.version == "1.0.0"
    assert persona.backstory["hometown"] == "Pune"
    assert "Hinglish" in persona.style.language_behavior
    assert "non-romantic" in persona.system_prompt()


def test_persona_is_immutable() -> None:
    persona = load_persona()

    with pytest.raises((ValidationError, FrozenInstanceError)):
        persona.name = "Someone else"  # type: ignore[misc]
