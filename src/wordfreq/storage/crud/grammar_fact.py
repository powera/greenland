"""CRUD operations for GrammarFact model."""

import logging
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from wordfreq.storage.models.grammar_fact import GrammarFact


logger = logging.getLogger(__name__)


def add_grammar_fact(
    session,
    lemma_id: int,
    language_code: str,
    fact_type: str,
    fact_value: Optional[str] = None,
    notes: Optional[str] = None,
    verified: bool = False
) -> Optional[GrammarFact]:
    """
    Add a grammar fact to a lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (e.g., "en", "lt", "fr")
        fact_type: Type of fact (e.g., "number_type", "gender", "declension")
        fact_value: Value for the fact (e.g., "plurale_tantum", "masculine", "1")
        notes: Optional notes
        verified: Whether this fact has been verified

    Returns:
        The created GrammarFact, or None if creation failed

    Examples:
        # Mark "scissors" as plurale tantum in English
        add_grammar_fact(session, lemma_id=123, language_code="en",
                        fact_type="number_type", fact_value="plurale_tantum")

        # Mark a French noun as masculine
        add_grammar_fact(session, lemma_id=456, language_code="fr",
                        fact_type="gender", fact_value="masculine")

        # Mark a Lithuanian noun's declension class
        add_grammar_fact(session, lemma_id=789, language_code="lt",
                        fact_type="declension", fact_value="1")
    """
    try:
        grammar_fact = GrammarFact(
            lemma_id=lemma_id,
            language_code=language_code,
            fact_type=fact_type,
            fact_value=fact_value,
            notes=notes,
            verified=verified
        )
        session.add(grammar_fact)
        session.commit()
        logger.info(f"Added grammar fact: lemma_id={lemma_id}, {fact_type}={fact_value} ({language_code})")
        return grammar_fact
    except IntegrityError as e:
        session.rollback()
        logger.warning(f"Grammar fact already exists or constraint violated: {e}")
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding grammar fact: {e}")
        return None


def get_grammar_facts(
    session,
    lemma_id: int,
    language_code: Optional[str] = None,
    fact_type: Optional[str] = None
) -> List[GrammarFact]:
    """
    Get grammar facts for a lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Optional filter by language
        fact_type: Optional filter by fact type

    Returns:
        List of matching GrammarFact objects

    Examples:
        # Get all grammar facts for a lemma
        facts = get_grammar_facts(session, lemma_id=123)

        # Get all English grammar facts
        facts = get_grammar_facts(session, lemma_id=123, language_code="en")

        # Get gender facts across all languages
        facts = get_grammar_facts(session, lemma_id=123, fact_type="gender")
    """
    query = session.query(GrammarFact).filter(GrammarFact.lemma_id == lemma_id)

    if language_code:
        query = query.filter(GrammarFact.language_code == language_code)

    if fact_type:
        query = query.filter(GrammarFact.fact_type == fact_type)

    return query.all()


def get_grammar_fact_value(
    session,
    lemma_id: int,
    language_code: str,
    fact_type: str
) -> Optional[str]:
    """
    Get a specific grammar fact value for a lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code
        fact_type: Type of fact to retrieve

    Returns:
        The fact_value string, or None if not found

    Examples:
        # Check if a word is plurale tantum
        number_type = get_grammar_fact_value(session, lemma_id=123,
                                            language_code="en",
                                            fact_type="number_type")
        is_plurale_tantum = (number_type == "plurale_tantum")

        # Get the gender of a French noun
        gender = get_grammar_fact_value(session, lemma_id=456,
                                       language_code="fr",
                                       fact_type="gender")
    """
    fact = session.query(GrammarFact).filter(
        GrammarFact.lemma_id == lemma_id,
        GrammarFact.language_code == language_code,
        GrammarFact.fact_type == fact_type
    ).first()

    return fact.fact_value if fact else None


