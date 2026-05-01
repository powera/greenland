#!/usr/bin/env python3
"""Backfill ``DerivativeForm.word_token_id`` by matching surface form text.

Some derivative forms were created before their corresponding ``WordToken``
existed (e.g. lemma added in trakaido bootstrap, then the token populated
later by wordfreq import). The lexeme-frequency rollup walks
``lexeme.forms`` and skips any form with ``word_token_id IS NULL``, so
those lemmas show zero rollup even when the underlying annotations exist.

This script joins ``derivative_forms`` to ``word_tokens`` on
``(derivative_form_text, language_code) == (token, language_code)`` and
sets the FK where it's currently null.
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


def run(dry_run: bool, config_args: argparse.Namespace) -> int:
    config = get_data_source_config(config_args)
    session = create_session(config)
    try:
        rows = (
            session.query(DerivativeForm, WordToken)
            .join(
                WordToken,
                (WordToken.token == DerivativeForm.derivative_form_text)
                & (WordToken.language_code == DerivativeForm.language_code),
            )
            .filter(DerivativeForm.word_token_id.is_(None))
            .all()
        )
        print(f"Found {len(rows)} derivative forms with a matching WordToken to link")
        for form, token in rows:
            form.word_token_id = token.id

        # Report unresolved (null word_token_id with no matching token).
        remaining = (
            session.query(DerivativeForm).filter(DerivativeForm.word_token_id.is_(None)).count()
        )
        # ``remaining`` reflects pre-update state if we haven't flushed/commit-ed yet,
        # but SQLAlchemy's identity map will reflect the in-session updates on next flush.
        # We compute the final unresolved count after flush:
        if not dry_run:
            session.flush()
        unresolved = (
            session.query(DerivativeForm).filter(DerivativeForm.word_token_id.is_(None)).count()
        )

        if dry_run:
            session.rollback()
            print(f"Dry run: would link {len(rows)} forms; rolled back")
        else:
            session.commit()
            print(f"Linked {len(rows)} derivative forms to existing word tokens")
            print(f"Remaining derivative forms with no matching WordToken: {unresolved}")
        return len(rows)
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
