# API Wrapper Package Guidelines

This `api/` package provides thin, typed Python wrappers around selected
BARSUKAS HTTP route operations.

## Purpose

- Offer a stable import surface for Python callers that need to interact with
  BARSUKAS programmatically.
- Keep wrappers very small and predictable.
- Mirror route domains from `src/barsukas/routes/`.

## Mirroring pattern

Each module in this directory mirrors a domain route module in
`src/barsukas/routes/`:

- `api/lemmas.py` <-> `src/barsukas/routes/lemmas.py`
- `api/sentences.py` <-> `src/barsukas/routes/sentences.py`
- `api/translations.py` <-> `src/barsukas/routes/translations.py`
- `api/audio.py` <-> `src/barsukas/routes/audio.py`
- `api/batch_operations.py` <-> `src/barsukas/routes/batch_operations.py`

When changing behavior in a mirrored Barsukas route file, make the
corresponding change in this `api/` module in the same commit.

## Design constraints

- Use typed `dataclass` request/response models (or `TypedDict` when needed).
- Facade functions should delegate to one implementation point only:
  the relevant BARSUKAS HTTP route.
- Do not duplicate business logic from Barsukas route handlers.
- Keep shared endpoint/location values in `api/constants.py`.
