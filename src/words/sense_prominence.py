"""Rate how prominent each sense of a shared spelling is, via an LLM.

``Lemma.sense_prominence`` only ever matters when several lemmas share a
surface form: ``wordfreq.lexeme_frequency.get_token_share`` splits that form's
corpus frequency between them in proportion to
``SENSE_PROMINENCE_WEIGHTS[prominence]``. A word with no homograph takes the
whole frequency whatever its label says, so rating it is wasted spend.

This module therefore works on *groups*: every set of two or more lemmas that
share ``lemma_text``. All senses in a group go into one LLM call, because the
question is comparative -- "top" the highest point beats "top" the spinning toy
*relative to each other*, and a model shown one sense at a time has no way to
see that. The prompt still allows repeated labels: two senses of "bank" can
both be very_common, which leaves them splitting the frequency evenly.

Compare ``wordfreq.translation.definitions``, which rates a sense
independently while discovering a word. That is the right question there (it
gates whether a sense is worth creating at all) and the wrong one here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from clients.types import Schema, SchemaProperty
from storage.models.schema import SENSE_PROMINENCE_VALUES, Lemma
from wordfreq.translation.definitions import SENSE_PROMINENCE_ORDER

logger = logging.getLogger(__name__)

# Ratings are asked for one shared spelling at a time, so a group is small (a
# heavily polysemous word has a handful of lemmas, not hundreds). No batching
# of groups into one call: the comparison is only meaningful within a group,
# and mixing groups invites the model to rate across them.
PROMPT_CONTEXT: str = "You are a lexicographer rating how common each sense of an English word is."


@dataclass(frozen=True)
class SenseToRate:
    """One lemma competing for a spelling."""

    lemma_id: int
    guid: Optional[str]
    pos_type: str
    definition_text: str
    # None when the sense has never been rated; readers treat that as "common".
    current_prominence: Optional[str]


@dataclass(frozen=True)
class ProminenceRating:
    """A model's verdict for one sense."""

    lemma_id: int
    prominence: str
    reasoning: str


@dataclass(frozen=True)
class GroupResult:
    """Outcome of rating one shared spelling."""

    lemma_text: str
    ratings: Tuple[ProminenceRating, ...]
    changed: Tuple[int, ...]
    error: Optional[str] = None


def find_duplicate_text_groups(
    session: Session,
    limit: Optional[int] = None,
    only_unrated: bool = False,
) -> List[Tuple[str, List[SenseToRate]]]:
    """Return every ``lemma_text`` held by two or more lemmas, with its senses.

    A single-sense lemma is skipped: its prominence label cannot change any
    frequency, since it takes the full token share regardless.

    Args:
        session: Database session.
        limit: Stop after this many groups. None for all of them.
        only_unrated: Skip groups where every lemma already carries a rating.
            A rating is a non-NULL ``sense_prominence``; NULL means nobody has
            judged the sense yet. Note this is not "differs from common" -- a
            group the model judged uniformly common is rated, and re-asking
            about it every run would repeat the spend forever.
    """
    duplicate_texts = (
        session.query(Lemma.lemma_text)
        .group_by(Lemma.lemma_text)
        .having(func.count(Lemma.id) > 1)
        .order_by(Lemma.lemma_text)
        .all()
    )

    groups: List[Tuple[str, List[SenseToRate]]] = []
    for (lemma_text,) in duplicate_texts:
        lemmas = (
            session.query(Lemma).filter(Lemma.lemma_text == lemma_text).order_by(Lemma.id).all()
        )
        senses = [
            SenseToRate(
                lemma_id=lemma.id,
                guid=lemma.guid,
                pos_type=lemma.pos_type,
                definition_text=lemma.definition_text,
                current_prominence=lemma.sense_prominence,
            )
            for lemma in lemmas
        ]
        if only_unrated and all(sense.current_prominence is not None for sense in senses):
            continue
        groups.append((lemma_text, senses))
        if limit is not None and len(groups) >= limit:
            break

    return groups


def _build_schema() -> Schema:
    return Schema(
        name="SenseProminenceRatings",
        description="How common each listed sense of one English spelling is",
        properties={
            "ratings": SchemaProperty(
                type="array",
                description="One entry per sense given, in the same order",
                array_items_schema=Schema(
                    name="SenseProminenceRating",
                    description="The rating for a single sense",
                    properties={
                        "sense_number": SchemaProperty(
                            "integer",
                            "The number of the sense being rated, as listed in the prompt",
                        ),
                        "sense_prominence": SchemaProperty(
                            "string",
                            "How often this sense is the one meant when the "
                            "written word appears in modern English text",
                            enum=list(SENSE_PROMINENCE_ORDER),
                        ),
                        "reasoning": SchemaProperty(
                            "string", "One short sentence justifying the rating"
                        ),
                    },
                ),
            )
        },
    )


