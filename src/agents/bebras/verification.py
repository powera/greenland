#!/usr/bin/env python3
"""
Translation verification module for the Bebras agent.

This module provides verification-only checks for word and sentence translations.
It does NOT regenerate content - it only validates and returns "correct"/"incorrect".
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.openai.batch_client import OpenAIBatchClient
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.storage.translation_helpers import (
    LANGUAGE_NAMES,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
    get_translation,
    bulk_get_translations,
)

logger = logging.getLogger(__name__)

# Model language support - which languages each model can reliably verify
# Based on user specification: only gpt-5-mini, supporting lt zh fr es de it nl pt sv
MODEL_LANGUAGE_SUPPORT: Dict[str, List[str]] = {
    "gpt-5-mini": ["lt", "zh", "zh-tw", "fr", "es", "de", "it", "nl", "pt", "sv"],
}

# Default languages to verify if none specified
DEFAULT_VERIFY_LANGUAGES = TIER_1_LANGUAGES  # lt, zh, fr, es

# Language dialect display names for prompts
LANGUAGE_DIALECT_NAMES: Dict[str, str] = {
    "lt": "Lithuanian",
    "zh": "Chinese (Mainland Simplified)",
    "zh-tw": "Chinese (Taiwan Traditional)",
    "fr": "French",
    "es": "Spanish (Castilian)",
    "de": "German",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese (Brazilian)",
    "sv": "Swedish",
}


def get_supported_languages(model: str) -> List[str]:
    """Get list of languages supported by a model for verification.

    Args:
        model: Model name (e.g., 'gpt-5-mini')

    Returns:
        List of language codes the model can verify
    """
    return MODEL_LANGUAGE_SUPPORT.get(model, [])


def filter_languages_for_model(requested_languages: List[str], model: str) -> List[str]:
    """Filter requested languages to those the model can verify.

    Args:
        requested_languages: Languages the user wants to verify
        model: Model to use for verification

    Returns:
        Filtered list of languages the model supports
    """
    supported = get_supported_languages(model)
    filtered = [lang for lang in requested_languages if lang in supported]

    if len(filtered) < len(requested_languages):
        unsupported = set(requested_languages) - set(filtered)
        logger.warning(
            f"Model {model} does not support languages: {unsupported}. "
            f"Skipping verification for these."
        )

    return filtered


def get_dialect_display_name(lang_code: str) -> str:
    """Get display name with dialect info for a language code.

    Args:
        lang_code: Language code (e.g., 'zh', 'zh-tw')

    Returns:
        Display name with dialect (e.g., 'Chinese (Mainland Simplified)')
    """
    return LANGUAGE_DIALECT_NAMES.get(lang_code, LANGUAGE_NAMES.get(lang_code, lang_code))


class VerificationAgent:
    """Agent for verifying translation correctness without regenerating content."""

    def __init__(self, config: DataSourceConfig):
        """Initialize the verification agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings
        """
        self.config = config
        self.debug = config.debug
        self.model = config.model or "gpt-5-mini"
        self.llm_client = UnifiedLLMClient.from_config(config)

        # Initialize batch processing components
        self.batch_client = OpenAIBatchClient(debug=self.debug)
        self.batch_session = create_batch_database_session()
        self.batch_manager = BatchQueueManager(
            self.batch_session, self.batch_client, debug=self.debug
        )

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def verify_word_translations(
        self,
        lemma: Lemma,
        languages: Optional[List[str]] = None,
        session: Any = None,
    ) -> Dict[str, Any]:
        """Verify translations for a single word/lemma.

        Args:
            lemma: Lemma object to verify translations for
            languages: Language codes to verify (defaults to tier-1 languages)
            session: Database session (creates one if None)

        Returns:
            Dictionary with verification results per language:
            {
                'lemma_guid': 'WRD-00123',
                'lemma_text': 'set',
                'results': {
                    'lt': 'correct',
                    'zh': 'correct',
                    'fr': 'incorrect',
                    ...
                },
                'success': True
            }
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True

        try:
            # Determine languages to verify
            if languages is None:
                languages = DEFAULT_VERIFY_LANGUAGES

            # Filter to languages the model supports
            languages = filter_languages_for_model(languages, self.model)
            if not languages:
                return {
                    "lemma_guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "results": {},
                    "success": False,
                    "error": f"No supported languages for model {self.model}",
                }

            # Get translations for all requested languages
            translations: Dict[str, str] = {}
            for lang_code in languages:
                trans = get_translation(session, lemma, lang_code)
                if trans and trans.strip():
                    translations[lang_code] = trans

            if not translations:
                return {
                    "lemma_guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "results": {},
                    "success": False,
                    "error": "No translations found for requested languages",
                }

            # Build verification prompt
            prompt = self._build_word_verification_prompt(lemma, translations)
            schema = self._build_word_verification_schema(list(translations.keys()))

            # Call LLM
            response = self.llm_client.generate_chat(prompt=prompt, json_schema=schema, timeout=60)

            if not response.structured_data:
                logger.error(f"No structured data received for lemma {lemma.guid}")
                return {
                    "lemma_guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "results": {},
                    "success": False,
                    "error": "LLM did not return structured data",
                }

            # Parse results
            results = {}
            for lang_code in translations.keys():
                result_key = f"{lang_code}_verdict"
                verdict = response.structured_data.get(result_key, "").lower()
                # Normalize to "correct" or "incorrect"
                if verdict in ["correct", "true", "yes", "1"]:
                    results[lang_code] = "correct"
                else:
                    results[lang_code] = "incorrect"

            return {
                "lemma_guid": lemma.guid,
                "lemma_text": lemma.lemma_text,
                "definition": lemma.definition_text,
                "pos_type": lemma.pos_type,
                "translations_checked": translations,
                "results": results,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error verifying word {lemma.guid}: {e}", exc_info=True)
            return {
                "lemma_guid": lemma.guid if lemma else None,
                "lemma_text": lemma.lemma_text if lemma else None,
                "results": {},
                "success": False,
                "error": str(e),
            }
        finally:
            if close_session:
                session.close()

    def _build_word_verification_prompt(self, lemma: Lemma, translations: Dict[str, str]) -> str:
        """Build the LLM prompt for word translation verification.

        Args:
            lemma: Lemma object with word info
            translations: Dict mapping language codes to translation strings

        Returns:
            Formatted prompt string
        """
        # Build disambiguation info
        disambiguation_info = ""
        if lemma.disambiguation:
            disambiguation_info = f'\nDisambiguation: "{lemma.disambiguation}"'

        # Build translations list with dialect names
        translations_list = []
        for lang_code, trans in translations.items():
            dialect_name = get_dialect_display_name(lang_code)
            translations_list.append(f"- {dialect_name} ({lang_code}): {trans}")
        translations_text = "\n".join(translations_list)

        prompt = f"""You are a translation verification expert. Your task is to verify whether translations are correct.

Word: "{lemma.lemma_text}" ({lemma.pos_type})
Definition: "{lemma.definition_text}"{disambiguation_info}

Translations to verify:
{translations_text}

For EACH translation, determine if it is a correct translation of the English word given the definition and context.

IMPORTANT:
- Respond with ONLY "correct" or "incorrect" for each translation
- A translation is "correct" if it accurately conveys the meaning of the English word
- A translation is "incorrect" if it has the wrong meaning, is misspelled, or uses the wrong word entirely
- Consider the specific dialect indicated (e.g., Mainland Chinese vs Taiwan Chinese)
- The translation should be in lemma/dictionary form (base form)
"""
        return prompt

    def _build_word_verification_schema(self, language_codes: List[str]) -> Schema:
        """Build the response schema for word verification.

        Args:
            language_codes: List of language codes being verified

        Returns:
            Schema object for LLM response
        """
        properties = {}
        for lang_code in language_codes:
            dialect_name = get_dialect_display_name(lang_code)
            properties[f"{lang_code}_verdict"] = SchemaProperty(
                type="string",
                description=f'Verdict for {dialect_name} translation: "correct" or "incorrect"',
                enum=["correct", "incorrect"],
            )

        return Schema(
            name="WordTranslationVerification",
            description="Verification results for word translations",
            properties=properties,
        )

    def verify_sentence_translations(
        self,
        sentence: Sentence,
        languages: Optional[List[str]] = None,
        session: Any = None,
        check_lemma_links: bool = True,
    ) -> Dict[str, Any]:
        """Verify translations for a sentence.

        Args:
            sentence: Sentence object to verify translations for
            languages: Language codes to verify (defaults to tier-1 languages)
            session: Database session (creates one if None)
            check_lemma_links: Whether to also verify linked lemmas

        Returns:
            Dictionary with verification results per language
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True

        try:
            # Determine languages to verify
            if languages is None:
                languages = DEFAULT_VERIFY_LANGUAGES

            # Filter to languages the model supports
            languages = filter_languages_for_model(languages, self.model)
            if not languages:
                return {
                    "sentence_id": sentence.id,
                    "results": {},
                    "success": False,
                    "error": f"No supported languages for model {self.model}",
                }

            # Get English sentence
            english_trans = (
                session.query(SentenceTranslation)
                .filter(
                    SentenceTranslation.sentence_id == sentence.id,
                    SentenceTranslation.language_code == "en",
                )
                .first()
            )

            if not english_trans:
                return {
                    "sentence_id": sentence.id,
                    "results": {},
                    "success": False,
                    "error": "No English translation found for sentence",
                }

            english_text = english_trans.translation_text

            # Get translations and sentence words for each language
            language_data: Dict[str, Dict[str, Any]] = {}

            for lang_code in languages:
                # Get translation
                trans = (
                    session.query(SentenceTranslation)
                    .filter(
                        SentenceTranslation.sentence_id == sentence.id,
                        SentenceTranslation.language_code == lang_code,
                    )
                    .first()
                )

                if not trans:
                    continue

                # Get sentence words for this language
                sentence_words = (
                    session.query(SentenceWord)
                    .filter(
                        SentenceWord.sentence_id == sentence.id,
                        SentenceWord.language_code == lang_code,
                    )
                    .order_by(SentenceWord.position)
                    .all()
                )

                # Build linked lemma info
                linked_lemmas = []
                for sw in sentence_words:
                    lemma_info: Dict[str, Any] = {
                        "position": sw.position,
                        "english_text": sw.english_text,
                        "target_text": sw.target_language_text,
                        "declined_form": sw.declined_form,
                        "word_role": sw.word_role,
                        "lemma_guid": None,
                        "expected_translation": None,
                    }

                    if sw.lemma:
                        lemma_info["lemma_guid"] = sw.lemma.guid
                        # Get the lemma's official translation for this language
                        lemma_trans = get_translation(session, sw.lemma, lang_code)
                        lemma_info["expected_translation"] = lemma_trans

                    linked_lemmas.append(lemma_info)

                language_data[lang_code] = {
                    "translation": trans.translation_text,
                    "linked_lemmas": linked_lemmas,
                }

            if not language_data:
                return {
                    "sentence_id": sentence.id,
                    "english_text": english_text,
                    "results": {},
                    "success": False,
                    "error": "No translations found for requested languages",
                }

            # Build verification prompt
            prompt = self._build_sentence_verification_prompt(
                english_text, language_data, check_lemma_links
            )
            schema = self._build_sentence_verification_schema(
                list(language_data.keys()), check_lemma_links
            )

            # Call LLM
            response = self.llm_client.generate_chat(prompt=prompt, json_schema=schema, timeout=90)

            if not response.structured_data:
                logger.error(f"No structured data received for sentence {sentence.id}")
                return {
                    "sentence_id": sentence.id,
                    "english_text": english_text,
                    "results": {},
                    "success": False,
                    "error": "LLM did not return structured data",
                }

            # Parse results
            results = {}
            for lang_code in language_data.keys():
                lang_result: Dict[str, Any] = {
                    "translation": language_data[lang_code]["translation"],
                    "meaning_correct": self._parse_verdict(
                        response.structured_data.get(f"{lang_code}_meaning")
                    ),
                    "grammar_correct": self._parse_verdict(
                        response.structured_data.get(f"{lang_code}_grammar")
                    ),
                }

                if check_lemma_links:
                    lemma_checks = {}
                    for lemma_info in language_data[lang_code]["linked_lemmas"]:
                        if lemma_info["lemma_guid"]:
                            guid = lemma_info["lemma_guid"]
                            safe_guid = guid.replace("-", "_")
                            lemma_checks[guid] = {
                                "sense_correct": self._parse_verdict(
                                    response.structured_data.get(f"{lang_code}_{safe_guid}_sense")
                                ),
                                "form_matches": self._parse_verdict(
                                    response.structured_data.get(f"{lang_code}_{safe_guid}_form")
                                ),
                            }
                    lang_result["lemma_checks"] = lemma_checks

                results[lang_code] = lang_result

            return {
                "sentence_id": sentence.id,
                "english_text": english_text,
                "results": results,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error verifying sentence {sentence.id}: {e}", exc_info=True)
            return {
                "sentence_id": sentence.id if sentence else None,
                "results": {},
                "success": False,
                "error": str(e),
            }
        finally:
            if close_session:
                session.close()

    def _parse_verdict(self, value: Optional[str]) -> str:
        """Parse LLM verdict to normalized form.

        Args:
            value: Raw verdict from LLM

        Returns:
            "correct" or "incorrect"
        """
        if not value:
            return "incorrect"
        value = value.lower().strip()
        if value in ["correct", "true", "yes", "1"]:
            return "correct"
        return "incorrect"

    def _build_sentence_verification_prompt(
        self,
        english_text: str,
        language_data: Dict[str, Dict[str, Any]],
        check_lemma_links: bool,
    ) -> str:
        """Build the LLM prompt for sentence translation verification.

        Args:
            english_text: English sentence text
            language_data: Dict of language data with translations and linked lemmas
            check_lemma_links: Whether to include lemma link verification

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "You are a translation verification expert. Your task is to verify whether sentence translations are correct.",
            f'\nEnglish Sentence: "{english_text}"',
            "\n" + "=" * 60,
        ]

        for lang_code, data in language_data.items():
            dialect_name = get_dialect_display_name(lang_code)
            prompt_parts.append(f"\n=== {dialect_name} ({lang_code}) ===")
            prompt_parts.append(f'Translation: "{data["translation"]}"')

            if check_lemma_links and data["linked_lemmas"]:
                prompt_parts.append("\nLinked Lemmas (vocabulary words in this sentence):")
                prompt_parts.append(
                    "| Pos | English Word | Lemma GUID | Expected Translation | Actual Form |"
                )
                prompt_parts.append(
                    "|-----|--------------|------------|---------------------|-------------|"
                )

                for lemma_info in data["linked_lemmas"]:
                    guid = lemma_info["lemma_guid"] or "(none)"
                    expected = lemma_info["expected_translation"] or "(n/a)"
                    actual = lemma_info["declined_form"] or lemma_info["target_text"] or "(n/a)"
                    english = lemma_info["english_text"] or "(n/a)"
                    prompt_parts.append(
                        f"| {lemma_info['position']} | {english} | {guid} | {expected} | {actual} |"
                    )

        prompt_parts.append("\n" + "=" * 60)
        prompt_parts.append("\nFor EACH language translation, verify:")
        prompt_parts.append("1. meaning_correct: Is the overall sentence meaning correct?")
        prompt_parts.append("2. grammar_correct: Is the grammar correct for this language?")

        if check_lemma_links:
            prompt_parts.append("\nFor EACH linked lemma (with a GUID), also verify:")
            prompt_parts.append(
                "3. sense_correct: Is this the right lemma/word sense for the context?"
            )
            prompt_parts.append(
                "4. form_matches: Does the actual form match what's expected for this lemma?"
            )
            prompt_parts.append(
                "   (Note: If a language doesn't use a particular lemma's concept, "
                "and it's not in the translation, that's still 'correct')"
            )

        prompt_parts.append("\nIMPORTANT:")
        prompt_parts.append('- Respond with ONLY "correct" or "incorrect" for each check')
        prompt_parts.append("- Consider the specific dialect indicated")

        return "\n".join(prompt_parts)

    def _build_sentence_verification_schema(
        self, language_codes: List[str], check_lemma_links: bool
    ) -> Schema:
        """Build the response schema for sentence verification.

        Args:
            language_codes: List of language codes being verified
            check_lemma_links: Whether to include lemma check fields

        Returns:
            Schema object for LLM response
        """
        properties = {}

        for lang_code in language_codes:
            dialect_name = get_dialect_display_name(lang_code)

            properties[f"{lang_code}_meaning"] = SchemaProperty(
                type="string",
                description=f'{dialect_name} meaning verification: "correct" or "incorrect"',
                enum=["correct", "incorrect"],
            )
            properties[f"{lang_code}_grammar"] = SchemaProperty(
                type="string",
                description=f'{dialect_name} grammar verification: "correct" or "incorrect"',
                enum=["correct", "incorrect"],
            )

        # Note: For lemma checks, we need to know the GUIDs ahead of time
        # This is handled dynamically in verify_sentence_translations

        return Schema(
            name="SentenceTranslationVerification",
            description="Verification results for sentence translations",
            properties=properties,
        )

    def batch_verify_words(
        self,
        lemmas: List[Lemma],
        languages: Optional[List[str]] = None,
        session: Any = None,
        dry_run: bool = False,
        update_verified_flag: bool = True,
    ) -> Dict[str, Any]:
        """Verify translations for multiple words.

        Args:
            lemmas: List of Lemma objects to verify
            languages: Language codes to verify
            session: Database session
            dry_run: If True, don't update database
            update_verified_flag: If True, update LemmaTranslation.verified flag

        Returns:
            Summary of verification results
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True

        try:
            results = []
            correct_count = 0
            incorrect_count = 0
            error_count = 0

            for i, lemma in enumerate(lemmas, 1):
                logger.info(f"[{i}/{len(lemmas)}] Verifying: {lemma.lemma_text} ({lemma.guid})")

                result = self.verify_word_translations(
                    lemma=lemma, languages=languages, session=session
                )
                results.append(result)

                if result.get("success"):
                    for lang_code, verdict in result.get("results", {}).items():
                        if verdict == "correct":
                            correct_count += 1
                            if update_verified_flag and not dry_run:
                                self._update_translation_verified(
                                    session, lemma.id, lang_code, True
                                )
                        else:
                            incorrect_count += 1
                            # Don't mark as verified if incorrect
                else:
                    error_count += 1

            if not dry_run:
                session.commit()

            return {
                "total_lemmas": len(lemmas),
                "total_translations_checked": correct_count + incorrect_count,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "error_count": error_count,
                "results": results,
            }

        finally:
            if close_session:
                session.close()

    def _update_translation_verified(
        self, session: Any, lemma_id: int, lang_code: str, verified: bool
    ) -> None:
        """Update the verified flag on a LemmaTranslation.

        Args:
            session: Database session
            lemma_id: Lemma ID
            lang_code: Language code
            verified: New verified status
        """
        trans = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma_id,
                LemmaTranslation.language_code == lang_code,
            )
            .first()
        )
        if trans:
            trans.verified = verified

    def batch_verify_sentences(
        self,
        sentences: List[Sentence],
        languages: Optional[List[str]] = None,
        session: Any = None,
        check_lemma_links: bool = True,
        dry_run: bool = False,
        update_verified_flag: bool = True,
    ) -> Dict[str, Any]:
        """Verify translations for multiple sentences.

        Args:
            sentences: List of Sentence objects to verify
            languages: Language codes to verify
            session: Database session
            check_lemma_links: Whether to verify linked lemmas
            dry_run: If True, don't update database
            update_verified_flag: If True, update SentenceTranslation.verified flag

        Returns:
            Summary of verification results
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True

        try:
            results = []
            fully_correct_count = 0
            has_issues_count = 0
            error_count = 0

            for i, sentence in enumerate(sentences, 1):
                logger.info(f"[{i}/{len(sentences)}] Verifying sentence ID: {sentence.id}")

                result = self.verify_sentence_translations(
                    sentence=sentence,
                    languages=languages,
                    session=session,
                    check_lemma_links=check_lemma_links,
                )
                results.append(result)

                if result.get("success"):
                    # Check if all checks passed
                    all_correct = True
                    for lang_code, lang_result in result.get("results", {}).items():
                        if (
                            lang_result.get("meaning_correct") != "correct"
                            or lang_result.get("grammar_correct") != "correct"
                        ):
                            all_correct = False
                            break

                        if check_lemma_links:
                            for lemma_check in lang_result.get("lemma_checks", {}).values():
                                if (
                                    lemma_check.get("sense_correct") != "correct"
                                    or lemma_check.get("form_matches") != "correct"
                                ):
                                    all_correct = False
                                    break

                        if update_verified_flag and not dry_run:
                            # Update verified flag for this translation
                            is_lang_correct = (
                                lang_result.get("meaning_correct") == "correct"
                                and lang_result.get("grammar_correct") == "correct"
                            )
                            self._update_sentence_translation_verified(
                                session, sentence.id, lang_code, is_lang_correct
                            )

                    if all_correct:
                        fully_correct_count += 1
                    else:
                        has_issues_count += 1
                else:
                    error_count += 1

            if not dry_run:
                session.commit()

            return {
                "total_sentences": len(sentences),
                "fully_correct_count": fully_correct_count,
                "has_issues_count": has_issues_count,
                "error_count": error_count,
                "results": results,
            }

        finally:
            if close_session:
                session.close()

    def _update_sentence_translation_verified(
        self, session: Any, sentence_id: int, lang_code: str, verified: bool
    ) -> None:
        """Update the verified flag on a SentenceTranslation.

        Args:
            session: Database session
            sentence_id: Sentence ID
            lang_code: Language code
            verified: New verified status
        """
        trans = (
            session.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence_id,
                SentenceTranslation.language_code == lang_code,
            )
            .first()
        )
        if trans:
            trans.verified = verified

    def submit_batch_word_verification(
        self,
        languages: List[str],
        limit: Optional[int] = None,
        unverified_only: bool = True,
    ) -> Tuple[Optional[str], int]:
        """Submit a batch verification job for word translations.

        Args:
            languages: Languages to verify
            limit: Maximum number of lemmas to verify
            unverified_only: Only verify unverified translations

        Returns:
            Tuple of (batch_id, request_count) or (None, 0) if no requests
        """
        session = self.get_session()
        try:
            # Filter languages
            languages = filter_languages_for_model(languages, self.model)
            if not languages:
                logger.warning(f"No supported languages for model {self.model}")
                return None, 0

            # Build query
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))

            if unverified_only:
                # Only lemmas with unverified translations
                query = (
                    query.join(LemmaTranslation)
                    .filter(
                        LemmaTranslation.verified == False,  # noqa: E712
                        LemmaTranslation.language_code.in_(languages),
                    )
                    .distinct()
                )

            if limit:
                query = query.limit(limit)

            lemmas = query.all()

            if not lemmas:
                logger.warning("No lemmas found for batch verification")
                return None, 0

            requests_queued = 0
            for lemma in lemmas:
                # Get translations for this lemma
                translations: Dict[str, str] = {}
                for lang_code in languages:
                    trans = get_translation(session, lemma, lang_code)
                    if trans and trans.strip():
                        translations[lang_code] = trans

                if not translations:
                    continue

                # Build prompt and schema
                prompt = self._build_word_verification_prompt(lemma, translations)
                schema = self._build_word_verification_schema(list(translations.keys()))

                custom_id = f"verify_word_{lemma.id}"

                # Build response format
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.name,
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                f"{key}_verdict": {
                                    "type": "string",
                                    "enum": ["correct", "incorrect"],
                                }
                                for key in translations.keys()
                            },
                            "required": [f"{key}_verdict" for key in translations.keys()],
                            "additionalProperties": False,
                        },
                    },
                }

                request_body = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": response_format,
                }

                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name="bebras_verify",
                    operation_type="verify_word",
                    entity_id=lemma.id,
                    entity_type="lemma",
                )

                try:
                    self.batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions",
                    )
                    requests_queued += 1
                except ValueError as e:
                    logger.debug("Skipping lemma %s: %s", lemma.guid, e)

            logger.info("Queued %s word verification requests", requests_queued)

            if requests_queued > 0:
                pending_requests = self.batch_manager.get_pending_requests(
                    agent_name="bebras_verify", operation_type="verify_word"
                )
                batch_id, _ = self.batch_manager.submit_batch(
                    pending_requests,
                    batch_metadata={
                        "agent": "bebras_verify",
                        "operation": "verify_words",
                    },
                )
                logger.info(
                    "Submitted batch %s with %s requests",
                    batch_id,
                    len(pending_requests),
                )
                return batch_id, len(pending_requests)

            return None, 0

        finally:
            session.close()

    def submit_batch_sentence_verification(
        self,
        languages: List[str],
        limit: Optional[int] = None,
        unverified_only: bool = True,
        check_lemma_links: bool = True,
    ) -> Tuple[Optional[str], int]:
        """Submit a batch verification job for sentence translations.

        Args:
            languages: Languages to verify
            limit: Maximum number of sentences to verify
            unverified_only: Only verify unverified translations
            check_lemma_links: Whether to check linked lemmas

        Returns:
            Tuple of (batch_id, request_count) or (None, 0) if no requests
        """
        session = self.get_session()
        try:
            # Filter languages
            languages = filter_languages_for_model(languages, self.model)
            if not languages:
                logger.warning(f"No supported languages for model {self.model}")
                return None, 0

            # Build query
            query = session.query(Sentence)

            if unverified_only:
                # Only sentences with unverified translations
                query = (
                    query.join(SentenceTranslation)
                    .filter(
                        SentenceTranslation.verified == False,  # noqa: E712
                        SentenceTranslation.language_code.in_(languages),
                    )
                    .distinct()
                )

            if limit:
                query = query.limit(limit)

            sentences = query.all()

            if not sentences:
                logger.warning("No sentences found for batch verification")
                return None, 0

            requests_queued = 0
            for sentence in sentences:
                # Get English sentence
                english_trans = (
                    session.query(SentenceTranslation)
                    .filter(
                        SentenceTranslation.sentence_id == sentence.id,
                        SentenceTranslation.language_code == "en",
                    )
                    .first()
                )

                if not english_trans:
                    continue

                english_text = english_trans.translation_text

                # Gather language data
                language_data: Dict[str, Dict[str, Any]] = {}
                for lang_code in languages:
                    trans = (
                        session.query(SentenceTranslation)
                        .filter(
                            SentenceTranslation.sentence_id == sentence.id,
                            SentenceTranslation.language_code == lang_code,
                        )
                        .first()
                    )

                    if not trans:
                        continue

                    sentence_words = (
                        session.query(SentenceWord)
                        .filter(
                            SentenceWord.sentence_id == sentence.id,
                            SentenceWord.language_code == lang_code,
                        )
                        .order_by(SentenceWord.position)
                        .all()
                    )

                    linked_lemmas = []
                    for sw in sentence_words:
                        lemma_info: Dict[str, Any] = {
                            "position": sw.position,
                            "english_text": sw.english_text,
                            "target_text": sw.target_language_text,
                            "declined_form": sw.declined_form,
                            "word_role": sw.word_role,
                            "lemma_guid": None,
                            "expected_translation": None,
                        }

                        if sw.lemma:
                            lemma_info["lemma_guid"] = sw.lemma.guid
                            lemma_trans = get_translation(session, sw.lemma, lang_code)
                            lemma_info["expected_translation"] = lemma_trans

                        linked_lemmas.append(lemma_info)

                    language_data[lang_code] = {
                        "translation": trans.translation_text,
                        "linked_lemmas": linked_lemmas,
                    }

                if not language_data:
                    continue

                # Build prompt
                prompt = self._build_sentence_verification_prompt(
                    english_text, language_data, check_lemma_links
                )

                custom_id = f"verify_sentence_{sentence.id}"

                # Build response format (simplified - no lemma checks in batch for now)
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceVerification",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                f"{lang_code}_meaning": {
                                    "type": "string",
                                    "enum": ["correct", "incorrect"],
                                }
                                for lang_code in language_data.keys()
                            }
                            | {
                                f"{lang_code}_grammar": {
                                    "type": "string",
                                    "enum": ["correct", "incorrect"],
                                }
                                for lang_code in language_data.keys()
                            },
                            "required": [
                                f"{lang_code}_{check}"
                                for lang_code in language_data.keys()
                                for check in ["meaning", "grammar"]
                            ],
                            "additionalProperties": False,
                        },
                    },
                }

                request_body = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": response_format,
                }

                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name="bebras_verify",
                    operation_type="verify_sentence",
                    entity_id=sentence.id,
                    entity_type="sentence",
                )

                try:
                    self.batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions",
                    )
                    requests_queued += 1
                except ValueError as e:
                    logger.debug("Skipping sentence %s: %s", sentence.id, e)

            logger.info("Queued %s sentence verification requests", requests_queued)

            if requests_queued > 0:
                pending_requests = self.batch_manager.get_pending_requests(
                    agent_name="bebras_verify", operation_type="verify_sentence"
                )
                batch_id, _ = self.batch_manager.submit_batch(
                    pending_requests,
                    batch_metadata={
                        "agent": "bebras_verify",
                        "operation": "verify_sentences",
                    },
                )
                logger.info(
                    "Submitted batch %s with %s requests",
                    batch_id,
                    len(pending_requests),
                )
                return batch_id, len(pending_requests)

            return None, 0

        finally:
            session.close()
