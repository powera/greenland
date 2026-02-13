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
    HONORIFIC = "honorific"  # Titles and forms of address (Sir, Lord, Mr., Mrs., Dr.)

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
    BUILDING_PART = (
        "building_part"  # Parts of buildings (door, window, wall, floor, ceiling, roof, stairs)
    )
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
    CHEMICAL_COMPOUND = (
        "chemical_compound"  # Chemical elements and compounds (oxygen, lithium, carbon dioxide)
    )
    MEDICATION_REMEDY = "medication_remedy"

    # Abstract Concepts and Ideas
    CONCEPT_IDEA = "concept_idea"
    COMMUNICATION_INFORMATION = "communication_information"  # Language, messages, information (word, language, message, news)
    TECHNOLOGY_DIGITAL = (
        "technology_digital"  # Digital/computing concepts (internet, email, website, data)
    )
    ABSTRACT_CONDITION = (
        "abstract_condition"  # Abstract conditions, situations (peace, danger, luck, fate)
    )
    SOCIAL_INSTITUTION = (
        "social_institution"  # Organizations, collective structures (government, army, company)
    )
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
    GROUP_ANIMAL = "animal_grouping_term"  # Measure words for animals (flock, herd, head)
    COLLECTION_THINGS = "collection_things"

    # Named Entities
    PERSONAL_NAME = "personal_name"
    PLACE_NAME = "place_name"  # Generic place nouns (room, street, etc.)
    COUNTRY = "country"  # Countries (Lithuania, France, Japan)
    CITY = "city"  # Cities (Vilnius, Paris, Tokyo)
    GEOGRAPHIC_PLACE = "geographic_place"  # Named geographic features (Atlantic Ocean, Pacific Ocean, Indian Ocean)
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
    EMOTION = "emotion"  # Emotional states (happy, sad, angry, excited, tired, scared)
    QUALITY = "quality"  # Evaluative and abstract properties (good, bad, excellent, important, possible, necessary, real, clear, simple)
    AESTHETIC = "aesthetic"  # Beauty or appearance (beautiful, ugly, pretty, handsome)
    IMPORTANCE = "importance"  # Importance or priority (important, essential, trivial, critical)
    ORIGIN = "origin"  # Origin or source (American, Chinese, domestic, foreign)
    PURPOSE = "purpose"  # Purpose or function (educational, medical, industrial, recreational)
    MATERIAL = "material"  # Material composition (wooden, metal, plastic, cotton)
    # DEFINITE_QUANTITY removed: moved to numeral POS
    INDEFINITE_QUANTITY = "indefinite_quantity"  # Inexact amounts (many, few, some, several)
    DURATION = "duration"  # Time duration (brief, long, eternal, temporary)
    FREQUENCY = "frequency"  # Frequency of occurrence (daily, occasional, rare, frequent)
    SEQUENCE = "sequence"  # Order or sequence (first, last, next, previous)
    OTHER = "other"


