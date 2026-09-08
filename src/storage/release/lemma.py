"""Read and write ``data/release/lemmas`` base.jsonl records.

Lemmas are the largest release type and the only one whose data is spread over
four file kinds: ``base.jsonl`` for the concept itself, ``{lang}.jsonl`` for
derivative forms, synonyms and grammar facts, and ``secondary.jsonl`` /
``ancient.jsonl`` for the translation tiers that would otherwise make the base
record unwieldy. **This module owns only the base record.** Locating and
rewriting the files stays with the caller (``storage.release.io``
for the UI, ``storage.migrate`` for the CLI), because that part genuinely
differs between the two.

What it does own is the mapping in both directions, in one place. Before this
module there were two base-record builders -- one in the sync blueprint, one
inline in ``storage.migrate.export_sqlite_to_release`` -- and they disagreed:
the CLI wrote ``concept_label`` without the disambiguation and omitted ``qid``
and ``translation_disambiguations``, so a CLI export after any UI work stripped
those from the tree, and re-importing it then nulled the disambiguation on
every lemma, because the sense had nowhere else to live.

It has somewhere now. ``disambiguation`` is a ``{language: sense}`` map in the
base record, covering English alongside every other language; it replaces the
old English-only parenthetical and the separate ``translation_disambiguations``
key. Splitting it on import is the same split ``translations`` already makes -
``en`` is the lemma's own column, the rest are per-translation rows.

``concept_label`` is a display string and nothing parses it back apart. A
record's identity is its GUID, so two labels may coincide without ambiguity.

Concepts are deliberately not handled here. A lemma's Wikidata pairing lives in
``concept_lemma_links`` and is written by ``storage.crud.concept``; the only
piece that reaches a release file is the Q-id, which callers pass in and read
back out. See ``docs/element_types_design.md``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import selectinload

from storage.config.grammar_facts import RELEASE_GRAMMAR_FACT_TYPES
from storage.release.derivative_form import forms_by_language
from storage.release.io import write_jsonl_atomic
from storage.release.mechanical_filter import clear_cache, without_derivable
from storage.release.variant import release_variants_by_language

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from storage import translation_helpers
from storage.models.schema import Lemma, LemmaTranslation

#: Per-language translation extras, as (release key, model field). Each is
#: omitted from ``translation_metadata`` when unset so a hand-edited file stays
#: readable.
_TRANSLATION_METADATA_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("translation_status", "translation_status"),
    ("translation_status_note", "translation_status_note"),
)

#: Difficulty written when a lemma has none. ``-1`` is the release convention
#: for "not levelled yet" (see data/release/README.md).
UNLEVELLED_DIFFICULTY = -1


# ---------------------------------------------------------------------------
# Release-side readers
#
# The release record is the source of truth for these, so parsing it lives next
# to the code that writes it.
# ---------------------------------------------------------------------------


def build_concept_label(lemma_text: str, disambiguation: Optional[str]) -> str:
    """Join a headword and its optional sense into one display label.

    The result is for people to read. Nothing in the system parses it back
    apart: a sense is read from the ``disambiguation`` map, and identity is the
    GUID. Two records may legitimately share a label.
    """
    return f"{lemma_text} ({disambiguation})" if disambiguation else lemma_text


def release_lemma_text(record: Dict[str, Any]) -> str:
    """The English headword of a release record."""
    english = (record.get("translations") or {}).get("en")
    return str(english) if english else ""


def release_disambiguations(record: Dict[str, Any]) -> Dict[str, str]:
    """The ``{language: sense}`` map of a release record."""
    raw = record.get("disambiguation")
    if not isinstance(raw, dict):
        return {}
    return {
        str(language): str(sense).strip()
        for language, sense in raw.items()
        if sense and str(sense).strip()
    }


def release_disambiguation(record: Dict[str, Any], language_code: str = "en") -> Optional[str]:
    """One language's sense from a release record, or None."""
    return release_disambiguations(record).get(language_code)


