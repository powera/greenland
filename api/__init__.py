"""Public typed facade for Barsukas domain HTTP wrappers."""

from api.audio import AudioResponse, GetLemmaAudioRequest, get_lemma_audio
from api.batch_operations import BatchOperationsResponse, ListBatchesRequest, list_batches
from api.lemmas import (
    GetLemmaRequest,
    LemmasResponse,
    SearchLemmasRequest,
    get_lemma,
    search_lemmas,
)
from api.llm_agents import (
    AgentTriggerRequest,
    AgentTriggerResponse,
    PronunciationTriggerRequest,
    add_missing_translations,
    check_translations,
    generate_pronunciations,
)
from api.sentences import GetLemmaSentencesRequest, SentencesResponse, get_lemma_sentences
from api.translations import (
    GetLemmaTranslationsRequest,
    TranslationResponse,
    get_lemma_translations,
)

__all__ = [
    "AgentTriggerRequest",
    "AgentTriggerResponse",
    "AudioResponse",
    "BatchOperationsResponse",
    "GetLemmaAudioRequest",
    "GetLemmaRequest",
    "GetLemmaSentencesRequest",
    "GetLemmaTranslationsRequest",
    "LemmasResponse",
    "ListBatchesRequest",
    "PronunciationTriggerRequest",
    "SearchLemmasRequest",
    "SentencesResponse",
    "TranslationResponse",
    "add_missing_translations",
    "check_translations",
    "generate_pronunciations",
    "get_lemma",
    "get_lemma_audio",
    "get_lemma_sentences",
    "get_lemma_translations",
    "list_batches",
    "search_lemmas",
]
