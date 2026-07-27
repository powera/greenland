from typing import Any, Dict, List, Optional

from flask import g, request
from flask.typing import ResponseReturnValue
from sqlalchemy import and_, case, func

from barsukas.routes.api import bp
from barsukas.routes._mirror import mirrored_facade
from barsukas.routes.api.meta_routes import _build_error_response, _build_success_response
from storage.crud.sentence import add_sentence, find_sentence_by_text
from storage.crud.sentence_translation import add_sentence_translation
from storage.models import Sentence, SentenceTranslation, SentenceWord
from storage.models.schema import AudioQualityReview
from storage.translation_helpers import LANGUAGE_HIERARCHY


@bp.route("/v1/sentences/<int:sentence_id>")
@mirrored_facade("/api/v1/sentences/<id>", "GET")
def get_sentence(sentence_id: int) -> ResponseReturnValue:
    sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id).first()
    if sentence is None:
        return {"error": f"Sentence {sentence_id} not found"}, 404
    translation_rows = (
        g.db.query(SentenceTranslation)
        .filter(SentenceTranslation.sentence_id == sentence.id)
        .order_by(SentenceTranslation.language_code.asc())
        .all()
    )
    translations: dict[str, str] = {}
    for row in translation_rows:
        if row.translation_text:
            translations[row.language_code] = row.translation_text
    word_rows = (
        g.db.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence.id)
        .order_by(SentenceWord.language_code.asc(), SentenceWord.position.asc())
        .all()
    )
    return {
        "data": {
            "id": sentence.id,
            "source_filename": sentence.source_filename,
            "minimum_level": sentence.minimum_level,
            "verified": sentence.verified,
            "translations": translations,
            "words": [
                {
                    "language_code": word.language_code,
                    "position": word.position,
                    "part_of_speech": word.part_of_speech,
                    "lemma_guid": word.lemma.guid if word.lemma is not None else None,
                    "english_text": word.english_text,
                    "target_language_text": word.target_language_text,
                    "grammatical_form": word.grammatical_form,
                }
                for word in word_rows
            ],
        }
    }


@bp.route("/v1/metadata/sentences")
@mirrored_facade("/api/v1/metadata/sentences", "GET")
def get_sentence_metadata() -> ResponseReturnValue:
    requested_language = request.args.get("language", "").strip().lower()
    max_difficulty_param = request.args.get("max_difficulty", "").strip()
    max_difficulty_sentences: Optional[int] = None
    if max_difficulty_param:
        try:
            max_difficulty_sentences = int(max_difficulty_param)
        except ValueError:
            return _build_error_response("max_difficulty must be an integer", 400)
    sentence_translation_languages = {
        row[0]
        for row in g.db.query(SentenceTranslation.language_code)
        .filter(
            SentenceTranslation.translation_text.isnot(None),
            SentenceTranslation.translation_text != "",
        )
        .distinct()
        .all()
    }
    sentence_audio_languages = {
        row[0]
        for row in g.db.query(AudioQualityReview.language_code)
        .filter(AudioQualityReview.sentence_id.isnot(None))
        .distinct()
        .all()
    }
    available_languages = (
        set(LANGUAGE_HIERARCHY) | sentence_translation_languages | sentence_audio_languages
    )
    if requested_language and requested_language not in available_languages:
        return _build_error_response(
            f"Language '{requested_language}' not found in metadata sources", 404
        )
    ordered_languages = [lang for lang in LANGUAGE_HIERARCHY if lang in available_languages]
    extra_languages = sorted(lang for lang in available_languages if lang not in LANGUAGE_HIERARCHY)
    selected_languages = (
        [requested_language] if requested_language else ordered_languages + extra_languages
    )
    summary_data: Dict[str, Any] = {}
    for current_language in selected_languages:
        sentence_filters = [
            SentenceTranslation.language_code == current_language,
            SentenceTranslation.translation_text.isnot(None),
            SentenceTranslation.translation_text != "",
        ]
        if max_difficulty_sentences is not None:
            sentence_filters.extend(
                [
                    Sentence.minimum_level.isnot(None),
                    Sentence.minimum_level >= 1,
                    Sentence.minimum_level <= max_difficulty_sentences,
                ]
            )
        base_subquery = (
            g.db.query(Sentence.id, Sentence.pattern_type, Sentence.verified)
            .join(SentenceTranslation, SentenceTranslation.sentence_id == Sentence.id)
            .filter(*sentence_filters)
            .distinct()
            .subquery()
        )
        total_sentences = g.db.query(func.count()).select_from(base_subquery).scalar() or 0
        pattern_rows = (
            g.db.query(
                case(
                    (base_subquery.c.pattern_type.is_(None), "unspecified"),
                    else_=base_subquery.c.pattern_type,
                ).label("pattern_type"),
                func.count().label("count"),
            )
            .group_by("pattern_type")
            .order_by("pattern_type")
            .all()
        )
        audio_count = (
            g.db.query(func.count(func.distinct(base_subquery.c.id)))
            .select_from(base_subquery)
            .join(
                AudioQualityReview,
                and_(
                    AudioQualityReview.sentence_id == base_subquery.c.id,
                    AudioQualityReview.language_code == current_language,
                ),
            )
            .scalar()
            or 0
        )
        verified_count = (
            g.db.query(func.count())
            .select_from(base_subquery)
            .filter(base_subquery.c.verified.is_(True))
            .scalar()
            or 0
        )
        summary_data[current_language] = {
            "total_sentences": total_sentences,
            "sentences_by_pattern": {row.pattern_type: row.count for row in pattern_rows},
            "audio": {"with_audio": audio_count, "without_audio": total_sentences - audio_count},
            "verification": {
                "verified": verified_count,
                "unverified": total_sentences - verified_count,
            },
        }
    metadata: Dict[str, Any] = {"languages": selected_languages, "count": len(selected_languages)}
    if requested_language:
        metadata["requested_language"] = requested_language
    if max_difficulty_sentences is not None:
        metadata["max_difficulty"] = max_difficulty_sentences
    return _build_success_response(summary_data, metadata)


