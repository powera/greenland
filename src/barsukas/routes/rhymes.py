#!/usr/bin/python3

"""
Rhyming dictionary routes.

Provides a two-tier browse of rhyme families derived from English IPA
pronunciations stored on DerivativeForm.rhyme_key.

Tier 1 (index):  Select a final sound (consonant or vowel cluster).
Tier 2 (endings): Within that final sound, browse distinct rhyme keys
                   grouped by their penultimate (vowel) segment.
Family detail:    View all words sharing a single rhyme key.
"""

from typing import Any, Dict, List, Optional, Tuple, cast

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from langtools.en.rhyme_key import (
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
)
from storage.models.schema import DerivativeForm, Lemma

bp = Blueprint("rhymes", __name__, url_prefix="/rhymes")

RHYME_ITEMS_PER_PAGE = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rhyme_family_rows() -> List[Tuple[str, int, str]]:
    """Return grouped rhyme-family rows limited to keys with 2+ distinct lemmas."""
    rows = (
        g.db.query(
            DerivativeForm.rhyme_key,
            func.count(func.distinct(DerivativeForm.lemma_id)).label("word_count"),
            func.min(DerivativeForm.derivative_form_text).label("example_word"),
        )
        .filter(
            DerivativeForm.language_code == "en",
            DerivativeForm.rhyme_key.isnot(None),
        )
        .group_by(DerivativeForm.rhyme_key)
        .having(func.count(func.distinct(DerivativeForm.lemma_id)) >= 2)
        .all()
    )
    return cast(List[Tuple[str, int, str]], rows)


def _distinct_final_sounds() -> List[Tuple[str, int]]:
    """Return (final_sound, family_count) pairs sorted by family count desc.

    Each "final sound" groups multiple rhyme keys together (e.g., all keys
    ending in "t": æt, ɪt, ʌt, …).  We compute this in Python from the
    distinct rhyme keys since the grouping logic lives in Python.
    """
    sound_counts: Dict[str, int] = {}
    for rk, _, _ in _rhyme_family_rows():
        fs = rhyme_key_final_sound(rk)
        if fs:
            sound_counts[fs] = sound_counts.get(fs, 0) + 1

    return sorted(sound_counts.items(), key=lambda x: (-x[1], x[0]))


def _rhyme_families_for_final_sound(
    final_sound: str,
) -> List[Dict[str, Any]]:
    """Return rhyme family dicts for all keys whose final sound matches.

    Each dict has: rhyme_key, penultimate, word_count, example_word.
    """
    families: List[Dict[str, Any]] = []
    for rk, count, example in _rhyme_family_rows():
        fs = rhyme_key_final_sound(rk)
        if fs == final_sound:
            families.append(
                {
                    "rhyme_key": rk,
                    "penultimate": rhyme_key_penultimate_sound(rk),
                    "word_count": count,
                    "example_word": example,
                }
            )

    # Sort by penultimate sound, then by rhyme key.
    families.sort(key=lambda f: (f["penultimate"], f["rhyme_key"]))
    return families


def _family_words(
    rhyme_key_value: str,
) -> List[Dict[str, Any]]:
    """Return word dicts for all lemmas in a given rhyme family."""
    rows = (
        g.db.query(
            Lemma.id,
            Lemma.lemma_text,
            Lemma.pos_type,
            Lemma.disambiguation,
            Lemma.difficulty_level,
            DerivativeForm.derivative_form_text,
            DerivativeForm.ipa_pronunciation,
            DerivativeForm.grammatical_form,
        )
        .join(DerivativeForm, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            DerivativeForm.language_code == "en",
            DerivativeForm.rhyme_key == rhyme_key_value,
            Lemma.guid.isnot(None),
        )
        .order_by(func.lower(Lemma.lemma_text), DerivativeForm.derivative_form_text)
        .all()
    )

    # Group by lemma, collecting derivative forms.
    seen_lemmas: Dict[int, Dict[str, Any]] = {}
    for lemma_id, lemma_text, pos, disambig, level, form_text, ipa, gram_form in rows:
        if lemma_id not in seen_lemmas:
            seen_lemmas[lemma_id] = {
                "id": lemma_id,
                "lemma_text": lemma_text,
                "pos_type": pos,
                "disambiguation": disambig,
                "difficulty_level": level,
                "forms": [],
            }
        seen_lemmas[lemma_id]["forms"].append(
            {
                "text": form_text,
                "ipa": ipa,
                "grammatical_form": gram_form,
            }
        )

    return sorted(seen_lemmas.values(), key=lambda w: w["lemma_text"].lower())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/")
def index() -> ResponseReturnValue:
    """Rhyming dictionary index — two-tier browse by ending sound."""
    final_sounds = _distinct_final_sounds()

    # If a final sound is selected, show its rhyme families.
    selected_sound: Optional[str] = request.args.get("sound", "").strip() or None
    valid_sounds = {s for s, _ in final_sounds}

    if selected_sound and selected_sound not in valid_sounds:
        selected_sound = None

    # Default to the most popular final sound.
    if selected_sound is None and final_sounds:
        selected_sound = final_sounds[0][0]

    families: List[Dict[str, Any]] = []
    penultimate_sounds: List[str] = []
    selected_penultimate: Optional[str] = None

    if selected_sound:
        families = _rhyme_families_for_final_sound(selected_sound)

        # Tier 2: collect distinct penultimate sounds for sub-navigation.
        pen_set: Dict[str, int] = {}
        for f in families:
            p = f["penultimate"]
            if p:
                pen_set[p] = pen_set.get(p, 0) + 1
        penultimate_sounds = sorted(pen_set.keys())

        # Filter by penultimate if requested.
        selected_penultimate = request.args.get("pen", "").strip() or None
        if selected_penultimate and selected_penultimate not in pen_set:
            selected_penultimate = None

        if selected_penultimate:
            families = [f for f in families if f["penultimate"] == selected_penultimate]

    total_families = len(families)

    return render_template(
        "rhymes/index.html",
        final_sounds=final_sounds,
        selected_sound=selected_sound,
        penultimate_sounds=penultimate_sounds,
        selected_penultimate=selected_penultimate,
        families=families,
        total_families=total_families,
    )


@bp.route("/family")
def family() -> ResponseReturnValue:
    """Detail view for a single rhyme family."""
    rhyme_key_value: Optional[str] = request.args.get("key", "").strip() or None

    if not rhyme_key_value:
        return render_template(
            "rhymes/family.html",
            rhyme_key=None,
            words=[],
            related_families=[],
            final_sound="",
        )

    words = _family_words(rhyme_key_value)

    # Find related families: same final sound, different penultimate.
    final_sound = rhyme_key_final_sound(rhyme_key_value)
    related: List[Dict[str, Any]] = []
    if final_sound:
        all_families = _rhyme_families_for_final_sound(final_sound)
        related = [f for f in all_families if f["rhyme_key"] != rhyme_key_value]

    return render_template(
        "rhymes/family.html",
        rhyme_key=rhyme_key_value,
        words=words,
        related_families=related,
        final_sound=final_sound,
    )
