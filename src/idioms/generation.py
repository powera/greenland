#!/usr/bin/python3

"""Idiom generation library.

This module is the canonical entry point for idiom generation, equivalent
population, and equivalent auditing. It owns prompt construction, the LLM
call, normalization, and storage. Both the workqueue handlers
(``workqueue.handlers.idioms``) and the GEGUTE agent (``agents.gegute.agent``)
delegate here.

The three capabilities map one-to-one onto the three prompt directories under
``prompts/idioms/``:

* ``generate`` proposes new idioms in a source language.
* ``equivalents`` fills in cross-language equivalents for an existing idiom.
* ``validate`` audits stored equivalents and reports problems without writing.

Only the first two write to the database. ``validate`` deliberately returns
findings for a human to act on rather than editing curated rows on an LLM's
say-so.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from langtools.directions import get_language_direction_note
from storage.backend.config import DataSourceConfig
from storage.crud.idiom import (
    add_idiom_equivalent,
    create_idiom,
    list_idioms,
)
from storage.models.idiom import IDIOM_EQUIVALENCE_KINDS, Idiom
from storage.translation_helpers import (
    DEFAULT_GENERATION_LANGUAGES,
    get_language_name,
    get_supported_languages,
)

import util.prompt_loader

logger = logging.getLogger(__name__)


# Registers the prompts constrain the model to. Kept here rather than on the
# model because it is a prompt-level vocabulary: the column is a free-text
# String so that release imports of externally-sourced idioms are not rejected
# for using a register we did not anticipate.
IDIOM_REGISTERS: tuple[str, ...] = (
    "neutral",
    "informal",
    "formal",
    "literary",
    "dated",
)

# How many existing expressions to show the generator as a do-not-repeat list.
# The full set would eventually crowd out the instructions; the newest entries
# are the ones a repeat is most likely to collide with.
MAX_EXISTING_EXPRESSIONS_IN_PROMPT = 200


GENERATE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "idioms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "meaning": {"type": "string"},
                    "register": {"type": "string", "enum": list(IDIOM_REGISTERS)},
                    "usage_note": {"type": "string"},
                },
                "required": ["expression", "meaning", "register", "usage_note"],
            },
        },
    },
    "required": ["idioms"],
}


EQUIVALENTS_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "equivalents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "language": {"type": "string"},
                    "expression": {"type": "string"},
                    "kind": {"type": "string", "enum": list(IDIOM_EQUIVALENCE_KINDS)},
                    "literal_gloss": {"type": "string"},
                    "usage_note": {"type": "string"},
                    "register": {"type": "string", "enum": list(IDIOM_REGISTERS)},
                },
                "required": [
                    "language",
                    "expression",
                    "kind",
                    "literal_gloss",
                    "usage_note",
                    "register",
                ],
            },
        },
    },
    "required": ["equivalents"],
}


VALIDATE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "problems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "equivalent_id": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["error", "warning"]},
                    "problem": {"type": "string"},
                    "suggested_kind": {"type": "string"},
                    "suggested_expression": {"type": "string"},
                },
                "required": ["equivalent_id", "severity", "problem"],
            },
        },
    },
    "required": ["problems"],
}


def _language_display_name(language_code: str) -> str:
    """Return a human-readable language name, falling back to the code itself.

    ``get_language_name`` raises for unsupported codes, but an idiom's source
    language comes from stored data that may predate a language being added to
    the registry. A prompt naming the raw code is degraded but still usable,
    whereas an exception would fail the whole run.
    """
    normalized = (language_code or "").strip().lower()
    if not normalized:
        return ""
    try:
        return get_language_name(normalized)
    except (ValueError, KeyError):
        return normalized


def _clean(value: Any) -> str:
    """Coerce an LLM string field to a stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def _optional(value: Any) -> Optional[str]:
    """Coerce an LLM string field to a stripped string or None if empty.

    The prompts ask for an empty string rather than a missing key when a field
    does not apply, so empty must become NULL on the way into the database - an
    empty-string usage note would otherwise render as a blank line in Barsukas.
    """
    cleaned = _clean(value)
    return cleaned or None


