"""Identity-preserving name renderings and Lithuanian singular inflections."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Sequence

from sqlalchemy.orm import Session

import constants
from clients.unified_client import UnifiedLLMClient
from langtools.lt.forms_config import CASES
from storage.backend.config import DataSourceConfig
from storage.crud.name_entity import add_name_derivative_form, set_name_translation
from storage.models.name_entity import Name
from storage.crud.uncertain_llm_result import DEFAULT_MIN_CONFIDENCE
from storage.translation_helpers import get_supported_languages, split_llm_language_batches

logger = logging.getLogger(__name__)


def name_form_slots(language_code: str) -> list[str]:
    """Return the persisted slots requested for a language's name rendering."""
    if language_code == "lt":
        return [f"noun/lt_{case}_singular" for case in CASES]
    return [f"noun/{language_code}_base"]


def pending_name_languages(name: Name, languages: Sequence[str]) -> list[str]:
    """Select missing renderings and incomplete Lithuanian paradigms."""
    renderings = {row.language_code: row.translation for row in name.translations}
    lithuanian_slots = {
        row.grammatical_form for row in name.derivative_forms if row.language_code == "lt"
    }
    return [
        code
        for code in languages
        if not renderings.get(code)
        or (code == "lt" and not set(name_form_slots(code)).issubset(lithuanian_slots))
    ]


def build_name_translation_prompt(
    name: Name, languages: Sequence[str], *, regenerate: bool = False
) -> tuple[str, str, dict[str, Any]]:
    """Build a structured name request, retaining existing bases during population."""
    language_names = get_supported_languages()
    existing = {row.language_code: row.translation for row in name.translations}
    properties: dict[str, Any] = {}
    instructions = [
        f"Source name (English): {json.dumps(name.name_text, ensure_ascii=False)}",
        f"Name kind: {name.kind} ({name.kind_label}). Gender hint: {name.gender or 'unknown'}.",
        f"Context: {name.disambiguation or ''}. Notes: {name.notes or ''}",
        "Preserve this person's identity and source pronunciation. Render the SAME name in each "
        "target language's conventional spelling/script; do not substitute a local equivalent, "
        "etymological cognate, translated meaning, or a different person's name.",
        "For example English John in Russian is Джон, NEVER Иван; George is Джордж, not Георгий. "
        "Use target-script transliteration where appropriate, retaining spelling where customary.",
        "Treat given names and family names according to their stated kind. Do not add titles, "
        "invent gender, or turn an unspecified surname into a married/gendered surname.",
        "For Lithuanian give all seven singular cases, including vocative, of the SAME rendering. "
        "Use normal Lithuanian adaptation and declension of foreign names where appropriate. "
        "For indeclinable names repeat the unchanged rendering in every case. Do not invent plurals.",
        "Return confidence from 0 to 1 for each language; use low confidence if gender or spelling "
        "is too ambiguous to supply a reliable rendering and paradigm.",
    ]
    for language_code in languages:
        slots = name_form_slots(language_code)
        instructions.append(
            f"{language_code}: {language_names.get(language_code, language_code)}; slots: {', '.join(slots)}"
        )
        if not regenerate and existing.get(language_code):
            instructions.append(
                f"Keep the existing {language_code} base EXACTLY: "
                f"{json.dumps(existing[language_code], ensure_ascii=False)}; fill its missing forms."
            )
        properties[language_code] = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "forms": {
                    "type": "object",
                    "properties": {slot: {"type": "string"} for slot in slots},
                    "required": slots,
                    "additionalProperties": False,
                },
            },
            "required": ["translation", "confidence", "forms"],
            "additionalProperties": False,
        }
    return (
        "You render proper names for multilingual language-learning texts. Preserve identity.",
        "\n".join(instructions),
        {
            "type": "object",
            "properties": properties,
            "required": list(languages),
            "additionalProperties": False,
        },
    )


