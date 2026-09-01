#!/usr/bin/env python3
"""
Dialect override definitions for language variants.

This module provides a centralized registry of dialect variants (e.g., zh-tw,
es-419, pt-br) and their relationships to parent languages.  It defines:

- Parent language mappings  (zh-tw -> zh, es-419 -> es, etc.)
- Display names with dialect qualifiers for use in LLM prompts
- Per-dialect script normalizers (e.g., repairing a mis-scripted zh-tw row)
- Sort-key language inheritance (dialects typically reuse the parent's sort key)
- TTS locale codes for speech synthesis
- Whether a dialect is stored separately or folded into another variant

Import from this module rather than hardcoding dialect information locally.

Two kinds of dialect live here, told apart by ``translation_target``:

* **Storage dialects** (``translation_target=True``: zh-tw, es-419, pt-br) get
  their own ``LemmaTranslation`` rows, their own LLM prompt configuration, and
  their own release/export column.  Adding one means registering it here *and*
  in ``storage.translation_helpers.LANGUAGE_FIELDS`` /
  ``wordfreq.translation.constants.DEFAULT_TRANSLATION_LANGUAGES``.
* **Presentation dialects** (``translation_target=False``: es-mx, fr-ca, en-gb)
  carry a prompt note and a TTS locale but store no separate text.  Their
  ``covered_by`` (falling back to ``parent_lang``) names the variant whose
  stored translations they read.  es-mx is the worked example: Mexican Spanish
  differs from neutral Latin American Spanish mostly in colloquial register,
  which lemma-level vocabulary rarely reaches, so it reads es-419 text and only
  contributes an accent for TTS.

Overlap between two storage dialects is stored rather than resolved: es and
es-419 hold the same word for most entries, and both rows carry it.  Nothing
here falls back from a dialect to its parent at read time -- a missing
translation means "not generated yet", not "use the parent's".
``get_dialects_reading`` is the inverse of ``get_translation_language``, for
the things keyed by the language a word is written in (audio, chiefly) that
have to follow the text outward.

Usage::

    from langtools.dialect_overrides import (
        is_dialect,
        get_parent_language,
        get_dialect_display_name,
        normalize_dialect_script,
    )

    if is_dialect("zh-tw"):
        parent = get_parent_language("zh-tw")   # "zh"
        name   = get_dialect_display_name("zh-tw")  # "Chinese (Taiwan Traditional)"

A storage dialect's text is generated and stored per variant, never derived from
its parent -- including zh-tw, where OpenCC could convert the script but would
still carry Mainland vocabulary (軟體 vs 軟件).  ``normalize_dialect_script``
is therefore scoped to a dialect's *own* rows: it repairs one stored in the
wrong script and leaves a blank row blank.  There is no forward parent-to-
dialect transform, and adding one would reintroduce exactly that fallback.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text transformation helpers (lazy-loaded to avoid import-time failures)
# ---------------------------------------------------------------------------


def _zh_simplified_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese."""
    from langtools.zh.converter import to_traditional

    return to_traditional(text)


def _zh_traditional_to_simplified(text: str) -> str:
    """Convert Traditional Chinese to Simplified Chinese."""
    from langtools.zh.converter import to_simplified

    return to_simplified(text)


