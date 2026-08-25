"""Turn a staged term into the thing it actually is, or reject it.

Approval routes on ``PendingImport.target_kind``:

* **lemma** -- the expensive path. Queries an LLM for full definitions
  (including the subtype the GUID is built from), skips senses that already
  exist, and hands off to ``wordfreq.translation.word_processing``.
* **name** -- no LLM call. A proper name needs a row in ``names`` and nothing
  else; its per-language renderings are generated later, by the same machinery
  that handles names the dialog generator invented.
* **concept** -- no LLM call either. An encyclopedia entry is created with its
  title and summary; the body is written later by the concept generator.

Deletion of the pending row goes through :func:`delete_pending_import` in every
case, including rejection and the "Use As Synonym" path in Barsukas. That is
deliberate: the row is referenced by synonym candidates, by sentence links, and
(in older databases) by word hints, and having one choke point is what stopped
each caller from having to remember all three.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.backend.config import DataSourceConfig
from storage.crud.concept import create_concept, get_concept_by_slug
from storage.crud.lemma_tags import add_tags, read_pending_import_tags
from storage.crud.name_entity import get_or_create_name
from storage.models.concept import normalize_concept_slug
from storage.models.imports import (
    TARGET_KIND_CONCEPT,
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    PendingImport,
    WordExclusion,
)
from storage.models.name_entity import NAME_KINDS, normalize_name_text
from storage.models.schema import Lemma
from util.logging_config import get_logger
from words.emoji import attach_pending_emoji_to_lemma, release_pending_emoji
from words.pending_imports.classification import DEFAULT_NAME_KIND
from words.pending_imports.sentence_links import (
    release_legacy_hints,
    resolve_sentence_links,
)
from words.pending_imports.synonym_screening import has_active_strong_synonym_candidate
from wordfreq.translation.client import LinguisticClient

logger = get_logger(__name__)


def _find_duplicate_lemma(
    session: Any,
    word: str,
    pos_type: Optional[str],
    pos_subtype: Optional[str],
) -> Optional[Any]:
    """Check if a lemma already exists for this word/POS/subtype combination.

    Matches both the lemma text itself and any alternate spelling recorded for
    it, so approving a pending "grey" resolves to the existing "gray" lemma
    instead of creating a duplicate concept under the other spelling.

    Returns the first matching Lemma, or None if no duplicate found.
    """
    from storage.models.variant_form import VariantForm

    normalized = word.strip().lower()

    def _apply_pos_filters(query: Any) -> Any:
        if pos_type:
            query = query.filter(Lemma.pos_type == pos_type)
        if pos_subtype:
            query = query.filter(Lemma.pos_subtype == pos_subtype)
        return query

    direct_match = _apply_pos_filters(
        session.query(Lemma).filter(func.lower(Lemma.lemma_text) == normalized)
    ).first()
    if direct_match is not None:
        return direct_match

    variant_match = _apply_pos_filters(
        session.query(Lemma)
        .join(VariantForm, VariantForm.lemma_id == Lemma.id)
        .filter(func.lower(VariantForm.variant_form_text) == normalized)
    ).first()
    return variant_match


def delete_pending_import(
    session: Session,
    pending: PendingImport,
    *,
    lemma_id: Optional[int] = None,
    name_id: Optional[int] = None,
) -> None:
    """Remove a pending row, settling everything that referenced it.

    The single exit from the pending queue, whatever the reason: approved into
    a lemma, accepted as a synonym of an existing one, promoted to a name or a
    concept, or rejected outright. In order:

    1. sentences that were waiting on the term get the outcome applied to their
       word rows, so the word is *linked* and not merely un-staged;
    2. hint rows from before the link table existed are repointed or dropped,
       since their foreign key has no ON DELETE behavior;
    3. emoji staged against the term settle: glyphs parked as ``missing_lemma``
       attach to the lemma when there is one, and otherwise go back to
       ``undecided`` for the review walk to offer again. This must happen here
       rather than in the callers -- ``Emoji.pending_import_id`` is ``ON DELETE
       SET NULL``, so once step 4 runs the link is gone and the glyph would be
       stranded in ``missing_lemma`` forever;
    4. the row goes, taking its synonym candidates and sentence links with it
       through the ORM cascades.

    Does not commit; the caller owns the transaction.

    Args:
        session: Database session.
        pending: The row to remove.
        lemma_id: Lemma the term became, when it became one.
        name_id: Name the term became, when it became one. A rejection, and a
            promotion to a concept, pass neither.
    """
    pending_import_id = int(pending.id)
    resolve_sentence_links(session, pending_import_id, lemma_id=lemma_id, name_id=name_id)
    release_legacy_hints(session, pending_import_id, lemma_id=lemma_id, name_id=name_id)

    lemma = session.get(Lemma, lemma_id) if lemma_id is not None else None
    if lemma is not None:
        attach_pending_emoji_to_lemma(session, pending_import_id, lemma)
    else:
        release_pending_emoji(session, pending_import_id)

    session.delete(pending)
    session.flush()


def approve_as_name(session: Session, pending: PendingImport) -> Dict[str, Any]:
    """Turn a staged term into a :class:`~storage.models.name_entity.Name`.

    No LLM call: a name needs text and a kind, and both are already on the row
    (or default to "other"). Existing names are reused rather than duplicated,
    which is what keeps a character's renderings stable across sentences.

    Does not commit.
    """
    word = pending.english_word
    kind = pending.name_kind if pending.name_kind in NAME_KINDS else DEFAULT_NAME_KIND

    name, created = get_or_create_name(
        session,
        name_text=normalize_name_text(word),
        kind=kind,
        source_model=pending.source,
        notes=f"Approved from pending import #{pending.id}",
        source="pending-import/approve",
    )
    name_id = int(name.id)
    delete_pending_import(session, pending, name_id=name_id)

    action = "Created" if created else "Reused existing"
    message = f"{action} name '{name.name_text}' ({name.kind_label})"
    logger.info("%s for pending import (name_id=%s)", message, name_id)
    return {
        "success": True,
        "word": word,
        "target_kind": TARGET_KIND_NAME,
        "name_id": name_id,
        "created": created,
        "message": message,
    }


def approve_as_concept(session: Session, pending: PendingImport) -> Dict[str, Any]:
    """Turn a staged term into a :class:`~storage.models.concept.Concept`.

    The entry is created with its title and the staged gloss as the summary;
    the body is generated later by the concept generator, which is where every
    other concept's body comes from. An existing concept with the same slug is
    reused, so approving the same term twice is harmless.

    ``create_concept`` commits internally, so this function's caller sees the
    concept persisted even if a later step fails -- which is correct: the
    concept is real, and re-running must not try to create it twice.
    """
    word = pending.english_word
    slug = normalize_concept_slug(word)
    if not slug:
        return {
            "success": False,
            "word": word,
            "error": f"'{word}' does not produce a usable concept slug",
        }

    concept = get_concept_by_slug(session, slug)
    created = False
    if concept is None:
        concept = create_concept(
            session,
            title=word,
            summary=pending.definition,
            concept_type=pending.concept_type,
            source_model=pending.source,
            notes=f"Approved from pending import #{pending.id}",
        )
        created = concept is not None

    if concept is None:
        return {
            "success": False,
            "word": word,
            "error": f"Could not create a concept for '{word}'",
        }

    concept_id = int(concept.id)
    # Neither a lemma nor a name, so sentences waiting on the term get no link
    # written; ``unlinked_words`` skips words that are known concepts, which is
    # what keeps those sentences from staging the term again.
    delete_pending_import(session, pending)

    action = "Created" if created else "Reused existing"
    message = f"{action} concept '{concept.title}'"
    logger.info("%s for pending import (concept_id=%s)", message, concept_id)
    return {
        "success": True,
        "word": word,
        "target_kind": TARGET_KIND_CONCEPT,
        "concept_id": concept_id,
        "created": created,
        "message": message,
    }


def approve_as_lemma(
    session: Any,
    pending: PendingImport,
    data_source_config: DataSourceConfig,
    model: str = "gpt-5.4-mini",
    debug: bool = False,
) -> Dict[str, Any]:
    """Convert a staged term into a full Lemma/DerivativeForm entry.

    Queries the LLM for full definitions (including pos_subtype and
    translations), checks for duplicate lemmas, then creates the lemma with a
    proper GUID. Commits, since ``process_word`` writes through its own session.
    """
    pending_import_id = int(pending.id)
    word = pending.english_word
    pending_definition = pending.definition
    pending_pos_type = pending.pos_type
    pending_pos_subtype = pending.pos_subtype
    # Read before the pending row is deleted below; applied to the lemma
    # once process_word() has created it.
    pending_tags = read_pending_import_tags(pending)

    logger.info(f"Approving word '{word}' (sense: {pending_definition[:60]}...)")

    # Use LinguisticClient to get full definitions from the LLM, including
    # pos_subtype (needed for GUID) and translations.
    client_config = data_source_config.with_model(model, debug=debug)
    client = LinguisticClient(config=client_config)

    example_sentence: Optional[str] = pending.example_sentence

    # Rated at staging time, when it was rated at all. The pre-staged branch
    # below makes no LLM call, so this is the only place that rating can come
    # from; on the LLM branch it overrides the fresh answer, since a human may
    # have corrected it on the detail page.
    pending_prominence: Optional[str] = pending.sense_prominence

    if pending_pos_type and pending_pos_subtype:
        # Already staged via the detail page — use stored values to avoid a redundant LLM call.
        logger.info(f"Using pre-staged data for '{word}': {pending_pos_type}/{pending_pos_subtype}")
        definitions_list: List[Dict[str, Any]] = [
            {
                "pos": pending_pos_type,
                "pos_subtype": pending_pos_subtype,
                "definition": pending_definition,
                "lemma": word,
                "sense_prominence": pending_prominence,
            }
        ]
    else:
        definitions_list, llm_success = client.query_definitions(
            word, example_sentence=example_sentence
        )
        if not llm_success or not definitions_list:
            logger.error(f"LLM query for definitions of '{word}' failed")
            return {
                "success": False,
                "word": word,
                "error": f"Failed to get definitions from LLM for '{word}'",
            }

        # If the pending import has a pos_type, keep only definitions that
        # match that POS so we don't create unrelated senses.
        if pending_pos_type:
            matching_defs = [d for d in definitions_list if d.get("pos") == pending_pos_type]
            # Fall back to the full list if nothing matched (LLM may use
            # slightly different POS labels).
            if matching_defs:
                definitions_list = matching_defs

    # Check for duplicates: for each definition the LLM returned, see if a
    # lemma with the same word + POS type + subtype already exists.
    filtered_definitions: List[Dict[str, Any]] = []
    for def_data in definitions_list:
        llm_pos_type = def_data.get("pos")
        llm_pos_subtype = def_data.get("pos_subtype")
        existing = _find_duplicate_lemma(session, word, llm_pos_type, llm_pos_subtype)
        if existing:
            logger.info(
                f"Skipping duplicate: '{word}' already exists as "
                f"{llm_pos_type}/{llm_pos_subtype} (lemma id={existing.id}, "
                f"guid={existing.guid})"
            )
        else:
            if pending_prominence and not def_data.get("sense_prominence"):
                def_data["sense_prominence"] = pending_prominence
            filtered_definitions.append(def_data)

    if not filtered_definitions:
        # Every sense already exists — remove the pending import and report.
        # Any sentence waiting on this word is repointed at the lemma that
        # already covers it, so the wait ends rather than dangling.
        existing_lemma = (
            session.query(Lemma).filter(func.lower(Lemma.lemma_text) == word.lower()).first()
        )
        delete_pending_import(
            session, pending, lemma_id=existing_lemma.id if existing_lemma else None
        )
        session.commit()
        msg = f"'{word}' already exists in the database for all senses; removed from pending."
        logger.info(msg)
        return {"success": True, "word": word, "target_kind": TARGET_KIND_LEMMA, "message": msg}

    try:
        from wordfreq.translation import word_processing

        success = word_processing.process_word(
            client.client,
            word,
            client.get_session,
            refresh=False,
            definitions_list=filtered_definitions,
        )
    except ValueError as e:
        # Handle subtype validation errors
        if "Unknown subtype" in str(e):
            logger.error(f"Subtype validation error for '{word}': {e}")
            logger.error("The LLM returned an invalid subtype. This word needs manual review.")
            return {"success": False, "word": word, "error": f"Invalid subtype: {e}"}
        raise

    if not success:
        logger.error(f"Failed to import '{word}'")
        return {"success": False, "word": word, "error": f"Failed to import '{word}'"}

    # Look up the newly created lemma so callers can trigger follow-on tasks.
    # Done before the delete so any sentence waiting on this pending import can
    # be repointed at the lemma it just became.
    new_lemma = (
        session.query(Lemma).filter(Lemma.lemma_text == word).order_by(Lemma.id.desc()).first()
    )
    new_lemma_id: Optional[int] = new_lemma.id if new_lemma else None

    delete_pending_import(session, pending, lemma_id=new_lemma_id)
    session.commit()

    # Carry any tags staged on the pending import onto the new lemma, so
    # a corpus ingested with `genys --tags legal` needs no second pass.
    if new_lemma is not None and pending_tags:
        add_tags(session, new_lemma, pending_tags, source="pending-import-approval")
        session.commit()

    logger.info(f"Successfully approved and imported '{word}' (lemma_id={new_lemma_id})")
    logger.debug("Pending import %s consumed", pending_import_id)
    return {
        "success": True,
        "word": word,
        "target_kind": TARGET_KIND_LEMMA,
        "lemma_id": new_lemma_id,
        "message": f"Successfully imported '{word}'",
    }


def approve_pending_import(
    session: Any,
    pending_import_id: int,
    data_source_config: DataSourceConfig,
    model: str = "gpt-5.4-mini",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Approve a pending import, creating whatever its ``target_kind`` says it is.

    This is step 2 of the two-step import process. Names and concepts settle
    without an LLM call; only the lemma path pays for one.

    Args:
        session: Database session
        pending_import_id: ID of the PendingImport record
        data_source_config: Data source configuration for LinguisticClient
        model: LLM model to use for processing (lemma path only)
        debug: Debug flag

    Returns:
        Dictionary with approval results. ``target_kind`` names the path taken.
    """
    logger.info(f"Approving pending import ID {pending_import_id}...")

    try:
        pending = session.query(PendingImport).filter(PendingImport.id == pending_import_id).first()

        if not pending:
            logger.error(f"Pending import ID {pending_import_id} not found")
            return {"error": f"Pending import ID {pending_import_id} not found", "success": False}

        target_kind = pending.target_kind or TARGET_KIND_LEMMA

        # Synonym screening compares a term against existing *lemmas*, so it
        # only gates the lemma path: a name or a concept is not a duplicate of
        # a word that happens to be spelled like it.
        if target_kind == TARGET_KIND_LEMMA and has_active_strong_synonym_candidate(
            session, pending_import_id
        ):
            logger.info(
                "Pending import ID %s has active strong synonym candidates; refusing normal approval",
                pending_import_id,
            )
            return {
                "success": False,
                "word": pending.english_word,
                "error": (
                    "Strong synonym candidates exist. Use 'Use As Synonym' or "
                    "'Create Anyway' from the pending import detail page."
                ),
            }

        if target_kind == TARGET_KIND_NAME:
            result = approve_as_name(session, pending)
            session.commit()
            return result

        if target_kind == TARGET_KIND_CONCEPT:
            result = approve_as_concept(session, pending)
            session.commit()
            return result

        return approve_as_lemma(session, pending, data_source_config, model=model, debug=debug)

    except Exception as e:
        logger.error(f"Error approving pending import: {e}")
        session.rollback()
        return {"error": str(e), "success": False}


