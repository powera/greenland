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
from sqlalchemy.orm import Query

from langtools.ja.gojuon import KANA_TO_ROW, ROW_INITIALS, ROW_MEMBERS
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

# Language-specific alphabets.
# CJK languages use sort_key for filtering: pinyin initials for zh,
# hiragana gojūon groups for ja, jamo consonants for ko.
LANGUAGE_ALPHABETS: Dict[str, List[str]] = {
    "lt": list("AĄBCČDEĘĖFGHIĮYJKLMNOPRSŠTUŲŪVZŽ"),
    "zh": list("ABCDEFGHJKLMNOPQRSTWXYZ"),  # pinyin initials (no I/U/V alone)
    "ja": ROW_INITIALS,  # 10 gojūon row initials
    "ko": list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"),  # 19 choseong (SK order)
    "de": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["Ä", "Ö", "Ü"],
    "es": list("ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"),
    "fr": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["É", "È"],
    "it": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "pt": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["Ã", "Ç", "Õ"],
    "sv": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["Å", "Ä", "Ö"],
    "vi": list("AĂÂBCDĐEÊGHIKLMNOÔƠPQRSTUƯVXY"),
}

# Languages whose alphabet bar filters on sort_key rather than translation.
_SORT_KEY_LANGUAGES = frozenset({"zh", "ja", "ko"})


def _get_display_langs(source_lang: str) -> List[str]:
    """Return the 3 translation columns to show for a given source language."""
    if source_lang in DICTIONARY_DISPLAY_POOL:
        return [c for c in DICTIONARY_DISPLAY_POOL if c != source_lang]
    return [c for c in DICTIONARY_DISPLAY_POOL if c != "fr"]


