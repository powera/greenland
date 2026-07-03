"""Models package for wordfreq."""

from storage.models.concept import (
    Concept,
    ConceptLemmaLink,
    ConceptWikidataIndex,
    MAX_CONCEPT_SOURCES,
    SUB_CONCEPT_CATEGORIES,
    SubConcept,
    concept_slug_to_title,
    normalize_concept_slug,
    wiki_target_qid,
)
from storage.models.enums import (
    AdjectiveSubtype,
    AdverbSubtype,
    GrammaticalForm,
    NounSubtype,
    VerbSubtype,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_tombstone import GuidTombstone
from storage.models.lemma_relation import (
    LemmaRelationGroup,
    LemmaRelationMember,
)
from storage.models.operation_log import OperationLog
from storage.models.query_log import QueryLog
from storage.models.schema import (
    Base,
    Corpus,
    DerivativeForm,
    Lemma,
    LemmaEmbedding,
    LemmaDifficultyOverride,
    LemmaTranslation,
    Sentence,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
    WordToken,
)
from storage.models.translations import Translation, TranslationSet

# Import after schema to ensure PendingImport is registered with the same Base
# before SentencePatternWord's relationship to it is resolved
from storage.models.imports import PendingImport, PendingImportSynonymCandidate, WordExclusion

__all__ = [
    "AdjectiveSubtype",
    "AdverbSubtype",
    "Base",
    "Concept",
    "ConceptLemmaLink",
    "ConceptWikidataIndex",
    "Corpus",
    "DerivativeForm",
    "GrammarFact",
    "GuidTombstone",
    "Lemma",
    "LemmaEmbedding",
    "LemmaDifficultyOverride",
    "LemmaRelationGroup",
    "LemmaRelationMember",
    "LemmaTranslation",
    "MAX_CONCEPT_SOURCES",
    "NounSubtype",
    "SUB_CONCEPT_CATEGORIES",
    "SubConcept",
    "wiki_target_qid",
    "OperationLog",
    "PendingImport",
    "PendingImportSynonymCandidate",
    "QueryLog",
    "concept_slug_to_title",
    "normalize_concept_slug",
    "Sentence",
    "SentencePatternWord",
    "SentenceTranslation",
    "SentenceWord",
    "Translation",
    "TranslationSet",
    "VerbSubtype",
    "WordExclusion",
    "WordToken",
]
