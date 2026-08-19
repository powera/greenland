#!/usr/bin/python3

"""Main sync hub route - entry point for all sync operations.

The hub lists the sync categories as data rather than as hand-written cards, so
adding an element type means adding an entry here instead of copying a block of
Bootstrap markup.

Deliberately absent: concepts. They are keyed to Wikidata and never enter
``data/release`` (see ``docs/element_types_design.md``); the only piece of
concept data that ships is a lemma's Q-id, which the lemma sync already
reconciles.
"""

from dataclasses import dataclass
from typing import List

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

bp = Blueprint("sync_hub", __name__, url_prefix="/sync")


@dataclass(frozen=True)
class SyncCategory:
    """One card on the hub: what it syncs and where to go."""

    #: Endpoint of the category's own landing page.
    endpoint: str
    #: Card title.
    title: str
    #: Bootstrap icon name.
    icon: str
    #: Bootstrap contextual colour for the header and button.
    colour: str
    #: One sentence on what this category covers.
    summary: str
    #: Bullet points naming the specific things it syncs.
    covers: List[str]


#: The hub's categories, in the order they are shown.
#:
#: Ordered roughly by how often they are used rather than alphabetically:
#: lemmas first because that is where most reconciliation happens, and lemma
#: audio last because it is a bulk mirror rather than a per-word review.
SYNC_CATEGORIES: List[SyncCategory] = [
    SyncCategory(
        endpoint="sync_release.index",
        title="Lemmas",
        icon="bi-book",
        colour="primary",
        summary="Base lemma records: the words themselves and their translations.",
        covers=[
            "Additions & removals",
            "Text, definition and emoji changes",
            "Difficulty levels",
            "Primary and secondary translations",
            "Grammar facts",
        ],
    ),
    SyncCategory(
        endpoint="sync_derivative_release.index",
        title="Derivative Forms",
        icon="bi-diagram-3",
        colour="success",
        summary="Conjugations, declensions and other derived forms, per language.",
        covers=["Per-language forms", "Grammatical patterns", "Pronunciations (IPA)"],
    ),
    SyncCategory(
        endpoint="sync_synonym_release.index",
        title="Synonyms",
        icon="bi-link-45deg",
        colour="secondary",
        summary="Per-language synonym entries, kept separate from inflected forms.",
        covers=[
            "synonym, synonym_near",
            "synonym_regional, synonym_register",
            "synonym_synecdoche, synonym_related",
        ],
    ),
    SyncCategory(
        endpoint="sync_variant_release.index",
        title="Spelling Variants",
        icon="bi-fonts",
        colour="success",
        summary="Alternate spellings of the same word, each with its own paradigm.",
        covers=[
            "spelling (gray / grey)",
            "script (Chinese simplified / traditional)",
            "Per-variant paradigms and pronunciations",
        ],
    ),
    SyncCategory(
        endpoint="sync_relation_release.index",
        title="Relations",
        icon="bi-diagram-2",
        colour="info",
        summary="Semantic relationships between lemmas.",
        covers=["Synonyms & antonyms", "Derivational groups", "Thematic categories"],
    ),
    SyncCategory(
        endpoint="sync_sentence_release.index",
        title="Sentences",
        icon="bi-chat-left-text",
        colour="warning",
        summary="Example sentences and their translations.",
        covers=[
            "Additions & removals",
            "Text changes",
            "Difficulty levels",
            "Translations, word hints and audio",
        ],
    ),
    SyncCategory(
        endpoint="sync_phrase_release.index",
        title="Phrases",
        icon="bi-chat-quote",
        colour="dark",
        summary="Fixed traveler and greeting phrases and their translations.",
        covers=["Additions & removals", "Text changes", "Difficulty levels", "Translations"],
    ),
    SyncCategory(
        endpoint="sync_idiom_release.index",
        title="Idioms",
        icon="bi-chat-square-quote",
        colour="danger",
        summary="Source-language idioms and their equivalents in other languages.",
        covers=[
            "Additions & removals",
            "Whole-record changes",
            "Equivalents, glosses and register",
        ],
    ),
    SyncCategory(
        endpoint="sync_name_release.index",
        title="Names",
        icon="bi-person-badge",
        colour="primary",
        summary="Proper names and their stable per-language renderings.",
        covers=[
            "Additions & removals",
            "Whole-record changes",
            "Renderings, transcriptions and sort keys",
        ],
    ),
    SyncCategory(
        endpoint="sync_tombstone_release.index",
        title="GUID Tombstones",
        icon="bi-archive",
        colour="dark",
        summary="Retired GUIDs, which must never be issued to another word.",
        covers=[
            "Additions & removals",
            "Replacement links and reasons",
            "Export only - a tombstone is never deleted",
        ],
    ),
    SyncCategory(
        endpoint="sync_lemma_audio_release.index",
        title="Lemma Audio",
        icon="bi-music-note-list",
        colour="secondary",
        summary="Approved lemma audio references in the per-category audio.jsonl files.",
        covers=[
            "Metadata only, not mp3 bytes",
            "Import / export whole directories",
            "Difference summary preview",
        ],
    ),
]


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display main sync hub with links to all sync categories."""
    return render_template("sync_hub/index.html", categories=SYNC_CATEGORIES)
