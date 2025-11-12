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
            'has_synonyms',
            'has_abbreviations',
            'has_expanded_forms',
            'has_alternate_spellings'
        ])
    ).first()

    if not fact:
        return None

    results = {}
    for fact_type in ['has_synonyms', 'has_abbreviations', 'has_expanded_forms', 'has_alternate_spellings']:
        value = get_grammar_fact_value(session, lemma_id, language_code, fact_type)
        results[fact_type] = (value == "true")

    return results
