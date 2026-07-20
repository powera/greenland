#!/usr/bin/python3

"""
Persona configurations for Barsukas launch environments.

A persona is the single source of truth for how a Barsukas process is
configured. launch.sh forwards --persona and decides nothing itself; the
PersonaConfig object is passed to create_app() and run_worker().

Barsukas talks to two databases, and personas configure them independently:

- main: the lemma/word database. SQLite, data/release JSONL, or PostgreSQL,
  depending on the persona. A custom URL can override it (unified_app --db-url).
- concepts: always the hardcoded global PostgreSQL from
  constants.POSTGRES_URL_TEMPLATE -- never a custom URL. Personas that leave
  use_postgres_concepts unset fall back to reading concepts out of the main
  database, which is what LOCAL_SQLITE wants.

Personas:
- PROD: PostgreSQL main, no local API keys
- GOLDEN/HOSTED: read-only data/release JSONL main, read-only PostgreSQL concepts
- SCHOLAR: read-only JSONL main, writable PostgreSQL concepts, API keys
- LOCAL: SQLite main, writable PostgreSQL concepts (the default)
- LOCAL_SQLITE: SQLite main, SQLite concepts -- fully offline, needs no keys
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PersonaName(Enum):
    """Available persona configurations."""

    PROD = "prod"
    GOLDEN = "golden"
    HOSTED = "hosted"
    LOCAL = "local"
    LOCAL_SQLITE = "local-sqlite"
    SCHOLAR = "scholar"


@dataclass
class PersonaConfig:
    """Configuration for a Barsukas persona."""

    name: PersonaName
    description: str

    # Backend configuration
    use_postgres: bool = False
    use_jsonl: bool = False
    jsonl_data_dir: Optional[str] = None  # Relative to repo root
    use_postgres_concepts: bool = False
    # When use_postgres_concepts is set, connect to PostgreSQL for concepts in a
    # read-only transaction (the server rejects writes/DDL). Used by golden/hosted
    # to browse concepts without granting write access.
    postgres_concepts_readonly: bool = False

    # Access control
    readonly: bool = False

    # API/LLM settings
    allow_api_keys: bool = True
    allow_outbound_calls: bool = True  # Non-LLM API calls

    # Worker settings
    enable_worker: bool = True

    # Hardening settings (for hosted/shared deployments)
    allow_restart: bool = True
    allow_exports: bool = True


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
        description="Golden mode: Read-only JSONL from data/release with read-only PostgreSQL concepts",
        use_jsonl=True,
        jsonl_data_dir="data/release",
        use_postgres_concepts=True,
        postgres_concepts_readonly=True,
        readonly=True,
        allow_api_keys=True,
        allow_outbound_calls=True,
        enable_worker=False,  # No worker needed for read-only
    ),
    PersonaName.HOSTED: PersonaConfig(
        name=PersonaName.HOSTED,
        description="Hosted mode: Read-only JSONL like golden, hardened for shared deployment",
        use_jsonl=True,
        jsonl_data_dir="data/release",
        use_postgres_concepts=True,
        postgres_concepts_readonly=True,
        readonly=True,
        allow_api_keys=False,
        allow_outbound_calls=False,
        enable_worker=False,
        allow_restart=False,
        allow_exports=False,
    ),
    PersonaName.SCHOLAR: PersonaConfig(
        name=PersonaName.SCHOLAR,
        description=(
            "Scholar mode: Golden JSONL data with API keys and writable PostgreSQL concepts"
        ),
        use_jsonl=True,
        jsonl_data_dir="data/release",
        use_postgres_concepts=True,
        readonly=True,
        allow_api_keys=True,
        allow_outbound_calls=True,
        enable_worker=False,
    ),
    PersonaName.LOCAL: PersonaConfig(
        name=PersonaName.LOCAL,
        description="Local development: SQLite main DB with writable PostgreSQL concepts",
        use_postgres=False,
        use_jsonl=False,
        use_postgres_concepts=True,
        readonly=False,
        allow_api_keys=True,
        allow_outbound_calls=True,
        enable_worker=True,
    ),
    PersonaName.LOCAL_SQLITE: PersonaConfig(
        name=PersonaName.LOCAL_SQLITE,
        description="Local development, fully offline: SQLite for both main DB and concepts",
        use_postgres=False,
        use_jsonl=False,
        use_postgres_concepts=False,
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


def resolve_persona(name: Optional[str] = None) -> PersonaConfig:
    """Resolve the persona for this process.

    Resolution order: explicit name, then the BARSUKAS_PERSONA environment
    variable, then LOCAL. The environment fallback is load-bearing -- Procfile
    and Dockerfile select the hosted persona that way, with no CLI flag.

    Args:
        name: Persona name from the command line, if any

    Returns:
        The resolved PersonaConfig; LOCAL when nothing selects one

    Raises:
        ValueError: If a persona name was given but is not recognized
    """
    env_name = os.environ.get("BARSUKAS_PERSONA")
    if name and env_name:
        logger.warning(
            "Both --persona %s and BARSUKAS_PERSONA=%s are set; the flag wins",
            name,
            env_name,
        )
    persona_name = name or env_name
    if persona_name:
        return get_persona(persona_name)
    return get_default_persona()
