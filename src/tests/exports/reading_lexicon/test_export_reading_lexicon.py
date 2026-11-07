"""The reading lexicon: every surface form of a text language, back to its lemma."""

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register all tables
from exports.reading_lexicon import (
    SCHEMA,
    ReadingLexiconExporter,
    function_word_entries,
    resolve_redirects,
    surface_key,
)
from exports.reading_lexicon.cli import main as cli_main
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    db_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


def _lemma(
    session: Session,
    guid: str,
    text: str,
    pos: str,
    translations: Dict[str, str],
    *,
    level: int = 5,
    definition: str = "",
    forms: Optional[List[Tuple[str, str, str]]] = None,
    facts: Optional[List[Tuple[str, str, str]]] = None,
) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=text,
        definition_text=definition or f"definition of {text}",
        pos_type=pos,
        pos_subtype="test",
        difficulty_level=level,
    )
    session.add(lemma)
    session.flush()
    for code, translation in translations.items():
        session.add(
            LemmaTranslation(lemma_id=lemma.id, language_code=code, translation=translation)
        )
    for language, grammatical_form, form_text in forms or []:
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                language_code=language,
                grammatical_form=grammatical_form,
                derivative_form_text=form_text,
                is_base_form=False,
            )
        )
    for language, fact_type, value in facts or []:
        session.add(
            GrammarFact(
                lemma_id=lemma.id, language_code=language, fact_type=fact_type, fact_value=value
            )
        )
    return lemma


def _build(engine: Engine, language: str, **kwargs: Any) -> Dict[str, Any]:
    with Session(engine) as session:
        return ReadingLexiconExporter(language=language, **kwargs).build(session)


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        _lemma(
            session,
            "N01_001",
            "lead",
            "noun",
            {"es": "plomo", "fr": "plomb", "zh": "铅", "lt": "švinas"},
            forms=[("en", "noun/en_plural", "leads")],
        )
        _lemma(
            session,
            "V01_001",
            "lead",
            "verb",
            {"es": "dirigir", "fr": "mener", "zh": "带领", "lt": "vadovauti"},
            forms=[("en", "verb/en_3s_present", "leads"), ("en", "verb/en_1s_past", "led")],
        )
        _lemma(
            session,
            "V01_002",
            "speak",
            "verb",
            {"es": "hablar", "fr": "parler"},
            # English verbs conjugate by rule only from stored principal parts.
            facts=[("en", "past", "spoke"), ("en", "past_participle", "spoken")],
        )
        _lemma(
            session, "N01_002", "length", "noun", {"zh": "长"}, facts=[("zh", "pinyin", "cháng")]
        )
        _lemma(session, "A01_001", "long", "adjective", {"zh": "长的"})
        _lemma(session, "N01_003", "junk", "noun", {"es": "trasto"}, level=-1)
        _lemma(session, "N01_004", "draft", "noun", {"es": "borrador"}, level=1399)
        session.add(
            GuidTombstone(
                guid="N09_001",
                original_lemma_text="lead (old)",
                original_pos_type="noun",
                reason="subtype_change",
                replacement_guid="N05_001",
            )
        )
        session.add(
            GuidTombstone(
                guid="N05_001",
                original_lemma_text="lead (older)",
                original_pos_type="noun",
                reason="subtype_change",
                replacement_guid="N01_001",
            )
        )
        session.add(
            GuidTombstone(
                guid="N09_002",
                original_lemma_text="gone",
                original_pos_type="noun",
                reason="wrong_category",
            )
        )
        session.commit()


def test_document_shape_and_meta(engine: Engine) -> None:
    _seed(engine)
    document = _build(engine, "en")
    assert set(document) == {"_meta", "lemmas", "forms", "function_words", "redirects", "deleted"}
    meta = document["_meta"]
    assert meta["schema"] == SCHEMA
    assert meta["language"] == "en"
    assert "en" not in meta["gloss_languages"]
    assert meta["lemma_count"] == len(document["lemmas"])


