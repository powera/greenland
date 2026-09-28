#!/usr/bin/python3

"""Words at the top of several corpora, and the most common words just below them.

Two lists, both ordered by the combined corpus rank (``WordToken.frequency_rank``):

  * **core** -- tokens ranked in the top ``top_n`` (default 150) of at least
    ``min_corpora`` (default 3) enabled corpora. Agreement across corpora is
    the point: a word at the top of cooking and nowhere else is a domain word,
    while one at the top of three unrelated corpora is general vocabulary.
  * **runners-up** -- the ``runner_up_count`` (default 50) best combined ranks
    that are *not* in the core list. These are broadly common without leading
    enough corpora to qualify, so the combined rank is doing the work that the
    per-corpus cutoff did for the core.

Both lists are read-only and cheap: the core list reads only the annotation rows
at or above the cutoff, so the report also backs a Barsukas page rendered per
request (``/reports/broadly-common``).

Usage:
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/reports/broadly_common_words.py
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import ExternalLexemeAnnotation, WordToken
from wordfreq.frequency.corpus import get_enabled_corpus_names

WORDFREQ_SOURCE_PREFIX: str = "wordfreq_"

DEFAULT_TOP_N: int = 150
DEFAULT_MIN_CORPORA: int = 3
DEFAULT_RUNNER_UP_COUNT: int = 50


@dataclass
class BroadWord:
    """One token and where it stands in each corpus."""

    word_token_id: int
    token: str
    combined_rank: Optional[int]
    # {corpus_name: rank} for every enabled corpus that ranks the token.
    corpus_ranks: Dict[str, int] = field(default_factory=dict)
    # Corpora where the token is within the report's top_n, best rank first.
    top_corpora: List[str] = field(default_factory=list)

    @property
    def best_rank(self) -> Optional[int]:
        return min(self.corpus_ranks.values()) if self.corpus_ranks else None


@dataclass
class BroadlyCommonReport:
    """Both lists, plus the parameters that produced them."""

    language_code: str
    top_n: int
    min_corpora: int
    corpus_names: List[str]
    core: List[BroadWord]
    runners_up: List[BroadWord]


def _corpus_ranks_for_tokens(
    session: Session,
    token_ids: List[int],
    sources: Dict[str, str],
) -> Dict[int, Dict[str, int]]:
    """``{word_token_id: {corpus_name: rank}}`` for the given tokens and sources."""
    ranks: Dict[int, Dict[str, int]] = {}
    for start in range(0, len(token_ids), 500):
        chunk = token_ids[start : start + 500]
        rows = session.query(
            ExternalLexemeAnnotation.word_token_id,
            ExternalLexemeAnnotation.source,
            ExternalLexemeAnnotation.ordinal_rank,
        ).filter(
            ExternalLexemeAnnotation.word_token_id.in_(chunk),
            ExternalLexemeAnnotation.source.in_(list(sources.keys())),
            ExternalLexemeAnnotation.ordinal_rank.isnot(None),
        )
        for word_token_id, source, ordinal_rank in rows.all():
            corpus_ranks = ranks.setdefault(word_token_id, {})
            corpus_name = sources[source]
            # A token can carry more than one row per corpus; keep the best.
            previous = corpus_ranks.get(corpus_name)
            if previous is None or ordinal_rank < previous:
                corpus_ranks[corpus_name] = int(ordinal_rank)
    return ranks


def _combined_rank_sort_key(word: BroadWord) -> tuple[int, int, str]:
    # Unranked tokens sort after every ranked one rather than first.
    if word.combined_rank is None:
        return (1, 0, word.token)
    return (0, word.combined_rank, word.token)


def build_report(
    session: Session,
    *,
    language_code: str = "en",
    top_n: int = DEFAULT_TOP_N,
    min_corpora: int = DEFAULT_MIN_CORPORA,
    runner_up_count: int = DEFAULT_RUNNER_UP_COUNT,
) -> BroadlyCommonReport:
    """Build the core and runner-up lists over the enabled corpora."""
    corpus_names = get_enabled_corpus_names()
    sources: Dict[str, str] = {f"{WORDFREQ_SOURCE_PREFIX}{name}": name for name in corpus_names}

    top_rows = (
        session.query(
            ExternalLexemeAnnotation.word_token_id,
            ExternalLexemeAnnotation.source,
        )
        .join(WordToken, WordToken.id == ExternalLexemeAnnotation.word_token_id)
        .filter(
            ExternalLexemeAnnotation.source.in_(list(sources.keys())),
            ExternalLexemeAnnotation.ordinal_rank.isnot(None),
            ExternalLexemeAnnotation.ordinal_rank <= top_n,
            WordToken.language_code == language_code,
        )
        .all()
    )
    top_corpora_by_token: Dict[int, set[str]] = {}
    for word_token_id, source in top_rows:
        top_corpora_by_token.setdefault(word_token_id, set()).add(sources[source])

    core_ids = [
        word_token_id
        for word_token_id, top_corpora in top_corpora_by_token.items()
        if len(top_corpora) >= min_corpora
    ]

    runner_up_tokens: List[WordToken] = []
    if runner_up_count > 0:
        runner_up_query = session.query(WordToken).filter(
            WordToken.language_code == language_code,
            WordToken.frequency_rank.isnot(None),
        )
        if core_ids:
            runner_up_query = runner_up_query.filter(WordToken.id.notin_(core_ids))
        runner_up_tokens = (
            runner_up_query.order_by(WordToken.frequency_rank, WordToken.token)
            .limit(runner_up_count)
            .all()
        )

    core_tokens: List[WordToken] = (
        session.query(WordToken).filter(WordToken.id.in_(core_ids)).all() if core_ids else []
    )

    all_ids = [token.id for token in core_tokens] + [token.id for token in runner_up_tokens]
    ranks_by_token = _corpus_ranks_for_tokens(session, all_ids, sources)

    def to_word(token: WordToken) -> BroadWord:
        corpus_ranks = ranks_by_token.get(token.id, {})
        top_corpora = sorted(
            (name for name, rank in corpus_ranks.items() if rank <= top_n),
            key=lambda name: (corpus_ranks[name], name),
        )
        return BroadWord(
            word_token_id=token.id,
            token=token.token,
            combined_rank=token.frequency_rank,
            corpus_ranks=corpus_ranks,
            top_corpora=top_corpora,
        )

    core = sorted((to_word(token) for token in core_tokens), key=_combined_rank_sort_key)
    runners_up = [to_word(token) for token in runner_up_tokens]

    return BroadlyCommonReport(
        language_code=language_code,
        top_n=top_n,
        min_corpora=min_corpora,
        corpus_names=corpus_names,
        core=core,
        runners_up=runners_up,
    )


def report_to_dict(report: BroadlyCommonReport) -> Dict[str, object]:
    """JSON-ready form of the report, with each word's best rank included."""

    def word_dict(word: BroadWord) -> Dict[str, object]:
        data = asdict(word)
        data["best_rank"] = word.best_rank
        return data

    return {
        "language_code": report.language_code,
        "top_n": report.top_n,
        "min_corpora": report.min_corpora,
        "corpus_names": report.corpus_names,
        "core": [word_dict(word) for word in report.core],
        "runners_up": [word_dict(word) for word in report.runners_up],
    }


