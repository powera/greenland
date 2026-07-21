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

    # Noun forms (English)
    NOUN_SINGULAR = "noun/singular"
    NOUN_PLURAL = "noun/plural"
    NOUN_POSSESSIVE_SINGULAR = "noun/possessive_singular"
    NOUN_POSSESSIVE_PLURAL = "noun/possessive_plural"

    # Adjective forms (English)
    ADJECTIVE_POSITIVE = "adjective/positive"
    ADJECTIVE_COMPARATIVE = "adjective/comparative"
    ADJECTIVE_SUPERLATIVE = "adjective/superlative"

    # Adverb forms
    ADVERB_POSITIVE = "adverb/positive"
    ADVERB_COMPARATIVE = "adverb/comparative"
    ADVERB_SUPERLATIVE = "adverb/superlative"

    # Language-specific adverb base forms (invariant adverbs)
    ADVERB_KO_BASE = "adverb/ko_base"

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

    # Korean numerals (native Korean vs Sino-Korean systems)
    NUMERAL_KO_NATIVE = "numeral/ko_native"  # 하나, 둘, 셋 (native Korean, for counting)
    NUMERAL_KO_SINO = "numeral/ko_sino"  # 일, 이, 삼 (Sino-Korean, for dates/numbers)
    NUMERAL_KO_ORDINAL = "numeral/ko_ordinal"  # 첫째, 둘째, 셋째

    # Kannada noun forms (singular/plural only)
    NOUN_KN_SINGULAR = "noun/kn_singular"
    NOUN_KN_PLURAL = "noun/kn_plural"

    # Estonian noun forms (singular/plural only - no grammatical gender)
    NOUN_ET_SINGULAR = "noun/et_singular"
    NOUN_ET_PLURAL = "noun/et_plural"

    # Latvian noun forms (legacy singular/plural - kept for backward compatibility)
    NOUN_LV_SINGULAR = "noun/lv_singular"
    NOUN_LV_PLURAL = "noun/lv_plural"

    # Malay noun forms (singular/plural - plural via reduplication e.g. buku-buku)
    NOUN_MS_SINGULAR = "noun/ms_singular"
    NOUN_MS_PLURAL = "noun/ms_plural"

    # Malay verb forms (isolating - no person conjugation, tense via context/markers)
    VERB_MS_PRESENT = "verb/ms_present"
    VERB_MS_PAST = "verb/ms_past"
    VERB_MS_FUTURE = "verb/ms_future"

    # Filipino (Tagalog) noun forms (singular/plural - plural via mga prefix)
    NOUN_TL_SINGULAR = "noun/tl_singular"
    NOUN_TL_PLURAL = "noun/tl_plural"

    # Filipino verb forms (aspect-based: completed/incompleted/contemplated)
    VERB_TL_PRESENT = "verb/tl_present"
    VERB_TL_PAST = "verb/tl_past"
    VERB_TL_FUTURE = "verb/tl_future"

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

    # Ukrainian verb forms (legacy tense-only - kept for backward compatibility)
    VERB_UK_PRESENT = "verb/uk_present"
    VERB_UK_PAST = "verb/uk_past"
    VERB_UK_FUTURE = "verb/uk_future"

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

        # Optional direct enum overrides for legacy/stable values that don't
        # map cleanly to form-pattern expansion.
        overrides = getattr(mod, "GRAMMATICAL_FORM_OVERRIDES", None)
        if isinstance(overrides, dict):
            for member_name, value_str in overrides.items():
                if not isinstance(member_name, str) or not isinstance(value_str, str):
                    continue
                if value_str not in existing_values and member_name not in new_members:
                    new_members[member_name] = value_str

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
