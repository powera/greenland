#!/usr/bin/env python3
"""Jonvabalis agent: review pending imports whose proposed head word is new.

``api.lemmas.add_word`` answers "what does this word mean" by creating the senses
it is confident about and queueing the rest.  A queued row names a *different*
English head word than the one that was asked about -- the word "world" was
queried and the row proposes "realm" -- and its ``notes`` field states the
question a reviewer has to answer: is that head word the right lemma for this
sense, is the queried word a variant of it, or are both separate lemmas?

Nothing answers that today, and the queue holds a few thousand rows.  This agent
reviews the tractable slice of it: rows whose proposed ``english_word`` does not
yet exist as a lemma at all, so the decision is "add this sense or don't" rather
than a merge into an existing paradigm.

The queried word usually *does* exist, and that is the trap.  A row proposing a
new head word can still duplicate a sense the queried word already carries --
"world" was queried, two ``world`` lemmas were created in the same operation,
and one queued row restates one of them under a new name.  So every existing
lemma for the queried word is put in front of the model, with its subtype,
level and translations, and the first thing it is asked is whether this row is
already covered.  A row judged a duplicate is never given a level.

What the model decides, in order (an early answer ends the row):

1. ``duplicate`` -- an existing sense of the queried word, or of the proposed
   word when it was asked about by id, already covers this.
2. ``distinct`` -- a real sense the database lacks, which then needs a head
   word, a subtype and, where the head word has other senses, a disambiguation.
3. ``unsure`` -- anything it cannot place, including rows whose answer depends
   on the unsettled question of when two everyday words for one concept are
   variants rather than separate lemmas (grandpa/grandfather, couch/sofa; see
   ``storage.models.variant_form``).

Choosing the head word is the heart of a ``distinct`` verdict, and it is two
separate questions.  Which word does a learner learn for this meaning -- the
queried word ("the world of finance"), the proposed word ("realm"), or a set
phrase containing one of them ("bail bond", which is never just "bond")?  And
if that word has other senses, what short tag tells them apart?  The tag is
often a synonym ("world" / "realm", as "fat" / "overweight" already is), but it
is only a label and says nothing about whether the synonym is a lemma.  To keep
the first question honest the model writes a definition and one natural sample
sentence first, and must choose the head word that sentence actually uses.
That sentence becomes the lemma's example; the queued examples are kept only
where they contain the chosen head word.  The proposed word is often only a
near-synonym ("representative" for a brand ambassador), so the model is asked
whether the queried word itself carries the meaning before moving it.

A row queried under a word that is not yet a lemma ("consumed", with no
"consume") is skipped without an LLM call: it is a minor sense of a word whose
main senses have never been added, and add_word should add those first.

Levels are asked for per sense, not per word.  Every row in a queued group
inherits the *word's* frequency rank, which is wrong for a minor sense -- the
rank-140 "world" carries it into the science-fiction "a distant world" reading --
so the prompt supplies the levels of semantically comparable lemmas as anchors
and asks for a level for this sense alone.  That answer is only reported (it is
in ``--output``); the lemma is stored at the unset level until the anchors are
good enough to trust it.

Acting on a decision goes through the same approval path the Barsukas review
page uses -- ``words.pending_imports.approve_pending_import`` creates the lemma
and clears the row, ``reject_pending_import`` clears it -- so an agent-cleared
row settles exactly as a hand-cleared one does.  A rejection records no word
exclusion, since only the sense was a duplicate, not the word.
A ``distinct`` verdict approves, a ``duplicate`` verdict rejects, and ``unsure``
is left in the queue for a human, as is any verdict below ``MIN_CONFIDENCE``.

An approval carries the model's answer through: its head word, definition,
subtype, translations and sample sentence are written onto the pending row
before approval reads it, and its disambiguation is passed to approval for the
new lemma.  The subtype is chosen from the POS's full subtype list, and a row
whose subtype is still an open-class catch-all (``noun_other``) is left queued,
as ``add_word`` does.  Translations are asked for on every row, since a changed
head word needs new ones and older rows were staged with none; a row missing
any of them is left queued.

``--dry-run`` prints the rows a run would review and makes no LLM calls.

Usage::

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/agents/jonvabalis.py --dry-run
    PYTHONPATH=src python src/agents/jonvabalis.py --limit 10 --output review.json
    PYTHONPATH=src python src/agents/jonvabalis.py --pending-id 2924 --pending-id 2925
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    get_data_source_config,
)
import constants
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.crud.pending_import_senses import (
    read_pending_import_example_sentences,
    read_pending_import_translations,
    serialize_example_sentences,
    serialize_translations,
)
from storage.backend import create_session as create_backend_session
from storage.models.guid_prefixes import classifiable_subtypes, render_subtype_list
from storage.models.imports import PendingImport
from storage.models.schema import Lemma
from storage.translation_helpers import LANG_CODE_TO_LLM_FIELD, convert_llm_response_to_lang_codes
from wordfreq.translation.constants import MAJOR_POS_TYPES
from words.lemma_creation import TRANSLATION_LANGUAGES
from words.pending_imports.approval import approve_pending_import, reject_pending_import

LOGGER = logging.getLogger(__name__)

# Ten rows is the default batch: enough to see whether the judgements are sound,
# small enough to read every one by hand before trusting the next run.
DEFAULT_LIMIT = 10

# Below this the verdict is reported but not acted on; the row stays queued.
MIN_CONFIDENCE = 0.8

VERDICT_DUPLICATE = "duplicate"
VERDICT_DISTINCT = "distinct"
VERDICT_UNSURE = "unsure"

RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [VERDICT_DUPLICATE, VERDICT_DISTINCT, VERDICT_UNSURE],
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences justifying the verdict.",
        },
        "duplicate_of_lemma_id": {
            "type": ["integer", "null"],
            "description": (
                "When the verdict is duplicate, the id of the existing lemma that "
                "already covers this sense. Null otherwise."
            ),
        },
        "definition": {
            "type": ["string", "null"],
            "description": (
                "When the verdict is distinct, a one-sentence definition of this "
                "sense. Null otherwise."
            ),
        },
        "sample_sentence": {
            "type": ["string", "null"],
            "description": (
                "When the verdict is distinct, one natural English sentence using "
                "this sense. It must contain head_word. Null otherwise."
            ),
        },
        "head_word": {
            "type": ["string", "null"],
            "description": (
                "When the verdict is distinct, the word or set phrase sample_sentence "
                "uses for this sense: the queried word, the proposed word, or a set "
                "phrase containing one of them. Never parenthesised. Null otherwise."
            ),
        },
        "disambiguation": {
            "type": ["string", "null"],
            "description": (
                "Short tag telling this sense apart from others with the same head "
                "word, e.g. 'area of activity' or a synonym such as 'realm'. "
                "Required when the head word already has a sense; null otherwise."
            ),
        },
        "pos_subtype": {
            "type": ["string", "null"],
            "description": (
                "When the verdict is distinct, the subtype for this sense, chosen from "
                "the listed subtypes. Never 'other' when a listed subtype fits."
            ),
        },
        "translations": {
            # Not nullable as a whole: OpenAI's strict mode rejects a nullable
            # object. Each field is nullable instead.
            "type": "object",
            "description": (
                "When the verdict is distinct, the head word in this sense translated "
                "into each language. Every field null otherwise."
            ),
            "properties": {
                LANG_CODE_TO_LLM_FIELD[lang_code]: {"type": ["string", "null"]}
                for lang_code in TRANSLATION_LANGUAGES
            },
            "required": [LANG_CODE_TO_LLM_FIELD[lang_code] for lang_code in TRANSLATION_LANGUAGES],
            "additionalProperties": False,
        },
        "difficulty_level": {
            "type": ["integer", "null"],
            "description": (
                "Level for THIS SENSE, anchored on the comparable lemmas supplied. "
                "Not the queried word's level and not its frequency rank."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in the verdict, from 0 to 1.",
        },
    },
    "required": ["verdict", "reasoning", "confidence"],
    "additionalProperties": False,
}


def uses_head_word(sentence: str, head_word: str) -> bool:
    """Whether ``sentence`` uses ``head_word``, allowing a regular suffix.

    A prefix match at a word boundary, so "continued" counts for "continue" and
    "worlds" for "world".  An irregular form ("ran" for "run") does not; the
    prompt asks for the dictionary form, and a miss only leaves a row queued.
    """
    pattern = rf"\b{re.escape(head_word.lower())}\w*\b"
    return re.search(pattern, sentence.lower()) is not None


def head_word_problem(
    head_word: Any,
    sample_sentence: Any,
    queried_word: Optional[str],
    proposed_word: Optional[str],
) -> Optional[str]:
    """Why a ``distinct`` verdict's head word cannot be used, or None if it can.

    The head word must be the queried word, the proposed word, or a set phrase
    containing one of them -- anything else is the model inventing a word,
    which is a human's call -- and the sample sentence must use it, since that
    sentence is the evidence the head word was chosen by.
    """
    if not isinstance(head_word, str) or not head_word.strip():
        return "no head word"
    if "(" in head_word:
        return f"parenthesised head word {head_word!r}"
    candidates = [word.lower() for word in (queried_word, proposed_word) if word]
    lowered = head_word.lower()
    if not any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in candidates):
        return f"unexpected head word {head_word!r}"
    if not isinstance(sample_sentence, str) or not sample_sentence.strip():
        return "no sample sentence"
    if not uses_head_word(sample_sentence, head_word):
        return f"sample sentence does not use {head_word!r}"
    return None


def is_catch_all_subtype(pos_type: Optional[str], pos_subtype: Optional[str]) -> bool:
    """Whether ``pos_subtype`` is an open-class catch-all that needs re-choosing.

    Closed classes (preposition, conjunction, ...) have ``<pos>_other`` as their
    only subtype, so it is only a failure to classify on an open-class word.
    """
    return bool(pos_type in MAJOR_POS_TYPES and pos_subtype and pos_subtype.endswith("_other"))


def subtype_problem(pos_type: Optional[str], pos_subtype: Optional[str]) -> Optional[str]:
    """Why ``pos_subtype`` cannot be approved for ``pos_type``, or None if it can."""
    if not pos_type or not pos_subtype:
        return "no POS subtype"
    if pos_subtype not in classifiable_subtypes(pos_type):
        return f"{pos_subtype!r} is not a {pos_type} subtype"
    if is_catch_all_subtype(pos_type, pos_subtype):
        return f"catch-all subtype {pos_subtype!r}"
    return None


def decision_translations(decision: Dict[str, Any]) -> Dict[str, str]:
    """The model's translations by language code, blank entries dropped."""
    raw = decision.get("translations")
    if not isinstance(raw, dict):
        return {}
    by_lang_code = convert_llm_response_to_lang_codes(raw)
    return {
        lang_code: text.strip()
        for lang_code, text in by_lang_code.items()
        if lang_code in TRANSLATION_LANGUAGES and isinstance(text, str) and text.strip()
    }


