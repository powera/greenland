#!/usr/bin/python3

"""Trakaido interactive activities served by Barsukas.

Ports the Trakaido web activities (spelling quiz, category choice,
sentence completion, multiple choice, listening, flashcards, typing,
verb forms) into server-rendered pages using the Greenland UI patterns.
No user state is persisted server-side; a level dropdown on each page
selects the difficulty ceiling to draw words from.  Words below the
selected level are still quizzed, but with exponentially decreasing
frequency the further below the level they sit.
"""

import json
import random
from typing import Any, Dict, List, Optional, Tuple, cast

from flask import Blueprint, g, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from storage.models.grammar_fact import GrammarFact
from storage.models.schema import (
    AudioQualityReview,
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

# Level weighting: the selected level is the ceiling.  Each level below the
# selected one is _LEVEL_DECAY times as likely to be drawn as the level above
# it, with a floor so long-learned words still show up occasionally.
_LEVEL_DECAY = 0.5
_LEVEL_WEIGHT_FLOOR = 0.05
_POOL_FETCH_CAP = 400

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


def _level_weight(selected_level: int, item_level: int) -> float:
    """Relative draw weight for an item at *item_level* when quizzing *selected_level*."""
    return max(_LEVEL_WEIGHT_FLOOR, _LEVEL_DECAY ** (selected_level - item_level))


def _weighted_sample_by_level(
    items: List[Dict[str, Any]], selected_level: int, count: int
) -> List[Dict[str, Any]]:
    """Sample up to *count* items, favoring the selected level.

    Each item must carry a ``level`` key.  The selected level gets the
    highest draw weight; each level below it is exponentially less likely.
    Items are drawn without replacement, so if the preferred levels run
    out the remaining slots fall through to whatever is left.
    """
    by_level: Dict[int, List[Dict[str, Any]]] = {}
    for item in items:
        by_level.setdefault(int(item["level"]), []).append(item)
    for bucket in by_level.values():
        random.shuffle(bucket)

    picked: List[Dict[str, Any]] = []
    while len(picked) < count and by_level:
        levels = list(by_level.keys())
        weights = [_level_weight(selected_level, lvl) for lvl in levels]
        chosen_level = random.choices(levels, weights=weights, k=1)[0]
        bucket = by_level[chosen_level]
        picked.append(bucket.pop())
        if not bucket:
            del by_level[chosen_level]

    random.shuffle(picked)
    return picked


def _fetch_words_at_level(level: int, foreign_lang: str, limit: int = 40) -> List[Dict[str, Any]]:
    """Fetch lemmas at or below the given difficulty level with foreign translations.

    The selected level is a ceiling: words above it never appear, and words
    below it are included with exponentially decreasing frequency the further
    below the level they sit (see _weighted_sample_by_level).
    """
    rows = (
        g.db.query(Lemma, LemmaTranslation.translation)
        .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
        .filter(LemmaTranslation.language_code == foreign_lang)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(LemmaTranslation.translation != "")
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(Lemma.difficulty_level.between(1, level))
        .order_by(func.random())
        .limit(_POOL_FETCH_CAP)
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
    return _weighted_sample_by_level(words, level, limit)


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

    # A sentence's level is the hardest word it contains; only sentences whose
    # hardest word is at or below the selected level qualify, and easier
    # sentences are drawn less often via the shared level weighting.
    sentence_rows = (
        g.db.query(Sentence, func.max(Lemma.difficulty_level).label("sentence_level"))
        .join(SentenceWord, SentenceWord.sentence_id == Sentence.id)
        .join(Lemma, Lemma.id == SentenceWord.lemma_id)
        .filter(Sentence.rejected == False)  # noqa: E712
        .filter(SentenceWord.language_code == foreign_lang)
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(Lemma.difficulty_level >= 1)
        .group_by(Sentence.id)
        .having(func.max(Lemma.difficulty_level) <= level)
        .order_by(func.random())
        .limit(120)
        .all()
    )
    sentence_items: List[Dict[str, Any]] = [
        {"sentence": sentence, "level": sentence_level}
        for sentence, sentence_level in sentence_rows
    ]
    sampled_sentences = _weighted_sample_by_level(sentence_items, level, 30)

    decoy_words_rows = (
        g.db.query(LemmaTranslation.translation)
        .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
        .filter(LemmaTranslation.language_code == foreign_lang)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(LemmaTranslation.translation != "")
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(Lemma.difficulty_level.between(1, level))
        .order_by(func.random())
        .limit(60)
        .all()
    )
    decoy_pool = [r[0] for r in decoy_words_rows if r[0]]

    questions: List[Dict[str, Any]] = []

    for sentence_item in sampled_sentences:
        sentence = sentence_item["sentence"]
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
# Multiple Choice
# ---------------------------------------------------------------------------

_STUDY_MODES = ["target-to-source", "source-to-target"]


def _build_multiple_choice_questions(
    words: List[Dict[str, Any]], study_mode: str
) -> List[Dict[str, Any]]:
    """Generate multiple-choice translation questions.

    study_mode:
      - "target-to-source": show foreign word, pick the English meaning
      - "source-to-target": show English word, pick the foreign translation
    """
    if len(words) < 4:
        return []

    questions: List[Dict[str, Any]] = []
    random.shuffle(words)

    for word_data in words:
        if len(questions) >= _QUESTIONS_PER_ROUND:
            break

        decoys = [
            w
            for w in words
            if w["id"] != word_data["id"]
            and w["foreign"].lower() != word_data["foreign"].lower()
            and w["english"].lower() != word_data["english"].lower()
        ]
        if len(decoys) < 3:
            continue

        random.shuffle(decoys)
        option_words = [word_data] + decoys[:3]
        random.shuffle(option_words)

        if study_mode == "source-to-target":
            prompt_text = word_data["english"]
            prompt_sub = word_data["definition"] or ""
            options = [
                {"text": o["foreign"], "correct": o["id"] == word_data["id"]} for o in option_words
            ]
            correct_display = word_data["foreign"]
        else:
            prompt_text = word_data["foreign"]
            prompt_sub = ""
            options = [
                {"text": o["english"], "correct": o["id"] == word_data["id"]} for o in option_words
            ]
            correct_display = word_data["english"]

        questions.append(
            {
                "prompt": prompt_text,
                "prompt_sub": prompt_sub,
                "correct_answer": correct_display,
                "options": options,
            }
        )

    return questions


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------


def _build_flashcard_questions(
    words: List[Dict[str, Any]], study_mode: str
) -> List[Dict[str, Any]]:
    """Generate self-graded flashcards from a word list.

    study_mode:
      - "target-to-source": show foreign word, reveal the English meaning
      - "source-to-target": show English word, reveal the foreign translation
    """
    cards: List[Dict[str, Any]] = []
    for word_data in words:
        if study_mode == "target-to-source":
            front = word_data["foreign"]
            front_sub = ""
            back = word_data["english"]
            back_sub = word_data["definition"] or ""
        else:
            front = word_data["english"]
            front_sub = word_data["definition"] or ""
            back = word_data["foreign"]
            back_sub = ""

        cards.append(
            {
                "front": front,
                "front_sub": front_sub,
                "back": back,
                "back_sub": back_sub,
            }
        )
        if len(cards) >= _QUESTIONS_PER_ROUND:
            break
    return cards


# ---------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------


def _build_typing_questions(words: List[Dict[str, Any]], study_mode: str) -> List[Dict[str, Any]]:
    """Generate typing questions: show a word, type its translation.

    study_mode:
      - "source-to-target": show English word, type the foreign translation
      - "target-to-source": show foreign word, type the English meaning
    """
    questions: List[Dict[str, Any]] = []
    for word_data in words:
        if study_mode == "target-to-source":
            prompt = word_data["foreign"]
            prompt_sub = ""
            answer = word_data["english"]
        else:
            prompt = word_data["english"]
            prompt_sub = word_data["definition"] or ""
            answer = word_data["foreign"]

        questions.append(
            {
                "prompt": prompt,
                "prompt_sub": prompt_sub,
                "answer": answer,
            }
        )
        if len(questions) >= _QUESTIONS_PER_ROUND:
            break
    return questions


# ---------------------------------------------------------------------------
# Verb Forms
# ---------------------------------------------------------------------------

_VERB_FORM_LABELS: Dict[str, str] = {
    "3s_present": "he / she / it — present tense",
    "3s_past": "he / she / it — past tense",
}


def _fetch_verbs_with_forms(level: int, foreign_lang: str) -> List[Dict[str, Any]]:
    """Fetch verb lemmas at or below *level* that have conjugation grammar facts."""
    fact_types = list(_VERB_FORM_LABELS.keys()) + ["infinitive"]
    rows = (
        g.db.query(GrammarFact, Lemma)
        .join(Lemma, Lemma.id == GrammarFact.lemma_id)
        .filter(GrammarFact.language_code == foreign_lang)
        .filter(GrammarFact.fact_type.in_(fact_types))
        .filter(GrammarFact.fact_value.isnot(None))
        .filter(GrammarFact.fact_value != "")
        .filter(Lemma.difficulty_level.isnot(None))
        .filter(Lemma.difficulty_level.between(1, level))
        .all()
    )

    by_lemma: Dict[int, Dict[str, Any]] = {}
    for fact, lemma in rows:
        entry = by_lemma.setdefault(
            lemma.id,
            {
                "id": lemma.id,
                "english": lemma.lemma_text,
                "definition": lemma.definition_text,
                "level": lemma.difficulty_level,
                "facts": {},
            },
        )
        entry["facts"][fact.fact_type] = fact.fact_value

    return [
        verb
        for verb in by_lemma.values()
        if any(ftype in verb["facts"] for ftype in _VERB_FORM_LABELS)
    ]


def _build_verb_form_questions(verbs: List[Dict[str, Any]], level: int) -> List[Dict[str, Any]]:
    """Generate conjugation questions: pick the correct verb form."""
    if len(verbs) < 4:
        return []

    sampled = _weighted_sample_by_level(verbs, level, _QUESTIONS_PER_ROUND)
    questions: List[Dict[str, Any]] = []

    for verb in sampled:
        available_forms = [ftype for ftype in _VERB_FORM_LABELS if ftype in verb["facts"]]
        if not available_forms:
            continue
        form_type = random.choice(available_forms)
        correct_text: str = verb["facts"][form_type]

        decoys = [
            v["facts"][form_type]
            for v in verbs
            if v["id"] != verb["id"]
            and form_type in v["facts"]
            and v["facts"][form_type].lower() != correct_text.lower()
        ]
        decoys = list(dict.fromkeys(decoys))
        if len(decoys) < 3:
            continue

        random.shuffle(decoys)
        option_list = [correct_text] + decoys[:3]
        random.shuffle(option_list)

        questions.append(
            {
                "english": verb["english"],
                "definition": verb["definition"] or "",
                "infinitive": verb["facts"].get("infinitive", ""),
                "form_label": _VERB_FORM_LABELS[form_type],
                "correct_answer": correct_text,
                "options": [{"text": o, "correct": o == correct_text} for o in option_list],
            }
        )

    return questions


# ---------------------------------------------------------------------------
# Listening
# ---------------------------------------------------------------------------

_AUDIO_STATUS_PRIORITY: Dict[str, int] = {
    "approved": 0,
    "approved_with_issues": 1,
    "pending_review": 2,
    "needs_replacement": 3,
}


def _pick_lemma_audio(lemma_id: int, language_code: str) -> Optional[AudioQualityReview]:
    """Return the best available lemma audio review, or None."""
    reviews = (
        g.db.query(AudioQualityReview)
        .filter(AudioQualityReview.lemma_id == lemma_id)
        .filter(AudioQualityReview.language_code == language_code)
        .filter(AudioQualityReview.sentence_id.is_(None))
        .all()
    )
    if not reviews:
        return None
    reviews.sort(key=lambda r: (_AUDIO_STATUS_PRIORITY.get(r.status, 99), r.id))
    return cast(AudioQualityReview, reviews[0])


def _build_listening_questions(
    words: List[Dict[str, Any]], foreign_lang: str, study_mode: str
) -> List[Dict[str, Any]]:
    """Generate listening quiz questions — only words with audio."""
    if len(words) < 4:
        return []

    words_with_audio: List[Dict[str, Any]] = []
    for word_data in words:
        audio = _pick_lemma_audio(word_data["id"], foreign_lang)
        if audio is not None:
            word_data_copy = dict(word_data)
            word_data_copy["audio_url"] = url_for(
                "audio.serve_audio_file",
                language=audio.language_code,
                voice=audio.voice_name,
                filename=audio.filename,
            )
            words_with_audio.append(word_data_copy)

    if len(words_with_audio) < 4:
        return []

    questions: List[Dict[str, Any]] = []
    random.shuffle(words_with_audio)

    for word_data in words_with_audio:
        if len(questions) >= _QUESTIONS_PER_ROUND:
            break

        decoys = [
            w
            for w in words_with_audio
            if w["id"] != word_data["id"]
            and w["foreign"].lower() != word_data["foreign"].lower()
            and w["english"].lower() != word_data["english"].lower()
        ]
        if len(decoys) < 3:
            continue

        random.shuffle(decoys)
        option_words = [word_data] + decoys[:3]
        random.shuffle(option_words)

        if study_mode == "target-to-target":
            options = [
                {"text": o["foreign"], "correct": o["id"] == word_data["id"]} for o in option_words
            ]
            correct_display = word_data["foreign"]
        else:
            options = [
                {"text": o["english"], "correct": o["id"] == word_data["id"]} for o in option_words
            ]
            correct_display = word_data["english"]

        questions.append(
            {
                "audio_url": word_data["audio_url"],
                "correct_answer": correct_display,
                "target_word": word_data["foreign"],
                "options": options,
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


@bp.route("/multiple-choice")
def multiple_choice() -> ResponseReturnValue:
    """Multiple choice translation activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    study_mode = request.args.get("study_mode", "target-to-source")
    if study_mode not in _STUDY_MODES:
        study_mode = "target-to-source"

    words = _fetch_words_at_level(level, foreign_lang, limit=40)
    questions = _build_multiple_choice_questions(words, study_mode)

    return render_template(
        "trakaido/activities/multiple_choice.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        study_mode=study_mode,
        study_modes=_STUDY_MODES,
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


@bp.route("/flashcards")
def flashcards() -> ResponseReturnValue:
    """Self-graded flashcard activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    study_mode = request.args.get("study_mode", "source-to-target")
    if study_mode not in _STUDY_MODES:
        study_mode = "source-to-target"

    words = _fetch_words_at_level(level, foreign_lang, limit=_QUESTIONS_PER_ROUND)
    questions = _build_flashcard_questions(words, study_mode)

    return render_template(
        "trakaido/activities/flashcards.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        study_mode=study_mode,
        study_modes=_STUDY_MODES,
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


@bp.route("/typing")
def typing() -> ResponseReturnValue:
    """Typing activity: type the translation of the shown word."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    study_mode = request.args.get("study_mode", "source-to-target")
    if study_mode not in _STUDY_MODES:
        study_mode = "source-to-target"

    words = _fetch_words_at_level(level, foreign_lang, limit=_QUESTIONS_PER_ROUND)
    questions = _build_typing_questions(words, study_mode)

    return render_template(
        "trakaido/activities/typing.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        study_mode=study_mode,
        study_modes=_STUDY_MODES,
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


@bp.route("/verb-forms")
def verb_forms() -> ResponseReturnValue:
    """Verb conjugation activity: pick the correct form of a verb."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    verbs = _fetch_verbs_with_forms(level, foreign_lang)
    questions = _build_verb_form_questions(verbs, level)

    return render_template(
        "trakaido/activities/verb_forms.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        **_common_template_vars(level, interface_lang, foreign_lang),
    )


_LISTENING_STUDY_MODES = ["target-to-source", "target-to-target"]


@bp.route("/listening")
def listening() -> ResponseReturnValue:
    """Listening comprehension activity."""
    level, interface_lang, foreign_lang = _parse_activity_params()
    study_mode = request.args.get("study_mode", "target-to-source")
    if study_mode not in _LISTENING_STUDY_MODES:
        study_mode = "target-to-source"

    words = _fetch_words_at_level(level, foreign_lang, limit=60)
    questions = _build_listening_questions(words, foreign_lang, study_mode)

    return render_template(
        "trakaido/activities/listening.html",
        questions_json=json.dumps(questions, ensure_ascii=False),
        question_count=len(questions),
        study_mode=study_mode,
        study_modes=_LISTENING_STUDY_MODES,
        **_common_template_vars(level, interface_lang, foreign_lang),
    )
