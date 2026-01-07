"""Handlers that execute Barsukas background tasks."""

from __future__ import annotations

from typing import Dict

from config import Config

import constants
from agents.papuga import PapugaAgent
from agents.sernas.agent import SernasAgent
from agents.vilkas.agent import VilkasAgent
from agents.voras.agent import VorasAgent
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS, get_reference_translation
from wordfreq.translation.client import LinguisticClient


def _build_config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def handle_add_missing_translations(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    config = _build_config()
    agent = VorasAgent(config=config)

    missing_languages = []
    for lc in LANGUAGE_FIELDS.keys():
        translation = agent.get_translation(session, lemma, lc)
        if not translation or not translation.strip():
            missing_languages.append(lc)

    if not missing_languages:
        return "No missing translations to generate"

    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=missing_languages
    )

    client = LinguisticClient(
        model=agent.config.model, db_path=config.sqlite_path, debug=Config.DEBUG
    )
    lang_code_to_name = {
        "zh": "chinese",
        "ko": "korean",
        "fr": "french",
        "es": "spanish",
        "de": "german",
        "pt": "portuguese",
        "sw": "swahili",
        "vi": "vietnamese",
        "lt": "lithuanian",
    }
    missing_lang_names = [
        lang_code_to_name[lang_code]
        for lang_code in missing_languages
        if lang_code in lang_code_to_name
    ]
    if not missing_lang_names:
        return "No supported languages to generate"

    if reference_translation:
        translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(reference_lang_code, reference_translation),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=missing_lang_names,
        )
    else:
        translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=("en", lemma.lemma_text),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=missing_lang_names,
        )

    if not success or not translations:
        raise RuntimeError("LLM could not generate translations")

    translation_field_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "es": "spanish_translation",
        "de": "german_translation",
        "pt": "portuguese_translation",
        "sw": "swahili_translation",
        "vi": "vietnamese_translation",
        "lt": "lithuanian_translation",
    }

    added_count = 0
    for lang_code in missing_languages:
        llm_field = translation_field_map.get(lang_code)
        translation = translations.get(llm_field, "").strip()
        if translation:
            agent.set_translation(session, lemma, lang_code, translation)
            added_count += 1

    session.commit()
    return f"Added {added_count} translation(s)"


def handle_generate_pronunciations(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "en")

    from wordfreq.storage.models.schema import (
        DerivativeForm,
        Sentence,
        SentenceTranslation,
        SentenceWord,
    )

    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    forms_missing_pronunciations = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == lang_code,
            DerivativeForm.ipa_pronunciation.is_(None),
            DerivativeForm.phonetic_pronunciation.is_(None),
        )
        .all()
    )

    if not forms_missing_pronunciations:
        return f"No missing pronunciations for {lang_code} forms"

    agent = PapugaAgent(config=_build_config())

    from wordfreq.tools.llm_validators import generate_pronunciation

    generated_count = 0
    for form in forms_missing_pronunciations:
        example_translation = (
            session.query(SentenceTranslation)
            .join(Sentence)
            .join(SentenceWord)
            .filter(
                SentenceWord.lemma_id == lemma_id,
                SentenceTranslation.language_code == "en",
            )
            .first()
        )
        example_text = example_translation.translation_text if example_translation else None

        result = generate_pronunciation(
            word=form.derivative_form_text,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text,
            example_sentence=example_text,
            model=constants.DEFAULT_MODEL,
        )

        if result.get("ipa_pronunciation"):
            form.ipa_pronunciation = result["ipa_pronunciation"]
        if result.get("phonetic_pronunciation"):
            form.phonetic_pronunciation = result["phonetic_pronunciation"]

        if result.get("ipa_pronunciation") or result.get("phonetic_pronunciation"):
            generated_count += 1

    session.commit()
    return f"Generated pronunciations for {generated_count} form(s)"


def handle_generate_forms(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "lt")
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    if not lemma.guid:
        raise ValueError("Lemma is missing a GUID")

    pos_type = lemma.pos_type
    config = _build_config()
    agent = VilkasAgent(config=config)

    supported_languages = {
        "lt": ["noun", "verb", "adjective"],
        "fr": ["noun", "verb"],
        "de": ["noun", "verb"],
        "es": ["noun", "verb"],
        "pt": ["noun", "verb"],
        "en": ["noun", "verb", "adjective", "adverb"],
    }

    if lang_code not in supported_languages:
        raise ValueError(f"Language {lang_code} not supported for form generation")

    if pos_type not in supported_languages[lang_code]:
        raise ValueError(f"POS type {pos_type} not supported for {lang_code}")

    translation = None
    if lang_code in LANGUAGE_FIELDS:
        field_name, _, uses_table = LANGUAGE_FIELDS[lang_code]
        if uses_table:
            from wordfreq.storage.models.schema import LemmaTranslation

            trans_obj = (
                session.query(LemmaTranslation)
                .filter(
                    LemmaTranslation.lemma_id == lemma_id,
                    LemmaTranslation.language_code == lang_code,
                )
                .first()
            )
            translation = trans_obj.translation if trans_obj else None
        else:
            translation = getattr(lemma, field_name, None)

    if not translation or not translation.strip():
        raise ValueError(f"No {lang_code} translation found")

    from wordfreq.translation.generate_forms_tasks import get_task_key

    client = LinguisticClient(config=config)
    task_key = get_task_key(lang_code, pos_type)

    success = agent.generate_forms_for_lemma(
        lemma_guid=lemma.guid,
        language_code=lang_code,
        pos_type=pos_type,
        client=client,
    )

    session.commit()
    if success:
        return f"Generated {lang_code} {pos_type} forms"
    raise RuntimeError(f"Could not generate {lang_code} {pos_type} forms")


def handle_generate_synonyms(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "en")
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    if lang_code != "en":
        from wordfreq.storage.translation_helpers import get_translation

        translation = get_translation(session, lemma, lang_code)
        if not translation or not translation.strip():
            raise ValueError(f"No {lang_code} translation found for this lemma")

    agent = SernasAgent(config=_build_config())
    result = agent.generate_synonyms_for_lemma(
        lemma_id=lemma_id, language_code=lang_code, model=constants.DEFAULT_MODEL, dry_run=False
    )

    if "error" in result:
        raise RuntimeError(result["error"])

    synonyms_count = result.get("stored_synonyms", 0)
    alternatives_count = (
        result.get("stored_abbreviations", 0)
        + result.get("stored_expanded", 0)
        + result.get("stored_spellings", 0)
        + result.get("stored_alternatives", 0)
    )
    session.commit()
    return f"Stored {synonyms_count} synonym(s) and {alternatives_count} alternative form(s)"


TASK_HANDLERS = {
    "add_missing_translations": handle_add_missing_translations,
    "generate_pronunciations": handle_generate_pronunciations,
    "generate_forms": handle_generate_forms,
    "generate_synonyms": handle_generate_synonyms,
}
