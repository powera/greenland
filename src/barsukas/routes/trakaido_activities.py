#!/usr/bin/python3

"""Trakaido interactive activities served by Barsukas.

Ports the "weird" Trakaido activities (spelling quiz, category choice,
sentence completion) into server-rendered pages using the Greenland UI
patterns.  No user state is persisted; a level dropdown on each page
selects which difficulty band to draw words from.
"""

import json
import random
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceWord,
)
from storage.translation_helpers import get_supported_languages

bp = Blueprint("trakaido_activities", __name__, url_prefix="/trakaido/activities")

DEFAULT_INTERFACE_LANG = "en"
DEFAULT_FOREIGN_LANG = "lt"
_QUESTIONS_PER_ROUND = 10
_LEVEL_EXPAND_RANGE = 2

CONFUSION_SETS: Dict[str, List[Dict[str, Any]]] = {
    "lt": [
        {"id": "fricatives", "options": ["s", "z", "š", "ž"]},
        {"id": "affricates", "options": ["c", "dz", "č", "dž"]},
        {"id": "diphthong-ie", "options": ["ie", "e", "ė", "i"]},
        {"id": "diphthong-uo", "options": ["uo", "o", "u", "ū"]},
        {"id": "e-variants", "options": ["e", "ė", "ę", "en"]},
        {"id": "u-long-nasal", "options": ["u", "ū", "ų", "un"]},
        {"id": "a-nasal", "options": ["a", "ą", "an", "am"]},
        {"id": "i-variants", "options": ["i", "į", "y", "j"]},
        {"id": "diphthongs", "options": ["ai", "ei", "au", "eu"]},
    ],
    "fr": [
        {"id": "accented-e", "options": ["e", "é", "è", "ê"]},
        {"id": "accented-a", "options": ["a", "à", "â"]},
        {"id": "nasals", "options": ["an", "en", "on", "in"]},
        {"id": "c-variants", "options": ["c", "ç", "ss", "s"]},
    ],
    "es": [
        {"id": "b-v", "options": ["b", "v"]},
        {"id": "accented-vowels", "options": ["a", "á", "e", "é"]},
        {"id": "n-variants", "options": ["n", "ñ"]},
        {"id": "ll-y", "options": ["ll", "y"]},
    ],
    "de": [
        {"id": "umlauts-a", "options": ["a", "ä"]},
        {"id": "umlauts-o", "options": ["o", "ö"]},
        {"id": "umlauts-u", "options": ["u", "ü"]},
        {"id": "ss-variants", "options": ["ss", "ß", "s"]},
    ],
}

CATEGORY_LABELS: Dict[str, str] = {
    "food": "Food",
    "beverage": "Beverages",
    "animal": "Animals",
    "body_part": "Body Parts",
    "clothing_accessory": "Clothing & Accessories",
    "building_structure": "Buildings & Structures",
    "building_part": "Parts of Buildings",
    "furniture": "Furniture",
    "tool": "Tools",
    "electronic_device": "Electronics",
    "plant": "Plants",
    "occupation": "Occupations",
    "family_relation": "Family & Relations",
    "small_movable_object": "Everyday Objects",
    "natural_feature": "Nature & Landscape",
    "vehicle": "Vehicles",
    "weapon": "Weapons",
    "sport": "Sports",
    "music": "Music",
}


def _parse_activity_params() -> Tuple[int, str, str]:
    """Read level and language params from the query string."""
    supported = set(get_supported_languages().keys())

    level_raw = request.args.get("level", "1")
    try:
        level = max(1, int(level_raw))
    except ValueError:
        level = 1

    interface_lang = (request.args.get("interface_lang") or DEFAULT_INTERFACE_LANG).strip().lower()
    foreign_lang = (request.args.get("foreign_lang") or DEFAULT_FOREIGN_LANG).strip().lower()

    if interface_lang not in supported:
        interface_lang = DEFAULT_INTERFACE_LANG
    if foreign_lang not in supported:
        foreign_lang = DEFAULT_FOREIGN_LANG

    return level, interface_lang, foreign_lang


def _available_levels() -> List[int]:
    """Return sorted list of difficulty levels that have at least one lemma."""
    rows = (
        g.db.query(Lemma.difficulty_level)
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(Lemma.difficulty_level > 0)
        .distinct()
        .order_by(Lemma.difficulty_level)
        .all()
    )
    return [row[0] for row in rows]


