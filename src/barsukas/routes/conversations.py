#!/usr/bin/python3

"""Routes for conversation management."""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from barsukas.config import Config
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import case
from werkzeug.wrappers import Response

import constants
from barsukas.helpers.flash_helpers import flash_and_log
from sentences.dialog_coverage import POS_NAME, CoverageReport, analyze_lines
from sentences.dialog_scene import DEFAULT_NUM_TURNS, SceneRequest
from storage.crud.name_entity import get_or_create_name
from storage.crud.sentence import (
    find_duplicate_sentences,
    get_sentence_conversation_count,
    merge_duplicate_sentences,
)
from storage.models.imports import PendingImport
from storage.models.name_entity import (
    NAME_KIND_LABELS,
    NAME_KINDS,
    Name,
    normalize_name_text,
)
from storage.models.schema import (
    Conversation,
    ConversationSentence,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import get_supported_languages
from workqueue.task_queue import TaskType, enqueue_task

logger = logging.getLogger(__name__)

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


@bp.route("/new")
def new_dialog() -> ResponseReturnValue:
    """Show the form for generating a dialog from a scene."""
    return render_template(
        "conversations/new.html",
        default_model=constants.DEFAULT_MODEL,
        default_turns=DEFAULT_NUM_TURNS,
        default_level=request.args.get("target_level", type=int) or 1,
        scene=request.args.get("scene", ""),
    )


@bp.route("/generate", methods=["POST"])
def generate_dialog() -> Response:
    """Queue generation of a dialog for a scene at a target level.

    The dialog is written by the worker rather than in-request: generation is a
    multi-second LLM call, and the result is a stored conversation the reviewer
    opens afterwards rather than a page that has to be waited on.
    """
    if current_app.config.get("READONLY"):
        flash("Cannot generate dialogs in read-only mode", "error")
        return redirect(url_for("conversations.list_conversations"))

    scene = request.form.get("scene", "").strip()
    target_level = request.form.get("target_level", type=int) or 1
    num_turns = request.form.get("num_turns", type=int) or DEFAULT_NUM_TURNS
    model = request.form.get("model", "").strip() or constants.DEFAULT_MODEL
    notes = request.form.get("notes", "").strip() or None

    scene_request = SceneRequest(
        scene=scene,
        target_level=target_level,
        num_turns=num_turns,
        model=model,
        notes=notes,
    )
    try:
        scene_request.validate()
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("conversations.new_dialog", scene=scene, target_level=target_level))

    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.CONVERSATIONS_SCENE_GENERATE,
            target_type=None,
            target_id=None,
            payload={
                "scene": scene,
                "target_level": target_level,
                "num_turns": num_turns,
                "model": model,
                "notes": notes,
            },
            dedup_key=f"{TaskType.CONVERSATIONS_SCENE_GENERATE}:{target_level}:{scene.lower()}",
        )
        g.db.commit()
    except Exception as exc:
        g.db.rollback()
        flash_and_log(f"Error queueing dialog generation: {exc}", "error")
        return redirect(url_for("conversations.new_dialog", scene=scene))

    if result.created:
        flash(
            f"Queued a level {target_level} dialog for {scene!r}. "
            "It will appear in the conversation list once the worker finishes.",
            "success",
        )
    else:
        flash("That scene is already queued at this level.", "info")

    return redirect(url_for("barsukas_tasks.list_tasks"))


def _conversation_cast_names(conversation: Conversation) -> List[str]:
    """Names this conversation casts, read from its stored word links.

    The links are the authoritative record -- registering a name relinks the
    words, so the cast follows without a second place to keep in sync. The
    keywords column is a fallback for conversations generated before word
    linking existed (and is only ever display/search data).
    """
    rows = (
        g.db.query(Name.name_text)
        .join(SentenceWord, SentenceWord.name_id == Name.id)
        .join(ConversationSentence, ConversationSentence.sentence_id == SentenceWord.sentence_id)
        .filter(ConversationSentence.conversation_id == conversation.id)
        .distinct()
        .all()
    )
    if rows:
        return [row[0] for row in rows]

    if not conversation.keywords:
        return []
    try:
        parsed = json.loads(conversation.keywords)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _coverage_for_conversation(
    conversation: Conversation, sentences_data: List[Dict[str, Any]]
) -> Optional[CoverageReport]:
    """Compute vocabulary coverage for a conversation's English lines.

    Recomputed on each view rather than stored, so coverage improves on its own
    as missing words are added to the dictionary.

    Returns:
        The report, or None when the conversation has no English text.
    """
    lines = [
        entry["translations"].get("en", "") for entry in sentences_data if entry["translations"]
    ]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return None

    target_level = conversation.target_level or conversation.minimum_level or 1
    try:
        return analyze_lines(
            g.db,
            lines,
            target_level=target_level,
            cast_names=_conversation_cast_names(conversation),
        )
    except Exception as exc:  # pragma: no cover - coverage is advisory
        logger.warning("Coverage analysis failed for conversation %s: %s", conversation.id, exc)
        return None


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
    coverage = _coverage_for_conversation(conversation, sentences_data)

    return render_template(
        "conversations/view.html",
        conversation=conversation,
        keywords=keywords,
        sentences_data=sentences_data,
        language_names=language_names,
        coverage=coverage,
        staged_words=_already_staged_words(coverage),
        name_kinds=NAME_KINDS,
        name_kind_labels=NAME_KIND_LABELS,
    )


