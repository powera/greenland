# Gender counterpart generation and shared audio

A concept retains one GUID. Its ordinary translation is unspecified; stored
male/female variants retain their own base words, grammar, and inflections.
Equal spellings do not merge semantic entries.

## Audio generation

Vieversys and Strazdas batches, the audio generation page, and queued single-word
requests include stored gender counterparts by default. They do not invent missing
counterparts. `--no-include-variants` limits CLI generation to ordinary words;
`--include-forms` additionally records stored inflections. Vieversys `populate-only`
reuses available recordings; `regenerate` replaces them. Strazdas uses `--force`
for replacement. Generation never runs the text/forms backfill implicitly.

The API's `generate_audio` helper accepts `include_variants=True`,
`include_forms=False`, `force=False`, and a Vieversys `tts_engine` selection.
The corresponding queue payload accepts `include_variants`, `include_forms`,
and `force` alongside its existing engine/voice inputs.

Generation groups equal spoken text within a lemma, language/accent, and voice.
Actor unspecified/male share an asset, while actress has a separate asset.
IPA-driven local generation groups by text **and** stored IPA and avoids
text-only reuse of recordings from previous runs. Shared entries have separate
`AudioQualityReview` rows containing the same filename, hash, and asset URLs.
Local files use content-addressed filenames too, so regenerating one slot cannot
overwrite an asset still used by another slot. No new schema is required. Manifests retain the slot used for synthesis; alias
slots are database references to that same asset, not additional uploads.

Base variants use `variant/gender/{male|female}/base`; inflections use
`variant/gender/{male|female}/{grammatical_form}`. Ordinary audio retains its
existing null/base and grammatical-form keys. Presentation dialects read their
configured text variety while retaining their own audio language/accent.

The exporter can also reuse existing slot recordings when current text matches,
including migrated recordings, per voice. Base and singular entries share audio.
Each entry retains its own grammar and form text. Ordinary default audio is
also exposed at the top level for existing clients.

## Edits and review

Changing ordinary text invalidates ordinary recordings, leaving unchanged
counterpart references intact. Variant edits invalidate that variant's recordings.
The next generation run may reuse a still-valid matching asset from another slot.
A quality review or production promotion applies to active references to the same
asset, GUID, language, voice, and expected text. References invalidated for a text
mismatch are not revived by reviewing another reference. Review validation looks
up the actual stored variant/form, rather than the ordinary translation.

## Completing the data rollout

The 1000+ gender counterpart backfill remains an explicit operation. First preview
its selection with `scripts/backfill_gender_variants.py --dry-run` and the desired
level/language filters. Its default language selection covers tiers 1–2;
`--languages all` covers tiers 1–3. Review low-confidence answers and incomplete
pairs before treating coverage as complete.

Then populate counterpart paradigms with `agents.vilkas.cli --populate
--gender-variants`, using the same selection. Both activation scripts now include
this forms step. Generate/review/promote missing audio, then export release and
WireWord artifacts through the normal workflows. No data backfill, paid TTS,
S3 publication, or release regeneration is part of applying these code changes.
