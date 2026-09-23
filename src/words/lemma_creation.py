"""Create one lemma from one sense: the write half of adding a word.

A "sense" here is the dict shape the definitions call returns -- ``pos``,
``pos_subtype``, ``definition``, the ``*_translation`` fields, ``examples``,
``ipa_spelling`` -- whether it came fresh from the LLM or was rebuilt from a
pending-import row.  :func:`create_sense_lemma` turns one of those into a
Lemma with a minted GUID, its translations, its example sentences and its
English base form, which is everything the lemma needs to be usable.

It is shared by :func:`words.add_word.add_word` and by pending-import approval,
so a word added directly and a word approved from the queue are written the
same way.  It does not go through ``wordfreq.translation.word_processing``,
whose ``process_word`` is a token-level bulk importer: it skips any token that
already has forms, so it cannot add a second sense to an existing word.

This module deliberately imports nothing from ``words.pending_imports``, so the
approval code can import it at module scope.
"""

from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from storage.crud.derivative_form import add_derivative_form
from storage.crud.operation_log import log_translation_change
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from langtools.en.base_forms import en_base_form
from storage.models.schema import Lemma, SentenceWordHint, WordToken
from storage.translation_helpers import convert_llm_response_to_lang_codes, set_translation
from storage.utils.guid import generate_guid
from wordfreq.translation.definitions import DEFINITIONS_PROMPT_LANGUAGES

# Level for a lemma whose difficulty nobody has decided yet. Exports skip it,
# so an unassessed sense does not ship at a made-up level.
UNSET_DIFFICULTY_LEVEL = -1

# Languages the definitions call already returns per sense, stored as the lemma
# is created so no second LLM call is needed for them.
TRANSLATION_LANGUAGES: Tuple[str, ...] = DEFINITIONS_PROMPT_LANGUAGES

# Collection tag for the example sentences the definitions call returns. These
# are not teaching material: the model wrote them to illustrate one sense of one
# word, nobody chose them for a curriculum, and they carry no translations. The
# tag keeps them separable from sentences that were authored as lessons, so a
# level rollup or an export can exclude them. They are stored with
# ``minimum_level`` unset for the same reason -- a difficulty would imply they
# had been placed in the curriculum.
EXAMPLE_SENTENCE_COLLECTION = "llm_word_examples"

# How many examples to keep per sense. The prompt asks for up to three and the
# model generally returns one; the cap is here so a model that returns ten does
# not quietly fill the sentence table.
MAX_EXAMPLES_PER_SENSE = 3


def store_sense_examples(
    session: Session,
    lemma: Lemma,
    sense: Dict[str, Any],
    *,
    source: str,
) -> int:
    """Store the LLM's example sentences for one sense. Returns how many were kept.

    The definitions call already returns these -- the schema asks for them and
    the prompt requests up to three per sense -- so they are paid for whether or
    not they are stored. They were previously discarded.

    English only, and deliberately: the model was asked to illustrate an English
    sense, not to translate a sentence, so there is nothing to store for the
    other languages and no second call is made to get one. A later pass can
    translate these if they are wanted as teaching material.

    The link back to the lemma is a ``SentenceWordHint`` rather than a
    ``SentenceWord``: a hint records which lemma a sentence was built to
    exercise, which is exactly what this is, while SentenceWord is the
    authoritative per-position breakdown and would need a parse these raw
    strings have not had.
    """
    raw_examples = sense.get("examples")
    if not isinstance(raw_examples, list):
        return 0

    stored = 0
    for raw_example in raw_examples:
        if stored >= MAX_EXAMPLES_PER_SENSE:
            break
        if not isinstance(raw_example, str):
            continue
        example_text = raw_example.strip()
        if not example_text:
            continue

        sentence = add_sentence(
            session,
            source_filename=f"add_word:{lemma.lemma_text}",
            notes=f"LLM example for {lemma.guid}: {lemma.definition_text[:80]}",
            sentence_collection=EXAMPLE_SENTENCE_COLLECTION,
            source=source,
        )
        add_sentence_translation(
            session,
            sentence,
            "en",
            example_text,
            source=source,
        )
        session.add(
            SentenceWordHint(
                sentence_id=sentence.id,
                lemma_id=lemma.id,
                position=0,
                # slot_name carries the POS, matching what the generators write.
                slot_name=lemma.pos_type,
                english_text=lemma.lemma_text,
            )
        )
        stored += 1

    return stored