def _get_alphabet(source_lang: str) -> List[str]:
    """Return the alphabet to use for the letter bar."""
    return LANGUAGE_ALPHABETS.get(source_lang, list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def _base_query_for_lang(lang: str) -> Query:  # type: ignore[type-arg]
    """Return a base Lemma query joined to LemmaTranslation when needed."""
    if lang == "en":
        return g.db.query(Lemma).filter(Lemma.guid.isnot(None))  # type: ignore[no-any-return]
    return (  # type: ignore[no-any-return]
        g.db.query(Lemma)
        .join(
            LemmaTranslation,
            (LemmaTranslation.lemma_id == Lemma.id) & (LemmaTranslation.language_code == lang),
        )
        .filter(Lemma.guid.isnot(None))
    )


def _query_by_letter(lang: str, letter: str) -> Query:  # type: ignore[type-arg]
    """Alphabetical query filtered by first letter."""
    if lang in _SORT_KEY_LANGUAGES:
        q = _base_query_for_lang(lang).filter(
            LemmaTranslation.sort_key.isnot(None),
        )
        if lang == "ja":
            # Match all kana in this gojūon row (including voiced variants).
            row_kana = ROW_MEMBERS.get(letter, [letter])
            q = q.filter(func.substr(LemmaTranslation.sort_key, 1, 1).in_(row_kana))
        elif lang == "ko":
            q = q.filter(func.substr(LemmaTranslation.sort_key, 1, 1) == letter)
        else:  # zh
            q = q.filter(
                func.substr(LemmaTranslation.sort_key, 1, 1).in_([letter.upper(), letter.lower()])
            )
        return q.order_by(LemmaTranslation.sort_key, Lemma.id)

    # Latin-alphabet languages.
    letter_variants = [letter.upper(), letter.lower()]
    if lang == "en":
        return (
            _base_query_for_lang(lang)
            .filter(func.substr(Lemma.lemma_text, 1, 1).in_(letter_variants))
            .order_by(func.lower(Lemma.lemma_text), Lemma.id)
        )
    return (
        _base_query_for_lang(lang)
        .filter(func.substr(LemmaTranslation.translation, 1, 1).in_(letter_variants))
        .order_by(func.lower(LemmaTranslation.translation), Lemma.id)
    )


def _query_by_level(lang: str, level: int) -> Query:  # type: ignore[type-arg]
    """Query filtered to a single difficulty level."""
    q = _base_query_for_lang(lang).filter(Lemma.difficulty_level == level)
    if lang == "en":
        return q.order_by(func.lower(Lemma.lemma_text), Lemma.id)
    return q.order_by(func.lower(LemmaTranslation.translation), Lemma.id)


# ---------------------------------------------------------------------------
# Available-item helpers (for navigation bars)
# ---------------------------------------------------------------------------


def _available_letters(lang: str) -> set[str]:
    """Return the set of alphabet-bar letters that have at least one entry.

    For CJK languages this queries the sort_key column; for others it uses
    the first character of the translation text.  SQLite upper() only handles
    ASCII, so we uppercase in Python for accented Latin characters.
    """
    if lang == "en":
        rows = (
            g.db.query(func.substr(Lemma.lemma_text, 1, 1))
            .filter(Lemma.guid.isnot(None))
            .distinct()
            .all()
        )
        return {r[0].upper() for r in rows if r[0] and r[0].isalpha()}

    if lang in _SORT_KEY_LANGUAGES:
        rows = (
            g.db.query(func.substr(LemmaTranslation.sort_key, 1, 1))
            .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
            .filter(
                LemmaTranslation.language_code == lang,
                LemmaTranslation.sort_key.isnot(None),
                Lemma.guid.isnot(None),
            )
            .distinct()
            .all()
        )
        raw_initials = {r[0] for r in rows if r[0]}

        if lang == "ja":
            # Map voiced/semi-voiced kana back to their gojūon row initial.
            return {KANA_TO_ROW.get(c, c) for c in raw_initials}
        elif lang == "zh":
            return {c.upper() for c in raw_initials if c.isalpha()}
        else:
            # Korean jamo — direct match.
            return raw_initials

    # Latin-alphabet languages.
    rows = (
        g.db.query(func.substr(LemmaTranslation.translation, 1, 1))
        .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
        .filter(
            LemmaTranslation.language_code == lang,
            Lemma.guid.isnot(None),
        )
        .distinct()
        .all()
    )
    return {r[0].upper() for r in rows if r[0] and r[0].isalpha()}


def _available_levels() -> set[int]:
    """Return the set of difficulty levels that have at least one entry."""
    rows = (
        g.db.query(Lemma.difficulty_level)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.difficulty_level.isnot(None),
            Lemma.difficulty_level >= 0,
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


@bp.route("/")
def dictionary() -> ResponseReturnValue:
    """Dictionary browse view."""
    lang = request.args.get("lang", "en").strip().lower()
    sort = request.args.get("sort", "alpha").strip().lower()
    page = request.args.get("page", 1, type=int)

    # Validate inputs.
    valid_codes = {code for code, _ in DICTIONARY_SOURCE_LANGUAGES}
    if lang not in valid_codes:
        lang = "en"
    if sort not in ("alpha", "level"):
        sort = "alpha"

    display_langs = _get_display_langs(lang)
    alphabet = _get_alphabet(lang)

    # --- Build query based on sort mode ---

    if sort == "level":
        available_levels = _available_levels()
        selected_level = request.args.get("level", None, type=int)
        if selected_level not in available_levels:
            selected_level = min(available_levels) if available_levels else 1
        level_list = sorted(available_levels)

        base_query = _query_by_level(lang, selected_level)

        # Template vars specific to level mode.
        letter = alphabet[0] if alphabet else "A"
        available_letters: set[str] = set()
    else:
        letter = request.args.get("letter", "").strip()
        if lang not in _SORT_KEY_LANGUAGES:
            letter = letter.upper()
        if not (len(letter) == 1 and letter in alphabet):
            letter = alphabet[0] if alphabet else "A"

        base_query = _query_by_letter(lang, letter)
        available_letters = _available_letters(lang)

        # Template vars specific to alpha mode.
        selected_level = None
        level_list = []

    # --- Paginate ---

    total = base_query.count()
    total_pages = max(1, (total + DICT_ITEMS_PER_PAGE - 1) // DICT_ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))

    lemmas = base_query.limit(DICT_ITEMS_PER_PAGE).offset((page - 1) * DICT_ITEMS_PER_PAGE).all()

    # --- Bulk-fetch translations ---

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

    # --- Build entry dicts for template ---

    entries: List[Dict[str, Any]] = []
    for lm in lemmas:
        headword = (
            lm.lemma_text if lang == "en" else (translations_map.get(lm.id, {}).get(lang) or "")
        )
        trans = translations_map.get(lm.id, {})
        trans["en"] = lm.lemma_text

        entries.append(
            {
                "id": lm.id,
                "headword": headword,
                "disambiguation": lm.disambiguation,
                "pos_type": lm.pos_type,
                "difficulty_level": lm.difficulty_level,
                "translations": trans,
            }
        )

    return render_template(
        "dictionary/index.html",
        lang=lang,
        letter=letter,
        sort=sort,
        selected_level=selected_level,
        level_list=level_list,
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
