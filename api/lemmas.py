"""HTTP facade for lemma-related Barsukas endpoints.

Mirrors ``src/barsukas/routes/api/v1.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict, cast

from api._mirror import mirrored_route
from api._http import get_json, patch_json, post_json
from api.constants import API_V1_PREFIX


class SearchResult(TypedDict, total=False):
    guid: str
    lemma_text: str
    definition: str
    pos_type: str
    pos_subtype: Optional[str]
    difficulty_level: Optional[int]
    disambiguation: Optional[str]
    lexical_gap_reason: Optional[str]
    translation_absence: Dict[str, Any]
    translations: Dict[str, str]
    verified: bool


class SearchResponse(TypedDict):
    data: List[SearchResult]
    metadata: Dict[str, Any]


class TranslationMapResponse(TypedDict):
    data: Dict[str, str]
    metadata: Dict[str, Any]


class BulkTranslationMapResponse(TypedDict):
    data: Dict[str, Dict[str, str]]
    metadata: Dict[str, Any]


class TranslationAbsence(TypedDict, total=False):
    language_code: str
    is_populated: bool
    reason: str
    reason_codes: List[str]
    effective_difficulty_level: Optional[int]
    difficulty_override: Dict[str, Any]
    lexical_gap_reason: str


class TranslationMetadata(TypedDict, total=False):
    translation_status: Optional[str]
    translation_status_note: Optional[str]


class LemmaInfo(TypedDict, total=False):
    guid: str
    lemma_text: str
    definition: str
    pos_type: str
    pos_subtype: Optional[str]
    difficulty_level: Optional[int]
    verified: bool
    tags: Optional[Any]
    disambiguation: Optional[str]
    lexical_gap_reason: Optional[str]


class DerivativeFormEntry(TypedDict, total=False):
    form_text: str
    language_code: str
    grammatical_form: str
    is_base_form: bool
    ipa_pronunciation: Optional[str]
    phonetic_pronunciation: Optional[str]
    verified: bool


class GrammarFactEntry(TypedDict, total=False):
    language_code: str
    fact_type: str
    fact_value: Optional[str]
    notes: Optional[str]
    verified: bool


class PronunciationEntry(TypedDict, total=False):
    ipa: Optional[str]
    phonetic: Optional[str]


class AudioFileEntry(TypedDict, total=False):
    grammatical_form: Optional[str]
    voice_name: str
    display_voice: str
    manifest_md5: str
    audio_url: Optional[str]
    s3_prod_url: Optional[str]
    s3_staging_url: Optional[str]
    status: str


class LanguageAudioEntry(TypedDict):
    has_lemma_audio: bool
    form_audio_count: int
    audio_files: List[AudioFileEntry]


class SentenceWordInfo(TypedDict, total=False):
    position: int
    word_role: str
    english_text: Optional[str]
    target_language_text: Optional[str]
    grammatical_form: Optional[str]
    declined_form: Optional[str]
    language_code: str


class SentenceEntry(TypedDict, total=False):
    sentence_id: int
    translations: Dict[str, str]
    minimum_level: Optional[int]
    pattern_type: Optional[str]
    tense: Optional[str]
    verified: bool
    word_info: List[SentenceWordInfo]


class WordfreqCorpusEntry(TypedDict):
    total_frequency: Optional[float]
    best_rank: Optional[int]


class WordfreqLanguageEntry(TypedDict):
    corpora: Dict[str, WordfreqCorpusEntry]


class WordfreqResponse(TypedDict):
    data: Dict[str, Dict[str, WordfreqCorpusEntry]]
    metadata: Dict[str, Optional[int]]


@mirrored_route("/api/v1/search", "GET")
def search(
    query: Optional[str] = None,
    *,
    pos_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> SearchResponse:
    """Search lemmas by text/definition/translations.

    ``query`` is optional: omit it (or pass an empty string) to match all
    lemmas, subject to the ``pos_type``/``difficulty`` filters and pagination.
    """
    return cast(
        SearchResponse,
        get_json(
            f"{API_V1_PREFIX}/search",
            {
                "q": query,
                "pos_type": pos_type,
                "difficulty": difficulty,
                "limit": limit,
                "offset": offset,
            },
        ),
    )


@mirrored_route("/api/v1/lemmas/by-difficulty", "GET")
def list_by_difficulty(
    difficulty: str,
    *,
    pos_type: Optional[str] = None,
    missing_translation: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> SearchResponse:
    """List lemmas by difficulty without requiring a search query."""
    return cast(
        SearchResponse,
        get_json(
            f"{API_V1_PREFIX}/lemmas/by-difficulty",
            {
                "difficulty": difficulty,
                "pos_type": pos_type,
                "missing_translation": missing_translation,
                "limit": limit,
                "offset": offset,
            },
        ),
    )


class AddLemmaInput(TypedDict, total=False):
    lemma_text: str
    definition_text: str
    pos_type: str
    pos_subtype: str
    difficulty_level: Optional[int]
    translations: Dict[str, str]


@mirrored_route("/api/v1/lemmas/add", "POST")
def add_lemmas(lemmas: List[AddLemmaInput]) -> Any:
    """Create one or more lemmas, returning their generated GUIDs.

    Each entry requires ``lemma_text``, ``definition_text``, ``pos_type`` and
    ``pos_subtype``; ``difficulty_level`` and ``translations`` are optional.
    An entry whose ``(lemma_text, pos_type)`` already exists is returned with
    ``status`` ``"already_exists"`` and is not modified.
    """
    return post_json(f"{API_V1_PREFIX}/lemmas/add", {"lemmas": lemmas})


@mirrored_route("/api/v1/words/add", "POST")
def add_word(word: str, model: str, dry_run: bool = False) -> Any:
    """Add a single English word to the database, from just the word.

    Unlike :func:`add_lemmas` (which takes fully specified lemma rows), this runs
    the intelligent pipeline: it queries the LLM for the word's senses, sizes how
    many senses to add by corpus frequency, caps closed-class words to one sense,
    collapses over-split senses, and writes one lemma per surviving sense.
    **Makes an LLM call and costs money.**

    A word already accounted for -- as a lemma, disambiguated lemma, English
    derivative form or alternate spelling -- returns ``status`` ``"already_exists"``
    and nothing is written. Pass ``dry_run=True`` to preview without writing.
    """
    return post_json(
        f"{API_V1_PREFIX}/words/add",
        {"word": word, "model": model, "dry_run": dry_run},
    )


@mirrored_route("/api/v1/lemma/<guid>", "GET")
def get_lemma(guid: str) -> Any:
    """Basic lemma details."""
    return get_json(f"{API_V1_PREFIX}/lemma/{guid}")


@mirrored_route("/api/v1/lemma/<guid>", "POST")
def set_lemma_difficulty(guid: str, difficulty_level: Optional[int]) -> Any:
    """Set or clear Barsukas difficulty level for a lemma."""
    return post_json(
        f"{API_V1_PREFIX}/lemma/{guid}",
        {"difficulty_level": difficulty_level},
    )


@mirrored_route("/api/v1/lemma/<guid>", "PATCH")
def patch_lemma_difficulty(guid: str, difficulty_level: Optional[int]) -> Any:
    """PATCH Barsukas difficulty level for a lemma."""
    return patch_json(
        f"{API_V1_PREFIX}/lemma/{guid}",
        {"difficulty_level": difficulty_level},
    )


@mirrored_route("/api/v1/lemma/<main_guid>/merge-synonym/<synonym_guid>", "POST")
def merge_synonym(
    main_guid: str,
    synonym_guid: str,
    *,
    changed_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> Any:
    """Merge ``synonym_guid`` into ``main_guid`` as per-language synonyms."""
    return post_json(
        f"{API_V1_PREFIX}/lemma/{main_guid}/merge-synonym/{synonym_guid}",
        {"changed_by": changed_by, "notes": notes},
    )


@mirrored_route("/api/v1/lemma/<guid>/translations", "GET")
def get_translations(guid: str, *, language: Optional[str] = None) -> Any:
    """Translations of a lemma keyed by language code."""
    return cast(
        TranslationMapResponse,
        get_json(
            f"{API_V1_PREFIX}/lemma/{guid}/translations",
            {"language": language},
        ),
    )


@mirrored_route("/api/v1/lemma/<guid>/translations/<language>/metadata", "PATCH")
def patch_translation_metadata(
    guid: str,
    language: str,
    *,
    translation_status: Optional[str] = None,
    translation_status_note: Optional[str] = None,
) -> Any:
    """Set metadata for one populated lemma translation."""
    return patch_json(
        f"{API_V1_PREFIX}/lemma/{guid}/translations/{language}/metadata",
        {
            "translation_status": translation_status,
            "translation_status_note": translation_status_note,
        },
    )


@mirrored_route("/api/v1/lemmas/translations", "GET")
def get_translations_bulk(
    guids: List[str], *, language: Optional[str] = None
) -> BulkTranslationMapResponse:
    """Translations for multiple lemmas keyed by GUID, then language code."""
    return cast(
        BulkTranslationMapResponse,
        get_json(
            f"{API_V1_PREFIX}/lemmas/translations",
            {"guids": ",".join(guids), "language": language},
        ),
    )


@mirrored_route("/api/v1/lemma/<guid>/forms", "GET")
def get_forms(guid: str, *, language: Optional[str] = None) -> Any:
    """Derivative/declined forms of a lemma."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/forms",
        {"language": language},
    )


