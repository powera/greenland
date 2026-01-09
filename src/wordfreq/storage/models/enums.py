#!/usr/bin/python3

"""Enumeration types for linguistic models."""

import enum


class NounSubtype(enum.Enum):
    """Subtypes for nouns.

    NOTE: When adding/modifying subtypes, update SUBTYPE_GUID_PREFIXES
    in guid_prefixes.py to keep GUID assignments in sync.
    """

    # People and Living Things
    OCCUPATION = "occupation"  # Professions and roles (teacher, doctor, accountant)
    FAMILY_RELATION = "family_relation"  # Family members (brother, uncle, cousin, parent)
    HUMAN = "human"

    ANIMAL = "animal"
    BODY_PART = "body_part"
    DISEASE_CONDITION = "disease_condition"
    PLANT = "plant"
    PLANT_PART = "plant_part"  # Parts of plants (leaf, root, seed, petal, bark)

    # Food and Consumables
    FOOD = "food"  # Solid consumables (bread, apple, rice, meat)
    BEVERAGE = "beverage"  # Liquid consumables (water, coffee, tea, juice)

    # Physical Objects and Structures
    BUILDING_STRUCTURE = "building_structure"
    FURNITURE = "furniture"  # Furniture items (table, chair, desk, sofa, bed)
    SMALL_MOVABLE_OBJECT = "small_movable_object"
    CLOTHING_ACCESSORY = "clothing_accessory"
    ARTWORK_ARTIFACT = "artwork_artifact"
    NATURAL_FEATURE = "natural_feature"
    TOOL = "tool"  # Hand tools and generic tools (hammer, saw, wrench, screwdriver)
    ELECTRONIC_DEVICE = "electronic_device"  # Computers, phones, TVs, radios, cameras
    APPLIANCE = "appliance"  # Kitchen and household appliances (blender, microwave, toaster)
    WEAPON = "weapon"  # Weapons and arms (sword, gun, bow, shield)
    VEHICLE = "vehicle"  # Transportation (car, truck, bicycle, boat, airplane)
    PATH_INFRASTRUCTURE = "path_infrastructure"

    # Materials and Substances
    MATERIAL_SUBSTANCE = "material_substance"
    CHEMICAL_COMPOUND = "chemical_compound"
    MEDICATION_REMEDY = "medication_remedy"

    # Abstract Concepts and Ideas
    CONCEPT_IDEA = "concept_idea"
    ACTIVITY = "activity"  # Activities and hobbies (reading, cooking, sports, dancing, hiking)
    SYMBOLIC_ELEMENT = "symbolic_element"
    QUALITY_ATTRIBUTE = "quality_attribute"
    MENTAL_CONSTRUCT = "mental_construct"
    KNOWLEDGE_DOMAIN = "knowledge_domain"
    QUANTITATIVE_CONCEPT = "quantitative_concept"
    EMOTION_FEELING = "emotion_feeling"
    SHAPE = "shape"  # Geometric shapes (circle, triangle, square, rectangle, etc.)

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

    PHYSICAL_ACTION = "physical_action"  # Physical actions (push, pull, lift, eat, drink)
    CREATION_ACTION = "creation_action"  # Creating things (make, create, build)
    DESTRUCTION_ACTION = "destruction_action"  # Destroying (break, destroy, demolish)
    MENTAL_STATE = "mental_state"  # Cognition (know, believe, understand, think)
    EMOTIONAL_STATE = "emotional_state"  # Feelings (love, hate, fear, enjoy)
    PERCEPTION = "perception"  # Sensory verbs (see, hear, smell, taste, feel, touch)
    COMMUNICATION = "communication"  # Speaking and writing (say, tell, speak, write, read)
    POSSESSION = "possession"  # Having/owning (have, own, possess, give, take)
    EXISTENCE = "existence"  # Living/existing (live, exist, die, survive, stay, remain)
    DEVELOPMENT = "development"  # Growing/evolving (grow, develop, evolve, mature)
    CHANGE = "change"  # Transforming (become, transform, change, turn)
    DIRECTIONAL_MOVEMENT = "directional_movement"  # Moving with direction (go, come, enter, leave)
    MANNER_MOVEMENT = "manner_movement"  # Way of moving (walk, run, swim, fly, crawl)
    OTHER = "other"


class AdjectiveSubtype(enum.Enum):
    """Subtypes for adjectives.

    NOTE: When adding/modifying subtypes, update SUBTYPE_GUID_PREFIXES
    in guid_prefixes.py to keep GUID assignments in sync.
    """

    SIZE = "size"  # Size descriptions (big, small, huge, tiny)
    COLOR = "color"  # Color descriptions (red, blue, green, yellow)
    SHAPE = "shape"  # Shape descriptions (round, square, triangular, oval)
    TEXTURE = "texture"  # Texture descriptions (soft, hard, smooth, rough)
    PERSONAL_QUALITY = "personal_quality"  # Character/personality traits (honest, kind, brave, lazy, clever, polite)
    PHYSICAL_PROPERTY = "physical_property"  # Physical properties and states (dimensions, weight, temperature, condition: high, low, heavy, light, cold, hot, wet, dry, open, closed)
    CONDITION = (
        "condition"  # Physical/temporal state (hot, cold, wet, dry, clean, dirty, new, old, fresh)
    )
    QUALITY = "quality"  # Evaluative and abstract properties (good, bad, excellent, important, possible, necessary, real, clear, simple)
    AESTHETIC = "aesthetic"  # Beauty or appearance (beautiful, ugly, pretty, handsome)
    IMPORTANCE = "importance"  # Importance or priority (important, essential, trivial, critical)
    ORIGIN = "origin"  # Origin or source (American, Chinese, domestic, foreign)
    PURPOSE = "purpose"  # Purpose or function (educational, medical, industrial, recreational)
    MATERIAL = "material"  # Material composition (wooden, metal, plastic, cotton)
    DEFINITE_QUANTITY = "definite_quantity"  # Specific amounts (one, ten, hundred, first)
    INDEFINITE_QUANTITY = "indefinite_quantity"  # Inexact amounts (many, few, some, several)
    DURATION = "duration"  # Time duration (brief, long, eternal, temporary)
    FREQUENCY = "frequency"  # Frequency of occurrence (daily, occasional, rare, frequent)
    SEQUENCE = "sequence"  # Order or sequence (first, last, next, previous)
    OTHER = "other"


