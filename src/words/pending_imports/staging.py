"""Create pending imports: the entry point every stager goes through.

Four things stage terms -- the frequency check, the document parser (genys),
the sentence import path, and a human typing a word list into Barsukas -- and
each of them used to build a ``PendingImport`` row by hand. That is how rows
ended up with no ``target_kind``, no example sentence, and inconsistent dedup.

:func:`create_pending_import` is the one constructor. It applies the rule-tier
classification from :mod:`words.pending_imports.classification`, so a proper
noun is marked as a name at staging time rather than after someone notices a
"George" lemma in the queue.
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.models.imports import TARGET_KIND_LEMMA, PendingImport
from storage.translation_helpers import LANG_CODE_TO_LLM_FIELD
from util.logging_config import get_logger
from words.pending_imports.classification import suggest_target_kind
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.definitions import select_senses_to_add

logger = get_logger(__name__)


def find_pending_import(
    session: Session, english_word: str, *, definition: Optional[str] = None
) -> Optional[PendingImport]:
    """The existing staged row for a term, if there is one.

    Matched case-insensitively on the English word, and additionally on the
    definition when one is given -- two senses of the same word are two rows,
    but two stagings of the same sense are one.
    """
    query = session.query(PendingImport).filter(
        func.lower(PendingImport.english_word) == english_word.strip().lower()
    )
    if definition is not None:
        query = query.filter(PendingImport.definition == definition)
    return cast(Optional[PendingImport], query.order_by(PendingImport.id).first())


def create_pending_import(
    session: Session,
    *,
    english_word: str,
    definition: str,
    disambiguation_translation: str,
    disambiguation_language: str,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    tags: Optional[str] = None,
    source: Optional[str] = None,
    frequency_rank: Optional[int] = None,
    notes: Optional[str] = None,
    example_sentence: Optional[str] = None,
    target_kind: Optional[str] = None,
    name_kind: Optional[str] = None,
    concept_type: Optional[str] = None,
    classify: bool = True,
) -> PendingImport:
    """Stage one term for review, classified into a target kind.

    Does not commit, and does not deduplicate: callers own both, since what
    counts as a duplicate differs between a per-sense frequency staging and a
    per-gloss sentence staging. Use :func:`find_pending_import` for the common
    checks.

    Args:
        session: Database session.
        english_word: The term as it will be reviewed.
        definition: Sense being staged; the sentence path passes the gloss
            itself when it has nothing better.
        disambiguation_translation: Foreign-language rendering that pins the
            sense down. NOT NULL on the table, so callers fall back to the
            definition when the LLM returned nothing.
        disambiguation_language: Language code the above is written in.
        pos_type: Part of speech, when known.
        pos_subtype: Subtype that will drive the GUID, when known.
        tags: Pre-serialized JSON tag array applied to the lemma this becomes.
        source: Provenance string, e.g. ``"genys/report.txt"``.
        frequency_rank: Corpus rank, for frequency-driven staging.
        notes: Free-text note.
        example_sentence: Sentence the term was seen in, used as context by the
            approval step's LLM call and by classification.
        target_kind: Force a kind instead of classifying. One of
            ``PENDING_IMPORT_TARGET_KINDS``.
        name_kind: For a name, one of ``NAME_KINDS``. Ignored for other kinds
            at approval time, so passing it costs nothing.
        concept_type: For a concept, its coarse type.
        classify: Run the rule-tier classifier when ``target_kind`` is None.
            Off for callers that know they are staging vocabulary.

    Returns:
        The created row, flushed so its id is populated.
    """
    resolved_kind = target_kind
    resolved_name_kind = name_kind
    resolved_concept_type = concept_type

    if resolved_kind is None:
        if classify:
            suggestion = suggest_target_kind(
                session,
                english_word,
                example_sentence=example_sentence,
                pos_type=pos_type,
            )
            resolved_kind = suggestion.target_kind
            resolved_name_kind = resolved_name_kind or suggestion.name_kind
            resolved_concept_type = resolved_concept_type or suggestion.concept_type
            if suggestion.target_kind != TARGET_KIND_LEMMA:
                logger.info(
                    "Staging '%s' as %s: %s",
                    english_word,
                    suggestion.target_kind,
                    suggestion.reason,
                )
        else:
            resolved_kind = TARGET_KIND_LEMMA

    pending = PendingImport(
        english_word=english_word,
        definition=definition,
        disambiguation_translation=disambiguation_translation,
        disambiguation_language=disambiguation_language,
        target_kind=resolved_kind,
        name_kind=resolved_name_kind,
        concept_type=resolved_concept_type,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        tags=tags,
        source=source,
        frequency_rank=frequency_rank,
        notes=notes,
        example_sentence=example_sentence,
    )
    session.add(pending)
    session.flush()
    return pending


def stage_missing_words_for_import(
    session: Any,
    missing_words: List[Dict[str, Any]],
    db_path: str,
    limit: Optional[int] = None,
    model: str = "gpt-5.4-mini",
    throttle: float = 1.0,
    dry_run: bool = False,
    target_language: str = "lt",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Stage high-frequency missing words to the pending_imports table.

    This is step 1 of a two-step import process:
    1. Identify candidate words and query LLM for definitions/translations -> PendingImport
    2. Review/approve pending imports -> Convert to Lemma/Name/Concept

    Args:
        session: Database session
        missing_words: List of missing words from check_high_frequency_missing_words
        db_path: Database path for LinguisticClient
        limit: Maximum number of words to stage
        model: LLM model to use for definitions
        throttle: Seconds to wait between API calls
        dry_run: If True, show what would be staged without making changes
        target_language: Language code for disambiguation translations (default: lt)
        debug: Debug flag

    Returns:
        Dictionary with staging results
    """
    logger.info("Staging high-frequency missing words for import...")

    total_missing = len(missing_words)

    if total_missing == 0:
        logger.info("No high-frequency missing words found!")
        return {
            "total_missing": 0,
            "staged": 0,
            "skipped_already_pending": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    logger.info(f"Found {total_missing} high-frequency missing words")

    # Apply limit if specified
    if limit:
        words_to_stage = missing_words[:limit]
        logger.info(f"Staging limited to {limit} words")
    else:
        words_to_stage = missing_words

    if dry_run:
        logger.info(f"DRY RUN: Would stage {len(words_to_stage)} words:")
        for word_info in words_to_stage[:20]:
            corpus_str = ", ".join(
                [f"{c['corpus']}:{c['rank']}" for c in word_info["corpus_frequencies"][:2]]
            )
            logger.info(
                f"  - '{word_info['word']}' (overall rank: {word_info['overall_rank']}, {corpus_str})"
            )
        if len(words_to_stage) > 20:
            logger.info(f"  ... and {len(words_to_stage) - 20} more")
        return {
            "total_missing": total_missing,
            "would_stage": len(words_to_stage),
            "dry_run": True,
            "sample": words_to_stage[:20],
        }

    # Initialize client for LLM-based definitions
    client = LinguisticClient(model=model, db_path=db_path, debug=debug)

    staged = 0
    skipped_already_pending = 0
    failed = 0

    try:
        for i, word_info in enumerate(words_to_stage, 1):
            word = word_info["word"]
            rank = word_info["overall_rank"]
            logger.info(f"\n[{i}/{len(words_to_stage)}] Staging: '{word}' (rank: {rank})")

            # Check if already in pending_imports
            if find_pending_import(session, word) is not None:
                logger.info(f"Word '{word}' already in pending imports, skipping")
                skipped_already_pending += 1
                continue

            # Query LLM for definition and translation
            # Use the linguistic client to get comprehensive word data
            definitions_list, success = client.query_definitions(word)
            if not success:
                logger.error(f"Failed to get definitions for '{word}'")
                failed += 1
                if i < len(words_to_stage):
                    time.sleep(throttle)
                continue

            word_data = {"definitions": definitions_list}

            if not word_data or "definitions" not in word_data:
                logger.error(f"Failed to get definitions for '{word}'")
                failed += 1
                if i < len(words_to_stage):
                    time.sleep(throttle)
                continue

            # Create a pending import per sense worth adding. The LLM returns
            # every sense it can think of, including marginal ones, so keep the
            # prominent handful rather than all of them.
            all_definitions = word_data.get("definitions", [])
            definitions = select_senses_to_add(all_definitions)
            if len(definitions) < len(all_definitions):
                kept_ids = {id(d) for d in definitions}
                dropped = [
                    f"{d.get('definition', '')[:40]} ({d.get('sense_prominence', 'unrated')})"
                    for d in all_definitions
                    if id(d) not in kept_ids
                ]
                logger.info(
                    f"'{word}': keeping {len(definitions)} of {len(all_definitions)} senses; "
                    f"skipped {'; '.join(dropped)}"
                )
            for definition_data in definitions:
                definition_text = definition_data.get("definition", "")
                # The schema uses "pos" not "pos_type"
                pos_type = definition_data.get("pos", None)
                pos_subtype = definition_data.get("pos_subtype", None)

                # Get translation for disambiguation. The schema keys are LLM
                # field names ("lithuanian_translation"), not language codes, so
                # map through LANG_CODE_TO_LLM_FIELD rather than building
                # f"{target_language}_translation" -- that produced
                # "lt_translation", which never matched, so the disambiguation
                # translation was always empty.
                translation_key = LANG_CODE_TO_LLM_FIELD[target_language]
                translation = definition_data.get(translation_key, "")

                if not definition_text:
                    logger.warning(f"Missing definition for '{word}', skipping this sense")
                    continue

                # Translation is optional - we can use definition as fallback for disambiguation
                if not translation:
                    logger.debug(
                        f"No {target_language} translation for '{word}', will use definition for disambiguation"
                    )

                create_pending_import(
                    session,
                    english_word=word,
                    definition=definition_text,
                    disambiguation_translation=translation,
                    disambiguation_language=target_language,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    source="dramblys_frequency_check",
                    frequency_rank=rank,
                    notes="Found in top frequency words",
                )
                staged += 1
                logger.info(
                    f"Staged '{word}' ({pos_type}/{pos_subtype}): {definition_text[:60]}..."
                )

            session.commit()

            # Throttle to avoid overloading the API
            if i < len(words_to_stage):
                time.sleep(throttle)

    except Exception as e:
        logger.error(f"Error during staging: {e}")
        session.rollback()
        return {
            "error": str(e),
            "total_missing": total_missing,
            "staged": staged,
            "skipped_already_pending": skipped_already_pending,
            "failed": failed,
            "dry_run": dry_run,
        }

    logger.info(f"\n{'='*60}")
    logger.info(f"Staging complete:")
    logger.info(f"  Total missing: {total_missing}")
    logger.info(f"  Processed: {len(words_to_stage)}")
    logger.info(f"  Staged: {staged}")
    logger.info(f"  Skipped (already pending): {skipped_already_pending}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*60}")

    return {
        "total_missing": total_missing,
        "processed": len(words_to_stage),
        "staged": staged,
        "skipped_already_pending": skipped_already_pending,
        "failed": failed,
        "dry_run": dry_run,
    }
