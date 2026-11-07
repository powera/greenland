"""Reading lexicon export: look up any word of running text in one language.

One file per *text language* -- the language being read -- shaped for word-by-
word annotated reading (click a word, see its dictionary form, grammar and
glosses).  newslettr and pow3 consume it; the format is documented in
``src/exports/reading_lexicon/README.md`` and versioned by ``_meta.schema``.

Unlike the WireWord export, this one is not a curriculum:

* every lemma with a translation in the text language is included, at any
  level, except words excluded for that language (level -1) and, unless asked,
  the unreviewed staging band;
* ``forms`` maps every surface spelling -- stored inflections, the rule-built
  paradigm (including the reading-only tenses), the base form and accepted
  spelling variants -- to a *list* of analyses, so a homograph ("lead",
  Spanish "como") keeps all its readings;
* ``redirects`` follows the GUID tombstones, so an ID stored against a post
  last year still resolves after a merge or recategorisation.

Stored derivative forms win over the rules when both fill a slot: a stored
row that differs from the rule is an irregular (or a known-bad row awaiting
cleanup), exactly as in the release files.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

import constants
from langtools.dialect_overrides import get_base_language
from langtools.grammatical_word_schema import GRAMMATICAL_SUBCATEGORY_KEYS
from langtools.zh.pinyin_helper import word_reading
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.crud.difficulty_override import bulk_get_effective_difficulty_levels
from storage.crud.grammar_fact import bulk_get_effective_grammar_facts
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import SYNONYM_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.models.variant_form import ACCEPTED_ANSWER_VARIANT_KINDS, VariantForm
from storage.translation_helpers import bulk_get_translations

logger = logging.getLogger(__name__)

SCHEMA = "greenland-reading-lexicon/1"

#: Glosses shipped by default: the five reading languages.
DEFAULT_GLOSS_LANGUAGES: Tuple[str, ...] = ("en", "es", "fr", "zh", "lt")

#: Grammar facts that describe the word to a reader.  Principal parts and
#: form overrides are already visible as ``forms``; the rest is noise here.
READER_FACT_TYPES: Tuple[str, ...] = (
    "grammatical_gender",
    "countability",
    "number_type",
    "animacy",
    "verb_transitivity",
    "verb_reflexivity",
    "auxiliary_verb",
    "measure_words",
)

#: Part of speech for each grammatical-word subcategory.
_SUBCATEGORY_POS: Dict[str, str] = {
    "personal_pronouns": "pronoun",
    "articles": "article",
    "auxiliaries": "auxiliary_verb",
    "particles": "particle",
    "prepositions": "preposition",
    "conjunctions": "conjunction",
    "determiners": "determiner",
    "interrogatives": "pronoun",
    "demonstratives": "determiner",
    "contractions": "contraction",
}

# Analysis sources, most authoritative first.
SOURCE_BASE = "base"
SOURCE_STORED = "stored"
SOURCE_RULE = "rule"
SOURCE_VARIANT = "variant"


def surface_key(text: str) -> str:
    """Normalise a surface form to its lookup key: trimmed, lowercased.

    Typographic apostrophes are folded so "l’homme" and "l'homme" meet.
    """
    return text.strip().replace("’", "'").lower()


def function_word_entries(language_code: str) -> Dict[str, List[Dict[str, str]]]:
    """Return the grammatical words of *language_code*, keyed by surface.

    Each entry carries ``pos`` and ``category`` (the registry subcategory).
    English also carries ``lemma``, its display headword ("be" for "was",
    "do not" for "don't").  These words have no GUID.
    """
    import importlib

    from langtools import grammatical_words as registry

    base = get_base_language(language_code)
    module_path = registry._LANGUAGE_MODULE_PATHS.get(base)
    prefix = registry._LANGUAGE_CONSTANT_PREFIXES.get(base)
    if module_path is None or prefix is None:
        return {}
    module = importlib.import_module(module_path)
    by_subcategory = getattr(module, f"{prefix}_GRAMMATICAL_WORDS_BY_SUBCATEGORY", {})

    headwords: Dict[str, Dict[str, str]] = {}
    if base == "en":
        from langtools.en.grammatical_words import ENGLISH_STOPWORD_ANNOTATIONS

        headwords = ENGLISH_STOPWORD_ANNOTATIONS

    entries: Dict[str, List[Dict[str, str]]] = {}
    for subcategory in GRAMMATICAL_SUBCATEGORY_KEYS:
        for word in sorted(by_subcategory.get(subcategory, ())):
            entry: Dict[str, str] = {
                "pos": _SUBCATEGORY_POS[subcategory],
                "category": subcategory,
            }
            headword = headwords.get(word, {}).get("lemma")
            if headword and headword != word:
                entry["lemma"] = headword
            key = surface_key(word)
            if entry not in entries.setdefault(key, []):
                entries[key].append(entry)
    return entries


def resolve_redirects(
    tombstones: Iterable[Tuple[str, Optional[str]]],
) -> Tuple[Dict[str, str], List[str]]:
    """Follow tombstone chains to the live GUID each old one now means.

    Returns ``(redirects, deleted)``: old GUID -> final live GUID, and the
    GUIDs whose chain ends without a replacement.  A cycle is treated as
    deleted rather than looped on.
    """
    replacement: Dict[str, Optional[str]] = dict(tombstones)
    redirects: Dict[str, str] = {}
    deleted: List[str] = []
    for guid in sorted(replacement):
        seen: Set[str] = {guid}
        current: Optional[str] = replacement[guid]
        while current is not None and current in replacement:
            if current in seen:
                current = None
                break
            seen.add(current)
            current = replacement[current]
        if current is None:
            deleted.append(guid)
        else:
            redirects[guid] = current
    return redirects, deleted


class ReadingLexiconExporter:
    """Build and write the reading lexicon for one text language."""

    def __init__(
        self,
        language: str,
        config: Optional[DataSourceConfig] = None,
        gloss_languages: Sequence[str] = DEFAULT_GLOSS_LANGUAGES,
        include_staging: bool = False,
        derive_forms: bool = True,
    ) -> None:
        """
        Args:
            language: The text language (``en``, ``es``, ``lt``, ``zh``, ...).
            config: Backend settings; the default SQLite database when None.
            gloss_languages: Languages to gloss each lemma in.  The text
                language itself is left out: it is the ``lemma`` field.
            include_staging: Also export the unreviewed staging band.
            derive_forms: Fill paradigms by rule where no row is stored, so
                a database whose forms were never generated still exports
                them.  Turn off to export exactly what is stored.
        """
        self.language = language
        self.config = config or DataSourceConfig(backend_type=BackendType.SQLITE)
        self.gloss_languages = tuple(code for code in gloss_languages if code != language)
        self.include_staging = include_staging
        self.derive_forms = derive_forms

    # -- selection -----------------------------------------------------------

    def _select_lemmas(
        self, session: Session
    ) -> Tuple[List[Lemma], Dict[int, str], Dict[int, Optional[int]]]:
        """Return the exported lemmas, their text-language headwords and levels."""
        lemmas: List[Lemma] = (
            session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.guid).all()
        )
        levels = bulk_get_effective_difficulty_levels(session, lemmas, self.language)
        if self.language == "en":
            headwords: Dict[int, str] = {lemma.id: lemma.lemma_text for lemma in lemmas}
        else:
            translations = bulk_get_translations(session, lemmas, self.language)
            headwords = {
                lemma_id: text.strip()
                for lemma_id, text in translations.items()
                if text and text.strip()
            }

        selected: List[Lemma] = []
        for lemma in lemmas:
            level = levels.get(lemma.id)
            if lemma.id not in headwords:
                continue
            if level == constants.EXCLUDE_DIFFICULTY_LEVEL:
                continue
            if level == constants.STAGING_DIFFICULTY_LEVEL and not self.include_staging:
                continue
            selected.append(lemma)
        return selected, headwords, levels

    # -- forms ---------------------------------------------------------------

    def _stored_forms(
        self, session: Session, lemma_ids: List[int]
    ) -> Dict[int, List[Tuple[str, str]]]:
        """lemma_id -> [(grammatical_form, text)] stored for the text language."""
        stored: Dict[int, List[Tuple[str, str]]] = {}
        rows = (
            session.query(
                DerivativeForm.lemma_id,
                DerivativeForm.grammatical_form,
                DerivativeForm.derivative_form_text,
            )
            .filter(
                DerivativeForm.lemma_id.in_(lemma_ids),
                DerivativeForm.language_code == self.language,
            )
            .order_by(DerivativeForm.id)
        )
        for lemma_id, grammatical_form, text in rows:
            if grammatical_form in SYNONYM_GRAMMATICAL_FORMS or not text:
                continue
            stored.setdefault(lemma_id, []).append((grammatical_form, text))
        return stored

    def _variant_forms(
        self, session: Session, lemma_ids: List[int]
    ) -> Dict[int, List[Tuple[str, str]]]:
        """lemma_id -> [(grammatical_form, text)] accepted spelling variants."""
        variants: Dict[int, List[Tuple[str, str]]] = {}
        rows = session.query(
            VariantForm.lemma_id, VariantForm.grammatical_form, VariantForm.variant_form_text
        ).filter(
            VariantForm.lemma_id.in_(lemma_ids),
            VariantForm.language_code == self.language,
            VariantForm.variant_kind.in_(sorted(ACCEPTED_ANSWER_VARIANT_KINDS)),
        )
        for lemma_id, grammatical_form, text in rows:
            if text:
                variants.setdefault(lemma_id, []).append((grammatical_form, text))
        return variants

    def _rule_forms(
        self, session: Session, lemmas: List[Lemma]
    ) -> Dict[int, List[Tuple[str, str]]]:
        """lemma_id -> [(grammatical_form, text)] the mechanical builders derive."""
        from langtools.mechanical_forms import (
            build_for_lemma_with_metadata,
            resolve_grammatical_form,
            supported,
        )
        from langtools.mechanical_inputs import MechanicalInputs

        if self.language not in supported():
            return {}
        derived: Dict[int, List[Tuple[str, str]]] = {}
        session.info["mechanical_inputs"] = MechanicalInputs.load(
            session, [lemma.id for lemma in lemmas]
        )
        try:
            for lemma in lemmas:
                paradigm, _metadata = build_for_lemma_with_metadata(session, lemma, self.language)
                if not paradigm:
                    continue
                pos_type = lemma.pos_type.lower()
                for form_key, text in paradigm.items():
                    if not text:
                        continue
                    grammatical_form = resolve_grammatical_form(self.language, pos_type, form_key)
                    if grammatical_form:
                        derived.setdefault(lemma.id, []).append((grammatical_form, text))
        finally:
            session.info.pop("mechanical_inputs", None)
        return derived

    # -- assembly ------------------------------------------------------------

    def _lemma_entry(
        self,
        lemma: Lemma,
        headword: str,
        level: Optional[int],
        glosses: Dict[str, Dict[int, Optional[str]]],
        facts: Dict[str, Optional[str]],
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "lemma": headword,
            "pos": lemma.pos_type,
        }
        if lemma.pos_subtype:
            entry["subtype"] = lemma.pos_subtype
        if level is not None:
            entry["level"] = level
        if lemma.definition_text:
            entry["definition"] = {"en": lemma.definition_text}
        if lemma.disambiguation:
            entry["sense"] = {"en": lemma.disambiguation}
        gloss: Dict[str, str] = {}
        for code in self.gloss_languages:
            text = lemma.lemma_text if code == "en" else glosses[code].get(lemma.id)
            if text:
                gloss[code] = text
        if gloss:
            entry["gloss"] = gloss
        reader_facts = {
            fact_type: value for fact_type in READER_FACT_TYPES if (value := facts.get(fact_type))
        }
        if reader_facts:
            entry["facts"] = reader_facts
        if get_base_language(self.language) == "zh":
            reading = word_reading(headword, facts.get("pinyin"))
            if reading is not None:
                entry["reading"] = {
                    "pinyin": reading.pinyin,
                    "syllables": list(reading.syllables),
                    "source": reading.source,
                }
                if reading.is_ambiguous:
                    entry["reading"]["review"] = True
        return entry

    def build(self, session: Session) -> Dict[str, Any]:
        """Build the lexicon document from *session* (no file is written)."""
        lemmas, headwords, levels = self._select_lemmas(session)
        lemma_ids = [lemma.id for lemma in lemmas]
        logger.info("Reading lexicon %s: %d lemmas", self.language, len(lemmas))

        glosses = {
            code: bulk_get_translations(session, lemmas, code)
            for code in self.gloss_languages
            if code != "en"
        }
        facts_by_lemma = bulk_get_effective_grammar_facts(session, lemma_ids, self.language)
        stored = self._stored_forms(session, lemma_ids)
        rules = self._rule_forms(session, lemmas) if self.derive_forms else {}
        variants = self._variant_forms(session, lemma_ids)

        lemma_entries: Dict[str, Dict[str, Any]] = {}
        forms: Dict[str, List[Dict[str, Any]]] = {}

        def add(surface: str, guid: str, grammatical_form: Optional[str], source: str) -> None:
            key = surface_key(surface)
            if not key:
                return
            analyses = forms.setdefault(key, [])
            for existing in analyses:
                if existing["g"] == guid and existing.get("f") == grammatical_form:
                    return
            analysis: Dict[str, Any] = {"g": guid, "src": source}
            if grammatical_form:
                analysis["f"] = grammatical_form
            analyses.append(analysis)

        for lemma in lemmas:
            assert lemma.guid is not None
            guid = lemma.guid
            headword = headwords[lemma.id]
            lemma_entries[guid] = self._lemma_entry(
                lemma, headword, levels.get(lemma.id), glosses, facts_by_lemma.get(lemma.id, {})
            )
            stored_rows = stored.get(lemma.id, [])
            stored_slots = {grammatical_form for grammatical_form, _ in stored_rows}
            base_slot = next(
                (form for form, text in stored_rows if surface_key(text) == surface_key(headword)),
                None,
            )
            add(headword, guid, base_slot, SOURCE_BASE)
            for grammatical_form, text in stored_rows:
                add(text, guid, grammatical_form, SOURCE_STORED)
            for grammatical_form, text in rules.get(lemma.id, []):
                if grammatical_form not in stored_slots:
                    add(text, guid, grammatical_form, SOURCE_RULE)
            for grammatical_form, text in variants.get(lemma.id, []):
                add(text, guid, grammatical_form or None, SOURCE_VARIANT)

        tombstone_rows = session.query(GuidTombstone.guid, GuidTombstone.replacement_guid).all()
        redirects, deleted = resolve_redirects((row[0], row[1]) for row in tombstone_rows)
        # A redirect must land on something this file can show.
        redirects = {old: new for old, new in redirects.items() if new in lemma_entries}

        function_words = function_word_entries(self.language)

        meta: Dict[str, Any] = {
            "schema": SCHEMA,
            "language": self.language,
            "gloss_languages": list(self.gloss_languages),
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lemma_count": len(lemma_entries),
            "form_count": len(forms),
            "analysis_count": sum(len(analyses) for analyses in forms.values()),
            "function_word_count": len(function_words),
            "include_staging": self.include_staging,
            "derived_forms": self.derive_forms,
        }
        return {
            "_meta": meta,
            "lemmas": lemma_entries,
            "forms": dict(sorted(forms.items())),
            "function_words": function_words,
            "redirects": redirects,
            "deleted": deleted,
        }

    def export(self, output_path: str, pretty: bool = False) -> Dict[str, Any]:
        """Build the lexicon from the configured backend and write it to *output_path*."""
        session = create_session(self.config)
        try:
            document = self.build(session)
        finally:
            session.close()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            if pretty:
                json.dump(document, handle, ensure_ascii=False, indent=1)
            else:
                json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        meta = document["_meta"]
        logger.info(
            "Wrote %s: %d lemmas, %d surface forms, %d function words",
            output_path,
            meta["lemma_count"],
            meta["form_count"],
            meta["function_word_count"],
        )
        return document
