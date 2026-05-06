# `api/` — Python wrapper around the Barsukas HTTP API

This package provides a thin, typed Python facade over the JSON endpoints
exposed by the Barsukas web app (`src/barsukas/routes/api.py` and
`src/barsukas/routes/pending_imports.py`).

It is the recommended way for scripts, agents, and external tools to consume
Barsukas. It is **not** a replacement for direct database access — code that
already runs inside the Barsukas process should keep using the SQLAlchemy
models in `src/storage/`.

## Layout

- `api/__init__.py` — public re-exports. Internal helpers (HTTP, decorator)
  live in underscore-prefixed modules and are intentionally not re-exported.
- `api/constants.py` — shared constants: `BASE_URL` (override with the
  `BARSUKAS_API_URL` env var), API path prefix, default timeout, user-agent.
- `api/_mirror.py` — the `mirrored_route` decorator (see "Mirroring contract"
  below).
- `api/_http.py` — minimal `requests.get`-based JSON transport and
  `BarsukasAPIError`.
- `api/lemmas.py` — search and lemma-detail endpoints.
- `api/sentences.py` — sentence-domain aggregates.
- `api/translations.py`, `api/audio.py` — re-export the matching lemma
  sub-resource accessors; reserved as the natural home for future
  standalone endpoints in those domains.
- `api/batch_operations.py` — bulk/aggregate endpoints (word metadata,
  model registry, pending-imports list / duplicate detection).
- `api/llm_agents.py` — LLM-driven agent triggers (translation generation
  /validation, pronunciation generation, definition / disambiguation
  review). Mirrors ``src/barsukas/routes/llm_api.py``. The Barsukas routes
  accept optional API keys in the JSON body; these facades intentionally
  do not expose those parameters and rely on Barsukas' system keys.

## Independence from `src/`

`api/` lives at the repo root and **does not import from `src/`**. The
package talks to Barsukas exclusively over HTTP. This is a deliberate
decoupling: external consumers can vendor `api/` without pulling in the
SQLAlchemy schema, the LLM clients, or the rest of the project.

By the same token, `src/barsukas/` does **not** import from `api/`. The two
trees stay textually aligned via the mirroring contract below.

## Mirroring contract

Every facade function in `api/` corresponds to exactly one route in
`src/barsukas/routes/`. Both sides carry a decorator that records the
mirrored route path and HTTP method:

- Facade side (`api/`):
  ```python
  from api._mirror import mirrored_route

  @mirrored_route("/api/v1/lemma/<guid>/translations", "GET")
  def get_translations(guid: str, *, language: Optional[str] = None) -> ...:
      ...
  ```

- Route side (`src/barsukas/routes/`):
  ```python
  from barsukas.routes._mirror import mirrored_facade

  @bp.route("/v1/lemma/<guid>/translations")
  @mirrored_facade("/api/v1/lemma/<guid>/translations", "GET")
  def get_lemma_translations(guid: str) -> ResponseReturnValue:
      ...
  ```

The two decorators are deliberately defined in two places — neither tree
imports from the other. They set the same attribute names
(`_mirrored_route`, `_mirrored_method`) so a precommit check can pair them
up by value.

### Precommit check

`scripts/check_api_mirror_routes.py` AST-walks the files on both sides,
collects every `(route_path, method)` literal passed to `@mirrored_route`
(facade side) and `@mirrored_facade` (Barsukas side), and fails if either
set has an entry the other doesn't.

The decorator arguments must be **string literals** — f-strings or other
expressions are rejected so the checker can read them statically without
importing either tree.

Run it directly:

```
python scripts/check_api_mirror_routes.py
```

### Editing rules

- **Adding an endpoint:** add the route in `src/barsukas/routes/...` with
  `@mirrored_facade(...)`, then add the matching facade in `api/...` with
  `@mirrored_route(...)` using the identical path string and method.
- **Changing an endpoint:** update both sides in the same commit — path,
  query params, and response shape. The route docstring is the source of
  truth for the response shape; the facade's `TypedDict`s should follow it.
- **Removing an endpoint:** remove both sides in the same commit. Update
  `src/barsukas/routes/API.md` too.

## Scope

`api/` mirrors:

- the read-only JSON endpoints documented in `src/barsukas/routes/API.md`
  (search, lemma sub-resources, metadata aggregates, model registry,
  pending-imports list / duplicate detection); and
- the LLM-agent trigger endpoints under `/api/llm/` (defined in
  `src/barsukas/routes/llm_api.py`).

Internal AJAX helpers used by the Barsukas HTML UI (e.g.
`/api/check_lemma_exists`, `/api/auto_populate_lemma`, the form-driven
`/agents/*` routes) are intentionally **not** mirrored — they are UI
implementation details, not part of the stable external surface.