_ADD_SENTENCES_MAX = 15


@bp.route("/v1/sentences/add", methods=["POST"])
@mirrored_facade("/api/v1/sentences/add", "POST")
def add_sentences() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    sentences_raw = payload.get("sentences")
    if not isinstance(sentences_raw, list) or not sentences_raw:
        return _build_error_response("sentences must be a non-empty list")
    if len(sentences_raw) > _ADD_SENTENCES_MAX:
        return _build_error_response(f"sentences may contain at most {_ADD_SENTENCES_MAX} items")
    sentences: List[str] = []
    for item in sentences_raw:
        if not isinstance(item, str) or not item.strip():
            return _build_error_response("each sentence must be a non-empty string")
        sentences.append(item.strip())
    source = payload.get("source", "")
    if not isinstance(source, str) or not source.strip():
        return _build_error_response("source is required and must be a non-empty string")
    language = payload.get("language", "en")
    if not isinstance(language, str) or not language.strip():
        return _build_error_response("language must be a non-empty string")
    language = language.strip().lower()
    results: List[Dict[str, Any]] = []
    created_count = 0
    already_exists_count = 0
    for sentence_text in sentences:
        existing = find_sentence_by_text(g.db, sentence_text, language_code=language)
        if existing is not None:
            results.append(
                {
                    "sentence_text": sentence_text,
                    "sentence_id": existing.id,
                    "guid": existing.guid,
                    "status": "already_exists",
                }
            )
            already_exists_count += 1
            continue
        sentence_row = add_sentence(g.db, source_filename=source.strip())
        add_sentence_translation(
            g.db,
            sentence=sentence_row,
            language_code=language,
            translation_text=sentence_text,
            verified=False,
        )
        results.append(
            {
                "sentence_text": sentence_text,
                "sentence_id": sentence_row.id,
                "guid": sentence_row.guid,
                "status": "created",
            }
        )
        created_count += 1
    return _build_success_response(
        results,
        {
            "total": len(sentences),
            "created": created_count,
            "already_exists": already_exists_count,
            "source": source.strip(),
            "language": language,
        },
    )
