"""Keep mechanically-derivable forms out of the release files.

``data/release`` deliberately carries only the forms the rules cannot derive:
a Lithuanian verb ships as three grammar facts (infinitive, 3s_present,
3s_past) rather than a 27-form paradigm, and a regular noun ships as its
nominative singular.  ``generate_mechanical_forms`` puts the derivable ones
back after an import, and ``storage.admin.bootstrap`` calls it, so a
bootstrapped database holds the full paradigms.

That makes the export the place the invariant has to be enforced.  Without
this filter a round trip -- import a release, then export it again -- writes
every generated form back out, roughly doubling the tree with rows the next
import would regenerate anyway.

The test is *value* equality, not slot presence.  A form is dropped only when
the generator would produce that same spelling for that same slot; an
irregular whose stored text differs from what the rule predicts is exactly the
form the release exists to carry, so it stays.  Comparing spellings rather
than slots is what keeps a suppletive paradigm ("go"/"went") in the files even
though the rules would happily emit "goed" for the same slot.

The paradigm comes from ``build_for_lemma``, the same entry point the
generator uses, so the two cannot drift: whatever the generator would write on
the next import is precisely what is withheld here.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

__all__ = ["derivable_form_keys", "is_derivable"]

# (lemma_id, language_code) -> the (grammatical_form, text) pairs the rules
# reproduce for it.  An export walks every lemma once per language, so the
# paradigm would otherwise be rebuilt for each form on the line.
_CACHE: Dict[Tuple[int, str], Set[Tuple[str, str]]] = {}


def derivable_form_keys(session: Session, lemma: Any, language_code: str) -> Set[Tuple[str, str]]:
    """Return the ``(grammatical_form, text)`` pairs the rules regenerate.

    An empty set means nothing about this lemma is derivable in this language
    -- the rules declined it, or the language has no builder -- so every form
    it has must be written to the release files.
    """
    cache_key = (lemma.id, language_code)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    derivable: Set[Tuple[str, str]] = set()
    # Imported lazily: generate_mechanical_forms pulls in every langtools
    # builder, which is far too much to load for an export that may write no
    # forms at all.
    from wordfreq.tools.generate_mechanical_forms import (
        SUPPORTED,
        build_for_lemma,
        resolve_grammatical_form,
    )

    pos_type = lemma.pos_type.lower()
    if pos_type in SUPPORTED.get(language_code, ()):
        paradigm: Optional[Dict[str, str]] = build_for_lemma(session, lemma, language_code)
        if paradigm:
            for form_key, form_text in paradigm.items():
                grammatical_form = resolve_grammatical_form(language_code, pos_type, form_key)
                if grammatical_form is None or not form_text or not form_text.strip():
                    continue
                derivable.add((grammatical_form, form_text.strip()))

    _CACHE[cache_key] = derivable
    return derivable


def is_derivable(session: Session, lemma: Any, form: Any) -> bool:
    """Whether *form* is one the rules would regenerate on the next import.

    A form carrying a pronunciation is never derivable, however ordinary its
    spelling.  The builders produce text only, so withholding "happy" because
    the rules can spell it would take its ``/ˈhæp.i/`` with it and the next
    import could not put it back.
    """
    if form.ipa_pronunciation or form.phonetic_pronunciation:
        return False
    keys = derivable_form_keys(session, lemma, form.language_code)
    if not keys:
        return False
    return (form.grammatical_form, (form.derivative_form_text or "").strip()) in keys


def without_derivable(session: Session, lemma: Any, forms: Iterable[Any]) -> List[Any]:
    """Drop the forms the rules regenerate, keeping the order given."""
    return [form for form in forms if not is_derivable(session, lemma, form)]


def clear_cache() -> None:
    """Forget memoized paradigms, so a later export re-reads changed facts."""
    _CACHE.clear()