def build_prompt(lemma_text: str, senses: Sequence[SenseToRate]) -> str:
    """Render the comparative rating question for one shared spelling."""
    lines = [
        f'The English word "{lemma_text}" is written the same way for several '
        f"different meanings. Rate how often each meaning is the one intended "
        f'when "{lemma_text}" appears in modern English text.',
        "",
        "Judge the meanings against each other: they are competing for the same "
        "spelling, and the ratings decide how that word's corpus frequency is "
        "divided between them. Rate what the written word usually means, not "
        "how useful or interesting the meaning is.",
        "",
        "You may give the same rating to more than one meaning when they really "
        "are comparable. Use 'rare' for a meaning that is genuinely unusual in "
        "everyday text, even if it is familiar to a child or a specialist.",
        "",
        "The meanings:",
    ]
    for index, sense in enumerate(senses, start=1):
        lines.append(f"{index}. ({sense.pos_type}) {sense.definition_text}")
    return "\n".join(lines)


def rate_group(
    client: Any,
    lemma_text: str,
    senses: Sequence[SenseToRate],
    model: Optional[str] = None,
) -> Tuple[List[ProminenceRating], Optional[str]]:
    """Ask the model to rate one group. Returns (ratings, error).

    Ratings are matched back to lemmas by the 1-based ``sense_number`` the
    prompt listed, not by array position: a model that drops or reorders an
    entry would otherwise silently misassign every rating after it. An entry
    with an out-of-range number or an unrecognized label is discarded.
    """
    model_name: str = model or getattr(client, "model", None) or "gpt-5.4-mini"
    prompt = build_prompt(lemma_text, senses)

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model_name,
            json_schema=_build_schema(),
            context=PROMPT_CONTEXT,
        )
    except Exception as exc:  # noqa: BLE001 - reported per group, run continues
        logger.error("Rating '%s' failed: %s: %s", lemma_text, type(exc).__name__, exc)
        return [], f"{type(exc).__name__}: {exc}"

    data = response.structured_data
    if not isinstance(data, dict) or not isinstance(data.get("ratings"), list):
        logger.warning("Malformed rating response for '%s'", lemma_text)
        return [], "malformed response"

    ratings: List[ProminenceRating] = []
    seen: set[int] = set()
    for entry in data["ratings"]:
        if not isinstance(entry, dict):
            continue
        raw_number = entry.get("sense_number")
        if raw_number is None:
            continue
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            continue
        if not 1 <= number <= len(senses) or number in seen:
            logger.warning(
                "Rating for '%s' referenced sense %s, which was not asked about",
                lemma_text,
                number,
            )
            continue
        prominence = entry.get("sense_prominence")
        if prominence not in SENSE_PROMINENCE_VALUES:
            logger.warning(
                "Rating for '%s' sense %s had unknown prominence %r",
                lemma_text,
                number,
                prominence,
            )
            continue
        seen.add(number)
        ratings.append(
            ProminenceRating(
                lemma_id=senses[number - 1].lemma_id,
                prominence=prominence,
                reasoning=str(entry.get("reasoning") or ""),
            )
        )

    if len(ratings) != len(senses):
        logger.warning("Rated %d of %d senses for '%s'", len(ratings), len(senses), lemma_text)

    return ratings, None


def apply_ratings(
    session: Session,
    ratings: Sequence[ProminenceRating],
) -> List[int]:
    """Write ratings onto their lemmas. Returns the ids that actually changed.

    Does not commit; the caller owns the transaction so a dry run can roll the
    whole thing back.
    """
    changed: List[int] = []
    for rating in ratings:
        lemma = session.get(Lemma, rating.lemma_id)
        if lemma is None:
            logger.warning("Lemma %s vanished before its rating was applied", rating.lemma_id)
            continue
        # A NULL lemma rated "common" is a real change: it is how the rating
        # gets recorded, and what stops --only-unrated asking again.
        if lemma.sense_prominence == rating.prominence:
            continue
        lemma.sense_prominence = rating.prominence
        changed.append(rating.lemma_id)
    return changed
