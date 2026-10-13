# src/quality

LLM review of data that is already in the database: is a word at the right
level, in the right category, with the right sense.  `src/words/` keeps the
shared word tooling these build on (`words.level_naming`, the add paths);
`src/reports/` keeps the rule-based, LLM-free reports.

Run each with `PYTHONPATH=src python src/quality/<name>.py --help`.  Prompts
live in `prompts/quality/<name>/`.

- `level_placement.py` — LLM placement of a word into a level, from every
  level title plus a shortlist from the rule and corpus-lean rankers.  Also
  the placement step jonvabalis runs on new head words.  Writes nothing.
- `level_outliers.py` — LLM review of one level for words to remove or fix
  (wrong sense, off topic, obscure).  Prints only; writes nothing.
