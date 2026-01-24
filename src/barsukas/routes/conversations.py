#!/usr/bin/python3

"""Routes for conversation management."""

import json
from typing import Union

from barsukas.config import Config
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import case
from werkzeug.wrappers import Response

from barsukas.helpers.flash_helpers import flash_and_log
from wordfreq.storage.crud.sentence import (
    find_duplicate_sentences,
    get_sentence_conversation_count,
    merge_duplicate_sentences,
)
from wordfreq.storage.models.schema import (
    Conversation,
    ConversationSentence,
    Sentence,
    SentenceTranslation,
)
from wordfreq.storage.translation_helpers import get_supported_languages

bp = Blueprint("conversations", __name__, url_prefix="/conversations")


@bp.route("/")
def list_conversations() -> ResponseReturnValue:
    """List all conversations with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    minimum_level = request.args.get("minimum_level", "", type=str).strip()
    show_all = request.args.get("show_all", "no")

    # Build query
    query = g.db.query(Conversation)

    # By default, exclude verified and rejected conversations unless specifically requested
    if show_all != "yes":
        query = query.filter(Conversation.verified == False)
        query = query.filter(Conversation.rejected == False)

    # Apply filters
    if search:
        # Search in title or keywords
        query = query.filter(
            (Conversation.title.ilike(f"%{search}%")) | (Conversation.keywords.ilike(f"%{search}%"))
        )

    if minimum_level:
        if minimum_level == "null":
            query = query.filter(Conversation.minimum_level.is_(None))
        else:
            query = query.filter(Conversation.minimum_level == int(minimum_level))

    # Order by minimum level (NULL at end), then by ID
    level_order = case((Conversation.minimum_level.is_(None), 99), else_=Conversation.minimum_level)
    query = query.order_by(level_order, Conversation.id)

    # Paginate
    total = query.count()
    conversations = (
        query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()
    )

    # Batch load sentence counts for all conversations
    conversation_ids = [c.id for c in conversations]
    sentence_counts = {}
    if conversation_ids:
        counts = (
            g.db.query(
                ConversationSentence.conversation_id,
                g.db.query(ConversationSentence)
                .filter(
                    ConversationSentence.conversation_id == ConversationSentence.conversation_id
                )
                .count(),
            )
            .filter(ConversationSentence.conversation_id.in_(conversation_ids))
            .group_by(ConversationSentence.conversation_id)
            .all()
        )
        # Actually let's do this more simply
        from sqlalchemy import func

        counts = (
            g.db.query(
                ConversationSentence.conversation_id,
                func.count(ConversationSentence.id).label("count"),
            )
            .filter(ConversationSentence.conversation_id.in_(conversation_ids))
            .group_by(ConversationSentence.conversation_id)
            .all()
        )
        sentence_counts = {c.conversation_id: c.count for c in counts}

    # Parse keywords for display
    conversation_keywords = {}
    for conv in conversations:
        if conv.keywords:
            try:
                conversation_keywords[conv.id] = json.loads(conv.keywords)
            except json.JSONDecodeError:
                conversation_keywords[conv.id] = []
        else:
            conversation_keywords[conv.id] = []

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "conversations/list.html",
        conversations=conversations,
        sentence_counts=sentence_counts,
        conversation_keywords=conversation_keywords,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        minimum_level=minimum_level,
        show_all=show_all,
    )


@bp.route("/<int:conversation_id>")
def view_conversation(conversation_id: int) -> Union[str, Response]:
    """View a single conversation with all sentences and translations."""
    conversation = g.db.query(Conversation).get(conversation_id)
    if not conversation:
        flash("Conversation not found", "error")
        return redirect(url_for("conversations.list_conversations"))

    # Parse keywords
    keywords = []
    if conversation.keywords:
        try:
            keywords = json.loads(conversation.keywords)
        except json.JSONDecodeError:
            keywords = []

    # Get all conversation sentences ordered by position
    conv_sentences = (
        g.db.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == conversation_id)
        .order_by(ConversationSentence.position)
        .all()
    )

    # Batch load all sentences
    sentence_ids = [cs.sentence_id for cs in conv_sentences]
    sentences_by_id = {}
    if sentence_ids:
        sentences = g.db.query(Sentence).filter(Sentence.id.in_(sentence_ids)).all()
        sentences_by_id = {s.id: s for s in sentences}

    # Batch load all translations for these sentences
    translations_by_sentence: dict[int, dict[str, str]] = {}
    if sentence_ids:
        all_translations = (
            g.db.query(SentenceTranslation)
            .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
            .all()
        )
        for t in all_translations:
            if t.sentence_id not in translations_by_sentence:
                translations_by_sentence[t.sentence_id] = {}
            translations_by_sentence[t.sentence_id][t.language_code] = t.translation_text

    # Build sentences data with speaker info
    sentences_data = []
    for cs in conv_sentences:
        sentence = sentences_by_id.get(cs.sentence_id)
        translations = translations_by_sentence.get(cs.sentence_id, {})
        sentences_data.append(
            {
                "position": cs.position,
                "speaker": cs.speaker,
                "sentence_id": cs.sentence_id,
                "sentence": sentence,
                "translations": translations,
            }
        )

    language_names = get_supported_languages()

    return render_template(
        "conversations/view.html",
        conversation=conversation,
        keywords=keywords,
        sentences_data=sentences_data,
        language_names=language_names,
    )


@bp.route("/<int:conversation_id>/verify", methods=["POST"])
def verify_conversation(conversation_id: int) -> Response:
    """Mark a conversation as verified."""
    conversation = g.db.query(Conversation).get(conversation_id)
    if not conversation:
        flash("Conversation not found", "error")
        return redirect(url_for("conversations.list_conversations"))

    try:
        conversation.verified = True
        g.db.commit()
        flash(f"Conversation #{conversation_id} verified", "success")
    except Exception as e:
        flash(f"Error verifying conversation: {e}", "error")
        g.db.rollback()

    return redirect(request.referrer or url_for("conversations.list_conversations"))


@bp.route("/<int:conversation_id>/reject", methods=["POST"])
def reject_conversation(conversation_id: int) -> Response:
    """Mark a conversation as rejected so it won't be regenerated."""
    conversation = g.db.query(Conversation).get(conversation_id)
    if not conversation:
        flash("Conversation not found", "error")
        return redirect(url_for("conversations.list_conversations"))

    try:
        conversation.rejected = True
        g.db.commit()
        flash(f"Conversation #{conversation_id} marked as rejected", "success")
    except Exception as e:
        flash(f"Error rejecting conversation: {e}", "error")
        g.db.rollback()

    return redirect(request.referrer or url_for("conversations.list_conversations"))