def _resolve_client(
    config: Optional[DataSourceConfig],
) -> tuple[UnifiedLLMClient, str]:
    """Return the ``(client, model)`` pair for a config, defaulting the config.

    Mirrors ``words.synonyms.query_synonyms_from_llm``: orchestration functions
    take a ``DataSourceConfig`` per the project convention, and the concrete
    client is built here so the prompt/query layer stays directly testable with
    a stub client.
    """
    if config is None:
        # Lazy import to avoid pulling workqueue at module load.
        from workqueue.tools import build_default_config

        config = build_default_config()

    # Lazy-imported to avoid a circular import via wordfreq -> langtools.
    from wordfreq.translation.client import LinguisticClient

    linguistic_client = LinguisticClient(config=config)
    return linguistic_client.client, linguistic_client.model


def _structured_payload(response: Any) -> Dict[str, Any]:
    """Extract a dict payload from an LLM response, or raise ValueError."""
    if not response.structured_data:
        raise ValueError("Empty response from LLM")

    payload = response.structured_data
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON response: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError("Structured response is not an object")

    return payload


# --------------------------------------------------------------------------- #
# Generate: propose new idioms in a source language                            #
# --------------------------------------------------------------------------- #


def build_generate_prompt(
    language_code: str,
    *,
    count: int,
    existing_expressions: Sequence[str] = (),
    theme: Optional[str] = None,
) -> str:
    """Build the idiom-generation prompt for one source language."""
    normalized = (language_code or "").strip().lower()
    language_name = _language_display_name(normalized)

    context = util.prompt_loader.get_context("idioms", "generate")
    prompt_template = util.prompt_loader.get_prompt("idioms", "generate")

    capped = list(existing_expressions)[-MAX_EXISTING_EXPRESSIONS_IN_PROMPT:]
    existing_block = (
        "\n".join(f"- {expression}" for expression in capped)
        if capped
        else "(none yet - this is the first batch for this language)"
    )

    theme_instruction = (
        f"Focus on idioms relating to: {theme}."
        if theme
        else "Range broadly across everyday topics; do not cluster on one theme."
    )

    prompt_body = prompt_template.replace("{{language_name}}", language_name)
    prompt_body = prompt_body.replace("{{count}}", str(count))
    prompt_body = prompt_body.replace("{{theme_instruction}}", theme_instruction)
    prompt_body = prompt_body.replace("{{existing_expressions}}", existing_block)
    prompt_body = prompt_body.replace("{{language_note}}", get_language_direction_note(normalized))

    return f"{context}\n\n{prompt_body}"


