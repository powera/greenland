#!/usr/bin/python3

"""Data completeness reports.

Shows per-lemma and per-sentence coverage of translations, IPA,
audio, and relation-group (synonym) membership, filterable by
Trakaido difficulty level.
"""

from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import and_, case, func

from barsukas.config import Config
from storage.models.lemma_relation import LemmaRelationMember
from storage.models.schema import (
    AudioQualityReview,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
    TIER_3_LANGUAGES,
    TIER_4_LANGUAGES,
)

bp = Blueprint("completeness", __name__, url_prefix="/completeness")


def _parse_int(value: str) -> Optional[int]:
    """Parse a string into an int, returning None on any failure."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _lemma_completeness_rows(
    min_level: Optional[int],
    max_level: Optional[int],
    page: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Build per-lemma completeness rows and return (rows, total_count)."""

    tier1_case = case((LemmaTranslation.language_code.in_(TIER_1_LANGUAGES), 1), else_=0)
    tier2_case = case((LemmaTranslation.language_code.in_(TIER_2_LANGUAGES), 1), else_=0)
    tier3_case = case((LemmaTranslation.language_code.in_(TIER_3_LANGUAGES), 1), else_=0)
    ipa_tier12_case = case(
        (
            and_(
                LemmaTranslation.ipa_pronunciation.isnot(None),
                LemmaTranslation.language_code.in_(TIER_1_LANGUAGES + TIER_2_LANGUAGES),
            ),
            1,
        ),
        else_=0,
    )

    # Per-lemma translation aggregates
    trans_sub = (
        g.db.query(
            LemmaTranslation.lemma_id.label("lemma_id"),
            func.count(LemmaTranslation.id).label("trans_total"),
            func.sum(tier1_case).label("tier1_count"),
            func.sum(tier2_case).label("tier2_count"),
            func.sum(tier3_case).label("tier3_count"),
            func.sum(ipa_tier12_case).label("ipa_count"),
        )
        .group_by(LemmaTranslation.lemma_id)
        .subquery()
    )

    # Per-lemma audio review aggregates (staging + prod)
    audio_sub = (
        g.db.query(
            AudioQualityReview.lemma_id.label("lemma_id"),
            func.count(AudioQualityReview.id).label("audio_total"),
            func.sum(case((AudioQualityReview.s3_prod_url.isnot(None), 1), else_=0)).label(
                "audio_prod"
            ),
        )
        .filter(AudioQualityReview.lemma_id.isnot(None))
        .group_by(AudioQualityReview.lemma_id)
        .subquery()
    )

    # Per-lemma sentence usage counts (distinct sentences containing the lemma,
    # via SentenceWord). Non-rejected sentences only.
    sentence_sub = (
        g.db.query(
            SentenceWord.lemma_id.label("lemma_id"),
            func.count(func.distinct(SentenceWord.sentence_id)).label("sentence_count"),
            func.count(
                func.distinct(
                    case((Sentence.verified == True, SentenceWord.sentence_id))
                )  # noqa: E712
            ).label("sentence_verified_count"),
        )
        .join(Sentence, Sentence.id == SentenceWord.sentence_id)
        .filter(SentenceWord.lemma_id.isnot(None))
        .filter(Sentence.rejected == False)  # noqa: E712
        .group_by(SentenceWord.lemma_id)
        .subquery()
    )

    # Per-lemma relation-group membership count (covers synonyms/derivationals)
    relation_sub = (
        g.db.query(
            LemmaRelationMember.lemma_id.label("lemma_id"),
            func.count(LemmaRelationMember.id).label("relation_count"),
        )
        .group_by(LemmaRelationMember.lemma_id)
        .subquery()
    )

    query = (
        g.db.query(
            Lemma.id,
            Lemma.lemma_text,
            Lemma.definition_text,
            Lemma.pos_type,
            Lemma.difficulty_level,
            Lemma.guid,
            func.coalesce(trans_sub.c.trans_total, 0).label("trans_total"),
            func.coalesce(trans_sub.c.tier1_count, 0).label("tier1_count"),
            func.coalesce(trans_sub.c.tier2_count, 0).label("tier2_count"),
            func.coalesce(trans_sub.c.tier3_count, 0).label("tier3_count"),
            func.coalesce(trans_sub.c.ipa_count, 0).label("ipa_count"),
            func.coalesce(audio_sub.c.audio_total, 0).label("audio_total"),
            func.coalesce(audio_sub.c.audio_prod, 0).label("audio_prod"),
            func.coalesce(relation_sub.c.relation_count, 0).label("relation_count"),
            func.coalesce(sentence_sub.c.sentence_count, 0).label("sentence_count"),
            func.coalesce(sentence_sub.c.sentence_verified_count, 0).label(
                "sentence_verified_count"
            ),
        )
        .outerjoin(trans_sub, trans_sub.c.lemma_id == Lemma.id)
        .outerjoin(audio_sub, audio_sub.c.lemma_id == Lemma.id)
        .outerjoin(relation_sub, relation_sub.c.lemma_id == Lemma.id)
        .outerjoin(sentence_sub, sentence_sub.c.lemma_id == Lemma.id)
    )

    if min_level is not None:
        query = query.filter(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        query = query.filter(Lemma.difficulty_level <= max_level)

    query = query.order_by(Lemma.difficulty_level.asc().nullslast(), Lemma.id.asc())

    total = query.count()
    rows = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "lemma_text": r.lemma_text,
                "definition_text": r.definition_text,
                "pos_type": r.pos_type,
                "difficulty_level": r.difficulty_level,
                "guid": r.guid,
                "trans_total": int(r.trans_total or 0),
                "tier1_count": int(r.tier1_count or 0),
                "tier2_count": int(r.tier2_count or 0),
                "tier3_count": int(r.tier3_count or 0),
                "ipa_count": int(r.ipa_count or 0),
                "audio_total": int(r.audio_total or 0),
                "audio_prod": int(r.audio_prod or 0),
                "relation_count": int(r.relation_count or 0),
                "sentence_count": int(r.sentence_count or 0),
                "sentence_verified_count": int(r.sentence_verified_count or 0),
            }
        )
    return result, total


