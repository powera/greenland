#!/usr/bin/python3

"""Release-file serialization for approved lemma audio.

Owns the mapping between ``AudioQualityReview`` rows and the per-category
``audio.jsonl`` files that sit inside the lemma tree, in both directions, with
no Flask or CLI dependency.

Lemma audio is the one element type the release round trip treats as a
*mirror* rather than a rebuild: the files carry metadata only (filenames, S3
URLs, review status), never mp3 bytes, and an import can be scoped to a subset
of categories or asked to prune rows the files no longer list. That is why the
import takes ``categories``/``keys``/``prune`` where the other element types
take nothing, and why this module also builds the release-vs-database diff the
Barsukas sync page renders before an operator commits either direction.

Names here drop the redundant ``lemma_audio`` infix that the CLI module gave
them -- ``lemma_audio.export_to_release``, not
``export_lemma_audio_release_from_session``.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Dict, Iterator, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Lemma
from storage.release.io import write_jsonl_atomic

#: Audio statuses that are published to the release tree.
APPROVED_AUDIO_RELEASE_STATUSES = {"approved", "approved_with_issues"}


@dataclass
class ExportStats:
    """Summary of a lemma-audio export (SQLite/DB -> release files)."""

    audio_rows: int = 0
    guids: int = 0
    categories: int = 0


@dataclass
class ImportStats:
    """Summary of a lemma-audio import (release files -> SQLite/DB)."""

    added: int = 0
    updated: int = 0
    pruned: int = 0
    unchanged: int = 0


# Directory names for each part of speech, shared by lemma-audio export/import.
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

DIR_TO_TYPE: Dict[str, str] = {dir_name: pos_type for pos_type, dir_name in TYPE_TO_DIR.items()}

# The audio.jsonl entry fields an export writes and an import reads back. Any
# difference in these between the database and the release file is a real change;
# every other AudioQualityReview column is local-only review metadata.
RELEASE_FIELDS: Tuple[str, ...] = (
    "filename",
    "status",
    "expected_text",
    "manifest_md5",
    "s3_prod_url",
    "s3_staging_url",
    "staging_agent",
)

# (guid, language_code, voice_name, grammatical_form) — the lemma-audio unique key.
AudioKey = Tuple[str, str, str, Any]
# (pos_type, pos_subtype) — one release directory's worth of lemma audio.
Category = Tuple[str, str]


def category_slug(category: Category) -> str:
    """Render a category as the ``{pos_dir}/{pos_subtype}`` slug used in forms and URLs."""
    pos_type, pos_subtype = category
    return f"{TYPE_TO_DIR.get(pos_type, pos_type)}/{pos_subtype}"


def parse_category_slug(slug: str) -> Optional[Category]:
    """Parse a ``{pos_dir}/{pos_subtype}`` slug back into a (pos_type, pos_subtype).

    Returns None for anything that is not exactly two non-empty path segments, so
    caller-supplied slugs (form fields, CLI flags) cannot escape the release tree.
    """
    parts = [part for part in slug.strip().strip("/").split("/") if part]
    if len(parts) != 2:
        return None
    dir_name, pos_subtype = parts[0].lower(), parts[1].lower()
    if dir_name in {".", ".."} or pos_subtype in {".", ".."}:
        return None
    return (DIR_TO_TYPE.get(dir_name, dir_name), pos_subtype)


def _category_dir(release_dir: str, category: Category) -> Path:
    """Path of the directory holding one category's ``audio.jsonl``."""
    return Path(release_dir) / category_slug(category)


def _category_for_file(release_dir: str, audio_file: Path) -> Category:
    """Recover the (pos_type, pos_subtype) an ``audio.jsonl`` path belongs to."""
    relative = audio_file.parent.relative_to(Path(release_dir))
    category = parse_category_slug(str(relative))
    if category is None:
        # A stray audio.jsonl at an unexpected depth: keep it addressable rather
        # than dropping it silently, using the raw path as the subtype.
        return ("misc", str(relative))
    return category


def _guids_in_categories(session: Session, categories: Collection[Category]) -> Set[str]:
    """GUIDs of the lemmas belonging to ``categories``.

    Used to scope a pruning import: a row may only be deleted if its lemma lives
    in one of the categories the import actually read.
    """
    if not categories:
        return set()

    guids: Set[str] = set()
    wanted = set(categories)
    for guid, pos_type, pos_subtype in (
        session.query(Lemma.guid, Lemma.pos_type, Lemma.pos_subtype)
        .filter(Lemma.guid.isnot(None))
        .all()
    ):
        category = (
            pos_type.lower() if pos_type else "misc",
            pos_subtype.lower() if pos_subtype else "other",
        )
        if category in wanted:
            guids.add(guid)
    return guids


