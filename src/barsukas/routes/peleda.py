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

from barsukas.helpers.strings import load_barsukas_strings
from barsukas.routes.categories import (
    ADJECTIVE_GROUPS,
    ADVERB_GROUPS,
    NOUN_GROUPS,
    SUBTYPE_DESCRIPTIONS,
    VERB_GROUPS,
)
from langtools.collation import LATIN_SORT_KEY_LANGUAGES
from langtools.ja.gojuon import KANA_TO_ROW, ROW_INITIALS, ROW_MEMBERS
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import LANGUAGE_NAMES

bp = Blueprint("peleda", __name__, url_prefix="/dictionary")

# Items per page for dictionary view (denser than default)
DICT_ITEMS_PER_PAGE = 200

# Languages available as a source (browsing) language.
# Order determines display in the dropdown.
DICTIONARY_SOURCE_LANGUAGES: List[str] = [
    "en",
    "lt",
    "zh",
    "fr",
    "es",
    "de",
    "it",
    "pt",
    "ja",
    "ko",
    "vi",
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

# CJK languages whose alphabet bar filters on sort_key rather than translation.
_CJK_SORT_KEY_LANGUAGES = frozenset({"zh", "ja", "ko"})

# All languages that use sort_key for ORDER BY (CJK + accented Latin).
_SORT_KEY_LANGUAGES = _CJK_SORT_KEY_LANGUAGES | LATIN_SORT_KEY_LANGUAGES

# Groups for building the category dropdown, keyed by POS type.
_POS_SUBTYPE_GROUPS: Dict[str, Dict[str, List[str]]] = {
    "noun": NOUN_GROUPS,
    "verb": VERB_GROUPS,
    "adjective": ADJECTIVE_GROUPS,
    "adverb": ADVERB_GROUPS,
    "numeral": {"Numerals": ["cardinal", "ordinal"]},
}


def _get_display_langs(source_lang: str) -> List[str]:
    """Return the 3 translation columns to show for a given source language."""
    if source_lang in DICTIONARY_DISPLAY_POOL:
        return [c for c in DICTIONARY_DISPLAY_POOL if c != source_lang]
    return [c for c in DICTIONARY_DISPLAY_POOL if c != "fr"]


def _get_alphabet(source_lang: str) -> List[str]:
    """Return the alphabet to use for the letter bar."""
    return LANGUAGE_ALPHABETS.get(source_lang, list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))


def _localized_language_names(ui_lang: str) -> Dict[str, str]:
    """Return language names in the selected UI language with English fallback."""
    strings = load_barsukas_strings(namespace="languages", ui_lang=ui_lang)
    result: Dict[str, str] = {}
    for code in DICTIONARY_SOURCE_LANGUAGES:
        result[code] = strings.get(code, LANGUAGE_NAMES.get(code, code))
    for code in DICTIONARY_DISPLAY_POOL:
        if code not in result:
            result[code] = strings.get(code, LANGUAGE_NAMES.get(code, code))
    return result


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
    if lang == "en":
        letter_variants = [letter.upper(), letter.lower()]
        return (
            _base_query_for_lang(lang)
            .filter(func.substr(Lemma.lemma_text, 1, 1).in_(letter_variants))
            .order_by(func.lower(Lemma.lemma_text), Lemma.id)
        )

    if lang in _CJK_SORT_KEY_LANGUAGES:
        # CJK: filter and order on sort_key.
        q = _base_query_for_lang(lang).filter(
            LemmaTranslation.sort_key.isnot(None),
        )
        if lang == "ja":
            row_kana = ROW_MEMBERS.get(letter, [letter])
            q = q.filter(func.substr(LemmaTranslation.sort_key, 1, 1).in_(row_kana))
        elif lang == "ko":
            q = q.filter(func.substr(LemmaTranslation.sort_key, 1, 1) == letter)
        else:  # zh
            q = q.filter(
                func.substr(LemmaTranslation.sort_key, 1, 1).in_([letter.upper(), letter.lower()])
            )
        return q.order_by(LemmaTranslation.sort_key, Lemma.id)

    # Latin-alphabet languages: filter on translation text, order on sort_key
    # when available (accented languages), otherwise on lowered translation.
    letter_variants = [letter.upper(), letter.lower()]
    q = _base_query_for_lang(lang).filter(
        func.substr(LemmaTranslation.translation, 1, 1).in_(letter_variants)
    )
    if lang in LATIN_SORT_KEY_LANGUAGES:
        return q.order_by(LemmaTranslation.sort_key, Lemma.id)
    return q.order_by(func.lower(LemmaTranslation.translation), Lemma.id)


def _query_by_level(lang: str, level: int) -> Query:  # type: ignore[type-arg]
    """Query filtered to a single difficulty level."""
    q = _base_query_for_lang(lang).filter(Lemma.difficulty_level == level)
    if lang == "en":
        return q.order_by(func.lower(Lemma.lemma_text), Lemma.id)
    if lang in _SORT_KEY_LANGUAGES:
        return q.order_by(LemmaTranslation.sort_key, Lemma.id)
    return q.order_by(func.lower(LemmaTranslation.translation), Lemma.id)


