#!/usr/bin/env python3
"""
One-off script to add English conjugations to existing verbs in database.

This script loads the English conjugations from verbs.py and adds them
to verbs that are already in the database but missing English conjugation forms.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
GREENLAND_REPO_ROOT = os.path.abspath(os.path.join(GREENLAND_SRC_PATH, ".."))
sys.path.append(GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import add_word_token, create_database_session
from wordfreq.storage.models.schema import DerivativeForm, Lemma
from wordfreq.storage.translation_helpers import get_translation

# Add verbs.py directory to path
sys.path.insert(0, os.path.join(GREENLAND_REPO_ROOT, "data", "trakaido_wordlists", "lang_lt"))
from verbs import verbs_new

# Form mapping from verbs.py to database format
FORM_MAPPING = {
    # Present tense
    "1s_present": "verb/lt_1s_present",
    "2s_present": "verb/lt_2s_present",
    "3s-m_present": "verb/lt_3s_m_present",
    "3s-f_present": "verb/lt_3s_f_present",
    "1p_present": "verb/lt_1p_present",
    "2p_present": "verb/lt_2p_present",
    "3p-m_present": "verb/lt_3p_m_present",
    "3p-f_present": "verb/lt_3p_f_present",
    # Past tense
    "1s_past": "verb/lt_1s_past",
    "2s_past": "verb/lt_2s_past",
    "3s-m_past": "verb/lt_3s_m_past",
    "3s-f_past": "verb/lt_3s_f_past",
    "1p_past": "verb/lt_1p_past",
    "2p_past": "verb/lt_2p_past",
    "3p-m_past": "verb/lt_3p_m_past",
    "3p-f_past": "verb/lt_3p_f_past",
    # Future tense
    "1s_future": "verb/lt_1s_future",
    "2s_future": "verb/lt_2s_future",
    "3s-m_future": "verb/lt_3s_m_future",
    "3s-f_future": "verb/lt_3s_f_future",
    "1p_future": "verb/lt_1p_future",
    "2p_future": "verb/lt_2p_future",
    "3p-m_future": "verb/lt_3p_m_future",
    "3p-f_future": "verb/lt_3p_f_future",
}

TENSE_MAPPING = {
    "present_tense": "present",
    "past_tense": "past",
    "future": "future",
}


def main():
    """Add English conjugations to existing verbs."""
    print("Adding English conjugations to existing verbs in database...")

    session = create_database_session(constants.WORDFREQ_DB_PATH)

    # Get all verbs from database
    verbs_in_db = session.query(Lemma).filter(Lemma.pos_type == "verb").all()

    print(f"Found {len(verbs_in_db)} verbs in database")

    updated_count = 0
    skipped_count = 0
    forms_added = 0

    for lemma in verbs_in_db:
        # Find matching verb in verbs.py by Lithuanian translation
        lithuanian_infinitive = get_translation(session, lemma, "lt")

        if not lithuanian_infinitive or lithuanian_infinitive not in verbs_new:
            print(f"⚠️  Skipping {lemma.lemma_text} - no match in verbs.py")
            skipped_count += 1
            continue

        verb_data = verbs_new[lithuanian_infinitive]

        # Check if this verb already has English conjugations
        existing_english_forms = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == "en",
                DerivativeForm.is_base_form == False,
            )
            .count()
        )

        if existing_english_forms > 0:
            print(
                f"✓ Skipping {lemma.lemma_text} - already has {existing_english_forms} English conjugations"
            )
            skipped_count += 1
            continue

        # Add English conjugations
        print(f"Adding English conjugations for {lemma.lemma_text}...")
        verb_forms_added = 0

        for tense_key, tense_data in verb_data.items():
            if tense_key == "english":
                continue

            tense_suffix = TENSE_MAPPING.get(tense_key)
            if not tense_suffix:
                continue

            for person_key, person_data in tense_data.items():
                form_key = f"{person_key}_{tense_suffix}"
                grammatical_form = FORM_MAPPING.get(form_key)

                if not grammatical_form:
                    continue

                english_text = person_data.get("english")
                if not english_text:
                    continue

                # Create English conjugation form
                english_token = add_word_token(session, english_text, "en")
                english_form = DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=english_text,
                    word_token_id=english_token.id,
                    language_code="en",
                    grammatical_form=grammatical_form,
                    is_base_form=False,
                    verified=True,
                )
                session.add(english_form)
                verb_forms_added += 1

        if verb_forms_added > 0:
            session.commit()
            print(f"✅ Added {verb_forms_added} English conjugations for {lemma.lemma_text}")
            updated_count += 1
            forms_added += verb_forms_added

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Verbs in database: {len(verbs_in_db)}")
    print(f"Updated with English conjugations: {updated_count}")
    print(f"Skipped (already had conjugations or no match): {skipped_count}")
    print(f"Total English conjugation forms added: {forms_added}")
    print("=" * 60)

    session.close()


if __name__ == "__main__":
    main()
