#!/usr/bin/python3

"""LLM naming for curriculum levels.

Two capabilities, both writing to ``curriculum_levels``:

* :func:`generate_level_name` reads the words at a level and proposes an
  English title (and a CEFR estimate), continuing any series the existing
  names already started ("Animals 3" after "Animals 2").
* :func:`translate_level_name` renders a level's English title into the
  interface languages, one ``curriculum_level_translations`` row each.

Both default to filling gaps only, so re-queueing a level never overwrites a
name somebody typed; ``overwrite`` is the explicit way to replace one.  Prompts
live under ``prompts/curriculum/``.  The workqueue handlers in
``workqueue.handlers.levels`` delegate here.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from langtools.directions import get_language_direction_note
from storage.backend.config import DataSourceConfig
from storage.crud.curriculum_level import (
    get_curriculum_level,
    list_curriculum_levels,
    set_curriculum_level,
    set_level_translation,
)
from storage.models.curriculum_level import CEFR_LEVELS
from storage.models.schema import Lemma
from storage.translation_helpers import get_default_generation_languages, get_language_name

logger = logging.getLogger(__name__)

#: Operation-log source for LLM-written names.
OPERATION_SOURCE = "llm/level-naming"

#: Words shown to the namer. The most frequent ones say what a level is about;
#: past a few dozen, extra words cost tokens without changing the answer.
MAX_WORDS_IN_PROMPT = 60

NAME_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "cefr": {"type": "string", "enum": list(CEFR_LEVELS)},
        "rationale": {"type": "string"},
    },
    "required": ["name", "cefr", "rationale"],
}

TRANSLATE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "language": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["language", "name"],
            },
        },
    },
    "required": ["translations"],
}


def default_translation_languages() -> List[str]:
    """Interface languages a level name is translated into by default."""
    return [code for code in get_default_generation_languages() if code != "en"]


def level_word_counts(session: Session) -> Dict[int, int]:
    """Number of lemmas at each positive level (the -1 exclusion is skipped)."""
    rows = (
        session.query(Lemma.difficulty_level, func.count(Lemma.id))
        .filter(Lemma.difficulty_level.isnot(None), Lemma.difficulty_level > 0)
        .group_by(Lemma.difficulty_level)
        .all()
    )
    return {int(level): int(count) for level, count in rows}


def level_words(session: Session, level: int, limit: Optional[int] = None) -> List[Lemma]:
    """Lemmas at ``level``, most frequent first (unranked last)."""
    query = (
        session.query(Lemma)
        .filter(Lemma.difficulty_level == level)
        .order_by(Lemma.frequency_rank.is_(None), Lemma.frequency_rank, Lemma.lemma_text)
    )
    if limit is not None:
        query = query.limit(limit)
    words: List[Lemma] = query.all()
    return words


def _describe_word(lemma: Lemma) -> str:
    """One prompt line for a word: text, part of speech, and sense hint."""
    pos = lemma.pos_type
    if lemma.pos_subtype:
        pos = f"{pos}/{lemma.pos_subtype}"
    line = f"- {lemma.lemma_text} ({pos})"
    if lemma.disambiguation:
        line += f" [{lemma.disambiguation}]"
    return line


def build_name_prompt(level: int, words: Sequence[Lemma], existing_names: Mapping[int, str]) -> str:
    """Build the prompt asking for one level's English title."""
    context = util.prompt_loader.get_context("curriculum", "level_name")
    template = util.prompt_loader.get_prompt("curriculum", "level_name")
    others = [
        f"- {number}: {name}" for number, name in sorted(existing_names.items()) if number != level
    ]
    body = template.replace("{{level}}", str(level))
    body = body.replace("{{word_count}}", str(len(words)))
    body = body.replace("{{words}}", "\n".join(_describe_word(lemma) for lemma in words))
    body = body.replace("{{existing_names}}", "\n".join(others) or "(none yet)")
    return f"{context}\n\n{body}"


def build_translate_prompt(name: str, words: Sequence[Lemma], languages: Sequence[str]) -> str:
    """Build the prompt asking for a title in each of ``languages``."""
    context = util.prompt_loader.get_context("curriculum", "level_name_translate")
    template = util.prompt_loader.get_prompt("curriculum", "level_name_translate")
    language_lines = []
    for code in languages:
        line = f"- {code}: {get_language_name(code)}"
        note = get_language_direction_note(code)
        if note:
            line += f" ({note.strip()})"
        language_lines.append(line)
    body = template.replace("{{name}}", name)
    body = body.replace("{{words}}", ", ".join(lemma.lemma_text for lemma in words))
    body = body.replace("{{languages}}", "\n".join(language_lines))
    return f"{context}\n\n{body}"


