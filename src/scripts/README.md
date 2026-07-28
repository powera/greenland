# scripts (src)

One-off administrative and maintenance scripts for data cleanup, migration,
and validation. Run with:

```bash
PYTHONPATH=src python src/scripts/<script>.py --help
```

- `check_duplicates.py` — classify word collisions in release data
- `find_duplicates.py` — find partial duplicates across non-English
  translations
- `accept_approved_sentence_audio.py` — promote staged sentence audio to
  production S3
- `backfill_derivative_form_tokens.py` — fix missing `word_token_id` links on
  derivative forms
- `migrate_staging_audio_paths.py` — migrate audio files to the
  language/voice directory layout
- `update_prominence.py` — set `sense_prominence` from Trakaido difficulty
  levels
- `trace_sentence_pipeline.py` — run one sentence through all four
  translate-and-decompose phases, printing every LLM result, lemma link, and
  database write, plus estimated vs. actual output tokens per phase. Makes
  real LLM calls; use `--dry-run` to skip persistence and
  `GREENLAND_DISABLE_LLM=1` to block the calls entirely

For repo-level checks and deployment helpers, see the top-level `scripts/`
directory instead.
