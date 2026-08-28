#!/usr/bin/python3

"""Deterministic heuristic scoring of a concept's lexical stratum ("term age").

Operational definition used here:
- A concept is "ancient" if ordinary pre-modern languages had a conventional
  word for it (leg, water, ship, salt), and "modern" if they did not and the
  rendering has to be a loan or a coinage (computer, bicycle, tomato).
- This is a heuristic for triage and reporting, not an etymological claim about
  any particular word form.

Signals, strongest first:

1. **Classical-language consensus.** ``LemmaTranslation.translation_status``
   across :data:`~storage.translation_helpers.ANCIENT_LANGUAGE_GROUP`. A
   ``conventional`` rendering in Latin or Sanskrit is direct evidence the
   concept existed; ``modern_loan``/``late_construction``/``descriptive`` is
   direct evidence it did not. This dominates when present.

2. **Japanese orthography.** Deterministic and free, but weaker than it looks,
   because it fails in two *systematic* directions (see
   :func:`japanese_signal`).

3. **Semantic domain prior.** ``pos_subtype`` correlates with age: body parts
   and animals are ancient, digital technology is not.

This module is pure and deterministic (no DB/LLM calls); the DB adapter is
:func:`score_term_age_for_lemma`. Nothing here is persisted - the score is
derived on demand from stored evidence, so it cannot go stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence

from sqlalchemy.orm import Session, selectinload

from langtools.ja.script_analysis import JapaneseScriptType, classify_japanese_script
from storage.models.enums import NounSubtype
from storage.models.schema import Lemma
from storage.translation_helpers import ANCIENT_LANGUAGE_GROUP


class LexicalStratum(Enum):
    """Coarse age bands, ordered ancient -> modern."""

    ANCIENT_CORE = "ancient_core"
    TRADITIONAL = "traditional"
    EARLY_MODERN = "early_modern"
    MODERN = "modern"
    UNKNOWN = "unknown"


#: Subtypes naming a specific real-world entity. Japanese writes these in
#: katakana as a transliteration of the foreign name, which says nothing about
#: the concept's age - Berlin and Paris are ancient cities spelled ベルリン and
#: パリ. The katakana signal is suppressed entirely for these.
#:
#: ``PLACE_NAME`` is deliberately absent: despite the name it covers generic
#: place nouns (room, street), which are ordinary vocabulary.
NAMED_ENTITY_SUBTYPES: frozenset[str] = frozenset(
    {
        NounSubtype.PERSONAL_NAME.value,
        NounSubtype.REGION.value,
        NounSubtype.CITY.value,
        NounSubtype.GEOGRAPHIC_PLACE.value,
        NounSubtype.ORGANIZATION_NAME.value,
        NounSubtype.TEMPORAL_NAME.value,
        NounSubtype.NATIONALITY.value,
    }
)

#: ``translation_status`` values, mapped to their pull toward "modern".
#: ``conventional`` is evidence of age; the coinage values are evidence of
#: modernity; ``uncertain`` abstains.
#:
#: ``modern_reimagining`` scores as *modern* despite naming an ancient word,
#: because the status is about the concept rather than the form: Sanskrit
#: विमानम् is genuinely Vedic, but a mythological flying palace is not a word for
#: "airplane". Such cases previously scored ``conventional`` and pulled a plainly
#: modern concept toward ancient against the other four languages.
STATUS_MODERNITY: Mapping[str, float] = {
    "conventional": -1.0,
    "late_construction": 1.0,
    "modern_loan": 1.0,
    "modern_reimagining": 1.0,
    "descriptive": 0.6,
    "uncertain": 0.0,
}

#: Japanese script types, mapped to their pull toward "modern".
SCRIPT_MODERNITY: Mapping[JapaneseScriptType, float] = {
    JapaneseScriptType.KANJI: -0.35,
    JapaneseScriptType.MIXED: -0.25,
    JapaneseScriptType.HIRAGANA: -0.15,
    JapaneseScriptType.KANA: -0.10,
    JapaneseScriptType.KATAKANA: 0.45,
    JapaneseScriptType.NONE: 0.0,
}

#: ``pos_subtype`` priors. Mixed-stratum subtypes (vehicle, occupation) get only
#: a mild pull so the other signals can break the tie: a cart and a bus are both
#: vehicles, a farmer and a programmer both occupations.
SUBTYPE_MODERNITY: Mapping[str, float] = {
    # Strongly ancient
    "body_part": -0.30,
    "animal": -0.30,
    "plant": -0.30,
    "plant_part": -0.30,
    "family_relation": -0.30,
    "natural_feature": -0.30,
    "food": -0.20,
    "beverage": -0.20,
    "emotion_feeling": -0.20,
    "color": -0.20,
    "weather_phenomenon": -0.20,
    # Strongly modern
    "technology_digital": 0.35,
    "electronic_device": 0.35,
    "appliance": 0.35,
    "chemical_compound": 0.30,
    # Mildly modern / mixed
    "vehicle": 0.15,
    "medication_remedy": 0.15,
    "path_infrastructure": 0.15,
    "occupation": 0.15,
    "social_institution": 0.15,
}

#: Upper bound of each stratum on the 0.0 (ancient) .. 1.0 (modern) scale.
STRATUM_THRESHOLDS: Sequence[tuple[float, LexicalStratum]] = (
    (0.30, LexicalStratum.ANCIENT_CORE),
    (0.50, LexicalStratum.TRADITIONAL),
    (0.70, LexicalStratum.EARLY_MODERN),
    (1.01, LexicalStratum.MODERN),
)

#: Neutral midpoint that signals push away from.
NEUTRAL_SCORE = 0.5

#: Confidence needed before the outer, strongly-worded bands
#: (:attr:`LexicalStratum.ANCIENT_CORE` and :attr:`LexicalStratum.MODERN`) may
#: be claimed. Below it a score in an outer band is reported as the adjacent
#: hedged band instead.
#:
#: This exists because a single weak signal can otherwise carry a lemma across
#: an outer threshold on its own: a ``mixed`` Japanese script contributes -0.25,
#: which lands under the 0.30 ancient cutoff with no other evidence at all. That
#: is right for *big* and *small* but not something to assert for *rectangular*
#: or *oval*, and 1470 of 2575 lemmas were in exactly that position. Requiring
#: corroboration keeps the confident labels meaningful.
CONFIDENT_BAND_MIN_CONFIDENCE = 0.35

#: Weight applied to the averaged classical-language consensus. Larger than any
#: other signal's maximum, so unanimous classical evidence decides the stratum
#: on its own.
ANCIENT_CONSENSUS_WEIGHT = 0.55

#: How much the weaker signals still count once classical evidence exists.
#:
#: The classical consensus is an average, so mixed evidence lands near zero even
#: when it is genuinely informative: *spoon* is ``conventional`` in Latin, Greek
#: and Sanskrit but a coinage in Old Norse and Classical Arabic, averaging to
#: only -0.20. Left at full strength the katakana signal (+0.45, because
#: Japanese writes スプーン as a loan) would then outvote three classical
#: languages that plainly had the word, and *spoon*, *cup* and *fork* scored
#: modern. Direct evidence about the concept must outrank orthography about one
#: language, so the weak signals are damped rather than dropped - they still
#: break ties, but they cannot overturn the classical verdict.
CORROBORATED_WEAK_SIGNAL_SCALE = 0.4


@dataclass(frozen=True)
class TermAgeResult:
    """Heuristic term-age decision with component signals and reason codes."""

    lemma_text: str
    stratum: LexicalStratum
    score: float
    confidence: float
    ancient_modernity: Optional[float]
    ancient_conventional_count: int
    ancient_evidence_count: int
    japanese_script: Optional[JapaneseScriptType]
    japanese_modernity: float
    subtype_modernity: float
    reasons: tuple[str, ...]


def ancient_signal(
    statuses: Mapping[str, Optional[str]],
) -> tuple[Optional[float], int, int, tuple[str, ...]]:
    """Score the classical-language consensus.

    Args:
        statuses: ``translation_status`` by language code. Codes outside the
            ancient group are ignored, and a ``None`` status means the language
            has a translation but no judgement, which is not evidence.

    Returns:
        ``(modernity, conventional_count, evidence_count, reasons)`` where
        ``modernity`` is the mean pull in ``[-1.0, 1.0]``, or ``None`` when no
        language carried a usable status.
    """
    reasons: list[str] = []
    pulls: list[float] = []
    conventional = 0

    for language_code in ANCIENT_LANGUAGE_GROUP:
        status = statuses.get(language_code)
        if not status:
            continue
        pull = STATUS_MODERNITY.get(status)
        if pull is None:
            reasons.append(f"ancient_status_unknown_value:{language_code}:{status}")
            continue
        pulls.append(pull)
        if status == "conventional":
            conventional += 1

    if not pulls:
        reasons.append("ancient_no_evidence")
        return None, 0, 0, tuple(reasons)

    modernity = sum(pulls) / len(pulls)
    reasons.append(f"ancient_consensus:{conventional}/{len(pulls)}_conventional")
    return modernity, conventional, len(pulls), tuple(reasons)


def japanese_signal(
    japanese_translation: Optional[str],
    pos_subtype: Optional[str],
) -> tuple[Optional[JapaneseScriptType], float, tuple[str, ...]]:
    """Score Japanese orthography, suppressing the named-entity confound.

    Katakana marks a Western loanword, which usually marks a modern concept -
    but the inference fails in two systematic ways, so this signal is weighted
    below the classical consensus and gated here:

    * **Named entities.** ベルリン (Berlin) is katakana because it transliterates
      a foreign name, not because the city is modern. Suppressed outright.
    * **Native flora and fauna.** Japanese conventionally writes animal and
      plant names in katakana (クマ bear, ネズミ mouse), so the subtype prior has
      to pull back against it. That is handled by the ``animal``/``plant``
      priors in :data:`SUBTYPE_MODERNITY` rather than here.

    Two further failure modes are *not* correctable from Japanese alone, which
    is the reason this signal is capped below the classical consensus:

    * **Katakana marks cultural novelty, not chronological age.** チーズ
      (cheese), バター (butter) and パン (bread) are katakana because dairy and
      leavened bread were foreign to Japan - not because the foods are recent.
      Only classical evidence separates these from genuinely modern items, and
      it does: *bread* carries a negative ancient consensus that pulls it back
      out of the modern band, while *tomato* does not.
    * **Kanji does not mean ancient.** 自転車 (bicycle) and 携帯電話 (cell phone)
      are modern concepts built as Sino-Japanese compounds of old morphemes, so
      kanji only rules out a *Western* loan.
    """
    if not japanese_translation:
        return None, 0.0, ("japanese_absent",)

    script = classify_japanese_script(japanese_translation)
    pull = SCRIPT_MODERNITY.get(script, 0.0)

    if script == JapaneseScriptType.KATAKANA and pos_subtype in NAMED_ENTITY_SUBTYPES:
        return script, 0.0, (f"katakana_suppressed_named_entity:{pos_subtype}",)

    if pull == 0.0:
        return script, 0.0, (f"japanese_script_neutral:{script.value}",)

    return script, pull, (f"japanese_script:{script.value}",)


def subtype_signal(pos_subtype: Optional[str]) -> tuple[float, tuple[str, ...]]:
    """Score the semantic-domain prior for a ``pos_subtype``."""
    if not pos_subtype:
        return 0.0, ("subtype_absent",)
    pull = SUBTYPE_MODERNITY.get(pos_subtype)
    if pull is None:
        return 0.0, (f"subtype_neutral:{pos_subtype}",)
    return pull, (f"subtype_prior:{pos_subtype}",)


def stratum_for_score(score: float, confidence: float = 1.0) -> LexicalStratum:
    """Return the stratum band containing ``score``, hedged by ``confidence``.

    The outer bands make a strong claim, so they require corroboration: below
    :data:`CONFIDENT_BAND_MIN_CONFIDENCE` an ancient-core score is reported as
    ``TRADITIONAL`` and a modern score as ``EARLY_MODERN``. See that constant
    for why.
    """
    band = LexicalStratum.MODERN
    for upper_bound, stratum in STRATUM_THRESHOLDS:
        if score < upper_bound:
            band = stratum
            break

    if confidence < CONFIDENT_BAND_MIN_CONFIDENCE:
        if band is LexicalStratum.ANCIENT_CORE:
            return LexicalStratum.TRADITIONAL
        if band is LexicalStratum.MODERN:
            return LexicalStratum.EARLY_MODERN
    return band


def score_term_age(
    *,
    lemma_text: str,
    pos_subtype: Optional[str] = None,
    japanese_translation: Optional[str] = None,
    ancient_statuses: Optional[Mapping[str, Optional[str]]] = None,
) -> TermAgeResult:
    """Score one concept's lexical stratum from the available signals.

    Pure: every input is passed in, nothing is read or written.

    Confidence reflects how much evidence actually voted. Classical evidence
    counts for more than the free signals, and a concept with no Japanese
    translation and a neutral subtype scores :attr:`LexicalStratum.UNKNOWN` at
    zero confidence rather than defaulting to the middle band.
    """
    reasons: list[str] = []

    ancient_modernity, conventional_count, evidence_count, ancient_reasons = ancient_signal(
        ancient_statuses or {}
    )
    reasons.extend(ancient_reasons)

    script, japanese_modernity, japanese_reasons = japanese_signal(
        japanese_translation, pos_subtype
    )
    reasons.extend(japanese_reasons)

    subtype_modernity, subtype_reasons = subtype_signal(pos_subtype)
    reasons.extend(subtype_reasons)

    weak_scale = 1.0 if ancient_modernity is None else CORROBORATED_WEAK_SIGNAL_SCALE
    score = NEUTRAL_SCORE + (japanese_modernity + subtype_modernity) * weak_scale
    if ancient_modernity is not None:
        score += ancient_modernity * ANCIENT_CONSENSUS_WEIGHT
        reasons.append("weak_signals_damped_by_classical_evidence")
    score = min(1.0, max(0.0, score))

    # Confidence: classical evidence is the trustworthy signal, so it carries
    # most of the weight and scales with how many languages agreed.
    confidence = 0.0
    if evidence_count:
        confidence += 0.6 * (evidence_count / len(ANCIENT_LANGUAGE_GROUP))
    if japanese_modernity:
        confidence += 0.25
    if subtype_modernity:
        confidence += 0.15
    confidence = min(1.0, confidence)

    if confidence == 0.0:
        stratum = LexicalStratum.UNKNOWN
        reasons.append("no_signals_fired")
    else:
        stratum = stratum_for_score(score, confidence)
        if confidence < CONFIDENT_BAND_MIN_CONFIDENCE:
            reasons.append("hedged_low_confidence")

    return TermAgeResult(
        lemma_text=lemma_text,
        stratum=stratum,
        score=score,
        confidence=confidence,
        ancient_modernity=ancient_modernity,
        ancient_conventional_count=conventional_count,
        ancient_evidence_count=evidence_count,
        japanese_script=script,
        japanese_modernity=japanese_modernity,
        subtype_modernity=subtype_modernity,
        reasons=tuple(reasons),
    )


def score_term_age_for_lemma(lemma: Lemma) -> TermAgeResult:
    """Score a lemma using its already-loaded translations.

    Reads ``lemma.translations`` rather than issuing per-language queries, so a
    caller iterating many lemmas should eager-load that relationship (see
    :func:`score_term_age_for_lemmas`) to avoid N+1 queries.
    """
    ancient_statuses: dict[str, Optional[str]] = {}
    japanese_translation: Optional[str] = None

    for translation in lemma.translations:
        if translation.language_code in ANCIENT_LANGUAGE_GROUP:
            ancient_statuses[translation.language_code] = translation.translation_status
        elif translation.language_code == "ja":
            japanese_translation = translation.translation

    return score_term_age(
        lemma_text=lemma.lemma_text,
        pos_subtype=lemma.pos_subtype,
        japanese_translation=japanese_translation,
        ancient_statuses=ancient_statuses,
    )


def score_term_age_for_lemmas(session: Session) -> list[TermAgeResult]:
    """Score every lemma in the database, eager-loading translations."""
    lemmas = (
        session.query(Lemma).options(selectinload(Lemma.translations)).order_by(Lemma.guid).all()
    )
    return [score_term_age_for_lemma(lemma) for lemma in lemmas]
