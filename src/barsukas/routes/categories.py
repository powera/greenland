#!/usr/bin/python3

"""Routes for viewing POS subtype categories."""

from typing import Any, Dict, List, cast

from flask import Blueprint, g, render_template
from flask.typing import ResponseReturnValue

from storage.models.enums import (
    AdjectiveSubtype,
    AdverbSubtype,
    NounSubtype,
    NumeralSubtype,
    VerbSubtype,
)
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.schema import Lemma

bp = Blueprint("categories", __name__, url_prefix="/categories")


# Descriptions for each POS subtype, extracted from enum docstrings/comments
SUBTYPE_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "noun": {
        # People and Living Things
        "occupation": "Professions and roles (teacher, doctor, accountant)",
        "family_relation": "Family members (brother, uncle, cousin, parent)",
        "human": "Generic humans and people",
        "honorific": "Titles and forms of address (Sir, Lord, Mr., Mrs., Dr.)",
        "animal": "Animals and creatures",
        "body_part": "Parts of the body",
        "disease_condition": "Diseases and medical conditions",
        "plant": "Plants and vegetation",
        "plant_part": "Parts of plants (leaf, root, seed, petal, bark)",
        # Food and Consumables
        "food": "Solid consumables (bread, apple, rice, meat)",
        "beverage": "Liquid consumables (water, coffee, tea, juice)",
        # Physical Objects and Structures
        "building_structure": "Buildings and structures",
        "building_part": "Parts of buildings (door, window, wall, floor, ceiling)",
        "furniture": "Furniture items (table, chair, desk, sofa, bed)",
        "small_movable_object": "Small movable objects",
        "clothing_accessory": "Clothing and accessories",
        "artwork_artifact": "Artworks and artifacts",
        "natural_feature": "Natural features and landscapes",
        "tool": "Hand tools and generic tools (hammer, saw, wrench)",
        "electronic_device": "Computers, phones, TVs, radios, cameras",
        "appliance": "Kitchen and household appliances (blender, microwave)",
        "weapon": "Weapons and arms (sword, gun, bow, shield)",
        "vehicle": "Transportation (car, truck, bicycle, boat, airplane)",
        "path_infrastructure": "Paths and infrastructure",
        # Materials and Substances
        "material_substance": "Materials and substances",
        "chemical_compound": "Chemical compounds",
        "medication_remedy": "Medications and remedies",
        # Abstract Concepts and Ideas
        "concept_idea": "Abstract concepts and ideas",
        "communication_information": "Language, messages, information (word, news)",
        "technology_digital": "Digital/computing concepts (internet, email, data)",
        "abstract_condition": "Abstract conditions, situations (peace, danger, luck)",
        "social_institution": "Organizations, collective structures (government, army)",
        "activity": "Activities and hobbies (reading, cooking, sports, dancing)",
        "symbolic_element": "Symbolic elements",
        "quality_attribute": "Quality attributes",
        "mental_construct": "Mental constructs",
        "knowledge_domain": "Knowledge domains",
        "quantitative_concept": "Quantitative concepts",
        "emotion_feeling": "Emotions and feelings",
        "shape": "Geometric shapes (circle, triangle, square, rectangle)",
        # Processes and Time
        "process_event": "Processes and events",
        "time_period": "Time periods",
        # Groups and Collections
        "group_people": "Groups of people",
        "animal_grouping_term": "Animal groupings and collective terms",
        "collection_things": "Collections of things",
        # Named Entities
        "personal_name": "Personal names",
        "place_name": "Generic place nouns (room, street, etc.)",
        "country": "Countries (Lithuania, France, Japan)",
        "city": "Cities (Vilnius, Paris, Tokyo)",
        "organization_name": "Organization names",
        # Temporal Names
        "temporal_name": "Days of week, months, etc.",
        # Nationality and Measurement
        "nationality": "Nationalities",
        "unit_of_measurement": "Units of measurement",
        # Other
        "other": "Other nouns",
    },
    "verb": {
        "physical_action": "Physical actions (push, pull, lift, eat, drink)",
        "creation_action": "Creating things (make, create, build)",
        "destruction_action": "Destroying things (break, destroy, demolish)",
        "mental_state": "Cognition (know, believe, understand, think)",
        "emotional_state": "Feelings (love, hate, fear, enjoy)",
        "perception": "Sensory verbs (see, hear, smell, taste, feel, touch)",
        "communication": "Speaking and writing (say, tell, speak, write, read)",
        "possession": "Having/owning (have, own, possess, give, take)",
        "existence": "Living/existing (live, exist, die, survive, stay, remain)",
        "development": "Growing/evolving (grow, develop, evolve, mature)",
        "change": "Transforming (become, transform, change, turn)",
        "directional_movement": "Moving with direction (go, come, enter, leave)",
        "manner_movement": "Way of moving (walk, run, swim, fly, crawl)",
        "other": "Other verbs",
    },
    "adjective": {
        "size": "Size descriptions (big, small, huge, tiny)",
        "color": "Color descriptions (red, blue, green, yellow)",
        "shape": "Shape descriptions (round, square, triangular, oval)",
        "texture": "Texture descriptions (soft, hard, smooth, rough)",
        "personal_quality": "Character/personality traits (honest, kind, brave)",
        "physical_property": "Physical properties (dimensions, weight, temperature)",
        "condition": "Physical/temporal state (hot, cold, wet, dry, clean)",
        "emotion": "Emotional states (happy, sad, angry, excited, tired)",
        "quality": "Evaluative properties (good, bad, excellent, important)",
        "aesthetic": "Beauty or appearance (beautiful, ugly, pretty, handsome)",
        "importance": "Importance or priority (important, essential, trivial)",
        "origin": "Origin or source (American, Chinese, domestic, foreign)",
        "purpose": "Purpose or function (educational, medical, industrial)",
        "material": "Material composition (wooden, metal, plastic, cotton)",
        # definite_quantity removed: moved to numeral POS
        "indefinite_quantity": "Inexact amounts (many, few, some, several)",
        "duration": "Time duration (brief, long, eternal, temporary)",
        "frequency": "Frequency of occurrence (daily, occasional, rare)",
        "sequence": "Order or sequence (first, last, next, previous)",
        "other": "Other adjectives",
    },
    "adverb": {
        # Manner
        "style": "Manner or style of action (quickly, carefully, well, slowly)",
        "attitude": "Attitude or approach (eagerly, reluctantly, willingly)",
        # Temporal
        "specific_time": "Specific time references (now, today, yesterday)",
        "relative_time": "Relative time references (already, soon, recently)",
        "duration": "Duration of time (briefly, temporarily, permanently)",
        "definite_frequency": "Specific frequency (daily, weekly, monthly, yearly)",
        "indefinite_frequency": "Inexact frequency (often, sometimes, rarely)",
        # Spatial
        "direction": "Directional movement (up, down, forward, backward)",
        "location": "Position or place (here, there, everywhere, somewhere)",
        "distance": "Distance references (nearby, far, close, away)",
        # Degree
        "intensity": "Intensity or degree (very, extremely, slightly, quite)",
        "completeness": "Degree of completeness (entirely, partly, completely)",
        "approximation": "Approximation (almost, nearly, exactly, approximately)",
        "other": "Other adverbs",
    },
    "numeral": {
        "cardinal": "Cardinal numbers (one, two, three, 100)",
        "ordinal": "Ordinal numbers (first, second, third, 100th)",
    },
}

