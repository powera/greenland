"""
Atacama export format — JSON lookup table for English word annotations.

Produces a single JSON file keyed by lowercase English word, containing
lemma metadata, translations, and derivative form mappings. Used by the
atacama blog system to annotate English text with vocabulary data.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from langtools.en.grammatical_words import ENGLISH_STOPWORD_ANNOTATIONS
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import bulk_get_translations

logger = logging.getLogger(__name__)


class AtacamaExporter:
    """Exports lemma data as a JSON lookup table for the atacama blog system."""

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        languages: Tuple[str, ...] = ("zh", "lt", "fr", "es"),
    ) -> None:
        """
        Initialize the AtacamaExporter.

        Args:
            config: DataSourceConfig with backend settings (uses default SQLite if None)
            languages: Tuple of language codes to include in translations
        """
        if config is None:
            config = DataSourceConfig(backend_type=BackendType.SQLITE)
        self.config = config
        self.languages = languages

    def _load_stopwords(self) -> Dict[str, Dict[str, str]]:
        """Return the stopword table from the langtools English registry.

        ENGLISH_STOPWORD_ANNOTATIONS covers all four grammatical tiers plus
        contractions, keyed by lowercase surface form. Entries are flagged in
        the export and not processed further: no GUID, no translations, no
        Lemma table entry. The "lemma" field is a display headword ("I" for
        "me", "do not" for "don't"), not a link to a lemma.

        This used to read data/release/stopwords/en.jsonl, a hand-maintained
        file that had drifted to 58 words - missing every conjunction ("as",
        "and", "but"), determiner, interrogative and particle. Deriving from
        the registry makes that drift impossible.

        Returns:
            Dictionary keyed by lowercase word → {pos, lemma}
        """
        stopwords: Dict[str, Dict[str, str]] = {
            word: dict(annotation) for word, annotation in ENGLISH_STOPWORD_ANNOTATIONS.items()
        }
        logger.info("Loaded %d stopword entries from the langtools registry", len(stopwords))
        return stopwords

    def _load_derivative_forms_from_jsonl(
        self, guid_set: set[str]
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Scan en.jsonl files for English derivative forms.

        The JSONL backend does not populate the DerivativeForm table in its
        in-memory SQLite DB, so we read derivative forms directly from the
        per-language files.

        Args:
            guid_set: Set of GUIDs to include (only derivatives for these lemmas)

        Returns:
            Dictionary mapping GUID → list of (form_text, grammatical_form) tuples
        """
        derivatives_by_guid: Dict[str, List[Tuple[str, str]]] = {}

        for data_dir_name in ("working", "release"):
            lemmas_dir = Path(constants.PROJECT_ROOT) / "data" / data_dir_name / "lemmas"
            if not lemmas_dir.exists():
                continue

            for en_file in lemmas_dir.rglob("en.jsonl"):
                try:
                    with open(en_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            data = json.loads(line)
                            guid = data.get("guid")
                            if not guid or guid not in guid_set:
                                continue
                            if "derivative_forms" not in data:
                                continue
                            forms = data["derivative_forms"]
                            for form_name, form_data in forms.items():
                                form_text = form_data.get("form", "")
                                if form_text:
                                    derivatives_by_guid.setdefault(guid, []).append(
                                        (form_text, form_name)
                                    )
                except Exception as e:
                    logger.warning("Error reading %s: %s", en_file, e)

            # Prefer working directory data; only fall back to release if working has no data
            if derivatives_by_guid:
                break

        total_forms = sum(len(v) for v in derivatives_by_guid.values())
        logger.info(
            "Loaded %d English derivative forms from JSONL files for %d lemmas",
            total_forms,
            len(derivatives_by_guid),
        )
        return derivatives_by_guid

    def export(self, output_path: str) -> Dict[str, Any]:
        """Export the atacama lookup JSON file.

        Args:
            output_path: Path to write the output JSON file

        Returns:
            The generated lookup dictionary (for testing/inspection)
        """
        session = create_session(self.config)

        try:
            # 1. Query all lemmas with GUIDs
            lemmas: List[Lemma] = session.query(Lemma).filter(Lemma.guid.isnot(None)).all()
            logger.info("Found %d lemmas with GUIDs", len(lemmas))

            # 2. Bulk-fetch translations for each requested language
            translations_by_lang: Dict[str, Dict[int, Optional[str]]] = {}
            for lang_code in self.languages:
                translations_by_lang[lang_code] = bulk_get_translations(session, lemmas, lang_code)

            # 3. Query English derivative forms from DB
            db_derivative_forms: List[DerivativeForm] = (
                session.query(DerivativeForm).filter(DerivativeForm.language_code == "en").all()
            )
            logger.info("Found %d English derivative forms in DB", len(db_derivative_forms))

            # Build lemma mappings
            lemma_by_id: Dict[int, Lemma] = {lemma.id: lemma for lemma in lemmas}
            lemma_by_guid: Dict[str, Lemma] = {lemma.guid: lemma for lemma in lemmas if lemma.guid}

            # 4. Build the lookup dictionary
            lookup: Dict[str, Any] = {}

            # Add base lemma entries
            for lemma in lemmas:
                word_key = lemma.lemma_text.lower()
                translations: Dict[str, str] = {}
                for lang_code in self.languages:
                    trans = translations_by_lang[lang_code].get(lemma.id)
                    if trans:
                        translations[lang_code] = trans

                entry: Dict[str, Any] = {
                    "guid": lemma.guid,
                    "lemma": lemma.lemma_text,
                    "definition": lemma.definition_text,
                    "pos_type": lemma.pos_type,
                }
                if lemma.pos_subtype:
                    entry["pos_subtype"] = lemma.pos_subtype
                if translations:
                    entry["translations"] = translations

                # Prefer base form over derivative if collision
                if word_key not in lookup or "form" in lookup.get(word_key, {}):
                    lookup[word_key] = entry

            # Add derivative form entries from DB (SQLite/Postgres backends)
            derivative_count = 0
            for df in db_derivative_forms:
                if df.lemma_id not in lemma_by_id:
                    continue

                parent_lemma = lemma_by_id[df.lemma_id]
                word_key = df.derivative_form_text.lower()

                if word_key in lookup and "form" not in lookup[word_key]:
                    continue

                translations = {}
                for lang_code in self.languages:
                    trans = translations_by_lang[lang_code].get(parent_lemma.id)
                    if trans:
                        translations[lang_code] = trans

                entry = {
                    "guid": parent_lemma.guid,
                    "lemma": parent_lemma.lemma_text,
                    "form": df.grammatical_form,
                    "definition": parent_lemma.definition_text,
                    "pos_type": parent_lemma.pos_type,
                }
                if parent_lemma.pos_subtype:
                    entry["pos_subtype"] = parent_lemma.pos_subtype
                if translations:
                    entry["translations"] = translations

                lookup[word_key] = entry
                derivative_count += 1

            # If DB had no derivative forms, read from JSONL files directly
            if derivative_count == 0 and len(lemmas) > 0:
                guid_set = {lemma.guid for lemma in lemmas if lemma.guid}
                jsonl_derivatives = self._load_derivative_forms_from_jsonl(guid_set)

                for guid, form_list in jsonl_derivatives.items():
                    maybe_parent = lemma_by_guid.get(guid)
                    if not maybe_parent:
                        continue
                    parent_lemma = maybe_parent

                    for form_text, form_name in form_list:
                        word_key = form_text.lower()

                        if word_key in lookup and "form" not in lookup[word_key]:
                            continue

                        translations = {}
                        for lang_code in self.languages:
                            trans = translations_by_lang[lang_code].get(parent_lemma.id)
                            if trans:
                                translations[lang_code] = trans

                        entry = {
                            "guid": parent_lemma.guid,
                            "lemma": parent_lemma.lemma_text,
                            "form": form_name,
                            "definition": parent_lemma.definition_text,
                            "pos_type": parent_lemma.pos_type,
                        }
                        if parent_lemma.pos_subtype:
                            entry["pos_subtype"] = parent_lemma.pos_subtype
                        if translations:
                            entry["translations"] = translations

                        lookup[word_key] = entry
                        derivative_count += 1

            # 5. Load and embed stopwords
            stopwords = self._load_stopwords()

            # 6. Build metadata
            meta: Dict[str, Any] = {
                "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "lemma_count": len(lemmas),
                "entry_count": len(lookup),
                "languages": list(self.languages),
            }

            # 7. Assemble final output with _meta and _stopwords first
            output: Dict[str, Any] = {"_meta": meta, "_stopwords": stopwords}
            output.update(lookup)

            # 8. Write to file
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            logger.info(
                "Exported %d entries (%d base + %d derivative) + %d stopwords to %s",
                len(lookup),
                len(lemmas),
                derivative_count,
                len(stopwords),
                output_path,
            )
            return output

        finally:
            session.close()
