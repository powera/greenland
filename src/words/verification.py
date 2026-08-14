"""Standalone verification for stored word translations.

The service mutates rows in the caller-owned SQLAlchemy session but deliberately
does not commit. Callers can therefore run one verification atomically with
their surrounding work, while the workqueue commits on successful completion.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict

from sqlalchemy.orm import Session

from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import get_translation
from verification.common import (
    DEFAULT_VERIFY_LANGUAGES,
    filter_languages_for_model,
    get_dialect_display_name,
    parse_verdict,
)

VerificationVerdict = Literal["correct", "incorrect"]


class WordTranslationVerificationResult(TypedDict):
    """Result of checking all available requested translations for one lemma."""

    lemma_guid: Optional[str]
    lemma_text: str
    definition: Optional[str]
    pos_type: str
    translations_checked: Dict[str, str]
    results: Dict[str, VerificationVerdict]
    success: Literal[True]


def build_word_verification_prompt(lemma: Lemma, translations: Dict[str, str]) -> str:
    """Build the LLM prompt for one lemma's translations."""
    disambiguation = f'\nDisambiguation: "{lemma.disambiguation}"' if lemma.disambiguation else ""
    translation_lines = [
        f"- {get_dialect_display_name(language_code)} ({language_code}): {translation_text}"
        for language_code, translation_text in translations.items()
    ]
    translations_text = "\n".join(translation_lines)
    return f"""You are a translation verification expert. Verify whether each translation is correct.

Word: "{lemma.lemma_text}" ({lemma.pos_type})
Definition: "{lemma.definition_text}"{disambiguation}

Translations to verify:
{translations_text}

For EACH translation, determine whether it correctly translates the English word in the given sense.

IMPORTANT:
- Respond with ONLY "correct" or "incorrect" for each translation.
- Mark a wrong meaning, spelling, word sense, dialect, or non-lemma form incorrect.
"""


def build_word_verification_schema(language_codes: List[str]) -> Schema:
    """Build the structured response schema for word verification."""
    properties = {
        f"{language_code}_verdict": SchemaProperty(
            type="string",
            description=(f"{get_dialect_display_name(language_code)} translation verdict"),
            enum=["correct", "incorrect"],
        )
        for language_code in language_codes
    }
    return Schema(
        name="WordTranslationVerification",
        description="Verification results for word translations",
        properties=properties,
    )


def verify_word_translations(
    session: Session,
    lemma_id: int,
    config: DataSourceConfig,
    languages: Optional[List[str]] = None,
    *,
    persist: bool = True,
    llm_client: Optional[UnifiedLLMClient] = None,
) -> WordTranslationVerificationResult:
    """Verify and optionally persist verdicts for one lemma.

    ``persist`` updates ``LemmaTranslation.verified`` for every checked row,
    including resetting a formerly verified translation when it is incorrect.
    The caller owns commit and rollback.
    """
    lemma = session.get(Lemma, lemma_id)
    if lemma is None:
        raise ValueError(f"Lemma {lemma_id} not found")

    model = config.model or "gpt-5.4-mini"
    requested_languages = languages or DEFAULT_VERIFY_LANGUAGES
    supported_languages = filter_languages_for_model(requested_languages, model)
    if not supported_languages:
        raise ValueError(f"No supported verification languages for model {model}")

    translations: Dict[str, str] = {}
    translation_rows: Dict[str, LemmaTranslation] = {}
    for language_code in supported_languages:
        translation_text = get_translation(session, lemma, language_code)
        if not translation_text or not translation_text.strip():
            continue
        translation_row = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .one()
        )
        translations[language_code] = translation_text
        translation_rows[language_code] = translation_row

    if not translations:
        raise ValueError("No translations found for requested languages")

    client = llm_client or UnifiedLLMClient.from_config(config)
    response = client.generate_chat(
        prompt=build_word_verification_prompt(lemma, translations),
        json_schema=build_word_verification_schema(list(translations)),
        timeout=60,
    )
    if not response.structured_data:
        raise RuntimeError("LLM did not return structured word verification data")

    verdicts: Dict[str, VerificationVerdict] = {
        language_code: parse_verdict(response.structured_data.get(f"{language_code}_verdict"))
        for language_code in translations
    }
    if persist:
        for language_code, verdict in verdicts.items():
            translation_rows[language_code].verified = verdict == "correct"
        session.flush()

    return {
        "lemma_guid": lemma.guid,
        "lemma_text": lemma.lemma_text,
        "definition": lemma.definition_text,
        "pos_type": lemma.pos_type,
        "translations_checked": translations,
        "results": verdicts,
        "success": True,
    }