# Groupings for noun subtypes (for better organization in the UI)
NOUN_GROUPS = {
    "People and Living Things": [
        "occupation",
        "family_relation",
        "human",
        "honorific",
        "animal",
        "body_part",
        "disease_condition",
        "plant",
        "plant_part",
    ],
    "Food and Consumables": ["food", "beverage"],
    "Physical Objects and Structures": [
        "building_structure",
        "building_part",
        "furniture",
        "small_movable_object",
        "clothing_accessory",
        "artwork_artifact",
        "natural_feature",
        "tool",
        "electronic_device",
        "appliance",
        "weapon",
        "vehicle",
        "path_infrastructure",
    ],
    "Materials and Substances": [
        "material_substance",
        "chemical_compound",
        "medication_remedy",
    ],
    "Abstract Concepts and Ideas": [
        "concept_idea",
        "communication_information",
        "technology_digital",
        "abstract_condition",
        "social_institution",
        "activity",
        "symbolic_element",
        "quality_attribute",
        "mental_construct",
        "knowledge_domain",
        "quantitative_concept",
        "emotion_feeling",
        "shape",
    ],
    "Processes and Time": ["process_event", "time_period"],
    "Groups and Collections": [
        "group_people",
        "animal_grouping_term",
        "collection_things",
    ],
    "Named Entities": [
        "personal_name",
        "place_name",
        "country",
        "city",
        "organization_name",
    ],
    "Other Categories": ["temporal_name", "nationality", "unit_of_measurement", "other"],
}

