# Reflexive verb forms

Spanish and French derivative forms include reflexive clitics, but omit subject
pronouns: `me lavo`, `te lavas`, `me lave`, `nous lavons`. The translation's
citation form selects the paradigm (`lavarse`, `se laver`, `s'habiller`);
`verb_reflexivity` classifies usage in the sense and does not turn a plain
translation into a reflexive one.

Spanish infinitives and gerunds retain enclitics (`lavarse`, `lavándose`),
including accent changes. Past participles remain bare (`lavado`). The
`es-419` second-plural slot uses `se lavan`, while `es` uses `os laváis`.

French infinitives and present participles retain their clitics (`se laver`,
`se lavant`). The four `pc_*` slots remain bare participle agreement forms,
without clitics or auxiliaries. They are not assembled passé composé phrases;
agreement in a particular sentence still depends on its syntax. Both straight
and typographic apostrophes are accepted; generated forms use straight ones.
For an h-initial base, the citation spelling supplies the elision distinction:
`s'habiller` versus `se hâter`. Arbitrary verb phrases are not mechanically
conjugated. Irregular base verbs still need an entry in the conjugator.
The restricted-person verb `s'ensuivre` declines mechanical generation rather
than inventing first- and second-person forms.

Lithuanian forms preserve reflexive morphology. Suffix reflexives require
reflexive principal parts (`mokytis`, `mokosi`, `mokėsi`); plain principal parts
are rejected. Prefixed verbs retain internal `-si-` through the ordinary rules
(`pasimokyti`, `pasimoko`, `pasimokė`). Principal parts remain required; they
cannot reliably be inferred from the infinitive alone.

These rules govern newly generated forms. Existing stored forms and overrides
are not automatically replaced. Audit and repair existing records separately,
using the normal persistence path and a minor database backup before repair.

## Linguistic references

- [French s'asseoir conjugation, Larousse](https://www.larousse.fr/conjugaison/francais/s%27asseoir-indicatif/601)
- [French se souvenir conjugation, Académie française](https://www.dictionnaire-academie.fr/conjuguer/A9S2476)
- [Lithuanian conjugation tables, SIH](https://sih.lt/dokumentubankas/download/37)

- [French battre conjugation, Larousse](https://www.larousse.fr/fr/conjugaison/francais/battre/871)
- [French inscrire conjugation, Larousse](https://www.larousse.fr/conjugaison/francais/inscrire/5526)
- [French s'ensuivre usage, Littré](https://www.littre.org/definition/ensuivre)