@bp.route("/dedupe")
def dedupe_sentences() -> ResponseReturnValue:
    """Show duplicate sentences that can be merged."""
    duplicates = find_duplicate_sentences(g.db, language_code="en")

    # Enrich with conversation counts for each sentence
    duplicates_data = []
    for text, sentences in duplicates:
        sentences_info = []
        for sentence in sentences:
            conv_count = get_sentence_conversation_count(g.db, sentence.id)
            # Get translation count
            trans_count = len(sentence.translations) if sentence.translations else 0
            sentences_info.append(
                {
                    "sentence": sentence,
                    "conversation_count": conv_count,
                    "translation_count": trans_count,
                }
            )
        # Sort by most translations first (prefer to keep the most complete one)
        sentences_info.sort(
            key=lambda x: (-x["translation_count"], -x["conversation_count"])  # type: ignore[operator]
        )
        duplicates_data.append(
            {
                "text": text,
                "sentences": sentences_info,
                "total_sentences": len(sentences_info),
            }
        )

    # Sort by number of duplicates (most duplicates first)
    duplicates_data.sort(key=lambda x: -x["total_sentences"])  # type: ignore[operator]

    return render_template(
        "conversations/dedupe.html",
        duplicates=duplicates_data,
        total_groups=len(duplicates_data),
    )


@bp.route("/dedupe/merge", methods=["POST"])
def merge_sentences() -> Response:
    """Merge duplicate sentences into one."""
    keep_id = request.form.get("keep_id", type=int)
    duplicate_ids_str = request.form.get("duplicate_ids", "")

    if not keep_id:
        flash("No sentence selected to keep", "error")
        return redirect(url_for("conversations.dedupe_sentences"))

    # Parse duplicate IDs
    duplicate_ids = []
    if duplicate_ids_str:
        try:
            duplicate_ids = [int(x.strip()) for x in duplicate_ids_str.split(",") if x.strip()]
        except ValueError:
            flash("Invalid duplicate IDs format", "error")
            return redirect(url_for("conversations.dedupe_sentences"))

    if not duplicate_ids:
        flash("No duplicates selected to merge", "error")
        return redirect(url_for("conversations.dedupe_sentences"))

    try:
        stats = merge_duplicate_sentences(g.db, keep_id, duplicate_ids)
        g.db.commit()

        flash(
            f"Merged {stats['sentences_deleted']} duplicate(s) into sentence #{keep_id}. "
            f"Updated {stats['conversations_updated']} conversation link(s), "
            f"merged {stats['translations_merged']} translation(s).",
            "success",
        )
    except ValueError as e:
        flash(f"Error: {e}", "error")
        g.db.rollback()
    except Exception as e:
        flash(f"Error merging sentences: {e}", "error")
        g.db.rollback()

    return redirect(url_for("conversations.dedupe_sentences"))