# Groupings for adjective subtypes
ADJECTIVE_GROUPS = {
    "Physical Properties": ["size", "color", "shape", "texture", "physical_property"],
    "Personal and Emotional": ["personal_quality", "condition", "emotion"],
    "Evaluative": ["quality", "aesthetic", "importance"],
    "Origin and Material": ["origin", "purpose", "material"],
    "Quantity and Time": [
        # definite_quantity removed: moved to numeral POS
        "indefinite_quantity",
        "duration",
        "frequency",
        "sequence",
    ],
    "Other": ["other"],
}

# Groupings for adverb subtypes
ADVERB_GROUPS = {
    "Manner": ["style", "attitude"],
    "Temporal": [
        "specific_time",
        "relative_time",
        "duration",
        "definite_frequency",
        "indefinite_frequency",
    ],
    "Spatial": ["direction", "location", "distance"],
    "Degree": ["intensity", "completeness", "approximation"],
    "Other": ["other"],
}

# Groupings for verb subtypes
VERB_GROUPS = {
    "Physical Actions": ["physical_action", "creation_action", "destruction_action"],
    "Mental and Emotional": ["mental_state", "emotional_state", "perception"],
    "Communication and Possession": ["communication", "possession"],
    "Existence and Change": ["existence", "development", "change"],
    "Movement": ["directional_movement", "manner_movement"],
    "Other": ["other"],
}


def get_subtype_counts(db_session: Any, pos_type: str) -> Dict[str, Dict[str, int]]:
    """Get the count of lemmas for each subtype within a POS type.

    Returns a dict mapping subtype to {"total": count, "categorized": count}
    where categorized means difficulty_level != -1.
    """
    from sqlalchemy import case, func

    results = (
        db_session.query(
            Lemma.pos_subtype,
            func.count(Lemma.id).label("total"),
            func.sum(case((Lemma.difficulty_level != -1, 1), else_=0)).label("categorized"),
        )
        .filter(Lemma.pos_type == pos_type)
        .filter(Lemma.pos_subtype.isnot(None))
        .group_by(Lemma.pos_subtype)
        .all()
    )
    return {
        subtype: {"total": total, "categorized": categorized or 0}
        for subtype, total, categorized in results
    }


