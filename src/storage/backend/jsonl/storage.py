"""JSONL storage backend implementation."""

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

from storage.backend.base import BaseSession, BaseStorage
from storage.backend.jsonl import models
from storage.backend.jsonl.session import JSONLSession
from storage.models.schema import NON_INFLECTION_GRAMMATICAL_FORMS
from storage.models.variant_form import VARIANT_KIND_SPELLING
from storage.translation_helpers import EXTRA_RELEASE_LANGUAGE_GROUPS

# Files under lemmas/{pos}/{subtype}/ whose stem is not a language code.
#
# Grouped translation files hold the same {guid, translations, translation_metadata}
# shape as base.jsonl but for languages kept out of the main record: every Tier 3/4
# language in secondary.jsonl, and one file per named group (ancient.jsonl). Reading
# them as if "secondary"/"ancient" were language codes is how those translations used
# to get dropped on import, so they are routed by name here instead.
GROUPED_TRANSLATION_FILE_STEMS: Set[str] = {"secondary", *EXTRA_RELEASE_LANGUAGE_GROUPS}

# audio.jsonl carries approved audio metadata, not lemma content. It is imported
# separately (storage.migrate.import_lemma_audio_release_to_sqlite) because those
# rows land in audio tables, so the lemma loader skips it rather than treating
# "audio" as a language.
NON_LEMMA_FILE_STEMS: Set[str] = {"audio"}


