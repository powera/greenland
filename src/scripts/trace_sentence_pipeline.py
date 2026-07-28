#!/usr/bin/env python3
"""Run one sentence through the translate-and-decompose pipeline, out loud.

Every phase prints what it sent, what came back, and what was written to the
database. The pipeline normally reports only a summary, which is fine in bulk
but useless when a single sentence comes out wrong: a mis-linked lemma or a
dropped word is invisible until someone reads ``sentence_words`` by hand.

The token accounting is the other reason this exists. Phases 3 and 4 size their
requests from an estimate of the response (see ``sentences.token_estimates``),
and an estimate nobody checks is a guess. Each phase prints estimated vs. actual
output tokens and the ratio, so the constants can be tuned against real
responses rather than arithmetic:

    Phase 3   estimated 22300  requested 30205  actual 4182  (est/actual 5.33x)

A ratio far above 1 means the estimate is wasteful; below 1 means it is
dangerous, since the request would have been truncated. Numbers land in the
"Token accounting" summary at the end of the run.

This makes real LLM calls and costs real money. It writes to the database by
default because the point is to exercise the storage path -- column types,
coercion, NULL handling -- that a print-and-exit script leaves untested. Use
--dry-run to skip persistence, and GREENLAND_DISABLE_LLM=1 to block the calls
entirely (the run then fails loudly rather than reaching a paid backend).

Examples:
    PYTHONPATH=src python src/scripts/trace_sentence_pipeline.py \\
        --sentence "The probate court has jurisdiction." --language en

    PYTHONPATH=src python src/scripts/trace_sentence_pipeline.py \\
        --sentence "..." --language en \\
        --decompose-languages en,fr,es --annotate-dependencies
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from clients.lib import limit_from_estimate
from clients.unified_client import UnifiedLLMClient
from sentences.token_estimates import (
    estimate_decomposition_output_tokens,
    estimate_dependency_output_tokens,
    estimate_translation_output_tokens,
)
from sentences.translate_and_decompose import (
    DEFAULT_MODEL,
    TranslateAndDecomposeResult,
    annotate_dependencies_for_result,
    decompose_with_existing_translations,
    lookup_candidate_lemmas,
    translate_sentence_text,
)
from sentences.translation import store_translation_results
from storage.backend.factory import create_session
from storage.crud.sentence import add_sentence
from storage.models.schema import SentenceTranslation, SentenceWord

_RULE = "=" * 78
_THIN = "-" * 78


class RecordingClient(UnifiedLLMClient):
    """A real client that also records what each call requested and got back.

    The pipeline does not surface per-call usage to its callers, and the whole
    point here is comparing the estimate against the actual response size, so
    the numbers are captured at the one place every phase passes through.
    Subclasses rather than wraps so the pipeline's type expectations hold and
    every other method behaves exactly as in production.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, *args: Any, **kwargs: Any) -> Any:
        response = super().generate_chat(*args, **kwargs)
        usage = getattr(response, "usage", None)
        self.calls.append(
            {
                "max_tokens": kwargs.get("max_tokens"),
                "tokens_in": getattr(usage, "tokens_in", None),
                "tokens_out": getattr(usage, "tokens_out", None),
            }
        )
        return response

    def tokens_out_since(self, index: int) -> Optional[int]:
        """Total output tokens across calls made after ``index``."""
        recent = [
            call["tokens_out"] for call in self.calls[index:] if isinstance(call["tokens_out"], int)
        ]
        return sum(recent) if recent else None


