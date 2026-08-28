# One-off migrations

This directory contains dated, one-off project migrations. New migrations live
here instead of being added to the older migration locations under `src/`.
Existing migrations are intentionally not moved.

Name each migration with a `YYYYMMDD_` prefix so execution order is visible.
Migration scripts must:

- add `ROOT/src` to `sys.path` before importing project modules;
- use `DataSourceConfig` when selecting a database;
- be safe to rerun, or fail clearly when rerunning would be unsafe;
- offer `--dry-run` when practical; and
- print a concise summary of what changed.

Run a migration from the repository root, for example:

```bash
GREENLAND_TEST_MODE=1 python migrations/20260828_rename_country_subtype_to_region.py --dry-run
GREENLAND_TEST_MODE=1 python migrations/20260828_rename_country_subtype_to_region.py
```