def _print_words(words: List[BroadWord], top_n: int) -> None:
    print(f"{'#':>4}  {'token':<16} {'combined':>8}  {'top-' + str(top_n):>7}  corpora")
    for index, word in enumerate(words, start=1):
        combined = str(word.combined_rank) if word.combined_rank is not None else "-"
        corpora = ", ".join(f"{name} {word.corpus_ranks[name]}" for name in word.top_corpora)
        print(f"{index:>4}  {word.token:<16} {combined:>8}  {len(word.top_corpora):>7}  {corpora}")


def print_report(report: BroadlyCommonReport) -> None:
    print(
        f"Top {report.top_n} in at least {report.min_corpora} of "
        f"{len(report.corpus_names)} corpora ({report.language_code}): {len(report.core)} words"
    )
    _print_words(report.core, report.top_n)
    print()
    print(f"Next {len(report.runners_up)} by combined rank, not in the list above")
    _print_words(report.runners_up, report.top_n)


def main() -> None:
    """Run the report from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("--language", default="en", help="Token language code (default: en)")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--min-corpora", type=int, default=DEFAULT_MIN_CORPORA)
    parser.add_argument("--runner-ups", type=int, default=DEFAULT_RUNNER_UP_COUNT)
    parser.add_argument("--output", type=Path, help="Also write the report as JSON")
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        report = build_report(
            session,
            language_code=args.language,
            top_n=args.top_n,
            min_corpora=args.min_corpora,
            runner_up_count=args.runner_ups,
        )
    finally:
        session.close()

    print_report(report)
    if args.output is not None:
        args.output.write_text(
            json.dumps(report_to_dict(report), indent=2, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
