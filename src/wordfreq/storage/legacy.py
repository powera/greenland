"""Legacy compatibility functions for backward compatibility."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from wordfreq.storage.crud.word_token import get_word_token_by_text


class WordWrapper:
    """Wrapper object that mimics the old Word model for backward compatibility."""

    def __init__(self, word_token: Any) -> None:
        self.word = word_token.token
        self.frequency_rank = word_token.frequency_rank
        self._word_token = word_token

    @property
    def definitions(self) -> Any:
        """Return derivative forms as 'definitions' for backward compatibility."""
        return self._word_token.derivative_forms


def get_word_by_text(
    session: Session, word_text: str, language_code: str = "en"
) -> Optional[WordWrapper]:
    """
    Legacy function for backward compatibility with reviewer.py.
    Returns a WordToken with a 'definitions' property that contains derivative forms.
    """
    word_token = get_word_token_by_text(session, word_text, language_code)
    if not word_token:
        return None

    return WordWrapper(word_token)
