# Barsukas

Barsukas is Greenland's Flask web interface for day-to-day human operations on the
linguistic database.

In practice, it combines:
- **database editing/review UX** (lemmas, translations, sentences, audio, categories, logs), and
- **agent operations UX** (launching and reviewing selected agent-backed workflows).

This README is intentionally focused on **what Barsukas is and how it is organized**.
For startup details, use `launch.sh` (deployment/runbook steps live outside this repo).

## What lives here

`src/barsukas/` is the full web app package:

- `app.py` — Flask app factory, global routes (`/`, `/metrics`, `/ipa-reference`),
  blueprint registration, request/session lifecycle.
- `unified_app.py` — unified process launcher used by `launch.sh` (web server + worker in one process).
- `routes/` — feature blueprints and URL handlers.
- `templates/` — Jinja templates by feature area.
- `static/` — JS/CSS assets.
- `helpers/` — UI helpers (language selection, flash helpers, display helpers, db optimizations).
- `config.py` and `personas.py` — runtime/server persona behavior.

## URL path map

Barsukas routes are organized as Flask blueprints. The main top-level paths are:

- `/` — home/dashboard.
- `/metrics` — Prometheus metrics endpoint.
- `/ipa-reference` — IPA reference page.
- `/lemmas` — lemma browse/view/edit flows.
- `/translations` — translation tools.
- `/sentences` — sentence browse/view flows.
- `/sentences/rapid-review` — sentence rapid review.
- `/sentence-stats` — sentence statistics.
- `/categories` — category management.
- `/overrides` — override management.
- `/conversations` — conversation views/tools.
- `/audio` — audio tooling and review.
- `/audio/rapid-review` — audio rapid review workflow.
- `/agents` — agent workflow endpoints/results.
- `/agents-launcher` — web launcher for agent CLI tasks.
- `/batch-operations` — queued/background task tracking.
- `/pending-imports` — pending import review.
- `/logs` — operation log and audit views.
- `/exports` — export hub.
- `/wireword` — wireword export tools.
- `/gyvate` — strings export utilities.
- `/dictionary` — dictionary-facing routes.
- `/pattern-sentences` — pattern sentence tooling.
- `/rhymes` — rhyme exploration views.
- `/pradzia` — start-page style utilities.
- `/rapid-review` — rapid review hub.
- `/sync` — sync hub.
- `/sync/lemmas` — lemma release sync.
- `/sync/relations` — relation release sync.
- `/sync/sentences` — sentence release sync.
- `/sync/derivatives` — derivative release sync.
- `/api` — core API endpoints.
- `/api/llm` — LLM-oriented API endpoints.
- `/api-client` — built-in API test client UI.

Note: benchmark paths under `/benchmarks...` are conditionally registered when the
benchmarks backend is available.

## How the app is structured (mental model)

Barsukas is organized by **feature slice**:

1. **Route module** in `routes/*.py` defines URL handlers.
2. **Template subtree** in `templates/<feature>/` renders the UI.
3. **Static JS/CSS** in `static/js` and `static/css` handles feature-specific client behavior.
4. **Shared helpers** in `helpers/` provide reusable formatting/language/session utilities.

This keeps most changes local to one feature area (route + template + optional JS/CSS).

## API and route documentation

For machine/API route details, start with:

- `src/barsukas/routes/API.md` — detailed API route reference for automation and integrations.

For behavior details beyond that:

- inspect the corresponding module under `src/barsukas/routes/` (source of truth for handlers), and
- inspect templates under `src/barsukas/templates/` for UI flow and form expectations.

## Running Barsukas

Use `src/barsukas/launch.sh`.

(Operational/server setup instructions are intentionally maintained in a separate repo.)