def store_sense_translations(
    session: Session, lemma: Lemma, sense: Dict[str, Any], *, source: str, model: Optional[str]
) -> Dict[str, str]:
    """Save the translations the definitions call already returned for this sense.

    The definitions schema returns lt/es/es-419/fr/zh per sense, so they arrive with
    the definition at no extra LLM cost, and each sense gets its own
    translation. Field names map to language codes through translation_helpers,
    per CLAUDE.md -- no local mapping.

    Returns:
        The language code -> translation text pairs actually stored.
    """
    by_lang_code = convert_llm_response_to_lang_codes(sense)
    stored: Dict[str, str] = {}
    for lang_code in TRANSLATION_LANGUAGES:
        translation = (by_lang_code.get(lang_code) or "").strip()
        if not translation:
            continue
        set_translation(session, lemma, lang_code, translation)
        log_translation_change(
            session=session,
            source=source,
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=None,
            new_translation=translation,
            guid=lemma.guid,
            model=model,
        )
        stored[lang_code] = translation
    return stored


def create_sense_lemma(
    session: Session,
    word: str,
    sense: Dict[str, Any],
    *,
    pos_type: str,
    pos_subtype: str,
    definition_text: str,
    sense_prominence: str,
    difficulty_level: int,
    source: str,
    model: Optional[str],
    frequency_rank: Optional[int] = None,
    best_corpus_rank: Optional[int] = None,
    disambiguation: Optional[str] = None,
) -> Tuple[Lemma, Dict[str, str]]:
    """Create one lemma for one sense of ``word``, flushed but not committed.

    The caller has already decided this sense is new and validated its POS;
    this only writes.  The caller commits, so it can decide whether a
    multi-sense word is one transaction or several.

    Raises:
        ValueError: from GUID generation, when ``pos_subtype`` has no prefix.

    Returns:
        The new lemma, and the translations stored on it by language code.
    """
    guid = generate_guid(session, pos_type, pos_subtype)

    lemma = Lemma(
        lemma_text=word,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        guid=guid,
        difficulty_level=difficulty_level,
        disambiguation=disambiguation,
        confidence=0.0,
        verified=False,
        sense_prominence=sense_prominence,
    )
    session.add(lemma)
    session.flush()

    log_translation_change(
        session=session,
        source=source,
        operation_type="lemma_create",
        lemma_id=lemma.id,
        language_code="en",
        old_translation=None,
        new_translation=word,
        guid=guid,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        definition=definition_text,
        sense_prominence=sense_prominence,
        model=model,
        best_corpus_rank=best_corpus_rank,
    )
    translations = store_sense_translations(session, lemma, sense, source=source, model=model)
    # The definitions call already returned example sentences for this
    # sense; keep them rather than paying for them and dropping them.
    store_sense_examples(session, lemma, sense, source=source)

    # A lemma's English text is stored on Lemma rather than in
    # LemmaTranslation, but the token-frequency system reaches lemmas
    # only through DerivativeForm/VariantForm attachments. Record the
    # English base form immediately so this newly claimed token leaves
    # the unlinked-token queue and its frequency can roll up to every
    # created sense.
    word_token = (
        session.query(WordToken)
        .filter(WordToken.token == word, WordToken.language_code == "en")
        .first()
    )
    if word_token is None:
        word_token = WordToken(token=word, language_code="en")
        session.add(word_token)
        session.flush()
    add_derivative_form(
        session,
        lemma,
        word,
        "en",
        en_base_form(pos_type),
        word_token=word_token,
        is_base_form=True,
        ipa_pronunciation=(sense.get("ipa_spelling") or None),
        phonetic_pronunciation=(sense.get("phonetic_spelling") or None),
        source=source,
    )

    # Record the corpus rank on the lemma itself, not only in the operation
    # log. This runs after the derivative form is attached because the rank
    # is a property of the token the form just linked: a lemma reached through
    # no DerivativeForm has nothing to roll up from, and downstream consumers
    # read Lemma.frequency_rank rather than re-deriving it.
    lemma.frequency_rank = frequency_rank

    return lemma, translations
