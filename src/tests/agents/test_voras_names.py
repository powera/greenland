"""Voras name selection, identity prompts, and persisted translation outcomes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.voras.cli import get_argument_parser, validate_name_args, _run_names
from storage.backend.config import DataSourceConfig
from storage.crud.name_entity import create_name, set_name_translation, add_name_derivative_form
from storage.models.name_entity import Name
from storage.models.schema import Base
from storage.release.name import to_release_record, import_release_record, apply_release_record
from words.name_translation import (
    build_name_translation_prompt,
    name_form_slots,
    pending_name_languages,
    store_name_translation_answer,
    translate_name,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def answer(language: str, text: str, confidence: float = 0.95) -> dict[str, Any]:
    return {
        "translation": text,
        "confidence": confidence,
        "forms": {slot: text for slot in name_form_slots(language)},
    }


@pytest.mark.parametrize("guid", ["E01_001", "E02_001"])
def test_name_guid_is_recognized(guid: str) -> None:
    parser = get_argument_parser()
    assert validate_name_args(parser, parser.parse_args(["--guid", guid, "--populate"]))
    assert not validate_name_args(parser, parser.parse_args(["--guid", "N01_001", "--populate"]))


@pytest.mark.parametrize(
    "flags",
    [
        ["--guid", "E01_001"],
        ["--guid", "N01_001"],
        ["--level", "5"],
        ["--pos-type", "noun"],
        ["--sample-rate", "0.5"],
        ["--batch"],
        ["--batch-submit"],
        ["--use-workqueue"],
        ["--cache-only"],
    ],
)
def test_all_names_rejects_lemma_modes(flags: list[str]) -> None:
    parser = get_argument_parser()
    with pytest.raises(SystemExit):
        validate_name_args(parser, parser.parse_args(["--all-names", "--populate", *flags]))


@pytest.mark.parametrize("kind", ["given_name", "family_name"])
def test_prompt_preserves_identity_and_requests_lithuanian_cases(
    session: Session, kind: str
) -> None:
    name = create_name(session, name_text="John", kind=kind, gender="masculine")
    _, prompt, schema = build_name_translation_prompt(name, ["ru", "lt"])
    assert "Джон, NEVER Иван" in prompt
    assert kind in prompt
    assert "masculine" in prompt
    assert schema["properties"]["lt"]["properties"]["forms"]["required"] == name_form_slots("lt")


def test_populate_fills_forms_without_replacing_reviewed_translation(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    set_name_translation(session, name, language_code="lt", translation="Džonas", verified=True)
    session.commit()
    assert pending_name_languages(name, ["lt"]) == ["lt"]
    _, prompt, _ = build_name_translation_prompt(name, ["lt"])
    assert "Keep the existing lt base EXACTLY" in prompt
    with pytest.raises(ValueError, match="cannot replace"):
        store_name_translation_answer(session, name, "lt", answer("lt", "Jonas"))
    assert store_name_translation_answer(session, name, "lt", answer("lt", "Džonas"))
    session.commit()
    assert len([row for row in name.derivative_forms if row.language_code == "lt"]) == 7
    assert name.translations[0].verified
    assert pending_name_languages(name, ["lt"]) == []


def test_invalid_or_uncertain_regeneration_keeps_old_forms(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    assert store_name_translation_answer(session, name, "lt", answer("lt", "Džonas"))
    session.commit()
    original = to_release_record(name)
    assert not store_name_translation_answer(
        session, name, "lt", answer("lt", "Jonas", 0.2), regenerate=True
    )
    incomplete = answer("lt", "Jonas")
    del incomplete["forms"]["noun/lt_vocative_singular"]
    with pytest.raises(ValueError, match="Incomplete"):
        store_name_translation_answer(session, name, "lt", incomplete, regenerate=True)
    assert to_release_record(name) == original


def test_regeneration_replaces_one_language_only(session: Session) -> None:
    name = create_name(session, name_text="John", kind="family_name")
    store_name_translation_answer(session, name, "lt", answer("lt", "Old"))
    store_name_translation_answer(session, name, "ru", answer("ru", "Джон"))
    session.commit()
    store_name_translation_answer(session, name, "lt", answer("lt", "Džonas"), regenerate=True)
    session.commit()
    assert {row.translation for row in name.translations} == {"Džonas", "Джон"}
    assert {
        row.derivative_form_text for row in name.derivative_forms if row.language_code == "lt"
    } == {"Džonas"}
    assert {
        row.derivative_form_text for row in name.derivative_forms if row.language_code == "en"
    } == {"John", "John's"}


class FakeClient:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.calls = 0

    def generate_chat(self, **kwargs: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(structured_data=self.data)


def test_generation_commits_success_when_other_language_fails(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    session.commit()
    fake = FakeClient({"ru": answer("ru", "Джон"), "lt": {}})
    assert not translate_name(session, name, ["ru", "lt"], config=DataSourceConfig(), client=fake)  # type: ignore[arg-type]
    session.expire_all()
    assert {row.language_code: row.translation for row in name.translations} == {"ru": "Джон"}
    assert fake.calls == 1


def test_complete_names_make_no_calls(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    store_name_translation_answer(session, name, "ru", answer("ru", "Джон"))
    session.commit()
    fake = FakeClient({})
    assert translate_name(session, name, ["ru"], config=DataSourceConfig(), client=fake)  # type: ignore[arg-type]
    assert fake.calls == 0


def test_release_round_trip_preserves_declensions_and_metadata(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    store_name_translation_answer(session, name, "lt", answer("lt", "Džonas"))
    session.commit()
    name.derivative_forms[-1].notes = "curated"
    name.derivative_forms[-1].verified = True
    session.commit()
    record = to_release_record(name)
    assert len(record["forms"]) == 7
    assert all(row["language_code"] != "en" for row in record["forms"])
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        imported = import_release_record(target, record)
        assert imported is not None
        target.commit()
        assert to_release_record(imported) == record
        apply_release_record(target, record, imported)
        target.commit()
        assert to_release_record(imported) == record
        without_forms = {field: value for field, value in record.items() if field != "forms"}
        apply_release_record(target, without_forms, imported)
        target.commit()
        assert all(row.language_code == "en" for row in imported.derivative_forms)
    engine.dispose()


def test_dry_run_does_not_translate_or_commit(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    session.commit()
    parser = get_argument_parser()
    args = parser.parse_args(["--all-names", "--populate", "--dry-run", "--languages", "lt"])
    monkeypatch.setattr(
        "words.name_translation.translate_name", lambda *a, **kw: pytest.fail("dry-run called LLM")
    )
    agent = SimpleNamespace(config=DataSourceConfig(), get_session=lambda: session)
    assert _run_names(agent, args) == 0
    assert session.query(Name).filter_by(guid=name.guid).one().translations == []


def test_population_keeps_curated_cases_and_stores_distinct_new_forms(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    set_name_translation(session, name, language_code="lt", translation="Džonas")
    add_name_derivative_form(
        session,
        name,
        language_code="lt",
        grammatical_form="noun/lt_genitive_singular",
        derivative_form_text="curated-genitive",
    )
    session.commit()
    response = answer("lt", "Džonas")
    response["forms"]["noun/lt_dative_singular"] = "model-dative"
    assert store_name_translation_answer(session, name, "lt", response)
    stored = {row.grammatical_form: row.derivative_form_text for row in name.derivative_forms}
    assert stored["noun/lt_genitive_singular"] == "curated-genitive"
    assert stored["noun/lt_dative_singular"] == "model-dative"


@pytest.mark.parametrize("mode", ["--populate", "--regenerate"])
def test_name_guid_dispatches_before_lemma_workflow(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    from agents.voras import cli

    called: list[str] = []
    monkeypatch.setattr("sys.argv", ["voras", mode, "--guid", "E01_001"])
    monkeypatch.setattr(cli, "get_data_source_config", lambda args: DataSourceConfig())
    monkeypatch.setattr("words.translation_workflow.TranslationWorkflow", lambda **kwargs: object())

    def run_names(agent: Any, args: Any) -> int:
        called.append(args.guid)
        return 0

    monkeypatch.setattr(cli, "_run_names", run_names)
    assert cli.main() == 0
    assert called == ["E01_001"]


def test_all_languages_are_batched_without_dropping_targets(session: Session) -> None:
    from storage.translation_helpers import get_supported_languages

    languages = [code for code in get_supported_languages() if code != "en"][:12]
    name = create_name(session, name_text="John", kind="given_name")
    session.commit()
    fake = FakeClient({code: answer(code, "rendering") for code in languages})
    assert translate_name(session, name, languages, config=DataSourceConfig(), client=fake)  # type: ignore[arg-type]
    assert fake.calls == 2
    assert {row.language_code for row in name.translations} == set(languages)


def test_guid_selects_family_name_even_when_given_name_has_same_text(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_name(session, name_text="Jordan", kind="given_name")
    family = create_name(session, name_text="Jordan", kind="family_name")
    session.commit()
    assert family.guid is not None
    selected: list[tuple[str, list[str], bool]] = []

    def translate_selected(
        db_session: Session,
        selected_name: Name,
        targets: list[str],
        **kwargs: Any,
    ) -> bool:
        selected.append((selected_name.kind, targets, kwargs["regenerate"]))
        return True

    monkeypatch.setattr("words.name_translation.translate_name", translate_selected)
    args = get_argument_parser().parse_args(
        [
            "--guid",
            family.guid,
            "--regenerate",
            "--languages",
            "lt",
            "--yes",
        ]
    )
    assert (
        _run_names(SimpleNamespace(config=DataSourceConfig(), get_session=lambda: session), args)
        == 0
    )
    assert selected == [("family_name", ["lt"], True)]
