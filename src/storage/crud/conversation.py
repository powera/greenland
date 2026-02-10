"""CRUD operations for Conversation and ConversationSentence models."""

import json
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session, joinedload

from storage.models.schema import (
    Conversation,
    ConversationSentence,
    Sentence,
    SentenceTranslation,
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
) -> ConversationSentence:
    """Link a sentence to a conversation.

    Args:
        session: Database session
        conversation: Conversation to add sentence to
        sentence: Sentence to add
        position: Position in conversation (0-indexed)
        speaker: Speaker identifier (e.g., "A", "B", or character name)

    Returns:
        Created ConversationSentence link object
    """
    conv_sentence = ConversationSentence(
        conversation_id=conversation.id,
        sentence_id=sentence.id,
        position=position,
        speaker=speaker,
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
