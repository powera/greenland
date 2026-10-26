"""Simple (A1) sentences: two short example sentences per early-level word.

A refinement of guided generation (sentences.guided_generation), which it reuses
for the LLM call and lemma lookup.  The differences:

* It keeps a fixed number of sentences per word (SIMPLE_SENTENCES_PER_LEMMA)
  rather than adding a batch on every run, asking for more candidates than it
  needs and keeping the easiest ones.
* Each candidate is levelled with the shared sentence rule
  (storage.crud.sentence.sentence_level_from_word_levels) and dropped if it
  lands above SIMPLE_MAX_LEVEL.  A word the database does not know makes the
  candidate too hard; it is never staged as a pending import.
* The prompt names no example subjects.  An earlier prompt suggested a
  non-pronoun subject and the model reused it in about one sentence in ten
  ("my friend"), so subjects are steered to pronouns and repeated phrases are
  filtered mechanically.

Stored rows carry sentence_collection SIMPLE_SENTENCE_COLLECTION and
source_filename "simple:<lemma GUID>", which is how the per-word count is kept.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

import constants
from langtools.grammatical_words import is_function_word
from sentences.guided_generation import GuidedSentenceGenerator
from sentences.sentence_word_linker import PART_OF_SPEECH_TO_POS, find_lemma_by_text
from sentences.vocabulary_budget import build_prompt_vocabulary_section
from storage.crud.sentence import (
    add_sentence,
    lemma_level_for_sentence,
    sentence_level_from_word_levels,
)
from storage.crud.sentence_translation import add_sentence_translation
from storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWordHint

logger = logging.getLogger(__name__)

SIMPLE_SENTENCE_COLLECTION = "simple"
SIMPLE_SOURCE_PREFIX = "simple:"
OPERATION_SOURCE = "buivolas:simple"

# Words at levels 1..SIMPLE_MAX_LEVEL get simple sentences, and a kept sentence
# must itself level at or below it.
SIMPLE_MAX_LEVEL = 10
SIMPLE_SENTENCES_PER_LEMMA = 2
SIMPLE_CANDIDATES_PER_CALL = 4
SIMPLE_POS_TYPES = ("noun", "verb", "adjective")

# The prompt asks for 4-7 words; one over is tolerated.
MAX_SENTENCE_WORDS = 8

# Phrases the model over-uses as a subject; a candidate containing one is dropped.
BANNED_PHRASES = ("my friend",)

# Time words the model pads sentences with.  At most one of a word's sentences
# may use one.
FILLER_TIME_WORDS = ("today", "yesterday", "now")

_WORD_PATTERN = re.compile(r"[a-z']+")


def simple_source_filename(lemma_guid: str) -> str:
    return f"{SIMPLE_SOURCE_PREFIX}{lemma_guid}"


def _sentence_words(text: str) -> List[str]:
    return _WORD_PATTERN.findall(text.lower())


def sentence_opener(text: str) -> str:
    """The first word, lowercased: used to keep a word's sentences varied."""
    words = _sentence_words(text)
    return words[0] if words else ""


def has_filler_time_word(text: str) -> bool:
    return any(word in FILLER_TIME_WORDS for word in _sentence_words(text))


@dataclass
class SimpleCandidate:
    """One LLM sentence, with its resolved lemmas and computed level."""

    text: str
    level: Optional[int] = None
    lemmas: List[Lemma] = field(default_factory=list)
    reject_reason: Optional[str] = None

    @property
    def opener(self) -> str:
        return sentence_opener(self.text)

    @property
    def has_filler(self) -> bool:
        return has_filler_time_word(self.text)


def resolve_simple_word(
    session: Session, word_text: str, part_of_speech: str, target: Lemma
) -> Optional[Lemma]:
    """Find the lemma for one content word, preferring the easiest sense.

    find_lemma_by_text takes the first match, which for a word with several
    senses ("coat": garment vs. layer of paint) is arbitrary.  A beginner
    sentence almost always means the common sense, so the lowest-level match
    wins; the target lemma wins outright when the text is its own.
    """
    if find_lemma_by_text(session, word_text, part_of_speech, source_lemma=target) is target:
        return target
    query = session.query(Lemma).filter(Lemma.lemma_text.ilike(word_text))
    pos_hint = PART_OF_SPEECH_TO_POS.get(part_of_speech)
    if pos_hint:
        query = query.filter(Lemma.pos_type == pos_hint)
    matches = query.all()
    if not matches:
        return None

    def sort_key(lemma: Lemma) -> int:
        level = lemma_level_for_sentence(lemma.difficulty_level)
        return level if level is not None else constants.MAX_DIFFICULTY_LEVEL + 2

    return min(matches, key=sort_key)


