"""Export person nouns' male/female words without making them alternatives.

The ordinary translation is the unspecified default. Male and female variants
have independent paradigms and grammatical genders; equal text does not merge
entries (a common-gender noun repeats its word). They come from the gender
variant rows (storage.crud.gender_variant); nothing here infers any.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from storage.models.variant_form import GENDER_VARIANT_KEYS, VARIANT_KIND_GENDER, VariantForm
from storage.release.variant import variants_by_language
from storage.variant_audio import gender_audio_slot


def bulk_gender_variants(
    session: Session, lemma_ids: Sequence[int], languages: Sequence[str]
) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    """Fetch both source and target paradigms in one query, without fallback."""
    grouped: Dict[int, List[VariantForm]] = {}
    if not lemma_ids:
        return {}
    for row in session.query(VariantForm).filter(
        VariantForm.lemma_id.in_(lemma_ids),
        VariantForm.language_code.in_(languages),
        VariantForm.variant_kind == VARIANT_KIND_GENDER,
    ):
        if row.variant_key not in GENDER_VARIANT_KEYS:
            raise ValueError(f"Invalid gender variant key: {row.variant_key!r}")
        grouped.setdefault(row.lemma_id, []).append(row)
    return {lemma_id: variants_by_language(rows) for lemma_id, rows in grouped.items()}


def build_gendered_forms(
    wireword: Mapping[str, Any],
    variants: Mapping[str, List[Dict[str, Any]]],
    target_language: str,
    source_language: str,
    audio_by_guid_form: Mapping[Tuple[str, Optional[str]], Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Build an explicit default and only the target variants actually stored.

    Source counterpart words are included when stored; otherwise the source
    stays the concept's ordinary translation, qualified by referent_gender.
    The app must use that qualifier for a gender-specific prompt. A missing
    target counterpart is never synthesized from the default or source.
    """
    target_variants = {entry["key"]: entry for entry in variants.get(target_language, [])}
    if not target_variants:
        return []
    source_variants = {entry["key"]: entry for entry in variants.get(source_language, [])}
    source_field = "base_english" if source_language == "en" else "base_source"
    default: Dict[str, Any] = {
        "referent_gender": "unspecified",
        "base_target": wireword["base_target"],
        source_field: wireword[source_field],
    }
    for field in ("grammar_metadata", "grammatical_forms", "audio"):
        if field in wireword:
            default[field] = wireword[field]
    result = [default]
    for gender in ("male", "female"):
        variant = target_variants.get(gender)
        if variant is None:
            continue
        bases = [form for form in variant["forms"] if form.get("is_base_form")]
        if len(bases) != 1:
            raise ValueError(f"Gender variant {gender} requires exactly one base form")
        source_variant = source_variants.get(gender)
        source_bases = (
            [form for form in source_variant["forms"] if form.get("is_base_form")]
            if source_variant
            else []
        )
        entry: Dict[str, Any] = {
            "referent_gender": gender,
            "base_target": bases[0]["text"],
            source_field: source_bases[0]["text"] if source_bases else wireword[source_field],
        }
        if variant.get("grammatical_gender") is not None:
            entry["grammar_metadata"] = {"grammatical_gender": variant["grammatical_gender"]}
        base_audio = audio_by_guid_form.get((wireword["guid"], gender_audio_slot(gender)))
        if base_audio:
            entry["audio"] = base_audio
        forms: List[Dict[str, Any]] = []
        for form in variant["forms"]:
            exported_form = dict(form)
            form_audio = audio_by_guid_form.get(
                (wireword["guid"], gender_audio_slot(gender, form["grammatical_form"]))
            )
            if form_audio:
                exported_form["audio"] = form_audio
            forms.append(exported_form)
        entry["grammatical_forms"] = forms
        result.append(entry)
    return result
