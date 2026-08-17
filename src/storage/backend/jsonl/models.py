"""Dataclass models for JSONL storage backend.

These dataclasses mirror the SQLAlchemy models but are designed for
serialization to/from JSONL format.
"""

import datetime
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional


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
    if isinstance(value, datetime.datetime):
        return value
    return None


@dataclass
class BaseConcept:
    """JSONL model for base concept (stored in base.jsonl).

    This represents the core concept independent of any specific language.
    The translations dict holds the canonical translation for each language.
    """

    # Primary identifier
    guid: str = ""

    # Part of speech classification
    pos_type: str = ""
    pos_subtype: Optional[str] = None

    # Concept identification (language-neutral, but likely English)
    concept_label: str = ""
    concept_definition: str = ""

    # Translations for all languages: {"en": "dog", "lt": "šuo", "zh": "狗"}
    translations: Dict[str, str] = field(default_factory=dict)

    # Base difficulty level (can be overridden per-language)
    difficulty_level: Optional[int] = None

    # Editorial notes about the concept (singleton for now)
    notes: Optional[str] = None

    # Concept-level explanation for why historical/classical languages may not
    # have a conventional native lexical item for this lemma.
    lexical_gap_reason: Optional[str] = None

    # Runtime field (not exported to JSONL - Git handles versioning)
    added_at: Optional[datetime.datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        # Remove runtime fields - Git handles versioning
        data.pop("added_at", None)
        # Only include translations if non-empty
        if not data.get("translations"):
            data.pop("translations", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BaseConcept":
        """Create from dictionary (JSONL deserialization)."""
        # Handle deprecated added_at for backward compatibility
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        else:
            data.setdefault("added_at", None)
        # Ensure translations dict exists
        data.setdefault("translations", {})
        return cls(**data)


@dataclass
class Lemma:
    """JSONL model for lemmas.

    This class represents the merged view of a lemma combining:
    - Base concept data from base.jsonl (including translations and difficulty_overrides)
    - Language-specific data from {lang}.jsonl files (derivative_forms, definition_text, etc.)

    File structure:
    - base.jsonl: guid, pos_type, pos_subtype, concept_label, concept_definition,
                  translations (dict), difficulty_level, difficulty_overrides (dict), notes
    - {lang}.jsonl: guid, derivative_forms, base_form (if no derivative has is_base_form),
                    audio_hashes, grammar_facts, definition_text (all languages),
                    tags/disambiguation/confidence (English only)
    """

    # Primary key for JSONL is guid
    guid: Optional[str] = None

    # ID for compatibility with code that expects it (not stored in JSONL)
    id: Optional[int] = None

    # Core fields from base.jsonl
    pos_type: str = ""
    pos_subtype: Optional[str] = None
    concept_label: str = ""  # From base.jsonl
    concept_definition: str = ""  # From base.jsonl

    # Legacy fields for backward compatibility during migration
    lemma_text: str = ""  # Deprecated: use translations['en'] instead
    definition_text: str = ""  # Deprecated: language-specific

    # Dictionary generation fields
    difficulty_level: Optional[int] = None  # From base.jsonl, can be overridden
    tags: Optional[str] = None  # JSON string

    # Development-only field (not exported to JSONL)
    frequency_rank: Optional[int] = None

    # Legacy translation fields (kept for backward compatibility)
    chinese_translation: Optional[str] = None
    french_translation: Optional[str] = None
    korean_translation: Optional[str] = None
    swahili_translation: Optional[str] = None
    lithuanian_translation: Optional[str] = None
    vietnamese_translation: Optional[str] = None

    # Disambiguation
    disambiguation: Optional[str] = None

    # Emoji representation(s) of the concept. Each entry is a dict
    #   {"type": "unicode", "value": "🐕"}  — a real Unicode emoji
    #   {"type": "image",   "value": "badger.svg"} — a custom static image
    #     (path relative to data/release/emoji/)
    # Lives in base.jsonl alongside translations; not a per-language field.
    emoji: List[Dict[str, str]] = field(default_factory=list)

    # Metadata
    confidence: float = 0.0
    notes: Optional[str] = None  # From base.jsonl
    lexical_gap_reason: Optional[str] = None  # From base.jsonl

    # Wikidata Q-id of the paired concept (e.g. "Q89" for apple). From
    # base.jsonl; used to populate concept_lemma_links when loading data/release
    # so the lemma<->concept pairing is visible in JSONL/golden/scholar mode.
    qid: Optional[str] = None

    # Runtime/internal fields (not exported to JSONL)
    verified: bool = False  # Moved to verifications.jsonl
    added_at: Optional[datetime.datetime] = None  # Git handles versioning
    updated_at: Optional[datetime.datetime] = None  # Git handles versioning

    # Nested relationships (stored as dicts in JSONL)
    # translations: Now stored in base.jsonl, still populated here at runtime
    translations: Dict[str, str] = field(default_factory=dict)  # lang_code -> translation
    # definitions: Per-language definitions stored in {lang}.jsonl files
    definitions: Dict[str, str] = field(default_factory=dict)  # lang_code -> definition
    difficulty_overrides: Dict[str, int] = field(default_factory=dict)  # lang_code -> level
    derivative_forms: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # lang_code -> {form_name -> form_data}
    # synonyms: Stored as a list because the same grammatical_form (e.g. "synonym")
    # can repeat. Each entry is a dict with grammatical_form, form, optional
    # ipa/phonetic. Loaded from the top-level "synonyms" array in {lang}.jsonl.
    synonyms: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )  # lang_code -> [{grammatical_form, form, ipa?, phonetic?}, ...]
    # base_forms: Used when no derivative_form has is_base_form=true for that language
    # Contains {form: str, ipa: str, phonetic: str} per language
    base_forms: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # lang_code -> {form, ipa, phonetic}
    # variants: Alternate spellings of the same lexeme ("grey" for "gray"), each
    # carrying its own full paradigm. Kept separate from derivative_forms and
    # synonyms because a variant is neither an inflection nor a different word;
    # loaded from the top-level "variants" array in {lang}.jsonl.
    variants: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )  # lang_code -> [{kind, key, forms: [{grammatical_form, text, ...}]}, ...]
    grammar_facts: List[Dict[str, Any]] = field(default_factory=list)
    audio_hashes: Dict[str, Dict[str, str]] = field(
        default_factory=dict
    )  # lang_code -> {voice -> hash}
    translation_pronunciations: Dict[str, Dict[str, Optional[str]]] = field(
        default_factory=dict
    )  # lang_code -> {"ipa_pronunciation": str|None, "phonetic_pronunciation": str|None}
    translation_disambiguations: Dict[str, str] = field(
        default_factory=dict
    )  # lang_code -> disambiguation string
    # translation_metadata: per-language translation_status / translation_status_note
    # from base.jsonl and the grouped translation files (secondary.jsonl,
    # ancient.jsonl). Kept separate from the flat translations map so the release
    # shape round-trips unchanged.
    translation_metadata: Dict[str, Dict[str, str]] = field(
        default_factory=dict
    )  # lang_code -> {translation_status, translation_status_note}

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)

        # Remove runtime/internal fields not meant for JSONL export
        data.pop("id", None)
        data.pop("verified", None)  # Now in verifications.jsonl
        data.pop("added_at", None)  # Git handles versioning
        data.pop("updated_at", None)  # Git handles versioning
        data.pop("frequency_rank", None)  # Development only

        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Lemma":
        """Create from dictionary (JSONL deserialization)."""
        # Handle deprecated datetime fields (for backward compatibility with old exports)
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        if "updated_at" in data and data["updated_at"]:
            data["updated_at"] = datetime.datetime.fromisoformat(data["updated_at"])

        # Ensure default values for nested structures
        data.setdefault("translations", {})
        data.setdefault("definitions", {})
        data.setdefault("difficulty_overrides", {})
        data.setdefault("derivative_forms", {})
        data.setdefault("synonyms", {})
        data.setdefault("base_forms", {})
        data.setdefault("variants", {})
        data.setdefault("grammar_facts", [])
        data.setdefault("audio_hashes", {})
        data.setdefault("translation_pronunciations", {})
        data.setdefault("translation_disambiguations", {})
        data.setdefault("emoji", [])

        # Set defaults for runtime fields that won't be in JSONL
        data.setdefault("verified", False)
        data.setdefault("frequency_rank", None)

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
    ipa_pronunciation: Optional[str] = None
    phonetic_pronunciation: Optional[str] = None
    sort_key: Optional[str] = None
    disambiguation: Optional[str] = None
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
    """JSONL model for sentences."""

    id: Optional[int] = None
    guid: Optional[str] = None  # Used as primary identifier in JSONL

    # Metadata
    pattern_type: Optional[str] = None
    tense: Optional[str] = None
    minimum_level: Optional[int] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None

    # Runtime/internal fields (not exported to JSONL)
    verified: bool = False  # Moved to verifications.jsonl
    added_at: Optional[datetime.datetime] = None  # Git handles versioning
    updated_at: Optional[datetime.datetime] = None  # Git handles versioning

    # Nested relationships
    translations: Dict[str, str] = field(default_factory=dict)  # lang_code -> text
    words: List[Dict[str, Any]] = field(default_factory=list)  # List of SentenceWord data
    word_hints: List[Dict[str, Any]] = field(default_factory=list)  # List of word hint data

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        # Remove runtime/internal fields not meant for JSONL export
        data.pop("id", None)
        data.pop("verified", None)  # Now in verifications.jsonl
        data.pop("added_at", None)  # Git handles versioning
        data.pop("updated_at", None)  # Git handles versioning
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Sentence":
        """Create from dictionary (JSONL deserialization)."""
        # Handle deprecated datetime fields (for backward compatibility with old exports)
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        if "updated_at" in data and data["updated_at"]:
            data["updated_at"] = datetime.datetime.fromisoformat(data["updated_at"])

        data.setdefault("translations", {})
        data.setdefault("words", [])
        data.setdefault("word_hints", [])

        # Set defaults for runtime fields that won't be in JSONL
        data.setdefault("verified", False)

        # Ignore keys that aren't dataclass fields (e.g. "audio", which is an
        # external audio manifest stored alongside the sentence but consumed
        # via AudioQualityReview rather than the Sentence model). Without this,
        # cls(**data) raises TypeError and aborts loading the entire file.
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}

        return cls(**filtered)


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
    ud_relation: Optional[str] = None
    ud_head_position: Optional[int] = None
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None

    # References
    sentence: Optional[Sentence] = None
    lemma: Optional[Lemma] = None