class TokenLedger:
    """Records estimated vs. actual output tokens for each phase."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def record(
        self, phase: str, estimated: Optional[int], requested: Optional[int], actual: Optional[int]
    ) -> None:
        self.rows.append(
            {"phase": phase, "estimated": estimated, "requested": requested, "actual": actual}
        )

    def report(self) -> None:
        print()
        print(_RULE)
        print("Token accounting")
        print(_RULE)
        if not self.rows:
            print("  (no phases ran)")
            return
        print(f"  {'phase':<24}{'estimated':>11}{'requested':>11}{'actual':>9}  ratio")
        for row in self.rows:
            estimated = row["estimated"]
            actual = row["actual"]
            if estimated is not None and isinstance(actual, int) and actual > 0:
                ratio = f"{estimated / actual:.2f}x"
            else:
                ratio = "-"
            print(
                f"  {row['phase']:<24}"
                f"{_fmt(estimated):>11}{_fmt(row['requested']):>11}{_fmt(actual):>9}  {ratio}"
            )
        print()
        print(
            "  ratio = estimated / actual. Well above 1.0 means the estimate is\n"
            "  wasteful; below 1.0 means the request would have been truncated."
        )


def _fmt(value: Optional[int]) -> str:
    return "-" if value is None else str(value)


def _heading(text: str) -> None:
    print()
    print(_RULE)
    print(text)
    print(_RULE)


def _print_words(words: Sequence[Dict[str, Any]]) -> None:
    if not words:
        print("    (no words returned)")
        return
    header = f"    {'pos':>3}  {'surface':<18}{'lemma_guid':<12}{'part_of_speech':<16}gloss"
    print(header)
    for word in words:
        guid = str(word.get("lemma_guid", ""))
        # A synthetic id means the model found no matching lemma in the DB; a
        # real GUID is a claim about an existing one and is what goes wrong
        # silently, so flag it for the reader.
        marker = " " if guid.startswith("SYN") or not guid else "*"
        print(
            f"  {marker} {str(word.get('position', '')):>3}  "
            f"{str(word.get('surface_form', '')):<18}"
            f"{guid:<12}"
            f"{str(word.get('part_of_speech', '')):<16}"
            f"{word.get('english_gloss', '')}"
        )
    print("    (* = linked to an existing database lemma; verify these)")


def trace_pipeline(args: argparse.Namespace) -> int:
    config = get_data_source_config(args, default_model=args.model)
    session = create_session(config)
    client = RecordingClient(
        debug=args.debug,
        openai_api_key=config.openai_api_key,
        anthropic_api_key=config.anthropic_api_key,
        google_api_key=config.google_api_key,
    )
    ledger = TokenLedger()

    source_text = args.sentence.strip()
    source_language = args.language
    target_languages = [lang.strip() for lang in args.target_languages.split(",") if lang.strip()]
    decompose_languages = [
        lang.strip() for lang in args.decompose_languages.split(",") if lang.strip()
    ]

    _heading("Input")
    print(f"  sentence          : {source_text!r}")
    print(f"  source language   : {source_language}")
    print(f"  target languages  : {', '.join(target_languages)}")
    print(f"  decompose         : {', '.join(decompose_languages)}")
    print(f"  model             : {args.model}")
    print(f"  persist to db     : {not args.dry_run}")

    result = TranslateAndDecomposeResult(
        source_sentence=source_text, source_language=source_language
    )

    # ----------------------------------------------------------------- Phase 1
    _heading("Phase 1 - sentence translation (LLM)")
    phase1_estimate = estimate_translation_output_tokens(
        source_text=source_text,
        source_language=source_language,
        target_languages=target_languages,
    )
    print(f"  estimated output tokens : {phase1_estimate}")
    print(f"  requested max_tokens    : {limit_from_estimate(phase1_estimate)}")

    phase1_mark = len(client.calls)
    translations = translate_sentence_text(
        sentence_text=source_text,
        source_language=source_language,
        target_languages=target_languages,
        client=client,
        model=args.model,
    )
    if not translations:
        print("  FAILED: Phase 1 returned no translations; nothing further to do.")
        ledger.report()
        return 1
    result.translations = dict(translations)
    ledger.record(
        "Phase 1 translate",
        phase1_estimate,
        limit_from_estimate(phase1_estimate),
        client.tokens_out_since(phase1_mark),
    )

    print()
    for language_code, text in translations.items():
        print(f"  {language_code:<4} {text}")

    # ----------------------------------------------------------------- Phase 2
    _heading("Phase 2 - candidate lemma lookup (database, no LLM)")
    candidates = lookup_candidate_lemmas(
        session=session,
        translations=translations,
        source_languages=list(translations.keys()),
    )
    result.candidate_lemmas = list(candidates)
    print(f"  {len(candidates)} candidate lemma(s) offered to Phase 3")
    print()
    if candidates:
        print(f"  {'guid':<12}{'lemma':<20}{'score':>5}  matched languages")
        for candidate in candidates:
            print(
                f"  {candidate.guid:<12}{candidate.lemma_text:<20}"
                f"{candidate.match_score:>5}  {', '.join(candidate.matched_languages)}"
            )
        print()
        print(
            "  NOTE: match_score is a sort key, never a threshold. A candidate\n"
            "  confirmed by one language can still be adopted by Phase 3 even when\n"
            "  other languages disagree -- that is how a zh homograph linked\n"
            "  'procedure' to the lemma 'program'."
        )

    # ----------------------------------------------------------------- Phase 3
    _heading("Phase 3 - word decomposition (LLM)")
    target_translations = {
        lang: translations[lang] for lang in decompose_languages if lang in translations
    }
    missing = [lang for lang in decompose_languages if lang not in translations]
    if missing:
        print(f"  skipping (no Phase 1 translation): {', '.join(missing)}")
    phase3_estimate = estimate_decomposition_output_tokens(target_translations=target_translations)
    print(f"  estimated output tokens : {phase3_estimate}")
    print(f"  requested max_tokens    : {limit_from_estimate(phase3_estimate)}")

    phase3_mark = len(client.calls)
    decompose_with_existing_translations(
        sentence_text=source_text,
        source_language=source_language,
        translations=translations,
        session=session,
        client=client,
        decompose_languages=list(target_translations.keys()),
        model=args.model,
        result=result,
    )
    phase3_actual = client.tokens_out_since(phase3_mark)

    for language_code, decomposition in result.decompositions.items():
        print()
        print(f"  --- {language_code} " + _THIN[: 74 - len(language_code)])
        print(f"    translation : {decomposition.translation}")
        print(f"    success     : {decomposition.success}")
        if decomposition.error:
            print(f"    error       : {decomposition.error}")
        if decomposition.missing_surface_forms:
            # Tokens present in the translation but absent from the breakdown.
            # A trailing run of these is the signature of a truncated response.
            print(f"    MISSING     : {', '.join(decomposition.missing_surface_forms)}")
        print(f"    words       : {len(decomposition.words)}")
        _print_words(decomposition.words)

    ledger.record(
        "Phase 3 decompose",
        phase3_estimate,
        limit_from_estimate(phase3_estimate),
        phase3_actual,
    )

    # ----------------------------------------------------------------- Phase 4
    if args.annotate_dependencies:
        _heading("Phase 4 - Universal Dependencies (LLM, one call per language)")
        total_estimate = 0
        for language_code, decomposition in result.decompositions.items():
            if not decomposition.success or not decomposition.words:
                continue
            estimate = estimate_dependency_output_tokens(word_count=len(decomposition.words))
            total_estimate += estimate
            print(
                f"  {language_code}: {len(decomposition.words)} words, "
                f"estimated {estimate}, requested {limit_from_estimate(estimate)}"
            )

        phase4_mark = len(client.calls)
        annotated = annotate_dependencies_for_result(result=result, client=client, model=args.model)
        phase4_actual = client.tokens_out_since(phase4_mark)

        print()
        for language_code, decomposition in result.decompositions.items():
            status = "annotated" if decomposition.ud_annotated else "NOT annotated"
            print(f"  {language_code}: {status}")
            if decomposition.ud_error:
                # The distinction the pipeline used to discard: a rejected tree
                # and a tree that was never requested both leave zero UD rows.
                print(f"    reason: {decomposition.ud_error}")
            if decomposition.ud_annotated:
                for word in decomposition.words:
                    print(
                        f"      {str(word.get('position', '')):>3}  "
                        f"{str(word.get('surface_form', '')):<18}"
                        f"{str(word.get('ud_relation', '')):<12}"
                        f"head={word.get('ud_head_position')}"
                    )
        ledger.record("Phase 4 dependencies", total_estimate, None, phase4_actual)
        print()
        print(f"  annotated {sum(1 for ok in annotated.values() if ok)}/{len(annotated)} languages")

    # ---------------------------------------------------------------- Persist
    _heading("Database writes")
    if args.dry_run:
        print("  --dry-run: nothing written.")
    else:
        sentence = add_sentence(
            session,
            source_filename=args.source_filename,
            notes=f"trace_sentence_pipeline: {source_text[:60]}",
        )
        session.flush()
        print(f"  created Sentence id={sentence.id} guid={sentence.guid}")

        # Flatten into the {lang: text, words_lang: [...]} shape the ordinary
        # persistence path consumes, so this exercises the same writer the real
        # callers use rather than a bespoke one.
        payload: Dict[str, Any] = dict(result.translations)
        for language_code, decomposition in result.decompositions.items():
            if not decomposition.success:
                print(f"  skipping words_{language_code}: decomposition failed")
                continue
            payload[f"words_{language_code}"] = list(decomposition.words)

        store_translation_results(sentence.id, payload, session)
        session.commit()

        stored_translations = (
            session.query(SentenceTranslation).filter_by(sentence_id=sentence.id).all()
        )
        stored_words = session.query(SentenceWord).filter_by(sentence_id=sentence.id).all()
        print(f"  wrote {len(stored_translations)} SentenceTranslation row(s)")
        print(f"  wrote {len(stored_words)} SentenceWord row(s)")
        print()
        by_language: Dict[str, int] = {}
        linked = 0
        for word_row in stored_words:
            language_key = word_row.language_code
            by_language[language_key] = by_language.get(language_key, 0) + 1
            if word_row.lemma_id is not None:
                linked += 1
        for language_code, count in sorted(by_language.items()):
            print(f"    {language_code}: {count} word(s)")
        print(f"    {linked} of {len(stored_words)} word(s) linked to an existing lemma")

    ledger.report()
    return 0


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one sentence through the pipeline, printing every step",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_args(parser)
    add_llm_args(parser, default_model=DEFAULT_MODEL)
    add_backend_args(parser)

    parser.add_argument("--sentence", required=True, help="Sentence text to process")
    parser.add_argument(
        "--language", default="en", help="Source language code of the sentence (default: en)"
    )
    parser.add_argument(
        "--target-languages",
        default="en,es,fr,zh,lt",
        help="Comma-separated Phase-1 target languages (default: en,es,fr,zh,lt)",
    )
    parser.add_argument(
        "--decompose-languages",
        default="en",
        help=(
            "Comma-separated languages to decompose in Phase 3. Each must be a "
            "Phase-1 target. Default 'en' matches what genys does today."
        ),
    )
    parser.add_argument(
        "--annotate-dependencies",
        action="store_true",
        help="Run the Phase-4 UD pass; costs one extra LLM call per language",
    )
    parser.add_argument(
        "--source-filename",
        default="trace_sentence_pipeline",
        help="Value stored in Sentence.source_filename",
    )
    # --dry-run and --debug come from add_common_args.
    return parser


def main() -> int:
    args = get_argument_parser().parse_args()
    return trace_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