class AdverbSubtype(enum.Enum):
    """Subtypes for adverbs."""

    # Manner
    STYLE = "style"  # Manner or style of action (quickly, carefully, well, slowly, badly, easily)
    ATTITUDE = "attitude"  # Attitude or approach (eagerly, reluctantly, willingly, gladly, sadly)

    # Temporal
    SPECIFIC_TIME = (
        "specific_time"  # Specific time references (now, today, yesterday, tomorrow, tonight)
    )
    RELATIVE_TIME = (
        "relative_time"  # Relative time references (already, soon, recently, lately, previously)
    )
    DURATION = (
        "duration"  # Duration of time (briefly, temporarily, permanently, forever, momentarily)
    )
    DEFINITE_FREQUENCY = (
        "definite_frequency"  # Specific frequency (daily, weekly, monthly, yearly, hourly)
    )
    INDEFINITE_FREQUENCY = "indefinite_frequency"  # Inexact frequency (often, sometimes, rarely, seldom, always, never)

    # Spatial
    DIRECTION = (
        "direction"  # Directional movement (up, down, forward, backward, left, right, north)
    )
    LOCATION = "location"  # Position or place (here, there, everywhere, nowhere, somewhere, inside, outside)
    DISTANCE = "distance"  # Distance references (nearby, far, close, away, afar)

    # Degree
    INTENSITY = (
        "intensity"  # Intensity or degree (very, extremely, slightly, quite, rather, too, enough)
    )
    COMPLETENESS = "completeness"  # Degree of completeness (entirely, partly, completely, fully, partially, halfway)
    APPROXIMATION = "approximation"  # Approximation (almost, nearly, exactly, approximately, precisely, roughly)

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
    VERB_EN_1S_PRESENT = "verb/en_1s_present"
    VERB_EN_2S_PRESENT = "verb/en_2s_present"
    VERB_EN_3S_PRESENT = "verb/en_3s_present"  # "eats" (gender-neutral)
    VERB_EN_3S_M_PRESENT = "verb/en_3s-m_present"  # "he eats"
    VERB_EN_3S_F_PRESENT = "verb/en_3s-f_present"  # "she eats"
    VERB_EN_1P_PRESENT = "verb/en_1p_present"
    VERB_EN_2P_PRESENT = "verb/en_2p_present"
    VERB_EN_3P_PRESENT = "verb/en_3p_present"  # "eat" (gender-neutral)
    VERB_EN_3P_M_PRESENT = "verb/en_3p-m_present"  # "they(m.) eat"
    VERB_EN_3P_F_PRESENT = "verb/en_3p-f_present"  # "they(f.) eat"

    # Past tense
    VERB_EN_1S_PAST = "verb/en_1s_past"
    VERB_EN_2S_PAST = "verb/en_2s_past"
    VERB_EN_3S_PAST = "verb/en_3s_past"  # "ate" (gender-neutral)
    VERB_EN_3S_M_PAST = "verb/en_3s-m_past"  # "he ate"
    VERB_EN_3S_F_PAST = "verb/en_3s-f_past"  # "she ate"
    VERB_EN_1P_PAST = "verb/en_1p_past"
    VERB_EN_2P_PAST = "verb/en_2p_past"
    VERB_EN_3P_PAST = "verb/en_3p_past"  # "ate" (gender-neutral)
    VERB_EN_3P_M_PAST = "verb/en_3p-m_past"  # "they(m.) ate"
    VERB_EN_3P_F_PAST = "verb/en_3p-f_past"  # "they(f.) ate"

    # Future tense
    VERB_EN_1S_FUTURE = "verb/en_1s_future"
    VERB_EN_2S_FUTURE = "verb/en_2s_future"
    VERB_EN_3S_FUTURE = "verb/en_3s_future"  # "will eat" (gender-neutral)
    VERB_EN_3S_M_FUTURE = "verb/en_3s-m_future"  # "he will eat"
    VERB_EN_3S_F_FUTURE = "verb/en_3s-f_future"  # "she will eat"
    VERB_EN_1P_FUTURE = "verb/en_1p_future"
    VERB_EN_2P_FUTURE = "verb/en_2p_future"
    VERB_EN_3P_FUTURE = "verb/en_3p_future"  # "will eat" (gender-neutral)
    VERB_EN_3P_M_FUTURE = "verb/en_3p-m_future"  # "they(m.) will eat"
    VERB_EN_3P_F_FUTURE = "verb/en_3p-f_future"  # "they(f.) will eat"

    # Imperative
    VERB_EN_2S_IMP = "verb/en_2s_imp"
    VERB_EN_2P_IMP = "verb/en_2p_imp"

    # English noun forms (singular/plural only)
    NOUN_EN_SINGULAR = "noun/en_singular"
    NOUN_EN_PLURAL = "noun/en_plural"

    # English adjective forms (comparative degrees)
    ADJ_EN_POSITIVE = "adjective/en_positive"
    ADJ_EN_COMPARATIVE = "adjective/en_comparative"
    ADJ_EN_SUPERLATIVE = "adjective/en_superlative"

    # English adverb forms (comparative degrees)
    ADVERB_EN_POSITIVE = "adverb/en_positive"
    ADVERB_EN_COMPARATIVE = "adverb/en_comparative"
    ADVERB_EN_SUPERLATIVE = "adverb/en_superlative"

    # Lithuanian verb forms (person_tense with gender distinction)
    # Present tense
    VERB_LT_1S_PRESENT = "verb/lt_1s_present"
    VERB_LT_2S_PRESENT = "verb/lt_2s_present"
    VERB_LT_3S_PRESENT = "verb/lt_3s_present"  # "dirba" (gender-neutral, verb doesn't change)
    VERB_LT_3S_M_PRESENT = "verb/lt_3s-m_present"
    VERB_LT_3S_F_PRESENT = "verb/lt_3s-f_present"
    VERB_LT_1P_PRESENT = "verb/lt_1p_present"
    VERB_LT_2P_PRESENT = "verb/lt_2p_present"
    VERB_LT_3P_PRESENT = "verb/lt_3p_present"  # "dirba" (gender-neutral, verb doesn't change)
    VERB_LT_3P_M_PRESENT = "verb/lt_3p-m_present"
    VERB_LT_3P_F_PRESENT = "verb/lt_3p-f_present"

    # Past tense
    VERB_LT_1S_PAST = "verb/lt_1s_past"
    VERB_LT_2S_PAST = "verb/lt_2s_past"
    VERB_LT_3S_PAST = "verb/lt_3s_past"  # "dirbo" (gender-neutral, verb doesn't change)
    VERB_LT_3S_M_PAST = "verb/lt_3s-m_past"
    VERB_LT_3S_F_PAST = "verb/lt_3s-f_past"
    VERB_LT_1P_PAST = "verb/lt_1p_past"
    VERB_LT_2P_PAST = "verb/lt_2p_past"
    VERB_LT_3P_PAST = "verb/lt_3p_past"  # "dirbo" (gender-neutral, verb doesn't change)
    VERB_LT_3P_M_PAST = "verb/lt_3p-m_past"
    VERB_LT_3P_F_PAST = "verb/lt_3p-f_past"

    # Future tense
    VERB_LT_1S_FUTURE = "verb/lt_1s_future"
    VERB_LT_2S_FUTURE = "verb/lt_2s_future"
    VERB_LT_3S_FUTURE = "verb/lt_3s_future"  # "dirbs" (gender-neutral, verb doesn't change)
    VERB_LT_3S_M_FUTURE = "verb/lt_3s-m_future"
    VERB_LT_3S_F_FUTURE = "verb/lt_3s-f_future"
    VERB_LT_1P_FUTURE = "verb/lt_1p_future"
    VERB_LT_2P_FUTURE = "verb/lt_2p_future"
    VERB_LT_3P_FUTURE = "verb/lt_3p_future"  # "dirbs" (gender-neutral, verb doesn't change)
    VERB_LT_3P_M_FUTURE = "verb/lt_3p-m_future"
    VERB_LT_3P_F_FUTURE = "verb/lt_3p-f_future"

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

    # Lithuanian adverb forms (comparative degrees)
    ADVERB_LT_POSITIVE = "adverb/lt_positive"
    ADVERB_LT_COMPARATIVE = "adverb/lt_comparative"
    ADVERB_LT_SUPERLATIVE = "adverb/lt_superlative"

    # French noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_FR_SINGULAR = "noun/fr_singular"
    NOUN_FR_PLURAL = "noun/fr_plural"

    # French adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_FR_SINGULAR_M = "adjective/fr_singular_m"
    ADJ_FR_PLURAL_M = "adjective/fr_plural_m"
    ADJ_FR_SINGULAR_F = "adjective/fr_singular_f"
    ADJ_FR_PLURAL_F = "adjective/fr_plural_f"

    # French verb forms (8 persons × 4 tenses = 32 forms)
    # Present tense (présent de l'indicatif)
    VERB_FR_1S_PRESENT = "verb/fr_1s_present"
    VERB_FR_2S_PRESENT = "verb/fr_2s_present"
    VERB_FR_3S_PRESENT = "verb/fr_3s_present"  # "va" (gender-neutral)
    VERB_FR_3S_M_PRESENT = "verb/fr_3s-m_present"
    VERB_FR_3S_F_PRESENT = "verb/fr_3s-f_present"
    VERB_FR_1P_PRESENT = "verb/fr_1p_present"
    VERB_FR_2P_PRESENT = "verb/fr_2p_present"
    VERB_FR_3P_PRESENT = "verb/fr_3p_present"  # "vont" (gender-neutral)
    VERB_FR_3P_M_PRESENT = "verb/fr_3p-m_present"
    VERB_FR_3P_F_PRESENT = "verb/fr_3p-f_present"

    # Imperfect (imparfait)
    VERB_FR_1S_IMPF = "verb/fr_1s_impf"
    VERB_FR_2S_IMPF = "verb/fr_2s_impf"
    VERB_FR_3S_IMPF = "verb/fr_3s_impf"  # "allait" (gender-neutral)
    VERB_FR_3S_M_IMPF = "verb/fr_3s-m_impf"
    VERB_FR_3S_F_IMPF = "verb/fr_3s-f_impf"
    VERB_FR_1P_IMPF = "verb/fr_1p_impf"
    VERB_FR_2P_IMPF = "verb/fr_2p_impf"
    VERB_FR_3P_IMPF = "verb/fr_3p_impf"  # "allaient" (gender-neutral)
    VERB_FR_3P_M_IMPF = "verb/fr_3p-m_impf"
    VERB_FR_3P_F_IMPF = "verb/fr_3p-f_impf"

    # Future (futur simple)
    VERB_FR_1S_FUTURE = "verb/fr_1s_future"
    VERB_FR_2S_FUTURE = "verb/fr_2s_future"
    VERB_FR_3S_FUTURE = "verb/fr_3s_future"  # "ira" (gender-neutral)
    VERB_FR_3S_M_FUTURE = "verb/fr_3s-m_future"
    VERB_FR_3S_F_FUTURE = "verb/fr_3s-f_future"
    VERB_FR_1P_FUTURE = "verb/fr_1p_future"
    VERB_FR_2P_FUTURE = "verb/fr_2p_future"
    VERB_FR_3P_FUTURE = "verb/fr_3p_future"  # "iront" (gender-neutral)
    VERB_FR_3P_M_FUTURE = "verb/fr_3p-m_future"
    VERB_FR_3P_F_FUTURE = "verb/fr_3p-f_future"

    # Passé composé (compound past with auxiliary)
    VERB_FR_1S_PC = "verb/fr_1s_pc"
    VERB_FR_2S_PC = "verb/fr_2s_pc"
    VERB_FR_3S_PC = "verb/fr_3s_pc"  # "est allé" (gender-neutral, but participle may vary)
    VERB_FR_3S_M_PC = "verb/fr_3s-m_pc"
    VERB_FR_3S_F_PC = "verb/fr_3s-f_pc"
    VERB_FR_1P_PC = "verb/fr_1p_pc"
    VERB_FR_2P_PC = "verb/fr_2p_pc"
    VERB_FR_3P_PC = "verb/fr_3p_pc"  # "sont allés" (gender-neutral, but participle may vary)
    VERB_FR_3P_M_PC = "verb/fr_3p-m_pc"
    VERB_FR_3P_F_PC = "verb/fr_3p-f_pc"

    # Past participles (masculine and feminine forms)
    VERB_FR_PC_M = "verb/fr_pc_m"  # masculine past participle, e.g., "allé"
    VERB_FR_PC_F = "verb/fr_pc_f"  # feminine past participle, e.g., "allée"

    # Spanish noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_ES_SINGULAR = "noun/es_singular"
    NOUN_ES_PLURAL = "noun/es_plural"

    # Spanish adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_ES_SINGULAR_M = "adjective/es_singular_m"
    ADJ_ES_PLURAL_M = "adjective/es_plural_m"
    ADJ_ES_SINGULAR_F = "adjective/es_singular_f"
    ADJ_ES_PLURAL_F = "adjective/es_plural_f"

    # Spanish verb forms (8 persons × 3 tenses = 24 forms)
    # Present tense (presente de indicativo)
    VERB_ES_1S_PRESENT = "verb/es_1s_present"
    VERB_ES_2S_PRESENT = "verb/es_2s_present"
    VERB_ES_3S_PRESENT = "verb/es_3s_present"  # "va" (gender-neutral)
    VERB_ES_3S_M_PRESENT = "verb/es_3s-m_present"
    VERB_ES_3S_F_PRESENT = "verb/es_3s-f_present"
    VERB_ES_1P_PRESENT = "verb/es_1p_present"
    VERB_ES_2P_PRESENT = "verb/es_2p_present"
    VERB_ES_3P_PRESENT = "verb/es_3p_present"  # "van" (gender-neutral)
    VERB_ES_3P_M_PRESENT = "verb/es_3p-m_present"
    VERB_ES_3P_F_PRESENT = "verb/es_3p-f_present"

    # Preterite (pretérito perfecto simple - simple past)
    VERB_ES_1S_PAST = "verb/es_1s_past"
    VERB_ES_2S_PAST = "verb/es_2s_past"
    VERB_ES_3S_PAST = "verb/es_3s_past"  # "fue" (gender-neutral)
    VERB_ES_3S_M_PAST = "verb/es_3s-m_past"
    VERB_ES_3S_F_PAST = "verb/es_3s-f_past"
    VERB_ES_1P_PAST = "verb/es_1p_past"
    VERB_ES_2P_PAST = "verb/es_2p_past"
    VERB_ES_3P_PAST = "verb/es_3p_past"  # "fueron" (gender-neutral)
    VERB_ES_3P_M_PAST = "verb/es_3p-m_past"
    VERB_ES_3P_F_PAST = "verb/es_3p-f_past"

    # Future (futuro simple)
    VERB_ES_1S_FUTURE = "verb/es_1s_future"
    VERB_ES_2S_FUTURE = "verb/es_2s_future"
    VERB_ES_3S_FUTURE = "verb/es_3s_future"  # "irá" (gender-neutral)
    VERB_ES_3S_M_FUTURE = "verb/es_3s-m_future"
    VERB_ES_3S_F_FUTURE = "verb/es_3s-f_future"
    VERB_ES_1P_FUTURE = "verb/es_1p_future"
    VERB_ES_2P_FUTURE = "verb/es_2p_future"
    VERB_ES_3P_FUTURE = "verb/es_3p_future"  # "irán" (gender-neutral)
    VERB_ES_3P_M_FUTURE = "verb/es_3p-m_future"
    VERB_ES_3P_F_FUTURE = "verb/es_3p-f_future"

    # German noun forms (4 cases × 2 numbers = 8 forms)
    # Singular
    NOUN_DE_NOMINATIVE_SINGULAR = "noun/de_nominative_singular"
    NOUN_DE_ACCUSATIVE_SINGULAR = "noun/de_accusative_singular"
    NOUN_DE_DATIVE_SINGULAR = "noun/de_dative_singular"
    NOUN_DE_GENITIVE_SINGULAR = "noun/de_genitive_singular"
    # Plural
    NOUN_DE_NOMINATIVE_PLURAL = "noun/de_nominative_plural"
    NOUN_DE_ACCUSATIVE_PLURAL = "noun/de_accusative_plural"
    NOUN_DE_DATIVE_PLURAL = "noun/de_dative_plural"
    NOUN_DE_GENITIVE_PLURAL = "noun/de_genitive_plural"

    # German adjective forms (2 genders × 2 numbers = 4 forms, simplified)
    ADJ_DE_SINGULAR_M = "adjective/de_singular_m"
    ADJ_DE_PLURAL_M = "adjective/de_plural_m"
    ADJ_DE_SINGULAR_F = "adjective/de_singular_f"
    ADJ_DE_PLURAL_F = "adjective/de_plural_f"

    # German verb forms (8 persons × 3 tenses = 24 forms)
    # Present tense (Präsens)
    VERB_DE_1S_PRESENT = "verb/de_1s_present"
    VERB_DE_2S_PRESENT = "verb/de_2s_present"
    VERB_DE_3S_PRESENT = "verb/de_3s_present"  # "geht" (gender-neutral)
    VERB_DE_3S_M_PRESENT = "verb/de_3s-m_present"
    VERB_DE_3S_F_PRESENT = "verb/de_3s-f_present"
    VERB_DE_1P_PRESENT = "verb/de_1p_present"
    VERB_DE_2P_PRESENT = "verb/de_2p_present"
    VERB_DE_3P_PRESENT = "verb/de_3p_present"  # "gehen" (gender-neutral)
    VERB_DE_3P_M_PRESENT = "verb/de_3p-m_present"
    VERB_DE_3P_F_PRESENT = "verb/de_3p-f_present"

    # Perfect (Perfekt - compound past, most common in spoken German)
    VERB_DE_1S_PAST = "verb/de_1s_past"
    VERB_DE_2S_PAST = "verb/de_2s_past"
    VERB_DE_3S_PAST = "verb/de_3s_past"  # "hat gegangen" (gender-neutral)
    VERB_DE_3S_M_PAST = "verb/de_3s-m_past"
    VERB_DE_3S_F_PAST = "verb/de_3s-f_past"
    VERB_DE_1P_PAST = "verb/de_1p_past"
    VERB_DE_2P_PAST = "verb/de_2p_past"
    VERB_DE_3P_PAST = "verb/de_3p_past"  # "haben gegangen" (gender-neutral)
    VERB_DE_3P_M_PAST = "verb/de_3p-m_past"
    VERB_DE_3P_F_PAST = "verb/de_3p-f_past"

    # Future (Futur I)
    VERB_DE_1S_FUTURE = "verb/de_1s_future"
    VERB_DE_2S_FUTURE = "verb/de_2s_future"
    VERB_DE_3S_FUTURE = "verb/de_3s_future"  # "wird gehen" (gender-neutral)
    VERB_DE_3S_M_FUTURE = "verb/de_3s-m_future"
    VERB_DE_3S_F_FUTURE = "verb/de_3s-f_future"
    VERB_DE_1P_FUTURE = "verb/de_1p_future"
    VERB_DE_2P_FUTURE = "verb/de_2p_future"
    VERB_DE_3P_FUTURE = "verb/de_3p_future"  # "werden gehen" (gender-neutral)
    VERB_DE_3P_M_FUTURE = "verb/de_3p-m_future"
    VERB_DE_3P_F_FUTURE = "verb/de_3p-f_future"

    # Portuguese noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_PT_SINGULAR = "noun/pt_singular"
    NOUN_PT_PLURAL = "noun/pt_plural"

    # Portuguese adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_PT_SINGULAR_M = "adjective/pt_singular_m"
    ADJ_PT_PLURAL_M = "adjective/pt_plural_m"
    ADJ_PT_SINGULAR_F = "adjective/pt_singular_f"
    ADJ_PT_PLURAL_F = "adjective/pt_plural_f"

    # Portuguese verb forms (8 persons × 3 tenses = 24 forms)
    # Present tense (presente do indicativo)
    VERB_PT_1S_PRESENT = "verb/pt_1s_present"
    VERB_PT_2S_PRESENT = "verb/pt_2s_present"
    VERB_PT_3S_PRESENT = "verb/pt_3s_present"  # "vai" (gender-neutral)
    VERB_PT_3S_M_PRESENT = "verb/pt_3s-m_present"
    VERB_PT_3S_F_PRESENT = "verb/pt_3s-f_present"
    VERB_PT_1P_PRESENT = "verb/pt_1p_present"
    VERB_PT_2P_PRESENT = "verb/pt_2p_present"
    VERB_PT_3P_PRESENT = "verb/pt_3p_present"  # "vão" (gender-neutral)
    VERB_PT_3P_M_PRESENT = "verb/pt_3p-m_present"
    VERB_PT_3P_F_PRESENT = "verb/pt_3p-f_present"

    # Preterite (pretérito perfeito - simple past)
    VERB_PT_1S_PAST = "verb/pt_1s_past"
    VERB_PT_2S_PAST = "verb/pt_2s_past"
    VERB_PT_3S_PAST = "verb/pt_3s_past"  # "foi" (gender-neutral)
    VERB_PT_3S_M_PAST = "verb/pt_3s-m_past"
    VERB_PT_3S_F_PAST = "verb/pt_3s-f_past"
    VERB_PT_1P_PAST = "verb/pt_1p_past"
    VERB_PT_2P_PAST = "verb/pt_2p_past"
    VERB_PT_3P_PAST = "verb/pt_3p_past"  # "foram" (gender-neutral)
    VERB_PT_3P_M_PAST = "verb/pt_3p-m_past"
    VERB_PT_3P_F_PAST = "verb/pt_3p-f_past"

    # Future (futuro do presente)
    VERB_PT_1S_FUTURE = "verb/pt_1s_future"
    VERB_PT_2S_FUTURE = "verb/pt_2s_future"
    VERB_PT_3S_FUTURE = "verb/pt_3s_future"  # "irá" (gender-neutral)
    VERB_PT_3S_M_FUTURE = "verb/pt_3s-m_future"
    VERB_PT_3S_F_FUTURE = "verb/pt_3s-f_future"
    VERB_PT_1P_FUTURE = "verb/pt_1p_future"
    VERB_PT_2P_FUTURE = "verb/pt_2p_future"
    VERB_PT_3P_FUTURE = "verb/pt_3p_future"  # "irão" (gender-neutral)
    VERB_PT_3P_M_FUTURE = "verb/pt_3p-m_future"
    VERB_PT_3P_F_FUTURE = "verb/pt_3p-f_future"

    # Adverb forms
    ADVERB_POSITIVE = "adverb/positive"
    ADVERB_COMPARATIVE = "adverb/comparative"
    ADVERB_SUPERLATIVE = "adverb/superlative"

    # Language-specific adverb base forms (invariant adverbs)
    ADVERB_EN_BASE = "adverb/en_base"
    ADVERB_LT_BASE = "adverb/lt_base"
    ADVERB_FR_BASE = "adverb/fr_base"
    ADVERB_DE_BASE = "adverb/de_base"
    ADVERB_ES_BASE = "adverb/es_base"
    ADVERB_PT_BASE = "adverb/pt_base"
    ADVERB_KO_BASE = "adverb/ko_base"
    ADVERB_ZH_BASE = "adverb/zh_base"

    # Pronoun forms - English, French, Spanish, Portuguese (function-based)
    PRONOUN_EN_SUBJECTIVE = "pronoun/en_subjective"  # I, you, he, she, we, they
    PRONOUN_EN_OBJECTIVE = "pronoun/en_objective"  # me, you, him, her, us, them
    PRONOUN_EN_POSSESSIVE = "pronoun/en_possessive"  # my, your, his, her, our, their
    PRONOUN_EN_REFLEXIVE = "pronoun/en_reflexive"  # myself, yourself, himself, herself, ourselves, themselves

    PRONOUN_FR_SUBJECTIVE = "pronoun/fr_subjective"  # je, tu, il, elle, nous, vous, ils, elles
    PRONOUN_FR_OBJECTIVE = "pronoun/fr_objective"  # me, te, le, la, nous, vous, les
    PRONOUN_FR_POSSESSIVE = "pronoun/fr_possessive"  # mon, ton, son, notre, votre, leur
    PRONOUN_FR_REFLEXIVE = "pronoun/fr_reflexive"  # me, te, se, nous, vous, se

    PRONOUN_ES_SUBJECTIVE = "pronoun/es_subjective"  # yo, tú, él, ella, nosotros, vosotros, ellos, ellas
    PRONOUN_ES_OBJECTIVE = "pronoun/es_objective"  # me, te, lo, la, nos, os, los, las
    PRONOUN_ES_POSSESSIVE = "pronoun/es_possessive"  # mi, tu, su, nuestro, vuestro, su
    PRONOUN_ES_REFLEXIVE = "pronoun/es_reflexive"  # me, te, se, nos, os, se

    PRONOUN_PT_SUBJECTIVE = "pronoun/pt_subjective"  # eu, tu, ele, ela, nós, vós, eles, elas
    PRONOUN_PT_OBJECTIVE = "pronoun/pt_objective"  # me, te, o, a, nos, vos, os, as
    PRONOUN_PT_POSSESSIVE = "pronoun/pt_possessive"  # meu, teu, seu, nosso, vosso, seu
    PRONOUN_PT_REFLEXIVE = "pronoun/pt_reflexive"  # me, te, se, nos, vos, se

    # Pronoun forms - Lithuanian (case-based)
    # Nominative (subject)
    PRONOUN_LT_NOMINATIVE_1S = "pronoun/lt_nominative_1s"  # aš (I)
    PRONOUN_LT_NOMINATIVE_2S = "pronoun/lt_nominative_2s"  # tu (you)
    PRONOUN_LT_NOMINATIVE_3S_M = "pronoun/lt_nominative_3s_m"  # jis (he)
    PRONOUN_LT_NOMINATIVE_3S_F = "pronoun/lt_nominative_3s_f"  # ji (she)
    PRONOUN_LT_NOMINATIVE_1P = "pronoun/lt_nominative_1p"  # mes (we)
    PRONOUN_LT_NOMINATIVE_2P = "pronoun/lt_nominative_2p"  # jūs (you plural)
    PRONOUN_LT_NOMINATIVE_3P_M = "pronoun/lt_nominative_3p_m"  # jie (they masculine)
    PRONOUN_LT_NOMINATIVE_3P_F = "pronoun/lt_nominative_3p_f"  # jos (they feminine)

    # Genitive (possession, "of")
    PRONOUN_LT_GENITIVE_1S = "pronoun/lt_genitive_1s"  # manęs/mano (of me/my)
    PRONOUN_LT_GENITIVE_2S = "pronoun/lt_genitive_2s"  # tavęs/tavo (of you/your)
    PRONOUN_LT_GENITIVE_3S_M = "pronoun/lt_genitive_3s_m"  # jo (of him/his)
    PRONOUN_LT_GENITIVE_3S_F = "pronoun/lt_genitive_3s_f"  # jos (of her/her)
    PRONOUN_LT_GENITIVE_1P = "pronoun/lt_genitive_1p"  # mūsų (of us/our)
    PRONOUN_LT_GENITIVE_2P = "pronoun/lt_genitive_2p"  # jūsų (of you plural/your)
    PRONOUN_LT_GENITIVE_3P = "pronoun/lt_genitive_3p"  # jų (of them/their)

    # Dative (indirect object, "to")
    PRONOUN_LT_DATIVE_1S = "pronoun/lt_dative_1s"  # man (to me)
    PRONOUN_LT_DATIVE_2S = "pronoun/lt_dative_2s"  # tau (to you)
    PRONOUN_LT_DATIVE_3S_M = "pronoun/lt_dative_3s_m"  # jam (to him)
    PRONOUN_LT_DATIVE_3S_F = "pronoun/lt_dative_3s_f"  # jai (to her)
    PRONOUN_LT_DATIVE_1P = "pronoun/lt_dative_1p"  # mums (to us)
    PRONOUN_LT_DATIVE_2P = "pronoun/lt_dative_2p"  # jums (to you plural)
    PRONOUN_LT_DATIVE_3P = "pronoun/lt_dative_3p"  # jiems/joms (to them)

    # Accusative (direct object)
    PRONOUN_LT_ACCUSATIVE_1S = "pronoun/lt_accusative_1s"  # mane (me)
    PRONOUN_LT_ACCUSATIVE_2S = "pronoun/lt_accusative_2s"  # tave (you)
    PRONOUN_LT_ACCUSATIVE_3S_M = "pronoun/lt_accusative_3s_m"  # jį (him)
    PRONOUN_LT_ACCUSATIVE_3S_F = "pronoun/lt_accusative_3s_f"  # ją (her)
    PRONOUN_LT_ACCUSATIVE_1P = "pronoun/lt_accusative_1p"  # mus (us)
    PRONOUN_LT_ACCUSATIVE_2P = "pronoun/lt_accusative_2p"  # jus (you plural)
    PRONOUN_LT_ACCUSATIVE_3P_M = "pronoun/lt_accusative_3p_m"  # juos (them masculine)
    PRONOUN_LT_ACCUSATIVE_3P_F = "pronoun/lt_accusative_3p_f"  # jas (them feminine)

    # Instrumental (by means of)
    PRONOUN_LT_INSTRUMENTAL_1S = "pronoun/lt_instrumental_1s"  # manimi (by me)
    PRONOUN_LT_INSTRUMENTAL_2S = "pronoun/lt_instrumental_2s"  # tavimi (by you)
    PRONOUN_LT_INSTRUMENTAL_3S_M = "pronoun/lt_instrumental_3s_m"  # juo (by him)
    PRONOUN_LT_INSTRUMENTAL_3S_F = "pronoun/lt_instrumental_3s_f"  # ja (by her)
    PRONOUN_LT_INSTRUMENTAL_1P = "pronoun/lt_instrumental_1p"  # mumis (by us)
    PRONOUN_LT_INSTRUMENTAL_2P = "pronoun/lt_instrumental_2p"  # jumis (by you plural)
    PRONOUN_LT_INSTRUMENTAL_3P = "pronoun/lt_instrumental_3p"  # jais/jomis (by them)

    # Locative (location)
    PRONOUN_LT_LOCATIVE_1S = "pronoun/lt_locative_1s"  # manyje (in me)
    PRONOUN_LT_LOCATIVE_2S = "pronoun/lt_locative_2s"  # tavyje (in you)
    PRONOUN_LT_LOCATIVE_3S_M = "pronoun/lt_locative_3s_m"  # jame (in him)
    PRONOUN_LT_LOCATIVE_3S_F = "pronoun/lt_locative_3s_f"  # joje (in her)
    PRONOUN_LT_LOCATIVE_1P = "pronoun/lt_locative_1p"  # mumyse (in us)
    PRONOUN_LT_LOCATIVE_2P = "pronoun/lt_locative_2p"  # jumyse (in you plural)
    PRONOUN_LT_LOCATIVE_3P = "pronoun/lt_locative_3p"  # juose/jose (in them)

    # Pronoun forms - German (case-based, simplified)
    # Nominative
    PRONOUN_DE_NOMINATIVE_1S = "pronoun/de_nominative_1s"  # ich (I)
    PRONOUN_DE_NOMINATIVE_2S = "pronoun/de_nominative_2s"  # du (you)
    PRONOUN_DE_NOMINATIVE_3S_M = "pronoun/de_nominative_3s_m"  # er (he)
    PRONOUN_DE_NOMINATIVE_3S_F = "pronoun/de_nominative_3s_f"  # sie (she)
    PRONOUN_DE_NOMINATIVE_3S_N = "pronoun/de_nominative_3s_n"  # es (it)
    PRONOUN_DE_NOMINATIVE_1P = "pronoun/de_nominative_1p"  # wir (we)
    PRONOUN_DE_NOMINATIVE_2P = "pronoun/de_nominative_2p"  # ihr (you plural)
    PRONOUN_DE_NOMINATIVE_3P = "pronoun/de_nominative_3p"  # sie (they)

    # Accusative
    PRONOUN_DE_ACCUSATIVE_1S = "pronoun/de_accusative_1s"  # mich (me)
    PRONOUN_DE_ACCUSATIVE_2S = "pronoun/de_accusative_2s"  # dich (you)
    PRONOUN_DE_ACCUSATIVE_3S_M = "pronoun/de_accusative_3s_m"  # ihn (him)
    PRONOUN_DE_ACCUSATIVE_3S_F = "pronoun/de_accusative_3s_f"  # sie (her)
    PRONOUN_DE_ACCUSATIVE_3S_N = "pronoun/de_accusative_3s_n"  # es (it)
    PRONOUN_DE_ACCUSATIVE_1P = "pronoun/de_accusative_1p"  # uns (us)
    PRONOUN_DE_ACCUSATIVE_2P = "pronoun/de_accusative_2p"  # euch (you plural)
    PRONOUN_DE_ACCUSATIVE_3P = "pronoun/de_accusative_3p"  # sie (them)

    # Dative
    PRONOUN_DE_DATIVE_1S = "pronoun/de_dative_1s"  # mir (to me)
    PRONOUN_DE_DATIVE_2S = "pronoun/de_dative_2s"  # dir (to you)
    PRONOUN_DE_DATIVE_3S_M = "pronoun/de_dative_3s_m"  # ihm (to him)
    PRONOUN_DE_DATIVE_3S_F = "pronoun/de_dative_3s_f"  # ihr (to her)
    PRONOUN_DE_DATIVE_3S_N = "pronoun/de_dative_3s_n"  # ihm (to it)
    PRONOUN_DE_DATIVE_1P = "pronoun/de_dative_1p"  # uns (to us)
    PRONOUN_DE_DATIVE_2P = "pronoun/de_dative_2p"  # euch (to you plural)
    PRONOUN_DE_DATIVE_3P = "pronoun/de_dative_3p"  # ihnen (to them)

    # Genitive (less common for pronouns)
    PRONOUN_DE_GENITIVE_1S = "pronoun/de_genitive_1s"  # meiner (of me)
    PRONOUN_DE_GENITIVE_2S = "pronoun/de_genitive_2s"  # deiner (of you)
    PRONOUN_DE_GENITIVE_3S_M = "pronoun/de_genitive_3s_m"  # seiner (of him)
    PRONOUN_DE_GENITIVE_3S_F = "pronoun/de_genitive_3s_f"  # ihrer (of her)
    PRONOUN_DE_GENITIVE_3S_N = "pronoun/de_genitive_3s_n"  # seiner (of it)
    PRONOUN_DE_GENITIVE_1P = "pronoun/de_genitive_1p"  # unser (of us)
    PRONOUN_DE_GENITIVE_2P = "pronoun/de_genitive_2p"  # euer (of you plural)
    PRONOUN_DE_GENITIVE_3P = "pronoun/de_genitive_3p"  # ihrer (of them)

    # Pronoun forms - Chinese (person/number/gender, no case)
    PRONOUN_ZH_1S = "pronoun/zh_1s"  # 我 (I/me)
    PRONOUN_ZH_2S = "pronoun/zh_2s"  # 你 (you)
    PRONOUN_ZH_3S_M = "pronoun/zh_3s_m"  # 他 (he/him)
    PRONOUN_ZH_3S_F = "pronoun/zh_3s_f"  # 她 (she/her)
    PRONOUN_ZH_3S_N = "pronoun/zh_3s_n"  # 它 (it)
    PRONOUN_ZH_1P = "pronoun/zh_1p"  # 我们 (we/us)
    PRONOUN_ZH_2P = "pronoun/zh_2p"  # 你们 (you plural)
    PRONOUN_ZH_3P_M = "pronoun/zh_3p_m"  # 他们 (they masculine)
    PRONOUN_ZH_3P_F = "pronoun/zh_3p_f"  # 她们 (they feminine)
    PRONOUN_ZH_3P_N = "pronoun/zh_3p_n"  # 它们 (they neuter/things)

    # Pronoun forms - Korean (person/number, no case)
    PRONOUN_KO_1S = "pronoun/ko_1s"  # 나/저 (I/me)
    PRONOUN_KO_2S = "pronoun/ko_2s"  # 너/당신 (you)
    PRONOUN_KO_3S = "pronoun/ko_3s"  # 그/그녀 (he/she)
    PRONOUN_KO_1P = "pronoun/ko_1p"  # 우리 (we/us)
    PRONOUN_KO_2P = "pronoun/ko_2p"  # 너희/당신들 (you plural)
    PRONOUN_KO_3P = "pronoun/ko_3p"  # 그들 (they)

    # Legacy forms (deprecated - use language-specific forms above)
    PRONOUN_SUBJECTIVE = "pronoun/subjective"  # Deprecated: use pronoun/en_subjective
    PRONOUN_OBJECTIVE = "pronoun/objective"  # Deprecated: use pronoun/en_objective
    PRONOUN_POSSESSIVE = "pronoun/possessive"  # Deprecated: use pronoun/en_possessive
    PRONOUN_REFLEXIVE = "pronoun/reflexive"  # Deprecated: use pronoun/en_reflexive

    # Other parts of speech (typically invariant)
    PREPOSITION = "preposition/base"
    CONJUNCTION = "conjunction/base"
    INTERJECTION = "interjection/base"
    DETERMINER = "determiner/base"
    ARTICLE = "article/base"

    # Language-specific article forms
    ARTICLE_EN_BASE = "article/en_base"
    ARTICLE_FR_MASCULINE_SINGULAR = "article/fr_masculine_singular"
    ARTICLE_FR_FEMININE_SINGULAR = "article/fr_feminine_singular"
    ARTICLE_FR_PLURAL = "article/fr_plural"
    ARTICLE_DE_MASCULINE_SINGULAR = "article/de_masculine_singular"
    ARTICLE_DE_FEMININE_SINGULAR = "article/de_feminine_singular"
    ARTICLE_DE_NEUTER_SINGULAR = "article/de_neuter_singular"
    ARTICLE_DE_PLURAL = "article/de_plural"
    ARTICLE_ES_MASCULINE_SINGULAR = "article/es_masculine_singular"
    ARTICLE_ES_FEMININE_SINGULAR = "article/es_feminine_singular"
    ARTICLE_ES_PLURAL = "article/es_plural"
    ARTICLE_PT_MASCULINE_SINGULAR = "article/pt_masculine_singular"
    ARTICLE_PT_FEMININE_SINGULAR = "article/pt_feminine_singular"
    ARTICLE_PT_PLURAL = "article/pt_plural"

    # Generic forms
    BASE_FORM = "base_form"
    OTHER = "other"
