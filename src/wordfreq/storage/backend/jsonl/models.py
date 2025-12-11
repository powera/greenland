"""Dataclass models for JSONL storage backend.

These dataclasses mirror the SQLAlchemy models but are designed for
serialization to/from JSONL format.
"""

import datetime
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


def datetime_serializer(obj: Any) -> Any:
    """Serialize datetime objects to ISO format strings."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return obj


def datetime_deserializer(data: dict, field_name: str) -> Optional[datetime.datetime]:
    """Deserialize ISO format strings to datetime objects."""
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value)
    return value


@dataclass
class Lemma:
    """JSONL model for lemmas."""

    # Primary key for JSONL is guid
    guid: Optional[str] = None

    # ID for compatibility with code that expects it (not stored in JSONL)
    id: Optional[int] = None

    # Core fields
    lemma_text: str = ""
    definition_text: str = ""
    pos_type: str = ""
    pos_subtype: Optional[str] = None

    # Dictionary generation fields
    difficulty_level: Optional[int] = None
    frequency_rank: Optional[int] = None
    tags: Optional[str] = None  # JSON string

    # Legacy translation fields (kept for backward compatibility)
    chinese_translation: Optional[str] = None
    french_translation: Optional[str] = None
    korean_translation: Optional[str] = None
    swahili_translation: Optional[str] = None
    lithuanian_translation: Optional[str] = None
    vietnamese_translation: Optional[str] = None

    # Disambiguation
    disambiguation: Optional[str] = None

    # Metadata
    confidence: float = 0.0
    verified: bool = False
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Nested relationships (stored as dicts in JSONL)
    translations: Dict[str, str] = field(default_factory=dict)  # lang_code -> translation
    difficulty_overrides: Dict[str, int] = field(default_factory=dict)  # lang_code -> level
    derivative_forms: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # lang_code -> {form_name -> form_data}
    grammar_facts: List[Dict[str, Any]] = field(default_factory=list)
    audio_hashes: Dict[str, Dict[str, str]] = field(
        default_factory=dict
    )  # lang_code -> {voice -> hash}

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)

        # Remove id field - GUID is the primary key in JSONL
        data.pop("id", None)

        # Convert datetime fields
        if self.added_at:
            data["added_at"] = self.added_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Lemma":
        """Create from dictionary (JSONL deserialization)."""
        # Handle datetime fields
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        if "updated_at" in data and data["updated_at"]:
            data["updated_at"] = datetime.datetime.fromisoformat(data["updated_at"])

        # Ensure default values for nested structures
        data.setdefault("translations", {})
        data.setdefault("difficulty_overrides", {})
        data.setdefault("derivative_forms", {})
        data.setdefault("grammar_facts", [])
        data.setdefault("audio_hashes", {})

        return cls(**data)


@dataclass
class LemmaTranslation:
    """JSONL model for lemma translations.

    Note: In JSONL backend, these are stored nested in Lemma.
    This class is for compatibility with CRUD operations.
    """

    id: Optional[int] = None
    lemma_id: Optional[int] = None
    language_code: str = ""
    translation: str = ""
    verified: bool = False
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Reference to parent lemma (not stored in JSONL, populated at runtime)
    lemma: Optional[Lemma] = None


@dataclass
class LemmaDifficultyOverride:
    """JSONL model for difficulty overrides.

    Note: In JSONL backend, these are stored nested in Lemma.
    """

    id: Optional[int] = None
    lemma_id: Optional[int] = None
    language_code: str = ""
    difficulty_level: int = 0
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Reference to parent lemma
    lemma: Optional[Lemma] = None


@dataclass
class DerivativeForm:
    """JSONL model for derivative forms.

    Note: In JSONL backend, these are stored nested in Lemma.
    """

    id: Optional[int] = None
    lemma_id: Optional[int] = None
    derivative_form_text: str = ""
    word_token_id: Optional[int] = None
    language_code: str = ""
    grammatical_form: str = ""
    is_base_form: bool = False
    ipa_pronunciation: Optional[str] = None
    phonetic_pronunciation: Optional[str] = None
    verified: bool = False
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # References
    lemma: Optional[Lemma] = None
    word_token: Optional[Any] = None  # WordToken


@dataclass
class GrammarFact:
    """JSONL model for grammar facts.

    Note: In JSONL backend, these are stored nested in Lemma.
    """

    id: Optional[int] = None
    lemma_id: Optional[int] = None
    language_code: str = ""
    fact_type: str = ""
    fact_value: Optional[str] = None
    notes: Optional[str] = None
    verified: bool = False
    added_at: Optional[datetime.datetime] = None

    # Reference to parent lemma
    lemma: Optional[Lemma] = None


@dataclass
class Sentence:
    """JSONL model for sentences.

    Note: Unlike the SQLite Sentence model which stores sentence_text in SentenceTranslation,
    the JSONL model stores it directly for convenience. The primary sentence text and language
    are stored in the main fields, with translations stored in the translations dict.
    """

    id: Optional[int] = None
    guid: Optional[str] = None  # Used as primary identifier in JSONL

    # Primary sentence data (stored directly in JSONL, unlike SQLite)
    sentence_text: str = ""  # The sentence text in its primary language
    language_code: str = ""  # The primary language of this sentence (e.g., 'lt', 'fr')

    # Metadata
    pattern_type: Optional[str] = None
    tense: Optional[str] = None
    difficulty_level: Optional[int] = None  # Alias for minimum_level
    minimum_level: Optional[int] = None  # For compatibility with SQLite schema
    audio_url: Optional[str] = None
    source_filename: Optional[str] = None
    verified: bool = False
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Nested relationships
    translations: Dict[str, str] = field(default_factory=dict)  # lang_code -> text
    words: List[Dict[str, Any]] = field(default_factory=list)  # List of SentenceWord data

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        # Remove id field - GUID is the primary key in JSONL
        data.pop("id", None)
        if self.added_at:
            data["added_at"] = self.added_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Sentence":
        """Create from dictionary (JSONL deserialization)."""
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        if "updated_at" in data and data["updated_at"]:
            data["updated_at"] = datetime.datetime.fromisoformat(data["updated_at"])

        # Ensure default values
        data.setdefault("translations", {})
        data.setdefault("words", [])
        data.setdefault("sentence_text", "")
        data.setdefault("language_code", "")

        # Handle both difficulty_level and minimum_level (for compatibility)
        if "difficulty_level" in data and "minimum_level" not in data:
            data["minimum_level"] = data["difficulty_level"]
        elif "minimum_level" in data and "difficulty_level" not in data:
            data["difficulty_level"] = data["minimum_level"]

        return cls(**data)


@dataclass
class SentenceTranslation:
    """JSONL model for sentence translations.

    Note: In JSONL backend, these are stored nested in Sentence.
    """

    id: Optional[int] = None
    sentence_id: Optional[int] = None
    language_code: str = ""
    translation_text: str = ""
    verified: bool = False
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Reference to parent sentence
    sentence: Optional[Sentence] = None


@dataclass
class SentenceWord:
    """JSONL model for sentence words.

    Note: In JSONL backend, these are stored nested in Sentence.
    """

    id: Optional[int] = None
    sentence_id: Optional[int] = None
    lemma_id: Optional[int] = None
    language_code: str = ""
    position: int = 0
    word_role: str = ""
    english_text: Optional[str] = None
    target_language_text: Optional[str] = None
    grammatical_form: Optional[str] = None
    grammatical_case: Optional[str] = None
    declined_form: Optional[str] = None
    is_required_vocab: bool = True  # Whether this word is required vocabulary (default: True)
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None

    # References
    sentence: Optional[Sentence] = None
    lemma: Optional[Lemma] = None


@dataclass
class AudioQualityReview:
    """JSONL model for audio quality reviews."""

    id: Optional[int] = None
    guid: str = ""
    language_code: str = ""
    voice_name: str = ""
    grammatical_form: Optional[str] = None
    filename: str = ""
    status: str = "pending"  # pending, approved, rejected, regenerate
    quality_issues: List[str] = field(default_factory=list)
    manifest_md5: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        if self.reviewed_at:
            data["reviewed_at"] = self.reviewed_at.isoformat()
        if self.added_at:
            data["added_at"] = self.added_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AudioQualityReview":
        """Create from dictionary (JSONL deserialization)."""
        if "reviewed_at" in data and data["reviewed_at"]:
            data["reviewed_at"] = datetime.datetime.fromisoformat(data["reviewed_at"])
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])

        data.setdefault("quality_issues", [])

        return cls(**data)


@dataclass
class OperationLog:
    """JSONL model for operation logs."""

    id: Optional[int] = None
    source: str = ""
    operation_type: str = ""
    timestamp: Optional[datetime.datetime] = None
    fact: str = ""  # JSON string
    lemma_id: Optional[int] = None
    word_token_id: Optional[int] = None
    derivative_form_id: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        if self.timestamp:
            data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "OperationLog":
        """Create from dictionary (JSONL deserialization)."""
        if "timestamp" in data and data["timestamp"]:
            data["timestamp"] = datetime.datetime.fromisoformat(data["timestamp"])

        return cls(**data)


@dataclass
class GuidTombstone:
    """JSONL model for GUID tombstones."""

    id: Optional[int] = None
    guid: str = ""
    original_lemma_text: str = ""
    original_pos_type: str = ""
    original_pos_subtype: Optional[str] = None
    replacement_guid: Optional[str] = None
    lemma_id: Optional[int] = None
    reason: str = "type_change"
    notes: Optional[str] = None
    changed_by: Optional[str] = None
    tombstoned_at: Optional[datetime.datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        if self.tombstoned_at:
            data["tombstoned_at"] = self.tombstoned_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "GuidTombstone":
        """Create from dictionary (JSONL deserialization)."""
        if "tombstoned_at" in data and data["tombstoned_at"]:
            data["tombstoned_at"] = datetime.datetime.fromisoformat(data["tombstoned_at"])

        return cls(**data)


# Model registry for dynamic lookup
MODEL_REGISTRY = {
    "Lemma": Lemma,
    "LemmaTranslation": LemmaTranslation,
    "LemmaDifficultyOverride": LemmaDifficultyOverride,
    "DerivativeForm": DerivativeForm,
    "GrammarFact": GrammarFact,
    "Sentence": Sentence,
    "SentenceTranslation": SentenceTranslation,
    "SentenceWord": SentenceWord,
    "AudioQualityReview": AudioQualityReview,
    "OperationLog": OperationLog,
    "GuidTombstone": GuidTombstone,
}
