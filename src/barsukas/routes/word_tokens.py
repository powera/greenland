#!/usr/bin/python3

"""Routes for browsing word tokens: the surface string rather than the sense.

Two views, both anchored on ``WordToken``:

* ``/word-tokens/`` and ``/word-tokens/<id>`` -- one surface string, the lemmas
  that use it, and its standing in every corpus. This is the string-level
  counterpart to the lemma page: "top" is one entry here and three there.
* ``/word-tokens/corpus-skew`` -- per corpus, the words that lean toward it.
  The cooking vocabulary, the science vocabulary.
"""

from typing import Any, Dict, List, Optional

from flask import Blueprint, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from storage.word_token_view import (
    WordTokenView,
    get_word_token_view,
    get_word_token_view_by_text,
    search_word_tokens,
)
from wordfreq.frequency.corpus import get_corpus_config, get_enabled_corpus_names
from wordfreq.frequency.corpus_skew import (
    ExclusiveWord,
    SkewedWord,
    exclusive_words,
    score_corpus_skew,
    score_zipf_steadiness,
)

bp = Blueprint("word_tokens", __name__, url_prefix="/word-tokens")

# The corpora are English-only today, but the token table is keyed by language,
# so the language is a parameter rather than a constant.
DEFAULT_LANGUAGE: str = "en"

SKEW_PAGE_SIZE: int = 100
EXCLUSIVE_PAGE_SIZE: int = 50
STEADY_PAGE_SIZE: int = 200


def _corpus_options() -> List[Dict[str, Any]]:
    """Enabled corpora with their descriptions, for the picker."""
    options: List[Dict[str, Any]] = []
    for name in get_enabled_corpus_names():
        config = get_corpus_config(name)
        options.append(
            {
                "name": name,
                "description": config.description if config else name,
                "weight": config.corpus_weight if config else None,
            }
        )
    return options


@bp.route("/")
def index() -> ResponseReturnValue:
    """Search for a surface string, or land on the search box.

    An exact hit goes straight to the detail page, since ``(token, language)``
    is unique and a one-result list would be a wasted click.
    """
    query_text = request.args.get("q", "").strip()
    language_code = request.args.get("language", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE

    matches = []
    if query_text:
        exact = get_word_token_view_by_text(g.db, query_text, language_code, include_shares=False)
        if exact is not None:
            return redirect(url_for("word_tokens.detail", word_token_id=exact.word_token.id))
        matches = search_word_tokens(g.db, query_text, language_code)

    return render_template(
        "word_tokens/index.html",
        query_text=query_text,
        language_code=language_code,
        matches=matches,
        corpus_options=_corpus_options(),
    )


@bp.route("/<int:word_token_id>")
def detail(word_token_id: int) -> ResponseReturnValue:
    """One surface string: its lemmas, their frequency shares, its corpora."""
    view: Optional[WordTokenView] = get_word_token_view(g.db, word_token_id)
    if view is None:
        return render_template("word_tokens/detail.html", view=None), 404

    # Corpus rows carry the corpus description so the page can explain what
    # "religious_translated" is without the reader opening the config.
    corpus_descriptions: Dict[str, str] = {}
    for stat in view.wordfreq_stats:
        if stat.corpus_name and stat.corpus_name not in corpus_descriptions:
            config = get_corpus_config(stat.corpus_name)
            if config is not None:
                corpus_descriptions[stat.corpus_name] = config.description

    return render_template(
        "word_tokens/detail.html",
        view=view,
        corpus_descriptions=corpus_descriptions,
    )


@bp.route("/corpus-skew")
def corpus_skew() -> ResponseReturnValue:
    """Words that are more common in one corpus than in the rest.

    Sorted by the Zipf delta, which is what makes the comparison sound across
    corpora of different sizes; the ranks are shown beside it because "rank 36
    here against 7399 elsewhere" is the readable form of the same fact.
    """
    corpus_names = get_enabled_corpus_names()
    selected = request.args.get("corpus", "").strip()
    if selected not in corpus_names:
        selected = corpus_names[0] if corpus_names else ""

    language_code = request.args.get("language", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    show_exclusive = request.args.get("exclusive", "").strip() == "1"

    try:
        min_others = int(request.args.get("min_others", "1"))
    except ValueError:
        min_others = 1
    min_others = max(0, min(min_others, max(len(corpus_names) - 1, 0)))

    skewed: List[SkewedWord] = []
    exclusive: List[ExclusiveWord] = []
    if selected:
        skewed = score_corpus_skew(
            g.db,
            selected,
            language_code=language_code,
            min_other_corpora=min_others,
            limit=SKEW_PAGE_SIZE,
        )
        if show_exclusive:
            exclusive = exclusive_words(
                g.db,
                selected,
                language_code=language_code,
                limit=EXCLUSIVE_PAGE_SIZE,
            )

    config = get_corpus_config(selected) if selected else None
    other_corpora = [name for name in corpus_names if name != selected]

    return render_template(
        "word_tokens/corpus_skew.html",
        corpus_options=_corpus_options(),
        selected_corpus=selected,
        selected_description=config.description if config else "",
        other_corpora=other_corpora,
        language_code=language_code,
        skewed=skewed,
        exclusive=exclusive,
        show_exclusive=show_exclusive,
        min_others=min_others,
        max_min_others=max(len(corpus_names) - 1, 0),
    )


@bp.route("/steady")
def steady() -> ResponseReturnValue:
    """Words whose frequency barely moves between corpora.

    The complement of the skew page. Defaults to requiring every corpus,
    because a standard deviation over four measurements is not comparable to
    one over six.
    """
    corpus_names = get_enabled_corpus_names()
    language_code = request.args.get("language", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    require_all = request.args.get("require_all", "1").strip() != "0"

    raw_max_rank = request.args.get("max_rank", "").strip()
    max_rank: Optional[int] = None
    if raw_max_rank:
        try:
            max_rank = int(raw_max_rank)
        except ValueError:
            max_rank = None
        if max_rank is not None and max_rank < 1:
            max_rank = None

    try:
        min_corpora = int(request.args.get("min_corpora", "2"))
    except ValueError:
        min_corpora = 2
    min_corpora = max(2, min(min_corpora, max(len(corpus_names), 2)))

    steady_words = score_zipf_steadiness(
        g.db,
        language_code=language_code,
        require_all=require_all,
        min_corpora=min_corpora,
        max_rank=max_rank,
        limit=STEADY_PAGE_SIZE,
    )

    return render_template(
        "word_tokens/steady.html",
        corpus_options=_corpus_options(),
        corpus_names=corpus_names,
        language_code=language_code,
        require_all=require_all,
        min_corpora=min_corpora,
        max_rank=max_rank,
        steady_words=steady_words,
    )