# ---------------------------------------------------------------------------
# DialectOverride dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DialectOverride:
    """Configuration for a dialect variant of a language.

    Attributes:
        parent_lang: Base language code this dialect derives from (e.g. ``"zh"``).
        display_name: Short display name (e.g. ``"Chinese (Taiwan)"``).
        dialect_display_name: Longer name suitable for LLM prompts that
            clarifies the specific variant (e.g. ``"Chinese (Taiwan Traditional)"``).
        script_normalizer: Optional callable that normalizes text **already
            stored for this dialect** into the script the dialect writes.  For
            example, zh-tw's normalizer converts Simplified characters to
            Traditional, repairing a row that was imported in the wrong script.
            It is deliberately *not* a way to derive this dialect's text from
            its parent's: it runs only on the dialect's own rows, and a blank
            row stays blank.  ``None`` means the stored text is used as-is.
        reverse_transform: Optional callable that converts text **from this
            dialect back to the parent** language.  For example, zh-tw's
            reverse converts Traditional Chinese to Simplified.  ``None``
            means no reverse conversion is available.
        sort_key_lang: Language code whose sort-key logic should be used.
            ``None`` means inherit from *parent_lang*.
        tts_locale: BCP-47 locale tag for text-to-speech engines
            (e.g. ``"zh-TW"``, ``"es-MX"``).  ``None`` means no specific
            TTS locale is defined.
        llm_prompt_note: Optional extra instruction to include in LLM prompts
            when generating or verifying content for this dialect.
        translation_target: Whether this dialect stores its own translations.
            ``True`` means it is a first-class generation/storage language and
            must also appear in ``LANGUAGE_FIELDS`` and
            ``DEFAULT_TRANSLATION_LANGUAGES``.  ``False`` means it only supplies
            a prompt note and a TTS locale, and reads *covered_by*'s text.
        covered_by: For a non-storage dialect, the language code whose stored
            translations it reads (e.g. es-mx reads es-419).  ``None`` means
            fall back to *parent_lang*.  Ignored when *translation_target* is
            ``True``.
        variant_name: Learner-facing name of the *region*, in the source
            language, for the client's variant picker: "Latin America", not
            "Spanish (Latin America)".  The picker sits inside an already
            chosen language, so repeating the language name there is noise.
            ``None`` means the dialect is not offered as a pickable variant.
        variant_native_name: The same regional name written in the target
            language ("Español de Latinoamérica").
        variant_description: One jargon-free sentence shown under the option.
        variant_flag: Emoji shown on the option row.
        variant_regions: ISO 3166-1 alpha-2 regions that select this variant by
            default.  A region should appear under at most one variant of a
            language.
        speech_locale: Locale the *client* passes to on-device TTS and speech
            recognition when the variant's own tag is not a locale those APIs
            accept (es-419 is not).  This is a client-side hint only and names
            no recording we ship -- it is deliberately separate from
            *tts_locale*, which is what our own audio pipeline records with.
            ``None`` means the client uses the variant's language code.
    """

    parent_lang: str
    display_name: str
    dialect_display_name: str
    script_normalizer: Optional[Callable[[str], str]] = field(default=None, repr=False)
    reverse_transform: Optional[Callable[[str], str]] = field(default=None, repr=False)
    sort_key_lang: Optional[str] = None
    tts_locale: Optional[str] = None
    llm_prompt_note: Optional[str] = None
    translation_target: bool = False
    covered_by: Optional[str] = None
    variant_name: Optional[str] = None
    variant_native_name: Optional[str] = None
    variant_description: Optional[str] = None
    variant_flag: Optional[str] = None
    variant_regions: List[str] = field(default_factory=list)
    speech_locale: Optional[str] = None


# ---------------------------------------------------------------------------
# Dialect registry
# ---------------------------------------------------------------------------

