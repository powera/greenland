#!/usr/bin/python3

"""Trakaido views served directly by Barsukas.

The first activity is a sentence comparison view: pick a sentence and render
it in two languages — an "interface language" the user already knows (defaults
to English) and a "foreign language" they are studying (defaults to Lithuanian).

When the interface language is English, words in the foreign sentence are
rendered with their English glosses underneath (using SentenceWord.english_text).
A second block always shows the two sentences in their original word order with
matched lemmas connected by lines and shared colors.
"""

from typing import Any, Dict, List, Optional, Tuple, cast

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from storage.models.schema import (
    AudioQualityReview,
    DerivativeForm,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceWord,
)
from storage.translation_helpers import get_supported_languages

bp = Blueprint("trakaido", __name__, url_prefix="/trakaido")


DEFAULT_INTERFACE_LANG = "en"
DEFAULT_FOREIGN_LANG = "lt"


def _parse_language_params() -> Tuple[str, str]:
    """Read interface/foreign language codes from the query string."""
    supported = set(get_supported_languages().keys())
    interface_lang = (request.args.get("interface_lang") or DEFAULT_INTERFACE_LANG).strip().lower()
    foreign_lang = (request.args.get("foreign_lang") or DEFAULT_FOREIGN_LANG).strip().lower()
    if interface_lang not in supported:
        interface_lang = DEFAULT_INTERFACE_LANG
    if foreign_lang not in supported:
        foreign_lang = DEFAULT_FOREIGN_LANG
    return interface_lang, foreign_lang


def _pick_random_sentence_id(interface_lang: str, foreign_lang: str) -> Optional[int]:
    """Pick a random non-rejected sentence with SentenceWord rows in both languages."""
    sub_iface = g.db.query(SentenceWord.sentence_id).filter(
        SentenceWord.language_code == interface_lang
    )
    sub_foreign = g.db.query(SentenceWord.sentence_id).filter(
        SentenceWord.language_code == foreign_lang
    )
    row = (
        g.db.query(Sentence.id)
        .filter(Sentence.rejected == False)  # noqa: E712
        .filter(Sentence.id.in_(sub_iface))
        .filter(Sentence.id.in_(sub_foreign))
        .order_by(func.random())
        .limit(1)
        .first()
    )
    return row[0] if row else None


# Tokens within grammatical_form features (post `pos/{lang}_` prefix) mapped to full words.
_GRAM_TOKEN_LABELS: Dict[str, str] = {
    # Case
    "nominative": "nominative",
    "accusative": "accusative",
    "genitive": "genitive",
    "dative": "dative",
    "instrumental": "instrumental",
    "locative": "locative",
    "vocative": "vocative",
    "ablative": "ablative",
    # Number
    "singular": "singular",
    "plural": "plural",
    # Gender
    "m": "masculine",
    "f": "feminine",
    "n": "neuter",
    "masculine": "masculine",
    "feminine": "feminine",
    "neuter": "neuter",
    # Tense / aspect / mood
    "present": "present",
    "past": "past",
    "future": "future",
    "imperf": "imperfect",
    "imperfect": "imperfect",
    "perfect": "perfect",
    "subjunctive": "subjunctive",
    "imperative": "imperative",
    "conditional": "conditional",
    "participle": "participle",
    "gerund": "gerund",
    "inf": "infinitive",
    "infinitive": "infinitive",
    "reflexive": "reflexive",
    "possessive": "possessive",
    "cardinal": "cardinal",
    "ordinal": "ordinal",
    "base": "",
    "pres": "present",
    "fut": "future",
    "objective": "objective",
    "subjective": "subjective",
}

_PERSON_NUMBER_TOKENS: Dict[str, str] = {
    "1s": "1st person singular",
    "2s": "2nd person singular",
    "3s": "3rd person singular",
    "1p": "1st person plural",
    "2p": "2nd person plural",
    "3p": "3rd person plural",
}

# Skip drawing connector lines when either side exceeds this word count.
_MAX_WORDS_FOR_LINES = 10