def evaluate_candidate(
    session: Session, target: Lemma, sentence_data: Dict[str, Any]
) -> SimpleCandidate:
    """Resolve a candidate's words to lemmas, level it, and note any reason to drop it."""
    text = str(sentence_data.get("en") or "").strip()
    candidate = SimpleCandidate(text=text)
    if not text:
        candidate.reject_reason = "empty"
        return candidate
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            candidate.reject_reason = f"uses '{phrase}'"
            return candidate
    if len(_sentence_words(text)) > MAX_SENTENCE_WORDS:
        candidate.reject_reason = "too long"
        return candidate

    resolved: Dict[int, Lemma] = {}
    for word_data in sentence_data.get("words_used") or []:
        if not isinstance(word_data, dict):
            continue
        word_lemma_text = str(word_data.get("lemma") or "").strip()
        if not word_lemma_text or is_function_word(word_lemma_text, "en"):
            continue
        found = resolve_simple_word(
            session,
            word_lemma_text,
            str(word_data.get("part_of_speech") or "unknown"),
            target,
        )
        if found is None:
            candidate.reject_reason = f"unknown word '{word_lemma_text}'"
            return candidate
        resolved[found.id] = found
    candidate.lemmas = list(resolved.values())

    if target.id not in resolved:
        candidate.reject_reason = "target word not used"
        return candidate

    word_levels = [
        level
        for level in (
            lemma_level_for_sentence(lemma.difficulty_level) for lemma in resolved.values()
        )
        if level is not None
    ]
    candidate.level = sentence_level_from_word_levels(word_levels)
    if candidate.level is None or candidate.level > SIMPLE_MAX_LEVEL:
        candidate.reject_reason = f"level {candidate.level}"
    return candidate


def select_candidates(
    candidates: Sequence[SimpleCandidate],
    existing_texts: Sequence[str],
    needed: int,
) -> List[SimpleCandidate]:
    """Pick up to `needed` acceptable candidates, easiest first.

    A candidate is skipped if it opens with the same word as one already kept
    (or already stored), or if it would be a second sentence padded with a time
    word.  Sentences without filler are preferred.
    """
    used_openers = {sentence_opener(text) for text in existing_texts}
    filler_used = any(has_filler_time_word(text) for text in existing_texts)
    seen_texts = {text.strip().lower() for text in existing_texts}
    pool = sorted(
        (candidate for candidate in candidates if candidate.reject_reason is None),
        key=lambda candidate: (candidate.has_filler, candidate.level or 0),
    )
    chosen: List[SimpleCandidate] = []
    for candidate in pool:
        if len(chosen) >= needed:
            break
        if candidate.text.lower() in seen_texts or candidate.opener in used_openers:
            continue
        if candidate.has_filler and filler_used:
            continue
        chosen.append(candidate)
        seen_texts.add(candidate.text.lower())
        used_openers.add(candidate.opener)
        filler_used = filler_used or candidate.has_filler
    return chosen


def existing_simple_sentences(session: Session, lemma_guid: str) -> List[str]:
    """English text of the word's stored, non-rejected simple sentences."""
    rows = (
        session.query(SentenceTranslation.translation_text)
        .join(Sentence, Sentence.id == SentenceTranslation.sentence_id)
        .filter(
            Sentence.source_filename == simple_source_filename(lemma_guid),
            Sentence.rejected == False,  # noqa: E712
            SentenceTranslation.language_code == "en",
        )
        .all()
    )
    return [str(text) for (text,) in rows]


