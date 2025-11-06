"""Legacy compatibility functions for backward compatibility."""

from wordfreq.storage.crud.word_token import get_word_token_by_text


def get_word_by_text(session, word_text: str, language_code: str = "en"):
    """
    Legacy function for backward compatibility with reviewer.py.
    Returns a WordToken with a 'definitions' property that contains derivative forms.
    """
    word_token = get_word_token_by_text(session, word_text, language_code)
    if not word_token:
        return None

    # Create a wrapper object that mimics the old Word model
    class WordWrapper:
        def __init__(self, word_token):
            self.word = word_token.token
            self.frequency_rank = word_token.frequency_rank
            self._word_token = word_token

        @property
        def definitions(self):
            """Return derivative forms as 'definitions' for backward compatibility."""
            return self._word_token.derivative_forms

    return WordWrapper(word_token)
