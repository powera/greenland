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

## Geography senses and curriculum tiers

`20261009_add_geography_senses.py` adds a curated starter inventory of separate
country, person/demonym, origin-adjective, language, and distinct ethnic senses.
It includes 22 main language names and the extended Igbo, Assamese, and Mongolian
examples. This is not an exhaustive top-150 ranking. It does not generate or
guess translations. Existing GUIDs, definitions, translations, and manual
language overrides are preserved; ambiguous existing matches stop the migration.

Preview additions and normalization of existing base levels (rolled back):

```bash
GREENLAND_TEST_MODE=1 PYTHONPATH=src python migrations/20261009_add_geography_senses.py --set-base-levels
GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/apply_country_overrides.py preview lt
GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/apply_country_overrides.py preview zh
```

When ready to apply, first make a WAL-safe backup. Then add the senses, normalize
their base levels, and regenerate the target-language overrides. These commands
are for the later population step; implementing the migration does not run them.

```bash
PYTHONPATH=src python -m storage.backup create --label geography-senses
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261009_add_geography_senses.py --set-base-levels --apply
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python src/scripts/apply_country_overrides.py apply-all
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python -m storage.release.cli export lemmas levels
```

The tiers are L15 for target-language promotions, L231 for the main inventory,
and L1031 for extended senses. Lithuanian and Chinese keep different country
priorities. Shared languages use the earliest associated country tier, but
extended languages are not promoted solely because a related country is early.
These rules are also used when WireWord export applies country overrides.

## Extended geography level split

`20261017_split_extended_geography_levels.py` splits extended geography the way
231-233 are split: 1031 countries, 1032 people and ethnic groups, 1033
languages. It names the three levels and moves the catalog senses still at
1031 (Mongolian, Igbo, Assamese). Run it before
`scripts/wordlists/import_geography_catalog.py`, which adds the rest of the
catalog through `add_sense`. The 20261009 migration is superseded by that
script and should not be re-applied.
