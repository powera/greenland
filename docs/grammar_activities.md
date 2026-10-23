# Word data required by grammar activities

This is the linguistic data contract for Trakaido web and the shared
Trakaido / Spanish with Sabi iOS code. Requirements below describe what a
generator must know to produce a valid question; they are not a claim that
every client currently checks every field. See the dated
[consumer audit](grammar_activity_field_audit.md) for implementation gaps.
Client activity descriptions live in the sibling repository's
`docs/grammar-mode.md` and `docs/journey/activity-types.md`.

Chinese grammar activities are not implemented yet. Chinese classifiers are
useful vocabulary data, but are outside the current activity requirements.

## Shared rules

- Facts belong to a particular word sense **and language**. English and target
  countability can differ; neither may stand in for the other.
- Missing facts mean unknown, not a default such as countable or masculine.
  Skip a candidate if a fact needed by that question is missing or uncertain.
- A stored form proves its spelling, not its suitability in a sentence.
  Check classification facts before selecting singular/plural forms.
- Keep grammatical eligibility separate from semantic suitability. A noun can
  be countable and still make a poor object of “eat” or “wear.” Theme groups
  and sense-level restrictions select plausible objects; countability does
  not replace them.
- Require only the facts/forms that the selected pattern actually uses.
  An uncountable noun can participate in “I want pasta”; it should not be
  removed from every sentence activity.

## Noun facts and forms

| Data | Meaning and use |
|---|---|
| `countability` | Per-language `countable`, `uncountable`, or `both`. Governs count frames, indefinite articles and mass-noun phrasing. |
| `number_type` | `regular`, `plurale_tantum` (plural-only), or `singulare_tantum` (singular-only). Governs which grammatical numbers are available. Separate from countability. |
| `grammatical_gender` | Explicit target-language gender for articles, adjectives and gendered numerals. Do not infer it from an ending when an activity needs a reliable answer. |
| English/source plural | Stored plural form for plural prompts; never create it by simply appending “s.” English “fish,” “children,” and compound nouns require their actual forms. |
| Target plural/case forms | Stored forms for the exact number and governed case used in the answer and reference tables. |

`both` does not authorize every count use in every frame. A generic generator
must choose a supported reading, or skip an ambiguous count frame. It must not
silently introduce a serving, container, variety or portion reading.

For the ordinary food sense, generate **“I want pasta,”** not **“I want
pastas.”** “Pastas” can describe varieties in another context; that does not
make it suitable for the generic beginner food frame. Similarly, use “I want
rice,” not “I want a rice” or “I want three rices.” “Three bowls of rice”
requires an explicit container construction that the activity supports.

Number and countability must both pass. A plural-only item such as “trousers”
must not become “a trousers” or be used as a singular subject. Existing form
builders can repeat a plural-only spelling in slots labelled singular and
plural; the activity must still consult `number_type` rather than treating
those slot labels as evidence of a real singular.

## Activity requirements

| Activity / pattern | Word data required | Eligibility and agreement |
|---|---|---|
| Want / have / eat / wear / see | Source and target countability and number paradigm; target gender when an article requires it; target noun form for the governed case/number. | Select count or mass phrasing independently in each language. Use a/an or un/una only for an appropriate singular count reading. Apply semantic object restrictions separately. |
| Like; singular/plural noun subjects | Same noun facts; stored source/target plurals for plural phrasing. | Subject number controls the verb (e.g. gusta/gustan). A generic mass reading stays mass; a plural-only noun keeps plural agreement. |
| Number + noun | Source/target countability and number paradigm; source plural; target numeral agreement facts and noun forms for that number. Lithuanian needs gender and the appropriate case/number forms. | Count discrete objects only. Skip mass/count mismatches until the generator supports a meaningful quantity construction. Plural-only nouns need dedicated numeral constructions; do not route them through ordinary singular/count frames. |
| Color / noun + adjective | Target noun gender/number, noun forms, adjective agreement forms; source plural when needed. | Agree the adjective and copula with the noun. Use objects for which the description is sensible. |
| Feelings | Target adjective agreement forms and the pattern's subject features; language-specific predicate construction. | A person's gender/number controls agreement where applicable. Fixed predicates such as Spanish tener hambre use their authored construction. |
| Go to; preposition + noun | Target case forms or articles/contractions required by the preposition; noun number paradigm and gender where relevant. | Use an appropriate location noun. Never assume its base spelling is nominative singular. |
| Negatives / questions / past versions | All requirements of the underlying pattern, plus its polarity/tense/person rules and any changed object case. | Lithuanian negative object patterns may require genitive rather than the positive pattern's case. |
| Lithuanian number-agreement drill | Explicit noun gender, countability, number paradigm, nominative/genitive plural and other case forms used by its numeral construction. | Do not infer gender from endings or count an arbitrary mass/plural-only noun as an ordinary discrete object. |
| Lithuanian preposition-case drill | Number paradigm and the governed forms; current catalog expects genitive, accusative and instrumental singular. | Singular-only frames must exclude plural-only nouns; plural frames need their own forms and agreement. Countability is needed only if the phrase introduces a count reading. |
| Declension case identification | Explicit case/number forms and number paradigm. | Do not invent a nominative singular from the base entry. Group identical surfaces so a valid syncretic case is not marked wrong. |
| Conjugation practice | Complete forms for the tested tense/mood/person/number, plus agreement/reflexive/auxiliary facts where the chosen construction needs them. | Principal parts or a classification alone are not a full conjugation table. Do not offer nonexistent slots. |
| Pronoun drills | Authored pronoun paradigms and question context specifying person/number/case and gender where relevant. | Not dependent on Lape2 noun facts. |
| Grammar lessons | Authored lesson/config JSON. | Not generated from per-word Lape2 facts. |

Patterns can use authored verbs and function words rather than wordlist verbs.
That does not remove the need for correct person/tense forms, but it means a
missing wordlist verb table need not block that authored sentence pattern.

## English comparison and gradability

Here `gradability` records whether and how an adjective/adverb is compared:

| Value | Example | Required comparison forms |
|---|---|---|
| `synthetic` | red → redder → reddest; good → better → best | Stored `comparative` and `superlative`; includes irregular forms. |
| `periphrastic` | useful → more useful → most useful | Stored comparative/superlative phrases. |
| `non_gradable` | A sense without an ordinary degree comparison | Exclude it from a generic comparison drill. |

Thus **“redder” makes sense** when comparing degree of redness. This is
sense-dependent: a classification label such as a red political affiliation
does not automatically authorize the same beginner comparison question.
Gradability is not noun countability or adjective gender/number agreement.
No current web/iOS consumer of the English `gradability` fact was found in
the audit; it is a requirement for a future English comparison activity,
not a missing dependency of today's noun sentence drills.

## Export and acceptance checks

Target facts are exported in `grammar_metadata`; forms are in
`grammatical_forms`. English/source facts and plurals also need an explicit
client-facing representation: target metadata alone cannot validate the
English prompt. Database coverage, exported coverage and activity eligibility
are separate checks.

Representative checks when wiring consumers:

- Generic pasta/rice sentences remain mass constructions in English.
- A noun with different source/target countability is rendered appropriately
  on each side or excluded from an unsupported count frame.
- Plural-only nouns never acquire an invented singular or singular agreement.
- Irregular noun genders follow stored facts, not ending guesses.
- English plural prompts use stored irregular/compound forms.
- Missing required facts/forms exclude that candidate without inventing data.
- Ordinary count nouns still work in singular, plural and numeral frames.