@mirrored_route("/api/v1/lemma/<guid>/grammar", "GET")
def get_grammar(guid: str, *, language: Optional[str] = None) -> Any:
    """Grammar facts about a lemma."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/grammar",
        {"language": language},
    )


@mirrored_route("/api/v1/lemma/<guid>/pronunciations", "GET")
def get_pronunciations(guid: str, *, language: Optional[str] = None) -> Any:
    """Base-form IPA/phonetic pronunciations by language."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/pronunciations",
        {"language": language},
    )


@mirrored_route("/api/v1/lemma/<guid>/audio", "GET")
def get_audio(guid: str, *, language: Optional[str] = None) -> Any:
    """Audio availability for a lemma by language."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/audio",
        {"language": language},
    )


@mirrored_route("/api/v1/lemma/<guid>/wordfreq", "GET")
def get_wordfreq(guid: str) -> WordfreqResponse:
    """Wordfreq corpus rollups and best ranks for a lemma by language."""
    return cast(WordfreqResponse, get_json(f"{API_V1_PREFIX}/lemma/{guid}/wordfreq"))


@mirrored_route("/api/v1/lemma/<guid>/sentences", "GET")
def get_sentences(guid: str, *, language: Optional[str] = None) -> Any:
    """Example sentences using a lemma."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/sentences",
        {"language": language},
    )
