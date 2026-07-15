#!/usr/bin/python3

"""Characterization tests for persona -> configuration resolution.

These pin down the observable configuration each persona produces so the
refactor that threads PersonaConfig through create_app()/run_worker() can be
proven to be a no-op. They assert on the persona definitions themselves and on
apply_persona_env(), not on Flask app construction, so they stay fast and need
no database or PostgreSQL credentials.
"""

import os
from pathlib import Path
from typing import Iterator, Optional

import pytest

from barsukas.personas import (
    PERSONAS,
    PersonaConfig,
    PersonaName,
    get_default_persona,
    get_persona,
    list_personas,
)

# Env vars that apply_persona_env() owns. Kept in one place so the isolation
# fixture and the assertions cannot drift apart.
PERSONA_ENV_VARS = (
    "STORAGE_BACKEND",
    "JSONL_DATA_DIR",
    "POSTGRES_URL",
    "BARSUKAS_CONCEPTS_BACKEND",
    "BARSUKAS_CONCEPTS_READONLY",
    "BARSUKAS_PERSONA",
)

REPO_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.fixture(autouse=True)
def clean_persona_env() -> Iterator[None]:
    """Remove persona-owned env vars so tests see a known starting state.

    The production code reads these from the ambient environment, so a stray
    STORAGE_BACKEND in the developer's shell would otherwise change results.
    """
    saved = {name: os.environ.get(name) for name in PERSONA_ENV_VARS}
    for name in PERSONA_ENV_VARS:
        os.environ.pop(name, None)
    yield
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class TestPersonaDefinitions:
    """The persona table is the source of truth; pin its contents."""

    def test_all_persona_names_have_a_config(self) -> None:
        for name in PersonaName:
            assert name in PERSONAS, f"PersonaName.{name.name} has no PersonaConfig"
            assert PERSONAS[name].name is name

    def test_default_persona_is_local(self) -> None:
        assert get_default_persona().name is PersonaName.LOCAL

    def test_get_persona_is_case_insensitive(self) -> None:
        assert get_persona("LOCAL").name is PersonaName.LOCAL
        assert get_persona("local").name is PersonaName.LOCAL

    def test_get_persona_rejects_unknown_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown persona"):
            get_persona("nonesuch")

    def test_list_personas_covers_every_persona(self) -> None:
        listed = {name for name, _description in list_personas()}
        assert listed == {p.value for p in PersonaName}

    @pytest.mark.parametrize(
        # (persona, main_backend, readonly, worker, pg_concepts, pg_concepts_readonly)
        "persona_name,main_backend,readonly,worker,pg_concepts,pg_concepts_readonly",
        [
            (PersonaName.PROD, "postgres", False, True, False, False),
            (PersonaName.GOLDEN, "jsonl", True, False, True, True),
            (PersonaName.HOSTED, "jsonl", True, False, True, True),
            (PersonaName.SCHOLAR, "jsonl", True, False, True, False),
            (PersonaName.LOCAL, "sqlite", False, True, True, False),
            (PersonaName.LOCAL_SQLITE, "sqlite", False, True, False, False),
        ],
    )
    def test_persona_backend_matrix(
        self,
        persona_name: PersonaName,
        main_backend: str,
        readonly: bool,
        worker: bool,
        pg_concepts: bool,
        pg_concepts_readonly: bool,
    ) -> None:
        """The main/concepts split is the whole point of the persona table.

        main is sqlite | jsonl | postgres and varies per persona; concepts are
        PostgreSQL (the hardcoded global) or absent.
        """
        persona = PERSONAS[persona_name]

        if main_backend == "postgres":
            assert persona.use_postgres and not persona.use_jsonl
        elif main_backend == "jsonl":
            assert persona.use_jsonl and not persona.use_postgres
        else:
            assert not persona.use_postgres and not persona.use_jsonl

        assert persona.readonly is readonly
        assert persona.enable_worker is worker
        assert persona.use_postgres_concepts is pg_concepts
        assert persona.postgres_concepts_readonly is pg_concepts_readonly

    def test_jsonl_personas_declare_a_data_dir(self) -> None:
        for persona in PERSONAS.values():
            if persona.use_jsonl:
                assert persona.jsonl_data_dir, f"{persona.name.value} is jsonl but sets no dir"

    def test_readonly_concepts_requires_postgres_concepts(self) -> None:
        """postgres_concepts_readonly is meaningless without use_postgres_concepts."""
        for persona in PERSONAS.values():
            if persona.postgres_concepts_readonly:
                assert persona.use_postgres_concepts, (
                    f"{persona.name.value} sets postgres_concepts_readonly "
                    f"without use_postgres_concepts"
                )

    def test_local_has_postgres_concepts_and_sqlite_main(self) -> None:
        """The mode this refactor exists to provide."""
        local = PERSONAS[PersonaName.LOCAL]
        assert not local.use_postgres and not local.use_jsonl  # main == sqlite
        assert local.use_postgres_concepts
        assert not local.postgres_concepts_readonly  # writable
        assert not local.readonly

    def test_local_sqlite_touches_no_postgres(self) -> None:
        """The fully-offline persona: no credentials required at all."""
        local_sqlite = PERSONAS[PersonaName.LOCAL_SQLITE]
        assert not local_sqlite.use_postgres
        assert not local_sqlite.use_jsonl
        assert not local_sqlite.use_postgres_concepts

    def test_hosted_is_hardened(self) -> None:
        hosted = PERSONAS[PersonaName.HOSTED]
        assert not hosted.allow_restart
        assert not hosted.allow_exports
        assert not hosted.allow_api_keys
        assert not hosted.allow_outbound_calls


