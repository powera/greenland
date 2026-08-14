"""Configuration-backed facade for database integrity checks."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

from storage.backend import DataSourceConfig, create_session
from storage.integrity.derivative_forms import (
    check_derivative_form_word_tokens,
    check_orphaned_derivative_forms,
)
from storage.integrity.lemmas import (
    check_duplicate_guids,
    check_duplicate_words,
    check_invalid_difficulty_levels,
    check_lemmas_without_derivatives,
    check_missing_required_fields,
)
from storage.integrity.sentences import (
    check_sentence_levels,
    check_sentences_missing_punctuation,
)

logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Run integrity checks using sessions owned by this facade.

    The module-level check functions accept caller-owned sessions and never
    finalize transactions.  This convenience facade owns each session it
    creates and commits successful repairs before closing it.
    """

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        if config.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Session:
        """Create a session configured for this checker."""
        return create_session(self.config)

    def _run(
        self,
        operation: Callable[[Session], Dict[str, Any]],
        *,
        commit_repairs: bool = False,
    ) -> Dict[str, Any]:
        session = self.get_session()
        try:
            result = operation(session)
            if commit_repairs and "error" not in result:
                session.commit()
            elif commit_repairs:
                session.rollback()
            return result
        except Exception:
            if commit_repairs:
                session.rollback()
            raise
        finally:
            session.close()

    def check_orphaned_derivative_forms(self) -> Dict[str, Any]:
        return self._run(check_orphaned_derivative_forms)

    def check_derivative_form_word_tokens(self) -> Dict[str, Any]:
        return self._run(check_derivative_form_word_tokens)

    def check_missing_required_fields(self) -> Dict[str, Any]:
        return self._run(check_missing_required_fields)

    def check_lemmas_without_derivatives(self) -> Dict[str, Any]:
        return self._run(check_lemmas_without_derivatives)

    def check_duplicate_guids(self) -> Dict[str, Any]:
        return self._run(check_duplicate_guids)

    def check_duplicate_words(self) -> Dict[str, Any]:
        return self._run(check_duplicate_words)

    def check_invalid_difficulty_levels(self) -> Dict[str, Any]:
        return self._run(check_invalid_difficulty_levels)

    def check_sentence_levels(self, fix: bool = False) -> Dict[str, Any]:
        return self._run(
            lambda session: check_sentence_levels(session, fix=fix),
            commit_repairs=fix,
        )

    def check_sentences_missing_punctuation(self, fix: bool = False) -> Dict[str, Any]:
        return self._run(
            lambda session: check_sentences_missing_punctuation(session, fix=fix),
            commit_repairs=fix,
        )