@dataclass
class Phrase:
    """JSONL model for phrases (fixed traveler/greeting expressions)."""

    id: Optional[int] = None
    guid: Optional[str] = None  # Used as primary identifier in JSONL

    phrase_subtype: str = ""  # e.g. "greetings", "traveler"
    concept_label: str = ""  # English concept label, e.g. "See you later"
    concept_definition: Optional[str] = None
    difficulty_level: Optional[int] = None

    # Runtime/internal fields (not exported to JSONL)
    verified: bool = False
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Nested relationships (lang_code -> text / lang_code -> {status, note})
    translations: Dict[str, str] = field(default_factory=dict)
    translation_metadata: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        data = asdict(self)
        data.pop("id", None)
        data.pop("verified", None)
        data.pop("notes", None)
        data.pop("added_at", None)
        data.pop("updated_at", None)
        return data

    @classmethod
    def from_dict(cls, data: dict, default_subtype: str = "") -> "Phrase":
        """Create from a base.jsonl record.

        Args:
            data: The parsed JSON object.
            default_subtype: phrase_subtype to use when the record omits it
                (typically the parent directory name).
        """
        if "added_at" in data and data["added_at"]:
            data["added_at"] = datetime.datetime.fromisoformat(data["added_at"])
        if "updated_at" in data and data["updated_at"]:
            data["updated_at"] = datetime.datetime.fromisoformat(data["updated_at"])

        data.setdefault("phrase_subtype", default_subtype)
        data.setdefault("translations", {})
        data.setdefault("translation_metadata", {})
        data.setdefault("verified", False)

        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class PhraseTranslation:
    """JSONL model for phrase translations.

    Note: In the JSONL backend these are stored nested in Phrase.translations;
    this dataclass exists to mirror the SQLAlchemy model for materialization.
    """

    id: Optional[int] = None
    phrase_id: Optional[int] = None
    language_code: str = ""
    translation: str = ""
    translation_status: Optional[str] = None
    translation_status_note: Optional[str] = None
    verified: bool = False
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Reference to parent phrase
    phrase: Optional[Phrase] = None


