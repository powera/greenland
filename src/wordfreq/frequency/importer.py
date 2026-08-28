#!/usr/bin/python3

"""Functions for importing corpus frequency data."""

import json
import logging
import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from sqlalchemy.orm import Session

from storage.models.schema import (
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    Lemma,
    WordToken,
)
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions, rank_to_wordfreq_tier_name

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Regular expression to detect words containing numerals
CONTAINS_NUMERAL_PATTERN = re.compile(r"[0-9]")


def _parse_frequency_file(
    file_path: str,
    file_type: str,
    value_type: str,
) -> Dict[str, Dict[str, Optional[Union[int, float]]]]:
    """Parse a corpus frequency file into ``{word: {"rank", "frequency"}}``.

    Keys keep the corpus file's own spelling, case included, so "March" and
    "march" stay distinct entries and get a ``WordToken`` each.

    Pure parsing/normalization — no database access.
    """
    raw_words_data: Dict[str, Any] = {}
    detected_type: str = "unknown"

    if file_type.lower() == "json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "global_word_frequency" in data:
            raw_words_data = data["global_word_frequency"]
            detected_type = "frequency"
        elif isinstance(data, dict):
            raw_words_data = data
            detected_type = "unknown"
        elif isinstance(data, list):
            raw_words_data = {word: i + 1 for i, word in enumerate(data)}
            detected_type = "rank"
        else:
            raise ValueError(f"Unrecognized JSON format in {file_path}")
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    resolved_value_type = value_type
    if resolved_value_type == "auto" and detected_type == "unknown":
        sample_values = list(raw_words_data.values())[:100]
        has_decimals = any(isinstance(v, float) and v != int(v) for v in sample_values)
        has_small_values = any(isinstance(v, (int, float)) and 0 < v < 0.1 for v in sample_values)
        sum_near_one = 0.8 < sum(v for v in sample_values if isinstance(v, (int, float))) < 1.2
        sequential_integers = all(
            isinstance(v, int) or (isinstance(v, float) and v == int(v)) for v in sample_values
        )
        if has_decimals and has_small_values and sum_near_one:
            resolved_value_type = "frequency"
        elif sequential_integers:
            resolved_value_type = "rank"
        else:
            resolved_value_type = "rank"
    elif resolved_value_type == "auto":
        resolved_value_type = detected_type

    words_data: Dict[str, Dict[str, Optional[Union[int, float]]]] = {}
    skipped_numeral_count = 0
    merged_count = 0

    for word_text, entry in raw_words_data.items():
        # Case is preserved: a corpus counts "March" the month apart from
        # "march" the verb, and each needs its own WordToken for a lemma
        # spelled that way to link to. Folding them here would put the verb's
        # frequency on the month.
        if CONTAINS_NUMERAL_PATTERN.search(word_text):
            skipped_numeral_count += 1
            continue

        rank: Optional[int] = None
        frequency: Optional[float] = None
        if isinstance(entry, dict) and "rank" in entry:
            rank = entry["rank"]
            freq_raw = entry.get("frequency")
            frequency = float(freq_raw) if freq_raw is not None else None
        elif isinstance(entry, (int, float)):
            if resolved_value_type == "rank":
                rank = int(entry) if isinstance(entry, int) else int(entry + 0.5)
            else:
                frequency = float(entry)

        if word_text in words_data:
            merged_count += 1
            existing = words_data[word_text]
            if resolved_value_type == "rank" and rank is not None:
                existing_rank = existing.get("rank")
                if existing_rank is None or rank < existing_rank:  # type: ignore[operator]
                    existing["rank"] = rank
            if resolved_value_type == "frequency" and frequency is not None:
                existing_freq = existing.get("frequency")
                if existing_freq is None or frequency > existing_freq:  # type: ignore[operator]
                    existing["frequency"] = frequency
        else:
            words_data[word_text] = {"rank": rank, "frequency": frequency}

    logger.info(
        f"Parsed {len(words_data)} unique words from {file_path} "
        f"(skipped {skipped_numeral_count} with numerals, merged {merged_count} duplicates, "
        f"value_type={resolved_value_type})"
    )
    return words_data