def _fetch_words_at_level(level: int, foreign_lang: str, limit: int = 40) -> List[Dict[str, Any]]:
    """Fetch lemmas near the given difficulty level with foreign translations."""
    rows = (
        g.db.query(Lemma, LemmaTranslation.translation)
        .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
        .filter(LemmaTranslation.language_code == foreign_lang)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(LemmaTranslation.translation != "")
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(
            Lemma.difficulty_level.between(
                max(1, level - _LEVEL_EXPAND_RANGE),
                level + _LEVEL_EXPAND_RANGE,
            )
        )
        .order_by(
            func.abs(Lemma.difficulty_level - level),
            func.random(),
        )
        .limit(limit)
        .all()
    )

    words: List[Dict[str, Any]] = []
    for lemma, translation in rows:
        words.append(
            {
                "id": lemma.id,
                "english": lemma.lemma_text,
                "definition": lemma.definition_text,
                "foreign": translation,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype,
                "level": lemma.difficulty_level,
            }
        )
    return words


# ---------------------------------------------------------------------------
# Spelling Quiz
# ---------------------------------------------------------------------------


def _is_vowel(char: str) -> bool:
    return char.lower() in "aeiouyąęėįųūéèêàâáíóúöüä"


def _breaks_vowel_sequence(word: str, start: int, end: int) -> bool:
    matched = word[start:end].lower()
    if len(matched) != 1 or not _is_vowel(matched):
        return False
    if start > 0 and _is_vowel(word[start - 1]):
        return True
    if end < len(word) and _is_vowel(word[end]):
        return True
    return False


