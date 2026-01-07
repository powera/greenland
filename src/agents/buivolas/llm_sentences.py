"""LLM-driven sentence generation for Buivolas."""

import json
import logging
from typing import Dict, List, Optional

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

    def get_session(self):
        return create_backend_session(self.config)

    def generate_sentences_for_noun(
        self,
        lemma: Lemma,
        target_languages: List[str],
        num_sentences: int = 3,
        difficulty_context: Optional[int] = None,
    ) -> Dict[str, any]:
        if lemma.pos_type != "noun":
            logger.warning("Lemma %s is not a noun (got %s)", lemma.guid, lemma.pos_type)
            return {"success": False, "error": f"Expected noun, got {lemma.pos_type}"}

        logger.info(
            "Generating %s sentences for noun: %s (GUID: %s)",
            num_sentences,
            lemma.lemma_text,
            lemma.guid,
        )

        session = self.get_session()
        try:
            noun_translations = {}
            for lang_code in target_languages:
                if lang_code == "en":
                    noun_translations[lang_code] = lemma.lemma_text
                else:
                    from wordfreq.storage.translation_helpers import get_translation

                    translation = get_translation(session, lemma, lang_code)
                    if translation:
                        noun_translations[lang_code] = translation

            context = self._build_sentence_context(lemma, difficulty_context)

            generated_sentences = []
            previous_sentences = []

            for i in range(num_sentences):
                logger.info(
                    "Generating sentence %s/%s for %s",
                    i + 1,
                    num_sentences,
                    lemma.lemma_text,
                )

                result = self._call_llm_for_sentence(
                    lemma=lemma,
                    noun_translations=noun_translations,
                    target_languages=target_languages,
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
        finally:
            session.close()

    def _build_sentence_context(
        self, lemma: Lemma, difficulty_level: Optional[int]
    ) -> str:
        context_parts = [
            f"Word: {lemma.lemma_text}",
            f"Definition: {lemma.definition_text}",
            f"Part of Speech: {lemma.pos_type}",
        ]

        if difficulty_level:
            context_parts.append(
                f"Difficulty Level: {difficulty_level} (Trakaido level 1-20)"
            )

        if lemma.disambiguation:
            context_parts.append(f"Disambiguation: {lemma.disambiguation}")

        return "\n".join(context_parts)

    def _call_llm_for_sentence(
        self,
        lemma: Lemma,
        noun_translations: Dict[str, str],
        target_languages: List[str],
        context: str,
        previous_sentences: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        langs_str = ", ".join(target_languages)
        translations_str = json.dumps(noun_translations, indent=2)

        previous_context = ""
        if previous_sentences:
            previous_context = (
                "\n\nPreviously generated sentences (make sure this new sentence is different):\n"
                + "\n".join(f"- {s}" for s in previous_sentences)
            )

        prompt = f"""Generate 1 English example sentence for language learning that features the following noun.

{context}

Translations of the noun in target languages:
{translations_str}
{previous_context}

Requirements:
1. Create 1 ENGLISH sentence using the noun "{lemma.lemma_text}"
2. Vary the sentence pattern (SVO, SOV, etc.) and use different verbs/contexts
3. Keep sentences simple and natural (appropriate for language learners)
4. Use common, everyday vocabulary for other words in the sentence
5. Translate the English sentence to ALL target languages: {langs_str}
   - Provide natural, idiomatic translations (not word-for-word)
   - Ensure grammatical correctness in each language

For the sentence, provide:
- Pattern type (SVO, SVAO, etc.) - based on English structure
- Tense used (present, past, future)
- Translations in all languages (keys are language codes like 'en', 'lt', etc.)
- For EACH target language sentence, list ALL words in order with their:
  - The actual word/phrase as it appears (e.g., "Le chocolat", "초콜릿은")
  - English translation of this word/phrase (e.g., "the chocolate", "chocolate")
  - Base/lemma form in that language (e.g., "chocolat", "초콜릿")
  - Role in sentence (subject, verb, object, adjective, preposition, article, etc.)
  - For nouns/adjectives: grammatical case (e.g., "accusative", "nominative")
  - For verbs: grammatical form (e.g., "3s_present", "1s_past")
  - English lemma for vocabulary linking (e.g., "chocolate", "melt", "sun")

Important: List words in the order they appear in that language's sentence, not English order.
Include ALL words including articles, prepositions, particles.

Focus on variety, natural language usage, and accurate translations."""

        translations_properties = {}
        words_by_language_properties = {}

        for lang_code in target_languages:
            translations_properties[lang_code] = {
                "type": "string",
                "description": f"Sentence in {lang_code}",
            }

            words_by_language_properties[f"words_{lang_code}"] = {
                "type": "array",
                "description": f"All words in the {lang_code} sentence, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "The word/phrase as it appears in sentence",
                        },
                        "english": {
                            "type": "string",
                            "description": "English translation of this word",
                        },
                        "lemma": {
                            "type": "string",
                            "description": "Base/lemma form in this language",
                        },
                        "role": {"type": "string", "description": "Role in sentence"},
                        "grammatical_form": {
                            "type": "string",
                            "description": "Grammatical form (e.g., '3s_present')",
                        },
                        "english_lemma": {
                            "type": "string",
                            "description": "English lemma for linking to vocabulary",
                        },
                    },
                    "required": ["word", "english", "lemma", "role"],
                },
            }

        translations_schema_props = {}
        for lang_code, lang_def in translations_properties.items():
            translations_schema_props[lang_code] = SchemaProperty(
                type=lang_def["type"],
                description=lang_def.get("description", ""),
            )

        translations_schema = Schema(
            name="Translations",
            description="Sentence in each language",
            properties=translations_schema_props,
        )

        top_level_properties = {
            "translations": SchemaProperty(
                type="object",
                description="Sentence in each language",
                object_schema=translations_schema,
            ),
            "pattern": SchemaProperty(
                type="string", description="Sentence pattern type (SVO, SVAO, etc.)"
            ),
            "tense": SchemaProperty(
                type="string", description="Verb tense (present, past, future)"
            ),
        }

        for lang_code in target_languages:
            if lang_code == "en":
                continue
            words_key = f"words_{lang_code}"
            top_level_properties[words_key] = SchemaProperty(
                type="array",
                description=f"All words in the {lang_code} sentence, in order",
                items=words_by_language_properties[words_key],
            )

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
                return response.structured_data

            logger.error("No structured data received from LLM")
            return None

        except Exception as e:
            logger.error("Error calling LLM: %s", e, exc_info=True)
            return None

    def store_sentences(
        self, sentences_data: List[Dict], source_lemma: Lemma, session
    ) -> Dict[str, any]:
        stored_count = 0
        failed_count = 0
        errors = []
        sentence_ids = []

        for sentence_data in sentences_data:
            try:
                sentence = add_sentence(
                    session=session,
                    pattern_type=sentence_data.get("pattern"),
                    tense=sentence_data.get("tense"),
                    source_filename=f"buivolas_{source_lemma.guid}",
                    verified=False,
                    notes=(
                        "Generated for %s (GUID: %s)" % (
                            source_lemma.lemma_text,
                            source_lemma.guid,
                        )
                    ),
                )

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
                        if english_lemma:
                            word_lemma = self._find_lemma_for_word(
                                session,
                                english_lemma,
                                word_data.get("role"),
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
        session,
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
            return lemma

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
            return lemma

        logger.debug("No lemma found for word '%s' (role: %s)", word_text, word_role)
        return None