def simple_sentence_counts(session: Session) -> Dict[str, int]:
    """Non-rejected simple sentences per lemma GUID."""
    counts: Dict[str, int] = {}
    rows = (
        session.query(Sentence.source_filename)
        .filter(
            Sentence.sentence_collection == SIMPLE_SENTENCE_COLLECTION,
            Sentence.rejected == False,  # noqa: E712
        )
        .all()
    )
    for (source_filename,) in rows:
        if source_filename and source_filename.startswith(SIMPLE_SOURCE_PREFIX):
            lemma_guid = source_filename[len(SIMPLE_SOURCE_PREFIX) :]
            counts[lemma_guid] = counts.get(lemma_guid, 0) + 1
    return counts


class SimpleSentenceGenerator(GuidedSentenceGenerator):
    """Fill a word up to SIMPLE_SENTENCES_PER_LEMMA simple sentences."""

    def generate_and_store(self, session: Session, lemma: Lemma) -> Dict[str, Any]:
        if lemma.pos_type not in SIMPLE_POS_TYPES:
            return {
                "success": True,
                "skipped": True,
                "reason": f"POS type '{lemma.pos_type}' not supported",
            }
        if lemma.guid is None:
            return {"success": False, "error": f"Lemma {lemma.id} has no GUID"}

        existing_texts = existing_simple_sentences(session, lemma.guid)
        needed = SIMPLE_SENTENCES_PER_LEMMA - len(existing_texts)
        if needed <= 0:
            return {"success": True, "skipped": True, "reason": "already has simple sentences"}

        previous_sentences = ""
        if existing_texts:
            previous_sentences = "Already written for this word (write different ones):\n" + (
                "\n".join(f"- {text}" for text in existing_texts)
            )
        vocabulary_section = build_prompt_vocabulary_section(
            target_word=lemma.lemma_text,
            target_pos_type=lemma.pos_type,
            target_pos_subtype=lemma.pos_subtype or "misc",
            max_level=SIMPLE_MAX_LEVEL,
        )
        response = self._call_llm_for_sentences(
            lemma=lemma,
            num_sentences=SIMPLE_CANDIDATES_PER_CALL,
            vocabulary_section=vocabulary_section,
            prompt_name="simple",
            previous_sentences=previous_sentences,
        )
        if not response or not response.get("sentences"):
            return {"success": False, "error": "LLM generation failed"}

        candidates = [
            evaluate_candidate(session, lemma, sentence_data)
            for sentence_data in response["sentences"]
            if isinstance(sentence_data, dict)
        ]
        for candidate in candidates:
            if candidate.reject_reason:
                logger.info("  x %s (%s)", candidate.text, candidate.reject_reason)
        chosen = select_candidates(candidates, existing_texts, needed)
        for candidate in chosen:
            logger.info("  -> %s (level %s)", candidate.text, candidate.level)
        if len(chosen) < needed:
            logger.warning(
                "%s (%s): kept %d of %d needed simple sentences",
                lemma.lemma_text,
                lemma.guid,
                len(chosen),
                needed,
            )

        result: Dict[str, Any] = {
            "success": True,
            "sentences": [candidate.text for candidate in chosen],
            "rejected": [
                {"en": candidate.text, "reason": candidate.reject_reason}
                for candidate in candidates
                if candidate.reject_reason
            ],
        }
        if self.dry_run:
            result["storage"] = {"stored": 0}
            return result
        result["storage"] = {"stored": self.store_simple_sentences(session, lemma, chosen)}
        return result

    def store_simple_sentences(
        self, session: Session, lemma: Lemma, chosen: Sequence[SimpleCandidate]
    ) -> int:
        assert lemma.guid is not None
        for candidate in chosen:
            sentence = add_sentence(
                session,
                source_filename=simple_source_filename(lemma.guid),
                notes=f"Simple sentence for {lemma.lemma_text} ({lemma.guid})",
                sentence_collection=SIMPLE_SENTENCE_COLLECTION,
                source=OPERATION_SOURCE,
            )
            add_sentence_translation(
                session, sentence, "en", candidate.text, source=OPERATION_SOURCE
            )
            for position, word_lemma in enumerate(candidate.lemmas):
                session.add(
                    SentenceWordHint(
                        sentence_id=sentence.id,
                        lemma_id=word_lemma.id,
                        position=position,
                        slot_name=word_lemma.pos_type,
                        english_text=word_lemma.lemma_text,
                    )
                )
            sentence.minimum_level = candidate.level
        session.commit()
        return len(chosen)