@dataclass
class LemmaRelationGroup:
    """JSONL model for lemma relation groups.

    In JSONL release files, relation groups are stored as:
    data/release/lemma_relations/{relation_type}/{subtype}.jsonl
    Each line: {"concept": "circle", "members": ["A03_001", "N37_001"]}
    """

    id: Optional[int] = None
    relation_type: str = ""
    concept_label: str = ""
    notes: Optional[str] = None
    added_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    # Member GUIDs (resolved to LemmaRelationMember objects at query time)
    member_guids: List[str] = field(default_factory=list)


@dataclass
class LemmaRelationMember:
    """JSONL model for lemma relation members.

    Note: In JSONL backend, these are derived from LemmaRelationGroup.member_guids.
    """

    id: Optional[int] = None
    group_id: Optional[int] = None
    lemma_id: Optional[int] = None
    added_at: Optional[datetime.datetime] = None

    # References (populated at runtime)
    group: Optional["LemmaRelationGroup"] = None
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


@dataclass
class LemmaVerification:
    """JSONL model for lemma verifications (stored in verifications/lemmas.jsonl)."""

    guid: str = ""
    verified: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LemmaVerification":
        """Create from dictionary (JSONL deserialization)."""
        return cls(**data)


@dataclass
class SentenceVerification:
    """JSONL model for sentence verifications (stored in verifications/sentences.jsonl)."""

    guid: str = ""
    verified: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SentenceVerification":
        """Create from dictionary (JSONL deserialization)."""
        return cls(**data)


# Model registry for dynamic lookup
MODEL_REGISTRY = {
    "BaseConcept": BaseConcept,
    "Lemma": Lemma,
    "LemmaTranslation": LemmaTranslation,
    "LemmaDifficultyOverride": LemmaDifficultyOverride,
    "DerivativeForm": DerivativeForm,
    "GrammarFact": GrammarFact,
    "Sentence": Sentence,
    "SentenceTranslation": SentenceTranslation,
    "SentenceWord": SentenceWord,
    "LemmaRelationGroup": LemmaRelationGroup,
    "LemmaRelationMember": LemmaRelationMember,
    "AudioQualityReview": AudioQualityReview,
    "OperationLog": OperationLog,
    "GuidTombstone": GuidTombstone,
    "LemmaVerification": LemmaVerification,
    "SentenceVerification": SentenceVerification,
}
