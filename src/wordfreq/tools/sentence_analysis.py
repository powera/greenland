"""Sentence analysis utilities for finding lemma associations."""

from typing import List

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import (
    DerivativeForm,
    Lemma,
    SentencePatternWord,
    SentenceWord,
)

# Languages that use logographic scripts where substring matching is appropriate
SUBSTRING_MATCH_LANGUAGES = {"zh", "ja", "ko"}


def _forms_match(sentence_form: str, derivative_form: str, language_code: str) -> bool:
    """Check if a sentence form matches a derivative form.

    For most languages: case-insensitive exact match.
    For Chinese/Japanese/Korean: also match if one contains the other.
    """
    sentence_lower = sentence_form.lower()
    derivative_lower = derivative_form.lower()

    # Exact match (case-insensitive)
    if sentence_lower == derivative_lower:
        return True

    # For logographic languages, also check substring containment
    if language_code in SUBSTRING_MATCH_LANGUAGES:
        if sentence_form in derivative_form or derivative_form in sentence_form:
            return True

    return False


def find_candidate_lemmas_for_sentence(
    session: Session, sentence_id: int, min_language_matches: int = 2
) -> List[dict]:
    """Find lemmas that match words in a sentence across multiple languages.

    For each word position/role in the sentence, searches derivative_forms
    to find lemmas whose forms match the declined_form in the sentence.
    Returns lemmas that match in at least min_language_matches languages.

    Matching rules:
    - Case-insensitive for all languages
    - For Chinese/Japanese/Korean: substring containment also counts as a match

    Args:
        session: Database session
        sentence_id: ID of the sentence to analyze
        min_language_matches: Minimum number of languages that must match (default 3)

    Returns:
        List of dicts with keys:
            - lemma: Lemma object
            - english_text: The English word from sentence_words
            - matched_languages: List of language codes that matched
            - word_role: The role of the word in the sentence
    """
    # Get all sentence words for this sentence
    sentence_words = (
        session.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence_id)
        .order_by(SentenceWord.position)
        .all()
    )

    # Group words by english_text to identify word "slots"
    word_slots: dict = {}
    for sw in sentence_words:
        if sw.english_text:
            key = sw.english_text.lower()
            if key not in word_slots:
                word_slots[key] = {
                    "english_text": sw.english_text,
                    "word_role": sw.word_role,
                    "forms_by_lang": {},
                    "has_lemma": False,
                }
            # Store the declined form for this language
            word_slots[key]["forms_by_lang"][sw.language_code] = sw.declined_form
            # Track if any language already has a lemma assigned
            if sw.lemma_id:
                word_slots[key]["has_lemma"] = True

    # Aggregate lemma matches across all slots
    # lemma_id -> {"langs": set of lang codes, "english_texts": set, "word_roles": set}
    global_lemma_matches: dict = {}

    for slot_key, slot_data in word_slots.items():
        # Skip slots that already have a lemma assigned
        if slot_data["has_lemma"]:
            continue

        # Collect all declined forms for this slot
        forms_by_lang = slot_data["forms_by_lang"]

        for lang_code, declined_form in forms_by_lang.items():
            if not declined_form:
                continue

            # For logographic languages, use SQL substring matching
            # For others, use case-insensitive exact match
            if lang_code in SUBSTRING_MATCH_LANGUAGES:
                # Use LIKE-based contains() for DB-portable substring matching
                # This works on both SQLite and Postgres
                matching_forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.language_code == lang_code,
                        or_(
                            # Exact match
                            DerivativeForm.derivative_form_text == declined_form,
                            # Derivative form contains the declined form
                            DerivativeForm.derivative_form_text.contains(declined_form),
                            # Declined form contains the derivative form
                            literal(declined_form).contains(DerivativeForm.derivative_form_text),
                        ),
                    )
                    .all()
                )
            else:
                # Case-insensitive exact match using SQL LOWER()
                matching_forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.language_code == lang_code,
                        func.lower(DerivativeForm.derivative_form_text) == declined_form.lower(),
                    )
                    .all()
                )

            for df in matching_forms:
                if df.lemma_id not in global_lemma_matches:
                    global_lemma_matches[df.lemma_id] = {
                        "langs": set(),
                        "english_texts": set(),
                        "word_roles": set(),
                    }
                global_lemma_matches[df.lemma_id]["langs"].add(lang_code)
                global_lemma_matches[df.lemma_id]["english_texts"].add(slot_data["english_text"])
                global_lemma_matches[df.lemma_id]["word_roles"].add(slot_data["word_role"])

    # Filter to lemmas that match in at least min_language_matches languages
    qualifying_lemma_ids = [
        lemma_id
        for lemma_id, match_data in global_lemma_matches.items()
        if len(match_data["langs"]) >= min_language_matches
    ]

    # Batch load all qualifying lemmas in one query
    lemmas_by_id = {}
    if qualifying_lemma_ids:
        lemmas = session.query(Lemma).filter(Lemma.id.in_(qualifying_lemma_ids)).all()
        lemmas_by_id = {lemma.id: lemma for lemma in lemmas}

    # Build results
    results = []
    for lemma_id in qualifying_lemma_ids:
        lemma = lemmas_by_id.get(lemma_id)
        if lemma:
            match_data = global_lemma_matches[lemma_id]
            results.append(
                {
                    "lemma": lemma,
                    "english_text": ", ".join(sorted(match_data["english_texts"])),
                    "matched_languages": sorted(match_data["langs"]),
                    "word_role": ", ".join(sorted(match_data["word_roles"])),
                }
            )

    return results


