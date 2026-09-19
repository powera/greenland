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
from storage.models.guid_prefixes import SUBTYPE_DEFS, SUBTYPE_GUID_PREFIXES
from storage.models.schema import Lemma

bp = Blueprint("categories", __name__, url_prefix="/categories")


# Descriptions for each POS subtype, extracted from enum docstrings/comments
def _subtype_descriptions() -> Dict[str, Dict[str, str]]:
    """Category-page descriptions, derived from the subtype table.

    This used to be a hand-written dict beside the one in the classification
    prompts and the one in the enum comments. It had already drifted: three
    noun subtypes that exist had no entry here and rendered blank on the
    category page. SUBTYPE_DEFS is the single source, so the page cannot fall
    behind a subtype being added.

    Keyed the way this page reads it: the catch-all is "other", matching the
    enum member rather than the "<pos>_other" prefix key.
    """
    descriptions: Dict[str, Dict[str, str]] = {}
    for pos_type, subtypes in SUBTYPE_DEFS.items():
        per_pos: Dict[str, str] = {}
        for subtype, spec in subtypes.items():
            name = "other" if subtype == f"{pos_type}_other" else subtype
            text = spec.description
            if spec.examples:
                text = f"{text} ({', '.join(spec.examples)})" if text else ", ".join(spec.examples)
            if name == "other":
                text = f"Other {pos_type}s"
            per_pos[name] = text or subtype.replace("_", " ")
        descriptions[pos_type] = per_pos
    return descriptions


SUBTYPE_DESCRIPTIONS: Dict[str, Dict[str, str]] = _subtype_descriptions()

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
        "region",
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
    "Origin and Material": ["origin", "location", "purpose", "material"],
    "Quantity and Time": [
        # definite_quantity removed: moved to numeral POS
        "indefinite_quantity",
        "duration",
        "frequency",
        "sequence",
        "temporal_status",
    ],
    "Technical and Domain": [
        "spatial_orientation",
        "chemical_physical",
        "biological_type",
        "belief_cultural",
        "mathematical",
        "legal",
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