def _find_confusion_positions(
    word: str, confusion_sets: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Find positions in *word* that match any confusion set option."""
    lower_word = word.lower()
    matches: List[Dict[str, Any]] = []

    for cset in confusion_sets:
        sorted_options = sorted(cset["options"], key=len, reverse=True)
        for option in sorted_options:
            search_from = 0
            while True:
                idx = lower_word.find(option.lower(), search_from)
                if idx == -1:
                    break
                opt_end = idx + len(option)
                overlaps = any(idx < m["end"] and opt_end > m["start"] for m in matches)
                breaks_seq = _breaks_vowel_sequence(lower_word, idx, opt_end)
                if not overlaps and not breaks_seq:
                    matches.append(
                        {
                            "start": idx,
                            "end": opt_end,
                            "options": cset["options"],
                            "matched": option,
                            "set_id": cset["id"],
                        }
                    )
                search_from = idx + 1

    matches.sort(key=lambda m: m["start"])
    return matches


def _build_spelling_questions(
    words: List[Dict[str, Any]], foreign_lang: str
) -> List[Dict[str, Any]]:
    """Generate spelling quiz questions from a word list."""
    csets = CONFUSION_SETS.get(foreign_lang, [])
    if not csets:
        return []

    questions: List[Dict[str, Any]] = []
    for word_data in words:
        foreign_word: str = word_data["foreign"]
        positions = _find_confusion_positions(foreign_word, csets)
        if not positions:
            continue

        pos = random.choice(positions)
        correct_answer = foreign_word[pos["start"] : pos["end"]]

        options_pool: List[str] = list(pos["options"])
        if len(options_pool) > 4:
            decoys = [o for o in options_pool if o.lower() != correct_answer.lower()]
            random.shuffle(decoys)
            final_options = [correct_answer.lower()] + decoys[:3]
        else:
            final_options = [o.lower() for o in options_pool]

        display_options = sorted(
            [o.upper() for o in final_options],
            key=lambda x: x.lower(),
        )

        questions.append(
            {
                "word": foreign_word,
                "english": word_data["english"],
                "definition": word_data["definition"],
                "blank_start": pos["start"],
                "blank_end": pos["end"],
                "correct_answer": correct_answer,
                "options": display_options,
            }
        )

        if len(questions) >= _QUESTIONS_PER_ROUND:
            break

    random.shuffle(questions)
    return questions


# ---------------------------------------------------------------------------
# Category Choice
# ---------------------------------------------------------------------------


def _build_category_questions(
    words: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate category-choice questions from a word list."""
    by_subtype: Dict[str, List[Dict[str, Any]]] = {}
    for w in words:
        sub = w.get("pos_subtype")
        if sub and sub in CATEGORY_LABELS:
            by_subtype.setdefault(sub, []).append(w)

    viable = [(sub, ws) for sub, ws in by_subtype.items() if len(ws) >= 1]
    if not viable:
        return []

    all_words = words
    questions: List[Dict[str, Any]] = []

    attempts = 0
    while len(questions) < _QUESTIONS_PER_ROUND and attempts < 50:
        attempts += 1
        sub, category_words = random.choice(viable)
        correct = random.choice(category_words)

        decoys = [
            w
            for w in all_words
            if w.get("pos_subtype") != sub and w["foreign"].lower() != correct["foreign"].lower()
        ]
        if len(decoys) < 3:
            continue

        random.shuffle(decoys)
        option_words = [correct] + decoys[:3]
        random.shuffle(option_words)

        questions.append(
            {
                "category": CATEGORY_LABELS[sub],
                "correct_foreign": correct["foreign"],
                "correct_english": correct["english"],
                "options": [
                    {
                        "foreign": o["foreign"],
                        "english": o["english"],
                        "correct": o["id"] == correct["id"],
                    }
                    for o in option_words
                ],
            }
        )

    return questions


# ---------------------------------------------------------------------------
# Sentence Completion
# ---------------------------------------------------------------------------


def _build_sentence_completion_questions(
    level: int, interface_lang: str, foreign_lang: str
) -> List[Dict[str, Any]]:
    """Generate sentence-completion questions."""
    content_roles = {"verb", "noun", "subject", "object", "adjective", "adverb"}

    sentence_rows = (
        g.db.query(Sentence)
        .join(SentenceWord, SentenceWord.sentence_id == Sentence.id)
        .join(Lemma, Lemma.id == SentenceWord.lemma_id)
        .filter(Sentence.rejected == False)  # noqa: E712
        .filter(SentenceWord.language_code == foreign_lang)
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(
            Lemma.difficulty_level.between(
                max(1, level - _LEVEL_EXPAND_RANGE),
                level + _LEVEL_EXPAND_RANGE,
            )
        )
        .distinct()
        .order_by(func.random())
        .limit(30)
        .all()
    )

    decoy_words_rows = (
        g.db.query(LemmaTranslation.translation)
        .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
        .filter(LemmaTranslation.language_code == foreign_lang)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(LemmaTranslation.translation != "")
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(
            Lemma.difficulty_level.between(
                max(1, level - _LEVEL_EXPAND_RANGE),
                level + _LEVEL_EXPAND_RANGE,
            )
        )
        .order_by(func.random())
        .limit(60)
        .all()
    )
    decoy_pool = [r[0] for r in decoy_words_rows if r[0]]

    questions: List[Dict[str, Any]] = []

    for sentence in sentence_rows:
        if len(questions) >= _QUESTIONS_PER_ROUND:
            break

        foreign_words_query = (
            g.db.query(SentenceWord)
            .filter(SentenceWord.sentence_id == sentence.id)
            .filter(SentenceWord.language_code == foreign_lang)
            .order_by(SentenceWord.position)
            .all()
        )
        interface_words_query = (
            g.db.query(SentenceWord)
            .filter(SentenceWord.sentence_id == sentence.id)
            .filter(SentenceWord.language_code == interface_lang)
            .order_by(SentenceWord.position)
            .all()
        )

        if not foreign_words_query or not interface_words_query:
            continue

        blankable = [
            w
            for w in foreign_words_query
            if w.word_role in content_roles
            and w.target_language_text
            and len(w.target_language_text) > 1
        ]
        if not blankable:
            continue

        target_word = random.choice(blankable)
        correct_text = target_word.target_language_text

        foreign_sentence = " ".join(w.target_language_text or "" for w in foreign_words_query)
        blanked_sentence = " ".join(
            "___" if w.position == target_word.position else (w.target_language_text or "")
            for w in foreign_words_query
        )
        interface_sentence = " ".join(w.target_language_text or "" for w in interface_words_query)

        decoys = [d for d in decoy_pool if d.lower() != correct_text.lower()]
        if len(decoys) < 3:
            continue

        random.shuffle(decoys)
        option_list = [correct_text] + decoys[:3]
        random.shuffle(option_list)

        questions.append(
            {
                "interface_sentence": interface_sentence,
                "foreign_sentence": foreign_sentence,
                "blanked_sentence": blanked_sentence,
                "correct_answer": correct_text,
                "blank_gloss": target_word.english_text or "",
                "options": [{"text": o, "correct": o == correct_text} for o in option_list],
            }
        )

    return questions


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _common_template_vars(level: int, interface_lang: str, foreign_lang: str) -> Dict[str, Any]:
    return {
        "level": level,
        "interface_lang": interface_lang,
        "foreign_lang": foreign_lang,
        "supported_languages": get_supported_languages(),
        "available_levels": _available_levels(),
    }


@bp.route("/")
def activities_index() -> ResponseReturnValue:
    """Landing page listing the available Trakaido activities."""
    return render_template("trakaido/activities/index.html")


@bp.route("/spelling-quiz")
def spelling_quiz() -> ResponseReturnValue:
    """Spelling quiz activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    words = _fetch_words_at_level(level, foreign_lang, limit=40)
    questions = _build_spelling_questions(words, foreign_lang)

    return render_template(
        "trakaido/activities/spelling_quiz.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


@bp.route("/category-choice")
def category_choice() -> ResponseReturnValue:
    """Category choice activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    words = _fetch_words_at_level(level, foreign_lang, limit=80)
    questions = _build_category_questions(words)

    return render_template(
        "trakaido/activities/category_choice.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


@bp.route("/sentence-completion")
def sentence_completion() -> ResponseReturnValue:
    """Sentence completion activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    questions = _build_sentence_completion_questions(level, interface_lang, foreign_lang)

    return render_template(
        "trakaido/activities/sentence_completion.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        **_common_template_vars(level, interface_lang, foreign_lang),
    )