def is_plurale_tantum(session, lemma_id: int, language_code: str) -> bool:
    """
    Check if a lemma is plurale tantum (plural-only) in a given language.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code

    Returns:
        True if the word is plurale tantum, False otherwise

    Example:
        if is_plurale_tantum(session, lemma_id=123, language_code="en"):
            print("This word only has plural forms")
    """
    number_type = get_grammar_fact_value(session, lemma_id, language_code, "number_type")
    return number_type == "plurale_tantum"


def delete_grammar_fact(
    session,
    lemma_id: int,
    language_code: str,
    fact_type: str
) -> bool:
    """
    Delete a specific grammar fact.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code
        fact_type: Type of fact to delete

    Returns:
        True if a fact was deleted, False if not found
    """
    fact = session.query(GrammarFact).filter(
        GrammarFact.lemma_id == lemma_id,
        GrammarFact.language_code == language_code,
        GrammarFact.fact_type == fact_type
    ).first()

    if fact:
        session.delete(fact)
        session.commit()
        logger.info(f"Deleted grammar fact: lemma_id={lemma_id}, {fact_type} ({language_code})")
        return True

    return False


def get_alternate_forms_facts(session, lemma_id: int, language_code: str) -> Optional[Dict[str, bool]]:
    """
    Get the alternate forms grammar facts for a lemma in a specific language.

    These facts describe whether the word linguistically has synonyms, abbreviations,
    expanded forms, or alternate spellings - NOT whether they're stored in the database.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code

    Returns:
        Dictionary with boolean values for each category, or None if facts not recorded
        Example: {
            'has_synonyms': False,          # Word has no synonyms
            'has_abbreviations': True,      # Word has abbreviations
            'has_expanded_forms': False,    # Word has no expanded forms
            'has_alternate_spellings': True # Word has alternate spellings
        }

        Returns None if no facts have been recorded (we don't know yet)

    Example:
        facts = get_alternate_forms_facts(session, lemma_id=123, language_code="en")
        if facts is None:
            print("Unknown - facts not yet recorded")
        elif not any(facts.values()):
            print("This word has no alternate forms")
        else:
            print(f"Has: {', '.join(k for k, v in facts.items() if v)}")
    """
    # Check if any alternate forms facts exist
    fact = session.query(GrammarFact).filter(
        GrammarFact.lemma_id == lemma_id,
        GrammarFact.language_code == language_code,
        GrammarFact.fact_type.in_([
            "has_synonyms",
            "has_abbreviations",
            "has_expanded_forms",
            "has_alternate_spellings"
        ])
    ).first()

    if not fact:
        return None

    results = {}
    for fact_type in ["has_synonyms", "has_abbreviations", "has_expanded_forms", "has_alternate_spellings"]:
        value = get_grammar_fact_value(session, lemma_id, language_code, fact_type)
        results[fact_type] = (value == "true")

    return results


def get_measure_word(session, lemma_id: int, language_code: str = "zh") -> Optional[str]:
    """
    Get the measure word (classifier) for a Chinese noun.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (default: "zh" for Chinese)

    Returns:
        The measure word string, or None if not found

    Example:
        measure_word = get_measure_word(session, lemma_id=123, language_code="zh")
        if measure_word:
            print(f"Use: 一{measure_word}...")  # e.g., "一个..." (one [classifier]...)
    """
    return get_grammar_fact_value(session, lemma_id, language_code, "measure_words")


def get_grammatical_gender(session, lemma_id: int, language_code: str) -> Optional[str]:
    """
    Get the grammatical gender for a noun in gendered languages.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (e.g., "fr", "es", "de", "ru")

    Returns:
        The gender string ("masculine", "feminine", "neuter"), or None if not found

    Example:
        gender = get_grammatical_gender(session, lemma_id=456, language_code="fr")
        if gender == "masculine":
            print("Use: le/un")  # masculine articles in French
        elif gender == "feminine":
            print("Use: la/une")  # feminine articles in French
    """
    return get_grammar_fact_value(session, lemma_id, language_code, "gender")


