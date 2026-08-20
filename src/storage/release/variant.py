"""Build and read the per-language ``variants`` array in ``{lang}.jsonl``.

A variant is the *same lexeme* spelled differently -- "grey" for "gray" -- and
carries a full paradigm of its own, which is why it is neither a ``synonym``
(a different lexeme) nor one of the lemma's own ``forms`` (a different
grammatical slot).  See ``storage/models/variant_form.py``.

The release shape groups by variant so each paradigm stays together::

    "variants": [
      {"kind": "spelling", "key": "grey", "forms": [
        {"grammatical_form": "adjective/en_positive", "text": "grey",
         "is_base_form": true},
        {"grammatical_form": "adjective/en_comparative", "text": "greyer",
         "is_base_form": false}]}]

``kind`` and ``key`` together identify the variant within a lemma and language,
matching the table's unique constraint.  Ordering is fixed -- variants by
(kind, key), forms by grammatical form -- so re-exporting an unchanged database
does not churn the file.

Everything that moves variants between the database and ``data/release`` builds
the array here: the two loaders in ``storage.migrate`` had grown independent
copies of this grouping, and the sync blueprint would have been a third.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.release.derivative_form import in_paradigm_order

#: Identifies one variant paradigm within a lemma and language.
VariantIdentity = Tuple[str, str]


def form_to_record(variant_form: VariantForm) -> Dict[str, Any]:
    """Build the release entry for one grammatical form of a variant.

    Pronunciations are omitted when unset rather than written as ``null``,
    matching how ``forms`` and ``synonyms`` are written on the same line.
    """
    record: Dict[str, Any] = {
        "grammatical_form": variant_form.grammatical_form,
        "text": variant_form.variant_form_text,
        "is_base_form": variant_form.is_base_form,
    }
    if variant_form.ipa_pronunciation:
        record["ipa"] = variant_form.ipa_pronunciation
    if variant_form.phonetic_pronunciation:
        record["phonetic"] = variant_form.phonetic_pronunciation
    return record


def _sorted_forms(forms: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order a variant's forms exactly as the lemma's own ``forms`` array is.

    A variant carries a full paradigm, so it reads in paradigm order
    ("grey", "greyer", "greyest") rather than alphabetically -- the same
    ordering ``storage.release.derivative_form`` applies to ``forms``, so the
    two arrays on one line cannot disagree about how a paradigm is laid out.
    """
    return in_paradigm_order(list(forms))


def paradigms_to_records(
    paradigms: Dict[VariantIdentity, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Turn ``{(kind, key): [form, ...]}`` into the release ``variants`` array."""
    return [
        {"kind": kind, "key": key, "forms": _sorted_forms(forms)}
        for (kind, key), forms in sorted(paradigms.items())
    ]


def variants_by_language(
    variant_forms: Iterable[VariantForm],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group a lemma's variant rows into ``{language_code: variants array}``.

    Languages with no variants are absent rather than mapped to an empty list,
    so a caller can test membership to decide whether to write the key at all.
    """
    grouped: Dict[str, Dict[VariantIdentity, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for variant_form in variant_forms:
        grouped[variant_form.language_code][
            (variant_form.variant_kind, variant_form.variant_key)
        ].append(form_to_record(variant_form))

    return {
        language_code: paradigms_to_records(paradigms)
        for language_code, paradigms in grouped.items()
    }


def records_to_paradigms(entries: Any) -> Dict[VariantIdentity, List[Dict[str, Any]]]:
    """Parse a release ``variants`` array back into ``{(kind, key): [form, ...]}``.

    Malformed entries are skipped rather than raising: a variant missing its key,
    or a form missing its text or grammatical slot, carries no information, and a
    hand-edited file should not stop a whole category from loading.
    """
    paradigms: Dict[VariantIdentity, List[Dict[str, Any]]] = {}
    if not isinstance(entries, list):
        return paradigms

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key") or ""
        if not key:
            continue
        kind = entry.get("kind") or VARIANT_KIND_SPELLING

        forms: List[Dict[str, Any]] = []
        for form_entry in entry.get("forms") or []:
            if not isinstance(form_entry, dict):
                continue
            text = form_entry.get("text") or ""
            grammatical_form = form_entry.get("grammatical_form") or ""
            if not text or not grammatical_form:
                continue
            record: Dict[str, Any] = {
                "grammatical_form": grammatical_form,
                "text": text,
                "is_base_form": bool(form_entry.get("is_base_form", False)),
            }
            if form_entry.get("ipa"):
                record["ipa"] = form_entry["ipa"]
            if form_entry.get("phonetic"):
                record["phonetic"] = form_entry["phonetic"]
            forms.append(record)

        if forms:
            paradigms[(str(kind), str(key))] = _sorted_forms(forms)
    return paradigms
