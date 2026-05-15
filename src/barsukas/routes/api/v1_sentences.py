from flask import g
from flask.typing import ResponseReturnValue

from barsukas.routes.api import bp
from barsukas.routes._mirror import mirrored_facade
from storage.models import Sentence, SentenceTranslation, SentenceWord


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
                    "role": word.word_role,
                    "lemma_guid": word.lemma.guid if word.lemma is not None else None,
                    "english_text": word.english_text,
                    "target_language_text": word.target_language_text,
                    "grammatical_form": word.grammatical_form,
                }
                for word in word_rows
            ],
        }
    }