def _entry_from_review(audio_review: Any) -> Dict[str, Any]:
    """Build the release ``audio[]`` entry for one AudioQualityReview row."""
    entry: Dict[str, Any] = {
        "language_code": audio_review.language_code,
        "voice_name": audio_review.voice_name,
    }
    for field_name in RELEASE_FIELDS:
        entry[field_name] = getattr(audio_review, field_name)
    entry["grammatical_form"] = audio_review.grammatical_form
    return entry


def iter_release_entries(
    release_dir: str, categories: Optional[Collection[Category]] = None
) -> Iterator[Tuple[Category, AudioKey, Dict[str, Any]]]:
    """Yield every well-formed lemma-audio entry in the release files.

    Shared by import and diff so both agree on which rows exist, how they are
    keyed, and which categories a scoped operation touches. Entries missing a
    language or voice cannot be keyed and are skipped.
    """
    wanted = set(categories) if categories is not None else None
    if wanted is not None:
        audio_files = [
            path
            for path in (
                _category_dir(release_dir, category) / "audio.jsonl" for category in sorted(wanted)
            )
            if path.is_file()
        ]
    else:
        audio_files = sorted(Path(release_dir).rglob("audio.jsonl"))

    for audio_file in audio_files:
        category = _category_for_file(release_dir, audio_file)
        with open(audio_file, "r", encoding="utf-8") as handle:
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
                        print(f"Warning: {audio_file} guid {guid} has audio without a voice")
                        continue
                    key = (guid, language_code, voice_name, entry.get("grammatical_form"))
                    yield category, key, entry


