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