#!/usr/bin/env python3
"""Backfill ``word_token_id`` on forms by matching surface form text.

A database built by ``bootstrap_database.py`` already has this link: the
bootstrap runs it between the corpus load and the rank calculation. This
script is the standalone repair path, for a database where forms were created
before their ``WordToken`` existed (e.g. a lemma added by hand, with the token
populated later by a wordfreq import).

The lexeme-frequency rollup walks ``lexeme.forms`` and skips any form with
``word_token_id IS NULL``, so those lemmas roll up zero even when the
underlying annotations exist -- and their combined rank silently falls back to
the tier sources alone.

The matching logic lives in ``wordfreq.lexeme_frequency`` so that this script,
the bootstrap, and the golden loader all share one implementation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend.factory import create_session
from storage.models.schema import DerivativeForm, WordToken
from wordfreq.lexeme_frequency import link_forms_to_word_tokens


def run(dry_run: bool, config_args: argparse.Namespace) -> int:
    config = get_data_source_config(config_args)
    session = create_session(config)
    try:
        if dry_run:
            pending = (
                session.query(DerivativeForm)
                .join(
                    WordToken,
                    (WordToken.token == DerivativeForm.derivative_form_text)
                    & (WordToken.language_code == DerivativeForm.language_code),
                )
                .filter(DerivativeForm.word_token_id.is_(None))
                .count()
            )
            print(f"Dry run: would link about {pending} derivative forms; nothing written")
            return pending

        counts = link_forms_to_word_tokens(session)
        unresolved = (
            session.query(DerivativeForm).filter(DerivativeForm.word_token_id.is_(None)).count()
        )
        print(f"Linked {counts['derivative_forms']} derivative forms to existing word tokens")
        print(f"Linked {counts['variant_forms']} variant forms to existing word tokens")
        print(f"Remaining derivative forms with no matching WordToken: {unresolved}")
        return counts["derivative_forms"]
    finally:
        session.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run, config_args=args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
