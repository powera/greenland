"""Test database fixture for candidate_lookup tests.

Builds an in-memory SQLite database seeded from a slice of data/release
(~50 real lemmas with bn/uk/kn translations from secondary.jsonl) plus a
handful of hand-authored ambiguous lemmas that the release data does not
supply (notably two senses of "can" — modal vs. container — and two senses
of "play" — verb vs. noun).

The fixture is reused by test_candidate_lookup.py and can also be used
from interactive debugging. It is deliberately kept free of test-framework
code so it is easy to import from a REPL.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation, Sentence

# Languages we pull out of the release JSONL files. "en" comes from the
# release "translations" map (NOT from concept_label, because some entries
# have disambiguation parentheticals).
_RELEASE_BASE_LANGUAGES = ["en", "fr", "es", "lt", "zh", "de", "sv", "ja"]

# Languages we expect in secondary.jsonl.
_RELEASE_SECONDARY_LANGUAGES = ["bn", "uk", "kn", "hi", "ta", "th"]

# Release categories we slice to get ~50 lemmas. Chosen for topical variety
# (animals, body parts, common actions, motion verbs) so the seeded
# vocabulary has enough reach for hand-written test sentences.
_RELEASE_SLICES: List[Tuple[str, int]] = [
    ("nouns/animal", 10),
    ("nouns/body_part", 8),
    ("nouns/small_movable_object", 6),
    ("nouns/tool", 4),
    ("verbs/physical_action", 8),
    ("verbs/directional_movement", 6),
    ("verbs/perception", 4),
    ("verbs/communication", 4),
]

_RELEASE_ROOT = Path(__file__).resolve().parents[3] / "data" / "release" / "lemmas"


@dataclass
class _CustomLemma:
    """Hand-authored lemma for ambiguity tests."""

    guid: str
    lemma_text: str
    pos_type: str
    definition_text: str
    disambiguation: str
    translations: Dict[str, str]
    # Optional derivative forms: list of (language_code, form_text, grammatical_form).
    derivative_forms: List[Tuple[str, str, str]] = field(default_factory=list)


# The two senses of "can" that drive the core ambiguity test. Translations
# are chosen so that bn/uk/kn rendering of a modal-"can" sentence confirms
# the modal lemma but not the container lemma (and vice versa).
_CUSTOM_LEMMAS: List[_CustomLemma] = [
    _CustomLemma(
        guid="TEST_CAN_MODAL",
        lemma_text="can",
        pos_type="verb",
        definition_text="to be able to do something",
        disambiguation="modal",
        translations={
            "fr": "pouvoir",
            "es": "poder",
            "lt": "galėti",
            "zh": "能",
            "de": "können",
            "sv": "kunna",
            "ja": "できる",
            "bn": "পারা",
            "uk": "могти",
            "kn": "ಸಾಧ್ಯ",
        },
        derivative_forms=[
            ("en", "can", "base"),
            ("uk", "можу", "1s_present"),
            ("uk", "можеш", "2s_present"),
        ],
    ),
    _CustomLemma(
        guid="TEST_CAN_CONTAINER",
        lemma_text="can",
        pos_type="noun",
        definition_text="a cylindrical metal container",
        disambiguation="container",
        translations={
            "fr": "boîte",
            "es": "lata",
            "lt": "skardinė",
            "zh": "罐",
            "de": "Dose",
            "sv": "burk",
            "ja": "缶",
            "bn": "ক্যান",
            "uk": "банка",
            "kn": "ಕ್ಯಾನ್",
        },
    ),
    _CustomLemma(
        guid="TEST_PLAY_NOUN",
        lemma_text="play",
        pos_type="noun",
        definition_text="a theatrical performance",
        disambiguation="theatre",
        translations={
            "fr": "pièce",
            "es": "obra",
            "lt": "pjesė",
            "zh": "戏剧",
            "de": "Theaterstück",
            "sv": "pjäs",
            "ja": "劇",
            "bn": "নাটক",
            "uk": "вистава",
            "kn": "ನಾಟಕ",
        },
    ),
    _CustomLemma(
        guid="TEST_TODAY",
        lemma_text="today",
        pos_type="adverb",
        definition_text="on the current day",
        disambiguation="",
        translations={
            "fr": "aujourd'hui",
            "es": "hoy",
            "lt": "šiandien",
            "zh": "今天",
            "de": "heute",
            "sv": "idag",
            "ja": "今日",
            "bn": "আজ",
            "uk": "сьогодні",
            "kn": "ಇಂದು",
        },
    ),
]


def _iter_release_slice(category: str, limit: int) -> Iterable[Tuple[dict, Optional[dict]]]:
    """Yield (base_entry, secondary_entry_or_None) pairs from one category."""
    base_path = _RELEASE_ROOT / category / "base.jsonl"
    if not base_path.exists():
        return

    secondary_by_guid: Dict[str, dict] = {}
    secondary_path = _RELEASE_ROOT / category / "secondary.jsonl"
    if secondary_path.exists():
        with secondary_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                guid = entry.get("guid")
                if guid:
                    secondary_by_guid[guid] = entry

    count = 0
    with base_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            guid = entry.get("guid")
            if not guid:
                continue
            yield entry, secondary_by_guid.get(guid)
            count += 1
            if count >= limit:
                break


def _insert_release_lemma(
    session: Session, base_entry: dict, secondary_entry: Optional[dict]
) -> Lemma:
    """Create one Lemma (and its LemmaTranslation rows) from release data."""
    base_translations: Dict[str, str] = base_entry.get("translations") or {}
    english_text = base_translations.get("en") or base_entry.get("concept_label", "")
    # Strip any "(disambiguation)" from concept_label if present.
    if "(" in english_text:
        english_text = english_text.split("(")[0].strip()

    lemma = Lemma(
        guid=base_entry["guid"],
        lemma_text=english_text,
        pos_type=base_entry.get("pos_type", ""),
        pos_subtype=base_entry.get("pos_subtype"),
        definition_text=base_entry.get("concept_definition", ""),
        disambiguation=None,
        difficulty_level=base_entry.get("difficulty_level"),
    )
    session.add(lemma)
    session.flush()

    _add_translations(session, lemma, base_translations, _RELEASE_BASE_LANGUAGES)
    if secondary_entry:
        secondary_translations = secondary_entry.get("translations") or {}
        _add_translations(session, lemma, secondary_translations, _RELEASE_SECONDARY_LANGUAGES)

    return lemma


def _add_translations(
    session: Session,
    lemma: Lemma,
    translations: Dict[str, str],
    languages: Sequence[str],
) -> None:
    for lang in languages:
        if lang == "en":
            # English lives on Lemma.lemma_text; no LemmaTranslation row.
            continue
        value = translations.get(lang)
        if not value:
            continue
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code=lang,
                translation=value,
            )
        )


def _insert_custom_lemma(session: Session, spec: _CustomLemma) -> Lemma:
    lemma = Lemma(
        guid=spec.guid,
        lemma_text=spec.lemma_text,
        pos_type=spec.pos_type,
        definition_text=spec.definition_text,
        disambiguation=spec.disambiguation or None,
    )
    session.add(lemma)
    session.flush()

    for lang, translation in spec.translations.items():
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code=lang,
                translation=translation,
            )
        )

    for lang, form_text, grammatical_form in spec.derivative_forms:
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                language_code=lang,
                derivative_form_text=form_text,
                grammatical_form=grammatical_form,
                is_base_form=(grammatical_form == "base"),
            )
        )

    return lemma


def build_test_engine() -> Engine:
    """Create an in-memory SQLite engine with the full schema applied."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def seed_test_database(session: Session) -> Dict[str, int]:
    """Seed the database with ~50 release lemmas + custom ambiguity lemmas.

    Returns a summary dict: {"release_lemmas": N, "custom_lemmas": M}.
    """
    release_count = 0
    for category, limit in _RELEASE_SLICES:
        for base_entry, secondary_entry in _iter_release_slice(category, limit):
            _insert_release_lemma(session, base_entry, secondary_entry)
            release_count += 1

    for spec in _CUSTOM_LEMMAS:
        _insert_custom_lemma(session, spec)

    session.commit()
    return {"release_lemmas": release_count, "custom_lemmas": len(_CUSTOM_LEMMAS)}


def add_test_sentence(
    session: Session,
    translations_by_language: Dict[str, str],
) -> Sentence:
    """Create a Sentence with SentenceTranslation rows for each provided language.

    Multi-language candidate lookup accepts sentences without an English
    translation; tests for that path call this fixture without an ``en`` entry.
    """
    if not translations_by_language:
        raise ValueError("translations_by_language must be non-empty")

    sentence = add_sentence(session, source_filename="candidate_lookup_fixture")
    for lang, text in translations_by_language.items():
        add_sentence_translation(
            session, sentence=sentence, language_code=lang, translation_text=text
        )
    session.flush()
    return sentence
