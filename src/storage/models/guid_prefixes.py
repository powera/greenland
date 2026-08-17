"""GUID prefix mappings for different POS subtypes.

NOTE: When adding/modifying prefixes, update the corresponding Subtype enum
in enums.py to keep GUID assignments in sync.
"""

# Subtype mapping for GUID generation, organized by POS type
SUBTYPE_GUID_PREFIXES = {
    "noun": {
        "human": "N01",
        "family_relation": "N35",
        "occupation": "N36",
        "honorific": "N48",
        "animal": "N02",
        "body_part": "N03",
        "disease_condition": "N04",
        "plant": "N05",
        "plant_part": "N38",
        "food": "N06",
        "beverage": "N42",
        "building_structure": "N07",
        "building_part": "N47",
        "furniture": "N39",
        "small_movable_object": "N08",
        "clothing_accessory": "N09",
        "artwork_artifact": "N10",
        "natural_feature": "N11",
        "tool": "N12",
        "electronic_device": "N57",
        "appliance": "N43",
        "weapon": "N44",
        "vehicle": "N40",
        "path_infrastructure": "N13",
        "material_substance": "N14",
        "chemical_compound": "N15",
        "medication_remedy": "N16",
        "concept_idea": "N17",
        "communication_information": "N50",
        "technology_digital": "N52",
        "abstract_condition": "N54",
        "social_institution": "N55",
        "activity": "N41",
        "symbolic_element": "N18",
        "quality_attribute": "N19",
        "mental_construct": "N20",
        "knowledge_domain": "N21",
        "quantitative_concept": "N22",
        "emotion_feeling": "N23",
        "shape": "N37",
        "process_event": "N24",
        "time_period": "N25",
        "group_people": "N26",
        "animal_grouping_term": "N27",
        "collection_things": "N28",
        "personal_name": "N29",
        "place_name": "N30",
        "country": "N45",
        "city": "N46",
        "geographic_place": "N56",
        "organization_name": "N31",
        "temporal_name": "N32",
        "nationality": "N33",
        "unit_of_measurement": "N34",
        "noun_other": "N99",
    },
    "verb": {
        "physical_action": "V01",
        "creation_action": "V02",
        "destruction_action": "V03",
        "mental_state": "V04",
        "emotional_state": "V05",
        "perception": "V10",
        "communication": "V09",
        "possession": "V06",
        "existence": "V11",
        "development": "V07",
        "change": "V08",
        "directional_movement": "V12",
        "manner_movement": "V13",
        "verb_other": "V99",
    },
    "adjective": {
        "size": "A01",
        "color": "A02",
        "shape": "A03",
        "texture": "A04",
        "personal_quality": "A16",
        "physical_property": "A18",
        "condition": "A17",
        "emotion": "A19",
        "quality": "A05",
        "aesthetic": "A06",
        "importance": "A07",
        "origin": "A08",
        "purpose": "A09",
        "material": "A10",
        # A11 removed: definite_quantity moved to numeral POS
        "indefinite_quantity": "A12",
        "duration": "A13",
        "frequency": "A14",
        "sequence": "A15",
        "adjective_other": "A99",
    },
    "adverb": {
        "style": "D01",
        "attitude": "D02",
        "specific_time": "D03",
        "relative_time": "D04",
        "duration": "D05",
        "direction": "D06",
        "location": "D07",
        "distance": "D08",
        "intensity": "D09",
        "completeness": "D10",
        "approximation": "D11",
        "definite_frequency": "D12",
        "indefinite_frequency": "D13",
        "adverb_other": "D99",
    },
    "conjunction": {
        "conjunction_other": "C99",
    },
    "pronoun": {
        "pronoun_other": "P99",
    },
    "preposition": {
        "preposition_other": "R99",
    },
    "interjection": {
        "interjection_other": "I99",
    },
    "determiner": {
        "determiner_other": "T99",
    },
    "article": {
        "article_other": "L99",
    },
    "numeral": {
        "cardinal": "Z01",
        "ordinal": "Z02",
    },
}

# GUID prefixes for phrase subtypes. Phrases (fixed traveler/greeting
# expressions, e.g. "Where is the toilet?") live in their own ``phrases`` table
# rather than ``lemmas``, so they are not part of SUBTYPE_GUID_PREFIXES above.
PHRASE_SUBTYPE_GUID_PREFIXES = {
    "greetings": "F01",
    "traveler": "F02",
}

# GUID prefix for idioms. Idioms (figurative expressions whose meaning is not
# compositional, e.g. "kick the bucket") live in their own ``idioms`` table, so
# like phrases they are not part of SUBTYPE_GUID_PREFIXES above. Idioms are not
# subtyped, so this is a single prefix rather than a mapping.
IDIOM_GUID_PREFIX = "M01"

# GUID prefixes for name kinds. Names ("George", "Fresh Mart") live in their own
# ``names`` table and are exported to ``data/release/names`` because their
# per-language renderings - Džordžas, 乔治, ジョージ - have to stay stable across
# every text that uses them. The kind is encoded in the prefix, mirroring how a
# lemma's subtype is, so a bare GUID says what it names. Keys are
# ``storage.models.name_entity.NAME_KINDS`` entries; the "E" family (entity) is
# reserved for names.
NAME_KIND_GUID_PREFIXES = {
    "given_name": "E01",
    "family_name": "E02",
    "full_name": "E03",
    "place": "E04",
    "organization": "E05",
    "brand": "E06",
    "animal": "E07",
    "other": "E99",
}
