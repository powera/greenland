# Grammar facts

A grammar fact is one row in `grammar_facts`: a lemma, a language, a
`fact_type`, a `fact_value`, free-text `notes` and a `verified` flag.  It
records something about a word in one language that its forms and translation
do not carry on their own: a noun's gender, a verb's auxiliary, an irregular
plural.

This page lists the fact types, what their values mean, and the rules that are
easy to get wrong.  Which *languages* each type applies to is not repeated
here; `src/storage/config/grammar_fact_registry.py` is the source of truth for
that, and for which types are exported to `data/release`.

## Facts belong to a sense

A lemma is one sense of a word, so a fact is about that sense.  French
*sortir* "to go out" takes être and *sortir* "to take out" takes avoir; Spanish
*el capital* "money" and *la capital* "city" are masculine and feminine.  These
are different lemmas with different facts, not one fact with two values.

## Three kinds of fact

**Classifications** describe the word: gender, auxiliary, countability,
transitivity.  Every lemma of the right part of speech should have one, and a
missing row means *not yet decided*, never "the usual value".  They are written
by the Lape agent (`src/agents/lape.py`), by rule where a rule is certain and by
the LLM otherwise.

**Principal parts** are inputs a conjugator cannot derive: the Lithuanian
`3s_present`/`3s_past`, the English `past`/`past_participle`.  The rule-based
form builders read them, and a verb without them gets no mechanical paradigm.

**Overrides** exist only where the rule is wrong: `plural` for an irregular
noun plural, `feminine_form` for a French adjective, `comparative` and
`superlative`, and the `verb_form_<slot>` family (`verb_form_1s_present`, ...)
for a single conjugated form.  Here a missing row *does* mean "the rule is
right", which is the opposite of a classification, so an override that agrees
with the rule should not be added.

## Fact types and values

| fact_type | kind | values |
|---|---|---|
| `grammatical_gender` | classification | `masculine`, `feminine`, `neuter`, `common` (see below) |
| `auxiliary_verb` | classification | the language's two auxiliaries: `avoir`/`être`, `haben`/`sein`, `avere`/`essere`, `hebben`/`zijn` |
| `countability` | classification | `countable`, `uncountable`, `both` |
| `animacy` | classification | `animate`, `inanimate` |
| `verb_transitivity` | classification | `transitive`, `intransitive`, `ditransitive`, `ambitransitive` |
| `verb_reflexivity` | classification | `inherently_reflexive`, `optionally_reflexive`, `non_reflexive` |
| `gradability` | classification | `synthetic` (-er/-est), `periphrastic` (more/most), `non_gradable` |
| `number_type` | classification, set only when exceptional | `plurale_tantum`, `singulare_tantum`, `uncountable`, `both` |
| `declension_class` | classification | `1`–`5` (Lithuanian; derived, not exported) |
| `measure_words` | classification | a Chinese classifier, optionally `个 (alt: 只, 头)` |
| `fanciful_collective` | classification | an ornamental English collective ("a murder of crows") |
| `infinitive`, `3s_present`, `3s_past`, `1s_present`, `1s_past`, `1s_future`, `past`, `past_participle` | principal part | the form's text |
| `plural`, `feminine_form`, `comparative`, `superlative`, `verb_form_<slot>` | override | the form's text |

`number_type` is the one classification that is recorded only when it is
exceptional, because nearly every noun is ordinary.  The form builders read it
the same way in every language: a plurale tantum (*jeans*, *gafas*,
*lunettes*) repeats the word in both the singular and plural slots, and
`uncountable` or `singulare_tantum` produce the singular only.

## Gender

Most gendered languages use `masculine` and `feminine`, plus `neuter` where
the language has one.

Spanish (es, es-419) and French also allow **`common`**: a noun with a single
form that takes either gender depending on who it refers to.

- Spanish: el/la estudiante, el/la artista, el/la joven, el/la testigo
- French: un/une élève, un/une enfant, un/une artiste, un/une collègue

`common` is **not** for:

- **Pairs of different words** — actor/actriz, profesor/profesora,
  acteur/actrice.  The lemma's translation is one of those words, and it gets
  that word's gender.  How the other member of the pair is stored is an open
  question.
- **Nouns whose meaning changes with gender** — el capital / la capital,
  le livre / la livre.  Those are separate senses (see above), each with an
  ordinary gender.

How `common` is shown to learners is a display question, not settled here.

The LLM decides each noun's gender.  An ending rule
(`langtools/{es,fr}/gender.py`) cross-checks the answer; when the two
disagree the LLM's value is kept and the fact's notes start with
`CHECK: ending rule predicts ...`, so review can find it.  The rule never
predicts `common`.  es-419 copies es's fact when both varieties use the same
word, so run es first.

## Auxiliary

Every French verb has an explicit `auxiliary_verb`, avoir included: there is
no implied default.  Reflexive verbs and the closed list of être verbs are
decided by rule (`langtools/fr/auxiliary.py`) and everything else is avoir.
The verbs that take either depending on sense (sortir, passer, monter,
descendre, rentrer, retourner, ...) go to the LLM, which answers for the sense
in the lemma's definition.

## Where the code lives

- `src/storage/config/grammar_fact_registry.py` — every fact type, the
  languages it applies to, and whether it is exported to `data/release` (the
  module docstring explains the exported/generated distinction)
- `src/words/grammar_facts.py`, `src/words/grammar_fact_tasks/` — Lape's
  generation, one module per fact type; the allowed values per language are in
  `GrammarFactService`
- `prompts/grammar/` — the LLM prompts
- `src/langtools/<lang>/` — the rules that decide or cross-check facts, and
  the form builders that read them
- `src/storage/crud/grammar_fact.py` — reading and writing facts