def _already_staged_words(coverage: Optional[CoverageReport]) -> Dict[str, int]:
    """Map missing words that are already in the import queue to their ids.

    A staged word stays in the missing list until it actually becomes a lemma,
    so the page has to say which ones are already waiting or the reviewer has no
    way to tell an untouched word from one they staged a minute ago.
    """
    if coverage is None or not coverage.missing:
        return {}

    words = [token.surface for token in coverage.missing]
    rows = (
        g.db.query(PendingImport.english_word, PendingImport.id)
        .filter(PendingImport.english_word.in_(words))
        .all()
    )
    return {row[0]: row[1] for row in rows}


@bp.route("/<int:conversation_id>/stage-word", methods=["POST"])
def stage_word(conversation_id: int) -> Response:
    """Stage a word the dialog used but the dictionary lacks as a pending import.

    Nothing enters the dictionary here: the word lands in the existing intake
    queue with the dialog line as its context, and the usual disambiguation and
    synonym-candidate review decides what becomes a lemma.
    """
    if current_app.config.get("READONLY"):
        flash("Cannot stage words in read-only mode", "error")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    word = request.form.get("word", "").strip()
    example_line = request.form.get("example_line", "").strip()
    if not word:
        flash("No word given to stage", "error")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    existing = g.db.query(PendingImport).filter(PendingImport.english_word == word).first()
    if existing is not None:
        flash(f"{word!r} is already staged as pending import #{existing.id}.", "info")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    try:
        pending = PendingImport(
            english_word=word,
            # The dialog line stands in for a definition until intake supplies
            # one; it is the context a reviewer needs to pick the right sense.
            definition=example_line or f"Used in conversation {conversation_id}",
            disambiguation_translation=word,
            disambiguation_language="en",
            example_sentence=example_line or None,
            source=f"dialog_conversation_{conversation_id}",
            notes=f"Missing vocabulary found in conversation {conversation_id}",
        )
        g.db.add(pending)
        g.db.commit()
        flash(f"Staged {word!r} for import.", "success")
    except Exception as exc:
        g.db.rollback()
        flash_and_log(f"Error staging {word!r}: {exc}", "error")

    return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))


@bp.route("/<int:conversation_id>/register-name", methods=["POST"])
def register_name(conversation_id: int) -> Response:
    """Record a token as a proper name and relink the dialog's words to it.

    Used when the generator failed to report a name it used, so the token shows
    up as missing vocabulary. Registering it moves the word out of the
    dictionary's problem list without teaching it as vocabulary.
    """
    if current_app.config.get("READONLY"):
        flash("Cannot register names in read-only mode", "error")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    conversation = g.db.query(Conversation).get(conversation_id)
    if not conversation:
        flash("Conversation not found", "error")
        return redirect(url_for("conversations.list_conversations"))

    name_text = request.form.get("name_text", "").strip()
    kind = request.form.get("kind", "given_name").strip()
    if not name_text:
        flash("No name given", "error")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    try:
        name, created = get_or_create_name(
            session=g.db,
            name_text=name_text,
            kind=kind,
            notes=f"Registered from conversation {conversation_id}",
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))

    normalized = normalize_name_text(name_text)
    sentence_ids = [
        row.sentence_id
        for row in g.db.query(ConversationSentence)
        .filter(ConversationSentence.conversation_id == conversation_id)
        .all()
    ]
    relinked = 0
    if sentence_ids:
        words = (
            g.db.query(SentenceWord)
            .filter(
                SentenceWord.sentence_id.in_(sentence_ids),
                SentenceWord.english_text == normalized,
            )
            .all()
        )
        for word_row in words:
            word_row.name_id = name.id
            word_row.lemma_id = None
            word_row.part_of_speech = POS_NAME
            relinked += 1

    g.db.commit()
    flash(
        f"{'Registered' if created else 'Reused'} name {normalized!r} "
        f"and linked {relinked} word occurrence(s).",
        "success",
    )
    return redirect(url_for("conversations.view_conversation", conversation_id=conversation_id))


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
