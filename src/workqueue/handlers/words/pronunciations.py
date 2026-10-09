"""Capability handlers for word pronunciation tasks.

``PRONUNCIATIONS_JOB`` is the staged-job form ``workqueue.llm_batch`` runs as
OpenAI batches (``papuga --populate --batch``), one item per (lemma, language),
grouped the way papuga's populate path groups its live calls:

1. ``pronunciations.forms``: one call for the lemma's forms -- the grouped
   prompt when there are several.
2. ``pronunciations.lemma``: the translation's (or English base form's) own
   pronunciation, prepared after every item's forms are stored, so it is
   usually copied from the base form with no call at all.

Both store through store_target_pronunciation, which records an answer below
PRONUNCIATION_MIN_CONFIDENCE as uncertain; planning skips those words unless
the state says ``retry_uncertain``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall
from storage.models.schema import Lemma
from words.llm_validators import (
    build_batch_pronunciation_call,
    build_pronunciation_call,
    interpret_batch_pronunciations,
    interpret_pronunciation,
)
from words.pronunciation_generation import (
    PronunciationTarget,
    generate_pronunciations_for_lemma,
    get_example_sentence_for_lemma,
    plan_pronunciation_targets,
    store_target_pronunciation,
    target_still_needed,
)
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_pronunciations(
    session: Any,
    lemma_id: int,
    language_code: str = "en",
    lang_code: Optional[str] = None,
    base_forms_only: bool = False,
    all_forms_pronunciation: bool = False,
    **_: Any,
) -> str:
    """Generate pronunciations for all missing forms on a lemma.

    Like the forms and translations queue handlers, it asks again for words a
    model was uncertain of; a new answer is still gated on its confidence.
    """
    effective_language_code = lang_code or language_code
    lemma = get_lemma_or_raise(session, lemma_id)
    generated_count, errors = generate_pronunciations_for_lemma(
        session,
        lemma,
        effective_language_code,
        base_forms_only=base_forms_only,
        all_forms_pronunciation=all_forms_pronunciation,
        retry_uncertain=True,
    )
    session.commit()

    if generated_count == 0 and not errors:
        return f"No missing pronunciations for {effective_language_code} forms"
    if generated_count == 0 and errors:
        raise RuntimeError("; ".join(errors))
    return f"Generated pronunciations for {generated_count} form(s)"


@workqueue_payload_handler()
def handle_words_pronunciations(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[list[int]] = None,
    language_code: str = "en",
    lang_code: Optional[str] = None,
    base_forms_only: bool = False,
    all_forms_pronunciation: bool = False,
    **_: Any,
) -> str:
    """Workqueue wrapper for pronunciation generation.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    if lemma_ids:
        results = [
            do_generate_pronunciations(
                session=session,
                lemma_id=queued_lemma_id,
                language_code=language_code,
                lang_code=lang_code,
                base_forms_only=base_forms_only,
                all_forms_pronunciation=all_forms_pronunciation,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_pronunciations(
        session=session,
        lemma_id=lemma_id,
        language_code=language_code,
        lang_code=lang_code,
        base_forms_only=base_forms_only,
        all_forms_pronunciation=all_forms_pronunciation,
    )


# ---------------------------------------------------------------------------
# Staged-job form, for batching (see workqueue.llm_batch)
# ---------------------------------------------------------------------------

PRONUNCIATIONS_JOB_NAME = "papuga"
FORMS_STAGE = "pronunciations.forms"
LEMMA_STAGE = "pronunciations.lemma"

# Ready markers: no forms to do in stage 1; a translation whose values are known.
_NO_FORMS = "__no_forms__"
_KNOWN = "__known_pronunciation__"


def pronunciation_state(
    lemma_id: int,
    language_code: str,
    base_forms_only: bool = False,
    all_forms_pronunciation: bool = False,
    retry_uncertain: bool = False,
) -> Dict[str, Any]:
    """The item state the pronunciation job works on: one lemma in one language."""
    return {
        "lemma_id": lemma_id,
        "language_code": language_code,
        "base_forms_only": base_forms_only,
        "all_forms_pronunciation": all_forms_pronunciation,
        "retry_uncertain": retry_uncertain,
    }


def _targets(session: Session, lemma: Lemma, state: Dict[str, Any]) -> List[PronunciationTarget]:
    return plan_pronunciation_targets(
        session,
        lemma,
        state["language_code"],
        base_forms_only=bool(state.get("base_forms_only")),
        all_forms_pronunciation=bool(state.get("all_forms_pronunciation")),
        retry_uncertain=bool(state.get("retry_uncertain")),
    )


def _form_entries(targets: List[PronunciationTarget]) -> List[Dict[str, Any]]:
    return [
        {"form": target.grammatical_form or "", "word": target.word, "form_id": target.form_id}
        for target in targets
        if target.kind == "form"
    ]


def _prepare_forms(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    """Stage 1: one call for the lemma's forms -- grouped when there are several."""
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    language_code = state["language_code"]
    targets = _targets(session, lemma, state)
    if not targets:
        return Done("skipped", "nothing missing")
    forms = _form_entries(targets)
    if not forms:
        return Ready({_NO_FORMS: True})
    english_translation = lemma.lemma_text if language_code != "en" else None
    # Apply matches answers to exactly these forms.
    state["forms"] = forms
    if len(forms) == 1:
        return build_pronunciation_call(
            word=forms[0]["word"],
            ipa_pronunciation=None,
            phonetic_pronunciation=None,
            pos_type=lemma.pos_type,
            example_sentence=get_example_sentence_for_lemma(session, lemma.id),
            definition=lemma.definition_text,
            language_code=language_code,
            grammatical_form=forms[0]["form"],
            english_translation=english_translation,
        )
    return build_batch_pronunciation_call(
        lemma=lemma.lemma_text,
        definition=lemma.definition_text or "",
        pos_type=lemma.pos_type,
        forms=[{"form": form["form"], "word": form["word"]} for form in forms],
        language_code=language_code,
        english_translation=english_translation,
    )


def _store_form_answers(
    session: Session,
    lemma: Lemma,
    state: Dict[str, Any],
    data: Dict[str, Any],
    model: Optional[str],
) -> Tuple[int, int]:
    """Write stage-1 answers; returns ``(written, rejected)``."""
    forms = state["forms"]
    if len(forms) > 1:
        results = interpret_batch_pronunciations(
            data, [{"form": form["form"], "word": form["word"]} for form in forms]
        )
        answers = [(form, results[form["form"]]) for form in forms]
    else:
        single = interpret_pronunciation(data, state["language_code"])
        answers = [
            (
                forms[0],
                {
                    "ipa_pronunciation": single.get("suggested_ipa"),
                    "phonetic_pronunciation": single.get("suggested_phonetic"),
                    "confidence": single.get("confidence", 0.0),
                },
            )
        ]
    written = rejected = 0
    for form, answer in answers:
        target = PronunciationTarget(
            kind="form",
            lemma_id=lemma.id,
            language_code=state["language_code"],
            word=form["word"],
            # As planned, so the uncertainty is recorded under the same question.
            grammatical_form=form["form"] or None,
            form_id=form["form_id"],
        )
        # Someone may have entered it by hand while the batch ran; theirs stays.
        if not target_still_needed(session, lemma, target):
            continue
        if store_target_pronunciation(
            session,
            lemma,
            target,
            answer.get("ipa_pronunciation") or None,
            answer.get("phonetic_pronunciation") or None,
            confidence=float(answer.get("confidence") or 0.0),
            model=model,
        ):
            written += 1
        else:
            rejected += 1
    return written, rejected


def _apply_forms(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    written = rejected = 0
    if not data.get(_NO_FORMS):
        written, rejected = _store_form_answers(session, lemma, state, data, ctx.model)
        session.flush()
    remaining = [t for t in _targets(session, lemma, state) if t.kind != "form"]
    if not remaining:
        if written:
            return Done("written", f"{written} form(s)")
        return Done("rejected" if rejected else "skipped", f"{rejected} below confidence")
    # The translation / English base form: often answerable now from the base
    # form stage 1 just filled, so it is prepared after the barrier.
    next_state = {key: value for key, value in state.items() if key != "forms"}
    return Next(next_state)


def _prepare_lemma(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    """Stage 2: the translation's (or English base form's) own pronunciation."""
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    remaining = [t for t in _targets(session, lemma, state) if t.kind != "form"]
    if not remaining:
        return Done("skipped", "nothing missing")
    target = remaining[0]
    state["target"] = target.to_state()
    if not target.needs_call:
        return Ready({_KNOWN: True})
    return build_pronunciation_call(
        word=target.word,
        ipa_pronunciation=None,
        phonetic_pronunciation=None,
        pos_type=lemma.pos_type,
        example_sentence=get_example_sentence_for_lemma(session, lemma.id),
        definition=lemma.definition_text,
        language_code=target.language_code,
        grammatical_form=target.grammatical_form,
        english_translation=(
            None
            if target.kind == "english_lemma" or target.language_code == "en"
            else lemma.lemma_text
        ),
    )


def _apply_lemma(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    target = PronunciationTarget.from_state(state["target"])
    if not target_still_needed(session, lemma, target):
        return Done("skipped", "pronunciation already present")
    ipa: Optional[str] = None
    phonetic: Optional[str] = None
    confidence: Optional[float] = None
    if not data.get(_KNOWN):
        result = interpret_pronunciation(data, target.language_code)
        ipa = result.get("suggested_ipa") or None
        phonetic = result.get("suggested_phonetic") or None
        if ipa or phonetic:
            confidence = float(result.get("confidence") or 0.0)
    stored = store_target_pronunciation(
        session, lemma, target, ipa, phonetic, confidence=confidence, model=ctx.model
    )
    if stored:
        return Done("written", f"{target.word}: {ipa or ''} {phonetic or ''}".strip())
    if stored is None and confidence is not None:
        return Done("rejected", f"{target.word!r} at confidence {confidence:.2f}")
    return Done("rejected", f"no pronunciation for {target.word!r}")


PRONUNCIATIONS_JOB = Job(
    name=PRONUNCIATIONS_JOB_NAME,
    stages=(
        Stage(FORMS_STAGE, _prepare_forms, _apply_forms),
        Stage(LEMMA_STAGE, _prepare_lemma, _apply_lemma),
    ),
    item_key=lambda state: f"{state['lemma_id']}:{state['language_code']}",
)
