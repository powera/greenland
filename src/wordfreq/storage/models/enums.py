#!/usr/bin/python3

"""Enumeration types for linguistic models."""

import enum

class NounSubtype(enum.Enum):
    """Subtypes for nouns."""
    # People and Living Things
    HUMAN = "human"
    ANIMAL = "animal"
    BODY_PART = "body_part"
    DISEASE_CONDITION = "disease_condition"
    PLANT = "plant"
    
    # Food and Consumables
    FOOD_DRINK = "food_drink"
    
    # Physical Objects and Structures
    BUILDING_STRUCTURE = "building_structure"
    SMALL_MOVABLE_OBJECT = "small_movable_object"
    CLOTHING_ACCESSORY = "clothing_accessory"
    ARTWORK_ARTIFACT = "artwork_artifact"
    NATURAL_FEATURE = "natural_feature"
    TOOL_MACHINE = "tool_machine"
    PATH_INFRASTRUCTURE = "path_infrastructure"
    
    # Materials and Substances
    MATERIAL_SUBSTANCE = "material_substance"
    CHEMICAL_COMPOUND = "chemical_compound"
    MEDICATION_REMEDY = "medication_remedy"
    
    # Abstract Concepts and Ideas
    CONCEPT_IDEA = "concept_idea"
    SYMBOLIC_ELEMENT = "symbolic_element"
    QUALITY_ATTRIBUTE = "quality_attribute"
    MENTAL_CONSTRUCT = "mental_construct"
    KNOWLEDGE_DOMAIN = "knowledge_domain"
    QUANTITATIVE_CONCEPT = "quantitative_concept"
    EMOTION_FEELING = "emotion_feeling"
    
    # Processes and Time
    PROCESS_EVENT = "process_event"
    TIME_PERIOD = "time_period"
    
    # Groups and Collections
    GROUP_PEOPLE = "group_people"
    GROUP_ANIMAL = "animal_grouping_term"
    COLLECTION_THINGS = "collection_things"
    
    # Named Entities
    PERSONAL_NAME = "personal_name"
    PLACE_NAME = "place_name"
    ORGANIZATION_NAME = "organization_name"
    
    # Temporal Names
    TEMPORAL_NAME = "temporal_name"  # Days of week, months, etc.
    
    # Nationality and Measurement
    NATIONALITY = "nationality"
    UNIT_OF_MEASUREMENT = "unit_of_measurement"
    
    # Other
    OTHER = "other"

class VerbSubtype(enum.Enum):
    """Subtypes for verbs."""
    PHYSICAL_ACTION = "physical_action"
    CREATION_ACTION = "creation_action"
    DESTRUCTION_ACTION = "destruction_action"
    MENTAL_STATE = "mental_state"
    EMOTIONAL_STATE = "emotional_state"
    POSSESSION = "possession"
    DEVELOPMENT = "development"
    CHANGE = "change"
    SPEAKING = "speaking"
    WRITING = "writing"
    EXPRESSING = "expressing"
    DIRECTIONAL_MOVEMENT = "directional_movement"
    MANNER_MOVEMENT = "manner_movement"
    OTHER = "other"

class AdjectiveSubtype(enum.Enum):
    """Subtypes for adjectives."""
    SIZE = "size"
    COLOR = "color"
    SHAPE = "shape"
    TEXTURE = "texture"
    QUALITY = "quality"
    AESTHETIC = "aesthetic"
    IMPORTANCE = "importance"
    ORIGIN = "origin"
    PURPOSE = "purpose"
    MATERIAL = "material"
    DEFINITE_QUANTITY = "definite_quantity"
    INDEFINITE_QUANTITY = "indefinite_quantity"
    DURATION = "duration"
    FREQUENCY = "frequency"
    SEQUENCE = "sequence"
    OTHER = "other"

