"""CRUD operations for Conversation and ConversationSentence models."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session, joinedload

from sentences.token_estimates import estimate_word_count
from storage.models.name_entity import Name
from storage.models.schema import (
    Conversation,
    ConversationSentence,
    Sentence,
    SentenceWordHint,
    SentenceTranslation,
    SentenceWord,
)

logger = logging.getLogger(__name__)

# How much dialog a translation prompt may carry as context. Under this budget
# the whole conversation goes in, which is what a translator actually wants: a
# pronoun or register choice made in turn 2 should still be visible in turn 9.
# Over it, only the run-up to the line survives -- see CONTEXT_FALLBACK_TURNS.
WHOLE_DIALOG_TOKEN_BUDGET: int = 500

# Turns of run-up kept when the whole dialog does not fit. Three is enough for
# an elliptical answer to reach its antecedent ("They are." -> "They look
# happy.") without the prompt growing with the dialog.
CONTEXT_FALLBACK_TURNS: int = 3

# Words-to-tokens factor for the budget check. Deliberately generous, in the
# spirit of sentences.token_estimates: over-estimating costs a little context,
# under-estimating costs an oversized prompt on every sentence of the dialog.
TOKENS_PER_CONTEXT_WORD: int = 2


@dataclass
class ConversationLine:
    """One dialog line as it will be shown to a translation prompt."""

    speaker: str
    text: str
    position: int
    turn_index: Optional[int]


@dataclass
class ConversationContext:
    """The dialog around one sentence, for use as translation-prompt context.

    Built by :func:`get_sentence_conversation_context`. Everything here is
    read-only prompt input; nothing in this object is persisted.
    """

    conversation_id: int
    title: Optional[str]
    scene_prompt: Optional[str]
    speaker: str
    position: int
    turn_index: Optional[int]
    previous_lines: List[ConversationLine] = field(default_factory=list)
    next_lines: List[ConversationLine] = field(default_factory=list)
    cast: List[Name] = field(default_factory=list)
    # True when the dialog was too long for WHOLE_DIALOG_TOKEN_BUDGET and only
    # the preceding CONTEXT_FALLBACK_TURNS turns were kept.
    truncated: bool = False


def _turn_key(link: ConversationSentence) -> int:
    """Group key identifying the turn a conversation sentence belongs to.

    ``turn_index`` is NULL for every row written before the turn-split work, and
    for those rows one row *is* one turn, so ``position`` is the exact answer.
    Grouping by speaker instead would be wrong: a speaker can genuinely hold two
    consecutive turns.
    """
    return link.position if link.turn_index is None else link.turn_index


def _line_turn_key(line: "ConversationLine") -> int:
    """Group key identifying the turn a rendered dialog line belongs to."""
    return line.position if line.turn_index is None else line.turn_index


def _conversation_cast(session: Session, conversation_id: int) -> List[Name]:
    """Names this conversation casts, in order of first appearance.

    Read from the stored word links rather than a cast table, which does not
    exist: ``SentenceWordHint`` holds the mechanical pre-decomposition
    guesses, and ``SentenceWord`` holds the same links for conversations
    generated before d8a4021c moved them.
    """
    ordered: List[Name] = []
    seen: set[int] = set()
    for word_model in (SentenceWordHint, SentenceWord):
        rows = (
            session.query(Name, ConversationSentence.position)
            .join(word_model, word_model.name_id == Name.id)
            .join(
                ConversationSentence,
                ConversationSentence.sentence_id == word_model.sentence_id,
            )
            .filter(ConversationSentence.conversation_id == conversation_id)
            .order_by(ConversationSentence.position)
            .all()
        )
        for name, _position in rows:
            if name.id not in seen:
                seen.add(name.id)
                ordered.append(name)
    return ordered


def _line_text(
    sentence: Optional[Sentence],
    translations_by_sentence: Dict[int, Dict[str, str]],
    language_code: str,
) -> str:
    """Best available text for a dialog line, preferring the asked-for language."""
    if sentence is None:
        return ""
    by_language = translations_by_sentence.get(sentence.id) or {}
    for candidate in (language_code, "en"):
        text = (by_language.get(candidate) or "").strip()
        if text:
            return text
    for text in by_language.values():
        if text and text.strip():
            return text.strip()
    return ""


def get_sentence_conversation_context(
    session: Session,
    sentence_id: int,
    *,
    language_code: str = "en",
    token_budget: int = WHOLE_DIALOG_TOKEN_BUDGET,
) -> Optional[ConversationContext]:
    """Return the dialog surrounding a sentence, or None if it is standalone.

    Translation runs one call per sentence, which leaves a dialog line with no
    way to know what it is answering. An elliptical reply ("They are.") then
    translates into a stranded copula in every language, and a language that
    forces a pronoun choice on every mention (Vietnamese, Japanese) has nothing
    to choose from. This assembles what the prompt needs: the surrounding turns
    with speaker labels, the scene, and the cast.

    Context size follows a budget. Under ``token_budget`` the whole dialog is
    returned, since register and pronoun choices should stay consistent across
    the conversation; over it, only the preceding ``CONTEXT_FALLBACK_TURNS``
    turns are kept and ``truncated`` is set.

    Note on the cast: a ``Name`` row's ``notes`` holds the role it was *first*
    created with (``get_or_create_name`` writes it only on creation), so for a
    recurring character it may describe a different dialog. Treat it as a hint
    and prefer ``scene_prompt`` for what is true of this scene.

    Args:
        session: Database session.
        sentence_id: The sentence being translated.
        language_code: Language to render the surrounding lines in; falls back
            to English and then to any available translation.
        token_budget: Whole-dialog cutoff, in estimated tokens.

    Returns:
        The context, or None when the sentence belongs to no conversation.
    """
    links_for_sentence = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.sentence_id == sentence_id)
        .order_by(ConversationSentence.conversation_id)
        .all()
    )
    if not links_for_sentence:
        return None

    # A sentence can end up in more than one conversation (merge_duplicate_
    # sentences allows it). Pick deterministically rather than at query order's
    # mercy, so a re-run produces the same prompt.
    link = links_for_sentence[0]
    if len(links_for_sentence) > 1:
        logger.debug(
            "Sentence %d is in %d conversations; using conversation %d for context",
            sentence_id,
            len(links_for_sentence),
            link.conversation_id,
        )

    conversation = session.get(Conversation, link.conversation_id)
    if conversation is None:
        return None

    all_links = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == link.conversation_id)
        .order_by(ConversationSentence.position)
        .all()
    )

    sentence_ids = [row.sentence_id for row in all_links]
    sentences_by_id: Dict[int, Sentence] = {}
    translations_by_sentence: Dict[int, Dict[str, str]] = {}
    if sentence_ids:
        for sentence in session.query(Sentence).filter(Sentence.id.in_(sentence_ids)).all():
            sentences_by_id[sentence.id] = sentence
        for translation in (
            session.query(SentenceTranslation)
            .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
            .all()
        ):
            translations_by_sentence.setdefault(translation.sentence_id, {})[
                translation.language_code
            ] = translation.translation_text

    lines: List[ConversationLine] = []
    for row in all_links:
        text = _line_text(
            sentences_by_id.get(row.sentence_id), translations_by_sentence, language_code
        )
        if not text:
            continue
        lines.append(
            ConversationLine(
                speaker=row.speaker,
                text=text,
                position=row.position,
                turn_index=row.turn_index,
            )
        )

    estimated_tokens = sum(
        estimate_word_count(line.text, language_code) * TOKENS_PER_CONTEXT_WORD for line in lines
    )
    truncated = estimated_tokens > token_budget

    this_turn = _turn_key(link)
    previous_lines = [line for line in lines if line.position < link.position]
    next_lines = [line for line in lines if line.position > link.position]

    if truncated:
        # Keep the run-up only: what the line is answering is what makes it
        # translatable, and the turns after it cost as much as the ones before.
        # The rest of this sentence's own turn stays on both sides regardless --
        # a split turn must not lose half of itself.
        turn_keys_before: List[int] = []
        for line in previous_lines:
            key = _line_turn_key(line)
            if key != this_turn and key not in turn_keys_before:
                turn_keys_before.append(key)
        kept = set(turn_keys_before[-CONTEXT_FALLBACK_TURNS:]) | {this_turn}
        previous_lines = [line for line in previous_lines if _line_turn_key(line) in kept]
        next_lines = [line for line in next_lines if _line_turn_key(line) == this_turn]

    return ConversationContext(
        conversation_id=conversation.id,
        title=conversation.title,
        scene_prompt=conversation.scene_prompt,
        speaker=link.speaker,
        position=link.position,
        turn_index=link.turn_index,
        previous_lines=previous_lines,
        next_lines=next_lines,
        cast=_conversation_cast(session, conversation.id),
        truncated=truncated,
    )


def add_conversation(
    session: Session,
    title: Optional[str] = None,
    theme: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    source_filename: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Conversation:
    """Create a new conversation.

    Args:
        session: Database session
        title: Conversation title (e.g., "At the doctor's office")
        theme: Theme/topic category (e.g., "medical", "shopping")
        keywords: List of keywords used to generate this conversation
        source_filename: Source file identifier (e.g., "conversation_level3_001")
        verified: Whether this conversation has been verified
        notes: Optional notes about the conversation

    Returns:
        Created Conversation object
    """
    conversation = Conversation(
        title=title,
        theme=theme,
        keywords=json.dumps(keywords) if keywords else None,
        source_filename=source_filename,
        verified=verified,
        notes=notes,
        minimum_level=None,  # Will be calculated later
    )
    session.add(conversation)
    session.flush()
    return conversation


def add_conversation_sentence(
    session: Session,
    conversation: Conversation,
    sentence: Sentence,
    position: int,
    speaker: str,
    turn_index: Optional[int] = None,
) -> ConversationSentence:
    """Link a sentence to a conversation.

    Args:
        session: Database session
        conversation: Conversation to add sentence to
        sentence: Sentence to add
        position: Position in conversation (0-indexed), dense across sentences
        speaker: Speaker identifier (e.g., "A", "B", or character name)
        turn_index: Which spoken turn this sentence belongs to. Several
            sentences of one turn share a value. None for callers that do not
            model turns separately from positions.

    Returns:
        Created ConversationSentence link object
    """
    conv_sentence = ConversationSentence(
        conversation_id=conversation.id,
        sentence_id=sentence.id,
        position=position,
        speaker=speaker,
        turn_index=turn_index,
    )
    session.add(conv_sentence)
    session.flush()
    return conv_sentence


def get_conversation_by_id(
    session: Session,
    conversation_id: int,
    include_sentences: bool = True,
    include_translations: bool = True,
) -> Optional[Conversation]:
    """Retrieve a conversation by ID with optional eager loading.

    Args:
        session: Database session
        conversation_id: Conversation ID to retrieve
        include_sentences: Whether to eager load sentences
        include_translations: Whether to eager load sentence translations

    Returns:
        Conversation object or None if not found
    """
    query = session.query(Conversation)

    if include_sentences:
        if include_translations:
            query = query.options(
                joinedload(Conversation.conversation_sentences)
                .joinedload(ConversationSentence.sentence)
                .joinedload(Sentence.translations)
            )
        else:
            query = query.options(
                joinedload(Conversation.conversation_sentences).joinedload(
                    ConversationSentence.sentence
                )
            )

    result: Optional[Conversation] = query.filter(Conversation.id == conversation_id).first()
    return result


def get_conversations_by_theme(
    session: Session,
    theme: str,
    max_level: Optional[int] = None,
    verified_only: bool = False,
) -> List[Conversation]:
    """Retrieve conversations by theme.

    Args:
        session: Database session
        theme: Theme to filter by
        max_level: Maximum difficulty level (optional)
        verified_only: Only return verified conversations

    Returns:
        List of Conversation objects
    """
    query = session.query(Conversation).filter(Conversation.theme == theme)

    if max_level is not None:
        query = query.filter(
            Conversation.minimum_level.isnot(None), Conversation.minimum_level <= max_level
        )

    if verified_only:
        query = query.filter(Conversation.verified == True)  # noqa: E712

    query = query.filter(Conversation.rejected == False)  # noqa: E712

    result: list[Conversation] = query.options(
        joinedload(Conversation.conversation_sentences)
    ).all()
    return result


def get_conversations_by_level(
    session: Session,
    max_level: int,
    language_code: Optional[str] = None,
    verified_only: bool = False,
) -> List[Conversation]:
    """Retrieve conversations up to a certain difficulty level.

    Args:
        session: Database session
        max_level: Maximum difficulty level (inclusive)
        language_code: Optional language code to filter translations
        verified_only: Only return verified conversations

    Returns:
        List of Conversation objects
    """
    query = session.query(Conversation).filter(
        Conversation.minimum_level.isnot(None),
        Conversation.minimum_level <= max_level,
        Conversation.rejected == False,  # noqa: E712
    )

    if verified_only:
        query = query.filter(Conversation.verified == True)  # noqa: E712

    query = query.options(
        joinedload(Conversation.conversation_sentences)
        .joinedload(ConversationSentence.sentence)
        .joinedload(Sentence.translations)
    )

    conversations: list[Conversation] = query.all()

    # Filter by language if specified
    if language_code:
        filtered = []
        for conv in conversations:
            has_language = False
            for cs in conv.conversation_sentences:
                if any(t.language_code == language_code for t in cs.sentence.translations):
                    has_language = True
                    break
            if has_language:
                filtered.append(conv)
        return filtered

    return conversations


def calculate_minimum_level(session: Session, conversation: Conversation) -> Optional[int]:
    """Calculate and update the minimum difficulty level for a conversation.

    The minimum level is the maximum difficulty of all sentences in the conversation.
    This ensures learners know all words in all sentences before seeing the conversation.

    Args:
        session: Database session
        conversation: Conversation object to calculate level for

    Returns:
        Calculated minimum level, or None if no sentences have levels
    """
    # Get all sentences for this conversation
    conv_sentences = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == conversation.id)
        .options(joinedload(ConversationSentence.sentence))
        .all()
    )

    if not conv_sentences:
        conversation.minimum_level = None
        return None

    # Find the maximum difficulty level among all sentences
    max_level = None
    for cs in conv_sentences:
        if cs.sentence and cs.sentence.minimum_level is not None:
            if max_level is None or cs.sentence.minimum_level > max_level:
                max_level = cs.sentence.minimum_level

    conversation.minimum_level = max_level
    return max_level


def get_conversation_keywords(conversation: Conversation) -> List[str]:
    """Get the keywords used to generate a conversation.

    Args:
        conversation: Conversation object

    Returns:
        List of keyword strings
    """
    if not conversation.keywords:
        return []
    try:
        result: list[str] = json.loads(conversation.keywords)
        return result
    except json.JSONDecodeError:
        return []


def get_conversation_sentences_ordered(
    session: Session, conversation: Conversation
) -> List[Dict[str, Any]]:
    """Get sentences in a conversation ordered by position with speaker info.

    Args:
        session: Database session
        conversation: Conversation object

    Returns:
        List of dicts with sentence, speaker, and position info
    """
    conv_sentences = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == conversation.id)
        .options(joinedload(ConversationSentence.sentence).joinedload(Sentence.translations))
        .order_by(ConversationSentence.position)
        .all()
    )

    return [
        {
            "position": cs.position,
            "turn_index": cs.turn_index,
            "speaker": cs.speaker,
            "sentence": cs.sentence,
            "sentence_id": cs.sentence_id,
        }
        for cs in conv_sentences
    ]


def update_conversation(
    session: Session,
    conversation: Conversation,
    title: Optional[str] = None,
    theme: Optional[str] = None,
    verified: Optional[bool] = None,
    rejected: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Conversation:
    """Update a conversation's metadata.

    Args:
        session: Database session
        conversation: Conversation object to update
        title: New title (optional)
        theme: New theme (optional)
        verified: New verification status (optional)
        rejected: New rejection status (optional)
        notes: New notes (optional)

    Returns:
        Updated Conversation object
    """
    if title is not None:
        conversation.title = title
    if theme is not None:
        conversation.theme = theme
    if verified is not None:
        conversation.verified = verified
    if rejected is not None:
        conversation.rejected = rejected
    if notes is not None:
        conversation.notes = notes

    return conversation


def delete_conversation(session: Session, conversation: Conversation) -> None:
    """Delete a conversation and all its sentence links.

    Note: This does NOT delete the underlying sentences, only the links.

    Args:
        session: Database session
        conversation: Conversation object to delete
    """
    session.delete(conversation)


def get_sentences_in_conversations(session: Session, sentence_id: int) -> List[Conversation]:
    """Find all conversations that contain a specific sentence.

    Args:
        session: Database session
        sentence_id: ID of the sentence to search for

    Returns:
        List of Conversation objects containing the sentence
    """
    conv_sentences = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.sentence_id == sentence_id)
        .options(joinedload(ConversationSentence.conversation))
        .all()
    )

    return [cs.conversation for cs in conv_sentences]
