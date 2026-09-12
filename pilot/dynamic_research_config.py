"""Server-owned credentials and executable paths for dynamic public research."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re


_MODEL = re.compile(r"[A-Za-z0-9_./:-]{1,128}")


@dataclass(frozen=True)
class DynamicResearchAgentConfiguration:
    codex_binary: str
    python_binary: str
    api_key: str = field(repr=False)
    model: str
    search_api_key: str = field(repr=False)


def _executable(value: str) -> bool:
    path = Path(value)
    return path.is_absolute() and path.is_file() and os.access(path, os.X_OK)


def dynamic_agent_configuration(values: tuple[str, str, str, str, str]):
    """Validate a complete deployment-owned worker configuration.

    Returning ``None`` means no dynamic worker values were supplied. A partial
    tuple is never guessed from PATH, the user environment, or local Codex state.
    """
    present = tuple(type(value) is str and bool(value.strip()) for value in values)
    if not any(present):
        return None
    if not all(present):
        raise ValueError("incomplete dynamic research agent configuration")
    codex, python, api_key, model, search_api_key = values
    valid = (
        _executable(codex)
        and _executable(python)
        and api_key == api_key.strip()
        and search_api_key == search_api_key.strip()
        and not any(character.isspace() for character in api_key)
        and not any(character.isspace() for character in search_api_key)
        and _MODEL.fullmatch(model) is not None
    )
    if not valid:
        raise ValueError("invalid dynamic research agent configuration")
    return DynamicResearchAgentConfiguration(
        codex_binary=codex,
        python_binary=python,
        api_key=api_key,
        model=model,
        search_api_key=search_api_key,
    )
