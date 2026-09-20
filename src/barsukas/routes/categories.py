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
from storage.models.guid_prefixes import (
    SUBTYPE_DEFS,
    SUBTYPE_GUID_PREFIXES,
    subtype_groups,
)
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
    counts: Dict[str, Dict[str, int]],
) -> List[Dict[str, Any]]:
    """Build category data structure for template rendering.

    The groups come from ``subtype_groups``, so every live subtype of this POS
    is rendered under its own heading. This used to walk a hand-written list of
    group memberships kept in this module, which had drifted: three noun
    subtypes -- legal_document, legal_concept and geographic_place -- were fully
    defined, issuing GUIDs, and appeared nowhere on the page.
    """
    guid_prefixes = SUBTYPE_GUID_PREFIXES.get(pos_type, {})
    descriptions = SUBTYPE_DESCRIPTIONS.get(pos_type, {})

    grouped_data = []
    for group_name, subtypes in subtype_groups(pos_type).items():
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

    # Build data for each POS type. Every POS is built the same way: the
    # groups and their membership come from the subtype table, so a POS needs
    # no per-POS listing here.
    titles = {
        "noun": ("Noun Subtypes", "bi-box", NounSubtype, noun_counts),
        "verb": ("Verb Subtypes", "bi-lightning", VerbSubtype, verb_counts),
        "adjective": ("Adjective Subtypes", "bi-palette", AdjectiveSubtype, adjective_counts),
        "adverb": ("Adverb Subtypes", "bi-speedometer2", AdverbSubtype, adverb_counts),
        "numeral": ("Numeral Subtypes", "bi-123", NumeralSubtype, numeral_counts),
    }
    categories: Dict[str, Dict[str, Any]] = {
        pos_type: {
            "title": title,
            "icon": icon,
            "total_subtypes": len(enum_class),
            "total_words": sum_total_words(counts),
            "groups": build_category_data(pos_type, counts),
        }
        for pos_type, (title, icon, enum_class, counts) in titles.items()
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