def _format_grammatical_label(form: Optional[str], lang: str) -> Optional[str]:
    """Turn 'noun/lt_accusative_singular_m' into 'acc. sg. masc.' etc."""
    if not form:
        return None
    if "/" not in form:
        return None
    _, _, features = form.partition("/")
    prefix = f"{lang}_"
    if features.startswith(prefix):
        features = features[len(prefix) :]
    elif features == lang:
        features = ""
    if not features or features == "base":
        return None
    labels: List[str] = []
    for tok in features.split("_"):
        if not tok:
            continue
        if tok in _PERSON_NUMBER_TOKENS:
            labels.append(_PERSON_NUMBER_TOKENS[tok])
        elif tok in _GRAM_TOKEN_LABELS:
            mapped = _GRAM_TOKEN_LABELS[tok]
            if mapped:
                labels.append(mapped)
        else:
            labels.append(tok)
    if not labels:
        return None
    return " ".join(labels)


def _word_payload(w: SentenceWord, lang: str) -> Dict[str, Any]:
    return {
        "position": w.position,
        "text": w.target_language_text,
        "gloss": w.english_text,
        "lemma_id": w.lemma_id,
        "part_of_speech": w.part_of_speech,
        "form": w.grammatical_form,
        "gram_label": _format_grammatical_label(w.grammatical_form, lang),
    }


# Rank parts of speech when we cap the colored set; lower number = higher priority.
_PART_OF_SPEECH_PRIORITY: Dict[str, int] = {
    "verb": 0,
    "noun": 1,
    "adjective": 2,
    "adverb": 3,
    "numeral": 4,
    "pronoun": 5,
    "article": 6,
    "preposition": 6,
    "conjunction": 7,
    "particle": 7,
    "other": 8,
}

_MAX_COLORED_PAIRS = 4


def _part_of_speech_rank(part_of_speech: Optional[str]) -> int:
    return _PART_OF_SPEECH_PRIORITY.get(part_of_speech or "", 9)


def _assign_pair_keys(
    iface_words: List[Dict[str, Any]], foreign_words: List[Dict[str, Any]]
) -> None:
    """Annotate words with 'pair_key' / 'pair_index' for cross-language coloring.

    Pairs are matched strictly by shared lemma_id (function words without a
    lemma never pair up). We then rank candidate pairs by the best part of speech on
    either side (content words like verb/noun outrank pronouns/conjunctions)
    and keep at most _MAX_COLORED_PAIRS. Words outside the kept set get
    pair_key=None, pair_index=None and render without color.
    """
    for w in iface_words:
        w["pair_key"] = None
        w["pair_index"] = None
    for w in foreign_words:
        w["pair_key"] = None
        w["pair_index"] = None

    iface_by_lemma: Dict[int, List[Dict[str, Any]]] = {}
    for w in iface_words:
        if w["lemma_id"] is not None:
            iface_by_lemma.setdefault(w["lemma_id"], []).append(w)
    foreign_by_lemma: Dict[int, List[Dict[str, Any]]] = {}
    for w in foreign_words:
        if w["lemma_id"] is not None:
            foreign_by_lemma.setdefault(w["lemma_id"], []).append(w)

    shared_lemmas = set(iface_by_lemma.keys()) & set(foreign_by_lemma.keys())

    candidates: List[Tuple[int, int, int]] = []  # (POS rank, first position, lemma ID)
    for lemma_id in shared_lemmas:
        best_rank = min(
            _part_of_speech_rank(w["part_of_speech"])
            for w in iface_by_lemma[lemma_id] + foreign_by_lemma[lemma_id]
        )
        first_pos = min(w["position"] for w in iface_by_lemma[lemma_id])
        candidates.append((best_rank, first_pos, lemma_id))

    candidates.sort()

    for index, (_rank, _pos, lemma_id) in enumerate(candidates[:_MAX_COLORED_PAIRS]):
        key = f"lemma:{lemma_id}"
        for w in iface_by_lemma[lemma_id] + foreign_by_lemma[lemma_id]:
            w["pair_key"] = key
            w["pair_index"] = index


_AUDIO_STATUS_PRIORITY = {
    "approved": 0,
    "approved_with_issues": 1,
    "pending_review": 2,
    "needs_replacement": 3,
}


