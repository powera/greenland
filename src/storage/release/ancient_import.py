"""Import grouped ancient-language translations from the release tree.

The ancient-language evidence (``la``, ``sa``, ``grc``, ``ar-classical``,
``non``) lives in ``data/release/lemmas/*/*/ancient.jsonl`` rather than in
``base.jsonl``, because those languages are kept out of the main record. Each
line carries ``{"guid", "translations", "translation_metadata"}``, where the
metadata holds the ``translation_status`` judgement that says whether a
rendering is ordinary historical vocabulary or a later coinage.

This module loads those files into the database. It exists because the release
files are the only place that evidence currently lives: nothing had ever read
them back into a SQL backend, so ``translation_status`` was NULL for every row.

Matching semantics follow ``jsonl.storage._merge_grouped_translation_file``:
records are matched by GUID, a GUID with no lemma is reported rather than
created, and an existing translation is left alone unless ``overwrite`` is set.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from storage import translation_helpers
from storage.models.schema import Lemma, LemmaTranslation

logger = logging.getLogger(__name__)

#: Stem of the grouped file holding ancient-language translations.
ANCIENT_FILE_STEM = "ancient"


@dataclass
class AncientImportResult:
    """Counts and diagnostics from one import run."""

    files_read: int = 0
    records_read: int = 0
    lemmas_matched: int = 0
    translations_written: int = 0
    translations_skipped_existing: int = 0
    statuses_written: int = 0
    missing_guids: List[str] = field(default_factory=list)
    unexpected_languages: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable summary."""
        return {
            "files_read": self.files_read,
            "records_read": self.records_read,
            "lemmas_matched": self.lemmas_matched,
            "translations_written": self.translations_written,
            "translations_skipped_existing": self.translations_skipped_existing,
            "statuses_written": self.statuses_written,
            "missing_guids": sorted(self.missing_guids),
            "unexpected_languages": sorted(set(self.unexpected_languages)),
        }


def find_ancient_files(release_root: Path) -> List[Path]:
    """Return every ``ancient.jsonl`` under a release lemma tree, sorted."""
    lemmas_root = release_root / "lemmas" if (release_root / "lemmas").is_dir() else release_root
    return sorted(lemmas_root.rglob(f"{ANCIENT_FILE_STEM}.jsonl"))


def iter_ancient_records(path: Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """Yield ``(line_number, record)`` for each non-blank line of a grouped file.

    A malformed line is logged and skipped rather than aborting the file, which
    matches how the JSONL backend reads the same files.
    """
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as parse_error:
                logger.error("Error loading %s:%s: %s", path, line_number, parse_error)
                continue
            yield line_number, record


def _apply_record(
    session: Session,
    lemma: Lemma,
    record: Dict[str, Any],
    *,
    languages: Sequence[str],
    overwrite: bool,
    result: AncientImportResult,
) -> None:
    """Write one record's ancient translations onto an already-matched lemma."""
    translations = record.get("translations") or {}
    metadata_by_language = record.get("translation_metadata") or {}
    existing_by_language: Dict[str, LemmaTranslation] = {
        existing.language_code: existing for existing in lemma.translations
    }

    for language_code, text in translations.items():
        if not text:
            continue
        if language_code not in languages:
            result.unexpected_languages.append(language_code)
            continue

        translation = existing_by_language.get(language_code)
        if translation is not None and not overwrite:
            result.translations_skipped_existing += 1
            continue

        if translation is None:
            translation = LemmaTranslation(lemma_id=lemma.id, language_code=language_code)
            session.add(translation)

        metadata = metadata_by_language.get(language_code) or {}
        status = metadata.get("translation_status")

        translation.translation = text
        translation.translation_status = status
        translation.translation_status_note = metadata.get("translation_status_note")
        translation.sort_key = translation_helpers.compute_sort_key(language_code, text)

        result.translations_written += 1
        if status:
            result.statuses_written += 1


def import_ancient_translations(
    session: Session,
    release_root: Path,
    *,
    languages: Optional[Sequence[str]] = None,
    overwrite: bool = False,
) -> AncientImportResult:
    """Load every ``ancient.jsonl`` under ``release_root`` into the database.

    Args:
        session: Open session; the caller owns the commit.
        release_root: A release tree, or its ``lemmas/`` subdirectory.
        languages: Language codes to accept, defaulting to the ancient group.
            Anything outside this set is recorded and skipped, so a stray code
            in a release file cannot silently create a translation row.
        overwrite: Replace translations that already exist. Off by default,
            matching the rule that the primary record wins.

    Returns:
        An :class:`AncientImportResult` with counts and diagnostics.
    """
    accepted = (
        list(languages)
        if languages is not None
        else list(translation_helpers.ANCIENT_LANGUAGE_GROUP)
    )
    result = AncientImportResult()

    for path in find_ancient_files(release_root):
        result.files_read += 1
        for _line_number, record in iter_ancient_records(path):
            result.records_read += 1
            guid = record.get("guid")
            if not guid:
                continue

            lemma = session.query(Lemma).filter(Lemma.guid == guid).one_or_none()
            if lemma is None:
                result.missing_guids.append(guid)
                logger.warning("%s contains guid %s not found in the database", path, guid)
                continue

            result.lemmas_matched += 1
            _apply_record(
                session,
                lemma,
                record,
                languages=accepted,
                overwrite=overwrite,
                result=result,
            )

    return result
