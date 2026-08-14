"""Decide what a staged term should become: a lemma, a name, or a concept.

Every pending import is one of three things, and until this module existed the
answer was always "lemma" -- so "George" and "World War II" were staged as
vocabulary and either became junk lemmas or sat in the queue forever.

The three destinations are genuinely different tables with different rules:

* a **lemma** is vocabulary, gets a GUID and a difficulty level, and is
  exported to ``data/release``;
* a **name** is a proper name used in our texts, carries no difficulty, and is
  skipped in a sentence's level rollup;
* a **concept** is an encyclopedia entry, keyed by slug, outside the
  lemma/GUID machinery entirely.

Classification runs in two tiers, cheap first:

1. :func:`suggest_target_kind` -- a pure database/shape check with no LLM call.
   It answers confidently when the term already exists as a name, a concept, or
   a lemma, and otherwise reads the term's capitalization. Every staging path
   calls this, so a proper noun is marked at staging time rather than after a
   human notices it.
2. :func:`classify_pending_import` -- one structured LLM call, used from the
   Barsukas stage step where an LLM call is already being made. It is the only
   thing that can reliably separate a name from a concept, and it is what fills
   in ``name_kind`` and ``concept_type``.

The rule tier never overrides a decision already stored on the row: once a
human (or the LLM tier) has said what a term is, re-staging must not undo it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from clients.types import Schema, SchemaProperty
from storage.crud.concept import get_concept_by_slug
from storage.crud.name_entity import find_name
from storage.models.concept import normalize_concept_slug
from storage.models.imports import (
    PENDING_IMPORT_TARGET_KINDS,
    TARGET_KIND_CONCEPT,
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    PendingImport,
)
from storage.models.name_entity import NAME_GENDERS, NAME_KINDS, normalize_name_text
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)

# Fallback name kind when nothing determined a better one. "other" is honest:
# the alternative is guessing between given_name and place from the text alone.
DEFAULT_NAME_KIND: str = "other"

# Confidence attached to a rule-tier verdict. A database hit is treated as
# certain; a capitalization read is a suggestion the LLM tier may overrule.
RULE_CONFIDENCE_EXISTING: float = 1.0
RULE_CONFIDENCE_SHAPE: float = 0.5

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")


@dataclass(frozen=True)
class TargetKindSuggestion:
    """What the rule tier thinks a term should become, and why."""

    target_kind: str
    name_kind: Optional[str] = None
    # Gender hint for a personal name, one of NAME_GENDERS. Only the LLM tier
    # produces it; names created without one simply carry NULL.
    gender: Optional[str] = None
    concept_type: Optional[str] = None
    confidence: float = RULE_CONFIDENCE_SHAPE
    reason: str = ""

    @property
    def is_certain(self) -> bool:
        """True when the verdict came from an existing row, not from shape."""
        return self.confidence >= RULE_CONFIDENCE_EXISTING


def is_valid_target_kind(target_kind: str) -> bool:
    """Return True when ``target_kind`` is part of the closed vocabulary."""
    return target_kind in PENDING_IMPORT_TARGET_KINDS


def looks_like_proper_noun(term: str, example_sentence: Optional[str] = None) -> bool:
    """True when the term's capitalization marks it as a proper noun.

    Capitalization is only evidence when it is not forced by position: a term
    that starts its example sentence is capitalized for that reason alone, so
    it is read as ordinary vocabulary unless something else marks it. A term
    with an inner capital ("McDonald", "iPhone") or several capitalized words
    ("World War") is proper regardless of where it sits.
    """
    stripped = term.strip()
    if not stripped:
        return False

    words = _WORD_RE.findall(stripped)
    if not words:
        return False

    capitalized = [word for word in words if word[:1].isupper()]
    if not capitalized:
        return False

    # Inner capitals, or more than one capitalized word, are position-independent.
    if len(capitalized) > 1:
        return True
    if any(character.isupper() for character in stripped[1:] if character.isalpha()):
        return True

    if example_sentence:
        first = _WORD_RE.search(example_sentence.strip())
        if first is not None and first.group(0).casefold() == words[0].casefold():
            # The only capital is the one the sentence start would have forced.
            return False

    return True


def suggest_target_kind(
    session: Session,
    term: str,
    *,
    example_sentence: Optional[str] = None,
    pos_type: Optional[str] = None,
) -> TargetKindSuggestion:
    """Classify a term without an LLM call.

    Checks what the database already knows before reading the term's shape, so
    a term we have already decided about is classified the same way twice.

    Args:
        session: Database session (read-only).
        term: The English term being staged.
        example_sentence: Sentence the term was seen in, when there is one.
            Used to tell a forced sentence-initial capital from a real one.
        pos_type: Part of speech the caller expects, when known. A term with a
            verb/adjective/adverb reading is vocabulary whatever its
            capitalization, so the shape check is skipped for those.

    Returns:
        A :class:`TargetKindSuggestion`.
    """
    normalized = term.strip()
    if not normalized:
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_LEMMA,
            confidence=RULE_CONFIDENCE_SHAPE,
            reason="empty term",
        )

    existing_name = find_name(session, normalize_name_text(normalized))
    if existing_name is not None:
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_NAME,
            name_kind=existing_name.kind,
            confidence=RULE_CONFIDENCE_EXISTING,
            reason=f"already a name (#{existing_name.id})",
        )

    concept = get_concept_by_slug(session, normalize_concept_slug(normalized))
    if concept is not None:
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_CONCEPT,
            concept_type=concept.concept_type,
            confidence=RULE_CONFIDENCE_EXISTING,
            reason=f"already a concept ({concept.slug})",
        )

    lemma_exists = (
        session.query(Lemma.id).filter(func.lower(Lemma.lemma_text) == normalized.lower()).first()
        is not None
    )
    if lemma_exists:
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_LEMMA,
            confidence=RULE_CONFIDENCE_EXISTING,
            reason="already a lemma",
        )

    # A word with a verb, adjective, or adverb reading is vocabulary; only
    # nouns (and terms with no part of speech at all) can be names or concepts.
    if pos_type and pos_type not in ("noun", "unknown"):
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_LEMMA,
            confidence=RULE_CONFIDENCE_SHAPE,
            reason=f"part of speech {pos_type} is vocabulary",
        )

    if looks_like_proper_noun(normalized, example_sentence):
        return TargetKindSuggestion(
            target_kind=TARGET_KIND_NAME,
            confidence=RULE_CONFIDENCE_SHAPE,
            reason="capitalization suggests a proper noun",
        )

    return TargetKindSuggestion(
        target_kind=TARGET_KIND_LEMMA,
        confidence=RULE_CONFIDENCE_SHAPE,
        reason="ordinary vocabulary",
    )


# ---------------------------------------------------------------------- #
# LLM tier                                                                #
# ---------------------------------------------------------------------- #


def build_classification_schema() -> Schema:
    """Structured-response schema for the term classification call."""
    return Schema(
        name="PendingImportClassification",
        description="What a staged English term should become",
        properties={
            "target_kind": SchemaProperty(
                "string",
                "Which table this term belongs in",
                enum=list(PENDING_IMPORT_TARGET_KINDS),
            ),
            "name_kind": SchemaProperty(
                "string",
                "For a name, what sort of name it is; omit for other kinds",
                required=False,
                enum=list(NAME_KINDS),
            ),
            "gender": SchemaProperty(
                "string",
                "For a personal name, the gender it usually implies; omit otherwise",
                required=False,
                enum=list(NAME_GENDERS),
            ),
            "concept_type": SchemaProperty(
                "string",
                "For a concept, a coarse type such as event, person, or art_movement",
                required=False,
            ),
            "explanation": SchemaProperty(
                "string", "Brief reason for the classification", required=False
            ),
        },
    )


def build_classification_prompt(pending_import: PendingImport) -> str:
    """Prompt asking an LLM which of the three kinds a term is."""
    context = ""
    if pending_import.example_sentence:
        context = f"\nExample sentence: {pending_import.example_sentence}"
    return (
        "Classify this English term before it is added to a language-learning database.\n\n"
        f"Term: {pending_import.english_word}\n"
        f"Definition or gloss: {pending_import.definition}\n"
        f"Part of speech: {pending_import.pos_type or 'unknown'}"
        f"{context}\n\n"
        "Choose exactly one target:\n"
        "- 'lemma' for ordinary vocabulary a learner studies (dog, run, quickly). "
        "This is the default; prefer it whenever the term is a common word.\n"
        "- 'name' for a proper name of a specific person, place, business, or animal "
        "that a learner does not study as vocabulary (George, Fresh Mart, Rex).\n"
        "- 'concept' for an encyclopedia topic that deserves an article rather than a "
        "dictionary entry (World War II, Art Deco, Mount Everest).\n\n"
        "For 'name', also give name_kind, and gender when the name implies one. "
        "For 'concept', also give a coarse concept_type."
    )


def parse_classification_response(response_data: Dict[str, Any]) -> TargetKindSuggestion:
    """Turn a structured LLM response into a suggestion, discarding junk.

    An unrecognized ``target_kind`` falls back to "lemma" rather than raising:
    the caller is deciding what to *stage*, and staging vocabulary is the
    reversible option.
    """
    raw_kind = response_data.get("target_kind")
    target_kind = raw_kind if isinstance(raw_kind, str) and is_valid_target_kind(raw_kind) else None
    if target_kind is None:
        logger.warning("LLM returned unusable target_kind %r; defaulting to lemma", raw_kind)
        target_kind = TARGET_KIND_LEMMA

    raw_name_kind = response_data.get("name_kind")
    name_kind = (
        raw_name_kind
        if target_kind == TARGET_KIND_NAME
        and isinstance(raw_name_kind, str)
        and raw_name_kind in NAME_KINDS
        else None
    )

    raw_gender = response_data.get("gender")
    gender = (
        raw_gender
        if target_kind == TARGET_KIND_NAME
        and isinstance(raw_gender, str)
        and raw_gender in NAME_GENDERS
        else None
    )

    raw_concept_type = response_data.get("concept_type")
    concept_type = (
        raw_concept_type.strip()
        if target_kind == TARGET_KIND_CONCEPT
        and isinstance(raw_concept_type, str)
        and raw_concept_type.strip()
        else None
    )

    explanation = response_data.get("explanation")
    return TargetKindSuggestion(
        target_kind=target_kind,
        name_kind=name_kind,
        gender=gender,
        concept_type=concept_type,
        confidence=RULE_CONFIDENCE_EXISTING,
        reason=explanation if isinstance(explanation, str) else "",
    )


def query_classification_llm(
    llm_client: Any, pending_import: PendingImport, *, model: str
) -> Dict[str, Any]:
    """Ask an LLM which of the three kinds a staged term is."""
    response = llm_client.generate_chat(
        prompt=build_classification_prompt(pending_import),
        model=model,
        json_schema=build_classification_schema(),
    )
    structured_data = getattr(response, "structured_data", None)
    if not isinstance(structured_data, dict):
        raise ValueError("LLM returned no structured classification data")
    return structured_data


def apply_suggestion(pending_import: PendingImport, suggestion: TargetKindSuggestion) -> bool:
    """Write a suggestion onto a pending row. Returns True when it changed.

    Only the fields the suggestion actually determined are written: a name
    classification does not blank out a ``concept_type`` a previous pass
    stored, it just stops being the field that matters.
    """
    changed = False
    if pending_import.target_kind != suggestion.target_kind:
        pending_import.target_kind = suggestion.target_kind
        changed = True
    if suggestion.name_kind and pending_import.name_kind != suggestion.name_kind:
        pending_import.name_kind = suggestion.name_kind
        changed = True
    if suggestion.concept_type and pending_import.concept_type != suggestion.concept_type:
        pending_import.concept_type = suggestion.concept_type
        changed = True
    return changed


def classify_pending_import(
    session: Session,
    pending_import: PendingImport,
    llm_client: Any,
    *,
    model: str,
) -> TargetKindSuggestion:
    """Classify a staged term with one LLM call and store the verdict.

    Falls back to the rule tier when the call fails, so a classification step
    that cannot reach a model still leaves the row usable rather than blocking
    the stage. Does not commit; the caller owns the transaction.

    Returns:
        The suggestion that was applied.
    """
    try:
        suggestion = parse_classification_response(
            query_classification_llm(llm_client, pending_import, model=model)
        )
    except Exception as exc:
        logger.warning(
            "Classification failed for pending import %s (%s): %s",
            pending_import.id,
            pending_import.english_word,
            exc,
        )
        suggestion = suggest_target_kind(
            session,
            pending_import.english_word,
            example_sentence=pending_import.example_sentence,
            pos_type=pending_import.pos_type,
        )

    apply_suggestion(pending_import, suggestion)
    session.flush()
    return suggestion


def describe_target_kinds() -> Sequence[str]:
    """The closed vocabulary, for CLI help text and select options."""
    return PENDING_IMPORT_TARGET_KINDS
