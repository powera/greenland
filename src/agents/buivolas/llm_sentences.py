"""LLM-driven sentence generation for Buivolas."""

import logging
from typing import Any, Dict, List, Optional, cast

from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.database import (
    Lemma,
    add_sentence,
    add_sentence_translation,
    add_sentence_word,
    calculate_minimum_level,
)
from wordfreq.storage.models.schema import SentencePatternWord

logger = logging.getLogger(__name__)


class LlmSentenceGenerator:
    """Generate sentences using an LLM and store structured word data."""

    def __init__(self, config: DataSourceConfig, dry_run: bool = False):
        self.config = config
        self.debug = config.debug
        self.dry_run = dry_run
        self.llm_client = UnifiedLLMClient.from_config(config)

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        return create_backend_session(self.config)

    def generate_sentences_for_noun(
        self,
        lemma: Lemma,
        num_sentences: int = 3,
        difficulty_context: Optional[int] = None,
    ) -> Dict[str, Any]:
        if lemma.pos_type != "noun":
            logger.warning("Lemma %s is not a noun (got %s)", lemma.guid, lemma.pos_type)
            return {"success": False, "error": f"Expected noun, got {lemma.pos_type}"}

        logger.info(
            "Generating %s sentences for noun: %s (GUID: %s)",
            num_sentences,
            lemma.lemma_text,
            lemma.guid,
        )

        try:
            context = self._build_sentence_context(lemma, difficulty_context)

            generated_sentences: List[Dict[str, Any]] = []
            previous_sentences: List[str] = []

            for i in range(num_sentences):
                logger.info(
                    "Generating sentence %s/%s for %s",
                    i + 1,
                    num_sentences,
                    lemma.lemma_text,
                )

                result = self._call_llm_for_sentence(
                    lemma=lemma,
                    context=context,
                    previous_sentences=previous_sentences,
                )

                if not result:
                    logger.error(
                        "LLM failed to generate sentence %s for %s",
                        i + 1,
                        lemma.lemma_text,
                    )
                    break

                generated_sentences.append(result)

                english_text = result.get("translations", {}).get("en", "")
                if english_text:
                    previous_sentences.append(english_text)

            if not generated_sentences:
                logger.error(
                    "LLM failed to generate any sentences for %s",
                    lemma.lemma_text,
                )
                return {"success": False, "error": "LLM generation failed"}

            return {
                "success": True,
                "sentences": generated_sentences,
                "lemma_guid": lemma.guid,
            }

        except Exception as e:
            logger.error(
                "Error generating sentences for %s: %s",
                lemma.lemma_text,
                e,
                exc_info=True,
            )
            return {"success": False, "error": str(e)}

    def _build_sentence_context(self, lemma: Lemma, difficulty_level: Optional[int]) -> str:
        context_parts = [
            f"Word: {lemma.lemma_text}",
            f"Definition: {lemma.definition_text}",
            f"Part of Speech: {lemma.pos_type}",
        ]

        if difficulty_level:
            context_parts.append(f"Difficulty Level: {difficulty_level} (Trakaido level 1-20)")

        if lemma.disambiguation:
            context_parts.append(f"Disambiguation: {lemma.disambiguation}")

        return "\n".join(context_parts)

    def _call_llm_for_sentence(
        self,
        lemma: Lemma,
        context: str,
        previous_sentences: Optional[List[str]] = None,
    ) -> Optional[Dict[Any, Any]]:
        previous_context = ""
        if previous_sentences:
            previous_context = (
                "\n\nPreviously generated sentences (make sure this new sentence is different):\n"
                + "\n".join(f"- {s}" for s in previous_sentences)
            )

        prompt = f"""Generate 1 English example sentence for language learning that features the following word.

{context}
{previous_context}

Requirements:
1. Create 1 ENGLISH sentence using the word "{lemma.lemma_text}"
2. Use varied contexts and sentence structures
3. Keep sentences simple and natural (appropriate for language learners)
4. Use common, everyday vocabulary for other words in the sentence

For the sentence, provide:
- Tense used (present, past, future, or N/A if not applicable)
- English translation (key 'en')

Focus on variety and natural language usage."""

        translations_schema = Schema(
            name="Translations",
            description="English sentence",
            properties={
                "en": SchemaProperty(
                    type="string",
                    description="Sentence in English",
                )
            },
        )

        top_level_properties = {
            "translations": SchemaProperty(
                type="object",
                description="English sentence",
                object_schema=translations_schema,
            ),
            "tense": SchemaProperty(
                type="string", description="Verb tense (present, past, future, or N/A)"
            ),
        }

        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentence with grammatical analysis",
            properties=top_level_properties,
        )

        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                json_schema=schema,
                timeout=60,
            )

            if response.structured_data:
                return cast(Dict[Any, Any], response.structured_data)

            logger.error("No structured data received from LLM")
            return None

        except Exception as e:
            logger.error("Error calling LLM: %s", e, exc_info=True)
            return None

    def store_sentences(
        self, sentences_data: List[Dict[str, Any]], source_lemma: Lemma, session: Any
    ) -> Dict[str, Any]:
        stored_count = 0
        failed_count = 0
        errors = []
        sentence_ids = []

        for sentence_data in sentences_data:
            try:
                sentence = add_sentence(
                    session=session,
                    pattern_type=sentence_data.get("pattern", "unknown"),
                    tense=sentence_data.get("tense"),
                    source_filename=f"buivolas_{source_lemma.guid}",
                    verified=False,
                    notes=(
                        "Generated for %s (GUID: %s)"
                        % (
                            source_lemma.lemma_text,
                            source_lemma.guid,
                        )
                    ),
                )

                # Link the sentence to the source lemma via SentencePatternWord
                # This allows zvirblis to find LLM-generated sentences for the lemma
                pattern_word = SentencePatternWord(
                    sentence_id=sentence.id,
                    lemma_id=source_lemma.id,
                    position=0,
                    slot_name="llm_generated",
                )
                session.add(pattern_word)

                translations = sentence_data.get("translations", {})
                for lang_code, text in translations.items():
                    add_sentence_translation(
                        session=session,
                        sentence=sentence,
                        language_code=lang_code,
                        translation_text=text,
                        verified=False,
                    )

                translations = sentence_data.get("translations", {})
                for lang_code in translations.keys():
                    if lang_code == "en":
                        continue

                    words_key = f"words_{lang_code}"
                    words_used = sentence_data.get(words_key, [])

                    flattened_words = []
                    for item in words_used:
                        if isinstance(item, list):
                            flattened_words.extend(item)
                        elif isinstance(item, dict):
                            flattened_words.append(item)
                        else:
                            logger.error(
                                "Unexpected item type in %s: %s",
                                words_key,
                                type(item),
                            )

                    words_used = flattened_words

                    for position, word_data in enumerate(words_used):
                        if not isinstance(word_data, dict):
                            logger.error(
                                "Expected dict at position %s in %s, got %s: %s",
                                position,
                                words_key,
                                type(word_data),
                                word_data,
                            )
                            continue

                        english_lemma = word_data.get("english_lemma")
                        word_lemma = None
                        role_value = word_data.get("role")
                        if english_lemma and isinstance(role_value, str):
                            word_lemma = self._find_lemma_for_word(
                                session,
                                english_lemma,
                                role_value,
                                source_lemma=source_lemma,
                            )

                        add_sentence_word(
                            session=session,
                            sentence=sentence,
                            position=position,
                            word_role=word_data.get("role", "unknown"),
                            lemma=word_lemma,
                            english_text=word_data.get("english"),
                            target_language_text=word_data.get("lemma"),
                            grammatical_form=word_data.get("grammatical_form"),
                            grammatical_case=None,
                            declined_form=word_data.get("word"),
                            language_code=lang_code,
                        )

                calculate_minimum_level(session, sentence)
                sentence.minimum_level = -1
                min_level = -1

                session.flush()
                stored_count += 1
                sentence_ids.append(sentence.id)

                logger.info(
                    "✓ Stored sentence %s: %s... (level: %s)",
                    sentence.id,
                    translations.get("en", "N/A")[:50],
                    min_level or "N/A",
                )

            except Exception as e:
                logger.error("Failed to store sentence: %s", e, exc_info=True)
                failed_count += 1
                errors.append(str(e))
                session.rollback()

        if stored_count > 0:
            session.commit()

        return {
            "stored": stored_count,
            "failed": failed_count,
            "errors": errors,
            "sentence_ids": sentence_ids,
        }

    def _find_lemma_for_word(
        self,
        session: Any,
        word_text: str,
        word_role: str,
        source_lemma: Optional[Lemma] = None,
    ) -> Optional[Lemma]:
        if not word_text:
            return None

        if source_lemma:
            source_text = source_lemma.lemma_text
            if "(" in source_text:
                source_base = source_text.split("(")[0].strip()
            else:
                source_base = source_text

            if word_text.lower() == source_base.lower():
                logger.debug(
                    "Matched word '%s' to source lemma: %s (%s)",
                    word_text,
                    source_lemma.guid,
                    source_lemma.lemma_text,
                )
                return source_lemma

        role_to_pos = {
            "subject": "noun",
            "object": "noun",
            "verb": "verb",
            "adjective": "adjective",
            "adverb": "adverb",
        }

        pos_hint = role_to_pos.get(word_role)

        query = session.query(Lemma).filter(Lemma.lemma_text == word_text)

        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)

        lemma = query.first()

        if lemma:
            logger.debug("Found lemma for '%s': %s", word_text, lemma.guid)
            return cast(Lemma, lemma)

        query = session.query(Lemma).filter(Lemma.lemma_text.ilike(word_text))

        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)

        lemma = query.first()

        if lemma:
            logger.debug(
                "Found lemma (case-insensitive) for '%s': %s",
                word_text,
                lemma.guid,
            )
            return cast(Lemma, lemma)

        logger.debug("No lemma found for word '%s' (role: %s)", word_text, word_role)
        return None
