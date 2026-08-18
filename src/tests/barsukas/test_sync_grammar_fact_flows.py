"""Grammar facts classified as exported must actually import, per language.

The registry decides what reaches ``data/release`` (see its module docstring:
export what a mechanical generator cannot reproduce). Nothing else has to
change when a fact type moves between the two lists -- the loader, the diff and
the apply all gate on ``is_release_grammar_fact_type``. This test pins that, so
promoting a fact type stays a one-line change rather than a hunt for the code
that also needs updating.

``grammatical_gender`` is the worked example: it feeds
``langtools.lt.declension.decline_noun``, which uses it to choose between
overlapping endings, so a rebuild without it picks the wrong declension
pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_release
from storage.config.grammar_fact_registry import (
    EXPORTED_FACT_TYPES,
    NOT_EXPORTED_FACT_TYPES,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import Lemma


@pytest.fixture()
def lemma_release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    directory = tmp_path / "lemmas"
    directory.mkdir(parents=True)
    monkeypatch.setattr(sync_release, "DEFAULT_RELEASE_DIR", directory)
    yield directory


def _write_lang_file(
    release_dir: Path, pos_dir: str, subtype: str, lang: str, records: List[Dict[str, Any]]
) -> None:
    target = release_dir / pos_dir / subtype
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{lang}.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_base(
    release_dir: Path, pos_dir: str, subtype: str, records: List[Dict[str, Any]]
) -> None:
    target = release_dir / pos_dir / subtype
    target.mkdir(parents=True, exist_ok=True)
    (target / "base.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _facts(db_session: Session, guid: str) -> Dict[str, str]:
    db_session.expire_all()
    lemma = db_session.query(Lemma).filter(Lemma.guid == guid).one()
    return {
        fact.fact_type: fact.fact_value
        for fact in db_session.query(GrammarFact).filter(GrammarFact.lemma_id == lemma.id).all()
    }


class TestGrammarFactImport:
    """Importing a new lemma pulls in its release-side grammar facts."""

    def _import_with_facts(
        self,
        client: FlaskClient,
        release_dir: Path,
        facts: List[Dict[str, str]],
        lang: str = "lt",
    ) -> None:
        _write_base(
            release_dir,
            "nouns",
            "animal",
            [
                {
                    "guid": "N08_010",
                    "pos_type": "noun",
                    "pos_subtype": "animal",
                    "concept_label": "wolf",
                    "concept_definition": "a wild canine",
                    "translations": {"en": "wolf", "lt": "vilkas"},
                    "difficulty_level": 3,
                }
            ],
        )
        _write_lang_file(
            release_dir, "nouns", "animal", lang, [{"guid": "N08_010", "grammar_facts": facts}]
        )
        response = client.post(
            "/sync/lemmas/additions/apply",
            data={"selected_guids": "N08_010"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_grammatical_gender_is_imported(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """The fact decline_noun needs as input, and used not to ship at all."""
        self._import_with_facts(
            client,
            lemma_release_dir,
            [{"fact_type": "grammatical_gender", "fact_value": "masculine"}],
        )
        assert _facts(db_session, "N08_010")["grammatical_gender"] == "masculine"

    def test_a_non_exported_fact_is_ignored_on_import(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """declension_class is recomputed by decline_noun, so the file is not its source."""
        self._import_with_facts(
            client,
            lemma_release_dir,
            [{"fact_type": "declension_class", "fact_value": "-as"}],
        )
        assert "declension_class" not in _facts(db_session, "N08_010")

    def test_an_override_fact_is_imported(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """Irregular forms are the original reason grammar facts ship."""
        self._import_with_facts(
            client,
            lemma_release_dir,
            [{"fact_type": "plural", "fact_value": "wolves"}],
            lang="en",
        )
        assert _facts(db_session, "N08_010")["plural"] == "wolves"


class TestListsDriveTheSync:
    """The registry lists are the only place the decision lives."""

    def test_every_exported_type_is_importable_for_its_languages(self) -> None:
        from storage.config.grammar_facts import is_release_grammar_fact_type
        from storage.config.grammar_fact_registry import GRAMMAR_FACT_DEFINITIONS

        for fact_type in EXPORTED_FACT_TYPES:
            definition = GRAMMAR_FACT_DEFINITIONS[fact_type]
            for language_code in definition.languages:
                assert is_release_grammar_fact_type(language_code, fact_type), (
                    f"{fact_type} is listed as exported but the sync would not "
                    f"import it for {language_code}"
                )

    def test_no_non_exported_type_is_importable(self) -> None:
        from storage.config.grammar_facts import is_release_grammar_fact_type
        from storage.config.grammar_fact_registry import GRAMMAR_FACT_DEFINITIONS

        for fact_type in NOT_EXPORTED_FACT_TYPES:
            definition = GRAMMAR_FACT_DEFINITIONS[fact_type]
            for language_code in definition.languages:
                assert not is_release_grammar_fact_type(language_code, fact_type), (
                    f"{fact_type} is listed as not exported but the sync would import "
                    f"it for {language_code}"
                )