def _pick_sentence_audio(sentence_id: int, language_code: str) -> Optional[AudioQualityReview]:
    """Return the best available audio review for this sentence/language, or None."""
    reviews = (
        g.db.query(AudioQualityReview)
        .filter(AudioQualityReview.sentence_id == sentence_id)
        .filter(AudioQualityReview.language_code == language_code)
        .all()
    )
    if not reviews:
        return None
    reviews.sort(key=lambda r: (_AUDIO_STATUS_PRIORITY.get(r.status, 99), r.id))
    return cast(AudioQualityReview, reviews[0])


@bp.route("/")
def index() -> ResponseReturnValue:
    """Trakaido landing page (lists available activities)."""
    return render_template("trakaido/index.html")


@bp.route("/compare")
def compare_random() -> ResponseReturnValue:
    """Pick a random eligible sentence and redirect to its canonical compare URL."""
    interface_lang, foreign_lang = _parse_language_params()
    sentence_id = _pick_random_sentence_id(interface_lang, foreign_lang)
    if sentence_id is None:
        return render_template(
            "trakaido/compare.html",
            sentence=None,
            interface_words=[],
            foreign_words=[],
            interface_lang=interface_lang,
            foreign_lang=foreign_lang,
            supported_languages=get_supported_languages(),
            show_gloss_block=False,
            show_lines=False,
            foreign_audio_url=None,
            foreign_audio_voice=None,
            no_results=True,
        )
    return redirect(
        url_for(
            "trakaido.compare",
            sentence_id=sentence_id,
            interface_lang=interface_lang,
            foreign_lang=foreign_lang,
        )
    )


@bp.route("/compare/<int:sentence_id>")
def compare(sentence_id: int) -> ResponseReturnValue:
    """Sentence comparison view."""
    interface_lang, foreign_lang = _parse_language_params()

    sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id).first()
    if sentence is None:
        abort(404)

    rows = (
        g.db.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence_id)
        .filter(SentenceWord.language_code.in_([interface_lang, foreign_lang]))
        .order_by(SentenceWord.language_code, SentenceWord.position)
        .all()
    )

    interface_words = [
        _word_payload(w, interface_lang) for w in rows if w.language_code == interface_lang
    ]
    foreign_words = [
        _word_payload(w, foreign_lang) for w in rows if w.language_code == foreign_lang
    ]
    interface_words.sort(key=lambda w: w["position"])
    foreign_words.sort(key=lambda w: w["position"])

    _assign_pair_keys(interface_words, foreign_words)

    foreign_audio = _pick_sentence_audio(sentence_id, foreign_lang)
    foreign_audio_url: Optional[str] = None
    if foreign_audio is not None:
        foreign_audio_url = url_for(
            "audio.serve_audio_file",
            language=foreign_audio.language_code,
            voice=foreign_audio.voice_name,
            filename=foreign_audio.filename,
        )

    return render_template(
        "trakaido/compare.html",
        sentence=sentence,
        interface_words=interface_words,
        foreign_words=foreign_words,
        interface_lang=interface_lang,
        foreign_lang=foreign_lang,
        supported_languages=get_supported_languages(),
        show_gloss_block=(interface_lang == "en"),
        show_lines=(
            len(interface_words) <= _MAX_WORDS_FOR_LINES
            and len(foreign_words) <= _MAX_WORDS_FOR_LINES
        ),
        foreign_audio_url=foreign_audio_url,
        foreign_audio_voice=foreign_audio.voice_name if foreign_audio else None,
        no_results=False,
    )


