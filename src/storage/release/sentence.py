#!/usr/bin/python3

"""Release-file serialization for sentences.

Owns the mapping between ``Sentence`` rows and the records in
``data/release/sentences/{collection}/{pos_dir}/{pos_subtype}/base.jsonl``,
in both directions, with no Flask or CLI dependency -- the Barsukas sync
blueprints and the release CLI both call in here so a record is built in
exactly one place.

A sentence's directory is *derived* (from its collection and its primary
lemma's category) rather than stored, which is why the export is a rebuild
that also removes the files a re-categorization left stale.

Audio is carried inline on each record's ``audio`` key, in the same shape the
lemma tree's ``audio.jsonl`` uses. :func:`import_audio_from_release` reads it
back: without it a release -> database -> release round trip silently dropped
every sentence's audio, because the JSONL backend loads audio reviews only
from the separate (and empty) ``audio_reviews/`` file.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple

from sqlalchemy.orm import Session, selectinload

from storage.models.schema import (
    AudioQualityReview,
    ConversationSentence,
    Sentence,
    SentenceWord,
    SentenceWordHint,
)
from storage.release.io import write_jsonl_atomic

#: Audio statuses that are published to the release tree.
APPROVED_AUDIO_RELEASE_STATUSES = {"approved", "approved_with_issues"}

#: Release-bearing fields on one audio entry, in the order they are written.
SENTENCE_AUDIO_RELEASE_FIELDS: Tuple[str, ...] = (
    "filename",
    "status",
    "expected_text",
    "manifest_md5",
    "s3_prod_url",
    "s3_staging_url",
    "staging_agent",
)

#: (guid, language_code, voice_name) -- the sentence-audio unique key.
SentenceAudioKey = Tuple[str, str, str]

# POS type -> release directory name (pluralized).
TYPE_TO_DIR: Dict[str, str] = {
    "noun": "nouns",
    "verb": "verbs",
    "adjective": "adjectives",
    "adverb": "adverbs",
    "pronoun": "pronouns",
    "preposition": "prepositions",
    "conjunction": "conjunctions",
    "interjection": "interjections",
    "numeral": "numerals",
    "particle": "particles",
}


@dataclass(frozen=True)
class SentenceExportStats:
    """What one sentence export wrote."""

    sentences: int = 0
    files: int = 0
    removed: int = 0


@dataclass(frozen=True)
class SentenceAudioImportStats:
    """What one sentence-audio import changed."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0


def sentence_word_to_record(word: Any) -> Dict[str, Any]:
    """Serialize one SentenceWord to its on-disk shape.

    Lemmas are referenced by GUID (the stable, on-disk identifier used
    throughout data/release); integer lemma_ids are ephemeral and would not
    survive a JSONL -> SQLite reload. The ``word_role`` key retains the
    database column name, which the JSONL read path maps back to
    ``part_of_speech``.

    ``name_guid`` is emitted for the same reason, and -- like the ``ud_*``
    dependency fields -- only when set: a word that resolves to a proper name
    is not an unresolved gap, and without the key the two cases were
    indistinguishable on disk (both ``lemma_guid: null``). Proper names and UD
    dependency parsing are both unfinished features with no rows in the
    database and no keys in ``data/release``, so writing them as explicit
    nulls would add three dead keys to every word of every sentence.

    Shared by every sentence-word serialization path so a newly added column
    reaches all of them at once.
    """
    record: Dict[str, Any] = {
        "lemma_guid": word.lemma.guid if word.lemma and word.lemma.guid else None,
        "language_code": word.language_code,
        "position": word.position,
        "word_role": word.word_role,
        "english_text": word.english_text,
        "target_language_text": word.target_language_text,
        "grammatical_form": word.grammatical_form,
        "grammatical_case": word.grammatical_case,
        "declined_form": word.declined_form,
    }
    name_guid = word.name.guid if word.name and word.name.guid else None
    if name_guid is not None:
        record["name_guid"] = name_guid
    if word.ud_relation is not None:
        record["ud_relation"] = word.ud_relation
    if word.ud_head_position is not None:
        record["ud_head_position"] = word.ud_head_position
    return record


