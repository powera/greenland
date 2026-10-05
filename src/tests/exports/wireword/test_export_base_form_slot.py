"""grammatical_forms carries the base form under its own slot name.

base_target is also one slot of the word's paradigm -- es ``singular_m``, lt
``nominative_singular_m``, es noun ``singular`` -- and which slot that is
differs by language and part of speech.  The export names it rather than
leaving it out, so a consumer reading grammatical_forms sees the whole
paradigm without knowing which slot is the headword.
"""

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register all tables
from exports.wireword.export_wireword import WirewordExporter
from langtools.form_tasks import get_base_grammatical_form
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation

FormRow = Tuple[str, str, bool]


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    db_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


def _add_word(
    engine: Engine,
    *,
    guid: str,
    lemma_text: str,
    pos_type: str,
    language: str,
    translation: str,
    forms: List[FormRow],
    level: int = 2,
) -> None:
    """Add a lemma, its translation, and (grammatical_form, text, is_base) rows."""
    with Session(engine) as session:
        lemma = Lemma(
            guid=guid,
            lemma_text=lemma_text,
            definition_text=lemma_text,
            pos_type=pos_type,
            pos_subtype="test",
            difficulty_level=level,
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(lemma_id=lemma.id, language_code=language, translation=translation)
        )
        for grammatical_form, text, is_base in forms:
            session.add(
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code=language,
                    grammatical_form=grammatical_form,
                    derivative_form_text=text,
                    is_base_form=is_base,
                )
            )
        session.commit()


def _export(engine: Engine, tmp_path: Path, language: str, verbs: bool = False) -> Dict[str, Any]:
    exporter = WirewordExporter(language=language)
    output_path = tmp_path / f"{language}_{'verbs' if verbs else 'words'}.json"
    with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
        if verbs:
            success, _ = exporter.export_verbs_to_wireword_format(str(output_path))
        else:
            success, _ = exporter.export_to_wireword_format(str(output_path))
    assert success
    rows: List[Dict[str, Any]] = json.loads(output_path.read_text(encoding="utf-8"))
    return {row["guid"]: row for row in rows}


def test_base_row_is_exported_under_its_slot_name(engine: Engine, tmp_path: Path) -> None:
    _add_word(
        engine,
        guid="A01_001",
        lemma_text="red",
        pos_type="adjective",
        language="es",
        translation="rojo",
        forms=[
            ("adjective/es_singular_m", "rojo", True),
            ("adjective/es_singular_f", "roja", False),
            ("adjective/es_plural_m", "rojos", False),
            ("adjective/es_plural_f", "rojas", False),
        ],
    )

    word = _export(engine, tmp_path, "es")["A01_001"]
    forms = word["grammatical_forms"]

    assert set(forms) == {
        "adjective/es_singular_m",
        "adjective/es_singular_f",
        "adjective/es_plural_m",
        "adjective/es_plural_f",
    }
    assert forms["adjective/es_singular_m"]["target"] == word["base_target"] == "rojo"
    # The base form is the word's own card, not a later declension drill.
    assert forms["adjective/es_singular_m"]["level"] == word["level"] == 2


def test_missing_base_row_is_filled_from_base_target(engine: Engine, tmp_path: Path) -> None:
    _add_word(
        engine,
        guid="A01_002",
        lemma_text="green",
        pos_type="adjective",
        language="lt",
        translation="žalias",
        forms=[
            ("adjective/lt_nominative_singular_f", "žalia", False),
            ("adjective/lt_nominative_plural_m", "žali", False),
        ],
    )

    forms = _export(engine, tmp_path, "lt")["A01_002"]["grammatical_forms"]

    assert forms["adjective/lt_nominative_singular_m"]["target"] == "žalias"


def test_generic_base_label_is_replaced_by_the_slot_name(engine: Engine, tmp_path: Path) -> None:
    """Older backfilled base rows say "lemma"; that is not a slot."""
    _add_word(
        engine,
        guid="N01_001",
        lemma_text="house",
        pos_type="noun",
        language="es",
        translation="casa",
        forms=[("lemma", "casa", True), ("noun/es_plural", "casas", False)],
    )

    forms = _export(engine, tmp_path, "es")["N01_001"]["grammatical_forms"]

    assert set(forms) == {"noun/es_singular", "noun/es_plural"}
    assert forms["noun/es_singular"]["target"] == "casa"


def test_word_without_a_paradigm_gets_no_grammatical_forms(engine: Engine, tmp_path: Path) -> None:
    _add_word(
        engine,
        guid="N01_002",
        lemma_text="dog",
        pos_type="noun",
        language="es",
        translation="perro",
        forms=[("noun/es_singular", "perro", True)],
    )

    assert "grammatical_forms" not in _export(engine, tmp_path, "es")["N01_002"]


def test_verb_exports_its_infinitive_and_its_base_slot(engine: Engine, tmp_path: Path) -> None:
    """The Lithuanian forms task marks 1s_present as base; it is a real slot."""
    _add_word(
        engine,
        guid="V01_001",
        lemma_text="walk",
        pos_type="verb",
        language="lt",
        translation="vaikščioti",
        forms=[
            ("verb/lt_1s_present", "vaikštau", True),
            ("verb/lt_2s_present", "vaikštai", False),
        ],
    )

    word = _export(engine, tmp_path, "lt", verbs=True)["V01_001"]
    forms = word["grammatical_forms"]

    assert forms["1s_present"]["target"] == "vaikštau"
    assert forms["infinitive"]["target"] == word["base_target"] == "vaikščioti"
    assert set(word["conjugation_mode"]["tables"]["pres"]) == {"1s", "2s"}


def test_french_infinitive_base_row_survives_the_tense_filter(
    engine: Engine, tmp_path: Path
) -> None:
    _add_word(
        engine,
        guid="V01_002",
        lemma_text="speak",
        pos_type="verb",
        language="fr",
        translation="parler",
        forms=[
            ("verb/fr_infinitive", "parler", True),
            ("verb/fr_1s_present", "parle", False),
        ],
    )

    forms = _export(engine, tmp_path, "fr", verbs=True)["V01_002"]["grammatical_forms"]

    assert set(forms) == {"infinitive", "1s_present"}
    assert forms["infinitive"]["target"] == "parler"


@pytest.mark.parametrize(
    "language, pos_type, expected",
    [
        ("es", "adjective", "adjective/es_singular_m"),
        ("fr", "adjective", "adjective/fr_singular_m"),
        ("lt", "adjective", "adjective/lt_nominative_singular_m"),
        ("es", "noun", "noun/es_singular"),
        ("es-419", "noun", "noun/es-419_singular"),
        ("lt", "noun", "noun/lt_nominative_singular"),
        ("xx", "noun", None),
    ],
)
def test_base_grammatical_form_by_language(
    language: str, pos_type: str, expected: Optional[str]
) -> None:
    assert get_base_grammatical_form(language, pos_type) == expected
