#!/usr/bin/python3

"""
Persona configurations for Barsukas launch environments.

Each persona defines a specific configuration for running Barsukas:
- PROD: Production mode with PostgreSQL, no local API keys
- GOLDEN: Read-only mode using data/release JSONL files
- LOCAL: Development mode with local SQLite database
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class PersonaName(Enum):
    """Available persona configurations."""

    PROD = "prod"
    GOLDEN = "golden"
    LOCAL = "local"


@dataclass
class PersonaConfig:
    """Configuration for a Barsukas persona."""

    name: PersonaName
    description: str

    # Backend configuration
    use_postgres: bool = False
    use_jsonl: bool = False
    jsonl_data_dir: Optional[str] = None  # Relative to repo root

    # Access control
    readonly: bool = False

    # API/LLM settings
    allow_api_keys: bool = True
    allow_outbound_calls: bool = True  # Non-LLM API calls

    # Worker settings
    enable_worker: bool = True


# Define the available personas
PERSONAS: dict[PersonaName, PersonaConfig] = {
    PersonaName.PROD: PersonaConfig(
        name=PersonaName.PROD,
        description="Production mode: PostgreSQL backend, no local API keys, LLM calls only",
        use_postgres=True,
        allow_api_keys=False,
        allow_outbound_calls=False,  # Only LLM calls allowed
        enable_worker=True,
    ),
    PersonaName.GOLDEN: PersonaConfig(
        name=PersonaName.GOLDEN,
        description="Golden mode: Read-only JSONL from data/release",
        use_jsonl=True,
        jsonl_data_dir="data/release",
        readonly=True,
        allow_api_keys=True,
        allow_outbound_calls=True,
        enable_worker=False,  # No worker needed for read-only
    ),
    PersonaName.LOCAL: PersonaConfig(
        name=PersonaName.LOCAL,
        description="Local development: SQLite database with full access",
        use_postgres=False,
        use_jsonl=False,
        readonly=False,
        allow_api_keys=True,
        allow_outbound_calls=True,
        enable_worker=True,
    ),
}


def get_persona(name: str) -> PersonaConfig:
    """Get a persona configuration by name.

    Args:
        name: Persona name (case-insensitive)

    Returns:
        PersonaConfig for the requested persona

    Raises:
        ValueError: If persona name is not recognized
    """
    try:
        persona_name = PersonaName(name.lower())
        return PERSONAS[persona_name]
    except ValueError:
        valid_names = [p.value for p in PersonaName]
        raise ValueError(f"Unknown persona '{name}'. Valid personas: {valid_names}")


def list_personas() -> list[tuple[str, str]]:
    """List all available personas with their descriptions.

    Returns:
        List of (name, description) tuples
    """
    return [(p.name.value, p.description) for p in PERSONAS.values()]


def get_default_persona() -> PersonaConfig:
    """Get the default persona (LOCAL).

    Returns:
        The LOCAL persona configuration
    """
    return PERSONAS[PersonaName.LOCAL]
