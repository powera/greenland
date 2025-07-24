#!/usr/bin/python3

"""
Dictionary Generator

This module generates dictionary files in the trakaido_wordlists format from the wordfreq database.
It creates Python files with structured word entries for different categories.
"""

import json
import os
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from wordfreq.models.schema import Lemma, DerivativeForm, AlternativeForm
from wordfreq.linguistic_db import create_database_session

def get_lemmas_by_category(session: Session, category: str) -> List[Lemma]:
    """Get all lemmas for a specific category, ordered by GUID."""
    return session.query(Lemma)\
        .filter(Lemma.category == category)\
        .filter(Lemma.guid != None)\
        .order_by(Lemma.guid)\
        .all()

def get_primary_english_form(session: Session, lemma: Lemma) -> str:
    """Get the primary English form for a lemma."""
    # First try to find a base form with English translation
    base_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.is_base_form == True)\
        .all()
    
    for form in base_forms:
        if form.word_token and form.word_token.token:
            return form.word_token.token
    
    # Fallback to lemma text
    return lemma.lemma_text

def get_primary_lithuanian_form(session: Session, lemma: Lemma) -> str:
    """Get the primary Lithuanian form for a lemma."""
    # First try to find a base form with Lithuanian translation
    base_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.is_base_form == True)\
        .filter(DerivativeForm.lithuanian_translation != None)\
        .all()
    
    for form in base_forms:
        if form.lithuanian_translation:
            return form.lithuanian_translation
    
    # Try any derivative form with Lithuanian translation
    any_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.lithuanian_translation != None)\
        .first()
    
    if any_forms and any_forms.lithuanian_translation:
        return any_forms.lithuanian_translation
    
    # Fallback to lemma text (might be Lithuanian)
    return lemma.lemma_text

def get_alternatives_for_lemma(session: Session, lemma: Lemma) -> Dict[str, List[str]]:
    """Get alternative forms for a lemma, organized by language."""
    alternatives = {'english': [], 'lithuanian': []}
    
    alt_forms = session.query(AlternativeForm)\
        .filter(AlternativeForm.lemma_id == lemma.id)\
        .all()
    
    for alt in alt_forms:
        if alt.language in alternatives:
            alternatives[alt.language].append(alt.alternative_text)
    
    return alternatives

def get_frequency_rank_for_lemma(session: Session, lemma: Lemma) -> Optional[int]:
    """Get the frequency rank for a lemma."""
    if lemma.frequency_rank:
        return lemma.frequency_rank
    
    # Try to get from derivative forms
    derivative_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .all()
    
    for form in derivative_forms:
        if form.word_token and form.word_token.frequency_rank:
            return form.word_token.frequency_rank
    
    return None

def generate_dictionary_entry(session: Session, lemma: Lemma) -> Dict[str, Any]:
    """Generate a dictionary entry for a lemma in the trakaido format."""
    english_form = get_primary_english_form(session, lemma)
    lithuanian_form = get_primary_lithuanian_form(session, lemma)
    alternatives = get_alternatives_for_lemma(session, lemma)
    frequency_rank = get_frequency_rank_for_lemma(session, lemma)
    
    # Parse tags from JSON
    tags = []
    if lemma.tags:
        try:
            tags = json.loads(lemma.tags)
        except json.JSONDecodeError:
            tags = []
    
    entry = {
        'guid': lemma.guid,
        'english': english_form,
        'lithuanian': lithuanian_form,
        'alternatives': alternatives,
        'metadata': {
            'difficulty_level': lemma.difficulty_level,
            'frequency_rank': frequency_rank,
            'tags': tags,
            'notes': lemma.notes or ''
        }
    }
    
    return entry

def generate_dictionary_file_content(session: Session, category: str) -> str:
    """Generate the complete content for a dictionary file."""
    lemmas = get_lemmas_by_category(session, category)
    
    if not lemmas:
        return f'"""\n{category.replace("_", " ").title()} - Dictionary Data\n\nNo entries found for this category.\n"""\n'
    
    # Generate header
    category_title = category.replace('_', ' ').title()
    header = f'''"""
{category_title} - Dictionary Data

This file contains detailed word entries for the "{category_title}" category.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., N14001)
- english: English word/phrase
- lithuanian: Lithuanian translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

'''
    
    # Generate entries
    entries = []
    for lemma in lemmas:
        entry_data = generate_dictionary_entry(session, lemma)
        
        # Format the entry as Python code
        entry_code = f"""{lemma.guid} = {{
  'guid': '{entry_data['guid']}',
  'english': '{entry_data['english']}',
  'lithuanian': '{entry_data['lithuanian']}',
  'alternatives': {{
    'english': {entry_data['alternatives']['english']},
    'lithuanian': {entry_data['alternatives']['lithuanian']}
  }},
  'metadata': {{
    'difficulty_level': {entry_data['metadata']['difficulty_level']},
    'frequency_rank': {entry_data['metadata']['frequency_rank']},
    'tags': {entry_data['metadata']['tags']},
    'notes': '{entry_data['metadata']['notes']}'
  }}
}}"""
        entries.append(entry_code)
    
    return header + '\n\n'.join(entries) + '\n'

def generate_dictionary_file(session: Session, category: str, output_dir: str) -> str:
    """Generate a dictionary file for a specific category."""
    content = generate_dictionary_file_content(session, category)
    filename = f"{category}_dictionary.py"
    filepath = os.path.join(output_dir, filename)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def generate_all_dictionary_files(output_dir: str, db_path: Optional[str] = None) -> List[str]:
    """Generate dictionary files for all categories that have lemmas."""
    session = create_database_session(db_path) if db_path else create_database_session()
    
    try:
        # Get all categories that have lemmas with GUIDs
        categories = session.query(Lemma.category)\
            .filter(Lemma.category != None)\
            .filter(Lemma.guid != None)\
            .distinct()\
            .all()
        
        generated_files = []
        for (category,) in categories:
            if category:
                filepath = generate_dictionary_file(session, category, output_dir)
                generated_files.append(filepath)
                print(f"Generated: {filepath}")
        
        return generated_files
    
    finally:
        session.close()

def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate dictionary files from wordfreq database')
    parser.add_argument('--output-dir', '-o', required=True, help='Output directory for dictionary files')
    parser.add_argument('--category', '-c', help='Generate file for specific category only')
    parser.add_argument('--db-path', help='Path to database file (optional)')
    
    args = parser.parse_args()
    
    if args.category:
        session = create_database_session(args.db_path) if args.db_path else create_database_session()
        try:
            filepath = generate_dictionary_file(session, args.category, args.output_dir)
            print(f"Generated: {filepath}")
        finally:
            session.close()
    else:
        generated_files = generate_all_dictionary_files(args.output_dir, args.db_path)
        print(f"Generated {len(generated_files)} dictionary files")

if __name__ == '__main__':
    main()