def query_generated_idioms(
    language_code: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    count: int,
    existing_expressions: Sequence[str] = (),
    theme: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the generation prompt and return ``{"success", "idioms"|"error"}``."""
    prompt = build_generate_prompt(
        language_code,
        count=count,
        existing_expressions=existing_expressions,
        theme=theme,
    )

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=GENERATE_JSON_SCHEMA,
        )
        payload = _structured_payload(response)
    except Exception as error:
        logger.error("Error generating idioms for %s: %s", language_code, error)
        return {"success": False, "error": str(error)}

    raw = payload.get("idioms")
    if not isinstance(raw, list):
        return {"success": False, "error": "Response is missing an 'idioms' array"}

    return {"success": True, "idioms": raw}


def store_generated_idioms(
    session: Session,
    language_code: str,
    proposals: Sequence[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    difficulty_level: int = -1,
) -> Dict[str, Any]:
    """Persist generated idioms, skipping duplicates and malformed entries.

    Generated idioms are stored unverified: they are proposals for a human to
    confirm in Barsukas, not curated data. ``difficulty_level`` defaults to -1
    to match the convention for newly added release words.

    Deduplication is against ``(source_language_code, expression)`` in the
    database plus the batch itself. The table's unique constraint also spans
    ``meaning``, which is deliberately looser than this check: two genuinely
    distinct senses of one expression are legal rows, but an LLM returning the
    same expression twice in one batch is far more likely repetition than a
    real second sense, so the agent declines to create it automatically.
    """
    stored: List[Idiom] = []
    skipped_duplicate = 0
    skipped_invalid = 0

    existing_rows = (
        session.query(Idiom.expression).filter(Idiom.source_language_code == language_code).all()
    )
    seen = {row[0].strip().casefold() for row in existing_rows if row[0]}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            skipped_invalid += 1
            continue

        expression = _clean(proposal.get("expression"))
        meaning = _clean(proposal.get("meaning"))
        if not expression or not meaning:
            skipped_invalid += 1
            continue

        key = expression.casefold()
        if key in seen:
            skipped_duplicate += 1
            continue
        seen.add(key)

        idiom = create_idiom(
            session,
            source_language_code=language_code,
            expression=expression,
            meaning=meaning,
            usage_note=_optional(proposal.get("usage_note")),
            register=_optional(proposal.get("register")),
            difficulty_level=difficulty_level,
            source_model=model,
            verified=False,
        )
        stored.append(idiom)

    return {
        "success": True,
        "stored": len(stored),
        "idioms": stored,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
    }


def generate_idioms_for_language(
    session: Session,
    language_code: str,
    *,
    config: Optional[DataSourceConfig] = None,
    count: int = 10,
    theme: Optional[str] = None,
    difficulty_level: int = -1,
) -> Dict[str, Any]:
    """Generate and store new idioms for one source language.

    Does not commit; the caller owns the transaction.
    """
    client, model = _resolve_client(config)
    normalized = (language_code or "").strip().lower()
    existing, _ = list_idioms(session, source_language_code=normalized)
    existing_expressions = [idiom.expression for idiom in existing]

    result = query_generated_idioms(
        normalized,
        client=client,
        model=model,
        count=count,
        existing_expressions=existing_expressions,
        theme=theme,
    )
    if not result.get("success"):
        return result

    return store_generated_idioms(
        session,
        normalized,
        result["idioms"],
        model=model,
        difficulty_level=difficulty_level,
    )


# --------------------------------------------------------------------------- #
# Equivalents: fill in cross-language equivalents for an existing idiom        #
# --------------------------------------------------------------------------- #


def default_target_languages(source_language_code: str) -> List[str]:
    """Return the default equivalent-target languages for a source language.

    The source language itself is dropped: an idiom is not its own equivalent.
    """
    normalized = (source_language_code or "").strip().lower()
    return [code for code in DEFAULT_GENERATION_LANGUAGES if code != normalized]


def missing_languages_for_idiom(idiom: Idiom, target_languages: Sequence[str]) -> List[str]:
    """Return the requested languages that have no stored equivalent yet."""
    present = {(equivalent.language_code or "").strip().lower() for equivalent in idiom.equivalents}
    return [code for code in target_languages if code.strip().lower() not in present]


def build_equivalents_prompt(idiom: Idiom, target_languages: Sequence[str]) -> str:
    """Build the equivalent-population prompt for one idiom."""
    context = util.prompt_loader.get_context("idioms", "equivalents")
    prompt_template = util.prompt_loader.get_prompt("idioms", "equivalents")

    supported = get_supported_languages()
    target_list = ", ".join(f"{code} ({supported.get(code, code)})" for code in target_languages)

    usage_note_line = f"Usage note: {idiom.usage_note}" if idiom.usage_note else ""

    prompt_body = prompt_template.replace(
        "{{source_language_name}}", _language_display_name(idiom.source_language_code)
    )
    prompt_body = prompt_body.replace("{{expression}}", idiom.expression)
    prompt_body = prompt_body.replace("{{meaning}}", idiom.meaning)
    prompt_body = prompt_body.replace("{{register}}", idiom.register or "neutral")
    prompt_body = prompt_body.replace("{{usage_note_line}}", usage_note_line)
    prompt_body = prompt_body.replace("{{target_language_list}}", target_list)
    prompt_body = prompt_body.replace(
        "{{language_note}}", get_language_direction_note(idiom.source_language_code)
    )

    return f"{context}\n\n{prompt_body}"


def query_equivalents(
    idiom: Idiom,
    target_languages: Sequence[str],
    *,
    client: UnifiedLLMClient,
    model: str,
) -> Dict[str, Any]:
    """Run the equivalents prompt and return ``{"success", "equivalents"|"error"}``."""
    prompt = build_equivalents_prompt(idiom, target_languages)

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=EQUIVALENTS_JSON_SCHEMA,
        )
        payload = _structured_payload(response)
    except Exception as error:
        logger.error("Error generating equivalents for %r: %s", idiom.expression, error)
        return {"success": False, "error": str(error)}

    raw = payload.get("equivalents")
    if not isinstance(raw, list):
        return {"success": False, "error": "Response is missing an 'equivalents' array"}

    return {"success": True, "equivalents": raw}


def store_equivalents(
    session: Session,
    idiom: Idiom,
    candidates: Sequence[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    allowed_languages: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Persist generated equivalents, skipping duplicates and invalid entries.

    ``allowed_languages`` restricts what may be written. Without it a model
    that volunteered an unrequested language would silently overwrite the
    caller's intent - which matters for the populate path, where the requested
    set is precisely the languages found to be missing.
    """
    stored: List[Any] = []
    skipped_duplicate = 0
    skipped_invalid = 0
    skipped_unrequested = 0

    allowed = (
        {code.strip().lower() for code in allowed_languages}
        if allowed_languages is not None
        else None
    )

    # (language, expression) pairs already on this idiom, matching the table's
    # unique constraint so a repeat is skipped rather than raising on flush.
    seen = {
        (
            (equivalent.language_code or "").strip().lower(),
            (equivalent.expression or "").strip().casefold(),
        )
        for equivalent in idiom.equivalents
    }

    for candidate in candidates:
        if not isinstance(candidate, dict):
            skipped_invalid += 1
            continue

        language_code = _clean(candidate.get("language")).lower()
        expression = _clean(candidate.get("expression"))
        kind = _clean(candidate.get("kind"))

        if not language_code or not expression:
            skipped_invalid += 1
            continue
        if kind not in IDIOM_EQUIVALENCE_KINDS:
            skipped_invalid += 1
            continue
        if allowed is not None and language_code not in allowed:
            skipped_unrequested += 1
            continue

        key = (language_code, expression.casefold())
        if key in seen:
            skipped_duplicate += 1
            continue
        seen.add(key)

        equivalent = add_idiom_equivalent(
            session,
            idiom,
            language_code=language_code,
            expression=expression,
            equivalence_kind=kind,
            literal_gloss=_optional(candidate.get("literal_gloss")),
            usage_note=_optional(candidate.get("usage_note")),
            register=_optional(candidate.get("register")),
            source_model=model,
            verified=False,
        )
        stored.append(equivalent)

    return {
        "success": True,
        "stored": len(stored),
        "equivalents": stored,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "skipped_unrequested": skipped_unrequested,
    }


def populate_equivalents_for_idiom(
    session: Session,
    idiom: Idiom,
    *,
    config: Optional[DataSourceConfig] = None,
    target_languages: Optional[Sequence[str]] = None,
    only_missing: bool = True,
) -> Dict[str, Any]:
    """Fill in missing equivalents for one idiom.

    Does not commit; the caller owns the transaction.
    """
    targets = list(target_languages or default_target_languages(idiom.source_language_code))
    if only_missing:
        targets = missing_languages_for_idiom(idiom, targets)

    if not targets:
        return {
            "success": True,
            "stored": 0,
            "equivalents": [],
            "skipped_duplicate": 0,
            "skipped_invalid": 0,
            "skipped_unrequested": 0,
            "note": "no missing languages",
        }

    client, model = _resolve_client(config)
    result = query_equivalents(idiom, targets, client=client, model=model)
    if not result.get("success"):
        return result

    return store_equivalents(
        session,
        idiom,
        result["equivalents"],
        model=model,
        allowed_languages=targets,
    )


# --------------------------------------------------------------------------- #
# Validate: audit stored equivalents, reporting rather than writing            #
# --------------------------------------------------------------------------- #


def build_validate_prompt(idiom: Idiom) -> str:
    """Build the audit prompt for one idiom's stored equivalents."""
    context = util.prompt_loader.get_context("idioms", "validate")
    prompt_template = util.prompt_loader.get_prompt("idioms", "validate")

    supported = get_supported_languages()
    lines: List[str] = []
    for equivalent in sorted(
        idiom.equivalents,
        key=lambda row: (row.language_code, row.equivalence_kind, row.id or 0),
    ):
        language_name = supported.get(equivalent.language_code, equivalent.language_code)
        lines.append(
            f"[{equivalent.id}] {language_name} ({equivalent.language_code}): "
            f'"{equivalent.expression}"'
        )
        lines.append(f"    kind: {equivalent.equivalence_kind}")
        lines.append(f"    literal gloss: {equivalent.literal_gloss or '(none)'}")
        if equivalent.register:
            lines.append(f"    register: {equivalent.register}")
        if equivalent.usage_note:
            lines.append(f"    usage note: {equivalent.usage_note}")

    equivalents_block = "\n".join(lines) if lines else "(no equivalents stored)"
    usage_note_line = f"Usage note: {idiom.usage_note}" if idiom.usage_note else ""

    prompt_body = prompt_template.replace(
        "{{source_language_name}}", _language_display_name(idiom.source_language_code)
    )
    prompt_body = prompt_body.replace("{{expression}}", idiom.expression)
    prompt_body = prompt_body.replace("{{meaning}}", idiom.meaning)
    prompt_body = prompt_body.replace("{{register}}", idiom.register or "neutral")
    prompt_body = prompt_body.replace("{{usage_note_line}}", usage_note_line)
    prompt_body = prompt_body.replace("{{equivalents_block}}", equivalents_block)
    prompt_body = prompt_body.replace(
        "{{language_note}}", get_language_direction_note(idiom.source_language_code)
    )

    return f"{context}\n\n{prompt_body}"


def query_validation(
    idiom: Idiom,
    *,
    client: UnifiedLLMClient,
    model: str,
) -> Dict[str, Any]:
    """Run the audit prompt and return ``{"success", "problems"|"error"}``."""
    prompt = build_validate_prompt(idiom)

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=VALIDATE_JSON_SCHEMA,
        )
        payload = _structured_payload(response)
    except Exception as error:
        logger.error("Error validating equivalents for %r: %s", idiom.expression, error)
        return {"success": False, "error": str(error)}

    raw = payload.get("problems")
    if not isinstance(raw, list):
        return {"success": False, "error": "Response is missing a 'problems' array"}

    return {"success": True, "problems": raw}