def export_to_release(
    session: Session,
    release_dir: str,
    categories: Optional[Collection[Category]] = None,
) -> ExportStats:
    """Export approved lemma audio from an open session to release files.

    Session-based core of :func:`export_sqlite_to_lemma_audio_release`; works with
    any SQLAlchemy backend (SQLite or PostgreSQL) so the Barsukas sync route can
    reuse it against the live request session. Does not close ``session``.

    Args:
        session: Open SQLAlchemy session to read audio rows from.
        release_dir: Release lemmas directory (parent of the per-category files).
        categories: If given, only rewrite these ``(pos_type, pos_subtype)``
            categories; every other ``audio.jsonl`` is left untouched. A selected
            category with no approved audio in the database is truncated to an
            empty file rather than left stale, so export stays the inverse of
            a pruning import. If None, every category with audio is written.
    """
    wanted = set(categories) if categories is not None else None

    rows = (
        session.query(AudioQualityReview, Lemma)
        .join(Lemma, AudioQualityReview.guid == Lemma.guid)
        .filter(AudioQualityReview.guid.isnot(None))
        .filter(AudioQualityReview.sentence_id.is_(None))
        .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        .order_by(
            Lemma.pos_type,
            Lemma.pos_subtype,
            AudioQualityReview.guid,
            AudioQualityReview.language_code,
            AudioQualityReview.voice_name,
        )
        .all()
    )

    records_by_category: Dict[Category, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # The English word each GUID's audio relates to, so audio.jsonl records
    # are self-describing without a cross-reference into base.jsonl.
    english_by_category_guid: Dict[Category, Dict[str, str]] = defaultdict(dict)
    exported_rows = 0
    for audio_review, lemma in rows:
        pos_type = lemma.pos_type.lower() if lemma.pos_type else "misc"
        pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "other"
        category = (pos_type, pos_subtype)
        if wanted is not None and category not in wanted:
            continue
        records_by_category[category][audio_review.guid].append(_entry_from_review(audio_review))
        english_by_category_guid[category][audio_review.guid] = lemma.lemma_text
        exported_rows += 1

    # Selected-but-empty categories still get written, so deselecting audio in the
    # database clears the corresponding file instead of leaving stale rows behind.
    written_categories = set(records_by_category)
    if wanted is not None:
        written_categories |= {
            category
            for category in wanted
            if (_category_dir(release_dir, category) / "audio.jsonl").is_file()
        }

    guid_count = 0
    for category in sorted(written_categories):
        audio_by_guid = records_by_category.get(category, {})
        category_dir = _category_dir(release_dir, category)
        category_dir.mkdir(parents=True, exist_ok=True)
        english_by_guid = english_by_category_guid[category]
        records = []
        for guid, audio in sorted(audio_by_guid.items(), key=lambda item: item[0]):
            record: Dict[str, Any] = {"guid": guid}
            english = english_by_guid.get(guid)
            if english:
                record["english"] = english
            record["audio"] = audio
            records.append(record)
        guid_count += len(records)
        slug = category_slug(category)
        print(f"Exporting {len(records)} lemma audio records to {slug}...")
        write_jsonl_atomic(category_dir / "audio.jsonl", records)

    print(f"Lemma audio export complete! Exported {exported_rows} approved audio rows.")
    return ExportStats(
        audio_rows=exported_rows,
        guids=guid_count,
        categories=len(written_categories),
    )


def import_from_release(
    session: Session,
    release_dir: str,
    prune: bool = False,
    categories: Optional[Collection[Category]] = None,
    keys: Optional[Collection[AudioKey]] = None,
) -> ImportStats:
    """Sync approved lemma audio from release files into an open session.

    Session-based core of :func:`import_lemma_audio_release_to_sqlite`; works with
    any SQLAlchemy backend so the Barsukas sync route can reuse it against the
    live request session. Commits on ``session`` but does not close it.

    Args:
        session: Open SQLAlchemy session to upsert audio rows into.
        release_dir: Release lemmas directory (parent of the per-category files).
        prune: If True, delete exportable lemma-audio rows that are no longer in
            the release files. Pruning respects ``categories``: a scoped import
            only ever deletes rows belonging to the categories it read, so
            syncing one directory cannot remove audio from another.
        categories: If given, only read these ``(pos_type, pos_subtype)``
            categories' files. If None, every ``audio.jsonl`` is read.
        keys: If given, only apply entries whose
            ``(guid, language_code, voice_name, grammatical_form)`` key is in this
            set — the selective-apply path used by the Barsukas diff page. Prune
            is likewise limited to these keys' categories.
    """
    added = 0
    updated = 0
    unchanged = 0
    pruned = 0

    # Map GUIDs to lemma ids so imported audio rows can be linked.
    lemma_id_by_guid: Dict[str, int] = {
        guid: lemma_id
        for guid, lemma_id in session.query(Lemma.guid, Lemma.id)
        .filter(Lemma.guid.isnot(None))
        .all()
    }

    selected_keys = set(keys) if keys is not None else None
    # Categories actually read, so a scoped prune knows what it is allowed to touch.
    visited_categories: Set[Category] = set()
    release_keys: Set[AudioKey] = set()

    for category, key, entry in iter_release_entries(release_dir, categories):
        visited_categories.add(category)
        release_keys.add(key)
        if selected_keys is not None and key not in selected_keys:
            continue

        guid, language_code, voice_name, grammatical_form = key
        existing = (
            session.query(AudioQualityReview)
            .filter(
                AudioQualityReview.guid == guid,
                AudioQualityReview.language_code == language_code,
                AudioQualityReview.voice_name == voice_name,
                (
                    AudioQualityReview.grammatical_form.is_(None)
                    if grammatical_form is None
                    else AudioQualityReview.grammatical_form == grammatical_form
                ),
            )
            .one_or_none()
        )

        if existing is None:
            session.add(
                AudioQualityReview(
                    guid=guid,
                    language_code=language_code,
                    voice_name=voice_name,
                    grammatical_form=grammatical_form,
                    filename=entry.get("filename", ""),
                    expected_text=entry.get("expected_text", ""),
                    manifest_md5=entry.get("manifest_md5", ""),
                    status=entry.get("status", "approved"),
                    s3_prod_url=entry.get("s3_prod_url"),
                    s3_staging_url=entry.get("s3_staging_url"),
                    staging_agent=entry.get("staging_agent"),
                    lemma_id=lemma_id_by_guid.get(guid),
                )
            )
            added += 1
            continue

        # Only count a row as updated when a release-bearing field really moved;
        # re-importing an unchanged file should report zero updates.
        changed = False
        for field_name in RELEASE_FIELDS:
            if field_name not in entry:
                continue
            new_value = entry[field_name]
            if getattr(existing, field_name) != new_value:
                setattr(existing, field_name, new_value)
                changed = True
        if existing.lemma_id is None:
            resolved_lemma_id = lemma_id_by_guid.get(guid)
            if resolved_lemma_id is not None:
                existing.lemma_id = resolved_lemma_id
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    if prune:
        prune_query = (
            session.query(AudioQualityReview)
            .filter(AudioQualityReview.guid.isnot(None))
            .filter(AudioQualityReview.sentence_id.is_(None))
            .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        )
        # A scoped import must not delete rows outside the categories it read.
        prune_scope: Optional[Set[Category]] = None
        if categories is not None or selected_keys is not None:
            prune_scope = set(categories) if categories is not None else visited_categories
        prunable_guids = (
            _guids_in_categories(session, prune_scope) if prune_scope is not None else None
        )
        for review in prune_query.all():
            if prunable_guids is not None and review.guid not in prunable_guids:
                continue
            # prune_query filters guid.isnot(None), so this is a str.
            review_key: AudioKey = (
                str(review.guid),
                review.language_code,
                review.voice_name,
                review.grammatical_form,
            )
            if review_key not in release_keys:
                session.delete(review)
                pruned += 1

    session.commit()
    summary = f"Lemma audio sync complete! Added {added}, updated {updated}, unchanged {unchanged}"
    if prune:
        summary += f", pruned {pruned}"
    print(summary + ".")
    return ImportStats(added=added, updated=updated, pruned=pruned, unchanged=unchanged)


# How one lemma-audio key differs between the release files and the database.
DIFF_STATES = ("only_in_release", "only_in_db", "changed", "identical")


@dataclass
class DiffEntry:
    """One lemma-audio key's state in a release-vs-database comparison.

    ``state`` is one of :data:`DIFF_STATES`. ``changed_fields`` lists
    the release-bearing fields that differ (only meaningful when ``state`` is
    ``"changed"``), each mapped to its ``(release_value, db_value)`` pair so the
    UI can show what an import would overwrite.
    """

    guid: str
    language_code: str
    voice_name: str
    grammatical_form: Optional[str] = None
    state: str = "identical"
    english: Optional[str] = None
    changed_fields: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)

    @property
    def key(self) -> AudioKey:
        """The lemma-audio unique key this entry describes."""
        return (self.guid, self.language_code, self.voice_name, self.grammatical_form)

    @property
    def key_token(self) -> str:
        """Round-trippable form-field token for this key (see :func:`parse_key_token`)."""
        return json.dumps(list(self.key), ensure_ascii=False, separators=(",", ":"))


