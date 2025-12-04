"""JSONL storage backend implementation."""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
from collections import defaultdict

from wordfreq.storage.backend.base import BaseStorage, BaseSession
from wordfreq.storage.backend.jsonl.session import JSONLSession
from wordfreq.storage.backend.jsonl import models


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
        directories = [
            self.data_dir / "lemmas" / "nouns",
            self.data_dir / "lemmas" / "verbs",
            self.data_dir / "lemmas" / "adjectives",
            self.data_dir / "lemmas" / "adverbs",
            self.data_dir / "lemmas" / "pronouns",
            self.data_dir / "lemmas" / "prepositions",
            self.data_dir / "lemmas" / "conjunctions",
            self.data_dir / "lemmas" / "interjections",
            self.data_dir / "lemmas" / "numerals",
            self.data_dir / "lemmas" / "particles",
            self.data_dir / "sentences",
            self.data_dir / "audio_reviews",
            self.data_dir / "operation_logs",
            self.data_dir / "tombstones",
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

    def _load_lemmas(self) -> None:
        """Load all lemma files from disk."""
        lemmas_dir = self.data_dir / "lemmas"
        if not lemmas_dir.exists():
            return

        for jsonl_file in lemmas_dir.rglob("*.jsonl"):
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        lemma = models.Lemma.from_dict(data)

                        # Assign ID if not present
                        if lemma.id is None:
                            lemma.id = self._next_lemma_id
                            self._next_lemma_id += 1
                        else:
                            self._next_lemma_id = max(self._next_lemma_id, lemma.id + 1)

                        # Store by guid and id
                        if lemma.guid:
                            self.lemmas[lemma.guid] = lemma
                        self.lemmas_by_id[lemma.id] = lemma

            except Exception as e:
                print(f"Error loading {jsonl_file}: {e}")

    def _load_sentences(self) -> None:
        """Load all sentence files from disk."""
        sentences_file = self.data_dir / "sentences" / "sentences.jsonl"
        if not sentences_file.exists():
            return

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
            print(f"Error loading sentences: {e}")

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
                        self._next_audio_review_id = max(
                            self._next_audio_review_id, review.id + 1
                        )

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

        # Determine file path based on pos_type
        file_path = self._get_lemma_file_path(lemma)

        # Write to file (rewrite entire file)
        self._rewrite_lemma_file(file_path)

    def _get_lemma_file_path(self, lemma: models.Lemma) -> Path:
        """Get the JSONL file path for a lemma.

        Args:
            lemma: The lemma

        Returns:
            Path to the JSONL file
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
        file_name = f"{pos_subtype}.jsonl"

        return self.data_dir / "lemmas" / dir_name / file_name

    def _rewrite_lemma_file(self, file_path: Path) -> None:
        """Rewrite a lemma JSONL file with all lemmas for that file.

        Args:
            file_path: Path to the JSONL file
        """
        # Collect all lemmas that belong to this file
        lemmas_for_file = []
        for lemma in self.lemmas.values():
            if self._get_lemma_file_path(lemma) == file_path:
                lemmas_for_file.append(lemma)

        # Write atomically
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for lemma in lemmas_for_file:
                json_data = lemma.to_dict()
                tmp_file.write(json.dumps(json_data, ensure_ascii=False) + "\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        # Atomic rename
        os.replace(tmp_file.name, file_path)

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
        self._rewrite_sentences_file()

    def _rewrite_sentences_file(self) -> None:
        """Rewrite the sentences JSONL file."""
        file_path = self.data_dir / "sentences" / "sentences.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            for sentence in self.sentences.values():
                json_data = sentence.to_dict()
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
        # Remove from in-memory storage
        if lemma.guid and lemma.guid in self.lemmas:
            del self.lemmas[lemma.guid]
        if lemma.id and lemma.id in self.lemmas_by_id:
            del self.lemmas_by_id[lemma.id]

        # Rewrite file
        file_path = self._get_lemma_file_path(lemma)
        self._rewrite_lemma_file(file_path)

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
        self._rewrite_sentences_file()

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