def validate_equivalents_for_idiom(
    session: Session,
    idiom: Idiom,
    *,
    config: Optional[DataSourceConfig] = None,
) -> Dict[str, Any]:
    """Audit one idiom's equivalents and return findings.

    Read-only by design: findings name an ``equivalent_id`` and are surfaced
    for a human to act on. Applying an LLM's correction directly would let an
    unreviewed call overwrite curated data, and the audit prompt is explicitly
    tuned to be conservative rather than authoritative.

    Findings whose ``equivalent_id`` does not belong to this idiom are dropped:
    the id is echoed back by the model and a hallucinated one would otherwise
    point a reviewer at an unrelated row.
    """
    _ = session  # read-only; kept for signature symmetry with the write paths

    if not idiom.equivalents:
        return {"success": True, "problems": [], "checked": 0}

    client, model = _resolve_client(config)
    result = query_validation(idiom, client=client, model=model)
    if not result.get("success"):
        return result

    valid_ids = {equivalent.id for equivalent in idiom.equivalents}
    problems: List[Dict[str, Any]] = []
    dropped_unknown = 0

    for problem in result["problems"]:
        if not isinstance(problem, dict):
            dropped_unknown += 1
            continue
        equivalent_id = problem.get("equivalent_id")
        if equivalent_id not in valid_ids:
            dropped_unknown += 1
            continue
        problems.append(problem)

    return {
        "success": True,
        "problems": problems,
        "checked": len(idiom.equivalents),
        "dropped_unknown": dropped_unknown,
    }