def reject_pending_import(
    session: Any,
    pending_import_id: int,
    reason: str = "manual_rejection",
    add_to_exclusions: bool = True,
) -> Dict[str, Any]:
    """
    Reject a pending import and optionally add to exclusions list.

    A rejected term becomes nothing, so any sentence waiting on it has its link
    dropped rather than resolved -- the word stays unlinked and the sentence is
    free to stage it again if it reappears.

    Args:
        session: Database session
        pending_import_id: ID of the PendingImport record
        reason: Reason for rejection
        add_to_exclusions: If True, add to WordExclusion table

    Returns:
        Dictionary with rejection results
    """
    logger.info(f"Rejecting pending import ID {pending_import_id}...")

    try:
        pending = session.query(PendingImport).filter(PendingImport.id == pending_import_id).first()

        if not pending:
            logger.error(f"Pending import ID {pending_import_id} not found")
            return {"error": f"Pending import ID {pending_import_id} not found", "success": False}

        word = pending.english_word

        # Add to exclusions if requested
        if add_to_exclusions:
            existing_exclusion = (
                session.query(WordExclusion)
                .filter(WordExclusion.excluded_word == word, WordExclusion.language_code == "en")
                .first()
            )

            if not existing_exclusion:
                exclusion = WordExclusion(
                    excluded_word=word,
                    language_code="en",
                    exclusion_reason=reason,
                    notes=f"Rejected from pending import. Original definition: {pending.definition[:100]}",
                )
                session.add(exclusion)
                logger.info(f"Added '{word}' to exclusions")

        delete_pending_import(session, pending)
        session.commit()

        logger.info(f"Rejected pending import for '{word}'")
        return {
            "success": True,
            "word": word,
            "added_to_exclusions": add_to_exclusions,
            "message": f"Rejected '{word}'",
        }

    except Exception as e:
        logger.error(f"Error rejecting pending import: {e}")
        session.rollback()
        return {"error": str(e), "success": False}