def _lemma_translation_for_language(
    lemma: Lemma, lang: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (text, definition, disambiguation) for the lemma in `lang`.

    English data lives on the Lemma itself; other languages come from
    LemmaTranslation rows.
    """
    if lang == "en":
        return lemma.lemma_text, lemma.definition_text, None
    row = (
        g.db.query(LemmaTranslation)
        .filter(LemmaTranslation.lemma_id == lemma.id)
        .filter(LemmaTranslation.language_code == lang)
        .first()
    )
    if row is None:
        return None, None, None
    return row.translation, row.definition_text, row.disambiguation


def _pick_lemma_audio(lemma_id: int, language_code: str) -> Optional[AudioQualityReview]:
    """Return the best available lemma audio review for this language, or None."""
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


_LEMMA_SEARCH_LIMIT = 50


def _form_order_key(lang: str, pos_type: Optional[str], grammatical_form: str) -> Tuple[int, str]:
    """Return a sort key giving canonical order for grammatical forms in (lang, pos).

    Falls back to alphabetical for unknown (lang, pos) or unknown forms.
    """
    if pos_type is None:
        return (10_000, grammatical_form)
    try:
        from langtools.form_registry import FORM_SPECS
    except ImportError:
        return (10_000, grammatical_form)
    spec = FORM_SPECS.get((lang, pos_type))
    if spec is None:
        return (10_000, grammatical_form)
    enum_to_index = {
        spec.form_mapping[field_name].value: idx
        for idx, field_name in enumerate(spec.form_fields)
        if field_name in spec.form_mapping
    }
    idx = enum_to_index.get(grammatical_form)
    if idx is None:
        return (10_000, grammatical_form)
    return (idx, grammatical_form)


@bp.route("/lemma/")
def lemma_search() -> ResponseReturnValue:
    """Search page for picking a lemma to open in the Trakaido lemma view."""
    interface_lang, foreign_lang = _parse_language_params()
    search = (request.args.get("search") or "").strip()

    results: List[Dict[str, Any]] = []
    if search:
        like = f"%{search}%"
        en_matches = (
            g.db.query(Lemma)
            .filter(Lemma.lemma_text.ilike(like))
            .order_by(Lemma.lemma_text)
            .limit(_LEMMA_SEARCH_LIMIT)
            .all()
        )
        translation_matches = (
            g.db.query(Lemma)
            .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
            .filter(LemmaTranslation.translation.ilike(like))
            .filter(LemmaTranslation.language_code.in_([interface_lang, foreign_lang]))
            .order_by(Lemma.lemma_text)
            .limit(_LEMMA_SEARCH_LIMIT)
            .all()
        )
        seen: set[int] = set()
        for lemma in list(en_matches) + list(translation_matches):
            if lemma.id in seen:
                continue
            seen.add(lemma.id)
            results.append(
                {
                    "id": lemma.id,
                    "lemma_text": lemma.lemma_text,
                    "definition_text": lemma.definition_text,
                    "pos_type": lemma.pos_type,
                    "disambiguation": lemma.disambiguation,
                }
            )
            if len(results) >= _LEMMA_SEARCH_LIMIT:
                break

    return render_template(
        "trakaido/lemma_search.html",
        search=search,
        results=results,
        interface_lang=interface_lang,
        foreign_lang=foreign_lang,
        supported_languages=get_supported_languages(),
    )


@bp.route("/lemma/<int:lemma_id>")
def lemma_view(lemma_id: int) -> ResponseReturnValue:
    """Trakaido lemma view: details + foreign forms + foreign audio."""
    interface_lang, foreign_lang = _parse_language_params()

    lemma = g.db.query(Lemma).filter(Lemma.id == lemma_id).first()
    if lemma is None:
        abort(404)

    iface_text, iface_definition, iface_disambiguation = _lemma_translation_for_language(
        lemma, interface_lang
    )
    foreign_text, foreign_definition, foreign_disambiguation = _lemma_translation_for_language(
        lemma, foreign_lang
    )

    foreign_forms = list(
        g.db.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma_id)
        .filter(DerivativeForm.language_code == foreign_lang)
        .all()
    )
    foreign_forms.sort(
        key=lambda f: (
            not f.is_base_form,
            _form_order_key(foreign_lang, lemma.pos_type, f.grammatical_form or ""),
        )
    )

    foreign_audio = _pick_lemma_audio(lemma_id, foreign_lang)
    foreign_audio_url: Optional[str] = None
    if foreign_audio is not None:
        foreign_audio_url = url_for(
            "audio.serve_audio_file",
            language=foreign_audio.language_code,
            voice=foreign_audio.voice_name,
            filename=foreign_audio.filename,
        )

    return render_template(
        "trakaido/lemma.html",
        lemma=lemma,
        interface_lang=interface_lang,
        foreign_lang=foreign_lang,
        supported_languages=get_supported_languages(),
        interface_text=iface_text,
        interface_definition=iface_definition,
        interface_disambiguation=iface_disambiguation,
        foreign_text=foreign_text,
        foreign_definition=foreign_definition,
        foreign_disambiguation=foreign_disambiguation,
        foreign_forms=foreign_forms,
        foreign_audio_url=foreign_audio_url,
        foreign_audio_voice=foreign_audio.voice_name if foreign_audio else None,
    )