class JSONLStorage(BaseStorage):
    """JSONL storage backend implementation.

    This backend stores all data as JSONL files organized by type and subtype.
    All data is loaded into memory for fast querying.
    """

    def __init__(self, data_dir: str):
        """Initialize JSONL storage.

        Args:
            data_dir: Path to the JSONL data directory (e.g., data/working)
        """
        self.data_dir = Path(data_dir)

        # In-memory storage
        self.lemmas: Dict[str, models.Lemma] = {}  # guid -> Lemma
        self.lemmas_by_id: Dict[int, models.Lemma] = {}  # id -> Lemma
        self.sentences: Dict[str, models.Sentence] = {}  # guid -> Sentence
        self.sentences_by_id: Dict[int, models.Sentence] = {}  # id -> Sentence
        self.phrases: Dict[str, models.Phrase] = {}  # guid -> Phrase
        self.phrases_by_id: Dict[int, models.Phrase] = {}  # id -> Phrase
        self.audio_reviews: List[models.AudioQualityReview] = []
        self.operation_logs: List[models.OperationLog] = []
        self.tombstones: List[models.GuidTombstone] = []
        self.lemma_verifications: Dict[str, models.LemmaVerification] = {}  # guid -> verification
        self.sentence_verifications: Dict[str, models.SentenceVerification] = (
            {}
        )  # guid -> verification
        self.relation_groups: List[models.LemmaRelationGroup] = []

        # ID counters for new objects
        self._next_lemma_id = 1
        self._next_sentence_id = 1
        self._next_phrase_id = 1
        self._next_audio_review_id = 1
        self._next_operation_log_id = 1
        self._next_tombstone_id = 1
        self._next_relation_group_id = 1
        self._next_relation_member_id = 1

        # Track if data is loaded
        self._loaded = False

        # Cached SQLite engine (shared across sessions for read-only mode).
        # Populated once on first query, then reused for all subsequent sessions.
        self._cached_sqlite_engine: Optional[Any] = None
        self._sqlite_populated = False

    def ensure_initialized(self) -> None:
        """Ensure directory structure exists and data is loaded."""
        self._ensure_directories()
        if not self._loaded:
            self._load_all_data()
            self._loaded = True

    def _ensure_directories(self) -> None:
        """Create directory structure if it doesn't exist."""
        # Create top-level directories
        # Lemma subdirectories will be created on-demand per POS/subtype/language
        directories = [
            self.data_dir / "lemmas",
            self.data_dir / "sentences",
            self.data_dir / "phrases",
            self.data_dir / "audio_reviews",
            self.data_dir / "operation_logs",
            self.data_dir / "tombstones",
            self.data_dir / "verifications",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_all_data(self) -> None:
        """Load all JSONL files into memory."""
        self._load_lemmas()
        self._load_sentences()
        self._load_phrases()
        self._load_relations()
        self._load_audio_reviews()
        self._load_operation_logs()
        self._load_tombstones()
        self._load_verifications()

    def _load_lemmas(self) -> None:
        """Load all lemma files from disk.

        New structure: lemmas are organized by POS type/subtype with per-language files:
        lemmas/nouns/animal/base.jsonl (concept definition + translations for all languages)
        lemmas/nouns/animal/en.jsonl (English-specific data: definition_text, tags, etc.)
        lemmas/nouns/animal/zh.jsonl (Chinese data: derivative_forms, base_form, audio, etc.)
        etc.
        """
        lemmas_dir = self.data_dir / "lemmas"
        if not lemmas_dir.exists():
            return

        # First pass: Load all base.jsonl files (concept definition + translations)
        for base_file in lemmas_dir.rglob("base.jsonl"):
            try:
                with open(base_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)

                        # Create Lemma from base concept data
                        lemma = models.Lemma()
                        lemma.guid = data.get("guid")
                        lemma.pos_type = data.get("pos_type", "")
                        lemma.pos_subtype = data.get("pos_subtype")
                        lemma.concept_label = data.get("concept_label", "")
                        lemma.concept_definition = data.get("concept_definition", "")

                        # Load translations from base.jsonl (new format)
                        if "translations" in data:
                            lemma.translations = data["translations"]

                        # Load difficulty_overrides from base.jsonl (new format)
                        if "difficulty_overrides" in data:
                            lemma.difficulty_overrides = data["difficulty_overrides"]

                        # Load translation_disambiguations from base.jsonl
                        if "translation_disambiguations" in data:
                            lemma.translation_disambiguations = data["translation_disambiguations"]

                        # Load per-language translation status from base.jsonl
                        if "translation_metadata" in data:
                            lemma.translation_metadata = dict(data["translation_metadata"])

                        # Load emoji list from base.jsonl
                        if "emoji" in data and data["emoji"]:
                            lemma.emoji = list(data["emoji"])

                        # Populate lemma_text and definition_text from concept fields
                        # or from translations dict for backward compatibility
                        if "en" in lemma.translations:
                            lemma.lemma_text = lemma.translations["en"]
                        else:
                            lemma.lemma_text = lemma.concept_label
                        lemma.definition_text = lemma.concept_definition

                        lemma.difficulty_level = data.get("difficulty_level")
                        lemma.notes = data.get("notes")
                        lemma.lexical_gap_reason = data.get("lexical_gap_reason")
                        lemma.qid = data.get("qid")
                        lemma.added_at = data.get("added_at")
                        if isinstance(lemma.added_at, str):
                            from datetime import datetime

                            lemma.added_at = datetime.fromisoformat(lemma.added_at)

                        # Assign ID if not present
                        if lemma.id is None:
                            lemma.id = self._next_lemma_id
                            self._next_lemma_id += 1

                        # Store by guid and id
                        if lemma.guid:
                            self.lemmas[lemma.guid] = lemma
                        self.lemmas_by_id[lemma.id] = lemma

            except Exception as e:
                print(f"Error loading {base_file}: {e}")

        # Second pass: grouped translation files (secondary.jsonl and the named
        # extra-language groups). These must be merged before the per-language
        # pass rejects them: their stem is a group name, not a language code.
        for grouped_file in lemmas_dir.rglob("*.jsonl"):
            if grouped_file.stem in GROUPED_TRANSLATION_FILE_STEMS:
                self._merge_grouped_translation_file(grouped_file)

        # Third pass: Load all language files (including en.jsonl) and merge data
        for lang_file in lemmas_dir.rglob("*.jsonl"):
            # Skip base.jsonl files (already loaded), the grouped translation
            # files handled above, and files that are not lemma content at all.
            if lang_file.name == "base.jsonl":
                continue
            if lang_file.stem in GROUPED_TRANSLATION_FILE_STEMS:
                continue
            if lang_file.stem in NON_LEMMA_FILE_STEMS:
                continue

            lang_code = lang_file.stem  # e.g., "en", "zh" from "en.jsonl", "zh.jsonl"

            try:
                with open(lang_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        guid = data.get("guid")

                        if not guid or guid not in self.lemmas:
                            print(
                                f"Warning: {lang_file} contains guid {guid} not found in base data"
                            )
                            continue

                        # Merge language-specific data into existing lemma
                        lemma = self.lemmas[guid]

                        # Backward compatibility: handle translation field in per-language files
                        # (old format - translations now live in base.jsonl)
                        if "translation" in data:
                            # Only use if not already set from base.jsonl
                            if lang_code not in lemma.translations:
                                lemma.translations[lang_code] = data["translation"]

                        # Backward compatibility: also accept lemma_text for English
                        if lang_code == "en" and "lemma_text" in data:
                            lemma.lemma_text = data["lemma_text"]
                            if "en" not in lemma.translations:
                                lemma.translations["en"] = data["lemma_text"]

                        # base_form: pronunciation/form data when no derivative has is_base_form
                        if "base_form" in data:
                            lemma.base_forms[lang_code] = data["base_form"]

                        # Definition text for this language (all languages can have definitions)
                        if "definition_text" in data:
                            lemma.definitions[lang_code] = data["definition_text"]
                            # Backward compatibility: also populate definition_text for English
                            if lang_code == "en":
                                lemma.definition_text = data["definition_text"]

                        lemma_translation_pronunciation: Dict[str, Optional[str]] = {}
                        if "ipa_pronunciation" in data:
                            lemma_translation_pronunciation["ipa_pronunciation"] = data.get(
                                "ipa_pronunciation"
                            )
                        if "phonetic_pronunciation" in data:
                            lemma_translation_pronunciation["phonetic_pronunciation"] = data.get(
                                "phonetic_pronunciation"
                            )
                        if lemma_translation_pronunciation:
                            lemma.translation_pronunciations[lang_code] = (
                                lemma_translation_pronunciation
                            )

                        if "frequency_rank" in data:
                            if lang_code == "en":
                                lemma.frequency_rank = data["frequency_rank"]

                        if "tags" in data:
                            if lang_code == "en":
                                lemma.tags = data["tags"]

                        if "disambiguation" in data:
                            if lang_code == "en":
                                lemma.disambiguation = data["disambiguation"]

                        if "translation_disambiguation" in data:
                            lemma.translation_disambiguations[lang_code] = data[
                                "translation_disambiguation"
                            ]

                        if "confidence" in data:
                            if lang_code == "en":
                                lemma.confidence = data.get("confidence", 0.0)

                        if "verified" in data:
                            if lang_code == "en":
                                lemma.verified = data.get("verified", False)

                        if "updated_at" in data:
                            if lang_code == "en":
                                lemma.updated_at = data.get("updated_at")
                                if isinstance(lemma.updated_at, str):
                                    from datetime import datetime

                                    lemma.updated_at = datetime.fromisoformat(lemma.updated_at)

                        # Nested data structures
                        if "derivative_forms" in data:
                            lemma.derivative_forms[lang_code] = data["derivative_forms"]

                        # New release format: top-level "forms" array (inflections)
                        # and "synonyms" array. True inflections are merged into
                        # the dict-shaped derivative_forms[lang], which assumes
                        # one entry per grammatical_form. Non-inflection multi-
                        # valued forms (synonyms, abbreviation, expanded_form)
                        # get routed into the list-shaped synonyms[lang] because
                        # the same grammatical_form can repeat per lemma.
                        if "forms" in data and isinstance(data["forms"], list):
                            inflections = lemma.derivative_forms.setdefault(lang_code, {})
                            syn_list_for_forms: Optional[List[Dict[str, Any]]] = None
                            for entry in data["forms"]:
                                gform = entry.get("grammatical_form", "")
                                if not gform:
                                    continue
                                text = entry.get("text", "")
                                if gform in NON_INFLECTION_GRAMMATICAL_FORMS:
                                    if not text:
                                        continue
                                    if syn_list_for_forms is None:
                                        syn_list_for_forms = lemma.synonyms.setdefault(
                                            lang_code, []
                                        )
                                    syn_record: Dict[str, Any] = {
                                        "grammatical_form": gform,
                                        "form": text,
                                    }
                                    if entry.get("ipa"):
                                        syn_record["ipa"] = entry["ipa"]
                                    if entry.get("phonetic"):
                                        syn_record["phonetic"] = entry["phonetic"]
                                    syn_list_for_forms.append(syn_record)
                                    continue
                                if gform in inflections:
                                    print(
                                        f"Warning: {lang_file} guid {guid} has duplicate "
                                        f"inflection grammatical_form '{gform}'; "
                                        f"keeping first, dropping '{text}'"
                                    )
                                    continue
                                form_record: Dict[str, Any] = {
                                    "form": text,
                                    "is_base_form": entry.get("is_base_form", False),
                                }
                                if entry.get("ipa"):
                                    form_record["ipa"] = entry["ipa"]
                                if entry.get("phonetic"):
                                    form_record["phonetic"] = entry["phonetic"]
                                inflections[gform] = form_record

                        if "synonyms" in data and isinstance(data["synonyms"], list):
                            syn_list = lemma.synonyms.setdefault(lang_code, [])
                            for entry in data["synonyms"]:
                                gform = entry.get("grammatical_form", "")
                                text = entry.get("text", "")
                                if not gform or not text:
                                    continue
                                syn_record = {
                                    "grammatical_form": gform,
                                    "form": text,
                                }
                                if entry.get("ipa"):
                                    syn_record["ipa"] = entry["ipa"]
                                if entry.get("phonetic"):
                                    syn_record["phonetic"] = entry["phonetic"]
                                syn_list.append(syn_record)

                        # Alternate spellings ("grey" for "gray"). Handled
                        # separately from "forms" so variants are never routed
                        # into the synonyms bucket: a variant is the same
                        # lexeme, not a different one.
                        if "variants" in data and isinstance(data["variants"], list):
                            variant_list = lemma.variants.setdefault(lang_code, [])
                            for variant_entry in data["variants"]:
                                variant_key = variant_entry.get("key", "")
                                raw_forms = variant_entry.get("forms", [])
                                if not variant_key or not isinstance(raw_forms, list):
                                    continue
                                variant_forms: List[Dict[str, Any]] = []
                                for form_entry in raw_forms:
                                    vgform = form_entry.get("grammatical_form", "")
                                    vtext = form_entry.get("text", "")
                                    if not vgform or not vtext:
                                        continue
                                    variant_record: Dict[str, Any] = {
                                        "grammatical_form": vgform,
                                        "text": vtext,
                                        "is_base_form": form_entry.get("is_base_form", False),
                                    }
                                    if form_entry.get("ipa"):
                                        variant_record["ipa"] = form_entry["ipa"]
                                    if form_entry.get("phonetic"):
                                        variant_record["phonetic"] = form_entry["phonetic"]
                                    variant_forms.append(variant_record)
                                if not variant_forms:
                                    continue
                                variant_list.append(
                                    {
                                        "kind": variant_entry.get("kind", VARIANT_KIND_SPELLING),
                                        "key": variant_key,
                                        "forms": variant_forms,
                                    }
                                )

                        if "audio_hashes" in data:
                            lemma.audio_hashes[lang_code] = data["audio_hashes"]

                        # Backward compatibility: read difficulty_level from per-language files
                        # (new format stores difficulty_overrides in base.jsonl)
                        if "difficulty_level" in data:
                            # Only use if not already set from base.jsonl
                            if lang_code not in lemma.difficulty_overrides:
                                lemma.difficulty_overrides[lang_code] = data["difficulty_level"]

                        if "grammar_facts" in data:
                            # Merge grammar facts with language_code tag
                            for fact in data["grammar_facts"]:
                                fact["language_code"] = lang_code
                                lemma.grammar_facts.append(fact)

            except Exception as e:
                print(f"Error loading {lang_file}: {e}")

    def _merge_grouped_translation_file(self, grouped_file: Path) -> None:
        """Merge one grouped translation file (secondary.jsonl, ancient.jsonl, ...).

        Each line is ``{"guid": ..., "translations": {lang: text},
        "translation_metadata": {lang: {...}}}`` for languages held outside the
        main record. Existing translations win: base.jsonl is the primary record
        for the languages it carries, and a group file should never quietly
        redefine one.
        """
        try:
            with open(grouped_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as parse_error:
                        print(f"Error loading {grouped_file}:{line_num}: {parse_error}")
                        continue

                    guid = data.get("guid")
                    if not guid or guid not in self.lemmas:
                        print(
                            f"Warning: {grouped_file} contains guid {guid} "
                            "not found in base data"
                        )
                        continue

                    lemma = self.lemmas[guid]
                    for lang_code, translation in (data.get("translations") or {}).items():
                        if translation and lang_code not in lemma.translations:
                            lemma.translations[lang_code] = translation
                    for lang_code, metadata in (data.get("translation_metadata") or {}).items():
                        if metadata and lang_code not in lemma.translation_metadata:
                            lemma.translation_metadata[lang_code] = metadata
        except Exception as e:
            print(f"Error loading {grouped_file}: {e}")

    def _load_sentences(self) -> None:
        """Load all sentence files from disk.

        Sentences are sharded across:
        - sentences/pattern/{pattern_type}.jsonl (BUIVOLAS pattern sentences)
        - sentences/group/{group_name}.jsonl (ZVIRDLIS grouped sentences)
        - sentences/misc/misc.jsonl (miscellaneous sentences)
        - sentences/sentences.jsonl (legacy format, for backward compatibility)
        """
        sentences_dir = self.data_dir / "sentences"
        if not sentences_dir.exists():
            return

        # Load from all JSONL files in sentences/ subdirectories
        for sentences_file in sentences_dir.rglob("*.jsonl"):
            try:
                with open(sentences_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            sentence = models.Sentence.from_dict(data)
                        except Exception as line_err:
                            # Skip the bad line but keep loading the rest of the file.
                            print(f"Error loading {sentences_file}:{line_num}: {line_err}")
                            continue

                        # Assign ID if not present
                        if sentence.id is None:
                            sentence.id = self._next_sentence_id
                            self._next_sentence_id += 1
                        else:
                            self._next_sentence_id = max(self._next_sentence_id, sentence.id + 1)

                        # Store by guid and id
                        if sentence.guid:
                            self.sentences[sentence.guid] = sentence
                        self.sentences_by_id[sentence.id] = sentence

            except Exception as e:
                print(f"Error loading {sentences_file}: {e}")

    def _load_phrases(self) -> None:
        """Load all phrase files from disk.

        Phrases live in their own tree, organized by subtype:
        - phrases/{phrase_subtype}/base.jsonl (e.g. phrases/greetings/base.jsonl)
        - phrases/{phrase_subtype}/secondary.jsonl (secondary-language translations)

        Each base line carries: guid, phrase_subtype, concept_label,
        concept_definition, translations, translation_metadata, difficulty_level.
        The phrase_subtype is taken from the record, falling back to the parent
        directory name.
        """
        phrases_dir = self.data_dir / "phrases"
        if not phrases_dir.exists():
            return

        # First pass: base.jsonl files (concept + primary translations).
        for base_file in phrases_dir.rglob("base.jsonl"):
            subtype_from_dir = base_file.parent.name
            try:
                with open(base_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            phrase = models.Phrase.from_dict(data, default_subtype=subtype_from_dir)
                        except Exception as line_err:
                            print(f"Error loading {base_file}:{line_num}: {line_err}")
                            continue

                        if phrase.id is None:
                            phrase.id = self._next_phrase_id
                            self._next_phrase_id += 1
                        else:
                            self._next_phrase_id = max(self._next_phrase_id, phrase.id + 1)

                        if phrase.guid:
                            self.phrases[phrase.guid] = phrase
                        self.phrases_by_id[phrase.id] = phrase
            except Exception as e:
                print(f"Error loading {base_file}: {e}")

        # Second pass: secondary.jsonl files merge extra-language translations
        # into already-loaded phrases (keyed by guid).
        for secondary_file in phrases_dir.rglob("secondary.jsonl"):
            try:
                with open(secondary_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        guid = data.get("guid")
                        if not guid or guid not in self.phrases:
                            continue
                        phrase = self.phrases[guid]
                        for lang_code, text in (data.get("translations") or {}).items():
                            phrase.translations.setdefault(lang_code, text)
                        for lang_code, meta in (data.get("translation_metadata") or {}).items():
                            phrase.translation_metadata.setdefault(lang_code, meta)
            except Exception as e:
                print(f"Error loading {secondary_file}: {e}")

    def _load_relations(self) -> None:
        """Load all lemma relation group files from disk.

        Relation groups are stored as:
        lemma_relations/{relation_type}/{subtype}.jsonl
        Each line: {"concept": "circle", "members": ["A03_001", "N37_001"]}
        """
        relations_dir = self.data_dir / "lemma_relations"
        if not relations_dir.exists():
            return

        for jsonl_file in sorted(relations_dir.rglob("*.jsonl")):
            # relation_type is the parent directory name (e.g., "derivational")
            relation_type = jsonl_file.parent.name

            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        concept = data.get("concept", "")
                        member_guids = data.get("members", [])

                        if not concept or not member_guids:
                            continue

                        group = models.LemmaRelationGroup()
                        group.id = self._next_relation_group_id
                        self._next_relation_group_id += 1
                        group.relation_type = relation_type
                        group.concept_label = concept
                        group.member_guids = member_guids

                        self.relation_groups.append(group)

            except Exception as e:
                print(f"Error loading {jsonl_file}: {e}")

    def _load_audio_reviews(self) -> None:
        """Load audio reviews from disk."""
        audio_file = self.data_dir / "audio_reviews" / "audio_quality_reviews.jsonl"
        if not audio_file.exists():
            return

        try:
            with open(audio_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    review = models.AudioQualityReview.from_dict(data)

                    if review.id is None:
                        review.id = self._next_audio_review_id
                        self._next_audio_review_id += 1
                    else:
                        self._next_audio_review_id = max(self._next_audio_review_id, review.id + 1)

                    self.audio_reviews.append(review)

        except Exception as e:
            print(f"Error loading audio reviews: {e}")

    def _load_operation_logs(self) -> None:
        """Load operation logs from disk."""
        log_file = self.data_dir / "operation_logs" / "operation_log.jsonl"
        if not log_file.exists():
            return

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    log = models.OperationLog.from_dict(data)

                    if log.id is None:
                        log.id = self._next_operation_log_id
                        self._next_operation_log_id += 1
                    else:
                        self._next_operation_log_id = max(self._next_operation_log_id, log.id + 1)

                    self.operation_logs.append(log)

        except Exception as e:
            print(f"Error loading operation logs: {e}")

    def _load_tombstones(self) -> None:
        """Load GUID tombstones from disk."""
        tombstone_file = self.data_dir / "tombstones" / "guid_tombstones.jsonl"
        if not tombstone_file.exists():
            return

        try:
            with open(tombstone_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    tombstone = models.GuidTombstone.from_dict(data)

                    if tombstone.id is None:
                        tombstone.id = self._next_tombstone_id
                        self._next_tombstone_id += 1
                    else:
                        self._next_tombstone_id = max(self._next_tombstone_id, tombstone.id + 1)

                    self.tombstones.append(tombstone)

        except Exception as e:
            print(f"Error loading tombstones: {e}")

    def _load_verifications(self) -> None:
        """Load verification data from disk."""
        # Load lemma verifications
        lemma_verif_file = self.data_dir / "verifications" / "lemmas.jsonl"
        if lemma_verif_file.exists():
            try:
                with open(lemma_verif_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        verification = models.LemmaVerification.from_dict(data)
                        self.lemma_verifications[verification.guid] = verification

                        # Apply verification status to lemma if loaded
                        if verification.guid in self.lemmas:
                            self.lemmas[verification.guid].verified = verification.verified

            except Exception as e:
                print(f"Error loading lemma verifications: {e}")

        # Load sentence verifications
        sentence_verif_file = self.data_dir / "verifications" / "sentences.jsonl"
        if sentence_verif_file.exists():
            try:
                with open(sentence_verif_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        sentence_verification = models.SentenceVerification.from_dict(data)
                        self.sentence_verifications[sentence_verification.guid] = (
                            sentence_verification
                        )

                        # Apply verification status to sentence if loaded
                        if sentence_verification.guid in self.sentences:
                            self.sentences[sentence_verification.guid].verified = (
                                sentence_verification.verified
                            )

            except Exception as e:
                print(f"Error loading sentence verifications: {e}")

    def save_lemma(self, lemma: models.Lemma) -> None:
        """Save a lemma to disk atomically.

        Args:
            lemma: The lemma to save
        """
        # Ensure lemma has ID
        if lemma.id is None:
            lemma.id = self._next_lemma_id
            self._next_lemma_id += 1

        # Update in-memory storage
        if lemma.guid:
            self.lemmas[lemma.guid] = lemma
        self.lemmas_by_id[lemma.id] = lemma

        # Save base.jsonl file (includes translations and difficulty_overrides)
        self._rewrite_base_file(lemma)

        # Determine which languages need per-language files
        # Note: translations and difficulty_overrides are now in base.jsonl.
        # Per-language files are needed for derivative_forms, base_forms,
        # audio_hashes, grammar_facts, definitions, and English-only fields.
        languages_to_save: Set[str] = set()
        languages_to_save.update(lemma.derivative_forms.keys())
        languages_to_save.update(lemma.base_forms.keys())
        languages_to_save.update(lemma.audio_hashes.keys())
        languages_to_save.update(lemma.definitions.keys())
        languages_to_save.update(lemma.translation_disambiguations.keys())
        languages_to_save.update(lemma.variants.keys())

        # Extract grammar_facts languages
        for fact in lemma.grammar_facts:
            if "language_code" in fact:
                languages_to_save.add(fact["language_code"])

        # English file may also have tags, disambiguation, confidence (English-only fields)
        # and definition_text for backward compat
        if lemma.definition_text or lemma.tags or lemma.disambiguation or lemma.confidence:
            languages_to_save.add("en")

        # Rewrite all affected language files
        for lang_code in languages_to_save:
            self._rewrite_language_file(lemma, lang_code)

        # Save verification status
        self._save_lemma_verification(lemma)

    def _get_lemma_dir_path(self, lemma: models.Lemma) -> Path:
        """Get the directory path for a lemma's language files.

        Args:
            lemma: The lemma

        Returns:
            Path to the directory containing language files
        """
        pos_type = lemma.pos_type.lower()
        pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "misc"

        # Map POS types to directory names
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

        dir_name = type_to_dir.get(pos_type, "misc")
        return self.data_dir / "lemmas" / dir_name / pos_subtype

    def _get_language_file_path(self, lemma: models.Lemma, lang_code: str) -> Path:
        """Get the JSONL file path for a specific language.

        Args:
            lemma: The lemma
            lang_code: Language code (e.g., "en", "zh", "fr")

        Returns:
            Path to the language-specific JSONL file
        """
        lemma_dir = self._get_lemma_dir_path(lemma)
        return lemma_dir / f"{lang_code}.jsonl"

    def _rewrite_base_file(self, lemma: models.Lemma) -> None:
        """Rewrite the base.jsonl file with all lemmas for that POS/subtype.

        Args:
            lemma: A lemma in the POS/subtype group being rewritten
        """
        # Get the directory for this POS/subtype
        lemma_dir = self._get_lemma_dir_path(lemma)
        file_path = lemma_dir / "base.jsonl"

        # Collect all lemmas that belong to this POS/subtype
        lemmas_for_file = []
        for lem in self.lemmas.values():
            if self._get_lemma_dir_path(lem) == lemma_dir:
                lemmas_for_file.append(lem)

        # Write atomically
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for lem in lemmas_for_file:
                # Extract base concept data
                base_data = self._extract_base_data(lem)

                if base_data:
                    tmp_file.write(json.dumps(base_data, ensure_ascii=False) + "\n")

            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        # Atomic rename
        os.replace(tmp_file.name, file_path)

    def _extract_base_data(self, lemma: models.Lemma) -> Dict[str, Any]:
        """Extract base concept data from a lemma for base.jsonl.

        Args:
            lemma: The lemma

        Returns:
            Dictionary with base concept data
        """
        data: Dict[str, Any] = {
            "guid": lemma.guid,
            "pos_type": lemma.pos_type,
            "pos_subtype": lemma.pos_subtype,
            "concept_label": lemma.concept_label,
            "concept_definition": lemma.concept_definition,
        }

        # Translations dict (all languages including English)
        # Build from lemma.translations, falling back to lemma_text for English
        translations: Dict[str, str] = {}
        if lemma.translations:
            translations.update(lemma.translations)
        # Backward compatibility: use lemma_text for English if not in translations
        if "en" not in translations and lemma.lemma_text:
            translations["en"] = lemma.lemma_text
        if translations:
            data["translations"] = translations

        # Optional fields
        if lemma.difficulty_level is not None:
            data["difficulty_level"] = lemma.difficulty_level

        # Difficulty overrides per language (e.g., {"en": -1} to exclude from English)
        if lemma.difficulty_overrides:
            data["difficulty_overrides"] = lemma.difficulty_overrides

        # Translation disambiguations per language (e.g., {"lt": "medžiaga"})
        if lemma.translation_disambiguations:
            data["translation_disambiguations"] = lemma.translation_disambiguations

        # Emoji representations of the concept (e.g. ["🐕"] for dog)
        if lemma.emoji:
            data["emoji"] = list(lemma.emoji)

        if lemma.notes:
            data["notes"] = lemma.notes

        if lemma.lexical_gap_reason:
            data["lexical_gap_reason"] = lemma.lexical_gap_reason

        # Note: added_at is not exported (Git handles versioning)

        return data

    def _rewrite_language_file(self, lemma: models.Lemma, lang_code: str) -> None:
        """Rewrite a language-specific JSONL file with all lemmas for that POS/subtype/language.

        Args:
            lemma: A lemma in the POS/subtype group being rewritten
            lang_code: The language code to rewrite
        """
        # Get the directory for this POS/subtype
        lemma_dir = self._get_lemma_dir_path(lemma)
        file_path = lemma_dir / f"{lang_code}.jsonl"

        # Collect all lemmas that belong to this POS/subtype
        lemmas_for_file = []
        for lem in self.lemmas.values():
            if self._get_lemma_dir_path(lem) == lemma_dir:
                lemmas_for_file.append(lem)

        # Write atomically
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for lem in lemmas_for_file:
                # Extract language-specific data
                lang_data = self._extract_language_data(lem, lang_code)

                # Only write if there's data for this language
                if lang_data:
                    tmp_file.write(json.dumps(lang_data, ensure_ascii=False) + "\n")

            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        # Atomic rename
        os.replace(tmp_file.name, file_path)

    def _extract_language_data(
        self, lemma: models.Lemma, lang_code: str
    ) -> Optional[Dict[str, Any]]:
        """Extract language-specific data from a lemma.

        Note: Translation and difficulty_overrides are now stored in base.jsonl.
        Per-language files contain: derivative_forms, base_form (if no derivative
        has is_base_form=true), audio_hashes, grammar_facts, definition_text (all languages),
        and English-only fields (tags, disambiguation, confidence).

        Args:
            lemma: The lemma
            lang_code: Language code

        Returns:
            Dictionary with language-specific data, or None if no data for this language
        """
        data: Dict[str, Any] = {"guid": lemma.guid}
        has_data = False

        # Derivative forms for this language
        has_base_form_in_derivatives = False
        if lang_code in lemma.derivative_forms:
            data["derivative_forms"] = lemma.derivative_forms[lang_code]
            has_data = True
            # Check if any derivative form has is_base_form=true
            for form_data in lemma.derivative_forms[lang_code].values():
                if isinstance(form_data, dict) and form_data.get("is_base_form"):
                    has_base_form_in_derivatives = True
                    break

        # base_form: Only include if there's no derivative_form with is_base_form=true
        # This provides form/ipa/phonetic data for the base word when derivatives don't
        if not has_base_form_in_derivatives:
            if lang_code in lemma.base_forms:
                data["base_form"] = lemma.base_forms[lang_code]
                has_data = True

        # Alternate spellings for this language, each with its own paradigm
        if lemma.variants.get(lang_code):
            data["variants"] = lemma.variants[lang_code]
            has_data = True

        # Audio hashes for this language
        if lang_code in lemma.audio_hashes:
            data["audio_hashes"] = lemma.audio_hashes[lang_code]
            has_data = True

        # Note: difficulty_overrides now stored in base.jsonl

        # Extract grammar facts for this language
        lang_grammar_facts = [
            fact for fact in lemma.grammar_facts if fact.get("language_code") == lang_code
        ]
        if lang_grammar_facts:
            data["grammar_facts"] = lang_grammar_facts
            has_data = True

        # Definition text for this language (all languages can have definitions)
        if lang_code in lemma.definitions:
            data["definition_text"] = lemma.definitions[lang_code]
            has_data = True
        elif lang_code == "en" and lemma.definition_text:
            # Backward compatibility: use definition_text for English
            data["definition_text"] = lemma.definition_text
            has_data = True

        translation_pronunciation = lemma.translation_pronunciations.get(lang_code)
        if translation_pronunciation:
            ipa_value = translation_pronunciation.get("ipa_pronunciation")
            phonetic_value = translation_pronunciation.get("phonetic_pronunciation")
            if ipa_value:
                data["ipa_pronunciation"] = ipa_value
                has_data = True
            if phonetic_value:
                data["phonetic_pronunciation"] = phonetic_value
                has_data = True

        # Translation disambiguation (any language)
        translation_disambig = lemma.translation_disambiguations.get(lang_code)
        if translation_disambig:
            data["translation_disambiguation"] = translation_disambig
            has_data = True

        # English-only fields
        if lang_code == "en":
            # Note: frequency_rank is development-only and not exported

            if lemma.tags:
                data["tags"] = lemma.tags
                has_data = True

            if lemma.disambiguation:
                data["disambiguation"] = lemma.disambiguation
                has_data = True

            if lemma.confidence is not None and lemma.confidence != 0.0:
                data["confidence"] = lemma.confidence
                has_data = True

            # Note: verified is now stored in verifications.jsonl
            # Note: updated_at is not exported (Git handles versioning)

        return data if has_data else None

    def save_sentence(self, sentence: models.Sentence) -> None:
        """Save a sentence to disk.

        Args:
            sentence: The sentence to save
        """
        # Ensure sentence has ID
        if sentence.id is None:
            sentence.id = self._next_sentence_id
            self._next_sentence_id += 1

        # Update in-memory storage
        if sentence.guid:
            self.sentences[sentence.guid] = sentence
        self.sentences_by_id[sentence.id] = sentence

        # Rewrite sentences file
        self._rewrite_sentences_file(sentence)

        # Save verification status
        self._save_sentence_verification(sentence)

    def _get_sentence_shard_path(self, sentence: models.Sentence) -> Path:
        """Get the shard file path for a sentence.

        Sentences are sharded by:
        - pattern/{pattern_id}.jsonl for BUIVOLAS pattern sentences (source_filename starts with "pattern:")
        - group/{source_filename}.jsonl for ZVIRDLIS grouped sentences and other sourced sentences
        - misc/misc.jsonl for sentences with no source

        Args:
            sentence: The sentence

        Returns:
            Path to the sentence shard file
        """
        if sentence.source_filename and sentence.source_filename.startswith("pattern:"):
            # Pattern sentence (BUIVOLAS) - extract pattern_id from "pattern:{pattern_id}"
            pattern_id = sentence.source_filename[8:]  # Remove "pattern:" prefix
            shard_dir = self.data_dir / "sentences" / "pattern"
            shard_file = f"{pattern_id}.jsonl"
        elif sentence.source_filename:
            # Grouped sentence (ZVIRDLIS) or other sourced sentence
            shard_dir = self.data_dir / "sentences" / "group"
            shard_file = f"{sentence.source_filename}.jsonl"
        else:
            # Fallback to misc if no source
            shard_dir = self.data_dir / "sentences" / "misc"
            shard_file = "misc.jsonl"

        return shard_dir / shard_file

    def _rewrite_sentences_file(self, sentence: models.Sentence) -> None:
        """Rewrite the sentence shard file containing this sentence."""
        file_path = self._get_sentence_shard_path(sentence)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect all sentences that belong to this shard
        sentences_for_shard = []
        for sent in self.sentences.values():
            if self._get_sentence_shard_path(sent) == file_path:
                sentences_for_shard.append(sent)

        # Write atomically
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for sent in sentences_for_shard:
                json_data = sent.to_dict()
                tmp_file.write(json.dumps(json_data, ensure_ascii=False) + "\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        os.replace(tmp_file.name, file_path)

    def append_audio_review(self, review: models.AudioQualityReview) -> None:
        """Append an audio review to the log.

        Args:
            review: The audio review to append
        """
        if review.id is None:
            review.id = self._next_audio_review_id
            self._next_audio_review_id += 1

        self.audio_reviews.append(review)

        # Append to file
        file_path = self.data_dir / "audio_reviews" / "audio_quality_reviews.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "a", encoding="utf-8") as f:
            json_data = review.to_dict()
            f.write(json.dumps(json_data, ensure_ascii=False) + "\n")

    def append_operation_log(self, log: models.OperationLog) -> None:
        """Append an operation log entry.

        Args:
            log: The operation log to append
        """
        if log.id is None:
            log.id = self._next_operation_log_id
            self._next_operation_log_id += 1

        self.operation_logs.append(log)

        # Append to file
        file_path = self.data_dir / "operation_logs" / "operation_log.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "a", encoding="utf-8") as f:
            json_data = log.to_dict()
            f.write(json.dumps(json_data, ensure_ascii=False) + "\n")

    def append_tombstone(self, tombstone: models.GuidTombstone) -> None:
        """Append a GUID tombstone entry.

        Args:
            tombstone: The tombstone to append
        """
        if tombstone.id is None:
            tombstone.id = self._next_tombstone_id
            self._next_tombstone_id += 1

        self.tombstones.append(tombstone)

        # Append to file
        file_path = self.data_dir / "tombstones" / "guid_tombstones.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "a", encoding="utf-8") as f:
            json_data = tombstone.to_dict()
            f.write(json.dumps(json_data, ensure_ascii=False) + "\n")

    def delete_lemma(self, lemma: models.Lemma) -> None:
        """Delete a lemma from storage.

        Args:
            lemma: The lemma to delete
        """
        # Collect languages before deleting
        # Note: difficulty_overrides are in base.jsonl, not per-language files
        languages_to_update = {"en"}
        languages_to_update.update(lemma.derivative_forms.keys())
        languages_to_update.update(lemma.base_forms.keys())
        languages_to_update.update(lemma.audio_hashes.keys())
        languages_to_update.update(lemma.definitions.keys())
        languages_to_update.update(lemma.variants.keys())

        # Remove from in-memory storage
        if lemma.guid and lemma.guid in self.lemmas:
            del self.lemmas[lemma.guid]
        if lemma.id and lemma.id in self.lemmas_by_id:
            del self.lemmas_by_id[lemma.id]

        # Rewrite base.jsonl (to remove this lemma's entry)
        self._rewrite_base_file(lemma)

        # Rewrite all affected language files
        for lang_code in languages_to_update:
            self._rewrite_language_file(lemma, lang_code)

    def delete_sentence(self, sentence: models.Sentence) -> None:
        """Delete a sentence from storage.

        Args:
            sentence: The sentence to delete
        """
        # Remove from in-memory storage
        if sentence.guid and sentence.guid in self.sentences:
            del self.sentences[sentence.guid]
        if sentence.id and sentence.id in self.sentences_by_id:
            del self.sentences_by_id[sentence.id]

        # Rewrite file
        self._rewrite_sentences_file(sentence)

    def _save_lemma_verification(self, lemma: models.Lemma) -> None:
        """Save lemma verification status to verifications/lemmas.jsonl.

        Args:
            lemma: The lemma whose verification to save
        """
        if not lemma.guid:
            return

        # Update in-memory verification
        verification = models.LemmaVerification(guid=lemma.guid, verified=lemma.verified)
        self.lemma_verifications[lemma.guid] = verification

        # Rewrite entire verifications file (small file, simple approach)
        file_path = self.data_dir / "verifications" / "lemmas.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for verif in self.lemma_verifications.values():
                if verif.verified:  # Only write verified=true entries
                    json_data = verif.to_dict()
                    tmp_file.write(json.dumps(json_data, ensure_ascii=False) + "\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        os.replace(tmp_file.name, file_path)

    def _save_sentence_verification(self, sentence: models.Sentence) -> None:
        """Save sentence verification status to verifications/sentences.jsonl.

        Args:
            sentence: The sentence whose verification to save
        """
        if not sentence.guid:
            return

        # Update in-memory verification
        verification = models.SentenceVerification(guid=sentence.guid, verified=sentence.verified)
        self.sentence_verifications[sentence.guid] = verification

        # Rewrite entire verifications file (small file, simple approach)
        file_path = self.data_dir / "verifications" / "sentences.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for verif in self.sentence_verifications.values():
                if verif.verified:  # Only write verified=true entries
                    json_data = verif.to_dict()
                    tmp_file.write(json.dumps(json_data, ensure_ascii=False) + "\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        os.replace(tmp_file.name, file_path)

    def create_session(self) -> BaseSession:
        """Create a new JSONL session.

        Returns:
            A new JSONLSession instance
        """
        return JSONLSession(self)

    def close(self) -> None:
        """Close the storage backend."""
        # JSONL backend doesn't need explicit cleanup
        pass