class TestResolvePersona:
    """Resolution order: explicit name, then BARSUKAS_PERSONA, then LOCAL.

    The env fallback is load-bearing: Procfile and Dockerfile select the hosted
    persona via BARSUKAS_PERSONA with no CLI flag.
    """

    def test_explicit_name_wins(self) -> None:
        from barsukas.personas import resolve_persona

        os.environ["BARSUKAS_PERSONA"] = "golden"
        assert resolve_persona("scholar").name is PersonaName.SCHOLAR

    def test_falls_back_to_env(self) -> None:
        from barsukas.personas import resolve_persona

        os.environ["BARSUKAS_PERSONA"] = "hosted"
        assert resolve_persona(None).name is PersonaName.HOSTED

    def test_defaults_to_local_when_nothing_set(self) -> None:
        """A bare launch.sh is the LOCAL persona, not an unpersona'd path."""
        from barsukas.personas import resolve_persona

        assert resolve_persona(None).name is PersonaName.LOCAL

    def test_unknown_env_persona_raises(self) -> None:
        from barsukas.personas import resolve_persona

        os.environ["BARSUKAS_PERSONA"] = "nonesuch"
        with pytest.raises(ValueError, match="Unknown persona"):
            resolve_persona(None)


class TestApplyPersonaEnv:
    """apply_persona_env() is the sole writer of the compatibility env vars.

    These are read by consumers outside barsukas that hold no persona object --
    notably clients/audio/s3_uploader.get_staging_prefix(), which uses
    STORAGE_BACKEND to pick an S3 key prefix. A wrong value there is a silent
    data-path bug, so the exported values are pinned here.
    """

    def _apply(self, persona: PersonaConfig, postgres_url: Optional[str] = None) -> None:
        from barsukas.personas import apply_persona_env

        apply_persona_env(persona, REPO_ROOT, postgres_url=postgres_url)

    def test_sqlite_persona_exports_sqlite(self) -> None:
        self._apply(PERSONAS[PersonaName.LOCAL])
        assert os.environ["STORAGE_BACKEND"] == "sqlite"
        assert "JSONL_DATA_DIR" not in os.environ
        assert "POSTGRES_URL" not in os.environ

    def test_jsonl_persona_exports_jsonl_and_absolute_dir(self) -> None:
        self._apply(PERSONAS[PersonaName.GOLDEN])
        assert os.environ["STORAGE_BACKEND"] == "jsonl"
        jsonl_dir = Path(os.environ["JSONL_DATA_DIR"])
        assert jsonl_dir.is_absolute()
        assert jsonl_dir == REPO_ROOT / "data/release"

    def test_postgres_persona_exports_url_and_backend(self) -> None:
        """PROD's main backend is postgres; the URL is passed in, not built here,
        so this test needs no credentials."""
        self._apply(PERSONAS[PersonaName.PROD], postgres_url="postgresql://u:p@h:5432/db")
        assert os.environ["STORAGE_BACKEND"] == "postgres"
        assert os.environ["POSTGRES_URL"] == "postgresql://u:p@h:5432/db"

    def test_postgres_concepts_exported_for_concepts_personas(self) -> None:
        self._apply(PERSONAS[PersonaName.LOCAL])
        assert os.environ["BARSUKAS_CONCEPTS_BACKEND"] == "postgres"
        # LOCAL concepts are writable
        assert "BARSUKAS_CONCEPTS_READONLY" not in os.environ

    def test_readonly_concepts_exported_for_golden(self) -> None:
        self._apply(PERSONAS[PersonaName.GOLDEN])
        assert os.environ["BARSUKAS_CONCEPTS_BACKEND"] == "postgres"
        assert os.environ["BARSUKAS_CONCEPTS_READONLY"] == "true"

    def test_local_sqlite_exports_no_concepts_backend(self) -> None:
        self._apply(PERSONAS[PersonaName.LOCAL_SQLITE])
        assert os.environ["STORAGE_BACKEND"] == "sqlite"
        assert "BARSUKAS_CONCEPTS_BACKEND" not in os.environ

    def test_does_not_leak_stale_values_between_personas(self) -> None:
        """Applying a sqlite persona after a jsonl one must clear JSONL_DATA_DIR.

        Otherwise a stale dir would linger and the storage factory's lazy
        from_env() could resolve to the wrong data source.
        """
        self._apply(PERSONAS[PersonaName.GOLDEN])
        assert "JSONL_DATA_DIR" in os.environ

        self._apply(PERSONAS[PersonaName.LOCAL_SQLITE])
        assert os.environ["STORAGE_BACKEND"] == "sqlite"
        assert "JSONL_DATA_DIR" not in os.environ
        assert "BARSUKAS_CONCEPTS_BACKEND" not in os.environ
