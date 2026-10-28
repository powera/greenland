"""Read-only practice and inspection of Trakaido's newer activity content."""

import json
import random
import unicodedata
from collections import Counter
from typing import Any

from flask import Blueprint, g, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from barsukas.routes.trakaido_activities import (
    _parse_activity_params,
    _pick_lemma_audio,
    _render_activity,
    _weighted_sample_by_level,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation

bp = Blueprint("trakaido_inspection", __name__, url_prefix="/trakaido/activities")

ACTIVITIES: dict[str, tuple[str, str]] = {
    "grammar-phrases": (
        "Grammar Phrases",
        "Translate rule-built phrases with explicit grammar eligibility. Prompts are in English; equivalent accepted forms are retained.",
    ),
    "number-arithmetic": (
        "Number Arithmetic",
        "Solve sums and differences using only number words present in the catalog.",
    ),
    "emoji-count": ("Emoji Count", "Count pictures and type the target cardinal number word."),
    "declension": (
        "Declension",
        "Identify cases from explicit stored noun forms; syncretic cases are accepted together.",
    ),
    "conjugation": (
        "Conjugation",
        "Produce a stored person/tense form. Missing forms are never invented.",
    ),
    "pronouns": (
        "Pronouns",
        "Practice stored pronoun vocabulary. Authored client-only supplemental paradigms are not included.",
    ),
    "numbers": (
        "Numbers",
        "Recognize cardinal and ordinal words from the shared Trakaido number catalog.",
    ),
    "emoji-choice": ("Emoji Choice", "Choose the target word matching the concept's stored emoji."),
    "listen-repeat": (
        "Listen and Repeat",
        "Listen, speak aloud, and compare yourself with the recording. Self-assessment only; no speech recognition.",
    ),
    "vocabulary-list": (
        "Vocabulary List",
        "Inspect translations, source records and approved base-form recordings.",
    ),
}
CASES = ("nominative", "genitive", "dative", "accusative", "instrumental", "locative", "vocative")
CARDINALS = [*range(21), 30, 40, 50, 60, 70, 80, 90, 100, 1000]
NUMBER_VALUES = {f"Z01_{index + 1:03}": str(value) for index, value in enumerate(CARDINALS)}
NUMBER_VALUES.update({f"Z02_{value:03}": f"ordinal {value}" for value in range(1, 11)})


def _emojis(raw: str | None) -> list[str]:
    """Read valid concept emoji without guessing from an English gloss."""
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return (
        [entry for entry in parsed if isinstance(entry, str) and entry.strip()]
        if isinstance(parsed, list)
        else []
    )


def _audio_url(lemma_id: int, language: str, form: str | None = None) -> str | None:
    """Use reviewed audio for the exact form, never another inflection."""
    from storage.models.schema import AudioQualityReview

    cache: dict[tuple[int, str, str | None], str | None] = g.setdefault("inspection_audio", {})
    cache_key = (lemma_id, language, form)
    if cache_key in cache:
        return cache[cache_key]
    if form is None:
        recording = _pick_lemma_audio(lemma_id, language)
    else:
        recording = (
            g.db.query(AudioQualityReview)
            .filter(
                AudioQualityReview.lemma_id == lemma_id,
                AudioQualityReview.language_code == language,
                AudioQualityReview.grammatical_form == form,
                AudioQualityReview.sentence_id.is_(None),
                AudioQualityReview.status.in_(["approved", "approved_with_issues"]),
            )
            .order_by(AudioQualityReview.id)
            .first()
        )
    if recording is None:
        cache[cache_key] = None
        return None
    result = str(
        url_for(
            "audio.serve_audio_file",
            language=language,
            voice=recording.voice_name,
            filename=recording.filename,
        )
    )
    cache[cache_key] = result
    return result


def _pool(level: int, language: str, source_language: str, kind: str) -> list[dict[str, Any]]:
    """Fetch a bounded, level-weighted pool with source-language translations."""
    query = (
        g.db.query(Lemma, LemmaTranslation.translation)
        .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
        .filter(
            LemmaTranslation.language_code == language,
            LemmaTranslation.translation != "",
            Lemma.difficulty_level.between(1, level),
        )
    )
    if kind in {"numbers", "number-arithmetic"}:
        query = query.filter(Lemma.guid.in_(NUMBER_VALUES))
    elif kind in {"declension", "conjugation", "pronouns"}:
        query = query.filter(
            Lemma.pos_type
            == {"declension": "noun", "conjugation": "verb", "pronouns": "pronoun"}[kind]
        )
    if kind == "emoji-count":
        rows = query.filter(Lemma.guid.in_(NUMBER_VALUES)).all()
        rows += (
            query.filter(Lemma.emoji.isnot(None), ~Lemma.guid.in_(NUMBER_VALUES))
            .order_by(func.random())
            .limit(350)
            .all()
        )
    else:
        rows = query.order_by(func.random()).limit(400).all()
    source = {
        translation.lemma_id: translation.translation
        for translation in g.db.query(LemmaTranslation).filter(
            LemmaTranslation.language_code == source_language,
            LemmaTranslation.lemma_id.in_([lemma.id for lemma, _target in rows]),
        )
    }
    items = []
    for lemma, target in rows:
        source_text = lemma.lemma_text if source_language == "en" else source.get(lemma.id)
        if source_text:
            items.append(
                {
                    "id": lemma.id,
                    "guid": lemma.guid,
                    "source": source_text,
                    "target": target,
                    "pos": lemma.pos_type,
                    "emoji": lemma.emoji,
                    "level": lemma.difficulty_level,
                }
            )
    return _weighted_sample_by_level(items, level, 400)


def _questions(
    kind: str, words: list[dict[str, Any]], language: str, level: int
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Build reviewable questions and explicit exclusion counts for this sample."""
    questions: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    if kind == "grammar-phrases":
        from langtools.sentence_patterns import render, supported_languages
        from sentences.pattern_pools import load_pools

        if language not in supported_languages():
            skipped["language has no rule-based phrase renderer"] += 1
            return questions, skipped
        result = render(language, load_pools(g.db, language, max_level=level))
        skipped.update(skip.reason for skip in result.skips)
        for phrase in result.sentences:
            questions.append(
                {
                    "prompt": phrase.english,
                    "source": phrase.english,
                    "target": phrase.target,
                    "answers": [phrase.target, *phrase.also_accepted],
                    "options": [],
                    "note": phrase.pattern_id + (" · " + phrase.detail if phrase.detail else ""),
                    "audio": None,
                    "guid": ", ".join(phrase.word_guids),
                    "url": (
                        url_for("lemmas.view_lemma", lemma_id=phrase.word_guids[0])
                        if phrase.word_guids
                        else url_for("lemmas.list_lemmas")
                    ),
                }
            )
        return questions, skipped
    if kind in {"number-arithmetic", "emoji-count"}:
        numbered = {
            int(NUMBER_VALUES[word["guid"]]): word
            for word in words
            if word["guid"] in NUMBER_VALUES and word["guid"].startswith("Z01_")
        }
        pictures: list[str] = []
        for pictured_word in words:
            try:
                parsed = json.loads(pictured_word["emoji"] or "[]")
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], str):
                pictures.append(parsed[0])
        for value, number_word in numbered.items():
            prompts: list[str] = []
            if kind == "emoji-count" and 1 <= value <= 10 and pictures:
                prompts.append(" ".join([random.choice(pictures)] * value))
            elif kind == "number-arithmetic":
                for left_value, left_word in numbered.items():
                    right_value = value - left_value
                    if right_value in numbered:
                        prompts.append(
                            f"{left_word['target']} + {numbered[right_value]['target']} = ?"
                        )
                    difference_value = left_value - value
                    if difference_value in numbered:
                        prompts.append(
                            f"{left_word['target']} − {numbered[difference_value]['target']} = ?"
                        )
            for prompt in prompts:
                questions.append(
                    {
                        **number_word,
                        "prompt": prompt,
                        "answers": [number_word["target"]],
                        "options": [],
                        "note": "Type the number word. Audio below is the answer only.",
                        "audio": _audio_url(number_word["id"], language),
                        "url": url_for("lemmas.view_lemma", lemma_id=number_word["id"]),
                    }
                )
        if not questions:
            skipped["missing catalog numbers or emoji required by this activity"] += 1
        return questions, skipped
    ids = [word["id"] for word in words]
    forms: dict[int, list[DerivativeForm]] = {}
    for stored_form in g.db.query(DerivativeForm).filter(
        DerivativeForm.lemma_id.in_(ids), DerivativeForm.language_code == language
    ):
        forms.setdefault(stored_form.lemma_id, []).append(stored_form)
    number_types = {
        fact.lemma_id: fact.fact_value
        for fact in g.db.query(GrammarFact).filter(
            GrammarFact.lemma_id.in_(ids),
            GrammarFact.language_code == language,
            GrammarFact.fact_type == "number_type",
        )
    }
    for word in words:
        item: dict[str, Any] = {
            **word,
            "prompt": word["source"],
            "answers": [word["target"]],
            "options": [],
            "note": "",
            "audio": None,
            "url": url_for("lemmas.view_lemma", lemma_id=word["id"]),
        }
        if kind == "declension":
            if word["pos"] != "noun":
                continue
            number_type = number_types.get(word["id"])
            if number_type not in {"regular", "singulare_tantum", "plurale_tantum"}:
                skipped["noun missing explicit number_type"] += 1
                continue
            grouped: dict[str, set[str]] = {}
            for noun_form in forms.get(word["id"], []):
                slot = noun_form.grammatical_form.removeprefix(f"noun/{language}_")
                parts = slot.rsplit("_", 1)
                if (
                    len(parts) != 2
                    or parts[0] not in CASES
                    or parts[1] not in {"singular", "plural"}
                ):
                    continue
                if (number_type == "plurale_tantum" and parts[1] == "singular") or (
                    number_type == "singulare_tantum" and parts[1] == "plural"
                ):
                    continue
                grouped.setdefault(noun_form.derivative_form_text, set()).add(parts[0])
            if not grouped:
                skipped["noun missing explicit case/number forms"] += 1
            for surface, valid_cases in grouped.items():
                questions.append(
                    {
                        **item,
                        "prompt": surface,
                        "answers": sorted(valid_cases),
                        "options": list(CASES),
                        "note": f"{word['source']} · {word['target']} · all matching stored cases count",
                    }
                )
            continue
        if kind == "conjugation":
            if word["pos"] != "verb":
                continue
            verb_forms = [
                entry
                for entry in forms.get(word["id"], [])
                if entry.grammatical_form.startswith(f"verb/{language}_")
                and entry.derivative_form_text.strip()
                and entry.grammatical_form != f"verb/{language}_infinitive"
            ]
            if not verb_forms:
                skipped["verb missing stored conjugations"] += 1
            verb_slots: dict[str, list[str]] = {}
            for verb_form in verb_forms:
                verb_slots.setdefault(verb_form.grammatical_form, []).append(
                    verb_form.derivative_form_text
                )
            for verb_slot, alternatives in verb_slots.items():
                questions.append(
                    {
                        **item,
                        "answers": list(dict.fromkeys(alternatives)),
                        "note": verb_slot,
                        "audio": _audio_url(word["id"], language, verb_slot),
                    }
                )
            continue
        if kind == "pronouns" and word["pos"] != "pronoun":
            continue
        if kind == "pronouns":
            pronoun_slots: dict[str, list[str]] = {}
            for pronoun_form in forms.get(word["id"], []):
                if not pronoun_form.grammatical_form.startswith(f"pronoun/{language}_"):
                    continue
                if not pronoun_form.derivative_form_text.strip():
                    continue
                pronoun_slots.setdefault(pronoun_form.grammatical_form, []).append(
                    pronoun_form.derivative_form_text
                )
            for pronoun_slot, pronoun_answers in pronoun_slots.items():
                questions.append(
                    {
                        **item,
                        "note": pronoun_slot,
                        "answers": list(dict.fromkeys(pronoun_answers)),
                        "audio": _audio_url(word["id"], language, pronoun_slot),
                    }
                )
        if kind == "numbers":
            if word["guid"] not in NUMBER_VALUES:
                continue
            item["prompt"] = NUMBER_VALUES[word["guid"]]
        if kind == "emoji-choice":
            emojis = _emojis(word["emoji"])
            if not emojis:
                skipped["missing valid emoji array"] += 1
                continue
            item["prompt"] = emojis[0]
            other_targets = sorted(
                {
                    candidate["target"]
                    for candidate in words
                    if candidate["id"] != word["id"]
                    and candidate["target"] != word["target"]
                    and emojis[0] not in _emojis(candidate["emoji"])
                }
            )
            if len(other_targets) < 3:
                skipped["fewer than three distinct distractors"] += 1
                continue
            item["options"] = [word["target"], *random.sample(other_targets, 3)]
            random.shuffle(item["options"])
        item["audio"] = _audio_url(word["id"], language)
        if kind == "listen-repeat" and not item["audio"]:
            skipped["missing approved base recording"] += 1
            continue
        questions.append(item)
    return questions, skipped


@bp.route("/inspect/<kind>", methods=["GET", "POST"])
def inspect_activity(kind: str) -> ResponseReturnValue:
    """Practice one content item without writing learning or linguistic data."""
    from flask import abort

    if kind not in ACTIVITIES:
        abort(404)
    level, source_language, language = _parse_activity_params()
    title, description = ACTIVITIES[kind]
    feedback = None
    questions, skipped = _questions(
        kind, _pool(level, language, source_language, kind), language, level
    )
    token = f"{kind}:{level}:{language}:{source_language}"
    saved = session.get("inspection_question")
    if request.method == "POST" and saved and saved.get("token") == token:
        question = saved["question"]

        def normalize(text: str) -> str:
            return " ".join(
                unicodedata.normalize("NFC", text)
                .casefold()
                .replace("’", "'")
                .strip()
                .rstrip(".!?。！？")
                .split()
            )

        answer = normalize(request.form.get("answer", ""))
        accepted = {normalize(text) for text in question["answers"]}
        feedback = (
            "Correct!" if answer in accepted else "Answer: " + " / ".join(question["answers"])
        )
    else:
        question = random.choice(questions) if questions else None
        if question:
            session["inspection_question"] = {"token": token, "question": question}
    return _render_activity(
        "trakaido/activities/inspection.html",
        level,
        source_language,
        language,
        kind=kind,
        activity_title=title,
        description=description,
        question=question,
        feedback=feedback,
        skipped=skipped,
        pool_count=len(questions),
        vocabulary=questions if kind == "vocabulary-list" else [],
    )
