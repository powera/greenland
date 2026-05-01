#!/usr/bin/python3

"""Functions for importing corpus frequency data."""

import csv
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import constants
import wordfreq.frequency.corpus
from storage import database
from storage.backend.config import DataSourceConfig
from storage.connection_pool import get_session
from storage.models.schema import (
    Corpus,
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    Lemma,
    WordFrequency,
    WordToken,
)
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions, rank_to_wordfreq_tier_name
from wordfreq.translation.client import LinguisticClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Regular expression to detect words containing numerals
CONTAINS_NUMERAL_PATTERN = re.compile(r"[0-9]")


def import_frequency_data(
    file_path: str,
    corpus_name: str,
    language_code: str = "en",  # Language code for the words being imported (e.g., "en", "lt", "zh", "fr")
    file_type: str = "json",
    max_words: int = 5000,
    value_type: str = "auto",  # Parameter to specify what the numeric values represent: "rank", "frequency", or "auto"
    corpus_description: Optional[str] = None,  # Optional description for new corpus
    config: Optional[
        "DataSourceConfig"
    ] = None,  # DataSourceConfig with backend settings (uses default if None)
) -> Tuple[int, int]:
    """
    Import word frequency data from a file into the database.

    Args:
        file_path: Path to the frequency data file
        corpus_name: Name of the corpus (gutenberg, books_20th, subtitles, wiki_vital)
        language_code: Language code for the words being imported (e.g., "en", "lt", "zh", "fr")
        file_type: File type (json, subtlex)
        max_words: Maximum number of words to import
        value_type: How to interpret numeric values in simple word->number mappings:
                   - "rank": Values are treated as ranks (lower is more frequent)
                   - "frequency": Values are treated as frequencies (higher is more frequent)
                   - "auto": Auto-detect based on data characteristics
        corpus_description: Optional description for the corpus if it needs to be created
        config: DataSourceConfig with backend settings (uses default if None)

    Returns:
        Tuple of (words imported, total words)
    """
    from storage.backend import create_session
    from storage.backend.config import DataSourceConfig

    logger.info(
        f"Importing frequency data from {file_path} for corpus '{corpus_name}' (language: {language_code})"
    )

    # Get session using DataSourceConfig
    if config is None:
        config = DataSourceConfig()
    session = create_session(config)

    # Sync corpus configurations from config file to database
    sync_result = wordfreq.frequency.corpus.sync_corpus_configs_to_db(session)
    if not sync_result["success"]:
        logger.warning(f"Failed to sync corpus configs: {sync_result['errors']}")

    # Get corpus from database
    corpus = session.query(Corpus).filter(Corpus.name == corpus_name).first()

    if not corpus:
        # If corpus doesn't exist and isn't in config, create it with provided description
        logger.info(f"Corpus '{corpus_name}' not found in config or database, creating it...")
        description = corpus_description or f"Corpus: {corpus_name}"
        corpus = Corpus(
            name=corpus_name,
            description=description,
            unknown_rank_weight=1.0,  # Default weight
            enabled=True,
        )
        session.add(corpus)
        session.commit()
        logger.info(f"Created new corpus '{corpus_name}' with description: {description}")
    elif not corpus.enabled:
        logger.warning(f"Corpus '{corpus_name}' is disabled in configuration")

    # Process the file based on type
    raw_words_data = {}

    try:
        if file_type.lower() == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Handle different JSON formats
                if isinstance(data, dict) and "global_word_frequency" in data:
                    # Known format with explicit frequency data
                    raw_words_data = data["global_word_frequency"]
                    # Mark that these are frequencies
                    detected_type = "frequency"
                elif isinstance(data, dict):
                    # Generic dictionary mapping
                    raw_words_data = data
                    # Will need to analyze
                    detected_type = "unknown"
                elif isinstance(data, list):
                    # Convert list to rank dictionary (1-indexed)
                    raw_words_data = {word: i + 1 for i, word in enumerate(data)}
                    # Mark that these are ranks
                    detected_type = "rank"
                else:
                    logger.error(f"Unrecognized JSON format in {file_path}")
                    return (0, 0)
        elif file_type.lower() == "subtlex":
            # Handle SUBTLEX format
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter="\t")
                header = next(reader)
                row_count = 0
                for row in reader:
                    if len(row) < 2:
                        continue
                    word = row[0]
                    row_count += 1
                    raw_words_data[word] = row_count
                detected_type = "rank"
        else:
            logger.error(f"Unsupported file type: {file_type}")
            return (0, 0)

        # If value_type is "auto", try to determine whether values represent ranks or frequencies
        if value_type == "auto" and detected_type == "unknown":
            # Sample data to see if values look like ranks or frequencies
            sample_values = list(raw_words_data.values())[:100]  # Take first 100 values

            # Heuristics:
            # 1. Ranks are typically integers
            # 2. Frequencies are typically small decimal values < 1.0
            # 3. Frequencies typically sum to a value close to 1.0 for normalized data
            # 4. Ranks typically start from 1 and increment

            has_decimals = any(isinstance(v, float) and v != int(v) for v in sample_values)
            has_small_values = any(0 < v < 0.1 for v in sample_values)
            sum_near_one = 0.8 < sum(sample_values) < 1.2
            sequential_integers = all(isinstance(v, int) or v == int(v) for v in sample_values)

            if has_decimals and has_small_values and sum_near_one:
                logger.info("Auto-detected value type: frequency")
                value_type = "frequency"
            elif sequential_integers:
                logger.info("Auto-detected value type: rank")
                value_type = "rank"
            else:
                logger.info("Could not auto-detect value type, defaulting to 'rank'")
                value_type = "rank"
        elif value_type == "auto" and detected_type != "unknown":
            # Use the detected type
            value_type = detected_type
            logger.info(f"Using detected value type: {value_type}")

        # Process words: lowercase, filter out numerals, and merge duplicate entries
        words_data: Dict[str, Dict[str, Optional[Union[int, float]]]] = {}
        skipped_numeral_count = 0
        merged_count = 0

        for word_text, data in raw_words_data.items():
            # Convert to lowercase
            word_text_lower = word_text.lower()

            # Skip words containing numerals
            if CONTAINS_NUMERAL_PATTERN.search(word_text_lower):
                skipped_numeral_count += 1
                continue

            # Determine rank and frequency for this entry
            rank = None
            frequency = None

            if isinstance(data, dict) and "rank" in data:
                # Explicit rank and possibly frequency in dictionary
                rank = data["rank"]
                frequency = data.get("frequency")
            elif isinstance(data, (int, float)):
                # If data is just a number, interpret based on value_type
                if value_type == "rank":
                    rank = int(data) if isinstance(data, int) else int(data + 0.5)  # Round floats
                    frequency = None
                else:  # value_type == "frequency"
                    frequency = float(data)
                    rank = None

            # If the lowercase word already exists in our processed data
            if word_text_lower in words_data:
                merged_count += 1
                existing_data = words_data[word_text_lower]

                # For ranks, keep the higher rank (lower number)
                if value_type == "rank" and rank is not None:
                    if existing_data.get("rank") is None or rank < existing_data["rank"]:
                        existing_data["rank"] = rank

                # For frequencies, keep the higher frequency
                if value_type == "frequency" and frequency is not None:
                    if (
                        existing_data.get("frequency") is None
                        or frequency > existing_data["frequency"]
                    ):
                        existing_data["frequency"] = frequency
            else:
                # Add new entry
                words_data[word_text_lower] = {"rank": rank, "frequency": frequency}

        logger.info(f"Processed word data: {len(words_data)} unique lowercase words")
        logger.info(f"Filtered out {skipped_numeral_count} words containing numerals")
        logger.info(f"Merged {merged_count} duplicate words with different capitalization")

        # Apply max_words limit before import
        words_to_import = list(words_data.items())[:max_words]
        total_count = len(words_to_import)
        logger.info(f"Will import {total_count} words (max_words={max_words})")

        # BATCH OPTIMIZATION: Fetch or create word tokens in bulk
        word_texts = [w[0] for w in words_to_import]

        # Batch fetch existing tokens
        logger.info(f"Batch fetching existing word tokens...")
        existing_tokens = (
            session.query(WordToken)
            .filter(WordToken.token.in_(word_texts), WordToken.language_code == language_code)
            .all()
        )
        token_map = {t.token: t for t in existing_tokens}
        logger.info(f"Found {len(token_map)} existing word tokens")

        # Identify and batch create new tokens
        new_token_texts = [t for t in word_texts if t not in token_map]
        if new_token_texts:
            logger.info(f"Creating {len(new_token_texts)} new word tokens in batch...")
            new_tokens = [WordToken(token=t, language_code=language_code) for t in new_token_texts]
            session.bulk_save_objects(new_tokens, return_defaults=True)
            session.commit()

            # Re-fetch the newly created tokens to get their IDs
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
            logger.info(f"Created {len(newly_created)} new word tokens")

        # BATCH OPTIMIZATION: Fetch existing frequency records for this corpus
        token_ids = [token_map[w[0]].id for w in words_to_import if w[0] in token_map]
        logger.info(f"Batch fetching existing frequency records...")
        existing_freqs = (
            session.query(WordFrequency)
            .filter(
                WordFrequency.word_token_id.in_(token_ids),
                WordFrequency.corpus_id == corpus.id,
            )
            .all()
        )
        freq_map = {f.word_token_id: f for f in existing_freqs}
        logger.info(f"Found {len(freq_map)} existing frequency records")

        # Process words: update existing or prepare new frequency records
        new_freq_records = []
        update_count = 0
        imported_count = 0

        for word_text, data in words_to_import:
            word_obj = token_map.get(word_text)
            if not word_obj:
                logger.warning(f"Token not found after batch create: {word_text}")
                continue

            rank_value = data.get("rank")
            frequency_value = data.get("frequency")
            resolved_rank: Optional[int] = int(rank_value) if rank_value is not None else None
            resolved_frequency: Optional[float] = (
                float(frequency_value) if frequency_value is not None else None
            )

            existing_freq = freq_map.get(word_obj.id)
            if existing_freq:
                # Update existing record
                if resolved_rank is not None:
                    existing_freq.rank = resolved_rank
                if resolved_frequency is not None:
                    existing_freq.frequency = resolved_frequency
                update_count += 1
            else:
                # Prepare new frequency record for bulk insert
                new_freq_records.append(
                    WordFrequency(
                        word_token_id=word_obj.id,
                        corpus_id=corpus.id,
                        rank=resolved_rank,
                        frequency=resolved_frequency,
                    )
                )

            imported_count += 1

            # Log progress
            if imported_count % 1000 == 0:
                logger.info(f"Processed {imported_count}/{total_count} words")

        # Batch insert new frequency records
        if new_freq_records:
            logger.info(f"Batch inserting {len(new_freq_records)} new frequency records...")
            session.bulk_save_objects(new_freq_records)

        # Commit all changes
        session.commit()
        logger.info(
            f"Batch import complete: {update_count} updated, {len(new_freq_records)} created"
        )

        # If we only have frequencies but no ranks, calculate ranks now
        if value_type == "frequency":
            logger.info("Calculating ranks from frequencies...")

            # Get all frequency records for this corpus ordered by frequency (descending)
            freq_records = (
                session.query(WordFrequency)
                .filter(WordFrequency.corpus_id == corpus.id, WordFrequency.frequency != None)
                .order_by(WordFrequency.frequency.desc())
                .all()
            )

            # Update ranks
            for i, record in enumerate(freq_records):
                record.rank = i + 1  # 1-indexed

                # Commit in batches
                if (i + 1) % 500 == 0:
                    session.commit()
                    logger.info(f"Updated ranks for {i+1}/{len(freq_records)} words")

            # Final commit for ranks
            session.commit()
            logger.info(f"Finished calculating ranks for {len(freq_records)} words")

        # Final commit
        session.commit()
        logger.info(
            f"Successfully imported {imported_count}/{total_count} words for corpus '{corpus_name}'"
        )
        return (imported_count, total_count)
    except Exception as e:
        logger.error(f"Error importing frequency data: {e}")
        session.rollback()
        raise


