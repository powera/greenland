"""Workqueue handler for scene-driven dialog generation.

This is the execution half of the Barsukas-first dialog flow: the web UI
enqueues a scene ("buying tomatoes at the grocery store") plus a target level,
and this handler generates the dialog and stores it as ordinary Conversation /
Sentence / SentenceWord rows -- the same shape the WireWord export consumes.

A turn is stored as *one Sentence per sentence*, not one per turn. The generator
returns each turn already split (``SceneTurn.sentences``), and the rows of one
turn share a ``ConversationSentence.turn_index``. Everything downstream --
translation, decomposition, audio alignment, WireWord export, and
``minimum_level`` as a gate -- assumes one Sentence is one sentence; a turn
stored whole made ``minimum_level`` the max over several sentences' vocabulary
and left translation with no way to render a line on its own.

What it stores that the older keyword-driven path did not:

* **Word links.** Every English token that resolves to a lemma or a name becomes
  a ``SentencePatternWord`` row. That makes the dialog's difficulty a *computed*
  property instead of an asserted one.

  These are the mechanical, pre-decomposition guesses, which is exactly what
  ``SentencePatternWord`` is for -- including, per its docstring, detecting that
  the English word breakdown has not been generated yet. Writing them to
  ``SentenceWord`` instead would defeat that: the translate/decompose path skips
  English when English ``SentenceWord`` rows already exist, so a scene dialog
  would never get its English decomposed, and a mechanical part-of-speech guess
  would sit in the table that is supposed to hold reviewed output. Grammatical
  words get no row at all, and missing words are staged through the ordinary
  pending-import flow on the review page.
* **A derived minimum level.** ``Sentence.minimum_level`` is the max difficulty
  of the lemmas the line actually used. The conversation's is the 85th
  percentile over the distinct lemmas of the whole dialog, floored at the level
  that was asked for -- a few harder words are expected and should not define
  the dialog. The level the author asked for is kept separately as
  ``target_level``, so the review page can show the gap.

  Both are provisional: they come from mechanical matching, and decomposition
  recomputes them from the reviewed ``SentenceWord`` rows once it has run.
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
)
from sentences.dialog_scene import SceneDraft, SceneRequest, generate_scene
from storage.backend.config import DataSourceConfig
from storage.crud.conversation import add_conversation, add_conversation_sentence
from storage.crud.name_entity import get_or_create_name, list_names
from storage.crud.operation_log import log_operation
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.models.name_entity import Name, normalize_name_text
from storage.models.schema import Conversation, Lemma, SentencePatternWord
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


def _store_sentence(
    session: Session,
    *,
    conversation: Conversation,
    position: int,
    turn_index: int,
    speaker: str,
    text: str,
    target_level: int,
    cast_names: set[str],
    names_by_text: Dict[str, Name],
    token_cache: Dict[str, TokenCoverage],
) -> Dict[str, Any]:
    """Store one sentence of a dialog turn as a Sentence with word links.

    One row per sentence, not per turn: a turn that says three sentences
    produces three rows sharing a ``turn_index``. Everything downstream --
    translation, decomposition, audio alignment, ``minimum_level`` as a gate --
    assumes one Sentence is one sentence.

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
    # Pattern positions are dense and independent of surface token positions:
    # grammatical words get no row, so reusing the token index would leave gaps
    # and collide with uq_sentence_pattern_position.
    pattern_position = 0
    for token in tokens:
        lemma = session.get(Lemma, token.lemma_id) if token.lemma_id is not None else None
        name = names_by_text.get(normalize_name_text(token.surface))
        if name is None and token.name_id is not None:
            name = session.get(Name, token.name_id)

        if token.status == STATUS_MISSING:
            missing_words.append(token.surface)

        # Only words the pattern can actually reference. A grammatical word
        # carries no pattern meaning, and the check constraint requires one of
        # lemma / pending import / name anyway. Missing words are staged through
        # the existing pending-import flow on the review page, not here.
        if lemma is None and name is None:
            continue

        session.add(
            SentencePatternWord(
                sentence_id=sentence.id,
                lemma_id=lemma.id if lemma is not None else None,
                name_id=name.id if lemma is None and name is not None else None,
                position=pattern_position,
                slot_name=token.status,
                english_text=token.surface,
            )
        )
        pattern_position += 1

        if lemma is not None and lemma.difficulty_level is not None:
            levels.append(lemma.difficulty_level)
            lemma_levels[lemma.id] = lemma.difficulty_level

    # Provisional, from mechanical matching only -- decomposition recomputes it
    # from the real SentenceWord rows once those exist. The max (not the
    # conversation's 85th percentile) because a per-sentence level is a hard
    # gate: a learner sees the line only once every word in it is known. Names
    # carry no difficulty, so a line of pure names and function words has no
    # level at all.
    sentence.minimum_level = max(levels) if levels else None

    add_conversation_sentence(
        session,
        conversation=conversation,
        sentence=sentence,
        position=position,
        speaker=speaker,
        turn_index=turn_index,
    )

    return {
        "sentence_id": sentence.id,
        "position": position,
        "turn_index": turn_index,
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
    stored_sentences: List[Dict[str, Any]] = []
    # position is dense across the whole dialog; turn_index groups the sentences
    # that belong to one spoken turn.
    position = 0
    for turn_index, turn in enumerate(draft.turns):
        for text in turn.sentences:
            stored_sentences.append(
                _store_sentence(
                    session,
                    conversation=conversation,
                    position=position,
                    turn_index=turn_index,
                    speaker=turn.speaker,
                    text=text,
                    target_level=draft.target_level,
                    cast_names=cast_names,
                    names_by_text=names_by_text,
                    token_cache=token_cache,
                )
            )
            position += 1

    # One entry per distinct lemma across the whole dialog, so a word used in
    # every turn does not drag the percentile up by repetition alone.
    conversation_lemma_levels: Dict[int, int] = {}
    for sentence_summary in stored_sentences:
        conversation_lemma_levels.update(sentence_summary["lemma_levels"])

    computed_level = dialog_difficulty_level(
        list(conversation_lemma_levels.values()),
        target_level=draft.target_level,
    )
    conversation.minimum_level = computed_level

    missing_words: List[str] = []
    for sentence_summary in stored_sentences:
        for word in sentence_summary["missing_words"]:
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
            "num_turns": len(draft.turns),
            "num_sentences": len(stored_sentences),
            "cast": draft.cast_names(),
            "missing_words": missing_words,
            "model": draft.source_model,
        },
    )

    logger.info(
        "Created conversation %s (%r) with %d turns in %d sentences; "
        "target level %s, computed %s, %d missing words",
        conversation.id,
        draft.title,
        len(draft.turns),
        len(stored_sentences),
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
        "num_turns": len(draft.turns),
        # One entry per stored Sentence, which is one sentence -- a turn that
        # said several sentences appears as several entries sharing a turn_index.
        "sentences": stored_sentences,
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
        f"({result['num_turns']} turns in {len(result['sentences'])} sentences, "
        f"target level {result['target_level']}, "
        f"computed level {result['computed_minimum_level']}); {missing_note}"
    )
