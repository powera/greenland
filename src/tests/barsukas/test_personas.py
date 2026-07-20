#!/usr/bin/python3

"""Characterization tests for persona -> configuration resolution.

These pin down the observable configuration each persona produces. They assert
on the persona definitions themselves, not on Flask app construction, so they
stay fast and need no database or PostgreSQL credentials.
"""

import os
from typing import Iterator

import pytest

from barsukas.personas import (
    PERSONAS,
    PersonaName,
    get_default_persona,
    get_persona,
    list_personas,
)


@pytest.fixture(autouse=True)
def clean_persona_env() -> Iterator[None]:
    """Remove BARSUKAS_PERSONA so tests see a known starting state."""
    saved = os.environ.get("BARSUKAS_PERSONA")
    os.environ.pop("BARSUKAS_PERSONA", None)
    yield
    if saved is None:
        os.environ.pop("BARSUKAS_PERSONA", None)
    else:
        os.environ["BARSUKAS_PERSONA"] = saved


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

    def test_flag_plus_env_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Setting both the flag and BARSUKAS_PERSONA warns that the flag wins."""
        import logging

        from barsukas.personas import resolve_persona

        os.environ["BARSUKAS_PERSONA"] = "golden"
        with caplog.at_level(logging.WARNING, logger="barsukas.personas"):
            resolve_persona("scholar")
        assert any("BARSUKAS_PERSONA" in record.message for record in caplog.records)

    def test_flag_alone_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from barsukas.personas import resolve_persona

        with caplog.at_level(logging.WARNING, logger="barsukas.personas"):
            resolve_persona("scholar")
        assert not caplog.records

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
