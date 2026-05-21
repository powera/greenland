#!/usr/bin/env python3
"""
Text rendering and formatting utilities for wireword exports.

Provides reusable functions for formatting display names and text output.
"""

from typing import Any


def format_subtype_display_name(subtype: str) -> str:
    """
    Convert database subtype values to display-friendly names.

    Args:
        subtype: Raw subtype value from database

    Returns:
        Display-friendly subtype name
    """
    # Handle None or empty values
    if not subtype:
        return "Other"

    # Special cases that need custom formatting
    special_cases = {
        # Noun subtypes
        "animal": "Animals",
        "food": "Food",
        "beverage": "Beverage",
        "furniture": "Furniture",
        "vehicle": "Vehicle",
        "plant_part": "Plant Part",
        "small_movable_object": "Small Movable Object",
        "clothing_accessory": "Clothing/Accessory",
        "building_structure": "Building/Structure",
        "artwork_artifact": "Artwork/Artifact",
        "tool_machine": "Tool/Machine",
        "path_infrastructure": "Path/Infrastructure",
        "material_substance": "Material/Substance",
        "chemical_compound": "Chemical Compound",
        "medication_remedy": "Medication/Remedy",
        "concept_idea": "Concept/Idea",
        "symbolic_element": "Symbolic Element",
        "quality_attribute": "Quality/Attribute",
        "mental_construct": "Mental Construct",
        "knowledge_domain": "Knowledge Domain",
        "quantitative_concept": "Quantitative Concept",
        "emotion_feeling": "Emotion/Feeling",
        "process_event": "Process/Event",
        "time_period": "Time Period",
        "group_people": "Group of People",
        "animal_grouping_term": "Animal Grouping",
        "collection_things": "Collection of Things",
        "personal_name": "Personal Name",
        "place_name": "Place Name",
        "organization_name": "Organization Name",
        "temporal_name": "Temporal Name",
        "unit_of_measurement": "Unit of Measurement",
        "body_part": "Body Part",
        "natural_feature": "Natural Feature",
        "disease_condition": "Disease/Condition",
        "occupation": "Occupation",
        "family_relation": "Family Relation",
        "human": "Humans",
        "plant": "Plants",
        # Verb subtypes
        "physical_action": "Physical Action",
        "creation_action": "Creation Action",
        "destruction_action": "Destruction Action",
        "mental_state": "Mental State",
        "emotional_state": "Emotional State",
        "perception": "Perception",
        "communication": "Communication",
        "possession": "Possession",
        "existence": "Existence",
        "development": "Development",
        "change": "Change",
        "directional_movement": "Directional Movement",
        "manner_movement": "Manner Movement",
        # Adjective subtypes
        "personal_quality": "Personal Quality",
        "condition": "Condition",
        "definite_quantity": "Definite Quantity",
        "indefinite_quantity": "Indefinite Quantity",
        # Adverb subtypes
        "specific_time": "Specific Time",
        "relative_time": "Relative Time",
        "definite_frequency": "Definite Frequency",
        "indefinite_frequency": "Indefinite Frequency",
    }

    # Check for special cases first
    if subtype in special_cases:
        return special_cases[subtype]

    # For regular cases, convert underscores to spaces and title case
    formatted = subtype.replace("_", " ")

    # Default: title case each word
    return formatted.title()


def resolve_group_label(subtype: str, interface_language: str, session: Any | None = None) -> str:
    """
    Resolve localized group labels for Wireword exports.

    Args:
        subtype: Raw subtype value from database (e.g. "food", "tool_machine")
        interface_language: Interface language code used by Wireword.
            For current exports this should be the source language.
        session: Optional database/session handle for future translation lookup support.

    Returns:
        Localized group label string. Currently falls back to English for all languages.
    """
    _ = interface_language
    _ = session
    return format_subtype_display_name(subtype)