@dataclass
class CategoryDiff:
    """One category's worth of lemma-audio differences."""

    pos_type: str
    pos_subtype: str
    entries: List[DiffEntry] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """The ``{pos_dir}/{pos_subtype}`` slug identifying this category."""
        return category_slug((self.pos_type, self.pos_subtype))

    @property
    def only_in_release(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "only_in_release")

    @property
    def only_in_db(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "only_in_db")

    @property
    def changed(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "changed")

    @property
    def identical(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "identical")

    @property
    def differing(self) -> int:
        """Entries an import or export would actually act on."""
        return self.only_in_release + self.only_in_db + self.changed

    @property
    def differing_entries(self) -> List["DiffEntry"]:
        """Just the entries that differ, for listing in the UI."""
        return [entry for entry in self.entries if entry.state != "identical"]


@dataclass
class ReleaseDiff:
    """Read-only comparison of lemma-audio release files vs. the database.

    Keys are the lemma-audio unique tuple ``(guid, language_code, voice_name,
    grammatical_form)``. Database rows are counted only when exportable
    (GUID-bearing, non-sentence, in an approved status), matching what an export
    would write. Unlike a plain key-set comparison, a key present on both sides
    whose release-bearing fields differ is reported as ``changed`` rather than
    ``in_both`` — those are exactly the rows an import would silently overwrite.
    """

    categories: List[CategoryDiff] = field(default_factory=list)

    @property
    def release_keys(self) -> int:
        return sum(
            category.only_in_release + category.changed + category.identical
            for category in self.categories
        )

    @property
    def db_keys(self) -> int:
        return sum(
            category.only_in_db + category.changed + category.identical
            for category in self.categories
        )

    @property
    def only_in_release(self) -> int:
        return sum(category.only_in_release for category in self.categories)

    @property
    def only_in_db(self) -> int:
        return sum(category.only_in_db for category in self.categories)

    @property
    def changed(self) -> int:
        return sum(category.changed for category in self.categories)

    @property
    def identical(self) -> int:
        return sum(category.identical for category in self.categories)

    @property
    def differing(self) -> int:
        return sum(category.differing for category in self.categories)

    @property
    def differing_categories(self) -> List[CategoryDiff]:
        """Categories with at least one difference, for listing in the UI."""
        return [category for category in self.categories if category.differing]