DIALECT_OVERRIDES: Dict[str, DialectOverride] = {
    # Chinese (Taiwan) - Traditional characters
    "zh-tw": DialectOverride(
        parent_lang="zh",
        display_name="Chinese (Taiwan)",
        dialect_display_name="Chinese (Taiwan Traditional)",
        # Repairs a zh-tw row that was imported holding Simplified characters.
        # This runs only on text already stored for zh-tw; it is never a way to
        # fill a blank zh-tw row from zh.  OpenCC gets the script right but not
        # the word (軟體 vs 軟件), so deriving would quietly ship Mainland
        # vocabulary in Traditional characters.
        script_normalizer=_zh_simplified_to_traditional,
        reverse_transform=_zh_traditional_to_simplified,
        sort_key_lang="zh",  # pinyin sort keys work for both variants
        tts_locale="zh-TW",
        llm_prompt_note=(
            "Use Traditional Chinese characters as used in Taiwan. "
            "Do NOT use Simplified Chinese characters."
        ),
        translation_target=True,
        variant_name="Taiwan",
        variant_native_name="臺灣正體",
        variant_description=("Traditional characters and vocabulary as used in Taiwan."),
        variant_flag="🇹🇼",
        # HK and MO also write Traditional, but their vocabulary is Cantonese-
        # influenced and not what this bundle holds; they stay on the base
        # variant until there is a zh-hk to send them to.
        variant_regions=["TW"],
        speech_locale="zh-TW",
    ),
    # Spanish (Latin America) - the neutral pan-regional standard.  This is the
    # variety US classroom Spanish teaches, so it is a storage dialect even
    # though the country-specific varieties below it are not.
    "es-419": DialectOverride(
        parent_lang="es",
        display_name="Spanish (Latin America)",
        dialect_display_name="Spanish (Latin American)",
        script_normalizer=None,  # text is the same script
        reverse_transform=None,
        sort_key_lang="es",
        # es-419 is not a locale any TTS engine offers; es-US is the neutral
        # Latin American voice Google, Azure, and Polly all expose.
        tts_locale="es-US",
        llm_prompt_note=(
            "Use neutral Latin American Spanish (español latinoamericano), the "
            "pan-regional standard used for dubbing and textbooks, not the "
            "Spanish of any single country. Use 'ustedes' for the second-person "
            "plural and never 'vosotros'. Prefer vocabulary understood across "
            "Latin America over Peninsular-only terms (e.g. 'computadora' not "
            "'ordenador', 'carro'/'auto' not 'coche', 'jugo' not 'zumo', "
            "'papa' not 'patata'). Avoid country-specific slang."
        ),
        translation_target=True,
        variant_name="Latin America",
        variant_native_name="Español de Latinoamérica",
        variant_description=(
            "Vocabulary and pronunciation as used in Mexico, Colombia, "
            "Argentina and the rest of Latin America."
        ),
        variant_flag="🌎",
        # Spanish-speaking Latin America, plus US (where classroom and
        # community Spanish is the Latin American standard, not Peninsular).
        variant_regions=[
            "MX",
            "CO",
            "AR",
            "PE",
            "VE",
            "CL",
            "EC",
            "GT",
            "CU",
            "BO",
            "DO",
            "HN",
            "PY",
            "SV",
            "NI",
            "CR",
            "PA",
            "UY",
            "PR",
            "US",
        ],
        # es-MX, not the es-US of tts_locale: this is the accent the client
        # asks the device to speak in, and es-MX is the Latin American voice
        # every mobile OS ships.  We record no audio for either locale today.
        speech_locale="es-MX",
    ),
    # Spanish (Mexico) - a regional accent within Latin American Spanish.
    # Not stored separately: at lemma level its vocabulary is es-419's, so it
    # reads es-419 text and contributes only a voice locale and prompt note.
    "es-mx": DialectOverride(
        parent_lang="es",
        display_name="Spanish (Mexico)",
        dialect_display_name="Spanish (Mexican)",
        script_normalizer=None,  # text is the same script
        reverse_transform=None,
        sort_key_lang="es",
        tts_locale="es-MX",
        llm_prompt_note=(
            "Use Mexican Spanish. Prefer 'ustedes' over 'vosotros'. "
            "Use Latin American vocabulary where it differs from Castilian Spanish."
        ),
        translation_target=False,
        covered_by="es-419",
    ),
    # Portuguese (Brazil) - Brazilian Portuguese
    "pt-br": DialectOverride(
        parent_lang="pt",
        display_name="Portuguese (Brazil)",
        dialect_display_name="Portuguese (Brazilian)",
        script_normalizer=None,  # text is the same script
        reverse_transform=None,
        sort_key_lang="pt",
        tts_locale="pt-BR",
        llm_prompt_note=(
            "Use Brazilian Portuguese. Prefer Brazilian vocabulary and spelling "
            "conventions where they differ from European Portuguese (e.g. "
            "'ônibus' not 'autocarro', 'trem' not 'comboio', 'celular' not "
            "'telemóvel'). Use 'você' rather than 'tu' for the second person."
        ),
        translation_target=True,
        variant_name="Brazil",
        variant_native_name="Português do Brasil",
        variant_description="Vocabulary and pronunciation as used in Brazil.",
        variant_flag="🇧🇷",
        variant_regions=["BR"],
        speech_locale="pt-BR",
    ),
    # French (Canada) - Canadian French
    "fr-ca": DialectOverride(
        parent_lang="fr",
        display_name="French (Canada)",
        dialect_display_name="French (Canadian)",
        script_normalizer=None,
        reverse_transform=None,
        sort_key_lang="fr",
        tts_locale="fr-CA",
        llm_prompt_note=(
            "Use Canadian French (québécois standard). Prefer Canadian vocabulary "
            "where it differs from Metropolitan French."
        ),
        translation_target=False,
    ),
    # English (UK) - British English
    "en-gb": DialectOverride(
        parent_lang="en",
        display_name="English (UK)",
        dialect_display_name="English (British)",
        script_normalizer=None,
        reverse_transform=None,
        sort_key_lang=None,  # English has no special sort key
        tts_locale="en-GB",
        llm_prompt_note=(
            "Use British English spelling (e.g. 'colour', 'favourite', "
            "'organise') and vocabulary."
        ),
        translation_target=False,
    ),
}