def resolve_primary_lemma_category(sentence: Any) -> Tuple[str, str]:
    """Resolve the primary lemma category for directory placement.

    Returns (pos_type, pos_subtype) based on the noun with the lowest GUID
    among the sentence's word hints.  Falls back to any lemma with the
    lowest GUID, or ("misc", "misc") if nothing resolves.
    """
    lemmas_with_guids = []
    for pw in sentence.word_hints:
        if pw.lemma and pw.lemma.guid:
            lemmas_with_guids.append(pw.lemma)

    if not lemmas_with_guids:
        return ("misc", "misc")

    # Prefer nouns
    nouns = [l for l in lemmas_with_guids if l.pos_type and l.pos_type.lower() == "noun"]
    if nouns:
        best = min(nouns, key=lambda l: l.guid)
    else:
        best = min(lemmas_with_guids, key=lambda l: l.guid)

    pos_type = best.pos_type.lower() if best.pos_type else "misc"
    pos_subtype = best.pos_subtype.lower() if best.pos_subtype else "other"
    return (pos_type, pos_subtype)


def to_release_record(sentence: Any) -> Dict[str, Any]:
    """Convert a Sentence ORM object to a release JSONL record."""
    from storage.translation_helpers import RELEASE_LANGUAGES

    release_lang_set = set(RELEASE_LANGUAGES)
    translations: Dict[str, str] = {}
    for trans in sentence.translations:
        if trans.language_code not in release_lang_set:
            continue
        if trans.translation_text and trans.translation_text.strip():
            translations[trans.language_code] = trans.translation_text

    word_hints: List[Dict[str, Any]] = []
    for pw in sorted(sentence.word_hints, key=lambda p: p.position):
        lemma_guid = pw.lemma.guid if pw.lemma and pw.lemma.guid else None
        # See sentence_word_to_record: a name-filled slot has to stay
        # distinguishable from an unresolved one, but the key is omitted while
        # proper names are unfinished rather than written as a dead null.
        hint_name_guid = pw.name.guid if pw.name and pw.name.guid else None
        # A hint that references neither a lemma nor a name is not exportable:
        # ck_word_hint_has_reference requires one of them, so an import could
        # only skip such a row, and the export would be writing something the
        # schema cannot hold.  These are word *tokens* left over from before
        # sentences carried per-word decompositions ("my", "bike", "math"),
        # they name no vocabulary, and the staging back-link they once fed
        # moved to SentencePendingImport.  Dropping them here is what makes the
        # release -> database -> release round trip stable.
        if lemma_guid is None and hint_name_guid is None:
            continue
        hint: Dict[str, Any] = {
            "position": pw.position,
            "slot_name": pw.slot_name,
            "lemma_guid": lemma_guid,
            "english_text": pw.english_text,
        }
        if hint_name_guid is not None:
            hint["name_guid"] = hint_name_guid
        word_hints.append(hint)

    record: Dict[str, Any] = {
        "guid": sentence.guid,
    }
    if sentence.sentence_collection:
        record["collection"] = sentence.sentence_collection
    # Which agent or corpus file produced this sentence. The release never
    # carried it, so a bootstrap nulled the column on every row it loaded.
    if sentence.source_filename:
        record["source_filename"] = sentence.source_filename
    if sentence.pattern_type:
        record["pattern_type"] = sentence.pattern_type
    if sentence.tense:
        record["tense"] = sentence.tense
    if sentence.minimum_level is not None:
        record["minimum_level"] = sentence.minimum_level
    if translations:
        record["translations"] = translations
    if word_hints:
        record["word_hints"] = word_hints
    if sentence.notes:
        record["notes"] = sentence.notes

    words: List[Dict[str, Any]] = [
        sentence_word_to_record(sentence_word)
        for sentence_word in sorted(
            sentence.words,
            key=lambda current_word: (current_word.language_code, current_word.position),
        )
    ]
    if words:
        record["words"] = words

    audio: List[Dict[str, Any]] = []
    for audio_review in sorted(
        sentence.audio_reviews,
        key=lambda current_audio: (current_audio.language_code, current_audio.voice_name),
    ):
        if audio_review.status not in APPROVED_AUDIO_RELEASE_STATUSES:
            continue
        audio.append(
            {
                "language_code": audio_review.language_code,
                "voice_name": audio_review.voice_name,
                "filename": audio_review.filename,
                "status": audio_review.status,
                "expected_text": audio_review.expected_text,
                "manifest_md5": audio_review.manifest_md5,
                "s3_prod_url": audio_review.s3_prod_url,
                "s3_staging_url": audio_review.s3_staging_url,
                "staging_agent": audio_review.staging_agent,
            }
        )
    if audio:
        record["audio"] = audio

    return record


