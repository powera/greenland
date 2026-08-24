"""TTS instruction lookup for dialect language codes.

OpenAI TTS gets its accent from the instruction text, not from the voice, so
prompts/audio/<type>/<code>.txt is the only thing that makes es-419 sound
different from es.  These tests pin the lookup, not the wording.
"""

from __future__ import annotations

import unittest

from clients.audio.openai_tts import _prompt_cache, get_instructions
from langtools.dialect_overrides import get_parent_language, get_translation_target_dialects

_GENERIC_FALLBACK = "Speak clearly and naturally."


class TestDialectInstructions(unittest.TestCase):
    def setUp(self) -> None:
        _prompt_cache.clear()

    def test_every_storage_dialect_has_its_own_instructions(self) -> None:
        """Inheriting the parent's file would ask for the wrong accent.

        prompts/audio/word/es.txt asks for Castilian, so es-419 falling back to
        it would be worse than useless.
        """
        for dialect in get_translation_target_dialects():
            for is_sentence in (False, True):
                dialect_text = get_instructions(dialect, is_sentence=is_sentence)
                parent_text = get_instructions(
                    get_parent_language(dialect), is_sentence=is_sentence
                )
                self.assertNotEqual(dialect_text, parent_text, dialect)
                self.assertNotEqual(dialect_text, _GENERIC_FALLBACK, dialect)

    def test_unknown_dialect_falls_back_to_its_parent(self) -> None:
        """fr-ca has no prompt file, so it should read as French, not as nothing."""
        self.assertEqual(get_instructions("fr-ca"), get_instructions("fr"))

    def test_lookup_accepts_unnormalized_codes(self) -> None:
        self.assertEqual(get_instructions("pt-BR"), get_instructions("pt-br"))
        self.assertEqual(get_instructions("zh_TW"), get_instructions("zh-tw"))

    def test_unknown_language_still_falls_back_to_the_generic_prompt(self) -> None:
        self.assertEqual(get_instructions("xx"), _GENERIC_FALLBACK)


if __name__ == "__main__":
    unittest.main()