def store_name_translation_answer(
    session: Session,
    name: Name,
    language_code: str,
    answer: Any,
    *,
    regenerate: bool = False,
) -> bool:
    """Validate a complete language before writing; keep uncertain answers untouched."""
    if not isinstance(answer, dict):
        raise ValueError(f"Missing {language_code} answer")
    confidence = answer.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"Invalid {language_code} confidence")
    if not 0 <= confidence <= 1:
        raise ValueError(f"Invalid {language_code} confidence")
    if confidence < DEFAULT_MIN_CONFIDENCE:
        return False
    rendering = answer.get("translation")
    forms = answer.get("forms")
    if not isinstance(rendering, str) or not rendering.strip() or not isinstance(forms, dict):
        raise ValueError(f"Invalid {language_code} rendering/forms")
    rendering = rendering.strip()
    slots = name_form_slots(language_code)
    if set(forms) != set(slots) or any(
        not isinstance(value, str) or not value.strip() for value in forms.values()
    ):
        raise ValueError(f"Incomplete {language_code} name forms")
    base_slot = "noun/lt_nominative_singular" if language_code == "lt" else slots[0]
    if forms[base_slot].strip() != rendering:
        raise ValueError(f"{language_code} base form differs from rendering")
    existing = next((row for row in name.translations if row.language_code == language_code), None)
    if existing is not None and not regenerate and existing.translation != rendering:
        raise ValueError(f"Population cannot replace existing {language_code} rendering")
    if existing is None or regenerate:
        set_name_translation(
            session, name, language_code=language_code, translation=rendering, source="voras"
        )
    for old_form in list(name.derivative_forms):
        if old_form.language_code != language_code:
            continue
        # Population keeps curated forms and fills only missing slots.
        if regenerate:
            session.delete(old_form)
    session.flush()
    if regenerate:
        session.expire(name, ["derivative_forms"])
    occupied = {
        row.grammatical_form for row in name.derivative_forms if row.language_code == language_code
    }
    for grammatical_form in slots:
        if grammatical_form in occupied:
            continue
        add_name_derivative_form(
            session,
            name,
            derivative_form_text=forms[grammatical_form].strip(),
            language_code=language_code,
            grammatical_form=grammatical_form,
            is_base_form=grammatical_form == base_slot,
            source="voras",
        )
    session.expire(name, ["translations", "derivative_forms"])
    return True


def translate_name(
    session: Session,
    name: Name,
    languages: Sequence[str],
    *,
    config: DataSourceConfig,
    regenerate: bool = False,
    client: UnifiedLLMClient | None = None,
    throttle: float = 0.0,
) -> bool:
    """Translate and commit each language independently, retaining paid successful results."""
    targets = list(languages) if regenerate else pending_name_languages(name, languages)
    if not targets:
        return True
    translation_client = client or UnifiedLLMClient.from_config(config)
    succeeded = True
    for batch_index, language_batch in enumerate(split_llm_language_batches(targets)):
        if batch_index and throttle > 0:
            time.sleep(throttle)
        context, prompt, schema = build_name_translation_prompt(
            name, language_batch, regenerate=regenerate
        )
        try:
            response = translation_client.generate_chat(
                prompt=prompt,
                context=context,
                json_schema=schema,
                model=config.model or constants.DEFAULT_MODEL,
            )
            data = response.structured_data
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict):
                raise ValueError("Name translation response must be an object")
        except Exception:
            logger.exception("Name translation failed for %s (%s)", name.guid, language_batch)
            succeeded = False
            continue
        for language_code in language_batch:
            try:
                written = store_name_translation_answer(
                    session, name, language_code, data.get(language_code), regenerate=regenerate
                )
                session.commit()
                if not written:
                    logger.warning("Uncertain name translation: %s %s", name.guid, language_code)
                    succeeded = False
            except Exception:
                session.rollback()
                logger.exception("Cannot save name translation: %s %s", name.guid, language_code)
                succeeded = False
    return succeeded
