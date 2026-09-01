#!/usr/bin/env python3
"""Staged-manifest parsing and database matching.

A staging manifest is the JSON an audio-generating agent writes to S3 beside
each MP3 (see clients.audio.manifest.generate_manifest). Importing that audio
back into a database means parsing the manifest and deciding which row it
describes, which is what this module does.

Kept out of src/agents so both the gandras importer and anything else that
consumes staged audio can share it, and so the matching rules are testable
without constructing an agent.

Distinct from audiotools.manifest_rebuild, which reconstructs a manifest for a
directory of MP3s from the filenames on disk.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.schema import Lemma, Sentence, SentenceTranslation
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)


@dataclass
class ManifestEntry:
    """Parsed manifest entry from S3."""

    md5: str
    agent: str
    voice_name: str
    language_code: str
    expected_text: str
    guid: Optional[str]
    sentence_id: Optional[int]
    grammatical_form: Optional[str]
    generated_at: str
    file_size_bytes: int
    generation_params: Optional[Dict[str, Any]]
    s3_audio_key: str
    s3_manifest_key: str
    # Set when this audio was rejected and the verdict written back to S3 (see
    # s3_ops.mark_manifest_rejected). Travels with the manifest, so every
    # database importing it sees the rejection, not just the one that made it.
    rejected: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], audio_key: str, manifest_key: str) -> "ManifestEntry":
        """Create ManifestEntry from manifest dict."""
        return cls(
            md5=data.get("md5", ""),
            agent=data.get("agent", ""),
            voice_name=data.get("voice_name", ""),
            language_code=data.get("language_code", ""),
            expected_text=data.get("expected_text", ""),
            guid=data.get("guid"),
            sentence_id=data.get("sentence_id"),
            grammatical_form=data.get("grammatical_form"),
            generated_at=data.get("generated_at", ""),
            file_size_bytes=data.get("file_size_bytes", 0),
            generation_params=data.get("generation_params"),
            s3_audio_key=audio_key,
            s3_manifest_key=manifest_key,
            rejected=data.get("rejected"),
        )

    @property
    def label(self) -> str:
        """Short identifier for log messages."""
        return self.guid or f"sentence_{self.sentence_id}"

    @property
    def is_rejected(self) -> bool:
        """Whether this manifest carries a rejection written back to S3."""
        return bool(self.rejected)

    @property
    def rejection_reason(self) -> str:
        """The recorded rejection reason, or a placeholder when absent."""
        if not self.rejected:
            return ""
        reason = self.rejected.get("reason") or "no reason recorded"
        return str(reason)


@dataclass
class MatchResult:
    """Result of matching a manifest to database records."""

    matched: bool
    match_type: str  # "guid", "sentence_id", "text_only", "no_match"
    lemma: Optional[Lemma]
    sentence: Optional[Sentence]
    text_matches: bool
    guid_matches: bool
    sentence_id_matches: bool
    pos_type: Optional[str]
    warnings: List[str]


def _texts_match(manifest_text: str, db_text: str) -> bool:
    """Compare manifest text to database text, ignoring case and edge whitespace."""
    return manifest_text.strip().lower() == db_text.strip().lower()


def match_manifest_to_database(
    session: Session,
    manifest: ManifestEntry,
    require_text_match: bool = True,
) -> MatchResult:
    """
    Match a manifest entry against the database.

    Matching priority:
    1. If guid is present, try to match lemma by GUID
    2. If sentence_id is present, try to match sentence by ID
    3. Fall back to text matching within the language

    Args:
        session: Database session
        manifest: Parsed manifest entry
        require_text_match: If True, a GUID/sentence_id hit whose text disagrees
            with the database is not treated as a match

    Returns:
        MatchResult with match details
    """
    warnings: List[str] = []
    lemma: Optional[Lemma] = None
    sentence: Optional[Sentence] = None
    text_matches = False
    guid_matches = False
    sentence_id_matches = False
    pos_type: Optional[str] = None

    # Try GUID match for lemmas
    if manifest.guid and not manifest.guid.startswith("S_"):
        lemma = session.query(Lemma).filter_by(guid=manifest.guid).first()

        if lemma:
            guid_matches = True
            pos_type = lemma.pos_type

            # Check if text matches translation
            db_translation = get_translation(session, lemma, manifest.language_code)
            if db_translation:
                text_matches = _texts_match(manifest.expected_text, db_translation)

                if not text_matches:
                    warnings.append(
                        f"Text mismatch: manifest='{manifest.expected_text}' "
                        f"vs db='{db_translation}'"
                    )
            else:
                warnings.append(
                    f"No {manifest.language_code} translation found for lemma {manifest.guid}"
                )

    # Try sentence_id match
    if manifest.sentence_id:
        sentence = session.query(Sentence).filter_by(id=manifest.sentence_id).first()

        if sentence:
            sentence_id_matches = True

            # Check if text matches translation
            translation = (
                session.query(SentenceTranslation)
                .filter_by(sentence_id=manifest.sentence_id, language_code=manifest.language_code)
                .first()
            )

            if translation:
                text_matches = _texts_match(manifest.expected_text, translation.translation_text)

                if not text_matches:
                    warnings.append(
                        f"Text mismatch: manifest='{manifest.expected_text}' "
                        f"vs db='{translation.translation_text}'"
                    )
            else:
                warnings.append(
                    f"No {manifest.language_code} translation found for sentence "
                    f"{manifest.sentence_id}"
                )

    # Determine match type and whether it's a valid match
    if guid_matches and text_matches:
        match_type = "guid"
        matched = True
    elif sentence_id_matches and text_matches:
        match_type = "sentence_id"
        matched = True
    elif guid_matches and not text_matches:
        match_type = "guid_text_mismatch"
        matched = not require_text_match  # Match if text match not required
    elif sentence_id_matches and not text_matches:
        match_type = "sentence_id_text_mismatch"
        matched = not require_text_match
    elif not manifest.guid and not manifest.sentence_id:
        match_type = "no_identifier"
        matched = False
        warnings.append("Manifest has no guid or sentence_id")
    else:
        match_type = "no_match"
        matched = False
        if manifest.guid:
            warnings.append(f"GUID {manifest.guid} not found in database")
        if manifest.sentence_id:
            warnings.append(f"Sentence ID {manifest.sentence_id} not found in database")

    return MatchResult(
        matched=matched,
        match_type=match_type,
        lemma=lemma,
        sentence=sentence,
        text_matches=text_matches,
        guid_matches=guid_matches,
        sentence_id_matches=sentence_id_matches,
        pos_type=pos_type,
        warnings=warnings,
    )