def _parse_frequency_file(
    file_path: str,
    file_type: str,
    value_type: str,
) -> Dict[str, Dict[str, Optional[Union[int, float]]]]:
    """Parse a corpus frequency file into ``{lowercase_word: {"rank", "frequency"}}``.

    Mirrors the parsing/normalization logic of ``import_frequency_data`` without
    touching the database.
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
        word_text_lower = word_text.lower()
        if CONTAINS_NUMERAL_PATTERN.search(word_text_lower):
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

        if word_text_lower in words_data:
            merged_count += 1
            existing = words_data[word_text_lower]
            if resolved_value_type == "rank" and rank is not None:
                existing_rank = existing.get("rank")
                if existing_rank is None or rank < existing_rank:  # type: ignore[operator]
                    existing["rank"] = rank
            if resolved_value_type == "frequency" and frequency is not None:
                existing_freq = existing.get("frequency")
                if existing_freq is None or frequency > existing_freq:  # type: ignore[operator]
                    existing["frequency"] = frequency
        else:
            words_data[word_text_lower] = {"rank": rank, "frequency": frequency}

    logger.info(
        f"Parsed {len(words_data)} unique words from {file_path} "
        f"(skipped {skipped_numeral_count} with numerals, merged {merged_count} duplicates, "
        f"value_type={resolved_value_type})"
    )
    return words_data


def _link_wordfreq_annotations_to_lemmas(
    session: Any,
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
    file_path: str,
    corpus_name: str,
    language_code: str = "en",
    file_type: str = "json",
    max_words: int = 5000,
    value_type: str = "auto",
    config: Optional["DataSourceConfig"] = None,
) -> Tuple[int, int]:
    """Import corpus frequency data directly into external_lexeme_annotations.

    Writes one row per surface form under source ``wordfreq_<corpus_name>`` with:
    - tier_name: rank bucket (very_common/common/rare)
    - ordinal_rank: integer rank within the corpus (1 = most frequent)
    - frequency: raw frequency, when present in source data
    - notes: JSON payload with corpus name (for provenance)

    Does not touch the legacy ``word_frequencies`` table.
    """
    if config is None:
        config = DataSourceConfig()

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

    session = get_session(config)
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
    finally:
        session.close()


# NOTE: The import_all_corpus_data function has been moved to corpus.py as load_all_corpora()
# This provides better organization by keeping corpus configuration and loading logic together.
# Use wordfreq.frequency.corpus.load_all_corpora() instead.


def process_stopwords(refresh: bool = False, model: Optional[str] = None) -> Dict[str, bool]:
    """
    Process all stop words from util.stopwords using linguistic_client.process_word.

    Args:
        refresh: If True, delete existing definitions and re-process all stop words
        model: Model name to use for processing (defaults to the default model in linguistic_client)

    Returns:
        Dictionary mapping words to success flags
    """
    from util.stopwords import (
        COMMON_ADVERBS,
        COMMON_NOUNS,
        COMMON_VERBS,
        CONTRACTIONS,
        MISC_WORDS,
        all_stopwords,
        stopwords,
    )

    logger.info(f"Processing stop words (refresh={refresh})")

    # Initialize the linguistic client
    client = (
        LinguisticClient.get_instance(model=model) if model else LinguisticClient.get_instance()
    )

    # Collect all words to process
    all_words = set(all_stopwords)  # Start with the basic stopwords

    # Add other word categories
    all_words.update(CONTRACTIONS)
    all_words.update(COMMON_VERBS)
    all_words.update(COMMON_NOUNS)
    all_words.update(COMMON_ADVERBS)
    all_words.update(MISC_WORDS)

    # Sort for consistent processing order
    words_to_process = sorted(list(all_words))

    logger.info(f"Found {len(words_to_process)} unique stop words to process")

    # Process each word
    results = {}
    success_count = 0
    failure_count = 0

    for i, word in enumerate(words_to_process):
        logger.info(f"Processing word {i+1}/{len(words_to_process)}: '{word}'")

        try:
            # Process the word
            success = client.process_word(word, refresh=refresh)
            results[word] = success

            if success:
                success_count += 1
                logger.info(f"Successfully processed '{word}'")
            else:
                failure_count += 1
                logger.warning(f"Failed to process '{word}'")

            # Add a small delay to avoid overwhelming the API
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error processing word '{word}': {e}")
            results[word] = False
            failure_count += 1

        # Log progress every 10 words
        if (i + 1) % 10 == 0:
            logger.info(f"Progress: {i+1}/{len(words_to_process)} words processed")

    # Log summary
    logger.info("Stop words processing summary:")
    logger.info(f"Total words: {len(words_to_process)}")
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Failed to process: {failure_count}")

    return results
