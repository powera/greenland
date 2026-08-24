"""TTS instruction lookup for dialect language codes.

OpenAI TTS gets its accent from the instruction text, not from the voice, so
prompts/audio/<type>/<code>.txt is the only thing that makes es-419 sound
different from es.  These tests pin the lookup, not the wording.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from clients.audio import openai_tts
from clients.audio.gpt_voices import DEFAULT_GPT_VOICES
from clients.audio.openai_tts import _prompt_cache, get_instructions
from langtools.dialect_overrides import get_all_dialect_codes, get_parent_language

_GENERIC_FALLBACK = "Speak clearly and naturally."


class TestDialectInstructions(unittest.TestCase):
    def setUp(self) -> None:
        _prompt_cache.clear()

    def test_every_recordable_dialect_has_its_own_instructions(self) -> None:
        """Inheriting the parent's file would ask for the wrong accent.

        prompts/audio/word/es.txt asks for Castilian and fr.txt for
        Metropolitan French, so a dialect that falls back to one is instructed
        to pronounce its words the one way it must not.  Any dialect we can
        record needs a file of its own.
        """
        recordable = [code for code in get_all_dialect_codes() if code in DEFAULT_GPT_VOICES]
        self.assertTrue(recordable, "no dialect is recordable; the check is vacuous")
        for dialect in recordable:
            for is_sentence in (False, True):
                dialect_text = get_instructions(dialect, is_sentence=is_sentence)
                parent_text = get_instructions(
                    get_parent_language(dialect), is_sentence=is_sentence
                )
                self.assertNotEqual(dialect_text, parent_text, dialect)
                self.assertNotEqual(dialect_text, _GENERIC_FALLBACK, dialect)

    def test_a_dialect_with_no_file_reads_its_texts_variety_not_its_base(self) -> None:
        """The middle step of the fallback, with es-mx's own file taken away.

        es-mx speaks es-419's words, so if it ever loses its file it must land
        on the Latin American prompt and not on Castilian es -- which would
        instruct the wrong pronunciation of the very words being read.
        """
        with TemporaryDirectory() as tmp:
            prompts = Path(tmp)
            (prompts / "word").mkdir()
            (prompts / "word" / "es.txt").write_text("Castilian.")
            (prompts / "word" / "es-419.txt").write_text("Latin American.")

            with patch.object(openai_tts, "PROMPTS_DIR", prompts):
                self.assertEqual(get_instructions("es-mx"), "Latin American.")

    def test_falls_back_to_the_base_language_when_nothing_closer_exists(self) -> None:
        """fr-ca reads fr directly, so the base language is the only fallback."""
        with TemporaryDirectory() as tmp:
            prompts = Path(tmp)
            (prompts / "word").mkdir()
            (prompts / "word" / "fr.txt").write_text("Metropolitan.")

            with patch.object(openai_tts, "PROMPTS_DIR", prompts):
                self.assertEqual(get_instructions("fr-ca"), "Metropolitan.")

    def test_en_gb_has_no_file_anywhere_in_its_chain(self) -> None:
        self.assertEqual(get_instructions("en-gb"), _GENERIC_FALLBACK)

    def test_lookup_accepts_unnormalized_codes(self) -> None:
        self.assertEqual(get_instructions("pt-BR"), get_instructions("pt-br"))
        self.assertEqual(get_instructions("zh_TW"), get_instructions("zh-tw"))

    def test_unknown_language_still_falls_back_to_the_generic_prompt(self) -> None:
        self.assertEqual(get_instructions("xx"), _GENERIC_FALLBACK)


if __name__ == "__main__":
    unittest.main()