def _sentence_completeness_rows(
    min_level: Optional[int],
    max_level: Optional[int],
    page: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Build per-sentence completeness rows and return (rows, total_count)."""

    tier1_case = case((SentenceTranslation.language_code.in_(TIER_1_LANGUAGES), 1), else_=0)
    tier2_case = case((SentenceTranslation.language_code.in_(TIER_2_LANGUAGES), 1), else_=0)
    tier3_case = case((SentenceTranslation.language_code.in_(TIER_3_LANGUAGES), 1), else_=0)

    trans_sub = (
        g.db.query(
            SentenceTranslation.sentence_id.label("sentence_id"),
            func.count(SentenceTranslation.id).label("trans_total"),
            func.sum(tier1_case).label("tier1_count"),
            func.sum(tier2_case).label("tier2_count"),
            func.sum(tier3_case).label("tier3_count"),
        )
        .group_by(SentenceTranslation.sentence_id)
        .subquery()
    )

    audio_sub = (
        g.db.query(
            AudioQualityReview.sentence_id.label("sentence_id"),
            func.count(AudioQualityReview.id).label("audio_total"),
            func.sum(case((AudioQualityReview.s3_prod_url.isnot(None), 1), else_=0)).label(
                "audio_prod"
            ),
        )
        .filter(AudioQualityReview.sentence_id.isnot(None))
        .group_by(AudioQualityReview.sentence_id)
        .subquery()
    )

    query = (
        g.db.query(
            Sentence.id,
            Sentence.guid,
            Sentence.pattern_type,
            Sentence.minimum_level,
            Sentence.rejected,
            func.coalesce(trans_sub.c.trans_total, 0).label("trans_total"),
            func.coalesce(trans_sub.c.tier1_count, 0).label("tier1_count"),
            func.coalesce(trans_sub.c.tier2_count, 0).label("tier2_count"),
            func.coalesce(trans_sub.c.tier3_count, 0).label("tier3_count"),
            func.coalesce(audio_sub.c.audio_total, 0).label("audio_total"),
            func.coalesce(audio_sub.c.audio_prod, 0).label("audio_prod"),
        )
        .outerjoin(trans_sub, trans_sub.c.sentence_id == Sentence.id)
        .outerjoin(audio_sub, audio_sub.c.sentence_id == Sentence.id)
        .filter(Sentence.rejected == False)  # noqa: E712
    )

    if min_level is not None:
        query = query.filter(Sentence.minimum_level >= min_level)
    if max_level is not None:
        query = query.filter(Sentence.minimum_level <= max_level)

    query = query.order_by(Sentence.minimum_level.asc().nullslast(), Sentence.id.asc())

    total = query.count()
    rows = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    sentence_ids = [r.id for r in rows]

    # Fetch English preview text if present
    preview: Dict[int, str] = {}
    if sentence_ids:
        preview_rows = (
            g.db.query(SentenceTranslation.sentence_id, SentenceTranslation.translation_text)
            .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
            .filter(SentenceTranslation.language_code == "en")
            .all()
        )
        for sentence_id, text in preview_rows:
            preview[sentence_id] = text

    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "guid": r.guid,
                "pattern_type": r.pattern_type,
                "minimum_level": r.minimum_level,
                "preview_text": preview.get(r.id, ""),
                "trans_total": int(r.trans_total or 0),
                "tier1_count": int(r.tier1_count or 0),
                "tier2_count": int(r.tier2_count or 0),
                "tier3_count": int(r.tier3_count or 0),
                "audio_total": int(r.audio_total or 0),
                "audio_prod": int(r.audio_prod or 0),
            }
        )
    return result, total


def _language_summary(
    min_level: Optional[int], max_level: Optional[int]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return per-language summary rows and totals.

    Counts are scoped by Trakaido difficulty level on the parent lemma/sentence
    (using ``Lemma.difficulty_level`` and ``Sentence.minimum_level``).
    """

    lemma_filter = []
    if min_level is not None:
        lemma_filter.append(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        lemma_filter.append(Lemma.difficulty_level <= max_level)

    sentence_filter = [Sentence.rejected == False]  # noqa: E712
    if min_level is not None:
        sentence_filter.append(Sentence.minimum_level >= min_level)
    if max_level is not None:
        sentence_filter.append(Sentence.minimum_level <= max_level)

    # Per-language lemma translation counts
    lemma_trans_q = (
        g.db.query(
            LemmaTranslation.language_code.label("lc"),
            func.count(LemmaTranslation.id).label("lemma_count"),
            func.sum(case((LemmaTranslation.ipa_pronunciation.isnot(None), 1), else_=0)).label(
                "ipa_count"
            ),
            func.sum(case((LemmaTranslation.verified == True, 1), else_=0)).label(  # noqa: E712
                "verified_count"
            ),
        )
        .join(Lemma, Lemma.id == LemmaTranslation.lemma_id)
        .group_by(LemmaTranslation.language_code)
    )
    for cond in lemma_filter:
        lemma_trans_q = lemma_trans_q.filter(cond)
    lemma_trans_by_lang: Dict[str, Dict[str, int]] = {}
    for lc, lemma_count, ipa_count, verified_count in lemma_trans_q.all():
        lemma_trans_by_lang[lc] = {
            "lemma_count": int(lemma_count or 0),
            "ipa_count": int(ipa_count or 0),
            "verified_count": int(verified_count or 0),
        }

    # Per-language sentence translation counts
    sentence_trans_q = (
        g.db.query(
            SentenceTranslation.language_code.label("lc"),
            func.count(SentenceTranslation.id).label("sentence_count"),
        )
        .join(Sentence, Sentence.id == SentenceTranslation.sentence_id)
        .group_by(SentenceTranslation.language_code)
    )
    for cond in sentence_filter:
        sentence_trans_q = sentence_trans_q.filter(cond)
    sentence_trans_by_lang: Dict[str, int] = {
        lc: int(count or 0) for lc, count in sentence_trans_q.all()
    }

    # Per-language lemma audio counts (joined to Lemma for level filter)
    lemma_audio_q = (
        g.db.query(
            AudioQualityReview.language_code.label("lc"),
            func.count(AudioQualityReview.id).label("audio_total"),
            func.sum(case((AudioQualityReview.s3_prod_url.isnot(None), 1), else_=0)).label(
                "audio_prod"
            ),
        )
        .join(Lemma, Lemma.id == AudioQualityReview.lemma_id)
        .filter(AudioQualityReview.lemma_id.isnot(None))
        .group_by(AudioQualityReview.language_code)
    )
    for cond in lemma_filter:
        lemma_audio_q = lemma_audio_q.filter(cond)
    lemma_audio_by_lang: Dict[str, Dict[str, int]] = {}
    for lc, total, prod in lemma_audio_q.all():
        lemma_audio_by_lang[lc] = {
            "audio_total": int(total or 0),
            "audio_prod": int(prod or 0),
        }

    # Per-language sentence audio counts
    sentence_audio_q = (
        g.db.query(
            AudioQualityReview.language_code.label("lc"),
            func.count(AudioQualityReview.id).label("audio_total"),
            func.sum(case((AudioQualityReview.s3_prod_url.isnot(None), 1), else_=0)).label(
                "audio_prod"
            ),
        )
        .join(Sentence, Sentence.id == AudioQualityReview.sentence_id)
        .filter(AudioQualityReview.sentence_id.isnot(None))
        .group_by(AudioQualityReview.language_code)
    )
    for cond in sentence_filter:
        sentence_audio_q = sentence_audio_q.filter(cond)
    sentence_audio_by_lang: Dict[str, Dict[str, int]] = {}
    for lc, total, prod in sentence_audio_q.all():
        sentence_audio_by_lang[lc] = {
            "audio_total": int(total or 0),
            "audio_prod": int(prod or 0),
        }

    # Build ordered rows: Tier 1, Tier 2, then any other languages that appear
    tier_map = [
        ("1", TIER_1_LANGUAGES),
        ("2", TIER_2_LANGUAGES),
        ("3", TIER_3_LANGUAGES),
        ("4", TIER_4_LANGUAGES),
    ]
    ordered_langs: List[Tuple[str, str]] = []
    seen: set = set()
    for tier, langs in tier_map:
        for lc in langs:
            ordered_langs.append((lc, tier))
            seen.add(lc)
    # Append any stray languages that have data but aren't in a known tier
    extras = (
        set(lemma_trans_by_lang)
        | set(sentence_trans_by_lang)
        | set(lemma_audio_by_lang)
        | set(sentence_audio_by_lang)
    ) - seen
    for lc in sorted(extras):
        ordered_langs.append((lc, "–"))

    # Total lemmas/sentences in scope, for reference
    total_lemmas_q = g.db.query(func.count(Lemma.id))
    for cond in lemma_filter:
        total_lemmas_q = total_lemmas_q.filter(cond)
    total_lemmas = int(total_lemmas_q.scalar() or 0)

    total_sentences_q = g.db.query(func.count(Sentence.id))
    for cond in sentence_filter:
        total_sentences_q = total_sentences_q.filter(cond)
    total_sentences = int(total_sentences_q.scalar() or 0)

    rows: List[Dict[str, Any]] = []
    for lc, tier in ordered_langs:
        lt = lemma_trans_by_lang.get(lc, {})
        la = lemma_audio_by_lang.get(lc, {})
        sa = sentence_audio_by_lang.get(lc, {})
        rows.append(
            {
                "language_code": lc,
                "tier": tier,
                "lemma_translations": lt.get("lemma_count", 0),
                "lemma_verified": lt.get("verified_count", 0),
                "lemma_ipa": lt.get("ipa_count", 0),
                "lemma_audio_total": la.get("audio_total", 0),
                "lemma_audio_prod": la.get("audio_prod", 0),
                "sentence_translations": sentence_trans_by_lang.get(lc, 0),
                "sentence_audio_total": sa.get("audio_total", 0),
                "sentence_audio_prod": sa.get("audio_prod", 0),
            }
        )

    totals = {
        "total_lemmas": total_lemmas,
        "total_sentences": total_sentences,
    }
    return rows, totals


@bp.route("/")
def index() -> ResponseReturnValue:
    """Data completeness summary, aggregated by language."""
    min_level = _parse_int(request.args.get("min_level", "").strip())
    max_level = _parse_int(request.args.get("max_level", "").strip())

    rows, totals = _language_summary(min_level, max_level)

    return render_template(
        "completeness/index.html",
        rows=rows,
        totals=totals,
        min_level=request.args.get("min_level", "").strip(),
        max_level=request.args.get("max_level", "").strip(),
    )


@bp.route("/stats")
def stats() -> ResponseReturnValue:
    """Per-lemma/sentence completeness stats (detailed table)."""
    scope = request.args.get("scope", "lemmas").strip()
    if scope not in ("lemmas", "sentences"):
        scope = "lemmas"

    min_level = _parse_int(request.args.get("min_level", "").strip())
    max_level = _parse_int(request.args.get("max_level", "").strip())
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1

    if scope == "lemmas":
        rows, total = _lemma_completeness_rows(min_level, max_level, page)
    else:
        rows, total = _sentence_completeness_rows(min_level, max_level, page)

    total_pages = max(1, (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE)

    return render_template(
        "completeness/stats.html",
        scope=scope,
        rows=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        min_level=request.args.get("min_level", "").strip(),
        max_level=request.args.get("max_level", "").strip(),
        tier1_total=len(TIER_1_LANGUAGES),
        tier2_total=len(TIER_2_LANGUAGES),
        tier3_total=len(TIER_3_LANGUAGES),
    )