class AdverbSubtype(enum.Enum):
    """Subtypes for adverbs."""
    STYLE = "style"
    ATTITUDE = "attitude"
    SPECIFIC_TIME = "specific_time"
    RELATIVE_TIME = "relative_time"
    DURATION = "duration"
    DIRECTION = "direction"
    LOCATION = "location"
    DISTANCE = "distance"
    INTENSITY = "intensity"
    COMPLETENESS = "completeness"
    APPROXIMATION = "approximation"
    DEFINITE_FREQUENCY = "definite_frequency"
    INDEFINITE_FREQUENCY = "indefinite_frequency"
    OTHER = "other"

class GrammaticalForm(enum.Enum):
    """Grammatical forms for derivative forms with part-of-speech prefixes."""
    # Verb forms - generic/language-neutral
    VERB_INFINITIVE = "verb/infinitive"
    VERB_PAST_PARTICIPLE = "verb/past_participle"
    VERB_PRESENT_PARTICIPLE = "verb/present_participle"
    VERB_GERUND = "verb/gerund"

    # English verb forms (person_tense)
    # Present tense
    VERB_EN_1S_PRES = "verb/en_1s_pres"
    VERB_EN_2S_PRES = "verb/en_2s_pres"
    VERB_EN_3S_PRES = "verb/en_3s_pres"
    VERB_EN_1P_PRES = "verb/en_1p_pres"
    VERB_EN_2P_PRES = "verb/en_2p_pres"
    VERB_EN_3P_PRES = "verb/en_3p_pres"

    # Past tense
    VERB_EN_1S_PAST = "verb/en_1s_past"
    VERB_EN_2S_PAST = "verb/en_2s_past"
    VERB_EN_3S_PAST = "verb/en_3s_past"
    VERB_EN_1P_PAST = "verb/en_1p_past"
    VERB_EN_2P_PAST = "verb/en_2p_past"
    VERB_EN_3P_PAST = "verb/en_3p_past"

    # Future tense
    VERB_EN_1S_FUT = "verb/en_1s_fut"
    VERB_EN_2S_FUT = "verb/en_2s_fut"
    VERB_EN_3S_FUT = "verb/en_3s_fut"
    VERB_EN_1P_FUT = "verb/en_1p_fut"
    VERB_EN_2P_FUT = "verb/en_2p_fut"
    VERB_EN_3P_FUT = "verb/en_3p_fut"

    # Imperative
    VERB_EN_2S_IMP = "verb/en_2s_imp"
    VERB_EN_2P_IMP = "verb/en_2p_imp"

    # Lithuanian verb forms (person_tense with gender distinction)
    # Present tense
    VERB_LT_1S_PRES = "verb/lt_1s_pres"
    VERB_LT_2S_PRES = "verb/lt_2s_pres"
    VERB_LT_3S_M_PRES = "verb/lt_3s-m_pres"
    VERB_LT_3S_F_PRES = "verb/lt_3s-f_pres"
    VERB_LT_1P_PRES = "verb/lt_1p_pres"
    VERB_LT_2P_PRES = "verb/lt_2p_pres"
    VERB_LT_3P_M_PRES = "verb/lt_3p-m_pres"
    VERB_LT_3P_F_PRES = "verb/lt_3p-f_pres"

    # Past tense
    VERB_LT_1S_PAST = "verb/lt_1s_past"
    VERB_LT_2S_PAST = "verb/lt_2s_past"
    VERB_LT_3S_M_PAST = "verb/lt_3s-m_past"
    VERB_LT_3S_F_PAST = "verb/lt_3s-f_past"
    VERB_LT_1P_PAST = "verb/lt_1p_past"
    VERB_LT_2P_PAST = "verb/lt_2p_past"
    VERB_LT_3P_M_PAST = "verb/lt_3p-m_past"
    VERB_LT_3P_F_PAST = "verb/lt_3p-f_past"

    # Future tense
    VERB_LT_1S_FUT = "verb/lt_1s_fut"
    VERB_LT_2S_FUT = "verb/lt_2s_fut"
    VERB_LT_3S_M_FUT = "verb/lt_3s-m_fut"
    VERB_LT_3S_F_FUT = "verb/lt_3s-f_fut"
    VERB_LT_1P_FUT = "verb/lt_1p_fut"
    VERB_LT_2P_FUT = "verb/lt_2p_fut"
    VERB_LT_3P_M_FUT = "verb/lt_3p-m_fut"
    VERB_LT_3P_F_FUT = "verb/lt_3p-f_fut"
    
    # Noun forms (English)
    NOUN_SINGULAR = "noun/singular"
    NOUN_PLURAL = "noun/plural"
    NOUN_POSSESSIVE_SINGULAR = "noun/possessive_singular"
    NOUN_POSSESSIVE_PLURAL = "noun/possessive_plural"

    # Lithuanian noun forms (7 cases × 2 numbers)
    NOUN_LT_NOMINATIVE_SINGULAR = "noun/lt_nominative_singular"
    NOUN_LT_GENITIVE_SINGULAR = "noun/lt_genitive_singular"
    NOUN_LT_DATIVE_SINGULAR = "noun/lt_dative_singular"
    NOUN_LT_ACCUSATIVE_SINGULAR = "noun/lt_accusative_singular"
    NOUN_LT_INSTRUMENTAL_SINGULAR = "noun/lt_instrumental_singular"
    NOUN_LT_LOCATIVE_SINGULAR = "noun/lt_locative_singular"
    NOUN_LT_VOCATIVE_SINGULAR = "noun/lt_vocative_singular"

    NOUN_LT_NOMINATIVE_PLURAL = "noun/lt_nominative_plural"
    NOUN_LT_GENITIVE_PLURAL = "noun/lt_genitive_plural"
    NOUN_LT_DATIVE_PLURAL = "noun/lt_dative_plural"
    NOUN_LT_ACCUSATIVE_PLURAL = "noun/lt_accusative_plural"
    NOUN_LT_INSTRUMENTAL_PLURAL = "noun/lt_instrumental_plural"
    NOUN_LT_LOCATIVE_PLURAL = "noun/lt_locative_plural"
    NOUN_LT_VOCATIVE_PLURAL = "noun/lt_vocative_plural"
    
    # Adjective forms (English)
    ADJECTIVE_POSITIVE = "adjective/positive"
    ADJECTIVE_COMPARATIVE = "adjective/comparative"
    ADJECTIVE_SUPERLATIVE = "adjective/superlative"

    # Lithuanian adjective forms (7 cases × 2 numbers × 2 genders = 28 forms)
    # Masculine singular
    ADJ_LT_NOMINATIVE_SINGULAR_M = "adjective/lt_nominative_singular_m"
    ADJ_LT_GENITIVE_SINGULAR_M = "adjective/lt_genitive_singular_m"
    ADJ_LT_DATIVE_SINGULAR_M = "adjective/lt_dative_singular_m"
    ADJ_LT_ACCUSATIVE_SINGULAR_M = "adjective/lt_accusative_singular_m"
    ADJ_LT_INSTRUMENTAL_SINGULAR_M = "adjective/lt_instrumental_singular_m"
    ADJ_LT_LOCATIVE_SINGULAR_M = "adjective/lt_locative_singular_m"
    ADJ_LT_VOCATIVE_SINGULAR_M = "adjective/lt_vocative_singular_m"

    # Feminine singular
    ADJ_LT_NOMINATIVE_SINGULAR_F = "adjective/lt_nominative_singular_f"
    ADJ_LT_GENITIVE_SINGULAR_F = "adjective/lt_genitive_singular_f"
    ADJ_LT_DATIVE_SINGULAR_F = "adjective/lt_dative_singular_f"
    ADJ_LT_ACCUSATIVE_SINGULAR_F = "adjective/lt_accusative_singular_f"
    ADJ_LT_INSTRUMENTAL_SINGULAR_F = "adjective/lt_instrumental_singular_f"
    ADJ_LT_LOCATIVE_SINGULAR_F = "adjective/lt_locative_singular_f"
    ADJ_LT_VOCATIVE_SINGULAR_F = "adjective/lt_vocative_singular_f"

    # Masculine plural
    ADJ_LT_NOMINATIVE_PLURAL_M = "adjective/lt_nominative_plural_m"
    ADJ_LT_GENITIVE_PLURAL_M = "adjective/lt_genitive_plural_m"
    ADJ_LT_DATIVE_PLURAL_M = "adjective/lt_dative_plural_m"
    ADJ_LT_ACCUSATIVE_PLURAL_M = "adjective/lt_accusative_plural_m"
    ADJ_LT_INSTRUMENTAL_PLURAL_M = "adjective/lt_instrumental_plural_m"
    ADJ_LT_LOCATIVE_PLURAL_M = "adjective/lt_locative_plural_m"
    ADJ_LT_VOCATIVE_PLURAL_M = "adjective/lt_vocative_plural_m"

    # Feminine plural
    ADJ_LT_NOMINATIVE_PLURAL_F = "adjective/lt_nominative_plural_f"
    ADJ_LT_GENITIVE_PLURAL_F = "adjective/lt_genitive_plural_f"
    ADJ_LT_DATIVE_PLURAL_F = "adjective/lt_dative_plural_f"
    ADJ_LT_ACCUSATIVE_PLURAL_F = "adjective/lt_accusative_plural_f"
    ADJ_LT_INSTRUMENTAL_PLURAL_F = "adjective/lt_instrumental_plural_f"
    ADJ_LT_LOCATIVE_PLURAL_F = "adjective/lt_locative_plural_f"
    ADJ_LT_VOCATIVE_PLURAL_F = "adjective/lt_vocative_plural_f"

    # French noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_FR_SINGULAR = "noun/fr_singular"
    NOUN_FR_PLURAL = "noun/fr_plural"

    # French adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_FR_SINGULAR_M = "adjective/fr_singular_m"
    ADJ_FR_PLURAL_M = "adjective/fr_plural_m"
    ADJ_FR_SINGULAR_F = "adjective/fr_singular_f"
    ADJ_FR_PLURAL_F = "adjective/fr_plural_f"

    # French verb forms (6 persons × 6 tenses = 36 forms)
    # Present tense (présent de l'indicatif)
    VERB_FR_1S_PRES = "verb/fr_1s_pres"
    VERB_FR_2S_PRES = "verb/fr_2s_pres"
    VERB_FR_3S_PRES = "verb/fr_3s_pres"
    VERB_FR_1P_PRES = "verb/fr_1p_pres"
    VERB_FR_2P_PRES = "verb/fr_2p_pres"
    VERB_FR_3P_PRES = "verb/fr_3p_pres"

    # Imperfect (imparfait)
    VERB_FR_1S_IMPF = "verb/fr_1s_impf"
    VERB_FR_2S_IMPF = "verb/fr_2s_impf"
    VERB_FR_3S_IMPF = "verb/fr_3s_impf"
    VERB_FR_1P_IMPF = "verb/fr_1p_impf"
    VERB_FR_2P_IMPF = "verb/fr_2p_impf"
    VERB_FR_3P_IMPF = "verb/fr_3p_impf"

    # Future (futur simple)
    VERB_FR_1S_FUT = "verb/fr_1s_fut"
    VERB_FR_2S_FUT = "verb/fr_2s_fut"
    VERB_FR_3S_FUT = "verb/fr_3s_fut"
    VERB_FR_1P_FUT = "verb/fr_1p_fut"
    VERB_FR_2P_FUT = "verb/fr_2p_fut"
    VERB_FR_3P_FUT = "verb/fr_3p_fut"

    # Conditional (conditionnel présent)
    VERB_FR_1S_COND = "verb/fr_1s_cond"
    VERB_FR_2S_COND = "verb/fr_2s_cond"
    VERB_FR_3S_COND = "verb/fr_3s_cond"
    VERB_FR_1P_COND = "verb/fr_1p_cond"
    VERB_FR_2P_COND = "verb/fr_2p_cond"
    VERB_FR_3P_COND = "verb/fr_3p_cond"

    # Subjunctive present (subjonctif présent)
    VERB_FR_1S_SUBJ = "verb/fr_1s_subj"
    VERB_FR_2S_SUBJ = "verb/fr_2s_subj"
    VERB_FR_3S_SUBJ = "verb/fr_3s_subj"
    VERB_FR_1P_SUBJ = "verb/fr_1p_subj"
    VERB_FR_2P_SUBJ = "verb/fr_2p_subj"
    VERB_FR_3P_SUBJ = "verb/fr_3p_subj"

    # Passé composé (compound past with auxiliary)
    VERB_FR_1S_PC = "verb/fr_1s_pc"
    VERB_FR_2S_PC = "verb/fr_2s_pc"
    VERB_FR_3S_PC = "verb/fr_3s_pc"
    VERB_FR_1P_PC = "verb/fr_1p_pc"
    VERB_FR_2P_PC = "verb/fr_2p_pc"
    VERB_FR_3P_PC = "verb/fr_3p_pc"

    # Spanish noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_ES_SINGULAR = "noun/es_singular"
    NOUN_ES_PLURAL = "noun/es_plural"

    # Spanish adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_ES_SINGULAR_M = "adjective/es_singular_m"
    ADJ_ES_PLURAL_M = "adjective/es_plural_m"
    ADJ_ES_SINGULAR_F = "adjective/es_singular_f"
    ADJ_ES_PLURAL_F = "adjective/es_plural_f"

    # Spanish verb forms (6 persons × 6 tenses = 36 forms)
    # Present tense (presente de indicativo)
    VERB_ES_1S_PRES = "verb/es_1s_pres"
    VERB_ES_2S_PRES = "verb/es_2s_pres"
    VERB_ES_3S_PRES = "verb/es_3s_pres"
    VERB_ES_1P_PRES = "verb/es_1p_pres"
    VERB_ES_2P_PRES = "verb/es_2p_pres"
    VERB_ES_3P_PRES = "verb/es_3p_pres"

    # Preterite (pretérito)
    VERB_ES_1S_PRET = "verb/es_1s_pret"
    VERB_ES_2S_PRET = "verb/es_2s_pret"
    VERB_ES_3S_PRET = "verb/es_3s_pret"
    VERB_ES_1P_PRET = "verb/es_1p_pret"
    VERB_ES_2P_PRET = "verb/es_2p_pret"
    VERB_ES_3P_PRET = "verb/es_3p_pret"

    # Imperfect (imperfecto)
    VERB_ES_1S_IMPF = "verb/es_1s_impf"
    VERB_ES_2S_IMPF = "verb/es_2s_impf"
    VERB_ES_3S_IMPF = "verb/es_3s_impf"
    VERB_ES_1P_IMPF = "verb/es_1p_impf"
    VERB_ES_2P_IMPF = "verb/es_2p_impf"
    VERB_ES_3P_IMPF = "verb/es_3p_impf"

    # Future (futuro simple)
    VERB_ES_1S_FUT = "verb/es_1s_fut"
    VERB_ES_2S_FUT = "verb/es_2s_fut"
    VERB_ES_3S_FUT = "verb/es_3s_fut"
    VERB_ES_1P_FUT = "verb/es_1p_fut"
    VERB_ES_2P_FUT = "verb/es_2p_fut"
    VERB_ES_3P_FUT = "verb/es_3p_fut"

    # Conditional (condicional simple)
    VERB_ES_1S_COND = "verb/es_1s_cond"
    VERB_ES_2S_COND = "verb/es_2s_cond"
    VERB_ES_3S_COND = "verb/es_3s_cond"
    VERB_ES_1P_COND = "verb/es_1p_cond"
    VERB_ES_2P_COND = "verb/es_2p_cond"
    VERB_ES_3P_COND = "verb/es_3p_cond"

    # Subjunctive present (presente de subjuntivo)
    VERB_ES_1S_SUBJ = "verb/es_1s_subj"
    VERB_ES_2S_SUBJ = "verb/es_2s_subj"
    VERB_ES_3S_SUBJ = "verb/es_3s_subj"
    VERB_ES_1P_SUBJ = "verb/es_1p_subj"
    VERB_ES_2P_SUBJ = "verb/es_2p_subj"
    VERB_ES_3P_SUBJ = "verb/es_3p_subj"

    # German noun forms (singular/plural only)
    NOUN_DE_SINGULAR = "noun/de_singular"
    NOUN_DE_PLURAL = "noun/de_plural"

    # German adjective forms (2 genders × 2 numbers = 4 forms, simplified)
    ADJ_DE_SINGULAR_M = "adjective/de_singular_m"
    ADJ_DE_PLURAL_M = "adjective/de_plural_m"
    ADJ_DE_SINGULAR_F = "adjective/de_singular_f"
    ADJ_DE_PLURAL_F = "adjective/de_plural_f"

    # German verb forms (6 persons × 6 tenses = 36 forms)
    # Present tense (Präsens)
    VERB_DE_1S_PRES = "verb/de_1s_pres"
    VERB_DE_2S_PRES = "verb/de_2s_pres"
    VERB_DE_3S_PRES = "verb/de_3s_pres"
    VERB_DE_1P_PRES = "verb/de_1p_pres"
    VERB_DE_2P_PRES = "verb/de_2p_pres"
    VERB_DE_3P_PRES = "verb/de_3p_pres"

    # Simple past (Präteritum)
    VERB_DE_1S_PAST = "verb/de_1s_past"
    VERB_DE_2S_PAST = "verb/de_2s_past"
    VERB_DE_3S_PAST = "verb/de_3s_past"
    VERB_DE_1P_PAST = "verb/de_1p_past"
    VERB_DE_2P_PAST = "verb/de_2p_past"
    VERB_DE_3P_PAST = "verb/de_3p_past"

    # Perfect (Perfekt - compound tense)
    VERB_DE_1S_PERF = "verb/de_1s_perf"
    VERB_DE_2S_PERF = "verb/de_2s_perf"
    VERB_DE_3S_PERF = "verb/de_3s_perf"
    VERB_DE_1P_PERF = "verb/de_1p_perf"
    VERB_DE_2P_PERF = "verb/de_2p_perf"
    VERB_DE_3P_PERF = "verb/de_3p_perf"

    # Future (Futur I)
    VERB_DE_1S_FUT = "verb/de_1s_fut"
    VERB_DE_2S_FUT = "verb/de_2s_fut"
    VERB_DE_3S_FUT = "verb/de_3s_fut"
    VERB_DE_1P_FUT = "verb/de_1p_fut"
    VERB_DE_2P_FUT = "verb/de_2p_fut"
    VERB_DE_3P_FUT = "verb/de_3p_fut"

    # Conditional (Konjunktiv II / würde + infinitive)
    VERB_DE_1S_COND = "verb/de_1s_cond"
    VERB_DE_2S_COND = "verb/de_2s_cond"
    VERB_DE_3S_COND = "verb/de_3s_cond"
    VERB_DE_1P_COND = "verb/de_1p_cond"
    VERB_DE_2P_COND = "verb/de_2p_cond"
    VERB_DE_3P_COND = "verb/de_3p_cond"

    # Subjunctive present (Konjunktiv I)
    VERB_DE_1S_SUBJ = "verb/de_1s_subj"
    VERB_DE_2S_SUBJ = "verb/de_2s_subj"
    VERB_DE_3S_SUBJ = "verb/de_3s_subj"
    VERB_DE_1P_SUBJ = "verb/de_1p_subj"
    VERB_DE_2P_SUBJ = "verb/de_2p_subj"
    VERB_DE_3P_SUBJ = "verb/de_3s_subj"

    # Adverb forms
    ADVERB_POSITIVE = "adverb/positive"
    ADVERB_COMPARATIVE = "adverb/comparative"
    ADVERB_SUPERLATIVE = "adverb/superlative"
    
    # Pronoun forms
    PRONOUN_SUBJECTIVE = "pronoun/subjective"
    PRONOUN_OBJECTIVE = "pronoun/objective"
    PRONOUN_POSSESSIVE = "pronoun/possessive"
    PRONOUN_REFLEXIVE = "pronoun/reflexive"
    
    # Other parts of speech (typically invariant)
    PREPOSITION = "preposition/base"
    CONJUNCTION = "conjunction/base"
    INTERJECTION = "interjection/base"
    DETERMINER = "determiner/base"
    ARTICLE = "article/base"
    
    # Generic forms
    BASE_FORM = "base_form"
    OTHER = "other"