#!/usr/bin/python3

"""
Dictionary view routes (peleda - owl).

Provides a dense, print-dictionary-style browse of lemmas in any source
language with translations shown in three other languages.
"""

from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from barsukas.config import Config
from wordfreq.storage.models.schema import Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import LANGUAGE_NAMES

bp = Blueprint("peleda", __name__, url_prefix="/dictionary")

# Items per page for dictionary view (denser than default)
DICT_ITEMS_PER_PAGE = 200

# Languages available as a source (browsing) language.
# Order determines display in the dropdown.
DICTIONARY_SOURCE_LANGUAGES: List[Tuple[str, str]] = [
    ("en", "English"),
    ("lt", "Lithuanian"),
    ("zh", "Chinese"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("vi", "Vietnamese"),
]

# The pool of translation languages to display alongside headwords.
# For each source language, show 3 of these, skipping the source language
# itself (or French if the source language is not in this list).
DICTIONARY_DISPLAY_POOL = ["en", "zh", "lt", "fr"]


def _get_display_langs(source_lang: str) -> List[str]:
    """Return the 3 translation columns to show for a given source language."""
    if source_lang in DICTIONARY_DISPLAY_POOL:
        return [c for c in DICTIONARY_DISPLAY_POOL if c != source_lang]
    # Source language not in the pool: drop French to make room
    return [c for c in DICTIONARY_DISPLAY_POOL if c != "fr"]


def _get_alphabet(source_lang: str) -> List[str]:
    """Return the alphabet to use for the letter bar."""
    if source_lang in ("zh", "ja", "ko"):
        # CJK languages don't use a Latin alphabet for browsing.
        # We still allow letter-based browsing of the *pinyin / romaji*
        # initial, but a simple A-Z bar works as a reasonable default
        # (sorted by translation text which is in native script).
        return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


@bp.route("/")
def dictionary() -> ResponseReturnValue:
    """Dictionary browse view."""
    lang = request.args.get("lang", "en").strip().lower()
    letter = request.args.get("letter", "A").strip().upper()
    page = request.args.get("page", 1, type=int)

    # Validate language
    valid_codes = {code for code, _ in DICTIONARY_SOURCE_LANGUAGES}
    if lang not in valid_codes:
        lang = "en"

    display_langs = _get_display_langs(lang)
    alphabet = _get_alphabet(lang)

    if letter and len(letter) == 1 and letter.isalpha():
        pass  # valid
    else:
        letter = "A"

    # Build query for headwords starting with the chosen letter
    if lang == "en":
        # English: query Lemma.lemma_text directly
        base_query = (
            g.db.query(Lemma)
            .filter(
                Lemma.guid.isnot(None),
                func.upper(func.substr(Lemma.lemma_text, 1, 1)) == letter,
            )
            .order_by(func.lower(Lemma.lemma_text), Lemma.id)
        )
    else:
        # Other languages: join LemmaTranslation to get headword
        base_query = (
            g.db.query(Lemma)
            .join(
                LemmaTranslation,
                (LemmaTranslation.lemma_id == Lemma.id) & (LemmaTranslation.language_code == lang),
            )
            .filter(
                Lemma.guid.isnot(None),
                func.upper(func.substr(LemmaTranslation.translation, 1, 1)) == letter,
            )
            .order_by(func.lower(LemmaTranslation.translation), Lemma.id)
        )

    total = base_query.count()
    total_pages = max(1, (total + DICT_ITEMS_PER_PAGE - 1) // DICT_ITEMS_PER_PAGE)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    lemmas = base_query.limit(DICT_ITEMS_PER_PAGE).offset((page - 1) * DICT_ITEMS_PER_PAGE).all()

    # Bulk-fetch all needed translations in one query
    lemma_ids = [lm.id for lm in lemmas]
    needed_langs = set(display_langs)
    if lang != "en":
        needed_langs.add(lang)

    translations_map: Dict[int, Dict[str, Optional[str]]] = {lm.id: {} for lm in lemmas}
    if lemma_ids and needed_langs:
        rows = (
            g.db.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id.in_(lemma_ids),
                LemmaTranslation.language_code.in_(list(needed_langs)),
            )
            .all()
        )
        for r in rows:
            translations_map.setdefault(r.lemma_id, {})[r.language_code] = r.translation

    # Build entry dicts for template
    entries: List[Dict[str, Any]] = []
    for lm in lemmas:
        if lang == "en":
            headword = lm.lemma_text
        else:
            headword = translations_map.get(lm.id, {}).get(lang) or ""

        trans = translations_map.get(lm.id, {})
        # English is always from lemma_text
        trans["en"] = lm.lemma_text

        entries.append(
            {
                "id": lm.id,
                "headword": headword,
                "disambiguation": lm.disambiguation,
                "pos_type": lm.pos_type,
                "translations": trans,
            }
        )

    # Determine which letters have entries (for greying out empty ones)
    available_letters = _available_letters(lang)

    return render_template(
        "dictionary/index.html",
        lang=lang,
        letter=letter,
        page=page,
        total=total,
        total_pages=total_pages,
        entries=entries,
        display_langs=display_langs,
        alphabet=alphabet,
        available_letters=available_letters,
        available_languages=DICTIONARY_SOURCE_LANGUAGES,
        language_names=LANGUAGE_NAMES,
    )


def _available_letters(lang: str) -> set[str]:
    """Return the set of uppercase first-letters that have at least one entry."""
    if lang == "en":
        rows = (
            g.db.query(func.upper(func.substr(Lemma.lemma_text, 1, 1)))
            .filter(Lemma.guid.isnot(None))
            .distinct()
            .all()
        )
    else:
        rows = (
            g.db.query(func.upper(func.substr(LemmaTranslation.translation, 1, 1)))
            .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
            .filter(
                LemmaTranslation.language_code == lang,
                Lemma.guid.isnot(None),
            )
            .distinct()
            .all()
        )
    return {r[0] for r in rows if r[0] and r[0].isalpha()}
