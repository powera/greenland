"""Discovery of lemmas still missing synonyms and alternative forms.

A lemma/language pair counts as *processed* once a synonym scan has been
recorded for it, not once a synonym exists: plenty of words legitimately have
no synonyms, and re-asking the LLM about them every run would be pure spend.
Anything without such a record, in a language the lemma actually has a
translation for, is missing work.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from storage.crud.operation_log import has_synonym_scan_record
from storage.models.schema import Lemma
from storage.translation_helpers import get_supported_languages, get_translation
from words.lemma_selection import LemmaQueryBuilder

logger = logging.getLogger(__name__)

__all__ = [
    "ALL_FORM_TYPES",
    "MissingSynonymLemma",
    "MissingSynonymReport",
    "find_missing_synonyms",
]

# Form types Šernas generates; all of them are covered by a single scan.
ALL_FORM_TYPES: List[str] = ["synonym", "abbreviation", "expanded_form"]


@dataclass(frozen=True)
class MissingSynonymLemma:
    """One lemma/language pair that has never been scanned for synonyms."""

    guid: str
    english: str
    translation: str
    pos_type: Optional[str]
    pos_subtype: Optional[str]
    difficulty_level: Optional[int]


@dataclass
class MissingSynonymReport:
    """What a coverage scan found, per language."""

    missing_by_language: Dict[str, List[MissingSynonymLemma]] = field(default_factory=dict)
    checked_languages: List[str] = field(default_factory=list)
    checked_form_types: List[str] = field(default_factory=list)
    # Set when the scan itself failed; the per-language lists are empty then.
    error: Optional[str] = None

    @property
    def total_missing(self) -> int:
        """Number of lemma/language pairs needing generation."""
        return sum(len(items) for items in self.missing_by_language.values())

    def for_language(self, language_code: str) -> List[MissingSynonymLemma]:
        """Return the missing lemmas for one language (empty if none)."""
        return self.missing_by_language.get(language_code, [])


def find_missing_synonyms(
    session: Any,
    *,
    lemmas: Optional[Sequence[Lemma]] = None,
    language_code: Optional[str] = None,
    form_type: Optional[str] = None,
) -> MissingSynonymReport:
    """Find lemmas that have never been scanned for synonyms/alternative forms.

    Args:
        session: Database session.
        lemmas: Lemmas to check. If None, checks all curated lemmas.
        language_code: Language to check (e.g. 'en', 'lt'). If None, checks
            English plus every supported language.
        form_type: Single form type to report as checked. If None, all of
            :data:`ALL_FORM_TYPES` are reported.

    Returns:
        A :class:`MissingSynonymReport`. On failure its ``error`` is set and the
        per-language lists are empty.
    """
    logger.info("Checking for lemmas missing synonyms/alternative forms...")

    try:
        if lemmas is None:
            lemmas = LemmaQueryBuilder(session).curated_only().order_by_id().build().all()
        logger.info(f"Checking {len(lemmas)} lemmas")

        if language_code:
            lang_codes = [language_code]
        else:
            # English first, then the rest; dict.fromkeys keeps that order and
            # drops the duplicate "en" that get_supported_languages() also has,
            # which would otherwise report every English lemma twice.
            lang_codes = list(dict.fromkeys(["en"] + list(get_supported_languages())))
        form_types = [form_type] if form_type else list(ALL_FORM_TYPES)

        missing_by_language: Dict[str, List[MissingSynonymLemma]] = {
            lang: [] for lang in lang_codes
        }

        for lemma in lemmas:
            # Uncurated lemmas have no GUID, so no agent can be pointed at them.
            if not lemma.guid:
                continue
            for lang in lang_codes:
                if lang == "en":
                    translation: Optional[str] = lemma.lemma_text
                else:
                    translation = get_translation(session, lemma, lang)

                if not translation or not translation.strip():
                    continue

                # A lemma/language pair is "processed" once ŠERNAS ran once.
                if has_synonym_scan_record(session, lemma.id, lang):
                    continue

                missing_by_language[lang].append(
                    MissingSynonymLemma(
                        guid=lemma.guid,
                        english=lemma.lemma_text,
                        translation=translation,
                        pos_type=lemma.pos_type,
                        pos_subtype=lemma.pos_subtype,
                        difficulty_level=lemma.difficulty_level,
                    )
                )

        report = MissingSynonymReport(
            missing_by_language=missing_by_language,
            checked_languages=lang_codes,
            checked_form_types=form_types,
        )
        logger.info(
            f"Found {report.total_missing} lemmas missing synonyms/alternatives "
            "across all languages"
        )
        return report

    except Exception as e:
        logger.error(f"Error checking missing synonyms: {e}")
        return MissingSynonymReport(error=str(e))
