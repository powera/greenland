"""Release-file serialization for derivative forms and synonyms.

A lemma's per-language line carries two arrays built from ``derivative_forms``
rows.  They are split by :data:`NON_INFLECTION_GRAMMATICAL_FORMS`:

``forms``
    True inflections -- "dogs", "grayer".  One entry per grammatical slot, so
    a repeated ``grammatical_form`` within a lemma/language is a data error.
    Each entry records ``is_base_form``.

``synonyms``
    Synonym-class relations plus ``abbreviation`` / ``expanded_form``.  The
    same relation label legitimately repeats ("bike" and "cycle" are both
    ``synonym_near`` of "bicycle"), so this array is not keyed by slot and has
    no ``is_base_form``.

Alternate spellings belong to neither array: "grey" is the same lexeme as
"gray" (not a synonym) written differently (not an inflection), and carries a
full paradigm of its own.  Those are ``variant_forms`` rows, serialized by
:mod:`storage.release.variant` into a third array.

The record shape here matches :func:`storage.release.variant.form_to_record`
so that a form reads the same whichever array it appears in.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple

from storage.models.schema import NON_INFLECTION_GRAMMATICAL_FORMS

# Lazily built by _paradigm_rank(); see the note there on the deferred import.
_PARADIGM_RANK: Optional[Dict[str, int]] = None

__all__ = [
    "form_to_record",
    "forms_by_language",
    "in_paradigm_order",
    "split_forms_and_synonyms",
]


def form_to_record(form: Any, *, include_base_form: bool) -> Dict[str, Any]:
    """Build the release entry for one derivative form.

    Pronunciations are omitted when unset rather than written as ``null``,
    matching how ``variants`` is written on the same line.

    Args:
        form: A ``DerivativeForm`` ORM row.
        include_base_form: Whether to record ``is_base_form``.  True for
            inflections, which occupy a grammatical slot; false for synonyms,
            which have no such notion.
    """
    record: Dict[str, Any] = {
        "grammatical_form": form.grammatical_form,
        "text": form.derivative_form_text,
    }
    if include_base_form:
        record["is_base_form"] = form.is_base_form
    if form.ipa_pronunciation:
        record["ipa"] = form.ipa_pronunciation
    if form.phonetic_pronunciation:
        record["phonetic"] = form.phonetic_pronunciation
    return record


def split_forms_and_synonyms(
    forms: Iterable[Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition one language's derivative forms into the two release arrays.

    Inflections are written in *paradigm* order -- "positive", "comparative",
    "superlative" -- taken from the language's
    :class:`~langtools.llm_forms_base.LanguageFormSpec`, which is the same
    order the shipped files already use and the order a reader expects.
    Sorting them alphabetically would be stable but would scramble the
    paradigm.  Synonyms have no intrinsic order, so they are sorted.

    Returns:
        ``(inflections, synonyms)``, each a list of release records.
    """
    inflections: List[Dict[str, Any]] = []
    synonyms: List[Dict[str, Any]] = []

    for form in forms:
        if form.grammatical_form in NON_INFLECTION_GRAMMATICAL_FORMS:
            synonyms.append(form_to_record(form, include_base_form=False))
        else:
            inflections.append(form_to_record(form, include_base_form=True))

    return in_paradigm_order(inflections), _sorted_records(synonyms)


def forms_by_language(
    forms: Iterable[Any],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
    """Group a lemma's derivative forms into per-language release arrays.

    Args:
        forms: The lemma's ``derivative_forms`` rows, any language.

    Returns:
        ``(forms_by_lang, synonyms_by_lang)``.  A language absent from a map
        has nothing of that kind, so callers can test membership to decide
        whether to write the key at all.
    """
    by_language: Dict[str, List[Any]] = {}
    for form in forms:
        by_language.setdefault(form.language_code, []).append(form)

    forms_by_lang: Dict[str, List[Dict[str, Any]]] = {}
    synonyms_by_lang: Dict[str, List[Dict[str, Any]]] = {}
    for language_code, language_forms in by_language.items():
        inflections, synonyms = split_forms_and_synonyms(language_forms)
        if inflections:
            forms_by_lang[language_code] = inflections
        if synonyms:
            synonyms_by_lang[language_code] = synonyms

    return forms_by_lang, synonyms_by_lang


def _sorted_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order records by slot then text, so re-export is byte-stable."""
    return sorted(records, key=lambda record: (record["grammatical_form"], record["text"]))


def _paradigm_rank() -> Dict[str, int]:
    """Map each known ``grammatical_form`` to its position in its paradigm.

    Built from every registered :data:`~langtools.form_registry.FORM_SPECS`
    entry, whose ``form_fields`` is ordered and whose ``form_mapping`` resolves
    those field names to ``grammatical_form`` values.  A slot registered by
    more than one spec keeps the first rank seen; the orders agree wherever
    they overlap, and disagreement between two languages' paradigms cannot
    matter because a release line holds one language.

    Cached, since the registry is fixed once imported.
    """
    global _PARADIGM_RANK
    if _PARADIGM_RANK is None:
        # Imported lazily: langtools.form_registry imports storage.models.enums
        # and scans every langtools/*/forms_config.py at import time, which is
        # far too much to pull in for a module that may only be serializing
        # synonyms.
        from langtools.form_registry import FORM_SPECS

        rank: Dict[str, int] = {}
        for spec in FORM_SPECS.values():
            for position, field_name in enumerate(spec.form_fields):
                grammatical_form = spec.form_mapping.get(field_name)
                if grammatical_form is None:
                    continue
                rank.setdefault(grammatical_form.value, position)
        _PARADIGM_RANK = rank
    return _PARADIGM_RANK


def in_paradigm_order(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order inflections by paradigm position, unknown slots last by name.

    An unregistered slot has no paradigm position to sort by, so it falls to
    the end in name order rather than silently landing at the front.
    """
    rank = _paradigm_rank()
    unknown = len(rank)
    return sorted(
        records,
        key=lambda record: (
            rank.get(record["grammatical_form"], unknown),
            record["grammatical_form"],
            record["text"],
        ),
    )
