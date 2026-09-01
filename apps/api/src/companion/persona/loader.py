from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from companion.persona.models import PersonaSpec

DEFAULT_PERSONA_PATH = Path(__file__).with_name("mira.v1.yaml")


def load_persona(path: Path | None = None) -> PersonaSpec:
    source = path or DEFAULT_PERSONA_PATH
    with source.open(encoding="utf-8") as stream:
        raw = cast(dict[str, Any], yaml.safe_load(stream))
    return PersonaSpec.model_validate(raw)