def export_to_release(session: Session, release_dir: Path) -> SentenceExportStats:
    """Export sentences from SQLite to data/release/sentences format.

    Sentences are grouped first by their **collection** (sentence_collection field,
    defaulting to "general"), then by primary lemma pos_type/pos_subtype — the noun
    with the lowest GUID among word hints, falling back to misc/misc.

    Structure: {release_dir}/{collection}/{pos_dir}/{pos_subtype}/base.jsonl

    Conversation and rejected sentences are excluded.

    Args:
    sqlite_path: Path to SQLite database
    release_dir: Directory to write release files (e.g., data/release/sentences)
    """
    # Map POS types to directory names (pluralized)
    type_to_dir: Dict[str, str] = {
        "noun": "nouns",
        "verb": "verbs",
        "adjective": "adjectives",
        "adverb": "adverbs",
        "pronoun": "pronouns",
        "preposition": "prepositions",
        "conjunction": "conjunctions",
        "interjection": "interjections",
        "numeral": "numerals",
        "particle": "particles",
    }

    # Exclude conversation sentences
    conversation_ids: Set[int] = set(
        row[0] for row in session.query(ConversationSentence.sentence_id).distinct().all()
    )

    # Get all sentences with GUIDs, eager-load relationships
    sentences = (
        session.query(Sentence)
        .filter(Sentence.guid.isnot(None))
        .filter(Sentence.rejected.is_(False))
        .options(
            selectinload(Sentence.translations),
            selectinload(Sentence.word_hints).selectinload(SentenceWordHint.lemma),
            selectinload(Sentence.words).selectinload(SentenceWord.lemma),
            selectinload(Sentence.audio_reviews),
        )
        .order_by(Sentence.guid)
        .all()
    )

    # Filter out conversation sentences
    sentences = [s for s in sentences if s.id not in conversation_ids]
    print(f"Found {len(sentences)} non-conversation, non-rejected sentences to export")

    # Group sentences by (collection, pos_type, pos_subtype)
    sentences_by_category: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

    for sentence in sentences:
        record = to_release_record(sentence)
        collection = sentence.sentence_collection or "general"
        pos_type, pos_subtype = resolve_primary_lemma_category(sentence)
        sentences_by_category[(collection, pos_type, pos_subtype)].append(record)

    print(f"Organized into {len(sentences_by_category)} categories")

    written_files: Set[Path] = set()
    for (collection, pos_type, pos_subtype), records in sentences_by_category.items():
        dir_name = type_to_dir.get(pos_type, pos_type)
        category_dir = release_dir / collection / dir_name / pos_subtype
        category_dir.mkdir(parents=True, exist_ok=True)

        # Sort by GUID within each file
        records.sort(key=lambda r: r["guid"])

        print(f"Exporting {len(records)} sentences to {collection}/{dir_name}/{pos_subtype}...")
        base_file = category_dir / "base.jsonl"
        write_jsonl_atomic(base_file, records)
        written_files.add(base_file.resolve())

    # A category that had sentences before and has none now must lose its
    # file, or the export stops being a rebuild -- the same rule the lemma
    # export follows above.  This matters more here than on the lemma side
    # because a sentence's directory is *derived* (from its collection and
    # its primary lemma's category), not stored: re-categorizing a sentence
    # moves its record to a different file and leaves the old one behind,
    # still holding the stale copy that the next import would read back.
    removed_count = 0
    for stale_file in release_dir.rglob("base.jsonl"):
        if stale_file.resolve() in written_files:
            continue
        stale_file.unlink()
        removed_count += 1

    # Prune the directories those files left empty, deepest first, so a
    # renamed collection does not leave an empty tree behind.  Anything
    # still holding a file (or a file this export does not manage) stops
    # the walk up.
    for stale_dir in sorted(release_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if stale_dir.is_dir() and not any(stale_dir.iterdir()):
            stale_dir.rmdir()

    if removed_count:
        print(f"Removed {removed_count} stale category file(s)")

    print("Sentence export complete!")
    return SentenceExportStats(
        sentences=len(sentences), files=len(written_files), removed=removed_count
    )


def iter_release_audio_entries(
    release_dir: Path,
) -> Iterator[Tuple[SentenceAudioKey, Dict[str, Any]]]:
    """Yield every well-formed sentence-audio entry in the release files.

    Keyed the way :func:`to_release_record` writes them. Entries missing a
    language or voice cannot be keyed and are skipped.
    """
    for base_file in sorted(release_dir.rglob("base.jsonl")):
        with open(base_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                guid = data.get("guid")
                if not guid:
                    continue
                for entry in data.get("audio", []):
                    language_code = entry.get("language_code")
                    voice_name = entry.get("voice_name")
                    if not language_code or not voice_name:
                        print(f"Warning: {base_file} guid {guid} has audio without a voice")
                        continue
                    yield (guid, language_code, voice_name), entry


def import_audio_from_release(session: Session, release_dir: Path) -> SentenceAudioImportStats:
    """Sync sentence audio from the release files back into the database.

    The export writes each sentence's approved audio inline on its record, but
    nothing read it back: the JSONL backend populates ``AudioQualityReview``
    only from the separate ``audio_reviews/`` file, which ships empty. So a
    database rebuilt from ``data/release`` lost every sentence's audio, and
    re-exporting it silently dropped the ``audio`` key from ~99 records.

    Rows are matched on (guid, language_code, voice_name) and scoped to
    sentence audio, so this never touches the lemma-audio rows that
    ``storage.release.lemma_audio`` owns.
    """
    added = updated = unchanged = 0

    sentence_id_by_guid: Dict[str, int] = {
        guid: sentence_id
        for sentence_id, guid in session.query(Sentence.id, Sentence.guid)
        .filter(Sentence.guid.isnot(None))
        .all()
    }

    for (guid, language_code, voice_name), entry in iter_release_audio_entries(release_dir):
        existing = (
            session.query(AudioQualityReview)
            .filter(
                AudioQualityReview.guid == guid,
                AudioQualityReview.language_code == language_code,
                AudioQualityReview.voice_name == voice_name,
                AudioQualityReview.sentence_id.isnot(None),
            )
            .one_or_none()
        )

        if existing is None:
            session.add(
                AudioQualityReview(
                    guid=guid,
                    language_code=language_code,
                    voice_name=voice_name,
                    filename=entry.get("filename", ""),
                    expected_text=entry.get("expected_text", ""),
                    manifest_md5=entry.get("manifest_md5", ""),
                    status=entry.get("status", "approved"),
                    s3_prod_url=entry.get("s3_prod_url"),
                    s3_staging_url=entry.get("s3_staging_url"),
                    staging_agent=entry.get("staging_agent"),
                    sentence_id=sentence_id_by_guid.get(guid),
                )
            )
            added += 1
            continue

        # Only count a row as updated when a release-bearing field really
        # moved; re-importing an unchanged file reports zero updates.
        changed = False
        for field_name in SENTENCE_AUDIO_RELEASE_FIELDS:
            if field_name not in entry:
                continue
            if getattr(existing, field_name) != entry[field_name]:
                setattr(existing, field_name, entry[field_name])
                changed = True
        if existing.sentence_id is None:
            resolved = sentence_id_by_guid.get(guid)
            if resolved is not None:
                existing.sentence_id = resolved
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    session.commit()
    print(f"Sentence audio sync complete! Added {added}, updated {updated}, unchanged {unchanged}.")
    return SentenceAudioImportStats(added=added, updated=updated, unchanged=unchanged)