def _link_wordfreq_annotations_to_lemmas(
    session: Session,
    source_name: str,
    language_code: str,
    tokens: List[WordToken],
) -> int:
    """Ensure ExternalLexemeAnnotationLemma rows exist for every (annotation, lemma)
    where ``lemma.lemma_text == word_token.token``.

    Wordfreq is token-level: it cannot disambiguate homographs (``bank`` river vs
    finance), so each annotation links to *every* lemma whose surface form matches
    the token. Consumers rely on the tier_name/ordinal_rank to estimate commonness
    rather than picking a specific sense.
    """
    if not tokens:
        return 0

    token_ids = [t.id for t in tokens]
    annotations = (
        session.query(ExternalLexemeAnnotation)
        .filter(
            ExternalLexemeAnnotation.source == source_name,
            ExternalLexemeAnnotation.word_token_id.in_(token_ids),
        )
        .all()
    )
    if not annotations:
        return 0

    token_text_by_id = {t.id: t.token for t in tokens}
    surface_forms = sorted({token_text_by_id[a.word_token_id] for a in annotations})

    matching_lemmas = session.query(Lemma).filter(Lemma.lemma_text.in_(surface_forms)).all()
    lemmas_by_text: Dict[str, List[int]] = {}
    for lemma in matching_lemmas:
        lemmas_by_text.setdefault(lemma.lemma_text, []).append(lemma.id)

    annotation_ids = [a.id for a in annotations]
    existing_links = (
        session.query(ExternalLexemeAnnotationLemma)
        .filter(ExternalLexemeAnnotationLemma.annotation_id.in_(annotation_ids))
        .all()
    )
    existing_pairs = {(link.annotation_id, link.lemma_id) for link in existing_links}

    new_links: List[ExternalLexemeAnnotationLemma] = []
    for annotation in annotations:
        surface = token_text_by_id.get(annotation.word_token_id)
        if surface is None:
            continue
        for lemma_id in lemmas_by_text.get(surface, ()):
            if (annotation.id, lemma_id) in existing_pairs:
                continue
            new_links.append(
                ExternalLexemeAnnotationLemma(
                    annotation_id=annotation.id,
                    lemma_id=lemma_id,
                )
            )

    if new_links:
        session.bulk_save_objects(new_links)
        session.commit()
    return len(new_links)