def parse_key_token(token: str) -> Optional[AudioKey]:
    """Parse a :attr:`DiffEntry.key_token` back into a lemma-audio key.

    Returns None for malformed tokens so caller-supplied form values cannot
    produce a partially-formed key.
    """
    try:
        parsed = json.loads(token)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 4:
        return None
    guid, language_code, voice_name, grammatical_form = parsed
    if not isinstance(guid, str) or not isinstance(language_code, str):
        return None
    if not isinstance(voice_name, str):
        return None
    if grammatical_form is not None and not isinstance(grammatical_form, str):
        return None
    return (guid, language_code, voice_name, grammatical_form)


def summarize_release_diff(
    session: Session,
    release_dir: str,
    categories: Optional[Collection[Category]] = None,
) -> ReleaseDiff:
    """Compare exportable lemma audio in ``session`` against the release files.

    Read-only: mutates nothing, used to preview a sync in the Barsukas UI.

    Args:
        session: Open SQLAlchemy session to read audio rows from.
        release_dir: Release lemmas directory (parent of the per-category files).
        categories: If given, restrict the comparison to these categories.
    """
    wanted = set(categories) if categories is not None else None

    release_entries: Dict[AudioKey, Dict[str, Any]] = {}
    release_category_by_key: Dict[AudioKey, Category] = {}
    for category, key, entry in iter_release_entries(release_dir, categories):
        release_entries[key] = entry
        release_category_by_key[key] = category

    db_entries: Dict[AudioKey, Dict[str, Any]] = {}
    db_category_by_key: Dict[AudioKey, Category] = {}
    english_by_guid: Dict[str, str] = {}
    exportable = (
        session.query(AudioQualityReview, Lemma)
        .join(Lemma, AudioQualityReview.guid == Lemma.guid)
        .filter(AudioQualityReview.guid.isnot(None))
        .filter(AudioQualityReview.sentence_id.is_(None))
        .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        .all()
    )
    for audio_review, lemma in exportable:
        category = (
            lemma.pos_type.lower() if lemma.pos_type else "misc",
            lemma.pos_subtype.lower() if lemma.pos_subtype else "other",
        )
        if wanted is not None and category not in wanted:
            continue
        db_key: AudioKey = (
            str(audio_review.guid),
            audio_review.language_code,
            audio_review.voice_name,
            audio_review.grammatical_form,
        )
        db_entries[db_key] = _entry_from_review(audio_review)
        db_category_by_key[db_key] = category
        english_by_guid[audio_review.guid] = lemma.lemma_text

    entries_by_category: Dict[Category, List[DiffEntry]] = defaultdict(list)
    for key in set(release_entries) | set(db_entries):
        guid, language_code, voice_name, grammatical_form = key
        release_entry = release_entries.get(key)
        db_entry = db_entries.get(key)

        if release_entry is None:
            state = "only_in_db"
            changed_fields: Dict[str, Tuple[Any, Any]] = {}
        elif db_entry is None:
            state = "only_in_release"
            changed_fields = {}
        else:
            changed_fields = {
                release_field: (release_entry.get(release_field), db_entry.get(release_field))
                for release_field in RELEASE_FIELDS
                if release_field in release_entry
                and release_entry.get(release_field) != db_entry.get(release_field)
            }
            state = "changed" if changed_fields else "identical"

        # Prefer the database's category: it is what an export would write, and
        # for release-only rows the file's own location is the only signal.
        category = db_category_by_key.get(key) or release_category_by_key[key]
        entries_by_category[category].append(
            DiffEntry(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=grammatical_form,
                state=state,
                english=english_by_guid.get(guid),
                changed_fields=changed_fields,
            )
        )

    category_diffs = []
    for category in sorted(entries_by_category):
        entries = sorted(
            entries_by_category[category],
            key=lambda entry: (entry.guid, entry.language_code, entry.voice_name),
        )
        category_diffs.append(
            CategoryDiff(pos_type=category[0], pos_subtype=category[1], entries=entries)
        )

    return ReleaseDiff(categories=category_diffs)