def select_pending_rows(
    session: Session,
    limit: int,
    pending_ids: Optional[Sequence[int]] = None,
) -> List[PendingImport]:
    """Return queued lemma rows whose proposed head word is not yet a lemma.

    Explicit ``pending_ids`` are returned as given, so a specific row can be
    re-reviewed after a prompt change without waiting for it to come up in the
    ordinary scan.
    """
    query = session.query(PendingImport).filter(PendingImport.target_kind == "lemma")
    if pending_ids:
        return query.filter(PendingImport.id.in_(list(pending_ids))).all()

    existing_lemma_texts = session.query(Lemma.lemma_text)
    return (
        query.filter(~PendingImport.english_word.in_(existing_lemma_texts))
        # See queried_word_is_missing: such rows wait for add_word.
        .filter(
            PendingImport.queried_word.is_(None)
            | PendingImport.queried_word.in_(existing_lemma_texts)
        )
        .order_by(PendingImport.id)
        .limit(limit)
        .all()
    )


def existing_senses_for(session: Session, lemma_text: Optional[str]) -> List[Dict[str, Any]]:
    """Describe every lemma already stored under ``lemma_text``.

    This is the duplicate-check context.  A row proposing a new head word may
    still restate a sense the queried word already holds, and that is only
    visible with these in hand.
    """
    if not lemma_text:
        return []

    lemmas = session.query(Lemma).filter(Lemma.lemma_text == lemma_text).all()
    return [
        {
            "lemma_id": lemma.id,
            "pos_type": lemma.pos_type,
            "pos_subtype": lemma.pos_subtype,
            "disambiguation": lemma.disambiguation,
            "difficulty_level": lemma.difficulty_level,
            "definition": lemma.definition_text,
        }
        for lemma in lemmas
    ]