def normalize_emoji_entry(item: Any) -> Optional[Dict[str, str]]:
    """Coerce one emoji-list item into a ``{type, value}`` dict, or None.

    Accepts either the canonical dict form or a bare Unicode string (legacy).
    """
    if isinstance(item, dict):
        entry_type = str(item.get("type", "")).strip()
        value = str(item.get("value", "")).strip()
        if entry_type in ("unicode", "image") and value:
            return {"type": entry_type, "value": value}
        return None
    if isinstance(item, str) and item.strip():
        return {"type": "unicode", "value": item.strip()}
    return None


def normalize_emoji_list(raw: Any) -> List[Dict[str, str]]:
    """Normalize any emoji-list shape into a list of ``{type, value}`` dicts."""
    if not isinstance(raw, list):
        return []
    entries: List[Dict[str, str]] = []
    for item in raw:
        entry = normalize_emoji_entry(item)
        if entry is not None:
            entries.append(entry)
    return entries


def decode_db_emoji(raw: Optional[str]) -> List[Dict[str, str]]:
    """Decode the JSON-encoded emoji list stored on ``Lemma.emoji``.

    Returns ``[]`` for null/empty/unparseable values so an equality check
    against a record with no ``emoji`` key treats both as "no emoji".
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return normalize_emoji_list(value)


def encode_db_emoji(entries: List[Dict[str, str]]) -> Optional[str]:
    """Encode an emoji list for storage on ``Lemma.emoji`` (None when empty)."""
    return json.dumps(entries) if entries else None


def release_emoji(record: Dict[str, Any]) -> List[Dict[str, str]]:
    """The emoji list of a release record (missing -> ``[]``)."""
    return normalize_emoji_list(record.get("emoji"))


# ---------------------------------------------------------------------------
# Database -> release
# ---------------------------------------------------------------------------


def translation_metadata_record(translation: LemmaTranslation) -> Dict[str, str]:
    """Build the ``translation_metadata`` entry for one translation (may be empty).

    An uninformative ``translation_status`` - a bare ``conventional`` on a
    living language, which is what every ordinary word is - is dropped along
    with its note, so it never reaches the file. See
    ``translation_helpers.translation_status_is_informative``.
    """
    metadata: Dict[str, str] = {}
    if not translation_helpers.translation_status_is_informative(
        translation.language_code,
        translation.translation_status,
        translation.translation_status_note,
    ):
        return metadata
    for release_key, model_field in _TRANSLATION_METADATA_FIELDS:
        value = getattr(translation, model_field, None)
        if value:
            metadata[release_key] = value
    return metadata


def lemma_to_release_record(lemma: Lemma, *, qid: Optional[str] = None) -> Dict[str, Any]:
    """Build the ``base.jsonl`` record for one lemma.

    Args:
        lemma: The lemma, with ``translations`` and ``difficulty_overrides``
            loaded (both are read).
        qid: The Wikidata Q-id this lemma is paired with, or None when it is
            unpaired. Passed in rather than looked up: the pairing lives in
            ``concept_lemma_links`` and resolving it is the caller's job, which
            keeps this function free of concept queries.

    Translations are emitted in ``RELEASE_LANGUAGES`` order with ``en`` first,
    so re-exporting an unchanged database is byte-stable.
    """
    by_language: Dict[str, LemmaTranslation] = {
        translation.language_code: translation for translation in lemma.translations
    }

    translations: Dict[str, str] = {"en": lemma.lemma_text}
    disambiguations: Dict[str, str] = {}
    translation_metadata: Dict[str, Dict[str, str]] = {}

    for language_code in translation_helpers.RELEASE_LANGUAGES:
        if language_code == "en":
            continue
        translation = by_language.get(language_code)
        if translation is None or not translation.translation:
            continue
        translations[language_code] = translation.translation
        if translation.disambiguation:
            disambiguations[language_code] = translation.disambiguation
        metadata = translation_metadata_record(translation)
        if metadata:
            translation_metadata[language_code] = metadata

    release_languages = set(translation_helpers.RELEASE_LANGUAGES)
    difficulty_overrides: Dict[str, int] = {
        override.language_code: override.difficulty_level
        for override in lemma.difficulty_overrides
        if override.language_code in release_languages
    }

    record: Dict[str, Any] = {
        "guid": lemma.guid,
        "pos_type": lemma.pos_type,
        "pos_subtype": lemma.pos_subtype or "",
        "concept_label": build_concept_label(lemma.lemma_text, lemma.disambiguation),
        "concept_definition": lemma.definition_text or "",
        "translations": translations,
        "difficulty_level": (
            lemma.difficulty_level if lemma.difficulty_level is not None else UNLEVELLED_DIFFICULTY
        ),
    }

    # One {language: sense} map. English is the lemma's own column and the
    # others are per-translation, but the release presents them uniformly.
    if lemma.disambiguation:
        disambiguations["en"] = lemma.disambiguation
    if disambiguations:
        record["disambiguation"] = disambiguations
    if translation_metadata:
        record["translation_metadata"] = translation_metadata
    if difficulty_overrides:
        record["difficulty_overrides"] = difficulty_overrides
    if lemma.lexical_gap_reason:
        record["lexical_gap_reason"] = lemma.lexical_gap_reason
    if lemma.notes:
        record["notes"] = lemma.notes
    # Omitted when unrated: an absent key means nobody has judged this sense,
    # which readers treat as "common". Writing "common" for a NULL would make
    # a round-trip claim a rating that was never made.
    if lemma.sense_prominence:
        record["sense_prominence"] = lemma.sense_prominence

    emoji = decode_db_emoji(lemma.emoji)
    if emoji:
        record["emoji"] = emoji

    if qid:
        record["qid"] = qid

    return record


# ---------------------------------------------------------------------------
# Release -> database
# ---------------------------------------------------------------------------


def apply_base_fields(lemma: Lemma, record: Dict[str, Any]) -> None:
    """Overwrite a lemma's base-concept fields from a release record.

    Covers exactly the fields :func:`lemma_to_release_record` writes onto the
    ``Lemma`` row itself. Translations, grammar facts and the concept pairing
    are separate and stay with the caller.
    """
    lemma.lemma_text = release_lemma_text(record)
    lemma.disambiguation = release_disambiguation(record)
    lemma.definition_text = record.get("concept_definition", "") or ""
    lemma.notes = record.get("notes") or None
    lemma.lexical_gap_reason = record.get("lexical_gap_reason") or None
    lemma.sense_prominence = record.get("sense_prominence") or None
    lemma.emoji = encode_db_emoji(release_emoji(record))


def apply_translations(session: Session, lemma: Lemma, record: Dict[str, Any]) -> int:
    """Create or update this lemma's translations from a release record.

    English is the lemma text, not a translation row, so it is skipped. Returns
    the number of languages written.
    """
    translations = record.get("translations") or {}
    # The "en" entry belongs to the lemma row, not here; apply_base_fields
    # takes it. Everything else annotates a translation.
    disambiguations = release_disambiguations(record)
    metadata_by_language = record.get("translation_metadata") or {}

    existing_by_language: Dict[str, LemmaTranslation] = {
        translation.language_code: translation for translation in lemma.translations
    }

    written = 0
    for language_code, text in translations.items():
        if language_code == "en" or not text:
            continue
        metadata = metadata_by_language.get(language_code, {})
        translation = existing_by_language.get(language_code)
        if translation is None:
            translation = LemmaTranslation(lemma_id=lemma.id, language_code=language_code)
            session.add(translation)
        translation.translation = text
        translation.disambiguation = disambiguations.get(language_code)
        translation.translation_status = metadata.get("translation_status")
        translation.translation_status_note = metadata.get("translation_status_note")
        translation.sort_key = translation_helpers.compute_sort_key(language_code, text)
        written += 1
    return written


def import_release_record(session: Session, record: Dict[str, Any]) -> Lemma:
    """Create a new lemma (and its translations) from a release record.

    The caller is responsible for the GUID not already existing, for grammar
    facts, and for the concept pairing.
    """
    lemma = Lemma(
        guid=record.get("guid"),
        lemma_text=release_lemma_text(record),
        disambiguation=release_disambiguation(record),
        definition_text=record.get("concept_definition", "") or "",
        pos_type=record.get("pos_type", "") or "",
        pos_subtype=record.get("pos_subtype") or None,
        difficulty_level=record.get("difficulty_level"),
        notes=record.get("notes") or None,
        lexical_gap_reason=record.get("lexical_gap_reason") or None,
        sense_prominence=record.get("sense_prominence") or None,
        emoji=encode_db_emoji(release_emoji(record)),
    )
    session.add(lemma)
    session.flush()  # assign lemma.id before the translations reference it

    apply_translations(session, lemma, record)
    return lemma


@dataclass(frozen=True)
class LemmaExportStats:
    """What one lemma export wrote."""

    lemmas: int = 0
    languages: List[str] = field(default_factory=list)


def export_to_release(session: Session, release_dir: Path) -> LemmaExportStats:
    """Export SQLite to data/release format.

    This creates per-category directories (e.g., nouns/animal/) containing:
    - base.jsonl: concept definitions with translations and difficulty_overrides
      (guid, pos_type, pos_subtype, concept_label, concept_definition,
       difficulty_level, translations: {lang_code: translation},
       difficulty_overrides: {lang_code: level})
    - {lang}.jsonl: per-language data keyed by guid, written only for languages
      that have derivative_forms (conjugations, inflections, etc.), synonyms
      (synonyms, abbreviations, expanded forms, and related lexical variants),
      or grammar_facts (gender, declension, number_type, etc.)

    Tombstones are *not* written here: they ship beside the lemma tree rather
    than inside it, and are their own registry entry. A full export runs both.
    """

    from storage import translation_helpers
    from storage.models.concept import ConceptLemmaLink
    from storage.models.schema import Lemma
    from storage.release.lemma import lemma_to_release_record

    from storage.utils.session import ensure_tables_exist

    ensure_tables_exist(session)

    # Paradigms are memoized per lemma; a second export in the same process
    # must re-read facts that may have changed since the first.
    clear_cache()

    # Get all lemmas with GUIDs (curated words only)
    # Eager-load derivative_forms and grammar_facts to avoid N+1 queries
    lemmas = (
        session.query(Lemma)
        .filter(Lemma.guid.isnot(None))
        .options(
            selectinload(Lemma.translations),
            selectinload(Lemma.derivative_forms),
            selectinload(Lemma.variant_forms),
            selectinload(Lemma.grammar_facts),
            # Read by the base record builder.
            selectinload(Lemma.difficulty_overrides),
        )
        .order_by(Lemma.id)
        .all()
    )
    print(f"Found {len(lemmas)} curated lemmas to export")

    # Every lemma's Q-id in one query. Resolving these per lemma inside the
    # export loop would be one query per word on a whole-tree export.
    qid_by_lemma_id: Dict[int, str] = dict(
        session.query(ConceptLemmaLink.lemma_id, ConceptLemmaLink.qid).tuples().all()
    )

    # Group lemmas by POS type/subtype
    lemmas_by_category: Dict[tuple, list] = defaultdict(list)
    for lemma in lemmas:
        pos_type = lemma.pos_type.lower() if lemma.pos_type else "misc"
        pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "other"
        category = (pos_type, pos_subtype)
        lemmas_by_category[category].append(lemma)

    print(f"Organized into {len(lemmas_by_category)} categories")

    # Map POS types to directory names (pluralized)
    type_to_dir = {
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

    # Track languages encountered
    all_languages: Set[str] = set()

    # Process each category
    for (pos_type, pos_subtype), category_lemmas in lemmas_by_category.items():
        # Determine directory structure
        dir_name = type_to_dir.get(pos_type, "misc")
        category_dir = release_dir / dir_name / pos_subtype
        category_dir.mkdir(parents=True, exist_ok=True)

        print(f"Exporting {len(category_lemmas)} lemmas to {dir_name}/{pos_subtype}...")

        # Collect base records (now includes translations)
        base_records = []

        release_lang_set = set(translation_helpers.RELEASE_LANGUAGES)
        secondary_lang_set = set(translation_helpers.SECONDARY_RELEASE_LANGUAGES)
        extra_group_lang_sets = {
            group_name: set(group_languages)
            for group_name, group_languages in translation_helpers.EXTRA_RELEASE_LANGUAGE_GROUPS.items()
        }

        # Collect secondary translation records alongside base records
        secondary_records: List[Dict[str, Any]] = []
        extra_group_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for lemma in category_lemmas:
            # Get all translations
            all_translations = translation_helpers.get_all_translations(session, lemma)

            # Route each language to the file that carries it. RELEASE_LANGUAGES
            # ride in the base record, which lemma_to_release_record builds
            # below, so this loop only needs to note that the language is in
            # play; the secondary and grouped tiers are collected here.
            secondary_translations_dict: Dict[str, str] = {}
            secondary_translation_metadata_dict: Dict[str, Dict[str, str]] = {}
            extra_group_translations: Dict[str, Dict[str, str]] = defaultdict(dict)
            extra_group_metadata: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)
            metadata_by_lang: Dict[str, Dict[str, str]] = {}
            for trans_obj in lemma.translations:
                metadata: Dict[str, str] = {}
                # A bare "conventional" on a living language is the assumed
                # default and is not written out.
                if translation_helpers.translation_status_is_informative(
                    trans_obj.language_code,
                    trans_obj.translation_status,
                    trans_obj.translation_status_note,
                ):
                    metadata["translation_status"] = trans_obj.translation_status
                    if trans_obj.translation_status_note:
                        metadata["translation_status_note"] = trans_obj.translation_status_note
                if metadata:
                    metadata_by_lang[trans_obj.language_code] = metadata

            for lang_code, translation in all_translations.items():
                if translation and translation.strip():
                    if lang_code in release_lang_set:
                        all_languages.add(lang_code)
                    elif lang_code in secondary_lang_set:
                        all_languages.add(lang_code)
                        secondary_translations_dict[lang_code] = translation
                        if lang_code in metadata_by_lang:
                            secondary_translation_metadata_dict[lang_code] = metadata_by_lang[
                                lang_code
                            ]
                    else:
                        for group_name, group_lang_set in extra_group_lang_sets.items():
                            if lang_code in group_lang_set:
                                all_languages.add(lang_code)
                                extra_group_translations[group_name][lang_code] = translation
                                if lang_code in metadata_by_lang:
                                    extra_group_metadata[group_name][lang_code] = metadata_by_lang[
                                        lang_code
                                    ]
                                break

            # The base record is built by storage.release.lemma, the same
            # function the Barsukas sync uses, so the two exports cannot
            # disagree about it. (They used to: this path wrote
            # concept_label without the disambiguation and omitted qid and
            # translation_disambiguations, so a CLI export after UI work
            # stripped both from the tree.) Secondary and grouped-language
            # records are this function's own concern and stay below.
            base_records.append(lemma_to_release_record(lemma, qid=qid_by_lemma_id.get(lemma.id)))

            # Secondary translations record (guid + translations only)
            if secondary_translations_dict:
                secondary_data: Dict[str, Any] = {
                    "guid": lemma.guid,
                    "translations": secondary_translations_dict,
                }
                if secondary_translation_metadata_dict:
                    secondary_data["translation_metadata"] = secondary_translation_metadata_dict
                secondary_records.append(secondary_data)

            for group_name, group_translations in extra_group_translations.items():
                if group_translations:
                    group_data: Dict[str, Any] = {
                        "guid": lemma.guid,
                        "translations": group_translations,
                    }
                    group_metadata = extra_group_metadata.get(group_name, {})
                    if group_metadata:
                        group_data["translation_metadata"] = group_metadata
                    extra_group_records[group_name].append(group_data)

        # Write base.jsonl (now includes translations)
        base_file = category_dir / "base.jsonl"
        write_jsonl_atomic(base_file, base_records)

        # Write secondary.jsonl (secondary language translations)
        secondary_file = category_dir / "secondary.jsonl"
        write_jsonl_atomic(secondary_file, secondary_records)

        for group_name, group_records in extra_group_records.items():
            group_file = category_dir / f"{group_name}.jsonl"
            write_jsonl_atomic(group_file, group_records)

        # Collect per-language data (derivative_forms, grammar_facts)
        # keyed by language code -> list of per-lemma records
        lang_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for lemma in category_lemmas:
            # Derivative forms, split into the array-shaped "forms" and
            # "synonyms" keys by storage.release.derivative_form -- the same
            # builder the /sync/derivatives and /sync/synonyms pages use.
            #
            # Forms the langtools rules regenerate are withheld: the release
            # carries only what cannot be derived, and generate_mechanical_forms
            # puts the rest back on import.  Without this an export after a
            # bootstrap writes back every generated paradigm.
            forms_by_lang, synonyms_by_lang = forms_by_language(
                without_derivable(session, lemma, lemma.derivative_forms)
            )

            # Variant forms (alternate spellings), already grouped per
            # language and per variant by storage.release.variant.
            variants_by_lang: Dict[str, List[Dict[str, Any]]] = release_variants_by_language(
                lemma.variant_forms
            )

            # Group grammar facts by language (only whitelisted types)
            facts_by_lang: Dict[str, List[Dict[str, Any]]] = {}
            for fact in lemma.grammar_facts:
                lang = fact.language_code
                allowed_types = RELEASE_GRAMMAR_FACT_TYPES.get(lang)
                if allowed_types and fact.fact_type in allowed_types:
                    if lang not in facts_by_lang:
                        facts_by_lang[lang] = []
                    facts_by_lang[lang].append(
                        {
                            "fact_type": fact.fact_type,
                            "fact_value": fact.fact_value,
                        }
                    )

            # Build per-language records for release languages that have data
            langs_with_data = (
                set(forms_by_lang.keys())
                | set(synonyms_by_lang.keys())
                | set(variants_by_lang.keys())
                | set(facts_by_lang.keys())
            ) & release_lang_set
            for lang in langs_with_data:
                record: Dict[str, Any] = {"guid": lemma.guid}
                if lang in forms_by_lang:
                    record["forms"] = forms_by_lang[lang]
                if lang in synonyms_by_lang:
                    record["synonyms"] = synonyms_by_lang[lang]
                if lang in variants_by_lang:
                    record["variants"] = variants_by_lang[lang]
                if lang in facts_by_lang:
                    record["grammar_facts"] = facts_by_lang[lang]
                lang_records[lang].append(record)

        # Write {lang}.jsonl files for each language that has data
        for lang, records in sorted(lang_records.items()):
            lang_file = category_dir / f"{lang}.jsonl"
            write_jsonl_atomic(lang_file, records)

        # A language that had rows before and has none now must lose its
        # file, or the export stops being a rebuild: the stale file would
        # survive and be re-imported.  This is reachable whenever the last
        # row for a language goes away -- deleting a translation, or the
        # mechanical filter withholding a whole category's forms.
        # "audio" is written by the separate lemma-audio export, so it is
        # reserved here even though this pass never writes it.
        reserved_stems = {"base", "secondary", "audio"} | set(extra_group_records)
        for stale_file in category_dir.glob("*.jsonl"):
            lang = stale_file.stem
            if lang in reserved_stems or lang in lang_records:
                continue
            stale_file.unlink()

    print(f"\nExport complete!")
    print(f"Languages exported: {', '.join(sorted(all_languages))}")
    return LemmaExportStats(lemmas=len(lemmas), languages=sorted(all_languages))