class NumeralSubtype(enum.Enum):
    """Subtypes for numerals.

    NOTE: When adding/modifying subtypes, update SUBTYPE_GUID_PREFIXES
    in guid_prefixes.py to keep GUID assignments in sync.
    """

    CARDINAL = "cardinal"  # Cardinal numbers (one, two, three, 100)
    ORDINAL = "ordinal"  # Ordinal numbers (first, second, third, 100th)


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

    # Italian noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_IT_SINGULAR = "noun/it_singular"
    NOUN_IT_PLURAL = "noun/it_plural"

    # Italian adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_IT_SINGULAR_M = "adjective/it_singular_m"
    ADJ_IT_PLURAL_M = "adjective/it_plural_m"
    ADJ_IT_SINGULAR_F = "adjective/it_singular_f"
    ADJ_IT_PLURAL_F = "adjective/it_plural_f"

    # Italian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (presente indicativo)
    VERB_IT_1S_PRESENT = "verb/it_1s_present"
    VERB_IT_2S_PRESENT = "verb/it_2s_present"
    VERB_IT_3S_PRESENT = "verb/it_3s_present"  # "va" (gender-neutral)
    VERB_IT_1P_PRESENT = "verb/it_1p_present"
    VERB_IT_2P_PRESENT = "verb/it_2p_present"
    VERB_IT_3P_PRESENT = "verb/it_3p_present"  # "vanno" (gender-neutral)

    # Passato remoto (simple past)
    VERB_IT_1S_PAST = "verb/it_1s_past"
    VERB_IT_2S_PAST = "verb/it_2s_past"
    VERB_IT_3S_PAST = "verb/it_3s_past"  # "andò" (gender-neutral)
    VERB_IT_1P_PAST = "verb/it_1p_past"
    VERB_IT_2P_PAST = "verb/it_2p_past"
    VERB_IT_3P_PAST = "verb/it_3p_past"  # "andarono" (gender-neutral)

    # Future (futuro semplice)
    VERB_IT_1S_FUTURE = "verb/it_1s_future"
    VERB_IT_2S_FUTURE = "verb/it_2s_future"
    VERB_IT_3S_FUTURE = "verb/it_3s_future"  # "andrà" (gender-neutral)
    VERB_IT_1P_FUTURE = "verb/it_1p_future"
    VERB_IT_2P_FUTURE = "verb/it_2p_future"
    VERB_IT_3P_FUTURE = "verb/it_3p_future"  # "andranno" (gender-neutral)

    # Swedish noun forms (singular/plural only)
    NOUN_SV_SINGULAR = "noun/sv_singular"
    NOUN_SV_PLURAL = "noun/sv_plural"

    # Swedish verb forms (one form per tense — Swedish does not conjugate by person)
    VERB_SV_PRESENT = "verb/sv_present"  # Presens: e.g. "talar", "springer"
    VERB_SV_PAST = "verb/sv_past"  # Preteritum: e.g. "talade", "sprang"
    VERB_SV_FUTURE = "verb/sv_future"  # Futurum: e.g. "ska tala", "ska springa"

    # Dutch noun forms (singular/plural only - each noun has a fixed gender)
    NOUN_NL_SINGULAR = "noun/nl_singular"
    NOUN_NL_PLURAL = "noun/nl_plural"

    # Dutch adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_NL_SINGULAR_M = "adjective/nl_singular_m"
    ADJ_NL_PLURAL_M = "adjective/nl_plural_m"
    ADJ_NL_SINGULAR_F = "adjective/nl_singular_f"
    ADJ_NL_PLURAL_F = "adjective/nl_plural_f"

    # Dutch verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (onvoltooid tegenwoordige tijd)
    VERB_NL_1S_PRESENT = "verb/nl_1s_present"
    VERB_NL_2S_PRESENT = "verb/nl_2s_present"
    VERB_NL_3S_PRESENT = "verb/nl_3s_present"  # "gaat" (gender-neutral)
    VERB_NL_1P_PRESENT = "verb/nl_1p_present"
    VERB_NL_2P_PRESENT = "verb/nl_2p_present"
    VERB_NL_3P_PRESENT = "verb/nl_3p_present"  # "gaan" (gender-neutral)

    # Past tense (onvoltooid verleden tijd / imperfectum)
    VERB_NL_1S_PAST = "verb/nl_1s_past"
    VERB_NL_2S_PAST = "verb/nl_2s_past"
    VERB_NL_3S_PAST = "verb/nl_3s_past"  # "ging" (gender-neutral)
    VERB_NL_1P_PAST = "verb/nl_1p_past"
    VERB_NL_2P_PAST = "verb/nl_2p_past"
    VERB_NL_3P_PAST = "verb/nl_3p_past"  # "gingen" (gender-neutral)

    # Future (onvoltooid toekomende tijd)
    VERB_NL_1S_FUTURE = "verb/nl_1s_future"
    VERB_NL_2S_FUTURE = "verb/nl_2s_future"
    VERB_NL_3S_FUTURE = "verb/nl_3s_future"  # "zal gaan" (gender-neutral)
    VERB_NL_1P_FUTURE = "verb/nl_1p_future"
    VERB_NL_2P_FUTURE = "verb/nl_2p_future"
    VERB_NL_3P_FUTURE = "verb/nl_3p_future"  # "zullen gaan" (gender-neutral)

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
    ADVERB_IT_BASE = "adverb/it_base"
    ADVERB_SV_BASE = "adverb/sv_base"
    ADVERB_NL_BASE = "adverb/nl_base"
    ADVERB_KO_BASE = "adverb/ko_base"
    ADVERB_ZH_BASE = "adverb/zh_base"

    # Pronoun forms - English, French, Spanish, Portuguese (function-based, simplified)
    # Word itself indicates person/number/gender; tag indicates grammatical function
    PRONOUN_EN_SUBJECTIVE = "pronoun/en_subjective"  # I, you, he, she, we, they
    PRONOUN_EN_OBJECTIVE = "pronoun/en_objective"  # me, you, him, her, us, them
    PRONOUN_EN_POSSESSIVE = (
        "pronoun/en_possessive"  # mine, yours, his, hers, ours, theirs (standalone)
    )
    PRONOUN_EN_REFLEXIVE = (
        "pronoun/en_reflexive"  # myself, yourself, himself, herself, ourselves, themselves
    )

    PRONOUN_FR_SUBJECTIVE = "pronoun/fr_subjective"  # je, tu, il, elle, nous, vous, ils, elles
    PRONOUN_FR_OBJECTIVE = "pronoun/fr_objective"  # me, te, le, la, nous, vous, les
    PRONOUN_FR_POSSESSIVE = (
        "pronoun/fr_possessive"  # le mien, le tien, le sien (standalone possessives)
    )
    PRONOUN_FR_REFLEXIVE = "pronoun/fr_reflexive"  # me, te, se, nous, vous, se

    PRONOUN_ES_SUBJECTIVE = (
        "pronoun/es_subjective"  # yo, tú, él, ella, nosotros, vosotros, ellos, ellas
    )
    PRONOUN_ES_OBJECTIVE = "pronoun/es_objective"  # me, te, lo, la, nos, os, los, las
    PRONOUN_ES_POSSESSIVE = "pronoun/es_possessive"  # mío, tuyo, suyo (standalone possessives)
    PRONOUN_ES_REFLEXIVE = "pronoun/es_reflexive"  # me, te, se, nos, os, se

    PRONOUN_PT_SUBJECTIVE = "pronoun/pt_subjective"  # eu, tu, ele, ela, nós, vós, eles, elas
    PRONOUN_PT_OBJECTIVE = "pronoun/pt_objective"  # me, te, o, a, nos, vos, os, as
    PRONOUN_PT_POSSESSIVE = "pronoun/pt_possessive"  # meu, teu, seu (standalone possessives)
    PRONOUN_PT_REFLEXIVE = "pronoun/pt_reflexive"  # me, te, se, nos, vos, se

    # Pronoun forms - Lithuanian (case-based, simplified)
    # Word itself indicates person/number/gender; tag indicates grammatical case
    PRONOUN_LT_NOMINATIVE = "pronoun/lt_nominative"  # aš, tu, jis, ji, mes, jūs, jie, jos
    PRONOUN_LT_GENITIVE = "pronoun/lt_genitive"  # manęs, tavęs, jo, jos, mūsų, jūsų, jų
    PRONOUN_LT_DATIVE = "pronoun/lt_dative"  # man, tau, jam, jai, mums, jums, jiems, joms
    PRONOUN_LT_ACCUSATIVE = "pronoun/lt_accusative"  # mane, tave, jį, ją, mus, jus, juos, jas
    PRONOUN_LT_INSTRUMENTAL = (
        "pronoun/lt_instrumental"  # manimi, tavimi, juo, ja, mumis, jumis, jais, jomis
    )
    PRONOUN_LT_LOCATIVE = (
        "pronoun/lt_locative"  # manyje, tavyje, jame, joje, mumyse, jumyse, juose, jose
    )
    PRONOUN_LT_POSSESSIVE = (
        "pronoun/lt_possessive"  # mano, tavo, etc. (standalone possessive forms)
    )

    # Pronoun forms - German (case-based, simplified)
    # Word itself indicates person/number/gender; tag indicates grammatical case
    PRONOUN_DE_NOMINATIVE = "pronoun/de_nominative"  # ich, du, er, sie, es, wir, ihr, sie
    PRONOUN_DE_ACCUSATIVE = "pronoun/de_accusative"  # mich, dich, ihn, sie, es, uns, euch, sie
    PRONOUN_DE_DATIVE = "pronoun/de_dative"  # mir, dir, ihm, ihr, ihm, uns, euch, ihnen
    PRONOUN_DE_GENITIVE = "pronoun/de_genitive"  # meiner, deiner, seiner, ihrer (rare)
    PRONOUN_DE_POSSESSIVE = (
        "pronoun/de_possessive"  # meiner/meine, deiner/deine (standalone possessives)
    )
    PRONOUN_DE_REFLEXIVE = "pronoun/de_reflexive"  # sich (reflexive pronoun)

    # Pronoun forms - Chinese (simplified)
    # Word itself indicates person/number/gender; tag indicates function
    PRONOUN_ZH_SUBJECTIVE = (
        "pronoun/zh_subjective"  # 我, 你, 他, 她, 它, 我们, 你们, 他们, 她们, 它们
    )
    PRONOUN_ZH_POSSESSIVE = "pronoun/zh_possessive"  # 我的, 你的, 他的, 她的, 它的 (with 的)

    # Pronoun forms - Korean (simplified)
    # Word itself indicates person/number/formality; tag indicates function
    PRONOUN_KO_SUBJECTIVE = "pronoun/ko_subjective"  # 나, 저, 너, 그, 그녀, 우리, 너희, 그들
    PRONOUN_KO_POSSESSIVE = "pronoun/ko_possessive"  # 나의/내, 저의/제, 우리의/우리

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

    # Numeral forms
    # For numerals, the lemma form is typically masculine singular where gender applies.
    # Cardinal numerals answer "how many?" (one, two, three)
    # Ordinal numerals answer "which position?" (first, second, third)

    # English numerals (invariant - no gender/case)
    NUMERAL_EN_CARDINAL = "numeral/en_cardinal"  # one, two, three
    NUMERAL_EN_ORDINAL = "numeral/en_ordinal"  # first, second, third

    # Lithuanian numerals (gender for 1-9, some case variation)
    # Lemma form is masculine nominative
    NUMERAL_LT_CARDINAL_M = "numeral/lt_cardinal_m"  # vienas, du, trys (masculine)
    NUMERAL_LT_CARDINAL_F = "numeral/lt_cardinal_f"  # viena, dvi, trys (feminine)
    NUMERAL_LT_ORDINAL_M = "numeral/lt_ordinal_m"  # pirmas, antras (masculine)
    NUMERAL_LT_ORDINAL_F = "numeral/lt_ordinal_f"  # pirma, antra (feminine)

    # German numerals (gender for ein/eine/ein only; others invariant)
    # Lemma form is masculine nominative
    NUMERAL_DE_CARDINAL_M = "numeral/de_cardinal_m"  # ein (masculine)
    NUMERAL_DE_CARDINAL_F = "numeral/de_cardinal_f"  # eine (feminine)
    NUMERAL_DE_CARDINAL_N = "numeral/de_cardinal_n"  # ein (neuter)
    NUMERAL_DE_ORDINAL = "numeral/de_ordinal"  # erste, zweite, dritte

    # French numerals (gender for un/une only; others invariant)
    NUMERAL_FR_CARDINAL_M = "numeral/fr_cardinal_m"  # un (masculine)
    NUMERAL_FR_CARDINAL_F = "numeral/fr_cardinal_f"  # une (feminine)
    NUMERAL_FR_ORDINAL_M = "numeral/fr_ordinal_m"  # premier (masculine)
    NUMERAL_FR_ORDINAL_F = "numeral/fr_ordinal_f"  # première (feminine)

    # Spanish numerals (gender for uno/una and ordinals)
    NUMERAL_ES_CARDINAL_M = "numeral/es_cardinal_m"  # un, uno (masculine)
    NUMERAL_ES_CARDINAL_F = "numeral/es_cardinal_f"  # una (feminine)
    NUMERAL_ES_ORDINAL_M = "numeral/es_ordinal_m"  # primero (masculine)
    NUMERAL_ES_ORDINAL_F = "numeral/es_ordinal_f"  # primera (feminine)

    # Portuguese numerals (gender for um/uma and ordinals)
    NUMERAL_PT_CARDINAL_M = "numeral/pt_cardinal_m"  # um (masculine)
    NUMERAL_PT_CARDINAL_F = "numeral/pt_cardinal_f"  # uma (feminine)
    NUMERAL_PT_ORDINAL_M = "numeral/pt_ordinal_m"  # primeiro (masculine)
    NUMERAL_PT_ORDINAL_F = "numeral/pt_ordinal_f"  # primeira (feminine)

    # Chinese numerals
    # Cardinal: 一, 二, 三 (standard counting form)
    # Quantity: 一, 两, 三 (两 used before measure words for "two")
    NUMERAL_ZH_CARDINAL = "numeral/zh_cardinal"  # 一, 二, 三, 四, 五...
    NUMERAL_ZH_QUANTITY = (
        "numeral/zh_quantity"  # 一, 两, 三... (两 replaces 二 before measure words)
    )
    NUMERAL_ZH_ORDINAL = "numeral/zh_ordinal"  # 第一, 第二, 第三...

    # Korean numerals (native Korean vs Sino-Korean systems)
    NUMERAL_KO_NATIVE = "numeral/ko_native"  # 하나, 둘, 셋 (native Korean, for counting)
    NUMERAL_KO_SINO = "numeral/ko_sino"  # 일, 이, 삼 (Sino-Korean, for dates/numbers)
    NUMERAL_KO_ORDINAL = "numeral/ko_ordinal"  # 첫째, 둘째, 셋째

    # Romanian noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_RO_SINGULAR = "noun/ro_singular"
    NOUN_RO_PLURAL = "noun/ro_plural"

    # Romanian adjective forms (2 genders × 2 numbers = 4 forms)
    ADJ_RO_SINGULAR_M = "adjective/ro_singular_m"
    ADJ_RO_PLURAL_M = "adjective/ro_plural_m"
    ADJ_RO_SINGULAR_F = "adjective/ro_singular_f"
    ADJ_RO_PLURAL_F = "adjective/ro_plural_f"

    # Romanian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (prezent)
    VERB_RO_1S_PRESENT = "verb/ro_1s_present"
    VERB_RO_2S_PRESENT = "verb/ro_2s_present"
    VERB_RO_3S_PRESENT = "verb/ro_3s_present"
    VERB_RO_1P_PRESENT = "verb/ro_1p_present"
    VERB_RO_2P_PRESENT = "verb/ro_2p_present"
    VERB_RO_3P_PRESENT = "verb/ro_3p_present"
    # Past tense (perfect compus)
    VERB_RO_1S_PAST = "verb/ro_1s_past"
    VERB_RO_2S_PAST = "verb/ro_2s_past"
    VERB_RO_3S_PAST = "verb/ro_3s_past"
    VERB_RO_1P_PAST = "verb/ro_1p_past"
    VERB_RO_2P_PAST = "verb/ro_2p_past"
    VERB_RO_3P_PAST = "verb/ro_3p_past"
    # Future tense (viitor)
    VERB_RO_1S_FUTURE = "verb/ro_1s_future"
    VERB_RO_2S_FUTURE = "verb/ro_2s_future"
    VERB_RO_3S_FUTURE = "verb/ro_3s_future"
    VERB_RO_1P_FUTURE = "verb/ro_1p_future"
    VERB_RO_2P_FUTURE = "verb/ro_2p_future"
    VERB_RO_3P_FUTURE = "verb/ro_3p_future"

    # Polish noun forms (7 cases × 2 numbers = 14 forms)
    # Singular
    NOUN_PL_NOMINATIVE_SINGULAR = "noun/pl_nominative_singular"
    NOUN_PL_GENITIVE_SINGULAR = "noun/pl_genitive_singular"
    NOUN_PL_DATIVE_SINGULAR = "noun/pl_dative_singular"
    NOUN_PL_ACCUSATIVE_SINGULAR = "noun/pl_accusative_singular"
    NOUN_PL_INSTRUMENTAL_SINGULAR = "noun/pl_instrumental_singular"
    NOUN_PL_LOCATIVE_SINGULAR = "noun/pl_locative_singular"
    NOUN_PL_VOCATIVE_SINGULAR = "noun/pl_vocative_singular"
    # Plural
    NOUN_PL_NOMINATIVE_PLURAL = "noun/pl_nominative_plural"
    NOUN_PL_GENITIVE_PLURAL = "noun/pl_genitive_plural"
    NOUN_PL_DATIVE_PLURAL = "noun/pl_dative_plural"
    NOUN_PL_ACCUSATIVE_PLURAL = "noun/pl_accusative_plural"
    NOUN_PL_INSTRUMENTAL_PLURAL = "noun/pl_instrumental_plural"
    NOUN_PL_LOCATIVE_PLURAL = "noun/pl_locative_plural"
    NOUN_PL_VOCATIVE_PLURAL = "noun/pl_vocative_plural"

    # Polish adjective forms (2 genders × 2 numbers = 4 simplified forms)
    ADJ_PL_SINGULAR_M = "adjective/pl_singular_m"
    ADJ_PL_PLURAL_M = "adjective/pl_plural_m"
    ADJ_PL_SINGULAR_F = "adjective/pl_singular_f"
    ADJ_PL_PLURAL_F = "adjective/pl_plural_f"

    # Polish verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (czas teraźniejszy)
    VERB_PL_1S_PRESENT = "verb/pl_1s_present"
    VERB_PL_2S_PRESENT = "verb/pl_2s_present"
    VERB_PL_3S_PRESENT = "verb/pl_3s_present"
    VERB_PL_1P_PRESENT = "verb/pl_1p_present"
    VERB_PL_2P_PRESENT = "verb/pl_2p_present"
    VERB_PL_3P_PRESENT = "verb/pl_3p_present"
    # Past tense (czas przeszły)
    VERB_PL_1S_PAST = "verb/pl_1s_past"
    VERB_PL_2S_PAST = "verb/pl_2s_past"
    VERB_PL_3S_PAST = "verb/pl_3s_past"
    VERB_PL_1P_PAST = "verb/pl_1p_past"
    VERB_PL_2P_PAST = "verb/pl_2p_past"
    VERB_PL_3P_PAST = "verb/pl_3p_past"
    # Future tense (czas przyszły)
    VERB_PL_1S_FUTURE = "verb/pl_1s_future"
    VERB_PL_2S_FUTURE = "verb/pl_2s_future"
    VERB_PL_3S_FUTURE = "verb/pl_3s_future"
    VERB_PL_1P_FUTURE = "verb/pl_1p_future"
    VERB_PL_2P_FUTURE = "verb/pl_2p_future"
    VERB_PL_3P_FUTURE = "verb/pl_3p_future"

    # Tamil noun forms (singular/plural only)
    NOUN_TA_SINGULAR = "noun/ta_singular"
    NOUN_TA_PLURAL = "noun/ta_plural"

    # Tamil verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (நிகழ்காலம்)
    VERB_TA_1S_PRESENT = "verb/ta_1s_present"
    VERB_TA_2S_PRESENT = "verb/ta_2s_present"
    VERB_TA_3S_PRESENT = "verb/ta_3s_present"
    VERB_TA_1P_PRESENT = "verb/ta_1p_present"
    VERB_TA_2P_PRESENT = "verb/ta_2p_present"
    VERB_TA_3P_PRESENT = "verb/ta_3p_present"
    # Past tense (இறந்தகாலம்)
    VERB_TA_1S_PAST = "verb/ta_1s_past"
    VERB_TA_2S_PAST = "verb/ta_2s_past"
    VERB_TA_3S_PAST = "verb/ta_3s_past"
    VERB_TA_1P_PAST = "verb/ta_1p_past"
    VERB_TA_2P_PAST = "verb/ta_2p_past"
    VERB_TA_3P_PAST = "verb/ta_3p_past"
    # Future tense (எதிர்காலம்)
    VERB_TA_1S_FUTURE = "verb/ta_1s_future"
    VERB_TA_2S_FUTURE = "verb/ta_2s_future"
    VERB_TA_3S_FUTURE = "verb/ta_3s_future"
    VERB_TA_1P_FUTURE = "verb/ta_1p_future"
    VERB_TA_2P_FUTURE = "verb/ta_2p_future"
    VERB_TA_3P_FUTURE = "verb/ta_3p_future"

    # Telugu noun forms (singular/plural only)
    NOUN_TE_SINGULAR = "noun/te_singular"
    NOUN_TE_PLURAL = "noun/te_plural"

    # Telugu verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (వర్తమానకాలం)
    VERB_TE_1S_PRESENT = "verb/te_1s_present"
    VERB_TE_2S_PRESENT = "verb/te_2s_present"
    VERB_TE_3S_PRESENT = "verb/te_3s_present"
    VERB_TE_1P_PRESENT = "verb/te_1p_present"
    VERB_TE_2P_PRESENT = "verb/te_2p_present"
    VERB_TE_3P_PRESENT = "verb/te_3p_present"
    # Past tense (భూతకాలం)
    VERB_TE_1S_PAST = "verb/te_1s_past"
    VERB_TE_2S_PAST = "verb/te_2s_past"
    VERB_TE_3S_PAST = "verb/te_3s_past"
    VERB_TE_1P_PAST = "verb/te_1p_past"
    VERB_TE_2P_PAST = "verb/te_2p_past"
    VERB_TE_3P_PAST = "verb/te_3p_past"
    # Future tense (భవిష్యత్కాలం)
    VERB_TE_1S_FUTURE = "verb/te_1s_future"
    VERB_TE_2S_FUTURE = "verb/te_2s_future"
    VERB_TE_3S_FUTURE = "verb/te_3s_future"
    VERB_TE_1P_FUTURE = "verb/te_1p_future"
    VERB_TE_2P_FUTURE = "verb/te_2p_future"
    VERB_TE_3P_FUTURE = "verb/te_3p_future"

    # Kannada noun forms (singular/plural only)
    NOUN_KN_SINGULAR = "noun/kn_singular"
    NOUN_KN_PLURAL = "noun/kn_plural"

    # Kannada verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (ವರ್ತಮಾನಕಾಲ)
    VERB_KN_1S_PRESENT = "verb/kn_1s_present"
    VERB_KN_2S_PRESENT = "verb/kn_2s_present"
    VERB_KN_3S_PRESENT = "verb/kn_3s_present"
    VERB_KN_1P_PRESENT = "verb/kn_1p_present"
    VERB_KN_2P_PRESENT = "verb/kn_2p_present"
    VERB_KN_3P_PRESENT = "verb/kn_3p_present"
    # Past tense (ಭೂತಕಾಲ)
    VERB_KN_1S_PAST = "verb/kn_1s_past"
    VERB_KN_2S_PAST = "verb/kn_2s_past"
    VERB_KN_3S_PAST = "verb/kn_3s_past"
    VERB_KN_1P_PAST = "verb/kn_1p_past"
    VERB_KN_2P_PAST = "verb/kn_2p_past"
    VERB_KN_3P_PAST = "verb/kn_3p_past"
    # Future tense (ಭವಿಷ್ಯತ್ಕಾಲ)
    VERB_KN_1S_FUTURE = "verb/kn_1s_future"
    VERB_KN_2S_FUTURE = "verb/kn_2s_future"
    VERB_KN_3S_FUTURE = "verb/kn_3s_future"
    VERB_KN_1P_FUTURE = "verb/kn_1p_future"
    VERB_KN_2P_FUTURE = "verb/kn_2p_future"
    VERB_KN_3P_FUTURE = "verb/kn_3p_future"

    # Malayalam noun forms (singular/plural only)
    NOUN_ML_SINGULAR = "noun/ml_singular"
    NOUN_ML_PLURAL = "noun/ml_plural"

    # Malayalam verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (വർത്തമാനകാലം)
    VERB_ML_1S_PRESENT = "verb/ml_1s_present"
    VERB_ML_2S_PRESENT = "verb/ml_2s_present"
    VERB_ML_3S_PRESENT = "verb/ml_3s_present"
    VERB_ML_1P_PRESENT = "verb/ml_1p_present"
    VERB_ML_2P_PRESENT = "verb/ml_2p_present"
    VERB_ML_3P_PRESENT = "verb/ml_3p_present"
    # Past tense (ഭൂതകാലം)
    VERB_ML_1S_PAST = "verb/ml_1s_past"
    VERB_ML_2S_PAST = "verb/ml_2s_past"
    VERB_ML_3S_PAST = "verb/ml_3s_past"
    VERB_ML_1P_PAST = "verb/ml_1p_past"
    VERB_ML_2P_PAST = "verb/ml_2p_past"
    VERB_ML_3P_PAST = "verb/ml_3p_past"
    # Future tense (ഭാവികാലം)
    VERB_ML_1S_FUTURE = "verb/ml_1s_future"
    VERB_ML_2S_FUTURE = "verb/ml_2s_future"
    VERB_ML_3S_FUTURE = "verb/ml_3s_future"
    VERB_ML_1P_FUTURE = "verb/ml_1p_future"
    VERB_ML_2P_FUTURE = "verb/ml_2p_future"
    VERB_ML_3P_FUTURE = "verb/ml_3p_future"

    # Sinhala noun forms (singular/plural only)
    NOUN_SI_SINGULAR = "noun/si_singular"
    NOUN_SI_PLURAL = "noun/si_plural"

    # Sinhala verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (වර්තමාන කාලය)
    VERB_SI_1S_PRESENT = "verb/si_1s_present"
    VERB_SI_2S_PRESENT = "verb/si_2s_present"
    VERB_SI_3S_PRESENT = "verb/si_3s_present"
    VERB_SI_1P_PRESENT = "verb/si_1p_present"
    VERB_SI_2P_PRESENT = "verb/si_2p_present"
    VERB_SI_3P_PRESENT = "verb/si_3p_present"
    # Past tense (අතීත කාලය)
    VERB_SI_1S_PAST = "verb/si_1s_past"
    VERB_SI_2S_PAST = "verb/si_2s_past"
    VERB_SI_3S_PAST = "verb/si_3s_past"
    VERB_SI_1P_PAST = "verb/si_1p_past"
    VERB_SI_2P_PAST = "verb/si_2p_past"
    VERB_SI_3P_PAST = "verb/si_3p_past"
    # Future tense (අනාගත කාලය)
    VERB_SI_1S_FUTURE = "verb/si_1s_future"
    VERB_SI_2S_FUTURE = "verb/si_2s_future"
    VERB_SI_3S_FUTURE = "verb/si_3s_future"
    VERB_SI_1P_FUTURE = "verb/si_1p_future"
    VERB_SI_2P_FUTURE = "verb/si_2p_future"
    VERB_SI_3P_FUTURE = "verb/si_3p_future"

    # Bulgarian noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_BG_SINGULAR = "noun/bg_singular"
    NOUN_BG_PLURAL = "noun/bg_plural"

    # Bulgarian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (сегашно време)
    VERB_BG_1S_PRESENT = "verb/bg_1s_present"
    VERB_BG_2S_PRESENT = "verb/bg_2s_present"
    VERB_BG_3S_PRESENT = "verb/bg_3s_present"
    VERB_BG_1P_PRESENT = "verb/bg_1p_present"
    VERB_BG_2P_PRESENT = "verb/bg_2p_present"
    VERB_BG_3P_PRESENT = "verb/bg_3p_present"
    # Past tense (минало свършено време)
    VERB_BG_1S_PAST = "verb/bg_1s_past"
    VERB_BG_2S_PAST = "verb/bg_2s_past"
    VERB_BG_3S_PAST = "verb/bg_3s_past"
    VERB_BG_1P_PAST = "verb/bg_1p_past"
    VERB_BG_2P_PAST = "verb/bg_2p_past"
    VERB_BG_3P_PAST = "verb/bg_3p_past"
    # Future tense (бъдеще време)
    VERB_BG_1S_FUTURE = "verb/bg_1s_future"
    VERB_BG_2S_FUTURE = "verb/bg_2s_future"
    VERB_BG_3S_FUTURE = "verb/bg_3s_future"
    VERB_BG_1P_FUTURE = "verb/bg_1p_future"
    VERB_BG_2P_FUTURE = "verb/bg_2p_future"
    VERB_BG_3P_FUTURE = "verb/bg_3p_future"

    # Croatian noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_HR_SINGULAR = "noun/hr_singular"
    NOUN_HR_PLURAL = "noun/hr_plural"

    # Croatian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (prezent)
    VERB_HR_1S_PRESENT = "verb/hr_1s_present"
    VERB_HR_2S_PRESENT = "verb/hr_2s_present"
    VERB_HR_3S_PRESENT = "verb/hr_3s_present"
    VERB_HR_1P_PRESENT = "verb/hr_1p_present"
    VERB_HR_2P_PRESENT = "verb/hr_2p_present"
    VERB_HR_3P_PRESENT = "verb/hr_3p_present"
    # Past tense (perfekt)
    VERB_HR_1S_PAST = "verb/hr_1s_past"
    VERB_HR_2S_PAST = "verb/hr_2s_past"
    VERB_HR_3S_PAST = "verb/hr_3s_past"
    VERB_HR_1P_PAST = "verb/hr_1p_past"
    VERB_HR_2P_PAST = "verb/hr_2p_past"
    VERB_HR_3P_PAST = "verb/hr_3p_past"
    # Future tense (futur I)
    VERB_HR_1S_FUTURE = "verb/hr_1s_future"
    VERB_HR_2S_FUTURE = "verb/hr_2s_future"
    VERB_HR_3S_FUTURE = "verb/hr_3s_future"
    VERB_HR_1P_FUTURE = "verb/hr_1p_future"
    VERB_HR_2P_FUTURE = "verb/hr_2p_future"
    VERB_HR_3P_FUTURE = "verb/hr_3p_future"

    # Czech noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_CS_SINGULAR = "noun/cs_singular"
    NOUN_CS_PLURAL = "noun/cs_plural"

    # Czech verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (přítomný čas)
    VERB_CS_1S_PRESENT = "verb/cs_1s_present"
    VERB_CS_2S_PRESENT = "verb/cs_2s_present"
    VERB_CS_3S_PRESENT = "verb/cs_3s_present"
    VERB_CS_1P_PRESENT = "verb/cs_1p_present"
    VERB_CS_2P_PRESENT = "verb/cs_2p_present"
    VERB_CS_3P_PRESENT = "verb/cs_3p_present"
    # Past tense (minulý čas)
    VERB_CS_1S_PAST = "verb/cs_1s_past"
    VERB_CS_2S_PAST = "verb/cs_2s_past"
    VERB_CS_3S_PAST = "verb/cs_3s_past"
    VERB_CS_1P_PAST = "verb/cs_1p_past"
    VERB_CS_2P_PAST = "verb/cs_2p_past"
    VERB_CS_3P_PAST = "verb/cs_3p_past"
    # Future tense (budoucí čas)
    VERB_CS_1S_FUTURE = "verb/cs_1s_future"
    VERB_CS_2S_FUTURE = "verb/cs_2s_future"
    VERB_CS_3S_FUTURE = "verb/cs_3s_future"
    VERB_CS_1P_FUTURE = "verb/cs_1p_future"
    VERB_CS_2P_FUTURE = "verb/cs_2p_future"
    VERB_CS_3P_FUTURE = "verb/cs_3p_future"

    # Danish noun forms (singular/plural only - each noun has a fixed gender c/n)
    NOUN_DA_SINGULAR = "noun/da_singular"
    NOUN_DA_PLURAL = "noun/da_plural"

    # Danish verb forms (6 persons × 3 tenses = 18 forms)
    # Note: Danish verbs don't conjugate by person, but we use the standard
    # 6-person schema for consistency with other languages.
    # Present tense (nutid)
    VERB_DA_1S_PRESENT = "verb/da_1s_present"
    VERB_DA_2S_PRESENT = "verb/da_2s_present"
    VERB_DA_3S_PRESENT = "verb/da_3s_present"
    VERB_DA_1P_PRESENT = "verb/da_1p_present"
    VERB_DA_2P_PRESENT = "verb/da_2p_present"
    VERB_DA_3P_PRESENT = "verb/da_3p_present"
    # Past tense (datid)
    VERB_DA_1S_PAST = "verb/da_1s_past"
    VERB_DA_2S_PAST = "verb/da_2s_past"
    VERB_DA_3S_PAST = "verb/da_3s_past"
    VERB_DA_1P_PAST = "verb/da_1p_past"
    VERB_DA_2P_PAST = "verb/da_2p_past"
    VERB_DA_3P_PAST = "verb/da_3p_past"
    # Future tense (fremtid)
    VERB_DA_1S_FUTURE = "verb/da_1s_future"
    VERB_DA_2S_FUTURE = "verb/da_2s_future"
    VERB_DA_3S_FUTURE = "verb/da_3s_future"
    VERB_DA_1P_FUTURE = "verb/da_1p_future"
    VERB_DA_2P_FUTURE = "verb/da_2p_future"
    VERB_DA_3P_FUTURE = "verb/da_3p_future"

    # Estonian noun forms (singular/plural only - no grammatical gender)
    NOUN_ET_SINGULAR = "noun/et_singular"
    NOUN_ET_PLURAL = "noun/et_plural"

    # Estonian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (olevik)
    VERB_ET_1S_PRESENT = "verb/et_1s_present"
    VERB_ET_2S_PRESENT = "verb/et_2s_present"
    VERB_ET_3S_PRESENT = "verb/et_3s_present"
    VERB_ET_1P_PRESENT = "verb/et_1p_present"
    VERB_ET_2P_PRESENT = "verb/et_2p_present"
    VERB_ET_3P_PRESENT = "verb/et_3p_present"
    # Past tense (lihtminevik)
    VERB_ET_1S_PAST = "verb/et_1s_past"
    VERB_ET_2S_PAST = "verb/et_2s_past"
    VERB_ET_3S_PAST = "verb/et_3s_past"
    VERB_ET_1P_PAST = "verb/et_1p_past"
    VERB_ET_2P_PAST = "verb/et_2p_past"
    VERB_ET_3P_PAST = "verb/et_3p_past"
    # Future tense (tulevik - formed with saama + infinitive)
    VERB_ET_1S_FUTURE = "verb/et_1s_future"
    VERB_ET_2S_FUTURE = "verb/et_2s_future"
    VERB_ET_3S_FUTURE = "verb/et_3s_future"
    VERB_ET_1P_FUTURE = "verb/et_1p_future"
    VERB_ET_2P_FUTURE = "verb/et_2p_future"
    VERB_ET_3P_FUTURE = "verb/et_3p_future"

    # Finnish noun forms (singular/plural only - no grammatical gender)
    NOUN_FI_SINGULAR = "noun/fi_singular"
    NOUN_FI_PLURAL = "noun/fi_plural"

    # Finnish verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (preesens)
    VERB_FI_1S_PRESENT = "verb/fi_1s_present"
    VERB_FI_2S_PRESENT = "verb/fi_2s_present"
    VERB_FI_3S_PRESENT = "verb/fi_3s_present"
    VERB_FI_1P_PRESENT = "verb/fi_1p_present"
    VERB_FI_2P_PRESENT = "verb/fi_2p_present"
    VERB_FI_3P_PRESENT = "verb/fi_3p_present"
    # Past tense (imperfekti)
    VERB_FI_1S_PAST = "verb/fi_1s_past"
    VERB_FI_2S_PAST = "verb/fi_2s_past"
    VERB_FI_3S_PAST = "verb/fi_3s_past"
    VERB_FI_1P_PAST = "verb/fi_1p_past"
    VERB_FI_2P_PAST = "verb/fi_2p_past"
    VERB_FI_3P_PAST = "verb/fi_3p_past"
    # Future tense (futuuri - formed with tulla + present participle)
    VERB_FI_1S_FUTURE = "verb/fi_1s_future"
    VERB_FI_2S_FUTURE = "verb/fi_2s_future"
    VERB_FI_3S_FUTURE = "verb/fi_3s_future"
    VERB_FI_1P_FUTURE = "verb/fi_1p_future"
    VERB_FI_2P_FUTURE = "verb/fi_2p_future"
    VERB_FI_3P_FUTURE = "verb/fi_3p_future"

    # Greek noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_EL_SINGULAR = "noun/el_singular"
    NOUN_EL_PLURAL = "noun/el_plural"

    # Greek verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (ενεστώτας)
    VERB_EL_1S_PRESENT = "verb/el_1s_present"
    VERB_EL_2S_PRESENT = "verb/el_2s_present"
    VERB_EL_3S_PRESENT = "verb/el_3s_present"
    VERB_EL_1P_PRESENT = "verb/el_1p_present"
    VERB_EL_2P_PRESENT = "verb/el_2p_present"
    VERB_EL_3P_PRESENT = "verb/el_3p_present"
    # Past tense (αόριστος)
    VERB_EL_1S_PAST = "verb/el_1s_past"
    VERB_EL_2S_PAST = "verb/el_2s_past"
    VERB_EL_3S_PAST = "verb/el_3s_past"
    VERB_EL_1P_PAST = "verb/el_1p_past"
    VERB_EL_2P_PAST = "verb/el_2p_past"
    VERB_EL_3P_PAST = "verb/el_3p_past"
    # Future tense (μέλλοντας - θα + subjunctive)
    VERB_EL_1S_FUTURE = "verb/el_1s_future"
    VERB_EL_2S_FUTURE = "verb/el_2s_future"
    VERB_EL_3S_FUTURE = "verb/el_3s_future"
    VERB_EL_1P_FUTURE = "verb/el_1p_future"
    VERB_EL_2P_FUTURE = "verb/el_2p_future"
    VERB_EL_3P_FUTURE = "verb/el_3p_future"

    # Hungarian noun forms (singular/plural only - no grammatical gender)
    NOUN_HU_SINGULAR = "noun/hu_singular"
    NOUN_HU_PLURAL = "noun/hu_plural"

    # Hungarian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (jelen idő)
    VERB_HU_1S_PRESENT = "verb/hu_1s_present"
    VERB_HU_2S_PRESENT = "verb/hu_2s_present"
    VERB_HU_3S_PRESENT = "verb/hu_3s_present"
    VERB_HU_1P_PRESENT = "verb/hu_1p_present"
    VERB_HU_2P_PRESENT = "verb/hu_2p_present"
    VERB_HU_3P_PRESENT = "verb/hu_3p_present"
    # Past tense (múlt idő)
    VERB_HU_1S_PAST = "verb/hu_1s_past"
    VERB_HU_2S_PAST = "verb/hu_2s_past"
    VERB_HU_3S_PAST = "verb/hu_3s_past"
    VERB_HU_1P_PAST = "verb/hu_1p_past"
    VERB_HU_2P_PAST = "verb/hu_2p_past"
    VERB_HU_3P_PAST = "verb/hu_3p_past"
    # Future tense (jövő idő - fog + infinitive)
    VERB_HU_1S_FUTURE = "verb/hu_1s_future"
    VERB_HU_2S_FUTURE = "verb/hu_2s_future"
    VERB_HU_3S_FUTURE = "verb/hu_3s_future"
    VERB_HU_1P_FUTURE = "verb/hu_1p_future"
    VERB_HU_2P_FUTURE = "verb/hu_2p_future"
    VERB_HU_3P_FUTURE = "verb/hu_3p_future"

    # Irish noun forms (singular/plural only - each noun has a fixed gender m/f)
    NOUN_GA_SINGULAR = "noun/ga_singular"
    NOUN_GA_PLURAL = "noun/ga_plural"

    # Irish verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (aimsir láithreach)
    VERB_GA_1S_PRESENT = "verb/ga_1s_present"
    VERB_GA_2S_PRESENT = "verb/ga_2s_present"
    VERB_GA_3S_PRESENT = "verb/ga_3s_present"
    VERB_GA_1P_PRESENT = "verb/ga_1p_present"
    VERB_GA_2P_PRESENT = "verb/ga_2p_present"
    VERB_GA_3P_PRESENT = "verb/ga_3p_present"
    # Past tense (aimsir chaite)
    VERB_GA_1S_PAST = "verb/ga_1s_past"
    VERB_GA_2S_PAST = "verb/ga_2s_past"
    VERB_GA_3S_PAST = "verb/ga_3s_past"
    VERB_GA_1P_PAST = "verb/ga_1p_past"
    VERB_GA_2P_PAST = "verb/ga_2p_past"
    VERB_GA_3P_PAST = "verb/ga_3p_past"
    # Future tense (aimsir fháistineach)
    VERB_GA_1S_FUTURE = "verb/ga_1s_future"
    VERB_GA_2S_FUTURE = "verb/ga_2s_future"
    VERB_GA_3S_FUTURE = "verb/ga_3s_future"
    VERB_GA_1P_FUTURE = "verb/ga_1p_future"
    VERB_GA_2P_FUTURE = "verb/ga_2p_future"
    VERB_GA_3P_FUTURE = "verb/ga_3p_future"

    # Latvian noun forms (legacy singular/plural - kept for backward compatibility)
    NOUN_LV_SINGULAR = "noun/lv_singular"
    NOUN_LV_PLURAL = "noun/lv_plural"

    # Latvian noun forms (7 cases × 2 numbers = 14 forms)
    NOUN_LV_NOMINATIVE_SINGULAR = "noun/lv_nominative_singular"
    NOUN_LV_GENITIVE_SINGULAR = "noun/lv_genitive_singular"
    NOUN_LV_DATIVE_SINGULAR = "noun/lv_dative_singular"
    NOUN_LV_ACCUSATIVE_SINGULAR = "noun/lv_accusative_singular"
    NOUN_LV_INSTRUMENTAL_SINGULAR = "noun/lv_instrumental_singular"
    NOUN_LV_LOCATIVE_SINGULAR = "noun/lv_locative_singular"
    NOUN_LV_VOCATIVE_SINGULAR = "noun/lv_vocative_singular"
    NOUN_LV_NOMINATIVE_PLURAL = "noun/lv_nominative_plural"
    NOUN_LV_GENITIVE_PLURAL = "noun/lv_genitive_plural"
    NOUN_LV_DATIVE_PLURAL = "noun/lv_dative_plural"
    NOUN_LV_ACCUSATIVE_PLURAL = "noun/lv_accusative_plural"
    NOUN_LV_INSTRUMENTAL_PLURAL = "noun/lv_instrumental_plural"
    NOUN_LV_LOCATIVE_PLURAL = "noun/lv_locative_plural"
    NOUN_LV_VOCATIVE_PLURAL = "noun/lv_vocative_plural"

    # Latvian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (tagadne)
    VERB_LV_1S_PRESENT = "verb/lv_1s_present"
    VERB_LV_2S_PRESENT = "verb/lv_2s_present"
    VERB_LV_3S_PRESENT = "verb/lv_3s_present"
    VERB_LV_1P_PRESENT = "verb/lv_1p_present"
    VERB_LV_2P_PRESENT = "verb/lv_2p_present"
    VERB_LV_3P_PRESENT = "verb/lv_3p_present"
    # Past tense (pagātne)
    VERB_LV_1S_PAST = "verb/lv_1s_past"
    VERB_LV_2S_PAST = "verb/lv_2s_past"
    VERB_LV_3S_PAST = "verb/lv_3s_past"
    VERB_LV_1P_PAST = "verb/lv_1p_past"
    VERB_LV_2P_PAST = "verb/lv_2p_past"
    VERB_LV_3P_PAST = "verb/lv_3p_past"
    # Future tense (nākotne)
    VERB_LV_1S_FUTURE = "verb/lv_1s_future"
    VERB_LV_2S_FUTURE = "verb/lv_2s_future"
    VERB_LV_3S_FUTURE = "verb/lv_3s_future"
    VERB_LV_1P_FUTURE = "verb/lv_1p_future"
    VERB_LV_2P_FUTURE = "verb/lv_2p_future"
    VERB_LV_3P_FUTURE = "verb/lv_3p_future"

    # Latvian adjective forms (7 cases × 2 numbers × 2 genders = 28 forms)
    # Masculine singular
    ADJ_LV_NOMINATIVE_SINGULAR_M = "adjective/lv_nominative_singular_m"
    ADJ_LV_GENITIVE_SINGULAR_M = "adjective/lv_genitive_singular_m"
    ADJ_LV_DATIVE_SINGULAR_M = "adjective/lv_dative_singular_m"
    ADJ_LV_ACCUSATIVE_SINGULAR_M = "adjective/lv_accusative_singular_m"
    ADJ_LV_INSTRUMENTAL_SINGULAR_M = "adjective/lv_instrumental_singular_m"
    ADJ_LV_LOCATIVE_SINGULAR_M = "adjective/lv_locative_singular_m"
    ADJ_LV_VOCATIVE_SINGULAR_M = "adjective/lv_vocative_singular_m"
    # Feminine singular
    ADJ_LV_NOMINATIVE_SINGULAR_F = "adjective/lv_nominative_singular_f"
    ADJ_LV_GENITIVE_SINGULAR_F = "adjective/lv_genitive_singular_f"
    ADJ_LV_DATIVE_SINGULAR_F = "adjective/lv_dative_singular_f"
    ADJ_LV_ACCUSATIVE_SINGULAR_F = "adjective/lv_accusative_singular_f"
    ADJ_LV_INSTRUMENTAL_SINGULAR_F = "adjective/lv_instrumental_singular_f"
    ADJ_LV_LOCATIVE_SINGULAR_F = "adjective/lv_locative_singular_f"
    ADJ_LV_VOCATIVE_SINGULAR_F = "adjective/lv_vocative_singular_f"
    # Masculine plural
    ADJ_LV_NOMINATIVE_PLURAL_M = "adjective/lv_nominative_plural_m"
    ADJ_LV_GENITIVE_PLURAL_M = "adjective/lv_genitive_plural_m"
    ADJ_LV_DATIVE_PLURAL_M = "adjective/lv_dative_plural_m"
    ADJ_LV_ACCUSATIVE_PLURAL_M = "adjective/lv_accusative_plural_m"
    ADJ_LV_INSTRUMENTAL_PLURAL_M = "adjective/lv_instrumental_plural_m"
    ADJ_LV_LOCATIVE_PLURAL_M = "adjective/lv_locative_plural_m"
    ADJ_LV_VOCATIVE_PLURAL_M = "adjective/lv_vocative_plural_m"
    # Feminine plural
    ADJ_LV_NOMINATIVE_PLURAL_F = "adjective/lv_nominative_plural_f"
    ADJ_LV_GENITIVE_PLURAL_F = "adjective/lv_genitive_plural_f"
    ADJ_LV_DATIVE_PLURAL_F = "adjective/lv_dative_plural_f"
    ADJ_LV_ACCUSATIVE_PLURAL_F = "adjective/lv_accusative_plural_f"
    ADJ_LV_INSTRUMENTAL_PLURAL_F = "adjective/lv_instrumental_plural_f"
    ADJ_LV_LOCATIVE_PLURAL_F = "adjective/lv_locative_plural_f"
    ADJ_LV_VOCATIVE_PLURAL_F = "adjective/lv_vocative_plural_f"

    # Latvian adverb forms (3 comparative degrees)
    ADVERB_LV_POSITIVE = "adverb/lv_positive"
    ADVERB_LV_COMPARATIVE = "adverb/lv_comparative"
    ADVERB_LV_SUPERLATIVE = "adverb/lv_superlative"

    # Maltese noun forms (singular/plural only - each noun has a fixed gender m/f)
    NOUN_MT_SINGULAR = "noun/mt_singular"
    NOUN_MT_PLURAL = "noun/mt_plural"

    # Maltese verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (preżent)
    VERB_MT_1S_PRESENT = "verb/mt_1s_present"
    VERB_MT_2S_PRESENT = "verb/mt_2s_present"
    VERB_MT_3S_PRESENT = "verb/mt_3s_present"
    VERB_MT_1P_PRESENT = "verb/mt_1p_present"
    VERB_MT_2P_PRESENT = "verb/mt_2p_present"
    VERB_MT_3P_PRESENT = "verb/mt_3p_present"
    # Past tense (passat)
    VERB_MT_1S_PAST = "verb/mt_1s_past"
    VERB_MT_2S_PAST = "verb/mt_2s_past"
    VERB_MT_3S_PAST = "verb/mt_3s_past"
    VERB_MT_1P_PAST = "verb/mt_1p_past"
    VERB_MT_2P_PAST = "verb/mt_2p_past"
    VERB_MT_3P_PAST = "verb/mt_3p_past"
    # Future tense (futur - se + imperfect)
    VERB_MT_1S_FUTURE = "verb/mt_1s_future"
    VERB_MT_2S_FUTURE = "verb/mt_2s_future"
    VERB_MT_3S_FUTURE = "verb/mt_3s_future"
    VERB_MT_1P_FUTURE = "verb/mt_1p_future"
    VERB_MT_2P_FUTURE = "verb/mt_2p_future"
    VERB_MT_3P_FUTURE = "verb/mt_3p_future"

    # Slovak noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_SK_SINGULAR = "noun/sk_singular"
    NOUN_SK_PLURAL = "noun/sk_plural"

    # Slovak verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (prítomný čas)
    VERB_SK_1S_PRESENT = "verb/sk_1s_present"
    VERB_SK_2S_PRESENT = "verb/sk_2s_present"
    VERB_SK_3S_PRESENT = "verb/sk_3s_present"
    VERB_SK_1P_PRESENT = "verb/sk_1p_present"
    VERB_SK_2P_PRESENT = "verb/sk_2p_present"
    VERB_SK_3P_PRESENT = "verb/sk_3p_present"
    # Past tense (minulý čas)
    VERB_SK_1S_PAST = "verb/sk_1s_past"
    VERB_SK_2S_PAST = "verb/sk_2s_past"
    VERB_SK_3S_PAST = "verb/sk_3s_past"
    VERB_SK_1P_PAST = "verb/sk_1p_past"
    VERB_SK_2P_PAST = "verb/sk_2p_past"
    VERB_SK_3P_PAST = "verb/sk_3p_past"
    # Future tense (budúci čas)
    VERB_SK_1S_FUTURE = "verb/sk_1s_future"
    VERB_SK_2S_FUTURE = "verb/sk_2s_future"
    VERB_SK_3S_FUTURE = "verb/sk_3s_future"
    VERB_SK_1P_FUTURE = "verb/sk_1p_future"
    VERB_SK_2P_FUTURE = "verb/sk_2p_future"
    VERB_SK_3P_FUTURE = "verb/sk_3p_future"

    # Slovenian noun forms (singular/plural only - each noun has a fixed gender m/f/n)
    NOUN_SL_SINGULAR = "noun/sl_singular"
    NOUN_SL_PLURAL = "noun/sl_plural"

    # Slovenian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (sedanjik)
    VERB_SL_1S_PRESENT = "verb/sl_1s_present"
    VERB_SL_2S_PRESENT = "verb/sl_2s_present"
    VERB_SL_3S_PRESENT = "verb/sl_3s_present"
    VERB_SL_1P_PRESENT = "verb/sl_1p_present"
    VERB_SL_2P_PRESENT = "verb/sl_2p_present"
    VERB_SL_3P_PRESENT = "verb/sl_3p_present"
    # Past tense (preteklik)
    VERB_SL_1S_PAST = "verb/sl_1s_past"
    VERB_SL_2S_PAST = "verb/sl_2s_past"
    VERB_SL_3S_PAST = "verb/sl_3s_past"
    VERB_SL_1P_PAST = "verb/sl_1p_past"
    VERB_SL_2P_PAST = "verb/sl_2p_past"
    VERB_SL_3P_PAST = "verb/sl_3p_past"
    # Future tense (prihodnjik)
    VERB_SL_1S_FUTURE = "verb/sl_1s_future"
    VERB_SL_2S_FUTURE = "verb/sl_2s_future"
    VERB_SL_3S_FUTURE = "verb/sl_3s_future"
    VERB_SL_1P_FUTURE = "verb/sl_1p_future"
    VERB_SL_2P_FUTURE = "verb/sl_2p_future"
    VERB_SL_3P_FUTURE = "verb/sl_3p_future"

    # Thai noun forms (singular/plural - Thai nouns don't inflect, stored for pedagogy)
    NOUN_TH_SINGULAR = "noun/th_singular"
    NOUN_TH_PLURAL = "noun/th_plural"

    # Thai verb forms (isolating language - no person conjugation, tense via particles)
    VERB_TH_PRESENT = "verb/th_present"
    VERB_TH_PAST = "verb/th_past"
    VERB_TH_FUTURE = "verb/th_future"

    # Malay noun forms (singular/plural - plural via reduplication e.g. buku-buku)
    NOUN_MS_SINGULAR = "noun/ms_singular"
    NOUN_MS_PLURAL = "noun/ms_plural"

    # Malay verb forms (isolating - no person conjugation, tense via context/markers)
    VERB_MS_PRESENT = "verb/ms_present"
    VERB_MS_PAST = "verb/ms_past"
    VERB_MS_FUTURE = "verb/ms_future"

    # Burmese noun forms (singular/plural - plurality via particles တွေ/များ)
    NOUN_MY_SINGULAR = "noun/my_singular"
    NOUN_MY_PLURAL = "noun/my_plural"

    # Burmese verb forms (isolating - tense via sentence-final particles)
    VERB_MY_PRESENT = "verb/my_present"
    VERB_MY_PAST = "verb/my_past"
    VERB_MY_FUTURE = "verb/my_future"

    # Khmer noun forms (singular/plural - no inflection, plurality via context)
    NOUN_KM_SINGULAR = "noun/km_singular"
    NOUN_KM_PLURAL = "noun/km_plural"

    # Khmer verb forms (isolating - no conjugation, tense via auxiliaries)
    VERB_KM_PRESENT = "verb/km_present"
    VERB_KM_PAST = "verb/km_past"
    VERB_KM_FUTURE = "verb/km_future"

    # Lao noun forms (singular/plural - no inflection, plurality via classifiers)
    NOUN_LO_SINGULAR = "noun/lo_singular"
    NOUN_LO_PLURAL = "noun/lo_plural"

    # Lao verb forms (isolating - tense via particles ຈະ/ໄດ້/ແລ້ວ)
    VERB_LO_PRESENT = "verb/lo_present"
    VERB_LO_PAST = "verb/lo_past"
    VERB_LO_FUTURE = "verb/lo_future"

    # Filipino (Tagalog) noun forms (singular/plural - plural via mga prefix)
    NOUN_TL_SINGULAR = "noun/tl_singular"
    NOUN_TL_PLURAL = "noun/tl_plural"

    # Filipino verb forms (aspect-based: completed/incompleted/contemplated)
    VERB_TL_PRESENT = "verb/tl_present"
    VERB_TL_PAST = "verb/tl_past"
    VERB_TL_FUTURE = "verb/tl_future"

    # Swahili noun forms (Bantu noun class system with singular/plural prefixes)
    NOUN_SW_SINGULAR = "noun/sw_singular"
    NOUN_SW_PLURAL = "noun/sw_plural"

    # Swahili verb forms (agglutinative - subject/tense/object prefixes on verb root)
    VERB_SW_PRESENT = "verb/sw_present"
    VERB_SW_PAST = "verb/sw_past"
    VERB_SW_FUTURE = "verb/sw_future"

    # Hausa noun forms (singular/plural - plural via suffixes and internal vowel changes)
    NOUN_HA_SINGULAR = "noun/ha_singular"
    NOUN_HA_PLURAL = "noun/ha_plural"

    # Hausa verb forms (conjugates for person/tense with preverbal markers)
    VERB_HA_PRESENT = "verb/ha_present"
    VERB_HA_PAST = "verb/ha_past"
    VERB_HA_FUTURE = "verb/ha_future"

    # Yoruba noun forms (isolating - no inflectional morphology on nouns)
    NOUN_YO_SINGULAR = "noun/yo_singular"
    NOUN_YO_PLURAL = "noun/yo_plural"

    # Yoruba verb forms (isolating - tense/aspect via preverbal particles)
    VERB_YO_PRESENT = "verb/yo_present"
    VERB_YO_PAST = "verb/yo_past"
    VERB_YO_FUTURE = "verb/yo_future"

    # Igbo noun forms (singular/plural - some nouns use prefix changes)
    NOUN_IG_SINGULAR = "noun/ig_singular"
    NOUN_IG_PLURAL = "noun/ig_plural"

    # Igbo verb forms (root + suffixes for tense/aspect, tonal distinctions)
    VERB_IG_PRESENT = "verb/ig_present"
    VERB_IG_PAST = "verb/ig_past"
    VERB_IG_FUTURE = "verb/ig_future"

    # Amharic noun forms (singular/plural - plural via suffix -ዎች/-ኦች)
    NOUN_AM_SINGULAR = "noun/am_singular"
    NOUN_AM_PLURAL = "noun/am_plural"

    # Amharic verb forms (Semitic root system with person/tense/mood conjugation)
    VERB_AM_PRESENT = "verb/am_present"
    VERB_AM_PAST = "verb/am_past"
    VERB_AM_FUTURE = "verb/am_future"

    # Zulu noun forms (Bantu noun class system with singular/plural prefixes)
    NOUN_ZU_SINGULAR = "noun/zu_singular"
    NOUN_ZU_PLURAL = "noun/zu_plural"

    # Zulu verb forms (agglutinative - subject/tense/object concords on verb root)
    VERB_ZU_PRESENT = "verb/zu_present"
    VERB_ZU_PAST = "verb/zu_past"
    VERB_ZU_FUTURE = "verb/zu_future"

    # Oromo noun forms (singular/plural - plural via suffixes -oota/-wwan/-lee)
    NOUN_OM_SINGULAR = "noun/om_singular"
    NOUN_OM_PLURAL = "noun/om_plural"

    # Oromo verb forms (conjugates for person/number/tense)
    VERB_OM_PRESENT = "verb/om_present"
    VERB_OM_PAST = "verb/om_past"
    VERB_OM_FUTURE = "verb/om_future"

    # Somali noun forms (singular/plural - plural via suffixes and vowel changes)
    NOUN_SO_SINGULAR = "noun/so_singular"
    NOUN_SO_PLURAL = "noun/so_plural"

    # Somali verb forms (conjugates for person/number/tense)
    VERB_SO_PRESENT = "verb/so_present"
    VERB_SO_PAST = "verb/so_past"
    VERB_SO_FUTURE = "verb/so_future"

    # Xhosa noun forms (Bantu noun class system with singular/plural prefixes)
    NOUN_XH_SINGULAR = "noun/xh_singular"
    NOUN_XH_PLURAL = "noun/xh_plural"

    # Xhosa verb forms (agglutinative - subject/tense/object concords on verb root)
    VERB_XH_PRESENT = "verb/xh_present"
    VERB_XH_PAST = "verb/xh_past"
    VERB_XH_FUTURE = "verb/xh_future"

    # Shona noun forms (Bantu noun class system with singular/plural prefixes)
    NOUN_SN_SINGULAR = "noun/sn_singular"
    NOUN_SN_PLURAL = "noun/sn_plural"

    # Shona verb forms (agglutinative - subject/tense/object markers on verb root)
    VERB_SN_PRESENT = "verb/sn_present"
    VERB_SN_PAST = "verb/sn_past"
    VERB_SN_FUTURE = "verb/sn_future"

    # Hindi noun forms (singular/plural - gender-based inflection)
    NOUN_HI_SINGULAR = "noun/hi_singular"
    NOUN_HI_PLURAL = "noun/hi_plural"

    # Hindi verb forms (person/number/gender/tense conjugation)
    VERB_HI_PRESENT = "verb/hi_present"
    VERB_HI_PAST = "verb/hi_past"
    VERB_HI_FUTURE = "verb/hi_future"

    # Bengali noun forms (singular/plural)
    NOUN_BN_SINGULAR = "noun/bn_singular"
    NOUN_BN_PLURAL = "noun/bn_plural"

    # Bengali verb forms (person/tense conjugation)
    VERB_BN_PRESENT = "verb/bn_present"
    VERB_BN_PAST = "verb/bn_past"
    VERB_BN_FUTURE = "verb/bn_future"

    # Pashto noun forms (singular/plural - gender/case inflection)
    NOUN_PS_SINGULAR = "noun/ps_singular"
    NOUN_PS_PLURAL = "noun/ps_plural"

    # Pashto verb forms (person/number/gender/tense conjugation)
    VERB_PS_PRESENT = "verb/ps_present"
    VERB_PS_PAST = "verb/ps_past"
    VERB_PS_FUTURE = "verb/ps_future"

    # Persian noun forms (singular/plural)
    NOUN_FA_SINGULAR = "noun/fa_singular"
    NOUN_FA_PLURAL = "noun/fa_plural"

    # Persian verb forms (person/number/tense conjugation)
    VERB_FA_PRESENT = "verb/fa_present"
    VERB_FA_PAST = "verb/fa_past"
    VERB_FA_FUTURE = "verb/fa_future"

    # Georgian noun forms (singular/plural - case declension)
    NOUN_KA_SINGULAR = "noun/ka_singular"
    NOUN_KA_PLURAL = "noun/ka_plural"

    # Georgian verb forms (complex screeve system with person/tense)
    VERB_KA_PRESENT = "verb/ka_present"
    VERB_KA_PAST = "verb/ka_past"
    VERB_KA_FUTURE = "verb/ka_future"

    # Armenian noun forms (singular/plural - case declension)
    NOUN_HY_SINGULAR = "noun/hy_singular"
    NOUN_HY_PLURAL = "noun/hy_plural"

    # Armenian verb forms (person/number/tense conjugation)
    VERB_HY_PRESENT = "verb/hy_present"
    VERB_HY_PAST = "verb/hy_past"
    VERB_HY_FUTURE = "verb/hy_future"

    # Azerbaijani noun forms (singular/plural - agglutinative with vowel harmony)
    NOUN_AZ_SINGULAR = "noun/az_singular"
    NOUN_AZ_PLURAL = "noun/az_plural"

    # Azerbaijani verb forms (agglutinative person/tense/mood conjugation)
    VERB_AZ_PRESENT = "verb/az_present"
    VERB_AZ_PAST = "verb/az_past"
    VERB_AZ_FUTURE = "verb/az_future"

    # Turkish noun forms (singular/plural - agglutinative with vowel harmony)
    NOUN_TR_SINGULAR = "noun/tr_singular"
    NOUN_TR_PLURAL = "noun/tr_plural"

    # Turkish verb forms (agglutinative person/tense/mood conjugation)
    VERB_TR_PRESENT = "verb/tr_present"
    VERB_TR_PAST = "verb/tr_past"
    VERB_TR_FUTURE = "verb/tr_future"

    # Ukrainian noun forms (legacy singular/plural - kept for backward compatibility)
    NOUN_UK_SINGULAR = "noun/uk_singular"
    NOUN_UK_PLURAL = "noun/uk_plural"

    # Ukrainian noun forms (7 cases × 2 numbers = 14 forms)
    NOUN_UK_NOMINATIVE_SINGULAR = "noun/uk_nominative_singular"
    NOUN_UK_GENITIVE_SINGULAR = "noun/uk_genitive_singular"
    NOUN_UK_DATIVE_SINGULAR = "noun/uk_dative_singular"
    NOUN_UK_ACCUSATIVE_SINGULAR = "noun/uk_accusative_singular"
    NOUN_UK_INSTRUMENTAL_SINGULAR = "noun/uk_instrumental_singular"
    NOUN_UK_LOCATIVE_SINGULAR = "noun/uk_locative_singular"
    NOUN_UK_VOCATIVE_SINGULAR = "noun/uk_vocative_singular"
    NOUN_UK_NOMINATIVE_PLURAL = "noun/uk_nominative_plural"
    NOUN_UK_GENITIVE_PLURAL = "noun/uk_genitive_plural"
    NOUN_UK_DATIVE_PLURAL = "noun/uk_dative_plural"
    NOUN_UK_ACCUSATIVE_PLURAL = "noun/uk_accusative_plural"
    NOUN_UK_INSTRUMENTAL_PLURAL = "noun/uk_instrumental_plural"
    NOUN_UK_LOCATIVE_PLURAL = "noun/uk_locative_plural"
    NOUN_UK_VOCATIVE_PLURAL = "noun/uk_vocative_plural"

    # Ukrainian verb forms (legacy tense-only - kept for backward compatibility)
    VERB_UK_PRESENT = "verb/uk_present"
    VERB_UK_PAST = "verb/uk_past"
    VERB_UK_FUTURE = "verb/uk_future"

    # Ukrainian verb forms (6 persons × 3 tenses = 18 forms)
    # Present tense (теперішній час)
    VERB_UK_1S_PRESENT = "verb/uk_1s_present"
    VERB_UK_2S_PRESENT = "verb/uk_2s_present"
    VERB_UK_3S_PRESENT = "verb/uk_3s_present"
    VERB_UK_1P_PRESENT = "verb/uk_1p_present"
    VERB_UK_2P_PRESENT = "verb/uk_2p_present"
    VERB_UK_3P_PRESENT = "verb/uk_3p_present"
    # Past tense (минулий час)
    VERB_UK_1S_PAST = "verb/uk_1s_past"
    VERB_UK_2S_PAST = "verb/uk_2s_past"
    VERB_UK_3S_PAST = "verb/uk_3s_past"
    VERB_UK_1P_PAST = "verb/uk_1p_past"
    VERB_UK_2P_PAST = "verb/uk_2p_past"
    VERB_UK_3P_PAST = "verb/uk_3p_past"
    # Future tense (майбутній час)
    VERB_UK_1S_FUTURE = "verb/uk_1s_future"
    VERB_UK_2S_FUTURE = "verb/uk_2s_future"
    VERB_UK_3S_FUTURE = "verb/uk_3s_future"
    VERB_UK_1P_FUTURE = "verb/uk_1p_future"
    VERB_UK_2P_FUTURE = "verb/uk_2p_future"
    VERB_UK_3P_FUTURE = "verb/uk_3p_future"

    # Ukrainian adjective forms (7 cases × 2 numbers × 2 genders = 28 forms)
    # Masculine singular
    ADJ_UK_NOMINATIVE_SINGULAR_M = "adjective/uk_nominative_singular_m"
    ADJ_UK_GENITIVE_SINGULAR_M = "adjective/uk_genitive_singular_m"
    ADJ_UK_DATIVE_SINGULAR_M = "adjective/uk_dative_singular_m"
    ADJ_UK_ACCUSATIVE_SINGULAR_M = "adjective/uk_accusative_singular_m"
    ADJ_UK_INSTRUMENTAL_SINGULAR_M = "adjective/uk_instrumental_singular_m"
    ADJ_UK_LOCATIVE_SINGULAR_M = "adjective/uk_locative_singular_m"
    ADJ_UK_VOCATIVE_SINGULAR_M = "adjective/uk_vocative_singular_m"
    # Feminine singular
    ADJ_UK_NOMINATIVE_SINGULAR_F = "adjective/uk_nominative_singular_f"
    ADJ_UK_GENITIVE_SINGULAR_F = "adjective/uk_genitive_singular_f"
    ADJ_UK_DATIVE_SINGULAR_F = "adjective/uk_dative_singular_f"
    ADJ_UK_ACCUSATIVE_SINGULAR_F = "adjective/uk_accusative_singular_f"
    ADJ_UK_INSTRUMENTAL_SINGULAR_F = "adjective/uk_instrumental_singular_f"
    ADJ_UK_LOCATIVE_SINGULAR_F = "adjective/uk_locative_singular_f"
    ADJ_UK_VOCATIVE_SINGULAR_F = "adjective/uk_vocative_singular_f"
    # Masculine plural
    ADJ_UK_NOMINATIVE_PLURAL_M = "adjective/uk_nominative_plural_m"
    ADJ_UK_GENITIVE_PLURAL_M = "adjective/uk_genitive_plural_m"
    ADJ_UK_DATIVE_PLURAL_M = "adjective/uk_dative_plural_m"
    ADJ_UK_ACCUSATIVE_PLURAL_M = "adjective/uk_accusative_plural_m"
    ADJ_UK_INSTRUMENTAL_PLURAL_M = "adjective/uk_instrumental_plural_m"
    ADJ_UK_LOCATIVE_PLURAL_M = "adjective/uk_locative_plural_m"
    ADJ_UK_VOCATIVE_PLURAL_M = "adjective/uk_vocative_plural_m"
    # Feminine plural
    ADJ_UK_NOMINATIVE_PLURAL_F = "adjective/uk_nominative_plural_f"
    ADJ_UK_GENITIVE_PLURAL_F = "adjective/uk_genitive_plural_f"
    ADJ_UK_DATIVE_PLURAL_F = "adjective/uk_dative_plural_f"
    ADJ_UK_ACCUSATIVE_PLURAL_F = "adjective/uk_accusative_plural_f"
    ADJ_UK_INSTRUMENTAL_PLURAL_F = "adjective/uk_instrumental_plural_f"
    ADJ_UK_LOCATIVE_PLURAL_F = "adjective/uk_locative_plural_f"
    ADJ_UK_VOCATIVE_PLURAL_F = "adjective/uk_vocative_plural_f"

    # Ukrainian adverb forms (3 comparative degrees)
    ADVERB_UK_POSITIVE = "adverb/uk_positive"
    ADVERB_UK_COMPARATIVE = "adverb/uk_comparative"
    ADVERB_UK_SUPERLATIVE = "adverb/uk_superlative"

    # Chinese noun forms (isolating language - base form only)
    NOUN_ZH_BASE = "noun/zh_base"

    # Chinese verb forms (analytic aspect patterns)
    VERB_ZH_BASE = "verb/zh_base"  # bare verb (买)
    VERB_ZH_PERFECTIVE = "verb/zh_perfective"  # verb + 了 (买了) — completed action
    VERB_ZH_EXPERIENTIAL = "verb/zh_experiential"  # verb + 过 (买过) — have done before
    VERB_ZH_PROGRESSIVE = "verb/zh_progressive"  # 在 + verb (在买) — currently doing

    # Japanese noun forms (no morphological change - base form only)
    NOUN_JA_BASE = "noun/ja_base"

    # Japanese verb forms (genuine conjugation)
    VERB_JA_MASU = "verb/ja_masu"  # polite present (食べます)
    VERB_JA_TE = "verb/ja_te"  # te-form (食べて)
    VERB_JA_TA = "verb/ja_ta"  # past plain (食べた)
    VERB_JA_NAI = "verb/ja_nai"  # negative plain (食べない)

    # Korean noun forms (no morphological change - base form only)
    NOUN_KO_BASE = "noun/ko_base"

    # Korean verb forms (genuine conjugation - 해요체 polite forms)
    VERB_KO_POLITE_PRESENT = "verb/ko_polite_present"  # 먹어요
    VERB_KO_POLITE_PAST = "verb/ko_polite_past"  # 먹었어요
    VERB_KO_POLITE_FUTURE = "verb/ko_polite_future"  # 먹을 거예요

    # Vietnamese noun forms (isolating language - base form only)
    NOUN_VI_BASE = "noun/vi_base"

    # Vietnamese verb forms (isolating language - base form only)
    VERB_VI_BASE = "verb/vi_base"

    # Generic forms
    BASE_FORM = "base_form"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Auto-generate GrammaticalForm members from langtools/*/forms_config.py
# ---------------------------------------------------------------------------
# Existing hand-written members are stable DB values and are never touched.
# This block only *adds* members that are defined in a forms_config but not
# yet present in the enum above, so new languages get their enum entries
# without manual edits to this file.


def _auto_extend_grammatical_form() -> None:
    """Scan forms_config modules and add missing GrammaticalForm members."""
    import importlib.util
    from pathlib import Path

    from langtools.form_patterns import get_all_enum_pairs

    langtools_dir = Path(__file__).resolve().parent.parent.parent / "langtools"
    if not langtools_dir.is_dir():
        return

    existing_values = {m.value for m in GrammaticalForm}
    new_members: dict[str, str] = {}

    for config_path in sorted(langtools_dir.glob("*/forms_config.py")):
        lang_dir = config_path.parent.name
        mod_name = f"langtools.{lang_dir}.forms_config"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, config_path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue

        lang_code: str = getattr(mod, "LANGUAGE_CODE", lang_dir)
        for attr_name in dir(mod):
            if not attr_name.endswith("_CONFIG"):
                continue
            cfg = getattr(mod, attr_name)
            if not isinstance(cfg, dict) or "type" not in cfg:
                continue
            # Derive pos_type from the attribute name: NOUN_CONFIG → noun
            pos_type = attr_name.removesuffix("_CONFIG").lower()
            for member_name, value_str in get_all_enum_pairs(cfg, lang_code, pos_type):
                if value_str not in existing_values and member_name not in new_members:
                    new_members[member_name] = value_str

    # Dynamically extend the enum
    if new_members:
        # Use the stdlib approach: extend __members__ via _value2member_map_
        for name, value in sorted(new_members.items()):
            member = object.__new__(GrammaticalForm)
            member._value_ = value
            member._name_ = name
            GrammaticalForm._value2member_map_[value] = member  # type: ignore[attr-defined]
            GrammaticalForm._member_map_[name] = member  # type: ignore[attr-defined]
            GrammaticalForm._member_names_.append(name)  # type: ignore[attr-defined]


_auto_extend_grammatical_form()