def build_category_data(
    pos_type: str,
    enum_class: Any,
    groups: Dict[str, List[str]],
    counts: Dict[str, Dict[str, int]],
) -> List[Dict[str, Any]]:
    """Build category data structure for template rendering."""
    guid_prefixes = SUBTYPE_GUID_PREFIXES.get(pos_type, {})
    descriptions = SUBTYPE_DESCRIPTIONS.get(pos_type, {})

    grouped_data = []
    for group_name, subtypes in groups.items():
        group_items = []
        for subtype in subtypes:
            # Handle the special case where enum value might differ from GUID key
            guid_prefix = guid_prefixes.get(subtype, guid_prefixes.get(f"{pos_type}_{subtype}", ""))
            subtype_counts = counts.get(subtype, {"total": 0, "categorized": 0})
            group_items.append(
                {
                    "name": subtype,
                    "display_name": subtype.replace("_", " ").title(),
                    "description": descriptions.get(subtype, ""),
                    "guid_prefix": guid_prefix,
                    "count": subtype_counts["total"],
                    "categorized_count": subtype_counts["categorized"],
                }
            )
        grouped_data.append({"group_name": group_name, "items": group_items})

    return grouped_data


@bp.route("/")
def list_categories() -> ResponseReturnValue:
    """List all POS subtype categories organized by POS type."""
    # Get counts for each POS type
    noun_counts = get_subtype_counts(g.db, "noun")
    verb_counts = get_subtype_counts(g.db, "verb")
    adjective_counts = get_subtype_counts(g.db, "adjective")
    adverb_counts = get_subtype_counts(g.db, "adverb")
    numeral_counts = get_subtype_counts(g.db, "numeral")

    # Helper to sum total words from new counts structure
    def sum_total_words(counts: Dict[str, Dict[str, int]]) -> int:
        return sum(c["total"] for c in counts.values())

    # Build data for each POS type
    categories = {
        "noun": {
            "title": "Noun Subtypes",
            "icon": "bi-box",
            "total_subtypes": len(NounSubtype),
            "total_words": sum_total_words(noun_counts),
            "groups": build_category_data("noun", NounSubtype, NOUN_GROUPS, noun_counts),
        },
        "verb": {
            "title": "Verb Subtypes",
            "icon": "bi-lightning",
            "total_subtypes": len(VerbSubtype),
            "total_words": sum_total_words(verb_counts),
            "groups": build_category_data("verb", VerbSubtype, VERB_GROUPS, verb_counts),
        },
        "adjective": {
            "title": "Adjective Subtypes",
            "icon": "bi-palette",
            "total_subtypes": len(AdjectiveSubtype),
            "total_words": sum_total_words(adjective_counts),
            "groups": build_category_data(
                "adjective", AdjectiveSubtype, ADJECTIVE_GROUPS, adjective_counts
            ),
        },
        "adverb": {
            "title": "Adverb Subtypes",
            "icon": "bi-speedometer2",
            "total_subtypes": len(AdverbSubtype),
            "total_words": sum_total_words(adverb_counts),
            "groups": build_category_data("adverb", AdverbSubtype, ADVERB_GROUPS, adverb_counts),
        },
        "numeral": {
            "title": "Numeral Subtypes",
            "icon": "bi-123",
            "total_subtypes": len(NumeralSubtype),
            "total_words": sum_total_words(numeral_counts),
            "groups": [
                {
                    "group_name": "Numerals",
                    "items": [
                        {
                            "name": subtype.value,
                            "display_name": subtype.value.replace("_", " ").title(),
                            "description": SUBTYPE_DESCRIPTIONS.get("numeral", {}).get(
                                subtype.value, ""
                            ),
                            "guid_prefix": SUBTYPE_GUID_PREFIXES.get("numeral", {}).get(
                                subtype.value, ""
                            ),
                            "count": numeral_counts.get(
                                subtype.value, {"total": 0, "categorized": 0}
                            )["total"],
                            "categorized_count": numeral_counts.get(
                                subtype.value, {"total": 0, "categorized": 0}
                            )["categorized"],
                        }
                        for subtype in NumeralSubtype
                    ],
                }
            ],
        },
    }

    # Calculate totals
    total_subtypes = sum(cast(int, cat["total_subtypes"]) for cat in categories.values())
    total_words = sum(cast(int, cat["total_words"]) for cat in categories.values())

    return render_template(
        "categories/list.html",
        categories=categories,
        total_subtypes=total_subtypes,
        total_words=total_words,
    )