def _resolve_client(config: Optional[DataSourceConfig]) -> Tuple[UnifiedLLMClient, str]:
    """Return the ``(client, model)`` pair for a config, defaulting the config."""
    if config is None:
        from workqueue.tools import build_default_config

        config = build_default_config()
    # Lazy-imported to avoid a circular import via wordfreq -> langtools.
    from wordfreq.translation.client import LinguisticClient

    linguistic_client = LinguisticClient(config=config)
    return linguistic_client.client, linguistic_client.model


def _structured_payload(response: Any) -> Dict[str, Any]:
    """Extract a dict payload from an LLM response, or raise ValueError."""
    payload = response.structured_data
    if not payload:
        raise ValueError("Empty response from LLM")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Structured response is not an object")
    return payload


def query_level_name(
    level: int,
    words: Sequence[Lemma],
    existing_names: Mapping[int, str],
    *,
    client: UnifiedLLMClient,
    model: str,
) -> Dict[str, str]:
    """Ask the LLM for a level title. Returns ``{"name", "cefr", "rationale"}``."""
    response = client.generate_chat(
        prompt=build_name_prompt(level, words, existing_names),
        model=model,
        json_schema=NAME_JSON_SCHEMA,
    )
    payload = _structured_payload(response)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("LLM returned no name")
    return {
        "name": name,
        "cefr": str(payload.get("cefr") or "").strip(),
        "rationale": str(payload.get("rationale") or "").strip(),
    }


def query_level_translations(
    name: str,
    words: Sequence[Lemma],
    languages: Sequence[str],
    *,
    client: UnifiedLLMClient,
    model: str,
) -> Dict[str, str]:
    """Ask the LLM for ``name`` in each language; unrequested languages are dropped."""
    response = client.generate_chat(
        prompt=build_translate_prompt(name, words, languages),
        model=model,
        json_schema=TRANSLATE_JSON_SCHEMA,
    )
    payload = _structured_payload(response)
    wanted = set(languages)
    translations: Dict[str, str] = {}
    for item in payload.get("translations") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("language") or "").strip()
        translated = str(item.get("name") or "").strip()
        if code in wanted and translated:
            translations[code] = translated
    return translations


def generate_level_name(
    session: Session,
    level: int,
    *,
    config: Optional[DataSourceConfig] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Name one level from its words, creating the metadata row if needed.

    An existing name is kept unless ``overwrite``; the CEFR estimate is only
    written where none is set, since it is the field most often hand-tuned.
    Does not commit.

    Returns:
        ``{"level", "name", "cefr", "rationale", "written"}``.
    """
    row = get_curriculum_level(session, level)
    if row is not None and not overwrite:
        return {"level": level, "name": row.name, "written": False, "rationale": "already named"}

    words = level_words(session, level, limit=MAX_WORDS_IN_PROMPT)
    if not words:
        raise ValueError(f"Level {level} has no words to name it from")
    existing_names = {other.level: other.name for other in list_curriculum_levels(session)}

    client, model = _resolve_client(config)
    proposal = query_level_name(level, words, existing_names, client=client, model=model)

    set_curriculum_level(
        session,
        level,
        name=proposal["name"],
        cefr=(row.cefr if row is not None and row.cefr else proposal["cefr"]) or None,
        prerequisites=row.get_prerequisites() if row else (),
        extra=row.get_extra() if row else None,
        notes=row.notes if row else None,
        source=OPERATION_SOURCE,
    )
    return {"level": level, "written": True, **proposal}


def translate_level_name(
    session: Session,
    level: int,
    *,
    config: Optional[DataSourceConfig] = None,
    languages: Optional[Sequence[str]] = None,
    overwrite: bool = False,
) -> Dict[str, str]:
    """Translate one level's English name, filling missing languages only.

    ``overwrite`` re-translates languages that already have a name.  Does not
    commit.

    Returns:
        The translations written, keyed by language code.
    """
    row = get_curriculum_level(session, level)
    if row is None:
        raise ValueError(f"Level {level} has no name to translate yet")

    requested = [code for code in (languages or default_translation_languages()) if code != "en"]
    existing = row.get_translations()
    targets = [code for code in requested if overwrite or code not in existing]
    if not targets:
        return {}

    words = level_words(session, level, limit=MAX_WORDS_IN_PROMPT)
    client, model = _resolve_client(config)
    translations = query_level_translations(row.name, words, targets, client=client, model=model)
    for code, translated in translations.items():
        set_level_translation(session, level, code, translated, source=OPERATION_SOURCE)
    return translations
