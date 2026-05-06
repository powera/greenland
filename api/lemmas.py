"""HTTP facade for lemma-related Barsukas endpoints.

Mirrors ``src/barsukas/routes/api.py``. Any change to a route signature or
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
    translations: Dict[str, str]
    verified: bool


class SearchResponse(TypedDict):
    data: List[SearchResult]
    metadata: Dict[str, Any]


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
    query: str,
    *,
    pos_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> SearchResponse:
    """Search lemmas by text/definition/translations."""
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


@mirrored_route("/api/v1/lemma/<guid>/translations", "GET")
def get_translations(guid: str, *, language: Optional[str] = None) -> Any:
    """Translations of a lemma keyed by language code."""
    return get_json(
        f"{API_V1_PREFIX}/lemma/{guid}/translations",
        {"language": language},
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
