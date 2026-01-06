#!/usr/bin/python3

"""Shared translation logic for sentence translation.

This module provides reusable translation functionality that can be used by:
- BUIVOLAS agent (batch translation)
- Barsukas web UI (single sentence translation)
- Future translation agents
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord, Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import get_translation, LANGUAGE_NAMES
from clients.unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


def build_translation_prompt(
    sentence: Sentence,
    sentence_words: List[SentenceWord],
    target_languages: List[str],
    session
) -> Tuple[str, str]:
    """
    Build LLM prompt for translating a sentence.

    Args:
        sentence: Sentence object with English translation
        sentence_words: List of SentenceWord objects (English words with lemma links)
        target_languages: List of language codes to translate to
        session: Database session for lemma lookups

    Returns:
        Tuple of (context, prompt) strings
    """
    # Get English translation
    en_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence.id, language_code="en")
        .first()
    )

    if not en_translation:
        raise ValueError(f"Sentence {sentence.id} has no English translation")

    template_text = en_translation.translation_text

    # Build word translations reference with GUIDs
    word_translations = {}
    for word in sentence_words:
        if not word.lemma_id:
            continue

        lemma = session.query(Lemma).filter_by(id=word.lemma_id).first()
        if not lemma:
            continue

        # Use English lemma text as the key (e.g., "fork", "apartment")
        english_text = lemma.lemma_text
        word_translations[english_text] = {
            "guid": lemma.guid if lemma.guid else "",
            "role": word.word_role  # Keep role for reference
        }

        for lang in target_languages:
            trans = get_translation(session, lemma, lang)
            if trans:
                word_translations[english_text][lang] = trans

    # Build context (general instructions only)
    context_lines = [
        "You are translating a simple language learning sentence.",
        "",
        "For each target language, provide detailed word-by-word breakdown including:",
        "- word: the actual inflected form as it appears in the sentence",
        "- english: English translation of this specific word/phrase",
        "- guid: the GUID for this word if provided in the word reference (e.g., 'N08_001'), or empty string if not provided",
        "- role: grammatical role (subject, verb, object, adjective, adverb, article, preposition, determiner, pronoun, etc.)",
        "- grammatical_form: Use format 'pos/lang_details' where:",
        "  * pos = part of speech (verb, noun, adjective, adverb, pronoun, preposition, conjunction, article, etc.)",
        "  * lang = language code for the target language (en, lt, fr, de, es, pt, ko, zh)",
        "  * details = specific form using this notation:",
        "    - Person/number: 1s, 2s, 3s, 1p, 2p, 3p (no gender unless the WORD FORM itself differs by gender)",
        "    - Gender ONLY when word form differs: use hyphen for person (3s-m, 3s-f, 3p-m, 3p-f) or underscore for case (singular_m, plural_f)",
        "    - Tense: pres, past, fut, impf, pc (passé composé), inf (infinitive), etc.",
        "    - Case (Lithuanian, German only): nominative, accusative, genitive, dative, instrumental, locative, vocative",
        "    - For languages WITHOUT grammatical case (English, French, Spanish, Portuguese, Korean, Chinese):",
        "      Use ONLY singular/plural without case: 'noun/en_singular', 'noun/fr_plural', 'noun/zh_singular'",
        "    - For languages WITH grammatical case (Lithuanian, German):",
        "      Use case_number: 'noun/lt_nominative_singular', 'noun/de_accusative_plural'",
        "    - Combine with underscores: nominative_singular, accusative_plural_m, etc.",
        "  * Examples:",
        "    - 'verb/lt_3s_pres' (Lithuanian 'dirba' - same form for he/she)",
        "    - 'verb/fr_3s_pres' (French 'va' - same form for he/she)",
        "    - 'verb/fr_past_participle_f' (French 'partagée' - feminine participle)",
        "    - 'noun/de_accusative_singular' (German noun in accusative)",
        "    - 'adjective/es_plural_f' (Spanish feminine plural adjective)",
        "    - 'pronoun/subjective' (for 'I', 'you', 'he', 'she', 'we', 'they')",
        "    - 'pronoun/objective' (for 'me', 'you', 'him', 'her', 'us', 'them')",
        "    - 'pronoun/possessive' (for 'my', 'your', 'his', 'her', 'our', 'their')",
        "  * For invariant words: 'preposition/base', 'conjunction/base', 'article/base'",
        "- grammatical_case: case if applicable (nominative, accusative, genitive, dative, instrumental, locative, vocative) or null",
        "",
        "IMPORTANT: Do NOT include punctuation marks as separate words in the breakdown.",
        "Provide words in the order they appear in the translated sentence."
    ]

    # Build main prompt (the specific task with all relevant data)
    prompt_lines = [
        f"Template sentence: {template_text}",
        "",
        "Word translations for reference:"
    ]

    for english_word, translations in word_translations.items():
        guid = translations.get("guid", "")
        role = translations.get("role", "")
        trans_items = [(lang, trans) for lang, trans in translations.items() if lang not in ("guid", "role")]
        trans_str = ", ".join([f"{lang}={trans}" for lang, trans in trans_items])

        # Format: "fork [object] (GUID: N08_001): lt=šakutė, zh=叉子, ..."
        role_str = f" [{role}]" if role else ""
        guid_str = f" (GUID: {guid})" if guid else ""
        prompt_lines.append(f"  {english_word}{role_str}{guid_str}: {trans_str}")

    prompt_lines.extend([
        "",
        f"Translate this sentence naturally into: {', '.join([LANGUAGE_NAMES[lang] for lang in target_languages if lang in LANGUAGE_NAMES])}.",
        "",
        "IMPORTANT: Also provide a grammatically correct English version (fixing issues like singular/plural, articles, etc.).",
        "Use the provided word translations where appropriate, but adjust grammar as needed for natural sentences."
    ])

    prompt = "\n".join(prompt_lines)

    return "\n".join(context_lines), prompt


def build_response_schema(target_languages: List[str]) -> Dict:
    """
    Build JSON schema for LLM response.

    Args:
        target_languages: List of language codes to translate to

    Returns:
        Schema dict suitable for clients.lib.schema_from_dict()
    """
    # Schema for individual word details - no descriptions to reduce token usage
    # (detailed field explanations are in the prompt context)
    word_schema = {
        "type": "object",
        "properties": {
            "word": {"type": "string"},
            "english": {"type": "string"},
            "guid": {"type": "string"},
            "role": {"type": "string"},
            "grammatical_form": {"type": ["string", "null"]},
            "grammatical_case": {"type": ["string", "null"]}
        },
        "required": ["word", "english", "guid", "role", "grammatical_form", "grammatical_case"],
        "additionalProperties": False
    }

    # Build properties for sentences and word arrays
    schema_properties = {
        "en": {
            "type": "string",
            "description": "Grammatically corrected English sentence"
        },
        "words_en": {
            "type": "array",
            "description": "English word breakdown",
            "items": word_schema
        }
    }

    required_fields = ["en", "words_en"]

    # Add sentence and words array for each target language
    for lang in target_languages:
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        schema_properties[lang] = {
            "type": "string",
            "description": f"{lang_name} translation"
        }
        schema_properties[f"words_{lang}"] = {
            "type": "array",
            "description": f"{lang_name} word breakdown",
            "items": word_schema
        }
        required_fields.extend([lang, f"words_{lang}"])

    # Return just the inner schema, not the OpenAI Batch API wrapper
    return {
        "type": "object",
        "properties": schema_properties,
        "required": required_fields,
        "additionalProperties": False
    }


def translate_sentence(
    sentence_id: int,
    target_languages: List[str],
    session,
    model: str = "gpt-5-mini"
) -> Dict:
    """
    Translate a single sentence to target languages using LLM.

    Args:
        sentence_id: ID of sentence to translate
        target_languages: List of language codes (e.g., ["lt", "zh", "fr"])
        session: Database session
        model: LLM model to use

    Returns:
        Dict with translation results
    """
    # Get sentence and existing translations
    sentence = session.query(Sentence).get(sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    # Get English words with lemma links
    sentence_words = (
        session.query(SentenceWord)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .all()
    )

    # Build context, prompt and schema
    context, prompt = build_translation_prompt(sentence, sentence_words, target_languages, session)
    schema = build_response_schema(target_languages)

    # Call LLM
    client = UnifiedLLMClient()
    result = client.generate_chat(
        prompt=prompt,
        model=model,
        json_schema=schema,
        context=context
    )

    # Parse response - check both structured_data and response_text
    if result.structured_data:
        translations = result.structured_data
    elif result.response_text:
        # Parse JSON from response_text
        translations = json.loads(result.response_text)
    else:
        raise ValueError("No response data found in LLM result")

    # Store translations in database
    store_translation_results(sentence_id, translations, session)

    return translations


def store_translation_results(sentence_id: int, translations: Dict, session):
    """
    Store translation results in database.

    Args:
        sentence_id: ID of sentence
        translations: Dict with translation data from LLM
        session: Database session
    """
    logger.info(f"=== Storing translations for sentence {sentence_id} ===")

    # Update English translation if provided
    if "en" in translations:
        logger.info(f"Updating English: {translations['en']}")
        en_trans = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code="en")
            .first()
        )
        if en_trans:
            en_trans.translation_text = translations["en"]

    # Store translations for each language
    for key, value in translations.items():
        if key == "en" or key.startswith("words_"):
            continue

        # This is a language translation
        lang_code = key
        translation_text = value

        logger.info(f"Storing translation for {lang_code}: {translation_text}")

        # Create or update translation
        existing = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code=lang_code)
            .first()
        )

        if existing:
            logger.info(f"  -> Updating existing translation")
            existing.translation_text = translation_text
        else:
            logger.info(f"  -> Creating new translation")
            new_translation = SentenceTranslation(
                sentence_id=sentence_id,
                language_code=lang_code,
                translation_text=translation_text,
                verified=False
            )
            session.add(new_translation)

    # Store word-by-word data
    for key, words_data in translations.items():
        if not key.startswith("words_"):
            continue

        lang_code = key.replace("words_", "")
        logger.info(f"Storing {len(words_data)} words for {lang_code}")

        # Delete existing word links for this language
        session.query(SentenceWord).filter_by(
            sentence_id=sentence_id,
            language_code=lang_code
        ).delete()

        # Add detailed word records
        for position, word_data in enumerate(words_data):
            # Find matching lemma by GUID if provided
            lemma_id = None
            guid = word_data.get("guid", "").strip()

            if guid:
                # Look up lemma by GUID
                lemma = session.query(Lemma).filter_by(guid=guid).first()
                if lemma:
                    lemma_id = lemma.id

            # Create SentenceWord with detailed grammatical info
            new_word = SentenceWord(
                sentence_id=sentence_id,
                lemma_id=lemma_id,
                language_code=lang_code,
                position=position,
                word_role=word_data.get("role"),
                english_text=word_data.get("english"),
                target_language_text=word_data.get("word"),
                grammatical_form=word_data.get("grammatical_form"),
                grammatical_case=word_data.get("grammatical_case"),
                declined_form=word_data.get("word")
            )
            session.add(new_word)

    session.commit()
    logger.info(f"Stored translation results for sentence {sentence_id}")
