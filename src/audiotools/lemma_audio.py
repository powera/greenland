"""Plan lemma recordings and share assets between equal spoken forms.

Slots retain independent review rows so editing one word never invalidates a
different word's reference to the same asset. Sharing stays within one GUID,
audio language (including accent), and voice; spelling is compared exactly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from audiotools.review_records import find_existing_review
from langtools.dialect_overrides import get_translation_language
from storage.models.schema import AudioQualityReview, DerivativeForm, Lemma
from storage.models.variant_form import VARIANT_KIND_GENDER, VariantForm
from storage.translation_helpers import get_translation
from storage.variant_audio import gender_audio_slot


@dataclass(frozen=True)
class LemmaAudioTarget:
    slot: Optional[str]
    text: str
    ipa: Optional[str] = None


def lemma_audio_targets(
    session: Session,
    lemma: Lemma,
    language_code: str,
    include_variants: bool = True,
    include_forms: bool = False,
) -> List[LemmaAudioTarget]:
    """Use stored text only; presentation dialects read their parent variety."""
    text_language = get_translation_language(language_code)
    targets: Dict[Optional[str], LemmaAudioTarget] = {}
    text = get_translation(session, lemma, text_language)
    if text:
        targets[None] = LemmaAudioTarget(None, text)
    if include_forms:
        for form in (
            session.query(DerivativeForm)
            .filter_by(lemma_id=lemma.id, language_code=text_language)
            .order_by(DerivativeForm.id)
        ):
            if (
                form.grammatical_form in targets
                and targets[form.grammatical_form].text != form.derivative_form_text
            ):
                raise ValueError(f"Ambiguous audio form: {form.grammatical_form}")
            targets[form.grammatical_form] = LemmaAudioTarget(
                form.grammatical_form, form.derivative_form_text, form.ipa_pronunciation
            )
    if include_variants:
        for variant in (
            session.query(VariantForm)
            .filter_by(
                lemma_id=lemma.id, language_code=text_language, variant_kind=VARIANT_KIND_GENDER
            )
            .order_by(VariantForm.variant_key, VariantForm.grammatical_form)
        ):
            if variant.is_base_form or include_forms:
                slot = gender_audio_slot(
                    variant.variant_key, None if variant.is_base_form else variant.grammatical_form
                )
                targets[slot] = LemmaAudioTarget(
                    slot, variant.variant_form_text, variant.ipa_pronunciation
                )
    return list(targets.values())


def audio_target(session: Session, lemma: Lemma, language: str, slot: str) -> LemmaAudioTarget:
    for target in lemma_audio_targets(session, lemma, language, include_forms=True):
        if target.slot == slot:
            return target
    raise ValueError(f"No stored audio target for {lemma.guid}/{language}/{slot}")


_ASSET_FIELDS = (
    "filename",
    "expected_text",
    "manifest_md5",
    "s3_staging_url",
    "s3_staging_manifest_url",
    "s3_prod_url",
    "staging_agent",
    "status",
    "quality_issues",
    "notes",
    "reviewed_at",
    "reviewed_by",
    "accepted_at",
    "accepted_by",
)


def alias_recording(
    session: Session, source: AudioQualityReview, slot: Optional[str]
) -> AudioQualityReview:
    """Reference one asset from another slot, preserving its review verdict."""
    destination = find_existing_review(
        session, source.language_code, source.voice_name, guid=source.guid, grammatical_form=slot
    )
    if destination is source:
        return source
    if destination is None:
        destination = AudioQualityReview(
            guid=source.guid,
            lemma_id=source.lemma_id,
            language_code=source.language_code,
            voice_name=source.voice_name,
            grammatical_form=slot,
        )
        session.add(destination)
    for field in _ASSET_FIELDS:
        setattr(destination, field, getattr(source, field))
    session.flush()
    return destination


def reusable_recording(
    session: Session,
    lemma: Lemma,
    language: str,
    voice: str,
    target: LemmaAudioTarget,
    output_dir: Path,
    require_upload: bool = False,
    require_approved: bool = False,
    link: bool = True,
) -> Optional[AudioQualityReview]:
    """Reuse healthy text-driven recordings; never cross voice or accent boundaries."""
    rows = (
        session.query(AudioQualityReview)
        .filter_by(
            guid=lemma.guid, language_code=language, voice_name=voice, expected_text=target.text
        )
        .filter(
            AudioQualityReview.status.in_(("approved", "approved_with_issues", "pending_review"))
        )
        .order_by(AudioQualityReview.id)
        .all()
    )
    for row in sorted(
        rows, key=lambda item: item.status not in ("approved", "approved_with_issues")
    ):
        if not row.manifest_md5:
            continue
        if require_approved and not (
            row.status in ("approved", "approved_with_issues") and row.s3_prod_url
        ):
            continue
        uploaded = bool(row.s3_prod_url or row.s3_staging_url)
        if require_upload and not uploaded:
            continue
        if not uploaded and not (output_dir / language / voice / row.filename).is_file():
            continue
        # IPA-driven generation is handled separately, without text-only reuse.
        return alias_recording(session, row, target.slot) if link else row
    return None


def generate_lemma_audio_targets(
    session: Session,
    lemma: Lemma,
    language: str,
    generate: Callable[[LemmaAudioTarget], Dict[str, Any]],
    include_variants: bool = True,
    include_forms: bool = False,
    use_ipa: bool = False,
) -> Dict[str, Any]:
    """Generate each distinct spoken form once, including on forced regeneration."""
    results: List[Dict[str, Any]] = []
    seen: Dict[tuple[str, Optional[str]], LemmaAudioTarget] = {}
    for target in lemma_audio_targets(session, lemma, language, include_variants, include_forms):
        identity = (target.text, target.ipa if use_ipa else None)
        original = seen.get(identity)
        if original is not None:
            for row in (
                session.query(AudioQualityReview)
                .filter_by(
                    guid=lemma.guid,
                    language_code=language,
                    grammatical_form=original.slot,
                    expected_text=target.text,
                )
                .filter(
                    AudioQualityReview.status.in_(
                        ("approved", "approved_with_issues", "pending_review")
                    )
                )
                .all()
            ):
                alias_recording(session, row, target.slot)
            continue
        result = generate(target)
        result["grammatical_form"] = target.slot
        results.append(result)
        if result.get("success"):
            seen[identity] = target
    session.commit()
    return {
        "success": bool(results) and all(result.get("success") for result in results),
        "lemma_guid": lemma.guid,
        "guid": lemma.guid,
        "language": language,
        "targets": results,
        "voices": [voice for result in results for voice in result.get("voices", [])],
        "error": next(
            (
                result.get("error", "Audio generation failed")
                for result in results
                if not result.get("success")
            ),
            None,
        ),
    }