def brief_senses_for(session: Session, lemma_text: Optional[str]) -> List[Dict[str, Any]]:
    """Summarise the lemmas already stored under the proposed head word.

    Brief on purpose: the model needs to see that "representative" already
    means "a person chosen to act on behalf of others" before it files a near
    synonym there, not the full detail given for the queried word's senses.
    """
    if not lemma_text:
        return []
    lemmas = session.query(Lemma).filter(Lemma.lemma_text == lemma_text).all()
    return [
        {
            "lemma_id": lemma.id,
            "pos_subtype": lemma.pos_subtype,
            "disambiguation": lemma.disambiguation,
            "definition": lemma.definition_text,
        }
        for lemma in lemmas
    ]


def queried_word_is_missing(session: Session, pending: PendingImport) -> bool:
    """Whether the row was queried under a word that is not yet a lemma.

    Such a row ("consumed" -> "destroy", with no "consume" in the database) is
    one sense of a word whose main senses have never been added.  Resolving it
    here would make a minor sense the word's first lemma, so it waits until the
    word itself goes through add_word.  A row with no queried word at all has
    nothing to wait for.
    """
    if not pending.queried_word:
        return False
    return session.query(Lemma.id).filter(Lemma.lemma_text == pending.queried_word).first() is None


def level_anchors_for(session: Session, pos_subtype: Optional[str]) -> List[Dict[str, Any]]:
    """Sample lemmas sharing a subtype, as difficulty-level reference points.

    The model is poor at inventing a level from nothing but reasonable at
    placing a sense beside words it can see, so a handful of same-subtype
    lemmas with their levels go into the prompt.
    """
    if not pos_subtype:
        return []

    lemmas = (
        session.query(Lemma)
        .filter(Lemma.pos_subtype == pos_subtype)
        .order_by(Lemma.difficulty_level)
        .limit(12)
        .all()
    )
    return [
        {"lemma_text": lemma.lemma_text, "difficulty_level": lemma.difficulty_level}
        for lemma in lemmas
    ]