def _query_by_category(
    lang: str, pos_type: str, pos_subtype: str
) -> Query:  # type: ignore[type-arg]
    """Query filtered to a single POS category (type + subtype)."""
    q = _base_query_for_lang(lang).filter(
        Lemma.pos_type == pos_type,
        Lemma.pos_subtype == pos_subtype,
    )
    if lang == "en":
        return q.order_by(func.lower(Lemma.lemma_text), Lemma.id)
    if lang in _SORT_KEY_LANGUAGES:
        return q.order_by(LemmaTranslation.sort_key, Lemma.id)
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

    if lang in _CJK_SORT_KEY_LANGUAGES:
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

        # Korean jamo — direct match.
        return raw_initials

    # Latin-alphabet languages (including those with sort keys).
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


def _available_categories() -> set[Tuple[str, str]]:
    """Return the set of (pos_type, pos_subtype) pairs that have entries."""
    rows = (
        g.db.query(Lemma.pos_type, Lemma.pos_subtype)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.pos_type.isnot(None),
            Lemma.pos_subtype.isnot(None),
        )
        .distinct()
        .all()
    )
    return {(r[0], r[1]) for r in rows}


def _build_category_options(available: set[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Build a grouped list of category options for the dropdown.

    Returns a list of dicts, each with:
      - pos_type: POS type key (e.g. "noun")
      - label: Display label for the optgroup (e.g. "Nouns")
      - items: list of dicts with value, display_name, description
    """
    result: List[Dict[str, Any]] = []
    for pos_type in ("noun", "verb", "adjective", "adverb", "numeral"):
        groups = _POS_SUBTYPE_GROUPS.get(pos_type, {})
        descriptions = SUBTYPE_DESCRIPTIONS.get(pos_type, {})
        items: List[Dict[str, str]] = []
        for _group_name, subtypes in groups.items():
            for subtype in subtypes:
                if (pos_type, subtype) in available:
                    items.append(
                        {
                            "value": f"{pos_type}:{subtype}",
                            "display_name": subtype.replace("_", " ").title(),
                            "description": descriptions.get(subtype, ""),
                        }
                    )
        if items:
            result.append(
                {
                    "pos_type": pos_type,
                    "items": items,
                }
            )
    return result


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


@bp.route("/")
def dictionary() -> ResponseReturnValue:
    """Dictionary browse view."""
    lang = request.args.get("lang", "en").strip().lower()
    sort = request.args.get("sort", "alpha").strip().lower()
    ui_lang = getattr(g, "ui_lang", "en")
    page = request.args.get("page", 1, type=int)

    # Validate inputs.
    valid_codes = set(DICTIONARY_SOURCE_LANGUAGES)
    if lang not in valid_codes:
        lang = "en"
    if sort not in ("alpha", "level", "category"):
        sort = "alpha"
    display_langs = _get_display_langs(lang)
    alphabet = _get_alphabet(lang)

    # --- Build query based on sort mode ---

    # Defaults for template vars that only apply to specific modes.
    selected_level: Optional[int] = None
    level_list: List[int] = []
    letter = alphabet[0] if alphabet else "A"
    available_letters: set[str] = set()
    category_options: List[Dict[str, Any]] = []
    selected_category: Optional[str] = None

    if sort == "category":
        available = _available_categories()
        category_options = _build_category_options(available)
        selected_category = request.args.get("category", "").strip()

        # Validate selected_category is a real option.
        all_values = {item["value"] for group in category_options for item in group["items"]}
        if selected_category not in all_values:
            # Default to the first available category.
            selected_category = category_options[0]["items"][0]["value"] if category_options else ""

        if ":" in selected_category:
            cat_pos_type, cat_subtype = selected_category.split(":", 1)
            base_query = _query_by_category(lang, cat_pos_type, cat_subtype)
        else:
            # Fallback: show nothing if no categories exist.
            base_query = _base_query_for_lang(lang).filter(Lemma.id < 0)

    elif sort == "level":
        available_levels = _available_levels()
        selected_level = request.args.get("level", None, type=int)
        if selected_level not in available_levels:
            selected_level = min(available_levels) if available_levels else 1
        level_list = sorted(available_levels)

        base_query = _query_by_level(lang, selected_level)
    else:
        letter = request.args.get("letter", "").strip()
        if lang not in _CJK_SORT_KEY_LANGUAGES:
            letter = letter.upper()
        if not (len(letter) == 1 and letter in alphabet):
            letter = alphabet[0] if alphabet else "A"

        base_query = _query_by_letter(lang, letter)
        available_letters = _available_letters(lang)

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
        for row in rows:
            translations_map.setdefault(row.lemma_id, {})[row.language_code] = row.translation

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

    language_names = _localized_language_names(ui_lang)
    available_languages: List[Tuple[str, str]] = [
        (code, language_names.get(code, LANGUAGE_NAMES.get(code, code)))
        for code in DICTIONARY_SOURCE_LANGUAGES
    ]

    return render_template(
        "dictionary/index.html",
        lang=lang,
        ui_lang=ui_lang,
        letter=letter,
        sort=sort,
        selected_level=selected_level,
        level_list=level_list,
        selected_category=selected_category,
        category_options=category_options,
        page=page,
        total=total,
        total_pages=total_pages,
        entries=entries,
        display_langs=display_langs,
        alphabet=alphabet,
        available_letters=available_letters,
        available_languages=available_languages,
        language_names=language_names,
    )