def import_frequency_as_annotations(
    session: Session,
    *,
    file_path: str,
    corpus_name: str,
    language_code: str = "en",
    file_type: str = "json",
    max_words: int = 5000,
    value_type: str = "auto",
) -> Tuple[int, int]:
    """Import corpus frequency data directly into external_lexeme_annotations.

    The caller owns the session lifecycle (open and close); this function
    commits its own writes mid-stream so partial progress is durable on a
    long load. Rolls back and re-raises on failure.

    Writes one row per surface form under source ``wordfreq_<corpus_name>`` with:
    - tier_name: rank bucket (very_common/common/rare)
    - ordinal_rank: integer rank within the corpus (1 = most frequent)
    - frequency: raw frequency, when present in source data
    - notes: JSON payload with corpus name (for provenance)
    """
    logger.info(
        f"Importing {corpus_name} from {file_path} into external_lexeme_annotations "
        f"(language={language_code})"
    )

    words_data = _parse_frequency_file(file_path, file_type, value_type)

    # Normalize raw counts to per-million (parts-per-million of the full corpus).
    # We use the *full* corpus total before truncation so values are comparable
    # across corpora and don't inflate when the top N is small.
    corpus_total = 0.0
    for d in words_data.values():
        freq_raw = d.get("frequency")
        if freq_raw is not None:
            corpus_total += float(freq_raw)
    if corpus_total > 0:
        scale = 1_000_000.0 / float(corpus_total)
        for entry in words_data.values():
            raw_freq = entry.get("frequency")
            if raw_freq is not None:
                entry["frequency"] = float(raw_freq) * scale
        logger.info(f"Normalized frequencies to per-million (corpus_total={corpus_total:.0f})")

    # If we only have frequencies (no ranks), assign ordinal ranks by descending frequency.
    items_with_freq_no_rank = [
        (w, d)
        for w, d in words_data.items()
        if d.get("rank") is None and d.get("frequency") is not None
    ]
    if items_with_freq_no_rank and not any(d.get("rank") is not None for d in words_data.values()):
        items_with_freq_no_rank.sort(key=lambda kv: kv[1]["frequency"], reverse=True)  # type: ignore[arg-type,return-value]
        for idx, (word_key, _) in enumerate(items_with_freq_no_rank, start=1):
            words_data[word_key]["rank"] = idx

    # Order words by rank for stable max_words truncation; words without rank go last.
    ordered = sorted(
        words_data.items(),
        key=lambda kv: (kv[1].get("rank") if kv[1].get("rank") is not None else 10**9, kv[0]),
    )
    words_to_import = ordered[:max_words]
    total_count = len(words_to_import)
    if total_count == 0:
        return (0, 0)

    source_name = f"wordfreq_{corpus_name}"
    notes_payload = json.dumps({"corpus": corpus_name})

    try:
        bootstrap_tier_definitions(session, sources=[source_name])

        word_texts = [w[0] for w in words_to_import]

        existing_tokens = (
            session.query(WordToken)
            .filter(WordToken.token.in_(word_texts), WordToken.language_code == language_code)
            .all()
        )
        token_map: Dict[str, WordToken] = {t.token: t for t in existing_tokens}

        new_token_texts = [t for t in word_texts if t not in token_map]
        if new_token_texts:
            new_tokens = [WordToken(token=t, language_code=language_code) for t in new_token_texts]
            session.bulk_save_objects(new_tokens, return_defaults=True)
            session.commit()
            newly_created = (
                session.query(WordToken)
                .filter(
                    WordToken.token.in_(new_token_texts),
                    WordToken.language_code == language_code,
                )
                .all()
            )
            for t in newly_created:
                token_map[t.token] = t

        token_ids = [token_map[w].id for w, _ in words_to_import if w in token_map]
        existing_annotations = (
            session.query(ExternalLexemeAnnotation)
            .filter(
                ExternalLexemeAnnotation.word_token_id.in_(token_ids),
                ExternalLexemeAnnotation.source == source_name,
                ExternalLexemeAnnotation.pos_hint.is_(None),
                ExternalLexemeAnnotation.sense_hint.is_(None),
            )
            .all()
        )
        annotation_map: Dict[int, ExternalLexemeAnnotation] = {
            a.word_token_id: a for a in existing_annotations
        }

        new_rows: List[ExternalLexemeAnnotation] = []
        update_count = 0

        for word_text, data in words_to_import:
            token = token_map.get(word_text)
            if token is None:
                logger.warning(f"Token missing after batch create: {word_text}")
                continue
            rank_value = data.get("rank")
            freq_value = data.get("frequency")
            ordinal_rank: Optional[int] = int(rank_value) if rank_value is not None else None
            frequency_val: Optional[float] = float(freq_value) if freq_value is not None else None
            tier_name = rank_to_wordfreq_tier_name(ordinal_rank)

            existing = annotation_map.get(token.id)
            if existing is None:
                new_rows.append(
                    ExternalLexemeAnnotation(
                        word_token_id=token.id,
                        source=source_name,
                        tier_name=tier_name,
                        ordinal_rank=ordinal_rank,
                        frequency=frequency_val,
                        notes=notes_payload,
                    )
                )
            else:
                existing.tier_name = tier_name
                existing.ordinal_rank = ordinal_rank
                existing.frequency = frequency_val
                existing.notes = notes_payload
                update_count += 1

        if new_rows:
            session.bulk_save_objects(new_rows)
        session.commit()

        links_inserted = _link_wordfreq_annotations_to_lemmas(
            session=session,
            source_name=source_name,
            language_code=language_code,
            tokens=list(token_map.values()),
        )

        logger.info(
            f"Annotation import complete for {corpus_name}: "
            f"{len(new_rows)} created, {update_count} updated, "
            f"{links_inserted} lemma links inserted"
        )
        return (len(new_rows) + update_count, total_count)
    except Exception as e:
        logger.error(f"Error importing annotations for {corpus_name}: {e}")
        session.rollback()
        raise


# NOTE: The import_all_corpus_data function has been moved to corpus.py as load_all_corpora()
# This provides better organization by keeping corpus configuration and loading logic together.
# Use wordfreq.frequency.corpus.load_all_corpora() instead.