def build_prompt(
    pending: PendingImport,
    existing_senses: Sequence[Dict[str, Any]],
    proposed_senses: Sequence[Dict[str, Any]],
    level_anchors: Sequence[Dict[str, Any]],
) -> str:
    """Build the review prompt for one queued row."""
    translations = read_pending_import_translations(pending)
    example_sentences = read_pending_import_example_sentences(pending)
    # Older rows carry no translations, only the one-word hint the reviewer
    # was shown; it still pins down which sense was meant.
    if pending.disambiguation_language and pending.disambiguation_translation:
        translations.setdefault(pending.disambiguation_language, pending.disambiguation_translation)

    payload = {
        "queried_word": pending.queried_word,
        "proposed_head_word": pending.english_word,
        "proposed_definition": pending.definition,
        "proposed_pos_type": pending.pos_type,
        "proposed_pos_subtype": pending.pos_subtype,
        "staged_translations_of_proposed_head_word": translations,
        "example_sentences": example_sentences,
        "server_note": pending.notes,
        "existing_senses_of_queried_word": list(existing_senses),
        "existing_senses_of_proposed_head_word": list(proposed_senses),
        "same_subtype_lemmas_for_level_reference": list(level_anchors),
    }

    # Every head word the model may choose shares the row's POS, so one list
    # covers them all.
    subtype_section = ""
    if pending.pos_type and classifiable_subtypes(pending.pos_type):
        subtype_section = (
            f"Subtypes for {pending.pos_type}:\n{render_subtype_list(pending.pos_type)}\n\n"
        )

    return (
        "A word was submitted to a vocabulary database. The server created the senses it "
        "was confident about and queued this one, because the sense seems to belong under "
        "a different English head word than the word that was asked about.\n\n"
        "Decide what to do with the queued row.\n\n"
        "First, and most importantly: is this sense ALREADY COVERED by one of the existing "
        "senses listed under 'existing_senses_of_queried_word' or "
        "'existing_senses_of_proposed_head_word'? The queried word's senses were often "
        "created by the very same request, so a queued row restating one of them under a "
        "new name is the common failure. Compare meanings and translations, not just "
        "labels. If it is covered, answer 'duplicate' and name the lemma id; do not assign "
        "a level.\n\n"
        "If it is genuinely a sense the database lacks, answer 'distinct' and work in "
        "this order:\n"
        "  1. definition: define this sense in one sentence.\n"
        "  2. sample_sentence: write one natural English sentence using this sense, "
        "phrased the way a speaker would actually say it, with the head word in its "
        "dictionary form or with a regular ending (-s, -ed, -ing).\n"
        "  3. head_word: the word or set phrase your sample sentence uses for this sense. "
        "It is one of: the queried word, the proposed head word, or a set phrase "
        "containing one of them. Strongly prefer the bare word. A set phrase is right "
        "only when speakers never use the bare word for this meaning: 'bail bond' is "
        "never just 'bond'. When people say the bare word in context -- a chemist says "
        "'bond', a university's staff say 'the chancellor' -- the head word is the bare "
        "word and the context goes in the disambiguation: 'bond' / 'chemical', not "
        "'chemical bond'; 'chancellor' / 'university', not 'university chancellor'. "
        "Then ask whether the queried word itself carries this meaning. The proposed word "
        "is often only a near-synonym: a 'brand ambassador' is not simply a "
        "'representative', and 'too much bureaucracy' is not simply 'red tape'. If the "
        "queried word expresses this meaning, the head word is the queried word with a "
        "tag, unless the proposed word is clearly the more common way to say it. A "
        "proposed word that already has a broader sense listed is a strong sign the "
        "meaning belongs to the queried word.\n"
        "  4. disambiguation: a short tag, one to three words, that tells this sense apart "
        "from the head word's other meanings. Give one whenever the head word has other "
        "common meanings, whether or not they are in the database yet -- 'chancellor' / "
        "'university' needs a tag even though only the government sense is listed. A "
        "synonym is often the best tag: 'world' / 'realm' is fine, and does not mean "
        "'realm' should be the head word. Never put the tag in head_word, as in "
        "'world (realm)'.\n"
        "  5. pos_subtype: choose from the subtypes listed below for this part of speech. "
        "Choose 'other' only if none of them fits; the proposed subtype is often a "
        "placeholder, especially when it is 'other'.\n"
        "  6. translations: translate the head word, in this sense, into each language. "
        "The staged translations were written for the proposed head word; reuse them "
        "where they still fit, and replace them where the head word or sense changed.\n"
        "  7. difficulty_level: for THIS SENSE. Anchor it on the same-subtype lemmas given. "
        "A minor or figurative sense belongs well above the everyday sense of the same "
        "word. Do not reuse the queried word's level or its frequency rank.\n\n"
        "If the answer depends on whether two everyday words for one concept should be one "
        "lemma or two (grandpa vs grandfather, couch vs sofa), answer 'unsure' -- that policy "
        "is unsettled and a human decides it.\n\n"
        f"{subtype_section}"
        f"Row under review:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


class JonvabalisAgent:
    """Review queued pending imports and propose a disposition for each."""

    def __init__(self, config: DataSourceConfig, timeout: int = 120) -> None:
        self.config = config
        self.client = UnifiedLLMClient.from_config(config, timeout=timeout)

    def review_row(self, session: Session, pending: PendingImport) -> Dict[str, Any]:
        """Ask the model what to do with one queued row."""
        existing_senses = existing_senses_for(session, pending.queried_word)
        proposed_senses = brief_senses_for(session, pending.english_word)
        level_anchors = level_anchors_for(session, pending.pos_subtype)
        prompt = build_prompt(pending, existing_senses, proposed_senses, level_anchors)

        response = self.client.generate_chat(prompt=prompt, json_schema=RESPONSE_SCHEMA)
        decision = response.structured_data if isinstance(response.structured_data, dict) else {}

        return {
            "pending_id": pending.id,
            "queried_word": pending.queried_word,
            "proposed_head_word": pending.english_word,
            "proposed_pos_subtype": pending.pos_subtype,
            "existing_sense_count": len(existing_senses),
            "decision": decision,
        }

    def review(
        self,
        limit: int = DEFAULT_LIMIT,
        pending_ids: Optional[Sequence[int]] = None,
    ) -> List[Dict[str, Any]]:
        """Review a batch of queued rows, one LLM call each, and act on each."""
        results: List[Dict[str, Any]] = []
        session = create_backend_session(self.config)
        try:
            rows = select_pending_rows(session, limit, pending_ids)
            LOGGER.info("Reviewing %d pending row(s)", len(rows))
            for index, pending in enumerate(rows, start=1):
                LOGGER.info(
                    "[%d/%d] pending %s: %s -> %s",
                    index,
                    len(rows),
                    pending.id,
                    pending.queried_word,
                    pending.english_word,
                )
                if queried_word_is_missing(session, pending):
                    # Checked before the LLM call: the answer is known already.
                    results.append(
                        {
                            "pending_id": pending.id,
                            "queried_word": pending.queried_word,
                            "proposed_head_word": pending.english_word,
                            "proposed_pos_subtype": pending.pos_subtype,
                            "decision": {},
                            "outcome": self.leave_in_queue(
                                f"queried word {pending.queried_word!r} is not a lemma yet; "
                                "add it with add_word first"
                            ),
                        }
                    )
                    continue
                result = self.review_row(session, pending)
                result["outcome"] = self.apply_decision(session, pending, result["decision"])
                results.append(result)
        finally:
            session.close()
        return results

    def apply_decision(
        self, session: Session, pending: PendingImport, decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Clear one reviewed row through the ordinary approval path.

        ``distinct`` approves, creating the lemma; ``duplicate`` rejects.  Anything
        else -- ``unsure``, a missing verdict, a low-confidence call -- is left
        in the queue, because those are exactly the rows a human should see.
        """
        # Read before applying: a successful approval or rejection deletes the
        # row, so the ORM object is stale after.
        pending_id = int(pending.id)
        verdict = decision.get("verdict")
        confidence = decision.get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < MIN_CONFIDENCE:
            return self.leave_in_queue("low_confidence")

        try:
            if verdict == VERDICT_DISTINCT:
                return self.approve_distinct(session, pending, decision)
            elif verdict == VERDICT_DUPLICATE:
                # No exclusion: it would key on the proposed head word and bar
                # that word from add_word entirely, when only this one sense
                # was a duplicate -- "humanity" is a real word even though
                # world's "humanity" sense is not new.
                outcome = reject_pending_import(
                    session=session,
                    pending_import_id=pending_id,
                    reason="jonvabalis_duplicate_sense",
                    add_to_exclusions=False,
                )
                action = "rejected"
            else:
                return self.leave_in_queue(f"verdict {verdict!r}")
        except Exception as exc:  # the batch continues past one bad row
            session.rollback()
            LOGGER.warning("Could not apply decision for pending %s: %s", pending_id, exc)
            return {"action": "error", "success": False, "error": str(exc)}

        return {
            "action": action,
            "success": bool(outcome.get("success")),
            "lemma_id": outcome.get("lemma_id"),
            "error": outcome.get("error"),
        }

    def approve_distinct(
        self, session: Session, pending: PendingImport, decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Approve a ``distinct`` row as the model described it, not as it was queued.

        Approval builds the lemma from the pending row, so the model's head
        word, definition, subtype, translations and example sentences are written onto the
        row first, in this session and uncommitted: a failed approval rolls
        them back and the row stays queued as it was.  The disambiguation has
        no pending-row column and is passed to approval directly.

        The model's difficulty level is not stored; approval creates the lemma
        at the unset level until levels are assessed properly.

        An incomplete verdict is left in the queue rather than approved with
        the gaps filled from the queued row.
        """
        pending_id = int(pending.id)
        head_word = decision.get("head_word")
        definition = decision.get("definition")
        sample_sentence = decision.get("sample_sentence")
        disambiguation = decision.get("disambiguation")

        problem = head_word_problem(
            head_word, sample_sentence, pending.queried_word, pending.english_word
        )
        if problem is not None:
            return self.leave_in_queue(problem)
        assert isinstance(head_word, str) and isinstance(sample_sentence, str)
        if not isinstance(definition, str) or not definition.strip():
            return self.leave_in_queue("no definition")

        pos_subtype = decision.get("pos_subtype") or pending.pos_subtype
        # The rendered list offers the catch-all under its bare name.
        if pos_subtype == "other" and pending.pos_type:
            pos_subtype = f"{pending.pos_type}_other"
        problem = subtype_problem(pending.pos_type, pos_subtype)
        if problem is not None:
            return self.leave_in_queue(problem)

        # Asked for on every row: a changed head word needs new translations,
        # and older rows were staged with none at all.
        translations = decision_translations(decision)
        missing = [code for code in TRANSLATION_LANGUAGES if code not in translations]
        if missing:
            return self.leave_in_queue(f"missing translations {missing}")

        if (
            not disambiguation
            and session.query(Lemma.id).filter(Lemma.lemma_text == head_word).first()
        ):
            return self.leave_in_queue(f"{head_word!r} already has a sense; no disambiguation")

        # The queued examples were written for the proposed word; only those
        # that use the chosen head word illustrate this lemma.
        queued_examples = [
            example
            for example in read_pending_import_example_sentences(pending)
            if uses_head_word(example, head_word)
        ]
        pending.english_word = head_word
        pending.definition = definition.strip()
        pending.example_sentences = serialize_example_sentences([sample_sentence, *queued_examples])
        pending.pos_subtype = pos_subtype
        pending.translations = serialize_translations(translations)

        outcome = approve_pending_import(
            session=session,
            pending_import_id=pending_id,
            data_source_config=self.config,
            model=self.config.model or constants.DEFAULT_MODEL,
            disambiguation=disambiguation or None,
        )
        lemma_id = outcome.get("lemma_id")
        if not outcome.get("success"):
            session.rollback()

        return {
            "action": "approved",
            "success": bool(outcome.get("success")),
            "lemma_id": lemma_id,
            "error": outcome.get("error"),
        }

    @staticmethod
    def leave_in_queue(reason: str) -> Dict[str, Any]:
        return {"action": "left_in_queue", "success": True, "reason": reason}


def print_dry_run(config: DataSourceConfig, limit: int, pending_ids: Sequence[int]) -> None:
    """Print the rows a run would review, making no LLM calls."""
    session = create_backend_session(config, readonly=True)
    try:
        rows = select_pending_rows(session, limit, pending_ids)
        print(f"Rows selected for review: {len(rows)}")
        for pending in rows:
            senses = existing_senses_for(session, pending.queried_word)
            print(
                f"  [{pending.id}] {pending.queried_word or '(no queried word)'} "
                f"-> {pending.english_word} ({pending.pos_type}/{pending.pos_subtype}); "
                f"{len(senses)} existing sense(s) of the queried word"
            )
    finally:
        session.close()
    print("\nDry run: no LLM calls made. Re-run without --dry-run to review.")


def print_results(results: Sequence[Dict[str, Any]]) -> None:
    """Print one line per reviewed row, then a verdict tally."""
    print()
    for result in results:
        decision = result["decision"]
        verdict = decision.get("verdict", "(no verdict)")
        detail = ""
        if verdict == VERDICT_DUPLICATE:
            detail = f"of lemma {decision.get('duplicate_of_lemma_id')}"
        elif verdict == VERDICT_DISTINCT:
            detail = (
                f"as {decision.get('head_word')!r} "
                f"[{decision.get('disambiguation') or 'no disambiguation'}]: "
                f"{decision.get('sample_sentence')}"
            )
        outcome = result.get("outcome") or {}
        applied = outcome.get("action", "")
        if applied and not outcome.get("success"):
            applied = f"{applied} FAILED: {outcome.get('error')}"
        elif applied == "approved" and outcome.get("lemma_id"):
            applied = f"approved -> lemma {outcome['lemma_id']}"
        elif outcome.get("reason"):
            applied = f"{applied} ({outcome['reason']})"
        print(
            f"  [{result['pending_id']}] {result['proposed_head_word']:<22} "
            f"{verdict:<10} {detail}"
        )
        if decision.get("reasoning"):
            print(f"       {decision['reasoning']}")
        if applied:
            print(f"       => {applied}")

    tally: Dict[str, int] = {}
    for result in results:
        verdict = result["decision"].get("verdict", "(no verdict)")
        tally[verdict] = tally.get(verdict, 0) + 1
    print("\nVerdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Review pending imports whose proposed head word is not yet a lemma, "
            "and approve, reject or leave each one. --dry-run lists the rows and "
            "makes no LLM calls."
        )
    )
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"How many queued rows to review (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--pending-id",
        type=int,
        action="append",
        default=[],
        dest="pending_ids",
        help="Review this specific pending row; repeatable. Overrides --limit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the full decisions to this path as JSON.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = get_data_source_config(args)

    if args.dry_run:
        print_dry_run(config, args.limit, args.pending_ids)
        return 0

    agent = JonvabalisAgent(config)
    results = agent.review(limit=args.limit, pending_ids=args.pending_ids)
    print_results(results)

    if args.output:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Decisions written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