def test_homographs_keep_every_analysis(engine: Engine) -> None:
    _seed(engine)
    forms = _build(engine, "en")["forms"]
    leads = {(analysis["g"], analysis.get("f")) for analysis in forms["leads"]}
    assert leads == {("N01_001", "noun/en_plural"), ("V01_001", "verb/en_3s_present")}
    assert {analysis["g"] for analysis in forms["lead"]} == {"N01_001", "V01_001"}
    assert forms["led"] == [{"g": "V01_001", "src": "stored", "f": "verb/en_1s_past"}]


def test_rule_built_forms_fill_unstored_slots(engine: Engine) -> None:
    _seed(engine)
    forms = _build(engine, "en")["forms"]
    # "speaks" is not stored; the English rules build it.
    assert any(a["g"] == "V01_002" and a["src"] == "rule" for a in forms["speaks"])


def test_stored_rows_win_over_rules(engine: Engine) -> None:
    _seed(engine)
    forms = _build(engine, "en")["forms"]
    # The stored irregular past is kept; the rule's "leaded" never appears.
    assert "leaded" not in forms


def test_stored_forms_only(engine: Engine) -> None:
    _seed(engine)
    forms = _build(engine, "en", derive_forms=False)["forms"]
    assert "speaks" not in forms
    assert "speak" in forms


def test_spanish_text_uses_spanish_headwords_and_reading_tenses(engine: Engine) -> None:
    _seed(engine)
    document = _build(engine, "es")
    assert document["lemmas"]["V01_002"]["lemma"] == "hablar"
    assert document["lemmas"]["V01_002"]["gloss"]["en"] == "speak"
    forms = document["forms"]
    assert {"g": "V01_002", "src": "rule", "f": "verb/es_1s_imperfect"} in forms["hablaba"]
    assert any(a.get("f") == "verb/es_3s_subjunctive_present" for a in forms["hable"])
    # Lemmas with no Spanish translation are not in a Spanish lexicon.
    assert "N01_002" not in document["lemmas"]


def test_excluded_and_staging_levels(engine: Engine) -> None:
    _seed(engine)
    assert "N01_003" not in _build(engine, "es")["lemmas"]
    assert "N01_004" not in _build(engine, "es")["lemmas"]
    assert "N01_004" in _build(engine, "es", include_staging=True)["lemmas"]


def test_chinese_readings_use_overrides_and_flag_guesses(engine: Engine) -> None:
    _seed(engine)
    lemmas = _build(engine, "zh")["lemmas"]
    assert lemmas["N01_002"]["reading"] == {
        "pinyin": "cháng",
        "syllables": ["cháng"],
        "source": "override",
    }
    long_reading = lemmas["A01_001"]["reading"]
    assert long_reading["pinyin"].endswith(" de")
    assert lemmas["N01_001"]["reading"]["pinyin"] == "qiān"


def test_redirects_follow_chains_to_live_guids(engine: Engine) -> None:
    _seed(engine)
    document = _build(engine, "en")
    assert document["redirects"]["N09_001"] == "N01_001"
    assert document["redirects"]["N05_001"] == "N01_001"
    assert "N09_002" in document["deleted"]


def test_resolve_redirects_handles_cycles() -> None:
    redirects, deleted = resolve_redirects([("A", "B"), ("B", "A"), ("C", "D")])
    assert redirects == {"C": "D"}
    assert deleted == ["A", "B"]


def test_function_words() -> None:
    english = function_word_entries("en")
    assert {"pos": "article", "category": "articles"} in english["the"]
    assert any(entry.get("lemma") == "be" for entry in english["was"])
    spanish = function_word_entries("es")
    assert any(entry["pos"] == "pronoun" for entry in spanish["lo"])
    assert function_word_entries("xx") == {}


def test_surface_key_folds_case_and_apostrophes() -> None:
    assert surface_key(" L’Homme ") == "l'homme"


def test_cli_writes_one_file_per_language(engine: Engine, tmp_path: Path, monkeypatch: Any) -> None:
    _seed(engine)
    monkeypatch.setattr(
        "exports.reading_lexicon.export_reading_lexicon.create_session",
        lambda config: Session(engine),
    )
    cli_main(["--language", "en", "es", "--output-dir", str(tmp_path)])
    for language in ("en", "es"):
        path = tmp_path / f"reading-lexicon.{language}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["_meta"]["language"] == language