def store_discovered_lemmas(
    session: Session, sentence_id: int, candidates: List[dict], commit: bool = True
) -> int:
    """Store discovered lemmas in sentence_pattern_words table.

    Adds entries with slot_name="discovered" for lemmas found via
    find_candidate_lemmas_for_sentence(). Skips lemmas that are already
    associated with the sentence.

    TODO: Rename sentence_pattern_words to sentence_lemmas - position/slot
    are not always meaningful (e.g., for discovered lemmas or lemmas that
    appear in different positions across languages like "to like" vs
    "to be pleasing to").

    Args:
        session: Database session
        sentence_id: ID of the sentence
        candidates: List of candidate dicts from find_candidate_lemmas_for_sentence()
        commit: Whether to commit the transaction (default True)

    Returns:
        Number of lemmas added
    """
    # Get existing lemma associations for this sentence
    existing_lemma_ids = {
        row[0]
        for row in session.query(SentencePatternWord.lemma_id)
        .filter(SentencePatternWord.sentence_id == sentence_id)
        .all()
    }

    # Find the next available position for this sentence
    max_position = (
        session.query(func.max(SentencePatternWord.position))
        .filter(SentencePatternWord.sentence_id == sentence_id)
        .scalar()
    )
    next_position = (max_position + 1) if max_position is not None else 0

    added = 0
    for candidate in candidates:
        lemma = candidate["lemma"]
        if lemma.id in existing_lemma_ids:
            continue

        pattern_word = SentencePatternWord(
            sentence_id=sentence_id,
            lemma_id=lemma.id,
            position=next_position,
            slot_name="discovered",
            english_text=candidate["english_text"],
        )
        session.add(pattern_word)
        existing_lemma_ids.add(lemma.id)
        next_position += 1
        added += 1

    if commit and added > 0:
        session.commit()

    return added


def discover_and_store_lemmas(
    session: Session, sentence_id: int, min_language_matches: int = 2, commit: bool = True
) -> dict:
    """Find and store candidate lemmas for a sentence.

    Convenience function that combines find_candidate_lemmas_for_sentence()
    and store_discovered_lemmas().

    Args:
        session: Database session
        sentence_id: ID of the sentence to analyze
        min_language_matches: Minimum languages that must match (default 2)
        commit: Whether to commit the transaction (default True)

    Returns:
        Dict with keys:
            - found: Number of candidate lemmas found
            - added: Number of new lemmas stored
            - candidates: List of candidate dicts
    """
    candidates = find_candidate_lemmas_for_sentence(session, sentence_id, min_language_matches)
    added = store_discovered_lemmas(session, sentence_id, candidates, commit)

    return {
        "found": len(candidates),
        "added": added,
        "candidates": candidates,
    }
