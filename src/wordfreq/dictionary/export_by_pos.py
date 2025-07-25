#!/usr/bin/python3

"""
Generate HTML pages that display all words for a part-of-speech subtype in tabular form.

This script:
1. Queries the linguistic database for words organized by POS subtypes
2. Generates static HTML files for each POS subtype
3. Places these files in a subdirectory of OUTPUT_DIR
"""

import os
import logging
import argparse
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func

import shutil

import constants
from wordfreq.storage import database
from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm, ExampleSentence

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Output directory
POS_SUBTYPE_DIR = os.path.join(constants.OUTPUT_DIR, "pos_subtypes")

# Style and script constants
CSS_FILENAME = "pos_subtypes.css"
CSS_TEMPLATE_PATH = os.path.join(constants.WORDFREQ_TEMPLATE_DIR, CSS_FILENAME)
JS_FILENAME = "pos_subtypes.js"
JS_TEMPLATE_PATH = os.path.join(constants.WORDFREQ_TEMPLATE_DIR, JS_FILENAME)

def ensure_directory(directory: str) -> None:
    """Ensure the specified directory exists."""
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")


def get_words_by_pos_subtype(session, pos_type: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get words organized by POS subtype for a specific part of speech.
    
    Args:
        session: Database session
        pos_type: Part of speech (noun, verb, adjective, adverb)
        
    Returns:
        Dictionary mapping subtypes to lists of word data
    """
    # Get the available subtypes for this POS
    subtypes = linguistic_db.get_subtype_values_for_pos(pos_type)
    
    # Query word tokens with derivative forms and lemmas of the specified part of speech
    query = session.query(
            WordToken, 
            DerivativeForm,
            Lemma
        ).join(
            DerivativeForm, WordToken.id == DerivativeForm.word_token_id
        ).join(
            Lemma, DerivativeForm.lemma_id == Lemma.id
        ).filter(
            Lemma.pos_type == pos_type
        ).order_by(
            WordToken.frequency_rank.nullslast(), 
            WordToken.token
        )
    
    # Organize by subtype, combining multiple derivative forms for the same word token
    words_by_subtype = defaultdict(list)
    word_token_data = {}  # Track data by word token to combine forms
    
    for word_token, derivative_form, lemma in query:
        subtype = lemma.pos_subtype or "uncategorized"
        if subtype not in subtypes:
            subtype = "uncategorized"
        
        # Create a unique key for this word token + lemma combination
        word_key = (word_token.token, lemma.lemma_text, lemma.definition_text)
        
        if word_key not in word_token_data:
            # Get the first example if available
            example = ""
            if derivative_form.example_sentences and len(derivative_form.example_sentences) > 0:
                example = derivative_form.example_sentences[0].example_text
                
            # Truncate definition and example if too long
            def_text = lemma.definition_text
            if len(def_text) > 150:
                def_text = def_text[:147] + "..."
                
            if len(example) > 120:
                example = example[:117] + "..."
            
            word_token_data[word_key] = {
                "word": word_token.token,
                "rank": word_token.frequency_rank,
                "lemma": lemma.lemma_text,
                "definition": def_text,
                "example": example,
                "pronunciation": derivative_form.phonetic_pronunciation or "",
                "ipa": derivative_form.ipa_pronunciation or "",
                "chinese": derivative_form.chinese_translation or "",
                "french": derivative_form.french_translation or "",
                "korean": derivative_form.korean_translation or "",
                "swahili": derivative_form.swahili_translation or "",
                "lithuanian": derivative_form.lithuanian_translation or "",
                "vietnamese": derivative_form.vietnamese_translation or "",
                "grammatical_forms": [derivative_form.grammatical_form],
                "subtype": subtype
            }
        else:
            # Add this grammatical form to the existing entry
            if derivative_form.grammatical_form not in word_token_data[word_key]["grammatical_forms"]:
                word_token_data[word_key]["grammatical_forms"].append(derivative_form.grammatical_form)
    
    # Group by subtype
    for word_data in word_token_data.values():
        subtype = word_data.pop("subtype")  # Remove subtype from the data dict
        # Convert grammatical forms list to a readable string
        word_data["forms"] = ", ".join(sorted(word_data["grammatical_forms"]))
        del word_data["grammatical_forms"]  # Remove the list, keep the string
        words_by_subtype[subtype].append(word_data)
    
    return words_by_subtype


def generate_pos_subtype_pages(session) -> None:
    """
    Generate HTML pages for each POS subtype.
    
    Args:
        session: Database session
    """
    # Ensure output directory exists
    ensure_directory(POS_SUBTYPE_DIR)
    
    # Copy static files (CSS and JS)
    copy_static_files()
    
    # Parts of speech to process
    pos_types = get_all_pos_types(session)
    
    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader(constants.WORDFREQ_TEMPLATE_DIR))
    
    # Generate index page
    generate_index_page(session, env, pos_types)
    
    # Generate individual POS type pages
    for pos_type in pos_types:
        logger.info(f"Processing {pos_type}...")
        
        # Get words by subtype
        words_by_subtype = get_words_by_pos_subtype(session, pos_type)
        
        if not words_by_subtype:
            logger.warning(f"No words found for POS type: {pos_type}")
            continue
        
        # Generate main POS type page
        generate_pos_type_page(env, pos_type, words_by_subtype)
        
        # Generate individual subtype pages
        for subtype, words in words_by_subtype.items():
            generate_subtype_page(env, pos_type, subtype, words)
    
    logger.info(f"Generated all POS subtype pages in {POS_SUBTYPE_DIR}")


def generate_index_page(session, env, pos_types: List[str]) -> None:
    """
    Generate the main index page with links to POS type pages.
    
    Args:
        session: Database session
        env: Jinja environment
        pos_types: List of POS types
    """
    pos_stats = {}
    
    for pos_type in pos_types:
        # Count word tokens and derivative forms for this POS
        word_count = session.query(func.count(WordToken.id.distinct()))\
            .join(DerivativeForm)\
            .join(Lemma)\
            .filter(Lemma.pos_type == pos_type)\
            .scalar() or 0
            
        derivative_form_count = session.query(func.count(DerivativeForm.id))\
            .join(Lemma)\
            .filter(Lemma.pos_type == pos_type)\
            .scalar() or 0
            
        # Count subtypes used
        subtype_count = session.query(func.count(Lemma.pos_subtype.distinct()))\
            .filter(
                Lemma.pos_type == pos_type,
                Lemma.pos_subtype != None
            ).scalar() or 0
        
        # Get top 5 most common words for this POS
        top_words = []
        query = session.query(WordToken.token)\
            .join(DerivativeForm)\
            .join(Lemma)\
            .filter(Lemma.pos_type == pos_type)\
            .order_by(WordToken.frequency_rank.nullslast())\
            .limit(5)
            
        for row in query:
            top_words.append(row[0])
        
        pos_stats[pos_type] = {
            "word_count": word_count,
            "definition_count": derivative_form_count,
            "subtype_count": subtype_count,
            "top_words": top_words
        }
    
    # Load template
    template = env.get_template('pos_index.html')
    
    # Render template
    html = template.render(
        pos_stats=pos_stats,
        css_file=CSS_FILENAME
    )
    
    # Write to file
    with open(os.path.join(POS_SUBTYPE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info("Generated index page")


def generate_pos_type_page(env, pos_type: str, words_by_subtype: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Generate a page for a specific part of speech with links to subtypes.
    
    Args:
        env: Jinja environment
        pos_type: Part of speech
        words_by_subtype: Words organized by subtype
    """
    # Calculate stats for each subtype
    subtype_stats = {}
    total_words = 0
    
    for subtype, words in words_by_subtype.items():
        word_count = len(words)
        total_words += word_count
        
        # Get top 5 words by frequency rank
        top_words = sorted(words, key=lambda w: float("inf") if w.get("rank") is None else w.get("rank"))[:5]
        top_words = [word["word"] for word in top_words]
        
        subtype_stats[subtype] = {
            "word_count": word_count,
            "percentage": 0,  # Will calculate after loop
            "top_words": top_words
        }
    
    # Calculate percentages
    for subtype in subtype_stats:
        subtype_stats[subtype]["percentage"] = round(subtype_stats[subtype]["word_count"] / total_words * 100, 1)
    
    # Sort subtypes by word count
    sorted_subtypes = sorted(subtype_stats.items(), key=lambda x: x[1]["word_count"], reverse=True)
    
    # Load template
    template = env.get_template('pos_type.html')
    
    # Render template
    html = template.render(
        pos_type=pos_type,
        total_words=total_words,
        subtypes=subtype_stats,
        sorted_subtypes=sorted_subtypes,
        css_file=CSS_FILENAME
    )
    
    # Write to file
    with open(os.path.join(POS_SUBTYPE_DIR, f"{pos_type}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"Generated page for {pos_type}")


def generate_subtype_page(env, pos_type: str, subtype: str, words: List[Dict[str, Any]]) -> None:
    """
    Generate a page for a specific POS subtype.
    
    Args:
        env: Jinja environment
        pos_type: Part of speech
        subtype: Subtype
        words: List of words for this subtype
    """
    # Load template
    template = env.get_template('pos_subtype.html')
    
    # Render template
    html = template.render(
        pos_type=pos_type,
        subtype=subtype,
        words=words,
        css_file=CSS_FILENAME,
        js_file=JS_FILENAME
    )
    
    # Write to file
    filename = f"{pos_type}_{subtype}.html"
    with open(os.path.join(POS_SUBTYPE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(html)
    
    logger.info(f"Generated page for {pos_type} subtype {subtype}")


def copy_static_files() -> None:
    """Copy the CSS and JS files from templates to the output directory."""
    
    # Copy CSS file from templates to output directory
    shutil.copy2(CSS_TEMPLATE_PATH, os.path.join(POS_SUBTYPE_DIR, CSS_FILENAME))
    logger.info(f"Copied CSS file from templates to output directory: {CSS_FILENAME}")
    
    # Copy JS file from templates to output directory
    shutil.copy2(JS_TEMPLATE_PATH, os.path.join(POS_SUBTYPE_DIR, JS_FILENAME))
    logger.info(f"Copied JS file from templates to output directory: {JS_FILENAME}")


def get_all_pos_types(session) -> List[str]:
    """
    Get all part of speech types from the database.
    
    Args:
        session: Database session
        
    Returns:
        List of all POS types found in the database
    """
    pos_types = session.query(Lemma.pos_type.distinct()).all()
    return [pos_type[0] for pos_type in pos_types]

def generate_index_page_only(session) -> None:
    """
    Generate only the index page with links to all POS type pages.
    
    Args:
        session: Database session
    """
    # Ensure output directory exists
    ensure_directory(POS_SUBTYPE_DIR)
    
    # Copy static files (CSS and JS)
    copy_static_files()
    
    # Get all POS types from the database
    pos_types = get_all_pos_types(session)
    
    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader(constants.WORDFREQ_TEMPLATE_DIR))
    
    # Generate index page
    generate_index_page(session, env, pos_types)
    
    logger.info(f"Generated index page in {POS_SUBTYPE_DIR}")

def main():
    """Main function to run the generator."""
    parser = argparse.ArgumentParser(description="Generate HTML pages for POS subtypes")
    parser.add_argument("--db-path", type=str, default=constants.WORDFREQ_DB_PATH,
                        help="Path to linguistic database")
    parser.add_argument("--index-only", action="store_true",
                        help="Generate only the index page")
    args = parser.parse_args()

    # Create output directory
    ensure_directory(POS_SUBTYPE_DIR)
    
    # Connect to database and generate pages
    session = get_session(args.db_path)
    try:
        if args.index_only:
            # Generate only the index page
            generate_index_page_only(session)
        else:
            # Generate all pages (index, POS types, and subtypes)
            generate_pos_subtype_pages(session)
    finally:
        session.close()
    
    logger.info(f"HTML generation complete. Files written to: {POS_SUBTYPE_DIR}")
    

if __name__ == "__main__":
    main()