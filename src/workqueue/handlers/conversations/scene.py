"""Workqueue handler for scene-driven dialog generation.

This is the execution half of the Barsukas-first dialog flow: the web UI
enqueues a scene ("buying tomatoes at the grocery store") plus a target level,
and this handler generates the dialog and stores it as ordinary Conversation /
Sentence / SentenceWord rows -- the same shape the WireWord export consumes.

What it stores that the older keyword-driven path did not:

* **Word links.** Every English token becomes a ``SentenceWord`` row pointing at
  a lemma, at a name, or at nothing (a word we do not have yet). That makes the
  dialog's difficulty a *computed* property instead of an asserted one.
* **A derived minimum level.** ``Sentence.minimum_level`` is the max difficulty
  of the lemmas the line actually used. The conversation's is the 85th
  percentile over the distinct lemmas of the whole dialog, floored at the level
  that was asked for -- a few harder words are expected and should not define
  the dialog. The level the author asked for is kept separately as
  ``target_level``, so the review page can show the gap.
* **The cast.** Proper names are registered as ``Name`` rows and linked, so
  "George" is neither mistaken for vocabulary nor left as an unresolved gap.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import constants
from sentences.dialog_coverage import (
    STATUS_MISSING,
    TokenCoverage,
    classify_line_tokens,
    dialog_difficulty_level,
    part_of_speech_for,
)
from sentences.dialog_scene import SceneDraft, SceneRequest, generate_scene
from storage.backend.config import DataSourceConfig
from storage.crud.conversation import add_conversation, add_conversation_sentence
from storage.crud.name_entity import get_or_create_name, list_names
from storage.crud.operation_log import log_operation
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.crud.sentence_word import add_sentence_word
from storage.models.name_entity import Name, normalize_name_text
from storage.models.schema import Conversation, Lemma
from workqueue.tools import build_default_config

logger = logging.getLogger(__name__)

# Language dialogs are generated in. English-only for now; translation into the
# other supported languages happens afterwards through the sentence pipeline.
GENERATION_LANG: str = "en"

# How many existing names to offer the generator for reuse. Enough to keep a
# recurring cast, small enough not to crowd the prompt.
KNOWN_NAMES_OFFERED: int = 30


def _register_cast(session: Session, draft: SceneDraft) -> Dict[str, Name]:
    """Create or reuse a Name row for every cast member of the draft.

    Returns:
        Mapping of normalized name text to its Name row.
    """
    registered: Dict[str, Name] = {}
    for member in draft.cast:
        if not member.name_text:
            continue
        name, created = get_or_create_name(
            session,
            name_text=member.name_text,
            kind=member.kind,
            gender=member.gender,
            source_model=draft.source_model,
            notes=member.role,
        )
        registered[normalize_name_text(member.name_text)] = name
        if created:
            logger.info("Registered new %s: %s", member.kind, name.name_text)
    return registered


def _store_turn(
    session: Session,
    *,
    conversation: Conversation,
    position: int,
    speaker: str,
    text: str,
    target_level: int,
    cast_names: set[str],
    names_by_text: Dict[str, Name],
    token_cache: Dict[str, TokenCoverage],
) -> Dict[str, Any]:
    """Store one dialog turn as a Sentence with word links.

    Returns:
        Summary dict describing the stored sentence.
    """
    sentence = add_sentence(
        session,
        pattern_type="conversation",
        verified=False,
        notes=f"Generated for conversation {conversation.id} (scene dialog)",
    )
    add_sentence_translation(
        session,
        sentence=sentence,
        language_code=GENERATION_LANG,
        translation_text=text,
    )

    tokens = classify_line_tokens(
        session,
        text,
        target_level=target_level,
        language_code=GENERATION_LANG,
        cast_names=cast_names,
        cache=token_cache,
    )

    levels: List[int] = []
    # Level of each distinct lemma this line used, for the conversation-wide
    # percentile; a word repeated across turns must only count once.
    lemma_levels: Dict[int, int] = {}
    missing_words: List[str] = []
    for token_position, token in enumerate(tokens):
        lemma = session.get(Lemma, token.lemma_id) if token.lemma_id is not None else None
        name = names_by_text.get(normalize_name_text(token.surface))
        if name is None and token.name_id is not None:
            name = session.get(Name, token.name_id)

        add_sentence_word(
            session,
            sentence=sentence,
            position=token_position,
            part_of_speech=part_of_speech_for(token, lemma.pos_type if lemma else None),
            language_code=GENERATION_LANG,
            lemma=lemma,
            name=name if lemma is None else None,
            english_text=token.surface,
            declined_form=token.surface,
        )
        if lemma is not None and lemma.difficulty_level is not None:
            levels.append(lemma.difficulty_level)
            lemma_levels[lemma.id] = lemma.difficulty_level
        if token.status == STATUS_MISSING:
            missing_words.append(token.surface)

    # A single line is short enough that a percentile over its words would just
    # be the max with extra steps, and the per-sentence level is a hard gate: a
    # learner sees the line only once every word in it is known. So this stays
    # the max over its lemmas -- the percentile applies to the conversation.
    # Names carry no difficulty, so a line of pure names and function words has
    # no level at all.
    sentence.minimum_level = max(levels) if levels else None

    add_conversation_sentence(
        session,
        conversation=conversation,
        sentence=sentence,
        position=position,
        speaker=speaker,
    )

    return {
        "sentence_id": sentence.id,
        "position": position,
        "speaker": speaker,
        "text": text,
        "minimum_level": sentence.minimum_level,
        "lemma_levels": lemma_levels,
        "missing_words": missing_words,
    }


def generate_scene_conversation(
    session: Session,
    request: SceneRequest,
    config: Optional[DataSourceConfig] = None,
) -> Dict[str, Any]:
    """Generate a dialog for a scene and store it, using the caller's session.

    Args:
        session: Database session from the worker (the caller commits).
        request: The scene, level, and shape to generate.
        config: Optional data source configuration; defaults to the standard
            Barsukas configuration.

    Returns:
        Result dict with the conversation id, title, levels, and the words the
        dialog used that are not in the dictionary yet.

    Raises:
        ValueError: If the request is invalid.
        RuntimeError: If generation returned nothing usable.
    """
    effective_config = config or build_default_config()
    if request.model:
        effective_config = effective_config.with_model(request.model)

    known_names = [name.name_text for name in list_names(session, limit=KNOWN_NAMES_OFFERED)]
    draft = generate_scene(session, request, effective_config, known_names=known_names)

    names_by_text = _register_cast(session, draft)
    cast_names = {normalize_name_text(text) for text in draft.cast_names()}

    conversation = add_conversation(
        session,
        title=draft.title,
        theme=draft.theme,
        keywords=draft.cast_names() or None,
        verified=False,
    )
    conversation.scene_prompt = draft.scene
    conversation.target_level = draft.target_level
    conversation.source_model = draft.source_model

    token_cache: Dict[str, TokenCoverage] = {}
    stored_turns: List[Dict[str, Any]] = []
    for position, turn in enumerate(draft.turns):
        stored_turns.append(
            _store_turn(
                session,
                conversation=conversation,
                position=position,
                speaker=turn.speaker,
                text=turn.text,
                target_level=draft.target_level,
                cast_names=cast_names,
                names_by_text=names_by_text,
                token_cache=token_cache,
            )
        )

    # One entry per distinct lemma across the whole dialog, so a word used in
    # every turn does not drag the percentile up by repetition alone.
    conversation_lemma_levels: Dict[int, int] = {}
    for turn_summary in stored_turns:
        conversation_lemma_levels.update(turn_summary["lemma_levels"])

    computed_level = dialog_difficulty_level(
        list(conversation_lemma_levels.values()),
        target_level=draft.target_level,
    )
    conversation.minimum_level = computed_level

    missing_words: List[str] = []
    for turn_summary in stored_turns:
        for word in turn_summary["missing_words"]:
            if word not in missing_words:
                missing_words.append(word)

    log_operation(
        session,
        operation_type="conversation_scene_generated",
        entity_type="conversation",
        entity_id=conversation.id,
        details={
            "scene": draft.scene,
            "title": draft.title,
            "target_level": draft.target_level,
            "computed_minimum_level": computed_level,
            "num_turns": len(stored_turns),
            "cast": draft.cast_names(),
            "missing_words": missing_words,
            "model": draft.source_model,
        },
    )

    logger.info(
        "Created conversation %s (%r) with %d turns; target level %s, computed %s, %d missing words",
        conversation.id,
        draft.title,
        len(stored_turns),
        draft.target_level,
        computed_level,
        len(missing_words),
    )

    return {
        "success": True,
        "conversation_id": conversation.id,
        "title": draft.title,
        "scene": draft.scene,
        "target_level": draft.target_level,
        "computed_minimum_level": computed_level,
        "turns": stored_turns,
        "cast": draft.cast_names(),
        "missing_words": missing_words,
        "model": draft.source_model,
    }


def handle_conversations_scene_generate(session: Session, payload: Dict[str, Any]) -> str:
    """Handle a scene dialog generation task (workqueue entry point).

    Payload schema:
        scene: str - The scene to act out (required)
        target_level: int - Difficulty level to write for (default 1)
        num_turns: int - Approximate number of dialog turns (default 10)
        model: str - Optional model override
        notes: str - Optional extra direction for the generator

    Returns:
        str: Result message naming the conversation and its coverage.

    Raises:
        ValueError: If the payload has no scene, or the request is invalid.
    """
    scene = str(payload.get("scene") or "").strip()
    if not scene:
        raise ValueError("No scene provided in payload")

    request = SceneRequest(
        scene=scene,
        target_level=int(payload.get("target_level") or 1),
        num_turns=int(payload.get("num_turns") or 10),
        model=payload.get("model") or constants.DEFAULT_MODEL,
        notes=payload.get("notes") or None,
    )

    result = generate_scene_conversation(session, request)
    session.commit()

    missing = result["missing_words"]
    missing_note = (
        f"{len(missing)} word(s) not in the dictionary yet: {', '.join(missing[:10])}"
        if missing
        else "every word already in the dictionary"
    )
    return (
        f"Generated conversation {result['conversation_id']}: '{result['title']}' "
        f"({len(result['turns'])} turns, target level {result['target_level']}, "
        f"computed level {result['computed_minimum_level']}); {missing_note}"
    )
