"""Add one domain sense of an English word, given the domain and a hint.

The fourth add path, for a curated list of a field's vocabulary -- a sport or a
game -- where the words are ordinary English but the meanings wanted are not
the ordinary ones:

* :func:`words.add_word.add_word` asks the LLM for every sense of a bare word
  and keeps the prominent ones. Asked about "check" it finds examining and
  verifying; the chess sense is too rare to survive selection. And it never
  gets that far, because "check (examine)" already exists and its existence
  guard stops at the headword.
* :func:`words.add_term.add_term` takes a caller-written definition and
  translates only that, but shares the same headword-level guard.

:func:`add_sense` takes the word, the domain ("chess") and optionally a short
hint ("an attack on the king"), and makes one LLM call that both describes the
domain sense -- POS, subtype, definition, translations -- and answers whether
one of the headword's existing senses already *is* that sense. The existence
question has to be the model's: the chess queen in the database has no
disambiguation, only a definition, and deciding that "the most powerful chess
piece" is the sense asked for is a judgement about meaning, not a string match.

The two questions share a call because the second costs almost nothing once
the model is describing the sense anyway, and asking it separately would pay
for the headword's senses to be read twice.

A sense the model says is already present is tagged rather than duplicated,
and with ``relevel_existing`` it is also moved to the caller's level and given
the caller's disambiguation -- the chess queen, created at a general level
before the chess vocabulary had a home, moves to the chess level.

New senses are stored with ``sense_prominence`` "rare". They are not rare in
their field, but the rating is relative to the headword's other senses, and
it is what keeps "checked" and "checking" in general text from rolling up to
the chess sense.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage.backend.config import DataSourceConfig
from storage.crud.lemma_tags import add_tags, normalize_tags, read_tags
from storage.crud.operation_log import FieldChange, log_field_changes, log_translation_change
from storage.crud.variant_form import add_variant_form
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES, render_subtype_list
from storage.models.schema import SENSE_PROMINENCE_RARE, Lemma
from storage.models.variant_form import VARIANT_KIND_ABBREVIATION
from storage.queries.lemma import get_english_senses
from storage.translation_helpers import (
    LLM_FIELD_TO_LANG_CODE,
    ensure_english_translation,
)
from storage.utils.enums import get_subtype_values_for_pos
from storage.utils.guid import generate_guid
from wordfreq.translation.constants import MAJOR_POS_TYPES, VALID_POS_TYPES
from wordfreq.translation.word_processing import determine_default_grammatical_form
from words.add_word import (
    _needs_subtype_review,
    _normalize_subtype,
    _validate_pos,
)
from words.lemma_creation import (
    TRANSLATION_LANGUAGES,
    attach_english_base_form,
    store_sense_examples,
    store_sense_translations,
)

logger = logging.getLogger(__name__)

# Matches add_word and add_term: without a caller-supplied level the lemma is
# created unset rather than guessed at.
DIFFICULTY_LEVEL = -1

# What the model returns when none of the listed senses is this one. Senses are
# numbered from 1 in the prompt so that 0 can mean "none" without a nullable.
NOT_COVERED = 0

# The open-class catch-all as the subtype lists spell it; _normalize_subtype
# turns it into "<pos>_other".  Withheld from this prompt entirely.  add_word
# queues a catch-all sense for review, but a domain term always has a real
# subtype -- the sports import filed layups and bicycle kicks as noun_other
# when nothing better was on offer -- so here it is not offered at all, and a
# sense that comes back with one anyway is refused rather than written.  The
# closed classes are unaffected: they answer with the bare POS name.
_CATCH_ALL_SUBTYPE = "other"

# Parts of speech with a real choice of subtype, which the second call makes.
# numeral has no catch-all, only cardinal and ordinal; every other closed class
# has "<pos>_other" as its only subtype and needs no call.
_SUBTYPED_POS_TYPES = frozenset({*MAJOR_POS_TYPES, "numeral"})


# A translation the model rates below this is dropped, leaving a gap for the
# translation coverage pass. The model is asked for a confidence per language
# because its doubt is per language: on chess "skewer" luna was sure of the
# Chinese and wrong about the Spanish and French ("clavada" is the pin). A
# literal but non-idiomatic rendering it is sure of is kept; this only catches
# the terms the model knows it does not know.
#
# 0.85 rather than 0.9 after the basketball run: between the two sat mostly real
# terms (lt "užtvara" for a screen, fr "marcher" for traveling), while the
# descriptions passed off as terms (lt "atšokusio kamuolio atkovojimas" for a
# rebound) were rated 0.82 and below.
TRANSLATION_CONFIDENCE_FLOOR = 0.85


def _offered_subtypes(values: Sequence[str]) -> List[str]:
    """``values`` without the open-class catch-all."""
    return [value for value in values if value != _CATCH_ALL_SUBTYPE]


@dataclass
class AddSenseResult:
    """Outcome of an :func:`add_sense` call.

    ``status`` is one of:
      * ``"created"`` -- a new lemma was written; ``guid`` is its GUID
      * ``"covered"`` -- the model matched an existing sense; it was tagged and
        ``guid`` is that sense's GUID
      * ``"moved"`` -- as ``"covered"``, and the sense was also moved to the
        requested level and disambiguation
      * ``"already_exists"`` -- an existing sense already carries the requested
        disambiguation or every requested tag, so no LLM call was made; it is
        tagged, and moved if asked, as a ``"covered"`` sense would be
      * ``"error"`` -- see ``error``; nothing was written
    """

    word: str
    status: str
    guid: Optional[str] = None
    disambiguation: Optional[str] = None
    definition_text: Optional[str] = None
    pos_type: Optional[str] = None
    pos_subtype: Optional[str] = None
    translations: Dict[str, str] = field(default_factory=dict)
    missing_languages: List[str] = field(default_factory=list)
    #: Translations dropped for falling under TRANSLATION_CONFIDENCE_FLOOR, by
    #: language code: ``{"translation": ..., "confidence": ...}``. Each is also
    #: in ``missing_languages``.
    low_confidence: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None


def _sense_schema(ask_pos: bool = True) -> Schema:
    """The structured answer: the covered_by verdict plus one described sense.

    Without ``ask_pos`` the caller has fixed the part of speech and subtype, and
    the model is not asked for them.
    """
    translation_fields = {
        "lithuanian_translation": "The Lithuanian term for this sense",
        "spanish_translation": "The Spanish term for this sense",
        "spanish_latam_translation": "The neutral Latin American Spanish term for this sense",
        "french_translation": "The French term for this sense",
        "chinese_translation": "The Chinese term for this sense",
    }
    properties: Dict[str, SchemaProperty] = {
        "covered_by": SchemaProperty(
            "integer",
            "Number of the listed existing sense that already is this meaning, or 0 if none",
        ),
        "definition": SchemaProperty("string", "The definition of the word in this field"),
    }
    if ask_pos:
        # The subtype is a second call (build_subtype_prompt), which can show
        # the one part of speech's subtypes with their descriptions.
        properties["pos"] = SchemaProperty(
            "string",
            "The part of speech of this sense",
            enum=list(VALID_POS_TYPES),
        )
    properties |= {
        "phonetic_spelling": SchemaProperty("string", "Phonetic spelling of the word"),
        "ipa_spelling": SchemaProperty("string", "International Phonetic Alphabet for the word"),
        "examples": SchemaProperty(
            type="array",
            description="Example sentences using the word in this field",
            items={"type": "string", "description": "Example sentence"},
        ),
    }
    for field_name, description in translation_fields.items():
        properties[field_name] = SchemaProperty(
            "object",
            description,
            properties={
                "translation": SchemaProperty("string", description),
                "confidence": SchemaProperty(
                    "number",
                    "Confidence from 0-1 that this is the term the field uses in this language",
                ),
            },
        )
    properties["confidence"] = SchemaProperty("number", "Confidence score from 0-1")
    return Schema(
        name="DomainSense",
        description="One sense of a word as a term of a field",
        properties=properties,
    )


def _describe_existing(senses: Sequence[Lemma]) -> str:
    """The numbered list of existing senses the prompt asks the model to judge."""
    if not senses:
        return "(none)"
    lines = []
    for number, lemma in enumerate(senses, start=1):
        label = lemma.lemma_text
        if lemma.disambiguation:
            label = f"{label} ({lemma.disambiguation})"
        lines.append(
            f"{number}. {label} [{lemma.pos_type}/{lemma.pos_subtype}]: {lemma.definition_text}"
        )
    return "\n".join(lines)


def _split_by_confidence(
    sense: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """``sense`` without its low-confidence translations, and those translations.

    A translation whose confidence is missing or not a number counts as low:
    the floor exists to keep doubtful terms out, so an unrated one stays out.

    Returns:
        A copy of ``sense`` with each dropped translation field removed, and
        the dropped ones by language code as ``{"translation", "confidence"}``.
    """
    kept = dict(sense)
    dropped: Dict[str, Dict[str, Any]] = {}
    for field_name, value in sense.items():
        lang_code = LLM_FIELD_TO_LANG_CODE.get(field_name)
        if lang_code is None or not isinstance(value, dict):
            continue
        raw_confidence = value.get("confidence")
        confidence: Optional[float] = None
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            confidence = float(raw_confidence)
        if confidence is not None and confidence >= TRANSLATION_CONFIDENCE_FLOOR:
            continue
        del kept[field_name]
        dropped[lang_code] = {"translation": value.get("translation"), "confidence": confidence}
    return kept, dropped


def pos_type_for_subtype(pos_subtype: str) -> Optional[str]:
    """The one part of speech ``pos_subtype`` belongs to, or None if not exactly one."""
    owners = [pos for pos, subtypes in SUBTYPE_GUID_PREFIXES.items() if pos_subtype in subtypes]
    return owners[0] if len(owners) == 1 else None


def build_sense_prompt(
    word: str,
    domain: str,
    hint: Optional[str],
    existing: Sequence[Lemma],
    pos_type: Optional[str] = None,
) -> tuple[str, str, Schema]:
    """Build the context, prompt and schema for one :func:`add_sense` call.

    With ``pos_type`` the caller has fixed the part of speech and subtype: the
    prompt names the part of speech.  Without it the model returns the part of
    speech, and :func:`build_subtype_prompt` asks for the subtype afterwards.
    """
    hint_line = f"The meaning intended: {hint}\n" if hint else ""
    if pos_type is not None:
        prompt = util.prompt_loader.get_prompt("translation", "sense_known_type").format(
            word=word,
            domain=domain,
            pos_type=pos_type,
            hint=hint_line,
            existing_senses=_describe_existing(existing),
        )
        context = util.prompt_loader.get_context("translation", "sense_known_type")
        return context, prompt, _sense_schema(ask_pos=False)

    context = util.prompt_loader.get_context("translation", "sense")
    prompt = util.prompt_loader.get_prompt("translation", "sense").format(
        word=word,
        domain=domain,
        hint=hint_line,
        existing_senses=_describe_existing(existing),
    )
    return context, prompt, _sense_schema()


def build_subtype_prompt(
    word: str, domain: str, definition: str, pos_type: str
) -> tuple[str, str, Schema]:
    """Build the context, prompt and schema for the second, subtype-only call.

    It shows only ``pos_type``'s subtypes, each with its description and
    examples.  Put in the first call, every part of speech's subtypes had to
    be listed, and as bare names: well over a hundred glosses would be too
    much for every call, and from the names alone the model filed referee as a
    participant_role and gave volley the catch-all.  The catch-all is withheld,
    as add_sense refuses it for an open-class word anyway.
    """
    context = util.prompt_loader.get_context("translation", "sense_subtype").format(
        pos_type=pos_type,
        pos_type_upper=pos_type.upper(),
        subtype_list=render_subtype_list(pos_type, include_catch_all=False),
    )
    prompt = util.prompt_loader.get_prompt("translation", "sense_subtype").format(
        word=word, domain=domain, pos_type=pos_type, definition=definition
    )
    schema = Schema(
        name="SenseSubtype",
        description="The subtype of one sense's part of speech",
        properties={
            "pos_subtype": SchemaProperty(
                "string",
                f"The {pos_type} subtype of this sense",
                enum=_offered_subtypes(get_subtype_values_for_pos(pos_type)),
            )
        },
    )
    return context, prompt, schema


def _already_present(
    senses: Sequence[Lemma], word: str, disambiguation: Optional[str], tags: Sequence[str]
) -> Optional[Lemma]:
    """An existing sense that settles the question without an LLM call.

    Either it carries exactly the requested disambiguation, or it carries every
    requested tag -- which is what a previous run left on a sense it created,
    matched or moved, so a re-run of a whole list is free.

    ``senses`` is already narrowed to the caller's part of speech when it fixed
    one: a list may carry the noun and the verb of one headword under the same
    tags, and the noun's tags must not stand in for the verb.
    """
    wanted_tags = set(normalize_tags(tags))
    for lemma in senses:
        if disambiguation is not None:
            label = disambiguation.lower()
            if (lemma.disambiguation or "").lower() == label:
                return lemma
            if lemma.lemma_text.lower() == f"{word.lower()} ({label})":
                return lemma
        if wanted_tags and wanted_tags <= set(read_tags(lemma)):
            return lemma
    return None


def _add_abbreviation(
    session: Session, lemma: Lemma, abbreviation: Optional[str], *, source: str
) -> None:
    """Record ``abbreviation`` ("LBW") as an abbreviation variant of ``lemma``."""
    if not abbreviation:
        return
    add_variant_form(
        session,
        lemma,
        abbreviation,
        "en",
        abbreviation,
        determine_default_grammatical_form(abbreviation, lemma.pos_type, abbreviation),
        variant_kind=VARIANT_KIND_ABBREVIATION,
        is_base_form=True,
        source=source,
    )


def _relevel(
    session: Session,
    lemma: Lemma,
    *,
    difficulty_level: int,
    disambiguation: Optional[str],
    source: str,
) -> None:
    """Move an existing sense to the caller's level and disambiguation.

    The disambiguation is only filled in, never replaced: a sense that already
    has one was labelled by someone on purpose, and one whose label is carried
    in the older "light (color)" ``lemma_text`` form already has a label too.
    """
    changes = [FieldChange("difficulty_level", lemma.difficulty_level, difficulty_level)]
    lemma.difficulty_level = difficulty_level

    if disambiguation and not lemma.disambiguation and "(" not in lemma.lemma_text:
        changes.append(FieldChange("disambiguation", None, disambiguation))
        lemma.disambiguation = disambiguation

    changes.append(FieldChange("sense_prominence", lemma.sense_prominence, SENSE_PROMINENCE_RARE))
    lemma.sense_prominence = SENSE_PROMINENCE_RARE

    log_field_changes(
        session,
        source=source,
        operation_type="lemma_update",
        entity_guid=lemma.guid,
        changes=changes,
        lemma_id=lemma.id,
    )


def add_sense(
    session: Session,
    word: str,
    *,
    domain: str,
    disambiguation: Optional[str],
    config: DataSourceConfig,
    hint: Optional[str] = None,
    difficulty_level: int = DIFFICULTY_LEVEL,
    tags: Optional[Sequence[str]] = None,
    abbreviation: Optional[str] = None,
    relevel_existing: bool = False,
    pos_subtype: Optional[str] = None,
    pos_type: Optional[str] = None,
    source: str = "add_sense",
    client: Optional[Any] = None,
) -> AddSenseResult:
    """Add the sense ``word`` has in ``domain``, unless the database already has it.

    Args:
        session: Database session. Committed on success.
        word: The English headword, which may be several words ("home run").
        domain: The field the sense belongs to, as the prompt should name it
            ("chess", "American football").
        disambiguation: Label stored on a new lemma ("chess" for "check
            (chess)"), or None for a headword with no other meaning.
        config: Data source configuration, per CLAUDE.md.
        hint: Optional short gloss naming the sense, for a headword that is
            ambiguous even within the domain.
        difficulty_level: Level to create the lemma at, or to move a matched
            sense to when ``relevel_existing`` is set.
        tags: Tags to put on the new or matched sense.
        abbreviation: An abbreviation ("LBW") to record as a variant of the
            sense.
        relevel_existing: Move a matched existing sense to ``difficulty_level``
            and ``disambiguation`` instead of only tagging it.
        pos_subtype: The subtype a new lemma is stored under, for a list whose
            members are all one kind of thing -- a closed set that must share
            its cohort's subtype. The part of speech follows from it, and the
            model is asked for neither. A matched existing sense keeps its own.
        pos_type: The part of speech of the sense, for a headword the field
            uses as both noun and verb ("dunk"). The model is told it and still
            chooses the subtype. Only senses of this part of speech are
            candidates for an existing match. Must agree with ``pos_subtype``
            when both are given.
        source: Provenance recorded in the operation log.
        client: Pre-built LLM client, for tests.

    Returns:
        An :class:`AddSenseResult`. **Makes one LLM call and costs money**,
        except when an existing sense already carries the requested
        disambiguation or tags.
    """
    normalized = " ".join(word.split())
    if not normalized:
        return AddSenseResult(word=word, status="error", error="word must not be empty")
    if not domain.strip():
        return AddSenseResult(word=normalized, status="error", error="domain must not be empty")
    requested_tags = list(tags or [])
    fixed_pos_type: Optional[str] = None
    if pos_type is not None:
        if pos_type not in VALID_POS_TYPES:
            return AddSenseResult(
                word=normalized, status="error", error=f"unknown pos_type {pos_type!r}"
            )
        fixed_pos_type = pos_type
    if pos_subtype is not None:
        subtype_owner = pos_type_for_subtype(pos_subtype)
        if subtype_owner is None or _needs_subtype_review(subtype_owner, pos_subtype):
            return AddSenseResult(
                word=normalized, status="error", error=f"unusable pos_subtype {pos_subtype!r}"
            )
        if fixed_pos_type is not None and fixed_pos_type != subtype_owner:
            return AddSenseResult(
                word=normalized,
                status="error",
                error=f"pos_subtype {pos_subtype!r} is not a {fixed_pos_type} subtype",
            )
        fixed_pos_type = subtype_owner

    def settle_match(matched: Lemma, status: str) -> AddSenseResult:
        """Tag, and on request move, an existing sense that is the one asked for."""
        try:
            if relevel_existing:
                _relevel(
                    session,
                    matched,
                    difficulty_level=difficulty_level,
                    disambiguation=disambiguation,
                    source=source,
                )
            if requested_tags:
                add_tags(session, matched, requested_tags, source=source)
            _add_abbreviation(session, matched, abbreviation, source=source)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return AddSenseResult(
            word=normalized,
            status=status,
            guid=matched.guid,
            disambiguation=matched.disambiguation,
            definition_text=matched.definition_text,
            pos_type=matched.pos_type,
            pos_subtype=matched.pos_subtype,
        )

    existing = get_english_senses(session, normalized)
    if fixed_pos_type is not None:
        existing = [lemma for lemma in existing if lemma.pos_type == fixed_pos_type]
    present = _already_present(existing, normalized, disambiguation, requested_tags)
    if present is not None:
        # Still tagged (and moved, if asked): a sense someone labelled "sports"
        # by hand is the one wanted, but nothing has marked it as the theme's.
        return settle_match(present, "already_exists")

    # Imported here rather than at module scope, as add_term does, so that
    # importing this module does not construct a client.
    from wordfreq.translation.client import LinguisticClient

    llm_client = client
    if llm_client is None:
        llm_client = LinguisticClient(config=config).client

    context, prompt, schema = build_sense_prompt(
        normalized, domain.strip(), hint, existing, pos_type=fixed_pos_type
    )
    try:
        response = llm_client.generate_chat(
            prompt=prompt, model=config.model, json_schema=schema, context=context
        )
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        logger.error("Sense call failed for '%s' (%s): %s", normalized, domain, error)
        return AddSenseResult(word=normalized, status="error", error=str(error))

    sense = response.structured_data
    if not isinstance(sense, dict):
        return AddSenseResult(
            word=normalized, status="error", error="Structured response is not an object"
        )

    covered_by = sense.get("covered_by", NOT_COVERED)
    if not isinstance(covered_by, int) or not NOT_COVERED <= covered_by <= len(existing):
        # A number that names no listed sense is not a "no": writing a new
        # lemma on it could duplicate the sense it was trying to point at.
        return AddSenseResult(
            word=normalized,
            status="error",
            error=f"covered_by {covered_by!r} names none of the {len(existing)} listed senses",
        )

    if covered_by != NOT_COVERED:
        return settle_match(existing[covered_by - 1], "moved" if relevel_existing else "covered")

    definition_text = str(sense.get("definition") or "").strip()
    if not definition_text:
        return AddSenseResult(word=normalized, status="error", error="LLM gave no definition")

    new_pos_type = fixed_pos_type or str(sense.get("pos") or "").lower()
    if pos_subtype is not None:
        new_subtype: Optional[str] = pos_subtype
    else:
        raw_subtype: Optional[str] = new_pos_type
        if new_pos_type in _SUBTYPED_POS_TYPES:
            # The second call: only a new sense pays for it, not a covered one.
            subtype_context, subtype_prompt, subtype_schema = build_subtype_prompt(
                normalized, domain.strip(), definition_text, new_pos_type
            )
            try:
                subtype_response = llm_client.generate_chat(
                    prompt=subtype_prompt,
                    model=config.model,
                    json_schema=subtype_schema,
                    context=subtype_context,
                )
            except Exception as error:  # noqa: BLE001 - reported, not swallowed
                logger.error("Subtype call failed for '%s' (%s): %s", normalized, domain, error)
                return AddSenseResult(word=normalized, status="error", error=str(error))
            subtype_data = subtype_response.structured_data
            raw_subtype = (
                subtype_data.get("pos_subtype") if isinstance(subtype_data, dict) else None
            )
        # A closed class answers with its part of speech, which normalizes to
        # its only subtype, "<pos>_other".
        new_subtype = _normalize_subtype(new_pos_type, raw_subtype)

    try:
        pos_error = _validate_pos(new_pos_type, new_subtype)
        if pos_error is not None:
            return AddSenseResult(word=normalized, status="error", error=f"LLM gave {pos_error}")
        assert new_subtype is not None  # _validate_pos rejects None
        if _needs_subtype_review(new_pos_type, new_subtype):
            # Not offered, but a schema-valid POS/subtype mismatch is normalized
            # to the catch-all too.  Nothing is written, so a re-run retries it.
            return AddSenseResult(
                word=normalized,
                status="error",
                error=f"LLM gave the catch-all subtype {new_subtype!r}; nothing written",
            )

        confident_sense, low_confidence = _split_by_confidence(sense)

        guid = generate_guid(session, new_pos_type, new_subtype)
        new_lemma = Lemma(
            lemma_text=normalized,
            disambiguation=disambiguation,
            definition_text=definition_text,
            pos_type=new_pos_type,
            pos_subtype=new_subtype,
            guid=guid,
            difficulty_level=difficulty_level,
            sense_prominence=SENSE_PROMINENCE_RARE,
            confidence=0.0,
            verified=False,
        )
        session.add(new_lemma)
        session.flush()
        ensure_english_translation(session, new_lemma)

        log_translation_change(
            session=session,
            source=source,
            operation_type="lemma_create",
            lemma_id=new_lemma.id,
            language_code="en",
            old_translation=None,
            new_translation=normalized,
            entity_guid=guid,
            guid=guid,
            pos_type=new_pos_type,
            pos_subtype=new_subtype,
            definition=definition_text,
            disambiguation=disambiguation,
            domain=domain,
            model=config.model,
        )
        # A missing language is reported rather than fatal, as in add_term:
        # the sense is still worth having, and the gap is visible to the
        # translation coverage pass. A low-confidence one is left missing too.
        stored = store_sense_translations(
            session, new_lemma, confident_sense, source=source, model=config.model
        )
        store_sense_examples(session, new_lemma, sense, source=source)
        attach_english_base_form(session, new_lemma, sense, source=source)
        _add_abbreviation(session, new_lemma, abbreviation, source=source)
        if requested_tags:
            add_tags(session, new_lemma, requested_tags, source=source)
        session.commit()
    except Exception:
        session.rollback()
        raise

    missing = [code for code in TRANSLATION_LANGUAGES if code not in stored]
    if missing:
        logger.warning(
            "Sense '%s' (%s) created as %s with no translation for: %s",
            normalized,
            domain,
            guid,
            ", ".join(missing),
        )
    for lang_code, dropped in low_confidence.items():
        logger.warning(
            "Sense '%s' (%s): dropped %s translation %r at confidence %s",
            normalized,
            domain,
            lang_code,
            dropped["translation"],
            dropped["confidence"],
        )
    return AddSenseResult(
        word=normalized,
        status="created",
        guid=guid,
        disambiguation=disambiguation,
        definition_text=definition_text,
        pos_type=new_pos_type,
        pos_subtype=new_subtype,
        translations=stored,
        missing_languages=missing,
        low_confidence=low_confidence,
    )
