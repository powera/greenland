# strings (src)

Tooling for Barsukas UI string localization. The string catalogs themselves
live in the top-level `strings/` directory (see `strings/README.md` and
`strings/NAMING.md`); this package contains the code that extracts, loads,
and tracks them.

- `generate_barsukas_strings.py` — extract hardcoded strings from Barsukas
  templates into localization catalogs
- `barsukas_helpers.py` — load UI strings by namespace for Barsukas
- `gyvate_service.py` — string export service and template change tracking
- `count_barsukas_pending_strings.py` — report strings awaiting translation
