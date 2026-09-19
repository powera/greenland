#!/usr/bin/python3

"""Add one fully specified English term, generating only its translations.

This is the third add path, and it exists for terms the sense-discovery
pipeline cannot handle:

* :func:`words.add_word.add_word` takes a bare word and asks the LLM what its
  senses are, which POS each is, and how to translate them. It is the right
  path for ordinary vocabulary and the wrong one for a borrowed term -- asked
  about "ex post facto" it tries to find a native English headword and a
  sense inventory that do not exist.
* ``POST /api/v1/lemmas/add`` takes everything pre-specified, including the
  translations, and makes no LLM call at all.

:func:`add_term` sits between them: the caller supplies the term, its POS,
subtype and definition -- the facts a curated wordlist already knows and the
model would only get wrong -- and the LLM is asked for the translations alone.

Exactly one lemma is created per call. There is no sense selection here: the
caller has already decided that this term is one sense, which is what makes
the path safe for a term whose senses the model cannot enumerate.

Latin and Law French legal terms are the motivating case. No untranslatability
marking is involved: a term that every Romance language borrows unchanged comes
back as itself in each of them, which is a correct translation rather than an
absent one.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.backend.config import DataSourceConfig
from storage.crud.operation_log import log_translation_change
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.schema import Lemma
from storage.queries.lemma import word_exists_in_english
from storage.translation_helpers import set_translation
from storage.utils.guid import generate_guid
from words.translation import build_term_translation_prompt

logger = logging.getLogger(__name__)

# Same target set the definitions call covers (DEFINITIONS_PROMPT_LANGUAGES), so
# a term added this way and a word added through add_word end up with the same
# languages populated. Spelled out rather than imported from
# wordfreq.translation.definitions: this module is re-exported from
# words/__init__, and importing the wordfreq.translation package from here runs
# its __init__, which imports the client, which imports back into words --
# a cycle. A test below asserts the two stay equal.
TRANSLATION_LANGUAGES: Tuple[str, ...] = ("lt", "es", "es-419", "fr", "zh")

# Matches add_word: a term with no caller-supplied level is created unset
# rather than guessed at.
DIFFICULTY_LEVEL = -1


@dataclass
class AddTermResult:
    """What one :func:`add_term` call did.

    ``status`` is one of:

    * ``"created"``      -- the lemma was written; ``guid`` names it.
    * ``"already_exists"`` -- the term was already accounted for; nothing written.
    * ``"error"``        -- nothing was written; ``error`` says why.
    """

    term: str
    status: str
    guid: Optional[str] = None
    translations: Dict[str, str] = field(default_factory=dict)
    missing_languages: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _validate_pos(pos_type: str, pos_subtype: str) -> Optional[str]:
    """Return an error string if the POS pair cannot produce a GUID.

    The same binding constraint add_word applies: a lemma needs a GUID, and
    ``guid_prefixes`` is what decides whether one can be minted.
    """
    if pos_type not in SUBTYPE_GUID_PREFIXES:
        return f"pos_type {pos_type!r} has no GUID prefix; not a lemma pos_type"
    if pos_subtype not in SUBTYPE_GUID_PREFIXES[pos_type]:
        return f"invalid pos_subtype {pos_subtype!r} for {pos_type!r}"
    return None


def add_term(
    session: Session,
    term: str,
    *,
    pos_type: str,
    pos_subtype: str,
    definition: str,
    config: DataSourceConfig,
    difficulty_level: Optional[int] = DIFFICULTY_LEVEL,
    tags: Optional[List[str]] = None,
    source: str = "add_term",
    client: Optional[Any] = None,
) -> AddTermResult:
    """Create one lemma for a fully specified term, translating it with the LLM.

    Args:
        session: Database session. Committed on success.
        term: The English term, which may be several words.
        pos_type: Part of speech; must have a GUID prefix.
        pos_subtype: Subtype driving the GUID.
        definition: What the term means. Required -- it is what tells the model
            which sense to translate, and a borrowed term's sense cannot be
            inferred from its surface form.
        config: Data source configuration, per CLAUDE.md.
        difficulty_level: Level to stamp on the lemma. Passed at creation
            rather than patched afterwards, for the reason add_word documents:
            a later patch can fail once the lemma is committed, stranding it
            where the existence guard counts it as done.
        tags: Free-form tags to apply, e.g. ``["legal"]``.
        source: Provenance recorded in the operation log.
        client: Pre-built LLM client, for tests.

    Returns:
        An :class:`AddTermResult`. **Makes one LLM call and costs money.**
    """
    normalized = " ".join(term.split())
    if not normalized:
        return AddTermResult(term=term, status="error", error="term must not be empty")

    definition_text = definition.strip()
    if not definition_text:
        return AddTermResult(
            term=normalized, status="error", error="definition is required for a term"
        )

    pos_error = _validate_pos(pos_type, pos_subtype)
    if pos_error is not None:
        return AddTermResult(term=normalized, status="error", error=pos_error)

    # The same guard add_word uses, so the two paths agree about what counts as
    # already present: lemmas, disambiguated lemmas, English derivative forms
    # and alternate spellings all count.
    if word_exists_in_english(session, normalized):
        return AddTermResult(term=normalized, status="already_exists")

    # Imported here rather than at module scope so that importing this module
    # does not construct a client; add_word does the same.
    from wordfreq.translation.client import LinguisticClient

    translation_client = client
    if translation_client is None:
        translation_client = LinguisticClient(config=config).client

    context, prompt, schema = build_term_translation_prompt(
        term=normalized,
        definition=definition_text,
        pos_type=pos_type,
        target_languages=TRANSLATION_LANGUAGES,
    )

    resolved_model = config.model
    try:
        response = translation_client.generate_chat(
            prompt=prompt,
            model=resolved_model,
            json_schema=schema,
            context=context,
        )
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        logger.error("Translation call failed for term '%s': %s", normalized, error)
        return AddTermResult(term=normalized, status="error", error=str(error))

    structured = response.structured_data
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except json.JSONDecodeError as error:
            return AddTermResult(
                term=normalized, status="error", error=f"Invalid JSON response: {error}"
            )
    if not isinstance(structured, dict):
        return AddTermResult(
            term=normalized, status="error", error="Structured response is not an object"
        )

    # A missing language is reported, not fatal: the lemma is still worth
    # creating, and the gap is visible to the translation coverage pass that
    # already exists for exactly this.
    translations: Dict[str, str] = {}
    missing: List[str] = []
    for lang_code in TRANSLATION_LANGUAGES:
        value = structured.get(lang_code)
        if isinstance(value, str) and value.strip():
            translations[lang_code] = value.strip()
        else:
            missing.append(lang_code)

    guid = generate_guid(session, pos_type, pos_subtype)
    new_lemma = Lemma(
        lemma_text=normalized,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        guid=guid,
        difficulty_level=difficulty_level,
        confidence=0.0,
        verified=False,
    )
    session.add(new_lemma)
    session.flush()

    log_translation_change(
        session=session,
        source=source,
        operation_type="lemma_create",
        lemma_id=new_lemma.id,
        language_code="en",
        old_translation=None,
        new_translation=normalized,
        # entity_guid populates the indexed column; guid also goes in the fact,
        # matching the shape add_word's lemma_create entries already have.
        entity_guid=guid,
        guid=guid,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        definition=definition_text,
        model=resolved_model,
    )

    for lang_code, translation in translations.items():
        set_translation(session, new_lemma, lang_code, translation)
        log_translation_change(
            session=session,
            source=source,
            operation_type="translation",
            lemma_id=new_lemma.id,
            language_code=lang_code,
            old_translation=None,
            new_translation=translation,
            entity_guid=guid,
            guid=guid,
            model=resolved_model,
        )

    if tags:
        # Imported here for the same reason as the client: keeps module import
        # free of the wider lemma CRUD surface.
        from storage.crud.lemma_tags import add_tags

        add_tags(session, new_lemma, tags, source=source)

    session.commit()

    if missing:
        logger.warning(
            "Term '%s' created as %s with no translation for: %s",
            normalized,
            guid,
            ", ".join(missing),
        )

    return AddTermResult(
        term=normalized,
        status="created",
        guid=guid,
        translations=translations,
        missing_languages=missing,
    )
