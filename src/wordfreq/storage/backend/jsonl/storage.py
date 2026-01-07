"""JSONL storage backend implementation."""

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from wordfreq.storage.backend.base import BaseSession, BaseStorage
from wordfreq.storage.backend.jsonl import models
from wordfreq.storage.backend.jsonl.session import JSONLSession


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
        self.audio_reviews: List[models.AudioQualityReview] = []
        self.operation_logs: List[models.OperationLog] = []
        self.tombstones: List[models.GuidTombstone] = []
        self.lemma_verifications: Dict[str, models.LemmaVerification] = {}  # guid -> verification
        self.sentence_verifications: Dict[str, models.SentenceVerification] = (
            {}
        )  # guid -> verification

        # ID counters for new objects
        self._next_lemma_id = 1
        self._next_sentence_id = 1
        self._next_audio_review_id = 1
        self._next_operation_log_id = 1
        self._next_tombstone_id = 1

        # Track if data is loaded
        self._loaded = False

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
        self._load_audio_reviews()
        self._load_operation_logs()
        self._load_tombstones()
        self._load_verifications()

    def _load_lemmas(self) -> None:
        """Load all lemma files from disk.

        New structure: lemmas are organized by POS type/subtype with per-language files:
        lemmas/nouns/animal/base.jsonl (concept definition)
        lemmas/nouns/animal/en.jsonl (English-specific data)
        lemmas/nouns/animal/zh.jsonl (Chinese data)
        etc.
        """
        lemmas_dir = self.data_dir / "lemmas"
        if not lemmas_dir.exists():
            return

        # First pass: Load all base.jsonl files (concept definition)
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

                        # Populate lemma_text and definition_text from concept fields
                        # This ensures compatibility when no en.jsonl exists
                        lemma.lemma_text = lemma.concept_label
                        lemma.definition_text = lemma.concept_definition

                        lemma.difficulty_level = data.get("difficulty_level")
                        lemma.notes = data.get("notes")
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

        # Second pass: Load all language files (including en.jsonl) and merge data
        for lang_file in lemmas_dir.rglob("*.jsonl"):
            # Skip base.jsonl files (already loaded)
            if lang_file.name == "base.jsonl":
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

                        # Handle translation field (now used for all languages including English)
                        if "translation" in data:
                            lemma.translations[lang_code] = data["translation"]

                        # Backward compatibility: also accept lemma_text for English
                        if lang_code == "en" and "lemma_text" in data:
                            lemma.lemma_text = data["lemma_text"]
                            if "lemma_text" in data and "translation" not in data:
                                lemma.translations["en"] = data["lemma_text"]

                        # Language-specific fields
                        if "definition_text" in data:
                            # Store in lemma for backward compatibility
                            if lang_code == "en":
                                lemma.definition_text = data["definition_text"]

                        if "frequency_rank" in data:
                            if lang_code == "en":
                                lemma.frequency_rank = data["frequency_rank"]

                        if "tags" in data:
                            if lang_code == "en":
                                lemma.tags = data["tags"]

                        if "disambiguation" in data:
                            if lang_code == "en":
                                lemma.disambiguation = data["disambiguation"]

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

                        if "audio_hashes" in data:
                            lemma.audio_hashes[lang_code] = data["audio_hashes"]

                        if "difficulty_level" in data:
                            # This is a language-specific override
                            lemma.difficulty_overrides[lang_code] = data["difficulty_level"]

                        if "grammar_facts" in data:
                            # Merge grammar facts with language_code tag
                            for fact in data["grammar_facts"]:
                                fact["language_code"] = lang_code
                                lemma.grammar_facts.append(fact)

            except Exception as e:
                print(f"Error loading {lang_file}: {e}")

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
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        sentence = models.Sentence.from_dict(data)

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
                        verification = models.SentenceVerification.from_dict(data)
                        self.sentence_verifications[verification.guid] = verification

                        # Apply verification status to sentence if loaded
                        if verification.guid in self.sentences:
                            self.sentences[verification.guid].verified = verification.verified

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

        # Save base.jsonl file
        self._rewrite_base_file(lemma)

        # Determine which languages are present in this lemma
        languages_to_save = set()
        languages_to_save.update(lemma.translations.keys())
        languages_to_save.update(lemma.derivative_forms.keys())
        languages_to_save.update(lemma.audio_hashes.keys())
        languages_to_save.update(lemma.difficulty_overrides.keys())

        # Extract grammar_facts languages
        for fact in lemma.grammar_facts:
            if "language_code" in fact:
                languages_to_save.add(fact["language_code"])

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

    def _extract_base_data(self, lemma: models.Lemma) -> dict:
        """Extract base concept data from a lemma for base.jsonl.

        Args:
            lemma: The lemma

        Returns:
            Dictionary with base concept data
        """
        data = {
            "guid": lemma.guid,
            "pos_type": lemma.pos_type,
            "pos_subtype": lemma.pos_subtype,
            "concept_label": lemma.concept_label,
            "concept_definition": lemma.concept_definition,
        }

        # Optional fields
        if lemma.difficulty_level is not None:
            data["difficulty_level"] = lemma.difficulty_level

        if lemma.notes:
            data["notes"] = lemma.notes

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

    def _extract_language_data(self, lemma: models.Lemma, lang_code: str) -> Optional[dict]:
        """Extract language-specific data from a lemma.

        Args:
            lemma: The lemma
            lang_code: Language code

        Returns:
            Dictionary with language-specific data, or None if no data for this language
        """
        # All languages now use the same structure (including English)
        data = {"guid": lemma.guid}
        has_data = False

        # Translation field (now used for all languages including English)
        if lang_code in lemma.translations:
            data["translation"] = lemma.translations[lang_code]
            has_data = True
        elif lang_code == "en" and lemma.lemma_text:
            # Backward compatibility: if English translation not in dict, use lemma_text
            data["translation"] = lemma.lemma_text
            has_data = True

        # Language-specific fields (only for English currently, but could be extended)
        if lang_code == "en":
            if lemma.definition_text:
                data["definition_text"] = lemma.definition_text
                has_data = True

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

        # Derivative forms for this language
        if lang_code in lemma.derivative_forms:
            data["derivative_forms"] = lemma.derivative_forms[lang_code]
            has_data = True

        # Audio hashes for this language
        if lang_code in lemma.audio_hashes:
            data["audio_hashes"] = lemma.audio_hashes[lang_code]
            has_data = True

        # Difficulty override for this language
        if lang_code in lemma.difficulty_overrides:
            data["difficulty_level"] = lemma.difficulty_overrides[lang_code]
            has_data = True

        # Extract grammar facts for this language
        lang_grammar_facts = [
            fact for fact in lemma.grammar_facts if fact.get("language_code") == lang_code
        ]
        if lang_grammar_facts:
            data["grammar_facts"] = lang_grammar_facts
            has_data = True

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
        languages_to_update = {"en"}
        languages_to_update.update(lemma.translations.keys())
        languages_to_update.update(lemma.derivative_forms.keys())
        languages_to_update.update(lemma.audio_hashes.keys())
        languages_to_update.update(lemma.difficulty_overrides.keys())

        # Remove from in-memory storage
        if lemma.guid and lemma.guid in self.lemmas:
            del self.lemmas[lemma.guid]
        if lemma.id and lemma.id in self.lemmas_by_id:
            del self.lemmas_by_id[lemma.id]

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
