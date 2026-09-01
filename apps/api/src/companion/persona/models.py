from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonaStyle(BaseModel):
    model_config = ConfigDict(frozen=True)

    tone: list[str] = Field(min_length=1)
    response_length: str
    language_behavior: str
    avoid: list[str] = Field(default_factory=list)


class PersonaSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    role: str
    core_traits: tuple[str, ...] = Field(min_length=1)
    backstory: dict[str, str]
    opinions: dict[str, str]
    style: PersonaStyle
    boundaries: tuple[str, ...] = Field(min_length=1)

    def system_prompt(self) -> str:
        traits = ", ".join(self.core_traits)
        backstory = "\n".join(f"- {key}: {value}" for key, value in self.backstory.items())
        opinions = "\n".join(f"- {key}: {value}" for key, value in self.opinions.items())
        boundaries = "\n".join(f"- {item}" for item in self.boundaries)
        avoid = "\n".join(f"- {item}" for item in self.style.avoid)

        return f"""You are {self.name}, {self.role}.

Canonical persona version: {self.version}
Core traits: {traits}

Canonical backstory (never contradict these facts):
{backstory}

Canonical opinions (do not silently reverse them):
{opinions}

Conversation style:
- Tone: {", ".join(self.style.tone)}
- Response length: {self.style.response_length}
- Language: {self.style.language_behavior}

Avoid:
{avoid}

Boundaries:
{boundaries}

Be a companion, not a generic customer-support assistant. Acknowledge feelings without diagnosing,
remember relevant details naturally, and never claim to remember information that is not present in
the supplied memories or recent conversation.
"""
