# BARSUKAS Web Interface Guidelines

BARSUKAS is the main web UX for interacting with the linguistic database.

- Always use ordinary form submits for POST data (no AJAX submissions)
- Avoid using disappearing UX elements
- Changes to barsukas generally do not require tests
- Ask the developer to test changes in their local browser
- Use Bootstrap 5 classes for styling (already included in base.html)
- Follow existing patterns for forms, buttons, and navigation
- API route reference for automation lives at `src/barsukas/routes/API.md`

## The /sync blueprints

`src/barsukas/routes/sync/` holds one blueprint per element type plus five
shared modules. Every blueprint routes through them; do not reintroduce a local
copy of any of this:

- `release_io.py` - all `data/release` JSONL reading and writing. Build a
  GUID->file index once per request with `build_guid_file_index` and look up
  through it; never re-scan the tree per GUID. `upsert_records` merges by key
  and is what an "export these rows" path should call.
- `actions.py` - form parsing (`action_{id}` and `action_{id}_{lang}`), the
  read-only guard, and `SyncOutcome`, which holds the counters and produces the
  flash messages. Do not hand-roll `updated/skipped/errors` counters; use
  `outcome.commit(g.db)` and `outcome.write_release(...)` so a failed write
  cannot report rows as written.
- `paging.py` - `paginate()` for difference lists. Every list page paginates:
  the lemma translations page renders one `<select>` per lemma per differing
  language, and a few thousand native select widgets is what made it crawl.
- `sync_release_helpers.py` - the per-language-file helpers the derivative and
  synonym syncs share.
- `record_sync.py` - the whole engine for *whole-record* types (idioms, names):
  one `base.jsonl`, no per-language files, a canonical record builder in
  `storage.release`. Adding another type of that shape means writing a
  `RecordSyncSpec`, not another blueprint.

Templates share `templates/sync/_macros.html` (pagers, action selects, bulk
apply) and `static/js/sync.js`. Import the macros **with context** - they read
`STRINGS`, and a plain `{% import %}` leaves it undefined at render time.

Lemma and sentence sync remain separate blueprints: their release data spans
per-language and grouped files and reconciles per field, so they share the file
I/O, form parsing and paging but not the record engine.

Every list page that offers a whole-list action must render it as its own form
below the per-row form (not a nested submit), carry the count it was rendered
with, and never widen a *deletion* to rows the user cannot see.

