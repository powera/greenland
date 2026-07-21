"""
Lithuanian-specific coverage checks extracted from the Vilkas agent.

This module provides functions that perform the same checks as the
original `VilkasAgent` methods but accept an `agent` parameter so they
can be reused elsewhere.
"""

import logging
from typing import Any, Dict

from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import get_translation, has_translation_clause

logger = logging.getLogger(__name__)


def check_missing_lithuanian_base_forms(agent: Any) -> Dict[str, Any]:
    """Check for lemmas with Lithuanian translations but no Lithuanian derivative forms.

    `agent` must provide `get_session()`.
    """
    logger.info("Checking for lemmas missing Lithuanian base forms...")

    session = agent.get_session()
    try:
        lemmas_with_lt = session.query(Lemma).filter(has_translation_clause("lt")).all()

        logger.info(f"Found {len(lemmas_with_lt)} lemmas with Lithuanian translations")

        missing_forms = []

        for lemma in lemmas_with_lt:
            lt_forms = (
                session.query(DerivativeForm)
                .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "lt")
                .all()
            )

            if not lt_forms:
                missing_forms.append(
                    {
                        "guid": lemma.guid,
                        "english": lemma.lemma_text,
                        "lithuanian_translation": get_translation(session, lemma, "lt"),
                        "pos_type": lemma.pos_type,
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                    }
                )

        logger.info(f"Found {len(missing_forms)} lemmas missing Lithuanian derivative forms")

        return {
            "total_with_translation": len(lemmas_with_lt),
            "missing_forms": missing_forms,
            "missing_count": len(missing_forms),
            "coverage_percentage": (
                ((len(lemmas_with_lt) - len(missing_forms)) / len(lemmas_with_lt) * 100)
                if lemmas_with_lt
                else 0
            ),
        }

    except Exception as e:
        logger.error(f"Error checking missing Lithuanian base forms: {e}")
        return {
            "error": str(e),
            "total_with_translation": 0,
            "missing_forms": [],
            "missing_count": 0,
            "coverage_percentage": 0,
        }
    finally:
        session.close()


def check_noun_declension_coverage(agent: Any) -> Dict[str, Any]:
    """Check Lithuanian noun declension coverage.

    `agent` must provide `get_session()`.
    """
    logger.info("Checking Lithuanian noun declension coverage...")

    session = agent.get_session()
    try:
        noun_lemmas = (
            session.query(Lemma)
            .filter(
                Lemma.pos_type == "noun",
                has_translation_clause("lt"),
            )
            .all()
        )

        logger.info(f"Found {len(noun_lemmas)} noun lemmas with Lithuanian translations")

        needs_declensions = []
        has_declensions = []

        for lemma in noun_lemmas:
            lt_forms = (
                session.query(DerivativeForm)
                .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "lt")
                .all()
            )

            if len(lt_forms) <= 1:
                needs_declensions.append(
                    {
                        "guid": lemma.guid,
                        "english": lemma.lemma_text,
                        "lithuanian": get_translation(session, lemma, "lt"),
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                        "current_form_count": len(lt_forms),
                    }
                )
            else:
                has_declensions.append({"guid": lemma.guid, "form_count": len(lt_forms)})

        logger.info(f"Nouns with declensions: {len(has_declensions)}")
        logger.info(f"Nouns needing declensions: {len(needs_declensions)}")

        return {
            "total_nouns": len(noun_lemmas),
            "with_declensions": len(has_declensions),
            "needs_declensions": len(needs_declensions),
            "nouns_needing_declensions": needs_declensions,
            "declension_coverage_percentage": (
                (len(has_declensions) / len(noun_lemmas) * 100) if noun_lemmas else 0
            ),
        }

    except Exception as e:
        logger.error(f"Error checking noun declension coverage: {e}")
        return {
            "error": str(e),
            "total_nouns": 0,
            "with_declensions": 0,
            "needs_declensions": 0,
            "nouns_needing_declensions": [],
            "declension_coverage_percentage": 0,
        }
    finally:
        session.close()
