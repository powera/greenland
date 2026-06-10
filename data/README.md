# data

Source corpora, vocabulary profiles, and release data for the linguistic
database.

## Subdirectories

- `release/` — canonical JSONL export of the lemma database, organized as
  `lemmas/{pos_type}/{pos_subtype}/*.jsonl`. See `release/README.md` for the
  record format and editing rules.
- `wordfreq/` — word frequency corpora (books, Wikipedia vital articles,
  SUBTLEX; see `wordfreq/subtlex.md`). Also the default home of the working
  database, `linguistics.sqlite` (gitignored).
- `basic_english/` — Ogden's Basic English extended wordlist
- `cambridge/` — Cambridge Young Learners English (YLE) vocabulary profile
- `cefr/` — CEFR-J (A1–B2) and Octanove (C1–C2) vocabulary profiles
- `greenland_input/` — git submodule (`powera/greenland-input`) with input
  files for import
- `trakaido_wordlists/` — git submodule (`powera/trakaido-wordlists`) holding
  the generated WireWord wordlists for the Trakaido app

Top-level files include `categorychoice*.json` (category metadata for
Trakaido exports) and `lt_sample_*.txt` (Lithuanian sample texts).

Frequency corpora are loaded into the database by the `pradzia` agent;
`data/release` is round-tripped via the Barsukas `/sync` UI and
`storage/migrate.py`.