# Pre-computed reverse index: parent_lang -> list of dialect codes
_PARENT_TO_DIALECTS: Dict[str, List[str]] = {}
for _dialect_code, _override in DIALECT_OVERRIDES.items():
    _PARENT_TO_DIALECTS.setdefault(_override.parent_lang, []).append(_dialect_code)


# Spellings of a dialect that are not the canonical registry key.  BCP-47 tags
# people actually type (``pt-BR``), Android-style underscores (``zh_TW``), and
# the region tags that mean the same variety we already register.
_CODE_ALIASES: Dict[str, str] = {
    "es-la": "es-419",
    "es-latam": "es-419",
    "es-us": "es-419",  # US Spanish is the neutral Latin American standard
    "pt-pt": "pt",
    "es-es": "es",
    "fr-fr": "fr",
    "en-us": "en",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "zh-hant": "zh-tw",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_language_code(lang_code: str) -> str:
    """Canonicalize a language code to the spelling this registry uses.

    Case, underscores, and the region aliases people type are folded away, so
    a CLI can accept whatever the caller wrote.  Unknown codes pass through
    lowercased with underscores turned into hyphens -- this is a normalizer,
    not a validator.

    >>> normalize_language_code("pt-BR")
    'pt-br'
    >>> normalize_language_code("zh_TW")
    'zh-tw'
    >>> normalize_language_code("es-US")
    'es-419'
    >>> normalize_language_code("es-419")
    'es-419'
    """
    normalized = (lang_code or "").strip().lower().replace("_", "-")
    return _CODE_ALIASES.get(normalized, normalized)


def is_dialect(lang_code: str) -> bool:
    """Return ``True`` if *lang_code* is a registered dialect variant."""
    return normalize_language_code(lang_code) in DIALECT_OVERRIDES


def get_dialect_override(lang_code: str) -> Optional[DialectOverride]:
    """Return the :class:`DialectOverride` for *lang_code*, or ``None``."""
    return DIALECT_OVERRIDES.get(normalize_language_code(lang_code))


def get_parent_language(lang_code: str) -> str:
    """Return the parent language code for a dialect, or *lang_code* itself.

    >>> get_parent_language("zh-tw")
    'zh'
    >>> get_parent_language("fr")
    'fr'
    """
    override = get_dialect_override(lang_code)
    return override.parent_lang if override else normalize_language_code(lang_code)


# ``get_base_language`` is the name to reach for when picking a *module*: the
# grammar, collation, tokenizer, and inflection engines are written per base
# language and a dialect always shares them.
get_base_language = get_parent_language


def is_translation_target(lang_code: str) -> bool:
    """Return ``True`` if *lang_code* stores its own translations.

    True for every non-dialect language and for the storage dialects; False
    for a presentation dialect such as es-mx, whose text comes from the
    variant named by :func:`get_translation_language`.

    >>> is_translation_target("es-419")
    True
    >>> is_translation_target("es-mx")
    False
    >>> is_translation_target("de")
    True
    """
    override = get_dialect_override(lang_code)
    return override.translation_target if override else True


def get_translation_language(lang_code: str) -> str:
    """Return the code whose stored translations *lang_code* should read.

    A storage language (including zh-tw, es-419, pt-br) reads its own rows; a
    presentation dialect reads its ``covered_by``, or its parent when it names
    none.

    >>> get_translation_language("es-419")
    'es-419'
    >>> get_translation_language("es-mx")
    'es-419'
    >>> get_translation_language("fr-ca")
    'fr'
    """
    override = get_dialect_override(lang_code)
    if override is None or override.translation_target:
        return normalize_language_code(lang_code)
    return override.covered_by or override.parent_lang


def get_dialects_reading(lang_code: str) -> List[str]:
    """Return the presentation dialects whose text comes from *lang_code*.

    The inverse of :func:`get_translation_language`.  Anything keyed by the
    language a word is *written* in has to reach these too -- audio recorded
    for es-mx speaks es-419's text, so a change to that text invalidates the
    Mexican recording just as it does the Latin American one.

    >>> get_dialects_reading("es-419")
    ['es-mx']
    >>> get_dialects_reading("fr")
    ['fr-ca']
    >>> get_dialects_reading("es")
    []
    """
    normalized = normalize_language_code(lang_code)
    return [
        code
        for code, override in DIALECT_OVERRIDES.items()
        if not override.translation_target
        and (override.covered_by or override.parent_lang) == normalized
    ]


def get_translation_target_dialects() -> List[str]:
    """Return the dialect codes that store their own translations.

    >>> get_translation_target_dialects()
    ['zh-tw', 'es-419', 'pt-br']
    """
    return [code for code, override in DIALECT_OVERRIDES.items() if override.translation_target]


def get_dialect_display_name(lang_code: str) -> str:
    """Return a dialect-qualified display name suitable for LLM prompts.

    Falls back to the plain language name from
    ``storage.translation_helpers.LANGUAGE_NAMES`` for non-dialect codes,
    and finally to the raw *lang_code* if nothing is found.

    >>> get_dialect_display_name("zh-tw")
    'Chinese (Taiwan Traditional)'
    >>> get_dialect_display_name("zh")
    'Chinese (Mainland Simplified)'
    """
    override = get_dialect_override(lang_code)
    if override:
        return override.dialect_display_name

    # For parent languages that have dialects, return a qualified name
    # to distinguish from the dialect variants.
    normalized = normalize_language_code(lang_code)
    return _PARENT_DISPLAY_NAMES.get(normalized, _language_name_fallback(normalized))


def get_dialects_for_language(parent_lang: str) -> List[str]:
    """Return all dialect codes that derive from *parent_lang*.

    >>> get_dialects_for_language("zh")
    ['zh-tw']
    >>> get_dialects_for_language("es")
    ['es-419', 'es-mx']
    >>> get_dialects_for_language("ko")
    []
    """
    return list(_PARENT_TO_DIALECTS.get(normalize_language_code(parent_lang), []))


def get_all_dialect_codes() -> List[str]:
    """Return all registered dialect codes.

    >>> sorted(get_all_dialect_codes())
    ['en-gb', 'es-419', 'es-mx', 'fr-ca', 'pt-br', 'zh-tw']
    """
    return list(DIALECT_OVERRIDES.keys())


def normalize_dialect_script(lang_code: str, text: str) -> str:
    """Normalize *text* stored for *lang_code* into the script it writes.

    *text* must already be this dialect's own stored text.  This repairs a row
    that landed in the wrong script (a zh-tw row holding Simplified characters,
    say) and is a no-op for text that is already correct.  It is not a way to
    derive a dialect's text from its parent's: pass a parent's text here and
    you get the parent's vocabulary in the dialect's script, which is wrong.

    If *lang_code* has no normalizer (or is not a dialect), the original text is
    returned unchanged.

    >>> normalize_dialect_script("zh-tw", "简体字")  # repair a mis-scripted row
    '簡體字'
    >>> normalize_dialect_script("es-mx", "hola")
    'hola'
    """
    override = get_dialect_override(lang_code)
    if override and override.script_normalizer:
        try:
            return override.script_normalizer(text)
        except Exception as exc:
            logger.warning("Failed to normalize text for dialect %s: %s", lang_code, exc)
    return text


def transform_from_dialect(lang_code: str, text: str) -> str:
    """Transform *text* from a dialect variant back to the parent language.

    If *lang_code* has no reverse transform (or is not a dialect), the
    original text is returned unchanged.

    >>> transform_from_dialect("zh-tw", "簡體字")  # traditional -> simplified
    '简体字'
    >>> transform_from_dialect("es-mx", "hola")
    'hola'
    """
    override = get_dialect_override(lang_code)
    if override and override.reverse_transform:
        try:
            return override.reverse_transform(text)
        except Exception as exc:
            logger.warning(
                "Failed to reverse-transform text for dialect %s: %s",
                lang_code,
                exc,
            )
    return text


def get_sort_key_language(lang_code: str) -> str:
    """Return the language code whose sort-key logic should be used.

    Dialects typically inherit their parent's sort-key algorithm.

    >>> get_sort_key_language("zh-tw")
    'zh'
    >>> get_sort_key_language("es-mx")
    'es'
    >>> get_sort_key_language("fr")
    'fr'
    """
    override = get_dialect_override(lang_code)
    if override:
        return override.sort_key_lang or override.parent_lang
    return normalize_language_code(lang_code)


def get_tts_locale(lang_code: str) -> Optional[str]:
    """Return the BCP-47 TTS locale for a dialect, or ``None``.

    >>> get_tts_locale("zh-tw")
    'zh-TW'
    >>> get_tts_locale("pt-br")
    'pt-BR'
    >>> get_tts_locale("fr") is None
    True
    """
    override = get_dialect_override(lang_code)
    return override.tts_locale if override else None


def get_llm_prompt_note(lang_code: str) -> Optional[str]:
    """Return an LLM prompt note for a dialect, or ``None``.

    >>> get_llm_prompt_note("zh-tw")
    'Use Traditional Chinese characters as used in Taiwan. Do NOT use Simplified Chinese characters.'
    >>> get_llm_prompt_note("fr") is None
    True
    """
    override = get_dialect_override(lang_code)
    return override.llm_prompt_note if override else None


# ---------------------------------------------------------------------------
# Qualified display names for parent languages that have dialect variants.
# These clarify which variant the "bare" code refers to.
# ---------------------------------------------------------------------------

_PARENT_DISPLAY_NAMES: Dict[str, str] = {
    "zh": "Chinese (Mainland Simplified)",
    "es": "Spanish (Castilian)",
    "pt": "Portuguese (European)",
    "fr": "French (Metropolitan)",
    "en": "English (American)",
}


# Variant-picker metadata for a *base* language, which is an option in its own
# variants.json but is not a dialect and so has no DIALECT_OVERRIDES entry.
# The fields mirror the ``variant_*`` ones on DialectOverride; a base language
# absent here is simply not offered as a pickable variant, which is what keeps
# a language with no regional varieties from emitting a registry at all.
@dataclass(frozen=True)
class BaseVariant:
    """Picker metadata for the unmarked variety of a language."""

    name: str
    native_name: str
    description: str
    language_code: str
    flag: Optional[str] = None
    regions: List[str] = field(default_factory=list)
    speech_locale: Optional[str] = None


BASE_VARIANTS: Dict[str, BaseVariant] = {
    "es": BaseVariant(
        name="Spain",
        native_name="Español de España",
        description="Vocabulary and pronunciation as used in Spain.",
        # The bundle is plain "es", but the picker names the variety it is:
        # es-ES is what distinguishes it from es-419 to a client.
        language_code="es-ES",
        flag="🇪🇸",
        regions=["ES"],
        speech_locale="es-ES",
    ),
    "zh": BaseVariant(
        name="Mainland China",
        native_name="简体中文",
        description="Simplified characters and vocabulary as used in mainland China.",
        language_code="zh-CN",
        flag="🇨🇳",
        # SG also writes Simplified and reads this bundle comfortably.
        regions=["CN", "SG"],
        speech_locale="zh-CN",
    ),
    "pt": BaseVariant(
        name="Portugal",
        native_name="Português de Portugal",
        description="Vocabulary and pronunciation as used in Portugal.",
        language_code="pt-PT",
        flag="🇵🇹",
        regions=["PT"],
        speech_locale="pt-PT",
    ),
}


def _language_name_fallback(lang_code: str) -> str:
    """Look up the language name from translation_helpers, or return the code."""
    try:
        from storage.translation_helpers import LANGUAGE_NAMES

        return LANGUAGE_NAMES.get(lang_code, lang_code)
    except ImportError:
        return lang_code