def get_declension_class(session, lemma_id: int, language_code: str) -> Optional[str]:
    """
    Get the declension class for a noun in languages with declensions.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (e.g., "lt", "la", "ru", "de")

    Returns:
        The declension class string (e.g., "1", "2", "3"), or None if not found

    Example:
        declension = get_declension_class(session, lemma_id=789, language_code="lt")
        if declension:
            print(f"This noun follows declension pattern {declension}")
    """
    return get_grammar_fact_value(session, lemma_id, language_code, "declension")


def update_alternate_forms_facts_after_deletion(
    session,
    lemma_id: int,
    language_code: str,
    deleted_form_type: Optional[str] = None
) -> Dict[str, bool]:
    """
    Update grammar facts for alternate forms after a derivative form is deleted.

    This function recalculates the has_* grammar facts based on remaining forms.
    If all forms of a type are removed, the grammar fact is DELETED (returns to NULL state),
    indicating "we don't know if there are any" rather than "there are definitely none".

    Three-state semantics:
    - NULL (no grammar fact): Unknown, needs LLM check (ŠERNAS should process)
    - "true": LLM confirmed forms exist AND they're stored in database
    - "false": LLM confirmed NO forms exist for this word

    When user deletes the last form, we return to NULL state because:
    - Maybe the LLM was wrong and there ARE other forms
    - Maybe the user deleted incorrect forms and we should re-check
    - We want ŠERNAS to re-evaluate rather than assume "none exist"

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (e.g., "en", "lt", "zh")
        deleted_form_type: Optional form type that was deleted
                          (e.g., 'synonym', 'abbreviation', 'expanded_form', 'alternate_spelling')
                          If None, recalculates all types

    Returns:
        Dictionary with updated fact values (True/False for each type, or omitted if deleted)

    Example:
        # After deleting a synonym
        update_alternate_forms_facts_after_deletion(session, lemma_id=123,
                                                    language_code="en",
                                                    deleted_form_type="synonym")

        # After bulk deletion (recalculate all)
        update_alternate_forms_facts_after_deletion(session, lemma_id=123,
                                                    language_code="en")
    """
    from wordfreq.storage.models.schema import DerivativeForm

    # Map form types to grammar fact types
    form_to_fact_map = {
        "synonym": "has_synonyms",
        "abbreviation": "has_abbreviations",
        "expanded_form": "has_expanded_forms",
        "alternate_spelling": "has_alternate_spellings",
        "alternative_form": "has_alternate_spellings",  # Legacy mapping
    }

    # Determine which fact types to update
    if deleted_form_type:
        fact_types_to_update = [form_to_fact_map.get(deleted_form_type)]
        fact_types_to_update = [ft for ft in fact_types_to_update if ft]  # Remove None
    else:
        # Update all fact types
        fact_types_to_update = list(set(form_to_fact_map.values()))

    results = {}

    for fact_type in fact_types_to_update:
        # Reverse map to get form types for this fact type
        relevant_form_types = [
            form_type for form_type, ft in form_to_fact_map.items()
            if ft == fact_type
        ]

        # Count remaining forms of this type
        remaining_count = session.query(DerivativeForm).filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == language_code,
            DerivativeForm.grammatical_form.in_(relevant_form_types)
        ).count()

        if remaining_count > 0:
            # Forms still exist - update fact to "true"
            # First delete old fact to avoid unique constraint issues
            delete_grammar_fact(session, lemma_id, language_code, fact_type)
            # Then add new fact
            add_grammar_fact(
                session, lemma_id, language_code, fact_type,
                fact_value="true",
                verified=True
            )
            results[fact_type] = True
            logger.info(f"Updated {fact_type}=true for lemma {lemma_id} ({language_code})")
        else:
            # No forms remain - DELETE the grammar fact (return to NULL/unknown state)
            deleted = delete_grammar_fact(session, lemma_id, language_code, fact_type)
            if deleted:
                logger.info(
                    f"Deleted {fact_type} for lemma {lemma_id} ({language_code}) - "
                    f"no forms remain, returning to unknown state"
                )
            # Don't add to results dict - absence indicates NULL state

    return results
